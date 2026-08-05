#!/usr/bin/env python3
"""hey board — daily output, leaderboards and the morning/evening cards.

Three things are counted.
    closed   boxes closed in the ledger that day, converted to AI-days
    code     lines added and removed that day, across every worktree of the project
    tokens   Claude Code transcript usage that day

Ranking compares **only against your own past records**. No user data is ever sent
or received.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import strings as S  # noqa: E402
from hey import (  # noqa: E402
    Ledger, ahead_of_base, die, fmt_date, load_config, merge_stats, project_base,
    project_setting, projects_in_scope, read_stats, record_progress, save_config,
    today_str, worktree_roots, _sh,
)

TRANSCRIPTS = Path(os.environ.get("HEY_TRANSCRIPTS", Path.home() / ".claude" / "projects"))
BAR_W = 20
EIGHTHS = "▏▎▍▌▋▊▉█"


# ---------------------------------------------------------------- collection


def code_lines(project: dict, on: str, author: str | None) -> dict:
    """Lines added and removed in commits made that day, across every worktree."""
    root = Path(project["root"])
    seen_commits: set[str] = set()
    added = deleted = commits = 0
    for w in worktree_roots(root):
        cmd = ["git", "log", "--all", "--no-merges",
               f"--since={on} 00:00", f"--until={on} 23:59",
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
        if datetime.fromtimestamp(f.stat().st_mtime).date() < date.fromisoformat(on):
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
                if prefixes and not any(cwd.startswith(x) for x in prefixes):
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

METRICS = {
    "ai": (_L["ai"], lambda r: r.get("earned_ai", 0.0), lambda v: f"{v:.2f}"),
    "code": (_L["code"], total_code, lambda v: f"{int(v):,}{_U['lines']}"),
    "tokens": (_L["tokens"], total_tokens, lambda v: human_tokens(v)),
}


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
        if Path(p["ledger"]).exists():
            fields.update(record_progress(Ledger(p), on))
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
        closed = ("baseline - counted from the next record on" if fields.get("baseline")
                  else f"{fields.get('earned_ai', 0)} AI-days")
        print(f"[{p['name']}] {fmt_date(on)} recorded"
              f"\n  closed  {closed}"
              f"\n  code    +{c['added']} -{c['deleted']} ({c['commits']} commits)"
              f"\n  tokens  {human_tokens(total_tokens(fields))} ({t['turns']} turns)")


# ---------------------------------------------------------------- leaderboard


def bar(value: float, top: float, width: int = BAR_W) -> str:
    if top <= 0:
        return ""
    filled = value / top * width
    full = int(filled)
    rem = filled - full
    out = "█" * full
    if full < width and rem >= 1 / 8:
        out += EIGHTHS[min(7, int(rem * 8)) - 1] if int(rem * 8) else ""
    return out


# Personality lines live in strings.py, with one pool per language.


def flair(kind: str, on: str, **kw) -> str:
    return S.flair(kind, on, LANG, **kw)


def leaderboard(rows: list[dict], on: str, metric: str, top_n: int) -> list[str]:
    label, get, fmt = METRICS[metric]
    scored = [(r["date"], get(r)) for r in rows if get(r)]
    if not scored:
        return [S.card("board_none", LANG, label=label)]
    today_val = next((v for d, v in scored if d == on), None)
    ranked = sorted(scored, key=lambda x: (-x[1], x[0]))
    peak = ranked[0][1]
    avg = sum(v for _, v in scored) / len(scored)
    rank = next((i + 1 for i, (d, _) in enumerate(ranked) if d == on), None)

    shown_val = fmt(today_val) if today_val is not None else "-"
    head = S.card("board_today", LANG, label=label, val=shown_val)
    tail = (S.card("board_rank", LANG, rank=rank, n=len(scored)) if rank
            else S.card("board_window", LANG, n=len(scored)))
    out = [f"{head:<28}{tail}", ""]
    shown = ranked[:top_n]
    if rank and rank > top_n:
        shown = ranked[: top_n - 1] + [(on, today_val)]
    for i, (d, v) in enumerate(shown):
        pos = next(j + 1 for j, (dd, _) in enumerate(ranked) if dd == d)
        note = (S.card("board_peak", LANG) if pos == 1
                else (S.card("board_is_today", LANG) if d == on else ""))
        out.append(f"{pos:2}  {short_date(d)}  {bar(v, peak):<{BAR_W}}  {fmt(v):>8}{note}")
    out.append(f"{'':4}{pad(S.card('board_avg', LANG), 9)}{bar(avg, peak):<{BAR_W}}  {fmt(avg):>8}")
    if today_val is None:
        return out
    out.append("")
    if today_val >= peak:
        out.append(f"{flair('peak', on)}  ({fmt(today_val)})")
    else:
        gap = peak - today_val
        share = today_val / peak if peak else 0
        kind = "close" if share >= 0.8 else ("mid" if share >= 0.4 else "far")
        out.append(flair(kind, on, gap=fmt(gap)))
    return out


def cmd_show(args, cfg):
    on = args.date or today_str()
    for p in projects_in_scope(cfg, args.scope, args.project):
        rows = [r for r in read_stats() if r["project"] == p["name"]]
        cutoff = (date.fromisoformat(on) - timedelta(days=args.window)).isoformat()
        rows = [r for r in rows if cutoff <= r["date"] <= on]
        print(f"[{p['name']}]")
        for ln in leaderboard(rows, on, args.metric, args.top):
            print(f"  {ln}" if ln else "")
        # A recorded-but-zero day never appears on the board, so say so explicitly.
        today_row = next((r for r in rows if r["date"] == on), None)
        if today_row and not METRICS[args.metric][1](today_row):
            print()
            print(f"  {flair('zero', on) if args.metric == 'ai' else 'Zero for today.'}")
        if args.metric == "ai":
            print()
            for m in ("code", "tokens"):
                label, get, fmt = METRICS[m]
                scored = [(r["date"], get(r)) for r in rows if get(r)]
                if not scored:
                    continue
                best = max(scored, key=lambda x: x[1])
                mine = next((v for d, v in scored if d == on), 0)
                print(f"  {pad(label, 9)}{pad(fmt(mine), 14)}"
                      f"{S.card('board_first', LANG)} {short_date(best[0])} {fmt(best[1])}")


# ---------------------------------------------------------------- streak and goals


def cmd_streak(args, cfg):
    for p in projects_in_scope(cfg, args.scope, args.project):
        rows = [r for r in read_stats() if r["project"] == p["name"] and "earned_ai" in r]
        if not rows:
            print(f"[{p['name']}] no records yet")
            continue
        thr = (args.threshold if args.threshold is not None
               else project_setting(cfg, p, "daily_goal_ai", 0.3))
        streak = best = 0
        for r in rows:
            if r["earned_ai"] >= thr:
                streak += 1
                best = max(best, streak)
            elif date.fromisoformat(r["date"]).weekday() < 5:
                streak = 0
        hit = [r for r in rows if r["earned_ai"] >= thr]
        print(f"[{p['name']}] against a daily goal of {thr} AI-days")
        print(f"  {streak} in a row (longest {best}) · hit on {len(hit)}/{len(rows)} days")
        print("  counted in recorded days - a day `collect` never ran on is not a gap")
        if streak and streak == best and streak >= 2:
            print(f"  {S.streak('record', LANG, n=streak)}")
        elif streak >= 5:
            print(f"  {S.streak('habit', LANG, n=streak)}")
        elif streak >= 2:
            print(f"  {S.streak('rolling', LANG, n=streak)}")
        elif streak == 1:
            print(f"  {S.streak('one', LANG)}")
        elif best >= 2:
            print(f"  {S.streak('broken', LANG, best=best)}")


def cmd_goal(args, cfg):
    """Read or set the goals. Goals are stored per project, not per machine."""
    projs = projects_in_scope(cfg, args.scope, args.project)
    if not projs:
        die("no project in scope. Register one with `hey.py add <path>`")

    if args.set is not None or args.daily is not None:
        for p in projs:
            if args.set is not None:
                p["weekly_goal_ai"] = args.set
            if args.daily is not None:
                p["daily_goal_ai"] = args.daily
            bits = [f"weekly {p['weekly_goal_ai']}"] if args.set is not None else []
            if args.daily is not None:
                bits.append(f"daily {p['daily_goal_ai']}")
            print(f"[{p['name']}] goal set: {' · '.join(bits)} AI-days")
        save_config(cfg)
        return

    on = date.fromisoformat(args.date or today_str())
    monday = on - timedelta(days=on.weekday())
    for p in projs:
        goal = project_setting(cfg, p, "weekly_goal_ai")
        if goal is None:
            print(f"[{p['name']}] no weekly goal set. Use `board.py goal --set 5.0`")
            continue
        rows = [r for r in read_stats()
                if r["project"] == p["name"]
                and monday.isoformat() <= r["date"] <= on.isoformat()]
        got = round(sum(r.get("earned_ai", 0) for r in rows), 2)
        workdays = sum(1 for n in range((on - monday).days + 1)
                       if (monday + timedelta(days=n)).weekday() < 5)
        expected = round(goal * workdays / 5, 2)
        gap = round(got - expected, 2)
        pace = "ahead" if gap > 0 else ("behind" if gap < 0 else "exactly on pace")
        print(f"[{p['name']}] this week (Mon {monday.isoformat()} ~ {on.isoformat()})")
        print(f"  goal {goal} · so far {got} · expected by now {expected}"
              f" -> {abs(gap)} {pace}")
        print(f"  {bar(got, goal, 30):<30} {round(got / goal * 100)}%")
        left = round(goal - got, 2)
        remaining_days = 5 - workdays
        if left > 0 and remaining_days > 0:
            print(f"  {left} left over {remaining_days} day(s) = {round(left / remaining_days, 2)}/day")


# ---------------------------------------------------------------- cards
#
# When a skill fires 8-10 separate commands, every round trip costs latency and every
# line of output lands in the context window. These commands gather what the morning and
# evening need and print **one compact card**.


RULE = "─"
DOT = "·"


WIDTH = 78  # Card width. Longer lines are clipped so nothing wraps in the terminal.


def head(title: str, right: str = "", width: int = WIDTH) -> str:
    left = f"{RULE * 3} {title} "
    fill = max(1, width - _w(left) - _w(right) - 1)
    return f"{left}{RULE * fill} {right}"


def clip(s: str, width: int = WIDTH) -> str:
    """Clip by display width. Markdown emphasis is noise in a terminal, so it is stripped."""
    s = s.replace("**", "")
    if _w(s) <= width:
        return s
    out = ""
    for c in s:
        if _w(out) + _w(c) > width - 1:
            return out + "…"
        out += c
    return out


def _w(s: str) -> int:
    """Display width in terminal columns.

    Only East Asian wide and fullwidth glyphs take two columns. Treating every
    non-ASCII character as wide mismeasures the card's own furniture — box drawing,
    block meters, the ellipsis — and both the rules and the clipping come out short.
    """
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - _w(s))


def meter(done: float, total: float, width: int = 24) -> str:
    if total <= 0:
        return "░" * width
    filled = min(width, int(round(done / total * width)))
    return "█" * filled + "░" * (width - filled)


def prev_workday(on: date) -> date:
    d = on - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _lines(cmd: list, cwd: Path) -> list:
    out = _sh(cmd, cwd)
    return [ln for ln in out.split("\n") if ln.strip()]


def _worktree_state(root: Path, base: str | None) -> list:
    """Per worktree: (path, branch, uncommitted files, commits ahead)."""
    rows = []
    for w in worktree_roots(root):
        st = _lines(["git", "status", "--short"], w)
        ahead, _ = ahead_of_base(w, base)
        rows.append((w, _sh(["git", "branch", "--show-current"], w), len(st), len(ahead)))
    return rows


def _touched(worktree: Path, on: str, limit: int = 2) -> list:
    """Files touched that day on the worktree's **current branch**.

    Passing `--all` would scan every branch and print an identical list for every
    worktree, so it is deliberately omitted.
    """
    files = _lines(["git", "log", f"--since={on} 00:00", f"--until={on} 23:59",
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

    # -- what happened
    label = (S.card("today_did", LANG) if mode == "wrap"
             else f'{S.card("yesterday", LANG)}  {short_date(focus)}')
    logged = _log_for(led, focus)
    out += ["", f" {label}"]
    if logged:
        out += [clip(f"   {DOT} {b}") for b in logged[:5]]
    else:
        commits = _lines(["git", "log", "--all", f"--since={focus} 00:00",
                          f"--until={focus} 23:59", "--format=%h %s"], root)
        out += ([clip(f"   {DOT} {c}") for c in commits[:4]] or
                [f'   {DOT} {S.card("no_record", LANG)}'])

    # -- easily-lost state
    wts = [w for w in _worktree_state(root, base) if w[2] or w[3]]
    if wts:
        out += ["", " " + S.card("loose" if mode == "wrap" else "resume", LANG)]
        for w, br, dirty, ahead in wts[:4]:
            bits = []
            if ahead:
                bits.append(S.card("commits_no_pr", LANG, n=ahead))
            if dirty:
                bits.append(S.card("uncommitted", LANG, n=dirty))
            out.append(clip(f"   {DOT} {w.name}  {br or 'detached'}  {' · '.join(bits)}"))
            for f in _touched(w, focus):
                out.append(clip(f"       {f}"))

    # -- notes
    notes = _ledger_notes(led, focus if mode == "wrap" else on)
    if notes:
        out += ["", f' {S.card("notes", LANG)} {len(notes)}']
        out += [clip(f"   {DOT} {n}") for n in notes[:4]]

    # -- progress
    remain = round(g["wip_ai"] + g["todo_ai"], 2)
    done_ai = f'{g["done_ai"]:.1f}'
    W, V = 12, 27  # label and value columns, sized so value+unit+denominator all fit
    out += ["",
            f' {pad(S.card("checklist", LANG), W)}'
            f'{pad(S.card("boxes_closed", LANG, done=g["cb_done"], total=g["cb_total"]), V)}'
            f'({g["cb_pct"]}%)  {meter(g["cb_done"], g["cb_total"], 18)}',
            f' {pad(S.card("effort", LANG), W)}'
            f'{pad(S.card("effort_val", LANG, done=done_ai, total=g["total_ai"]), V)}'
            f'{S.card("effort_note", LANG, left=remain, wip=g["wip_ai"])}']
    goal = project_setting(cfg, p, "weekly_goal_ai")
    if goal:
        d = date.fromisoformat(on)
        monday = d - timedelta(days=d.weekday())
        got = round(sum(r.get("earned_ai", 0) for r in rows
                        if monday.isoformat() <= r["date"] <= on), 2)
        wd = sum(1 for n in range((d - monday).days + 1)
                 if (monday + timedelta(days=n)).weekday() < 5)
        exp = round(goal * wd / 5, 2)
        gap = round(got - exp, 2)
        pace = S.card("ahead" if gap > 0 else ("behind" if gap < 0 else "on_pace"), LANG)
        out.append(f' {pad(S.card("week", LANG), W)}'
                   f'{pad(S.card("week_val", LANG, got=got, goal=goal), V)}'
                   f'{S.card("week_note", LANG, gap=abs(gap), pace=pace)}')

    # -- output
    win = [r for r in rows
           if (date.fromisoformat(focus) - timedelta(days=14)).isoformat() <= r["date"] <= focus]
    if win:
        out += ["", f' {S.card("results", LANG)}  {short_date(focus)}']
        for m in ("ai", "code", "tokens"):
            lbl, get, f = METRICS[m]
            scored = [(r["date"], get(r)) for r in win if get(r)]
            mine = next((v for d_, v in scored if d_ == focus), 0)
            best = max(scored, key=lambda x: x[1]) if scored else None
            shown = f(mine) + (f' {S.card("unit_aid", LANG)}' if m == "ai" else "")
            line = f"   {pad(lbl, 9)}{pad(shown, 20)}"
            if best:
                line += S.card("best_on", LANG, val=f(best[1]), date=short_date(best[0]))
            out.append(line)
        scored_ai = [r for r in win if r.get("earned_ai")]
        if len(scored_ai) >= 2:
            top = [ln for ln in leaderboard(win, focus, "ai", 3) if ln]
            out += [f"   {ln}" for ln in top[1:-1]]

    # -- what is next
    nxt = led.next_up()
    if nxt:
        out += ["", " " + S.card("tomorrow_next" if mode == "wrap" else "today_next", LANG)]
        out += [clip(f"   {n}") for n in nxt[:3]]

    # -- blocked
    blocked = led.blockers()
    if blocked:
        out += ["", f' {S.card("blocked", LANG)} {len(blocked)}']
        out += [clip(f"   {DOT} {b['key']}") for b in blocked[:3]]
        if len(blocked) > 3:
            out.append(f'   {DOT} {S.card("and_more", LANG, n=len(blocked) - 3)}')

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

    sp = add("show", cmd_show, help="leaderboard")
    sp.add_argument("--date")
    sp.add_argument("--window", type=int, default=14)
    sp.add_argument("--top", type=int, default=6)
    sp.add_argument("--metric", choices=list(METRICS), default="ai")

    sp = add("streak", cmd_streak, help="consecutive days on goal")
    sp.add_argument("--threshold", type=float)

    sp = add("goal", cmd_goal, help="weekly goal and pace, per project")
    sp.add_argument("--set", type=float, help="weekly goal in AI-days")
    sp.add_argument("--daily", type=float, help="daily goal in AI-days, used by `streak`")
    sp.add_argument("--date")

    for name, mode, helptext in (("brief", "brief", "morning card (one call)"),
                                 ("wrap", "wrap", "end-of-day card (one call)")):
        sp = add(name, cmd_card, help=helptext)
        sp.set_defaults(mode=mode)
        sp.add_argument("--date")

    args = ap.parse_args()
    args.fn(args, load_config())


if __name__ == "__main__":
    main()
