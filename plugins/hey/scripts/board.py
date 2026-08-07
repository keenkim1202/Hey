#!/usr/bin/env python3
"""hey board — the daily record and the morning/evening cards.

Three things are counted and written to `stats.jsonl`.
    closed   boxes closed in the ledger that day, converted to AI-days
    code     lines added and removed that day, across every worktree of the project
    tokens   Claude Code transcript usage that day

**None of them is ranked.** Days used to be scored against each other here -- a board,
a streak, a weekly pace, a personal best. Closed work rests on estimates the tool itself
cannot calibrate, and code and tokens measure activity rather than accomplishment, so
every one of those numbers dressed a bookkeeping choice as a result. What is left is the
record and the two cards that read it back. No user data is ever sent or received.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import strings as S  # noqa: E402
from hey import (  # noqa: E402
    Ledger, ahead_of_base, card_width, day_range, die, fmt_date, load_config, merge_stats,
    clip_to, need_history, project_base, projects_in_scope, read_stats,
    record_progress, today_str, unpushed, worktree_roots, _sh,
)

TRANSCRIPTS = Path(os.environ.get("HEY_TRANSCRIPTS", Path.home() / ".claude" / "projects"))


# ---------------------------------------------------------------- collection


def code_lines(project: dict, on: str, author: str | None) -> dict:
    """Lines added and removed in commits made that day, across every worktree."""
    root = Path(project["root"])
    seen_commits: set[str] = set()
    added = deleted = commits = 0
    for w in worktree_roots(root):
        cmd = ["git", "log", "--all", "--no-merges", *day_range(on),
               "--format=__C__%H", "--numstat"]
        if author:
            cmd.append(f"--author={author}")
        out = _sh(cmd, w)
        cur = None
        for ln in out.split("\n"):
            if ln.startswith("__C__"):
                cur = ln[5:]
                if cur not in seen_commits:
                    seen_commits.add(cur)
                    commits += 1
                    cur = "new"
                else:
                    cur = None
                continue
            if cur != "new" or not ln.strip():
                continue
            parts = ln.split("\t")
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                added += int(parts[0])
                deleted += int(parts[1])
    return {"added": added, "deleted": deleted, "commits": commits}


def token_usage(project: dict | None, on: str) -> dict:
    """Transcript usage for that day. With a project, only sessions under its worktrees.

    Filtering on the main root alone would drop nearly everything: a linked worktree
    normally lives outside the repository it belongs to, and `code_lines` already counts
    all of them. The two metrics have to agree on what "this project" means.
    """
    if not TRANSCRIPTS.is_dir():
        return {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0, "turns": 0}
    prefixes = [str(w) for w in worktree_roots(Path(project["root"]))] if project else []
    tot = {"in": 0, "out": 0, "cache_read": 0, "cache_write": 0, "turns": 0}
    for f in TRANSCRIPTS.glob("*/*.jsonl"):
        # Every live session writes into this directory, and `collect` runs at the end of
        # the day while some of them are still open. A file rotated away between the glob
        # and the stat took the whole command down with it -- `f.open` was already guarded
        # against exactly that, one line further on.
        try:
            stale = datetime.fromtimestamp(f.stat().st_mtime).date() < date.fromisoformat(on)
        except OSError:
            continue
        if stale:
            continue
        try:
            fh = f.open(errors="replace")
        except OSError:
            continue
        # Single transcripts reach tens of MB. Stream instead of reading the whole file.
        with fh:
            for ln in fh:
                if '"usage"' not in ln:
                    continue
                try:
                    d = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                ts = d.get("timestamp")
                if not ts or _local_day(ts) != on:
                    continue
                cwd = str(d.get("cwd", ""))
                # Compared as a path, not as a string. A raw `startswith` charges
                # `/w/alpha-ios` to a project rooted at `/w/alpha` -- and a suffixed
                # sibling is how these directories are normally named, so the two
                # projects' token counts silently merge into one of them.
                if prefixes and not any(cwd == x or cwd.startswith(x + os.sep)
                                        for x in prefixes):
                    continue
                u = (d.get("message") or {}).get("usage") or {}
                tot["in"] += u.get("input_tokens", 0)
                tot["out"] += u.get("output_tokens", 0)
                tot["cache_read"] += u.get("cache_read_input_tokens", 0)
                tot["cache_write"] += u.get("cache_creation_input_tokens", 0)
                tot["turns"] += 1
    return tot


def _local_day(ts: str) -> str:
    """Convert a transcript UTC timestamp to a local calendar date."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return dt.astimezone().date().isoformat()


def total_tokens(row: dict) -> int:
    """Cache reads are excluded.

    Including `cache_read` prints hundreds of millions on long sessions and turns the
    metric into "how much cache was reused". Input, output and cache writes stay closer
    to what was actually produced. Cache reads are still stored in the record.
    """
    t = row.get("tokens") or {}
    return t.get("in", 0) + t.get("out", 0) + t.get("cache_write", 0)


def total_code(row: dict) -> int:
    c = row.get("code") or {}
    return c.get("added", 0) + c.get("deleted", 0)


LANG = S.lang(load_config())
_L = S.METRIC_LABELS[LANG]
_U = S.UNITS[LANG]

# (label, value, format, was it measured at all). The fourth is not the same question as
# "is the value zero", and reading a zero as an answer to it is what let a day nothing was
# measured on count as a day that produced nothing -- and, the other way round, let a
# recorded zero drop out of the average that is supposed to include it. A baseline day
# carries no `earned_ai`; a day collected before `code` existed carries no `code`.
METRICS = {
    "ai": (_L["ai"], lambda r: r.get("earned_ai", 0.0), lambda v: f"{v:.2f}{_U['aid']}",
           lambda r: "earned_ai" in r),
    "code": (_L["code"], total_code, lambda v: f"{int(v):,}{_U['lines']}",
             lambda r: r.get("code") is not None),
    "tokens": (_L["tokens"], total_tokens, lambda v: f"{human_tokens(v)}{_U['tok']}",
               lambda r: r.get("tokens") is not None),
}


def contradicts_zero(row: dict | None) -> bool:
    """Did this day produce code or tokens while closing no work?

    That pair is the only thing the zero note has to say -- it names two candidate causes,
    an item sized too large or a box nobody ticked, and both are checkable. On a day that
    produced nothing at all there is no contradiction to name: the card already says "no
    record", and adding "work happened" beside it would make one line contradict the other.
    """
    if row is None or "earned_ai" not in row or row["earned_ai"]:
        return False
    return bool(total_code(row) or total_tokens(row))


def short_date(iso: str) -> str:
    """`08-04 (Tue)` for boards. No year."""
    d = date.fromisoformat(iso)
    return f"{iso[5:]} ({S.WEEKDAYS[LANG][d.weekday()]})"


def human_tokens(n: float) -> str:
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


# ---------------------------------------------------------------- recording


def cmd_collect(args, cfg):
    on = args.date or today_str()
    projs = projects_in_scope(cfg, args.scope, args.project)
    if not projs:
        die("no project in scope. Register one with `hey.py add <path>`")
    for p in projs:
        fields = {}
        root = Path(p["root"])
        # Box state is only ever the ledger's *current* state -- there is no history in the
        # file. Stamping it under an earlier date than a record that already exists moves
        # which day counts as the baseline, and the newer day then diffs against an
        # identical snapshot and reads 0 forever. Code and tokens do backfill, because git
        # and the transcripts keep their own history, so those are still collected.
        later = [r for r in read_stats()
                 if r["project"] == p["name"] and r.get("items") and r["date"] > on]
        if Path(p["ledger"]).exists() and not later:
            fields.update(record_progress(Ledger(p), on))
        elif later:
            print(f"[{p['name']}] {fmt_date(on)} is before a day already recorded, so box "
                  f"state is left alone -- the ledger only holds today. Code and tokens only")
        # Resolved per project: a repository may carry its own committer identity.
        author = (args.author or cfg.get("author")
                  or _sh(["git", "config", "user.email"], root))
        if not author:
            print(f"[{p['name']}] no git author resolved, so code counts every author's "
                  f"commits. Pass --author to narrow it")
        fields["code"] = code_lines(p, on, author)
        fields["tokens"] = token_usage(p, on)
        merge_stats(on, p["name"], fields)
        c, t = fields["code"], fields["tokens"]
        if "cb_done" not in fields:
            closed = "not collected - a later day is already recorded"
        elif fields.get("baseline"):
            closed = "baseline - counted from the next record on"
        else:
            closed = f"{fields.get('earned_ai', 0)} AI-days"
        print(f"[{p['name']}] {fmt_date(on)} recorded"
              f"\n  closed  {closed}"
              f"\n  code    +{c['added']} -{c['deleted']} ({c['commits']} commits)"
              f"\n  tokens  {human_tokens(total_tokens(fields))} ({t['turns']} turns)")


# ---------------------------------------------------------------- leaderboard




def flair(kind: str, on: str, **kw) -> str:
    return S.flair(kind, on, LANG, **kw)






# ---------------------------------------------------------------- streak and goals






# ---------------------------------------------------------------- cards
#
# When a skill fires 8-10 separate commands, every round trip costs latency and every
# line of output lands in the context window. These commands gather what the morning and
# evening need and print **one compact card**.


RULE = "─"
DOT = "·"


WIDTH = card_width()[0]  # Resolved once at import, so the layout defaults below inherit it.
INDENT = "   "  # Content sits under a section marker, which is two columns plus a space.


def head(title: str, right: str = "", width: int = WIDTH) -> str:
    left = f"{RULE * 3} {title} "
    fill = max(1, width - _w(left) - _w(right) - 1)
    return f"{left}{RULE * fill} {right}"


def clip(s: str, width: int = WIDTH) -> str:
    """Clip by display width. Markdown emphasis is noise in a terminal, so it is stripped.

    For prose use `fold` instead — see why there.
    """
    s = s.replace("**", "")
    if _w(s) <= width:
        return s
    out = ""
    for c in s:
        if _w(out) + _w(c) > width - 1:
            return out + "…"
        out += c
    return out


def _cut(s: str, width: int) -> str:
    """The longest prefix of `s` that fits, with an ellipsis when something was dropped."""
    return clip_to(s, width)


def _pieces(text: str) -> list:
    """`(wants a space in front, text)` pairs, split at every place a line may break.

    Spaces are not the only opportunity. A run of symbols joined by `·` or `/` carries no
    space at all, so breaking on spaces alone splits an identifier down the middle —
    `URLSessionCo` / `nfig` reads worse than dropping the tail outright, and it is no
    longer greppable. The separator stays attached to the piece on its left.
    """
    out = []
    for w, word in enumerate(text.split()):
        parts = [p for p in re.split(r"(?<=[·/,;])", word) if p]
        out += [(w > 0 and i == 0, p) for i, p in enumerate(parts)]
    return out


def _break_lines(text: str, width: int) -> list:
    """Lines that each fit `width` columns, breaking at spaces and separators first."""
    out, cur = [], ""
    for wants_space, piece in _pieces(text):
        joiner = " " if wants_space and cur else ""
        if _w(cur + joiner + piece) <= width:
            cur += joiner + piece
            continue
        if cur:
            out.append(cur)
            cur = ""
        # Still too long with a line to itself: a path with no separator in it at all.
        while _w(piece) > width:
            head_ = ""
            for c in piece:
                if _w(head_) + _w(c) > width:
                    break
                head_ += c
            out.append(head_)
            piece = piece[len(head_):]
        cur = piece
    if cur:
        out.append(cur)
    return out


def fold(text: str, first: str, cont: str, limit: int = 2, width: int = WIDTH) -> list:
    """Lay prose out over up to `limit` lines instead of cutting it off at one.

    Korean and Japanese take two columns a character, so a 78-column card holds about
    thirty-five of them. Clipping a sentence there throws the sentence away — the reader
    gets a subject and no verb. Folding keeps it, and `limit` keeps one long bullet from
    eating the card.
    """
    text = text.replace("**", "")
    room = width - max(_w(first), _w(cont))
    body = _break_lines(text, room)
    kept = body[:limit]
    if len(body) > limit and kept:
        kept[-1] = _cut(" ".join(body[limit - 1:]), room)
    return [(first if i == 0 else cont) + ln for i, ln in enumerate(kept)]


def _w(s: str) -> int:
    """Display width in terminal columns.

    Only East Asian wide and fullwidth glyphs take two columns. Treating every
    non-ASCII character as wide mismeasures the card's own furniture — box drawing,
    block meters, the ellipsis — and both the rules and the clipping come out short.
    """
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _w(s))


def rpad(s: str, width: int) -> str:
    """Right-align by display width. `str.rjust` counts characters, so a Korean unit
    suffix would pull the column out of true."""
    return " " * max(0, width - _w(s)) + s




def prev_workday(on: date) -> date:
    d = on - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _lines(cmd: list, cwd: Path) -> list:
    out = _sh(cmd, cwd)
    return [ln for ln in out.split("\n") if ln.strip()]


def _worktree_state(root: Path, base: str | None) -> list:
    """Per worktree: (path, branch, uncommitted files, unpushed commits, has upstream).

    Unpushed rather than ahead-of-base. A pushed branch waiting on review is ahead of the
    base too, and listing it as state about to be lost is the kind of false alarm that
    teaches the reader to skip the section that holds the real ones.
    """
    rows = []
    for w in worktree_roots(root):
        st = _lines(["git", "status", "--short"], w)
        gone, has_up = unpushed(w, base)
        rows.append((w, _sh(["git", "branch", "--show-current"], w), len(st), gone, has_up))
    return rows


def _touched(worktree: Path, on: str, limit: int = 2) -> list:
    """Files touched that day on the worktree's **current branch**.

    Passing `--all` would scan every branch and print an identical list for every
    worktree, so it is deliberately omitted.
    """
    files = _lines(["git", "log", *day_range(on),
                    "--name-only", "--format="], worktree)
    return sorted(set(files))[:limit]


def _ledger_notes(led, on: str) -> list:
    body = led.section_body("notes")
    out, hit = [], False
    for ln in body:
        if m := led.DAY.match(ln):
            hit = m[1] == on
        elif hit and ln.strip().startswith("- "):
            out.append(ln.strip()[2:])
    return out


def _log_for(led, on: str) -> list:
    return next((b for d, b in led.log_days() if d == on), [])


def card(p: dict, cfg: dict, on: str, mode: str) -> list:
    """mode: 'brief' (start of day) or 'wrap' (end of day)."""
    led = Ledger(p)
    g = led.progress()
    root = Path(p["root"])
    base = project_base(cfg, p)
    rows = [r for r in read_stats() if r["project"] == p["name"]]
    focus = on if mode == "wrap" else prev_workday(date.fromisoformat(on)).isoformat()
    out = [head(p["name"], fmt_date(on))]

    # Bullets fold onto a second line rather than being cut off, so three of them cost
    # about what five clipped ones did and all three can actually be read.
    bullet, under = f"{INDENT}{DOT} ", f"{INDENT}  "

    def section(key: str, title: str) -> list:
        return ["", f"{S.MARK[key]} {title}"]

    # -- what happened
    label = (S.card("today_did", LANG) if mode == "wrap"
             else f'{S.card("yesterday", LANG)}  {short_date(focus)}')
    logged = _log_for(led, focus)
    out += section("log", label)
    if logged:
        for b in logged[:3]:
            out += fold(b, bullet, under)
    else:
        commits = _lines(["git", "log", "--all", *day_range(focus),
                          "--format=%h %s"], root)
        if commits:
            for c in commits[:3]:
                out += fold(c, bullet, under)
        else:
            out.append(f'{bullet}{S.card("no_record", LANG)}')

    # -- easily-lost state
    wts = [w for w in _worktree_state(root, base) if w[2] or w[3]]
    if wts:
        out += section("resume", S.card("loose" if mode == "wrap" else "resume", LANG))
        for w, br, dirty, gone, has_up in wts[:4]:
            bits = []
            if gone:
                # Say which of the two it is. "No PR" was the old wording and it asserted
                # something never checked -- nothing here queries a forge for pull requests.
                bits.append(S.card("commits_unpushed" if has_up else "commits_unpushed_all",
                                   LANG, n=gone))
            if dirty:
                bits.append(S.card("uncommitted", LANG, n=dirty))
            # Which item this branch belongs to, when the ledger says. The whole point of
            # this section is knowing what is at risk, and a directory name is not that.
            owner = led.item_for_branch(br)
            if owner:
                bits.append(owner["title"])
            out.append(clip(f"{bullet}{w.name}  {br or 'detached'}  {' · '.join(bits)}"))
            for f in _touched(w, focus):
                out.append(clip(f"{INDENT}    {f}"))

    # -- notes
    notes = _ledger_notes(led, focus if mode == "wrap" else on)
    if notes:
        out += section("notes", f'{S.card("notes", LANG)} {len(notes)}')
        for n in notes[:3]:
            out += fold(n, bullet, under)

    # -- progress
    remain = round(g["wip_ai"] + g["todo_ai"], 2)
    done_ai = f'{g["done_ai"]:.1f}'
    W, V = 12, 27  # label and value columns, sized so value+unit+denominator all fit
    # No percentage and no meter on the checklist row. The count is exact and the
    # denominator is whatever the user chose to write, so a filled bar reads as "you are
    # this far along" on the strength of how finely the items happen to be split. Adding
    # subitems would push the bar backwards without anything being undone.
    out += section("progress", S.card("progress_head", LANG)) + [
            f'{INDENT}{pad(S.card("checklist", LANG), W)}'
            f'{S.card("boxes_closed", LANG, done=g["cb_done"], total=g["cb_total"])}',
            f'{INDENT}{pad(S.card("effort", LANG), W)}'
            f'{pad(S.card("effort_val", LANG, done=done_ai, total=g["total_ai"]), V)}'
            f'{S.card("effort_note", LANG, left=remain, wip=g["wip_ai"])}']
    # -- output
    win = [r for r in rows
           if (date.fromisoformat(focus) - timedelta(days=14)).isoformat() <= r["date"] <= focus]
    if win:
        out += section("results", f'{S.card("results", LANG)}  {short_date(focus)}')
        # Three figures for the day, and nothing to compare them against. A personal best
        # survived here after the board, the streak and the rank were taken out, which made
        # this file claim in its own docstring that days are no longer scored against each
        # other while still printing the highest one.
        for m in ("ai", "code", "tokens"):
            lbl, get, f, _ = METRICS[m]
            mine = next((get(r) for r in win if r["date"] == focus), 0)
            out.append(f"{INDENT}{pad(lbl, 9)}{f(mine)}")
        # The zero line moved here when the board it used to live on was removed. It is the
        # one piece of commentary that does work, and only in the case `contradicts_zero`
        # picks out.
        if contradicts_zero(next((r for r in win if r["date"] == focus), None)):
            # Folded, not appended: these lines run past 72 columns and the card has a
            # floor of 72. On the board it used to sit on there was no width contract.
            out += fold(flair("zero", focus), INDENT, INDENT, limit=2)

    # -- what is next
    nxt = led.next_up()
    if nxt:
        out += section("next", S.card("tomorrow_next" if mode == "wrap"
                                      else "today_next", LANG))
        # Three lines here, two everywhere else: these are the items the reader is about
        # to start, and a next-up entry carries the reason it comes first. Losing that
        # to an ellipsis costs more than the three lines of card it buys back.
        for n in nxt[:3]:
            out += fold(n, INDENT, f"{INDENT}   ", limit=3)

    # -- blocked
    blocked = led.blockers(on)
    if blocked:
        out += section("blocked", f'{S.card("blocked", LANG)} {len(blocked)}')
        # The title, not the key: `<phase>|<name>` is how the scripts join records to
        # items, and it has no business in something a person reads. Oldest first, because
        # age is what decides which one to go chase; the undated ones sort last rather
        # than pretending to be new.
        ranked = sorted(blocked, key=lambda b: -(b["days"] if b["days"] is not None else -1))
        for b in ranked[:3]:
            age = f'  {S.card("waiting_days", LANG, n=b["days"])}' if b["days"] is not None else ""
            out += fold(b["title"] + age, bullet, under, limit=1)
        if len(ranked) > 3:
            # Name what shows the rest. A count with no next step is a dead end on a card
            # the reader cannot scroll or expand.
            out.append(f'{bullet}{S.card("and_more", LANG, n=len(ranked) - 3)}')

    return out


def cmd_card(args, cfg):
    on = args.date or today_str()
    projs = projects_in_scope(cfg, args.scope, args.project)
    if not projs:
        die("no project in scope. Register one with `hey.py add <path>`")
    for p in projs:
        if not Path(p["ledger"]).exists():
            print(f"[{p['name']}] ledger missing: {p['ledger']}")
            continue
        for ln in card(p, cfg, on, args.mode):
            print(ln)
        print()


def main() -> None:
    ap = argparse.ArgumentParser(prog="board.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        sp = sub.add_parser(name, **kw)
        sp.set_defaults(fn=fn)
        sp.add_argument("--project")
        sp.add_argument("--scope", choices=["current", "all"])
        return sp

    sp = add("collect", cmd_collect, help="record today's closed/code/token totals")
    sp.add_argument("--date")
    sp.add_argument("--author", help="git author filter (default: git config user.email)")

    for name, mode, helptext in (("brief", "brief", "morning card (one call)"),
                                 ("wrap", "wrap", "end-of-day card (one call)")):
        sp = add(name, cmd_card, help=helptext)
        sp.set_defaults(mode=mode)
        sp.add_argument("--date")

    args = ap.parse_args()
    args.fn(args, load_config())


if __name__ == "__main__":
    main()
