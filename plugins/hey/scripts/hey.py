#!/usr/bin/env python3
"""hey — ledger parsing, aggregation and recording.

Every number the skills report comes from here, so no skill ever has to count by hand.
The ledger is one human-readable, human-editable markdown file; this script only parses it.

Config and history live in ~/.hey/
    config.json     registered projects, default scope, weekly goal, language
    stats.jsonl     daily snapshots. Ranking, burndown, carry-over and variance all
                    derive from these.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

HOME = Path(os.environ.get("HEY_HOME", Path.home() / ".hey"))
CONFIG = HOME / "config.json"
STATS = HOME / "stats.jsonl"
TEMPLATES = Path(__file__).parent.parent / "templates"

sys.path.insert(0, str(Path(__file__).parent))
import strings as S  # noqa: E402

DOT = "\u00b7"
WEEKDAY_KO = S.WEEKDAYS["ko"]  # kept for callers that import it
BLOCKER_WORDS = S.BLOCKER_WORDS  # per-language; detection uses the union

CARD_W = 78  # Default card width. Fits a standard terminal.
CARD_MIN, CARD_MAX = 72, 120


def card_width() -> tuple[int, str]:
    """The card's column count, and where it came from.

    `HEY_WIDTH` wins, then a real terminal, then the default. When stdout is a pipe --
    which is how an agent calls these scripts -- probing the terminal only ever returns
    its 80-column fallback, so it is not worth asking.

    The floor is 72, not 60: the card's progress rows spend a fixed 51 columns on labels
    before the value starts, and anything narrower makes them overflow.

    `doctor` reports the source, so returning it beats making the caller re-derive it.

    **This is deliberately the whole of it.** There used to be more: a walk up twelve
    process ancestors looking for a pty, `stty` with a BSD flag and a GNU one, and a
    `doctor` warning asking the user to confirm their usable width and write it down.
    Seventy-odd lines and a warning slot, to decide whether a card is 78 columns or 120.
    No project decision turns on that, and `doctor`'s warning budget is finite -- an
    unresolved base branch loses work, and it should not have to compete for attention
    with a cosmetic one. Set `HEY_WIDTH` if the default is wrong.
    """
    raw = (os.environ.get("HEY_WIDTH") or "").strip()
    if raw.isdigit():
        n = int(raw)
        clamped = max(CARD_MIN, min(CARD_MAX, n))
        note = "HEY_WIDTH" if clamped == n else f"HEY_WIDTH={n}, clamped"
        return clamped, note
    if sys.stdout.isatty():
        cols = shutil.get_terminal_size().columns
        return max(CARD_MIN, min(CARD_MAX, cols - 2)), f"terminal, {cols} columns"
    return CARD_W, "default"






# ---------------------------------------------------------------- config


def load_config() -> dict:
    if CONFIG.exists():
        return json.loads(CONFIG.read_text())
    return {"projects": [], "scope": "current"}


def save_config(cfg: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")


def git_root(cwd: Path) -> Path | None:
    """Return the main repository root, even when called inside a linked worktree."""
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=cwd, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return Path(common).parent if common.endswith("/.git") else Path(common)


def display_width(s: str) -> int:
    """Width in terminal columns.

    Only East Asian wide and fullwidth glyphs take two columns. Treating every non-ASCII
    character as wide mismeasures the card's own furniture -- box drawing, block meters,
    the ellipsis -- and both the rules and the clipping come out short.

    Lives here rather than in `board` because the ledger parser needs it too, and one
    implementation is the only way the two agree.
    """
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def clip_to(s: str, width: int, slack: int = 14) -> str:
    """The longest prefix that fits, ending on a word where one is near, plus an ellipsis.

    Cutting purely on width lands mid-word -- `...건너뛴 항` for `항목` -- which reads as a
    typo rather than as a sentence that was too long. Backing up to the last space costs a
    few columns and never a line, so it is only skipped when the nearest space is further
    back than `slack`: a long unbroken token would otherwise lose most of itself.
    """
    if display_width(s) <= width:
        return s
    out = ""
    for c in s:
        if display_width(out) + display_width(c) > width - 1:
            break
        out += c
    i = out.rfind(" ")
    if i != -1 and display_width(out) - display_width(out[:i]) <= slack:
        out = out[:i]
    return out.rstrip() + "…"


def _lines_of(out: str) -> list:
    return [ln.strip() for ln in out.split("\n") if ln.strip()]


def _sh(cmd: list[str], cwd: Path) -> str:
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def day_range(on: str) -> list[str]:
    """`git log` arguments covering one whole calendar day.

    `--until <day> 23:59` means `23:59:00`, so a commit made in the last minute of the day
    falls outside it -- and the next day starts at `00:00`, so it falls outside that one
    too and is counted on no day at all. Someone finishing up just before midnight is
    exactly who runs `/seeya`.

    Defined once because five call sites spell this range out, and a boundary that is
    written five times is a boundary that is wrong in four places.
    """
    return [f"--since={on} 00:00:00", f"--until={on} 23:59:59"]


def worktree_roots(root: Path) -> list[Path]:
    """Every worktree of a repository, the main one first.

    Work in a linked worktree is work on the project, so anything that counts per
    project counts across all of these. Falls back to `[root]` outside git.
    """
    out = [Path(ln.split(" ", 1)[1])
           for ln in _sh(["git", "worktree", "list", "--porcelain"], root).split("\n")
           if ln.startswith("worktree ")]
    return out or [root]


def default_base(root: Path) -> str | None:
    """The branch a repository is measured against: whatever its remote calls default.

    Returns None rather than guessing. A wrong base makes `origin/<base>..HEAD` fail,
    and a failed comparison silently reads as "zero unpushed commits" — which hides
    exactly the state this tool exists to surface.
    """
    ref = _sh(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root)
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    for cand in ("main", "develop", "master"):
        if _sh(["git", "rev-parse", "--verify", "--quiet",
                f"refs/remotes/origin/{cand}"], root):
            return cand
    return None


def project_base(cfg: dict, p: dict) -> str | None:
    """Base branch for a project: what `add` recorded, else detected from the remote."""
    return p.get("base") or cfg.get("base_branch") or default_base(Path(p["root"]))


def project_setting(cfg: dict, p: dict, key: str, default=None):
    """A setting read per project, falling back to the global value.

    Goals belong to a project, not to the machine. With several registered, one shared
    weekly target is measured against each project's slice of the work, so every card
    reports the same goal and every one of them looks behind.
    """
    return p[key] if key in p else cfg.get(key, default)


def already_merged(worktree: Path, base: str | None) -> bool:
    """Is this branch's work already in `origin/<base>`, differing only in history?

    A squash merge rewrites the branch's commits into one new commit, so the branch keeps
    commits the base has never seen while its *content* is fully merged. Counting those as
    unpushed work makes the report nag about a branch whose only remaining job is to be
    deleted. Comparing trees instead of commits is what tells the two apart.
    """
    if not base:
        return False
    diff = subprocess.run(["git", "diff", "--quiet", f"origin/{base}", "HEAD"],
                          cwd=worktree, capture_output=True)
    return diff.returncode == 0


def ahead_of_base(worktree: Path, base: str | None) -> tuple[list[str], bool]:
    """Commits on HEAD that never reached `origin/<base>`.

    The second value is False when the comparison could not be made at all. That case
    must never be reported as zero — see `default_base`. Commits whose content is already
    merged are excluded; see `already_merged`.
    """
    if not base:
        return [], False
    if not _sh(["git", "rev-parse", "--verify", "--quiet",
                f"refs/remotes/origin/{base}"], worktree):
        return [], False
    if already_merged(worktree, base):
        return [], True
    out = _sh(["git", "log", "--oneline", f"origin/{base}..HEAD"], worktree)
    return [ln for ln in out.split("\n") if ln.strip()], True


def unpushed(worktree: Path, base: str | None) -> tuple[int, bool]:
    """(commits not on any remote, whether the branch has an upstream at all).

    `ahead_of_base` answers a different question -- what is not in the base branch yet --
    and a pushed feature branch answers that too. Reporting those as work at risk is a
    false alarm, and a card full of false alarms is one nobody reads. Work is only
    losable while no remote has it.

    With no upstream, nothing on the branch has left the machine, so everything it holds
    over the base counts. With one, only what sits past it does.
    """
    up = _sh(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
             worktree)
    if not up or up == "@{upstream}":
        return len(ahead_of_base(worktree, base)[0]), False
    out = _sh(["git", "log", "--oneline", f"{up}..HEAD"], worktree)
    return len([ln for ln in out.split("\n") if ln.strip()]), True


def resolve_project(cfg: dict, cwd: Path | None = None) -> dict | None:
    """Find which registered project the current directory belongs to."""
    cwd = cwd or Path.cwd()
    candidates = [cwd, *cwd.parents]
    root = git_root(cwd)
    if root:
        candidates = [root, *candidates]
    for cand in candidates:
        for proj in cfg["projects"]:
            if Path(proj["root"]) == cand:
                return proj
    return None


def projects_in_scope(cfg: dict, scope: str | None, name: str | None) -> list[dict]:
    if name:
        hits = [p for p in cfg["projects"] if p["name"] == name]
        if not hits:
            die(f"unknown project: {name}. Run `hey.py projects` to list them")
        return hits
    scope = scope or cfg.get("scope", "current")
    if scope == "all":
        return list(cfg["projects"])
    cur = resolve_project(cfg)
    if cur:
        return [cur]
    # Scope `current` means the project you are standing in, and nothing else. Answering
    # from the sole registered project when the cwd matches none of them briefs the wrong
    # ledger silently, and the same command starts failing the day a second project is
    # registered. Out of scope is out of scope, at one project and at ten.
    return []


def die(msg: str) -> None:
    print(f"hey: {msg}", file=sys.stderr)
    sys.exit(2)


def die_out_of_scope(escape: str | None = "scope") -> None:
    """Every entry point fails the same way when the cwd is in no registered project.

    Naming the resolved main root matters more than it looks: from inside a linked
    worktree it is not the directory the user is standing in, and it is the path `add`
    wants.

    `escape` names the way out, which is not the same for every command. A report widens
    to every project. A note has to land in exactly one ledger, so widening is not on
    offer -- and `note` accepts `--scope` only to ignore it, which makes that advice fail
    without saying anything. `resolve` answers about one directory or not at all, and has
    neither flag. Sending a reader to a flag that cannot help is worse than the bare
    failure, because they spend the next minute believing they mistyped it.
    """
    root = git_root(Path.cwd())
    lines = [f"{root} is not a registered project" if root
             else f"not inside a git repository: {Path.cwd()}"]
    if root:
        lines.append(f"register:  hey.py add {root} --init")
    lines.append("list:      hey.py projects")
    if escape == "scope":
        lines.append("sweep all: pass `--scope all`")
    elif escape == "project":
        lines.append("by name:   pass `--project <name>`")
    die("\n     ".join(lines))


# ---------------------------------------------------------------- ledger


class Ledger:
    """One ledger file. Reads checkboxes, estimates and sections.

    An *item* is a top-level `- [ ]`; an indented `  - [ ]` is its child.
    Estimates are read from `N MD / AI M` on the item line only. Missing means 0.
    """

    # `[X]` is accepted as well as `[x]`. A human edits this file by hand, and an
    # unrecognised box drops out of the totals entirely, denominator included.
    ITEM = re.compile(r"- \[([ xX])\] (.*)")
    KID = re.compile(r"\s+- \[([ xX])\] (.*)")
    EST = re.compile(r"(\d+\.?\d*) MD / AI (\d+\.?\d*)")
    DAY = re.compile(r"^### (\d{4}-\d{2}-\d{2})")
    # A subitem's share of its item's estimate, for the cases where an even split lies.
    # Numeric and `AI`-prefixed, so it cannot be confused with a tag like `[migrated]`.
    KID_AI = re.compile(r"\[AI (\d+\.?\d*)\]")
    # When a blocker started waiting, so its age does not depend on recorded history.
    # `unknown` is a real answer and not the same as an empty one: it says the start was
    # looked for and could not be found, which is settled, where a missing marker is a
    # question nobody has asked yet.
    SINCE = re.compile(r"\[since (\d{4}-\d{2}-\d{2}|unknown)\]")
    # Blocked, said outright. This used to be inferred from words in the item text --
    # `waiting`, `pending`, `TBD` -- and ordinary prose uses those without meaning "hold
    # this". A false positive is expensive: the item drops out of `/hey-run` candidates
    # and starts accruing a wait it was never on. `doctor` still reads the words, but
    # only to point at lines that may want the marker.
    BLOCKED = re.compile(r"\[blocked\]")
    # A name for the item that does not change when its name does. Without one the key
    # is `<phase>|<title>`, so editing the wording of a line severs everything recorded
    # against it -- carry-over restarts, `item` loses the history, and `earned_ai` reads
    # the rename as one item vanishing and another appearing on the same day.
    ID = re.compile(r"\[id ([^\]\s]+)\]")
    # Which branch an item's work lives on. Branches outlast worktrees, whose paths are
    # temporary, and they are what commits and pull requests actually attach to.
    BRANCH = re.compile(r"\[branch ([^\]\s]+)\]")
    # Every marker, for stripping them back out of anything a person reads.
    MARKERS = re.compile(r"`?\[(?:AI \d+\.?\d*|since (?:\d{4}-\d{2}-\d{2}|unknown)"
                         r"|branch [^\]\s]+|blocked|id [^\]\s]+)\]`?")
    # A line still holding the template's `<...>` stand-in is scaffolding, not work. A
    # freshly created ledger otherwise reports its own example rows as an item, a subitem
    # and a blocker, so the first card anyone sees is three counts of nothing, and the
    # snapshot taken that day records example names that no later ledger answers to.
    # The whole title has to be the stand-in: an item that merely mentions `<T>` somewhere
    # in its sentence is a real item and is left alone.
    PLACEHOLDER = re.compile(r"^<[^<>]+>$")

    def __init__(self, project: dict):
        self.project = project
        self.path = Path(project["ledger"])
        self.text = self.path.read_text() if self.path.exists() else ""
        self.lines = self.text.split("\n")
        # An append-only half -- work log, notes, PR log -- grows forever while the
        # checklist is the part edited daily, so a long-running project ends up wanting
        # them in separate files. `ledger_log` names the second one; sections are then
        # looked for across both, and a project without it behaves exactly as before.
        log = project.get("ledger_log")
        log_path = Path(log) if log else None
        self.log_path = log_path if log_path and log_path.exists() else None
        self.log_lines = self.log_path.read_text().split("\n") if self.log_path else []
        self.items: list[dict] = []
        # Counted rather than silently dropped, so `doctor` can say why a ledger that
        # visibly has rows in it reports no items.
        self.placeholders = 0
        self._parse()

    def _parse(self) -> None:
        section, cur = None, None
        for ln in self.lines:
            if ln.startswith("## "):
                section, cur = ln[3:].strip(), None
                continue
            if m := self.ITEM.match(ln):
                title = self._title(m[2])
                if self.PLACEHOLDER.match(title):
                    # Its subitems belong to it, so clearing `cur` drops them with it.
                    cur = None
                    self.placeholders += 1
                    continue
                est = self.EST.search(m[2])
                cur = {
                    "section": section or "?",
                    "phase": (section or "?").split(".")[0].split(" ")[0],
                    "title": title,
                    "text": m[2],
                    "done": m[1].lower() == "x",
                    "kids": [],
                    "kid_ai": [],
                    "id": (self.ID.search(m[2]) or [None, None])[1],
                    "branches": self.BRANCH.findall(m[2]),
                    "md": float(est[1]) if est else 0.0,
                    "ai": float(est[2]) if est else 0.0,
                }
                self.items.append(cur)
            elif k := self.KID.match(ln):
                # Tested before the `cur` guard, so a stand-in under a stand-in parent is
                # still counted rather than disappearing along with it.
                if self.PLACEHOLDER.match(self._title(k[2])):
                    self.placeholders += 1
                    continue
                if cur is None:
                    continue
                cur["kids"].append(k[1].lower() == "x")
                w = self.KID_AI.search(k[2])
                cur["kid_ai"].append(float(w[1]) if w else None)
                # A subitem is usually the thing that becomes one branch and one PR, so
                # the marker is read there too and credited to the item that owns it.
                cur["branches"] += self.BRANCH.findall(k[2])

    @classmethod
    def _title(cls, text: str) -> str:
        """The item's name, which is also half its key -- so this has to stay stable.

        A trailing parenthetical is almost always a list of what the item covers, and
        dropping it is what turns a line into a name. But when the parenthesis opens early
        in a sentence that carries on afterwards, cutting there keeps a fragment and throws
        the sentence away. So the cut is skipped when what follows the closing bracket is
        more than twice what precedes the opening one: at that ratio the head is not the
        title, it is the first few words of one.
        """
        # Markers are metadata, so they never belong in the name -- and the name is half
        # the key, so leaving one in silently renames the item and severs its history.
        text = cls.MARKERS.sub("", text)
        seg = re.split(r" — | - ", text, maxsplit=1)[0]
        i = seg.find("(")
        if i != -1:
            j = seg.find(")", i)
            tail = seg[j + 1:].strip() if j != -1 else ""
            clean = lambda x: x.replace("**", "").replace("`", "").strip()  # noqa: E731
            if display_width(clean(tail)) <= 2 * display_width(clean(seg[:i])):
                seg = seg[:i]
        return seg.replace("**", "").replace("`", "").strip()

    # -- state

    @staticmethod
    def state(it: dict) -> str:
        if it["done"] or (it["kids"] and all(it["kids"])):
            return S.DONE
        return S.WIP if any(it["kids"]) else S.TODO

    @staticmethod
    def boxes(it: dict) -> tuple[int, int]:
        """(closed boxes, total boxes). The item line itself counts as one box."""
        all_boxes = [it["done"], *it["kids"]]
        return sum(all_boxes), len(all_boxes)

    @staticmethod
    def box_ai(it: dict) -> list:
        """Each box's share of the item's estimate, in `[done, *kids]` order.

        An even split is the default and is right often enough, but not always: the last
        subitem of a ten-box module can be the whole remaining job, and scoring it at a
        tenth understates the day. A subitem may therefore claim a share with `[AI 0.3]`.

        **A closed box that claimed nothing keeps its plain even share, always.** Sharing
        out the remainder across every unclaimed box instead would move boxes that are
        already banked and recorded, so annotating a half-finished item would restate
        output that past snapshots have already counted -- and `earned_ai` diffs those
        snapshots, so the restatement lands as either a negative day or a double count.
        Nothing you write today may change what a closed box was worth.

        What is left after the claims and the closed shares goes to the open boxes that
        claimed nothing, and never below zero. So the shares can add up to more than the
        item's estimate, and that is the signal rather than a fault: it says the item was
        under-estimated. `doctor` reports the excess; it is also what catches `[AI 3]`
        written for `[AI 0.3]`.
        """
        weights = [None, *it["kid_ai"]]
        closed = [it["done"], *it["kids"]]
        n = len(weights)
        even = it["ai"] / n if n else 0.0
        out = [w if w is not None else (even if c else None)
               for w, c in zip(weights, closed)]
        spoken = sum(x for x in out if x is not None)
        free = [i for i, x in enumerate(out) if x is None]
        share = max(0.0, it["ai"] - spoken) / len(free) if free else 0.0
        return [share if x is None else x for x in out]

    @classmethod
    def earned(cls, it: dict) -> float:
        """AI-days already banked on this item, by which boxes are closed.

        Recorded per snapshot so `earned_ai` can diff a value instead of multiplying a
        count, which is what lets a weighted subitem score what it is worth.
        """
        closed = [it["done"], *it["kids"]]
        return round(sum(w for w, c in zip(cls.box_ai(it), closed) if c), 4)

    @classmethod
    def overclaimed(cls, it: dict) -> float:
        """How much the box shares add up to beyond the item's own estimate, or 0.

        Measured on the shares rather than the claims alone, because a closed box holds
        its even share regardless -- so a claim can push the total over even when the
        claim on its own would fit.
        """
        if not it["ai"]:
            return 0.0
        return round(max(0.0, sum(cls.box_ai(it)) - it["ai"]), 4)

    # -- aggregation

    def progress(self) -> dict:
        """Totals. **Boxes are counted, effort is estimated, and neither is a percentage.**

        A box count has no error term -- it is the one figure here that is not an estimate.
        What it does not have is a meaningful denominator: the user writes it, and one box
        may be a typo fix while the next is a subsystem. So `37/80` is worth printing and
        `46%` is not, because the percentage reads as "the project is 46% done" and nothing
        in the count supports that. `[AI n]` exists precisely because an even split lies.

        Adding subitems makes the fraction fall without anything being undone, which is the
        clearest sign it was never a completion rate: discovering scope is not regressing.
        """
        scoped = [i for i in self.items if i["ai"]]
        cb_done = sum(self.boxes(i)[0] for i in self.items)
        cb_total = sum(self.boxes(i)[1] for i in self.items)
        by_state = {s: [i for i in scoped if self.state(i) == s] for s in (S.DONE, S.WIP, S.TODO)}
        return {
            "cb_done": cb_done,
            "cb_total": cb_total,
            "total_ai": round(sum(i["ai"] for i in scoped), 2),
            "total_md": round(sum(i["md"] for i in scoped), 2),
            **{
                f"{k}_ai": round(sum(i["ai"] for i in v), 2) for k, v in by_state.items()
            },
            **{f"{k}_n": len(v) for k, v in by_state.items()},
        }

    def phases(self) -> list[dict]:
        out, seen = [], []
        for it in self.items:
            if it["phase"] not in seen:
                seen.append(it["phase"])
        for ph in seen:
            g = [i for i in self.items if i["phase"] == ph]
            done = sum(1 for i in g if self.state(i) == S.DONE)
            part = sum(1 for i in g if self.state(i) == S.WIP)
            cd = sum(self.boxes(i)[0] for i in g)
            ct = sum(self.boxes(i)[1] for i in g)
            out.append({
                "phase": ph, "items": len(g), "done": done, "partial": part,
                "cb_done": cd, "cb_total": ct,
                "ai": round(sum(i["ai"] for i in g), 2),
            })
        return out

    def blockers(self, on: str | None = None) -> list[dict]:
        """Blocked items: unfinished items in a blocker section, or marked blocked in text.

        A blocker's age is the number that decides whether to chase it, and `carryover`
        can only derive it once several days are on record. `[since YYYY-MM-DD]` on the
        line says it outright, so the age survives a machine with no history at all --
        and a blocker is exactly the kind of thing that predates the ledger.
        """
        today = on or date.today().isoformat()
        out = []
        for it in self.items:
            if self.state(it) == S.DONE:
                continue
            sect = it["section"].lower()
            in_section = any(w.lower() in sect for w in S.blocker_sections())
            marked = bool(self.BLOCKED.search(it["text"]))
            if in_section or marked:
                m = self.SINCE.search(it["text"])
                raw = m[1] if m else None
                days, bad = None, False
                if raw and raw != "unknown":
                    try:
                        days = (date.fromisoformat(today) - date.fromisoformat(raw)).days
                    except ValueError:
                        # The pattern only checks the shape, so `2026-13-45` reaches here.
                        # Reported rather than swallowed: it looks answered on the line but
                        # yields no age, so nothing would ever prompt anyone to fix it.
                        bad = True
                    else:
                        # A date in the future is a real date, not a typo. It has no age,
                        # and reporting a negative wait would be worse than reporting none.
                        days = days if days >= 0 else None
                # The title is a key first, and a key that reads well is a coincidence.
                # The listing wants the line as written, minus the markup and the markers.
                shown = self.MARKERS.sub("", it["text"]).replace("**", "").replace("`", "")
                out.append({"key": self.key(it), "title": it["title"],
                            "shown": " ".join(shown.split()),
                            "section": it["section"],
                            "since": raw,
                            "bad_since": bad,
                            "days": days})
        return out

    def item_for_branch(self, branch: str) -> dict | None:
        """The item whose `[branch ...]` marker names this branch, if any.

        Without this the two halves never meet: `batch` knows the items and `dirty` knows
        the worktrees, and which item a loose branch belongs to lives only as prose in the
        work log. Reading it off the ledger keeps the join where every other number comes
        from, instead of guessing it from how a branch happens to be named.
        """
        if not branch:
            return None
        for it in self.items:
            if branch in it["branches"]:
                return it
        return None

    def branch_markers(self) -> list[tuple[str, str]]:
        """(branch, item title) for every marker in the ledger."""
        return [(b, it["title"]) for it in self.items for b in it["branches"]]

    @staticmethod
    def key(it: dict) -> str:
        """What history is recorded against: the `[id ...]` when there is one.

        Falling back to `<phase>|<title>` is what every ledger written so far relies on,
        and it works right up until someone improves the wording of a line. It also cannot
        tell two items apart when a phase holds the same title twice -- `doctor` reports
        that, because the recorded rows silently keep only one of them.

        An id makes every **later** rename free. It does not reconnect an item to history
        already recorded under its old name: once the rename has happened that name is no
        longer anywhere in the ledger, so matching it back would mean guessing which
        recorded key used to be this item -- and guessing wrong would merge two items'
        histories without saying so. `doctor` reports recorded keys that no item answers
        to, which names the severance instead of papering over it.
        """
        return it.get("id") or f"{it['phase']}|{it['title']}"

    @staticmethod
    def legacy_key(it: dict) -> str:
        """The key this item would have without an id. What `doctor` compares against."""
        return f"{it['phase']}|{it['title']}"

    # -- section bodies

    def section_body(self, key: str, level: str = "## ") -> list[str]:
        """Body lines of a section, found by any of its language aliases.

        Searched in the primary ledger first, then in `ledger_log` when one is configured.
        Checkboxes are only ever read from the primary file, so a split cannot double-count
        progress -- only the prose sections move.
        """
        for lines in (self.lines, self.log_lines):
            out, inside = [], False
            for ln in lines:
                if ln.startswith(level):
                    if inside:
                        break
                    inside = ln[len(level):].strip().startswith(S.section_aliases(key))
                    continue
                if inside:
                    out.append(ln)
            if out:
                return out
        return []

    def log_days(self) -> list[tuple[str, list[str]]]:
        """(date, bullets) pairs from the work log, in file order."""
        body = self.section_body("log")
        days, cur = [], None
        for ln in body:
            if m := self.DAY.match(ln):
                cur = (m[1], [])
                days.append(cur)
            elif cur and ln.strip().startswith("- "):
                cur[1].append(ln.strip()[2:])
        return days

    def _own_section(self, key: str, level: str = "## ") -> bool:
        """Is the heading in the primary ledger, as opposed to the companion file?"""
        names = S.section_aliases(key)
        return any(ln.startswith(level) and ln[len(level):].strip().startswith(names)
                   for ln in self.lines)

    def has_section(self, key: str, level: str = "## ") -> bool:
        """Is the heading present at all, in either half? A section can exist and be empty."""
        names = S.section_aliases(key)
        return any(ln.startswith(level) and ln[len(level):].strip().startswith(names)
                   for ln in (*self.lines, *self.log_lines))

    def next_up(self) -> list[str]:
        body = self.section_body("next", level="### ")
        return [ln.strip() for ln in body if re.match(r"^\d+\.", ln.strip())]


# ---------------------------------------------------------------- snapshots


def snapshot(led: Ledger, on: str) -> dict:
    p = led.progress()
    return {
        "date": on,
        "project": led.project["name"],
        **{k: p[k] for k in ("cb_done", "cb_total", "total_ai", "done_ai", "wip_ai", "todo_ai")},
        "items": [
            {
                "k": Ledger.key(i), "ai": i["ai"], "state": Ledger.state(i),
                "closed": Ledger.boxes(i)[0], "boxes": Ledger.boxes(i)[1],
                "earned": Ledger.earned(i),
            }
            for i in led.items
        ],
        "blockers": [b["key"] for b in led.blockers()],
    }


def need_history(name: str, what: str, have: int, need: int) -> None:
    """Report a history shortfall as a countdown, not as an empty answer.

    Five commands go quiet on a fresh install for the same one reason, and `not enough
    snapshots` does not say which reason or what clears it -- so it reads as five broken
    features instead of one clock that has not run yet. The first recorded day is a
    baseline by design, so even a diligent user sees this on day one.
    """
    short = max(0, need - have)
    print(f"[{name}] {what} needs {need} recorded day(s), and has {have}. "
          f"{short} more of `/seeya` (or `board.py collect`) opens it. "
          f"The first day recorded is a baseline, so it does not count toward output")



def read_stats() -> list[dict]:
    """Every recorded day. A damaged line is skipped loudly rather than crashing."""
    if not STATS.exists():
        return []
    out = []
    for n, ln in enumerate(STATS.read_text().splitlines(), 1):
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            print(f"hey: skipping damaged line {n} of {STATS}", file=sys.stderr)
    return out


def write_stats(rows: list[dict]) -> None:
    """Rewrite stats.jsonl atomically.

    The whole file is rewritten on every record, so a half-finished write would take
    the entire history with it.
    """
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = STATS.with_name(STATS.name + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    tmp.replace(STATS)


def merge_stats(on: str, project: str, fields: dict) -> None:
    """Merge fields into one day's row, keeping what another command already recorded.

    `snapshot` and `collect` each own part of a day. Replacing the row instead of
    merging would make whichever ran last erase the other's numbers.
    """
    rows = read_stats()
    hit = next((r for r in rows if r["date"] == on and r["project"] == project), None)
    if hit is None:
        hit = {"date": on, "project": project}
        rows.append(hit)
    # A None means the field no longer applies -- a day that gained `earned_ai` is not a
    # baseline any more. Merging it as a value would leave the key sitting there.
    for k, v in fields.items():
        if v is None:
            hit.pop(k, None)
        else:
            hit[k] = v
    rows.sort(key=lambda r: (r["date"], r["project"]))
    write_stats(rows)


def record_progress(led: Ledger, on: str) -> dict:
    """Snapshot fields for a day, with `earned_ai` only when there is a day to diff against.

    The first record has no predecessor, so counting its closed boxes as "closed today"
    would credit every box finished before recording began. That inflated figure then
    becomes the peak every later day is ranked against, so the first record is marked
    a baseline and carries no closed-work number at all.
    """
    snap = snapshot(led, on)
    prev = [r for r in read_stats()
            if r["project"] == led.project["name"] and r["date"] < on and r.get("items")]
    if prev:
        snap["earned_ai"] = earned_ai(prev[-1], snap)
        # A row that gains a closed-work number is no longer the baseline, and `merge_stats`
        # keeps whatever the row already had -- so the stale flag has to be cleared here or
        # the day claims to be both.
        snap["baseline"] = None
    else:
        snap["baseline"] = True
    return snap


def earned_ai(prev: dict | None, now: dict) -> float:
    """Convert boxes closed between two snapshots into AI-days.

    Each box carries a share of its item's estimate -- even by default, or whatever a
    subitem claimed with `[AI n]`. Diffing the banked total is what makes a weighted
    subitem score what it is worth rather than its fraction of the box count.

    Records written before shares existed have no `earned`, so those fall back to the old
    count-based split. Rewriting them is not an option: the ledger only holds its current
    state, so the box weights of a past day are gone.
    """
    before = {i["k"]: i for i in (prev or {}).get("items", [])}
    total = 0.0
    for it in now["items"]:
        was = before.get(it["k"], {})
        if "earned" in it and "earned" in was:
            total += max(0.0, it["earned"] - was["earned"])
        elif "earned" in it and not was:
            total += it["earned"]          # first sighting of the item
        else:
            delta = it["closed"] - was.get("closed", 0)
            if delta > 0 and it["boxes"]:
                total += it["ai"] * delta / it["boxes"]
    return round(total, 3)


# ---------------------------------------------------------------- commands


def today_str() -> str:
    return date.today().isoformat()


def fmt_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{iso} ({S.WEEKDAYS[S.lang(load_config())][d.weekday()]})"


def cmd_projects(args, cfg):
    if not cfg["projects"]:
        print("No projects registered. Run `hey.py add <path>`.")
        return
    cur = resolve_project(cfg)
    print(f"default scope: {cfg.get('scope', 'current')}")
    for p in cfg["projects"]:
        mark = "  <- you are here" if cur and cur["name"] == p["name"] else ""
        exists = "" if Path(p["ledger"]).exists() else "  [ledger missing]"
        print(f"- {p['name']}  {p['root']}\n    ledger: {p['ledger']}{exists}{mark}")


def cmd_add(args, cfg):
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        die(f"not a directory: {root}")
    # One project is one repository. A linked worktree registered on its own would keep a
    # second ledger and its own history, and `resolve` would never match it anyway
    # because it resolves the cwd to the main root.
    main_root = git_root(root)
    if main_root and main_root != root:
        die(f"{root} is a linked worktree of {main_root}. Register the main repository "
            f"instead - its worktrees are already counted with it")
    ledger = Path(args.ledger).expanduser().resolve() if args.ledger else root / "TASKS.local.md"
    name = args.name or root.name
    base = args.base or default_base(root)

    created = False
    if args.init and not ledger.exists():
        tpl = TEMPLATES / ("LEDGER.ko.md" if S.lang(cfg) == "ko" else "LEDGER.md")
        if not tpl.exists():
            die(f"template not found: {tpl}")
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(tpl.read_text())
        created = True

    # Re-adding an already-registered project is a routine thing to do -- `doctor` tells you
    # to, in three separate places, whenever the base branch is wrong or the ledger is
    # missing. Rebuilding the entry from scratch threw away everything `add` does not
    # manage, so following that advice silently deleted the project's goals. Only the
    # fields this command actually resolves are overwritten; a setting is cleared by
    # `remove` and a fresh `add`, or by editing the config.
    prior = next((p for p in cfg["projects"] if p["name"] == name), None)
    entry = dict(prior or {})
    entry.update({"name": name, "root": str(root), "ledger": str(ledger)})
    if args.ledger_log:
        entry["ledger_log"] = str(Path(args.ledger_log).expanduser().resolve())
    if base:
        entry["base"] = base
    cfg["projects"] = [p for p in cfg["projects"] if p["name"] != name]
    cfg["projects"].append(entry)
    cfg["projects"].sort(key=lambda p: p["name"])
    save_config(cfg)

    if created:
        note = "  [created from template]"
    elif ledger.exists():
        note = ""
    else:
        note = "  [missing - re-run with --init]"
    print(f"{'updated' if prior else 'registered'}: {name}"
          f"\n  root:   {root}\n  ledger: {ledger}{note}")
    # Named rather than merely kept. A re-add that quietly carries settings forward is
    # better than one that drops them, but the user still has to be able to see what this
    # entry holds beyond the three things they just typed.
    kept = sorted(k for k in entry
                  if k not in ("name", "root", "ledger", "ledger_log", "base"))
    if prior and kept:
        print(f"  kept:   {', '.join(kept)}")
    if entry.get("ledger_log"):
        exists = "" if Path(entry["ledger_log"]).exists() else "  [missing]"
        print(f"  log:    {entry['ledger_log']}{exists}")
    # Read off the entry, not off `base`. On a re-add where the remote cannot be inspected
    # the entry keeps the base already on record, and reporting "unresolved" there
    # contradicts the config this command just wrote.
    settled = entry.get("base")
    if settled:
        if args.base:
            how = ""
        elif base:
            how = "  (detected)"
        else:
            how = "  (kept)"
        print(f"  base:   origin/{settled}{how}")
    else:
        print("  base:   unresolved - unpushed commits cannot be counted. "
              "Re-run with `--base <branch>`")
    if created:
        print("  the ledger is local state. Add it to .git/info/exclude")


def cmd_remove(args, cfg):
    """Unregister a project. Neither the ledger nor the recorded history is touched."""
    hits = [p for p in cfg["projects"] if p["name"] == args.name]
    if not hits:
        die(f"unknown project: {args.name}. Run `hey.py projects` to list them")
    cfg["projects"] = [p for p in cfg["projects"] if p["name"] != args.name]
    save_config(cfg)
    kept = sum(1 for r in read_stats() if r["project"] == args.name)
    print(f"unregistered: {args.name}")
    print(f"  the ledger at {hits[0]['ledger']} was left alone")
    if kept:
        print(f"  {kept} recorded day(s) stay in {STATS}. Registering the same name again "
              f"picks them back up")


def cmd_doctor(args, cfg):
    """Report what is misconfigured, in one place.

    Almost everything that goes wrong here goes wrong quietly. A base branch that cannot
    be resolved, a ledger missing the heading a command reads, a damaged history line —
    each produces an empty or zero answer instead of an error, so they are collected here
    where they can be seen.
    """
    counts = {"FAIL": 0, "warn": 0}

    def say(level: str, msg: str) -> None:
        counts[level] = counts.get(level, 0) + 1
        print(f"  {level:<5} {msg}")

    ok = lambda msg: print(f"  ok    {msg}")  # noqa: E731

    print("environment")
    v = sys.version_info
    label = f"python {v.major}.{v.minor}.{v.micro}"
    ok(label) if v >= (3, 9) else say("FAIL", f"{label} - 3.9 or newer is required")
    for tool, required in (("git", True), ("gh", False)):
        found = shutil.which(tool)
        if found:
            ok(f"{tool} at {found}")
        elif required:
            say("FAIL", f"{tool} not found - nothing that reads a repository will work")
        else:
            say("warn", f"{tool} not found - `pr-sync` cannot read merged PRs")
    ok(f"language {S.lang(cfg)}")
    cols, source = card_width()
    ok(f"card width {cols} ({source})")

    print("config")
    ok(str(CONFIG)) if CONFIG.exists() else say("warn", f"{CONFIG} does not exist yet")
    if not cfg["projects"]:
        say("warn", "no projects registered. `hey.py add <path> --init`")

    for p in cfg["projects"]:
        print(f"project {p['name']}")
        root = Path(p["root"])
        if not root.is_dir():
            say("FAIL", f"root is gone: {root}. `hey.py remove {p['name']}`")
            continue
        ok(f"root {root}")
        if not git_root(root):
            say("warn", "not a git repository - code counts and dirty checks stay empty")
        else:
            base = project_base(cfg, p)
            if not base:
                say("FAIL", "base branch unresolved - unpushed commits are never counted. "
                            'Set "base" for this project')
            elif _sh(["git", "rev-parse", "--verify", "--quiet",
                      f"refs/remotes/origin/{base}"], root):
                ok(f"base origin/{base}")
                # The remote's default branch is not always the branch work merges into:
                # a repository can keep `main` for releases and integrate on `develop`.
                # Detected by the main worktree sitting well ahead of its own base, which
                # otherwise makes every report count commits pushed weeks ago.
                cur = _sh(["git", "branch", "--show-current"], root)
                if cur and cur != base:
                    n = _sh(["git", "rev-list", "--count",
                             f"origin/{base}..origin/{cur}"], root)
                    if n.isdigit() and int(n) >= 10:
                        say("warn", f"this worktree is on `{cur}`, {n} commit(s) ahead of "
                                    f"origin/{base}. If `{cur}` is what work merges into, "
                                    f"re-add with `--base {cur}` - otherwise every report "
                                    f"counts commits that were pushed long ago")
            else:
                say("FAIL", f"origin/{base} does not exist - unpushed commits are never "
                            f"counted. Re-add with --base <branch>")
            trees = worktree_roots(root)
            ok(f"{len(trees)} worktree(s) counted")
            # Squash-merged branches keep commits the base never saw. `dirty` and the
            # session hook stay quiet about them so they do not nag every session, which
            # leaves this the only place the leftover surfaces.
            for w in trees:
                if not _sh(["git", "log", "--oneline",
                            f"origin/{base}..HEAD"], w):
                    continue
                if already_merged(w, base):
                    branch = _sh(["git", "branch", "--show-current"], w) or "detached"
                    say("warn", f"{w.name} on `{branch}` is already merged into "
                                f"origin/{base} - the commits differ but the content does "
                                f"not, which is what a squash merge leaves. Delete it")

        led = Path(p["ledger"])
        if not led.exists():
            say("FAIL", f"ledger missing: {led}. `hey.py add {root} --init`")
            continue
        ok(f"ledger {led}")
        ledger = Ledger(p)
        for key in ("notes", "log", "next", "summary"):
            level = "### " if key == "next" else "## "
            if not ledger.has_section(key, level):
                names = " / ".join(S.section_aliases(key))
                say("warn", f"no `{names}` heading - whatever reads it returns nothing")
        if not ledger.items:
            # The ledger having rows in it and reporting none of them is the confusing
            # case, and on a fresh `--init` it is the only case. Say which it is.
            if ledger.placeholders:
                say("warn", f"{ledger.placeholders} template stand-in(s) and no real item "
                            f"yet. Rows still reading `<like this>` are not counted - "
                            f"replace them, or run `/hey-plan`")
            else:
                say("warn", "no checklist items found. Is the estimate format "
                            "`N MD / AI M`?")
        else:
            g = ledger.progress()
            ok(f"{len(ledger.items)} item(s), {g['cb_total']} box(es), AI {g['total_ai']}")
            if p.get("ledger_log"):
                if ledger.log_path:
                    ok(f"companion log {ledger.log_path}")
                else:
                    say("warn", f"ledger_log points at {p['ledger_log']}, which does not "
                                f"exist. The log, notes and PR sections read as empty")
            # An estimate only matters for work still ahead. A finished item's estimate is
            # moot, and a blocker is somebody else's effort — a ledger that deliberately
            # leaves both blank is right to, so warning about them is noise.
            blocked = {b["key"] for b in ledger.blockers()}
            missing = [i for i in ledger.items
                       if not i["ai"] and ledger.state(i) != S.DONE
                       and ledger.key(i) not in blocked]
            if missing:
                say("warn", f"{len(missing)} unfinished item(s) carry no estimate, so they count "
                            f"toward boxes but not toward effort")
            # A day written into the log but never recorded is a hole in every trend that
            # reads the history. Code and tokens are still recoverable -- git and the
            # transcripts keep them -- so the hole is worth naming while that is true.
            recorded = {r["date"] for r in read_stats() if r["project"] == p["name"]}
            gaps = sorted(d for d, _ in ledger.log_days() if d not in recorded)
            if gaps:
                shown = ", ".join(gaps[:3]) + (f" and {len(gaps) - 3} more" if len(gaps) > 3 else "")
                say("warn", f"{len(gaps)} logged day(s) never recorded: {shown}. "
                            f"`board.py collect --date <day>` recovers that day's code and "
                            f"tokens. Closed work is not recoverable and is left alone -- "
                            f"the ledger only holds today, so writing it would move the "
                            f"baseline and zero the newer day")
            # A marker pointing at a branch git has never heard of is either a typo or a
            # branch that was deleted after merging. Both leave the join silently dead, and
            # a dead join reads exactly like an item that has no branch.
            markers = ledger.branch_markers()
            if markers:
                known = set(_lines_of(_sh(["git", "branch", "--format=%(refname:short)"],
                                          root)))
                known |= set(_lines_of(_sh(["git", "branch", "-r",
                                            "--format=%(refname:short)"], root)))
                known |= {b[len("origin/"):] for b in known if b.startswith("origin/")}
                stale = sorted({b for b, _ in markers if b not in known})
                if stale:
                    say("warn", f"{len(stale)} `[branch ...]` marker(s) name a branch git "
                                f"does not have: {', '.join(stale[:3])}")
                else:
                    ok(f"{len(markers)} branch marker(s), all resolvable")
            # Two items answering to one key is not a syntax error and produces no message
            # anywhere: the recorded row holds both, and every reader builds a dict off the
            # key, so one of them silently wins and the other's closed work is never
            # counted. An `[id ...]` on either is the fix.
            seen_keys: dict = {}
            for i in ledger.items:
                seen_keys.setdefault(ledger.key(i), []).append(i["title"])
            clashes = {k: v for k, v in seen_keys.items() if len(v) > 1}
            if clashes:
                first = sorted(clashes)[0]
                say("FAIL", f"{len(clashes)} key(s) claimed by more than one item, so only "
                            f"one of each is recorded: `{first}` is used by "
                            f"{len(clashes[first])} items. Give one an `[id <name>]`")
            # A recorded key nothing answers to is a rename, a deletion or a phase move.
            # Each severs everything filed under it -- carry-over restarts, `item` finds
            # nothing, and the first snapshot after banks the item's closed boxes again.
            # Naming the orphan is the only honest report: which of the three it was cannot
            # be recovered from the ledger, since the old name is no longer in it.
            known = {ledger.key(i) for i in ledger.items}
            recorded = {i["k"] for r in read_stats()
                        if r["project"] == p["name"] and r.get("items")
                        for i in r["items"]}
            orphans = sorted(recorded - known)
            if orphans:
                say("warn", f"{len(orphans)} recorded key(s) no item answers to now: "
                            f"{', '.join(orphans[:3])}. A renamed, moved or deleted item "
                            f"leaves its history behind -- `[id <name>]` on an item makes "
                            f"its later renames free")
            # Said before the rename rather than after it. Every message about `[id ...]`
            # used to arrive as a remedy for damage already done -- a clash, or a key
            # nothing answers to -- by which point the history it protects is already
            # detached. One summary line, never one per item: a ledger of two hundred
            # items would otherwise bury every other thing on this page.
            unnamed = [i for i in ledger.items if not i["id"]]
            if unnamed:
                say("info", f"{len(unnamed)} of {len(ledger.items)} item(s) carry no "
                            f"`[id <name>]`, so each one's history is tied to its wording. "
                            f"Adding one now is free; adding it after a rename is too late")
            # Words used to classify an item as blocked on their own. They no longer do, so
            # a ledger written under the old rule would go quiet about its blockers. Named
            # rather than guessed at: `doctor` still reads the words, and says which lines
            # look like they want the marker.
            unmarked = [i for i in ledger.items
                        if ledger.state(i) != S.DONE and ledger.key(i) not in blocked
                        and S.blocker_hit(i["text"])]
            if unmarked:
                say("warn", f"{len(unmarked)} item(s) read as waiting but carry no "
                            f"`[blocked]` marker and sit outside a blocker section, so "
                            f"nothing treats them as blocked: "
                            f"{', '.join(i['title'] for i in unmarked[:3])}")
            # `[since 2026-13-45]` matches the marker's shape and then fails to parse, so
            # the age silently reads as "none" while the line looks answered -- it is also
            # excluded from the `blockers` hint that chases undated ones. Nothing else in
            # the tool would ever surface the typo.
            bad_since = [b for b in ledger.blockers() if b["bad_since"]]
            if bad_since:
                say("warn", f"{len(bad_since)} `[since ...]` marker(s) are not a real date, "
                            f"so those blockers have no age: "
                            f"{', '.join(b['title'] for b in bad_since[:3])}")
            over = [i for i in ledger.items if Ledger.overclaimed(i)]
            if over:
                worst = max(over, key=Ledger.overclaimed)
                say("warn", f"{len(over)} item(s) whose box shares total more than the "
                            f"item's estimate, worst by {Ledger.overclaimed(worst)} on "
                            f"`{worst['title']}` — under-estimated by that much, or a "
                            f"misplaced decimal. `/hey-tune` re-estimates it")

    print("history")
    if not STATS.exists():
        say("warn", f"{STATS} does not exist yet. Run `board.py collect`")
    else:
        raw = [ln for ln in STATS.read_text().splitlines() if ln.strip()]
        rows = read_stats()
        if len(rows) != len(raw):
            say("FAIL", f"{len(raw) - len(rows)} damaged line(s) in {STATS}")
        else:
            ok(f"{len(rows)} recorded day(s)")
        orphans = sorted({r["project"] for r in rows} - {p["name"] for p in cfg["projects"]})
        if orphans:
            say("warn", f"history for unregistered project(s): {', '.join(orphans)}")

    print()
    if counts["FAIL"]:
        print(f"{counts['FAIL']} problem(s), {counts['warn']} warning(s)")
    elif counts["warn"]:
        print(f"no problems, {counts['warn']} warning(s)")
    else:
        print("all checks passed")
    sys.exit(1 if counts["FAIL"] else 0)


def cmd_scope(args, cfg):
    cfg["scope"] = args.value
    save_config(cfg)
    print(f"default scope: {args.value}")


def cmd_resolve(args, cfg):
    p = resolve_project(cfg)
    if not p:
        # No escape: `resolve` takes neither `--project` nor `--scope`. It answers about
        # the directory you are standing in, or it does not answer.
        die_out_of_scope(escape=None)
    print(json.dumps(p, ensure_ascii=False))


def _each(args, cfg):
    projs = projects_in_scope(cfg, args.scope, args.project)
    if not projs:
        die_out_of_scope()
    for p in projs:
        if not Path(p["ledger"]).exists():
            print(f"[{p['name']}] ledger missing: {p['ledger']}")
            continue
        yield p, Ledger(p)


def cmd_progress(args, cfg):
    for p, led in _each(args, cfg):
        g = led.progress()
        print(f"[{p['name']}]")
        print(f"  checklist  {g['cb_done']}/{g['cb_total']} boxes")
        pct = round(g["done_ai"] * 100 / g["total_ai"], 1) if g["total_ai"] else 0
        print(f"  effort     {g['done_ai']}/{g['total_ai']} AI-days closed ({pct}%) · "
              f"{g['wip_ai']} in progress · "
              f"{round(g['wip_ai'] + g['todo_ai'], 2)} left")
        print(f"  items      {g['done_n']} done · {g['wip_n']} in progress · {g['todo_n']} not started")
        if args.phases:
            for ph in led.phases():
                part = f" ({ph['partial']} partial)" if ph["partial"] else ""
                print(f"    {ph['phase']:6} {ph['items']:3} items  {ph['done']:2} done{part:12}"
                      f"  {ph['cb_done']}/{ph['cb_total']} boxes"
                      f"  AI {ph['ai']}")


def cmd_snapshot(args, cfg):
    on = args.date or today_str()
    for p, led in _each(args, cfg):
        snap = record_progress(led, on)
        merge_stats(on, p["name"], snap)
        boxes = f"({snap['cb_done']}/{snap['cb_total']} boxes)"
        if snap.get("baseline"):
            print(f"[{p['name']}] {fmt_date(on)} recorded as the baseline {boxes}. "
                  f"Closed work is counted from the next record on")
        else:
            print(f"[{p['name']}] {fmt_date(on)} recorded. "
                  f"Closed today: {snap['earned_ai']} AI-days {boxes}")






def cmd_carryover(args, cfg):
    """Blockers that have aged, and items observed unfinished across snapshots.

    **Blockers come first, because their age is the sounder of the two numbers.** A dated
    `[since]` survives a machine with no history at all and survives an item being renamed.
    The carried-over count survives neither: it needs an unbroken run of snapshots, and the
    key it tracks is `<phase>|<title>`, so editing a title silently restarts the count at
    zero. A weaker signal printed above a stronger one gets read as the headline.

    The carried-over unit is **observations, not days.** A run of six means the item was
    seen unfinished in six consecutive recorded snapshots, and nothing here looks at the
    dates between them -- a gap does not break a run, so six observations can span two
    months. What breaks a run is a sample where the item is not in progress, or a title
    edit, since the key is `<phase>|<title>`. Everything here says "observations" for that
    reason; "days" is reserved for the blocker ages, which really are calendar days.

    And *unfinished*, never *unchanged*: the run is computed from the WIP state alone, so
    an item whose boxes closed steadily all week still counts every snapshot. Saying it
    was unchanged would assert something nothing here measured.
    """
    for p, led in _each(args, cfg):
        rows = [r for r in read_stats()
                if r["project"] == p["name"] and r.get("items")]
        if len(rows) < 2:
            need_history(p["name"], "carry-over", len(rows), 2)
            continue
        streak: dict[str, int] = {}
        for r in rows:
            wip = {i["k"] for i in r["items"] if i["state"] == S.WIP}
            for k in list(streak):
                if k not in wip:
                    del streak[k]
            for k in wip:
                streak[k] = streak.get(k, 0) + 1
        stale = sorted(((k, n) for k, n in streak.items() if n >= args.days),
                       key=lambda x: -x[1])
        as_of = rows[-1]["date"]
        first_seen: dict[str, str] = {}
        for r in rows:
            for k in r.get("blockers", []):
                first_seen.setdefault(k, r["date"])
        # *What* is blocked comes from the ledger, not from the last record: the ledger is
        # always the more current of the two, and a blocker cleared since the last snapshot
        # has no business being chased. *How old* it is comes from the line's own `[since]`
        # when it carries one -- which is the entire reason that marker exists, and reading
        # it here is what stops `blockers` and `carryover` reporting two different ages for
        # the same item. Records stay the fallback, so a ledger with no markers is unchanged.
        #
        # Both ages are measured to the last recorded day rather than to today. Mixing an
        # age-as-of-today with an age-as-of-the-last-record in one list would make the two
        # sources incomparable exactly where they sit side by side.
        old = []
        for b in led.blockers(as_of):
            if b["days"] is not None:
                old.append((b["key"], b["days"], "ledger"))
                continue
            # Three things leave a blocker with no age, and only two of them are a gap the
            # records may fill. `[since unknown]` says the start could not be found, so a
            # first-sighting is a useful floor; a malformed date is a typo `doctor` chases
            # separately. But a real date later than the day being measured is the line
            # stating that the wait has not begun -- answering that from the records would
            # override an explicit claim with the opposite one.
            if b["since"] not in (None, "unknown") and not b["bad_since"]:
                continue
            if b["key"] in first_seen:
                old.append((b["key"], (date.fromisoformat(as_of)
                                       - date.fromisoformat(first_seen[b["key"]])).days,
                            "records"))
        old.sort(key=lambda x: -x[1])
        aged = [x for x in old if x[1] >= args.days]
        span = f"{rows[0]['date']} ~ {rows[-1]['date']}"
        print(f"[{p['name']}]  {len(rows)} snapshots ({span})")
        # Blockers first: a `[since]` age is a calendar fact that survives both a missing
        # snapshot and a renamed item, and the count below survives neither.
        if aged:
            print(f"  long-standing blockers, in days waiting (as of {as_of}):")
            for k, n, src in aged[:8]:
                print(f"    - {k}  ({n} days, from the {src})")
        if stale:
            print(f"  observed unfinished in {args.days}+ consecutive snapshots:")
            for k, n in stale:
                print(f"    - {k}  ({n} observations)")
            print("  a snapshot is any recorded day, so this counts how often the item was\n"
                  "  sampled, not how long it has been open. Calendar gaps do not break a\n"
                  "  run -- two observations a fortnight apart are consecutive. What breaks\n"
                  "  it is a sample where the item is not in progress, or an edited title")
        if not stale and not aged:
            print(f"  no blocker waiting {args.days}+ days, nothing left unfinished across "
                  f"{args.days}+ snapshots")


def cmd_variance(args, cfg):
    """Estimate against **elapsed business days**, per item. No multiplier.

    There used to be a mean of the per-item ratios, offered as "multiply estimates by this
    to land nearer reality". It is not an effort calibration and cannot be one: the days
    counted are days the item was open, and an item waits for review, runs alongside other
    items, pauses on a blocker and gets its boxes ticked late. `/hey-run` exists to run
    several at once, so the tool encourages exactly the thing that inflates the number.
    `/hey-tune` warned not to take it at face value and `/hey-recap` warned again -- a
    figure that has to be disclaimed twice is not carrying information, and averaging
    ratios that are each confounded does not remove the confounding.

    The per-item rows stay. "Estimated 0.4, was open eight business days" is a fact worth
    looking at one at a time, and the reader knows what else was happening in those days.

    **Only items seen unfinished before they closed are measured.** An item already
    complete in the first record was finished before tracking began, so its duration is
    unknown; scoring it as one day would drag the multiplier toward zero and turn the
    advice upside down.
    """
    for p, led in _each(args, cfg):
        rows = [r for r in read_stats() if r["project"] == p["name"] and r.get("items")]
        if len(rows) < 2:
            need_history(p["name"], "estimate variance", len(rows), 2)
            continue
        first_open: dict[str, str] = {}
        first_wip: dict[str, str] = {}
        results: dict[str, tuple] = {}
        for r in rows:
            for i in r["items"]:
                k = i["k"]
                if i["state"] != S.DONE:
                    first_open.setdefault(k, r["date"])
                    if i["state"] == S.WIP:
                        first_wip.setdefault(k, r["date"])
                elif k in first_open and i["ai"]:
                    d0 = date.fromisoformat(first_wip.get(k, first_open[k]))
                    d1 = date.fromisoformat(r["date"])
                    workdays = sum(1 for n in range((d1 - d0).days + 1)
                                   if (d0 + timedelta(days=n)).weekday() < 5)
                    results[k] = (i["ai"], workdays)
                    first_open.pop(k, None)
                    first_wip.pop(k, None)
        if not results:
            print(f"[{p['name']}] no item has been seen closing yet, so there is nothing to "
                  f"measure. Items already complete in the first record are excluded")
            continue
        print(f"[{p['name']}] estimate vs elapsed, per item ({len(results)} measured)")
        for k, (ai, wd) in results.items():
            print(f"  {k:44} est AI {ai:5} -> {wd} business day(s) elapsed")
        print("  elapsed from when the item was first seen started -- or first seen at "
              "all, if it\n  never passed through in-progress -- to when it was first "
              "seen closed. Not effort:\n  an item waits for review, shares its days "
              "with other items and pauses on blockers.\n  Read these one at a time and "
              "ask what share of each span went to the item")


def cmd_burndown(args, cfg):
    """The trend of estimated work remaining. **A trend, not a rate.**

    The figure is `wip_ai + todo_ai` off each snapshot, and it moves for four different
    reasons: work closed, scope added, scope removed, an item re-estimated. Dividing its
    fall by the number of snapshots therefore does not produce a delivery rate, and the
    runway that used to be divided out of it -- "the remaining 80.85 is about 2788 days" --
    was absurd often enough that `/hey-recap` carried instructions for explaining it away.

    What is left is the shape and the endpoints, which do answer a real question: is the
    remaining work going down at all.
    """
    bars = " ▁▂▃▄▅▆▇█"
    for p, _ in _each(args, cfg):
        rows = [r for r in read_stats()
                if r["project"] == p["name"] and "wip_ai" in r]
        if len(rows) < 2:
            need_history(p["name"], "the burndown trend", len(rows), 2)
            continue
        rows = rows[-args.days:]
        vals = [round(r["wip_ai"] + r["todo_ai"], 2) for r in rows]
        lo, hi = min(vals), max(vals)
        if hi == lo:
            # A flat series normalises to all zeros, which prints as blanks. Draw a flat line.
            spark = "▄" * len(vals)
        else:
            spark = "".join(bars[min(8, int((v - lo) / (hi - lo) * 8))] for v in vals)
        print(f"[{p['name']}] AI-days left  {vals[0]} -> {vals[-1]}   {spark}")
        print(f"  {rows[0]['date']} ~ {rows[-1]['date']} · {len(rows)} days · "
              f"net change {round(vals[-1] - vals[0], 2):+}")
        print("  the line moves on closed work, added scope, removed scope and "
              "re-estimates alike,\n  so a fall is not a delivery rate and no runway can "
              "be divided out of it")


def cmd_note(args, cfg):
    """Insert a note at the top of the ledger's notes section, under today's date."""
    projs = projects_in_scope(cfg, "current", args.project)
    if not projs:
        # A note goes into one ledger, so `--scope all` is not a way out of this.
        die_out_of_scope(escape="project")
    p = projs[0]
    # The note goes wherever the notes heading actually lives. With the halves split, the
    # primary ledger has no such heading, and inserting there would put the note in a file
    # nothing reads it from.
    led = Ledger(p)
    path = led.log_path if (led.log_path and not led._own_section("notes")) else Path(p["ledger"])
    if not path.exists():
        die(f"ledger not found: {path}")

    cwd = Path.cwd()
    branch = _sh(["git", "branch", "--show-current"], cwd)
    head = _sh(["git", "rev-parse", "--short", "HEAD"], cwd)
    bits = []
    for f in args.file or []:
        bits.append(f"`{f}`")
    for d in args.doc or []:
        bits.append(d)
    if branch:
        bits.append(f"branch `{branch}`")
    if head:
        bits.append(f"`{head}`")
    stamp = datetime.now().strftime("%H:%M")
    bullet = f"- {stamp} {args.text}" + (f" — {' · '.join(bits)}" if bits else "")

    text = path.read_text()
    today = today_str()
    header = f"### {fmt_date(today)}"
    heads = tuple(f"## {n}" for n in S.section_aliases("notes"))
    lines = text.split("\n")
    at = next((i for i, ln in enumerate(lines) if ln.startswith(heads)), None)
    if at is None:
        die("ledger has no notes section. Add one - see templates/LEDGER.md")
    # Skip the section blurb, stopping at the first `### `, the next `## `, or a `---`.
    # Without `---` as a stop, notes slide below the rule and look like the next section.
    j = at + 1
    while j < len(lines) and not (
        lines[j].startswith(("### ", "## ")) or lines[j].strip() == "---"
    ):
        j += 1
    # Match on the ISO date, not the whole heading: the weekday is rendered in whichever
    # language was active when the heading was written, and that can change.
    existing = Ledger.DAY.match(lines[j]) if j < len(lines) else None
    if existing and existing[1] == today:
        lines.insert(j + 2, bullet)
    else:
        lines[j:j] = [header, "", bullet, ""]
    path.write_text("\n".join(lines))
    print(f"[{p['name']}] note added -> {path}\n{bullet}")


def _blocker_age(b: dict) -> tuple[str, str | None]:
    """(what goes in the age column, what that mark means when it is not a number).

    Four different things leave a blocker with no age, and each calls for a different
    move: a date that is not a date is a typo to fix, a date the calendar has not reached
    says the wait has not started, `unknown` is settled and wants nothing, and no marker at
    all is a question nobody has asked yet. One dash for all four made the last three
    indistinguishable from each other on the one screen where you go to triage them.

    The marks are ASCII on purpose. This column is right-aligned, and an arrow, a bullet or
    an em dash is East Asian Width `A` -- one column by measurement, two as drawn in a CJK
    terminal, which is the same trap `strings.MARK` documents for the section glyphs. The
    self-test holds every mark this can return to that rule.
    """
    if b["days"] is not None:
        return f'{b["days"]}d', None
    if b["bad_since"]:
        return "!", "`[since]` is not a real date, so no age can be read from it"
    if b["since"] == "unknown":
        return "?", "the start could not be found, and that is a settled answer"
    if b["since"]:
        return ">", "dated ahead of today, so the wait has not started"
    return "-", "no start recorded. Add `[since YYYY-MM-DD]`, or `[since unknown]`"


def cmd_blockers(args, cfg):
    """Every blocked item, oldest wait first.

    The card shows three and counts the rest, and until this existed the rest could not be
    read anywhere -- `progress` totals phases, `batch` only says how many it excluded, and
    `carryover` wants a history the first week does not have.
    """
    for p, led in _each(args, cfg):
        rows = led.blockers()
        if not rows:
            print(f"[{p['name']}] nothing blocked")
            continue
        rows.sort(key=lambda b: -(b["days"] if b["days"] is not None else -1))
        print(f"[{p['name']}] {len(rows)} blocked")
        # Only the marks actually used get explained. A fixed legend is four lines of the
        # same noise every day, and noise is what teaches the reader to skip the line that
        # was about their typo.
        legend: dict[str, str] = {}
        for b in rows:
            age, note = _blocker_age(b)
            if note:
                legend[age] = note
            print(f"  {age:>5}  {clip_to(b['shown'], card_width()[0] - 9)}")
        for mark, note in legend.items():
            print(f"  {mark:>5}  {note}")


def cmd_notes(args, cfg):
    for p, led in _each(args, cfg):
        body = led.section_body("notes")
        days, cur = [], None
        for ln in body:
            if m := Ledger.DAY.match(ln):
                cur = (m[1], [])
                days.append(cur)
            elif cur and ln.strip().startswith("- "):
                cur[1].append(ln.strip()[2:])
        cutoff = (date.today() - timedelta(days=args.since)).isoformat()
        shown = [(d, b) for d, b in days if d >= cutoff]
        print(f"[{p['name']}] {sum(len(b) for _, b in shown)} note(s) in the last {args.since} days")
        for d, bullets in shown:
            print(f"  {fmt_date(d)}")
            for b in bullets:
                print(f"    - {b}")


def cmd_log(args, cfg):
    for p, led in _each(args, cfg):
        days = led.log_days()
        print(f"[{p['name']}] work log: {len(days)} day(s)")
        for d, bullets in days[:args.limit]:
            print(f"  {fmt_date(d)}")
            for b in bullets:
                print(f"    - {b}")


def cmd_next(args, cfg):
    for p, led in _each(args, cfg):
        print(f"[{p['name']}] next up")
        for ln in led.next_up()[:args.limit]:
            print(f"  {ln}")


def cmd_dirty(args, cfg):
    """Work that never left as a commit or PR. The easiest state to forget, so it gets its own view."""
    for p in projects_in_scope(cfg, args.scope, args.project):
        root = Path(p["root"])
        led = Ledger(p) if Path(p["ledger"]).exists() else None
        base = args.base or project_base(cfg, p)
        found, comparable = False, True
        for w in worktree_roots(root):
            st = _sh(["git", "status", "--short"], w)
            br = _sh(["git", "branch", "--show-current"], w)
            ahead, ok = ahead_of_base(w, base)
            gone, has_up = unpushed(w, base)
            comparable = comparable and ok
            if st or gone or ahead:
                found = True
                owner = led.item_for_branch(br) if led else None
                whose = f"  {DOT} {owner['title']}" if owner else ""
                print(f"[{p['name']}] {w}  ({br or 'detached'}){whose}")
                # Two different facts, and only the first is work at risk. A pushed branch
                # awaiting review is ahead of the base as well, and calling that unpushed
                # is what made this view cry wolf.
                if gone:
                    where = "unpushed" if has_up else "on a branch never pushed"
                    print(f"    {gone} commit(s) {where}")
                if ahead and not gone:
                    print(f"    {len(ahead)} commit(s) pushed but not in origin/{base}")
                if st:
                    print(f"    {len(st.split(chr(10)))} uncommitted file(s)")
                    for f in st.split("\n")[:5]:
                        print(f"      {f}")
        if not comparable:
            missing = f"origin/{base} not found" if base else "no remote default branch"
            print(f"[{p['name']}] unpushed commits were NOT checked ({missing}). "
                  f'Set "base" for this project in {CONFIG}')
        elif not found:
            print(f"[{p['name']}] nothing uncommitted or unpushed")


BACKTICK = re.compile(r"`([^`]+)`")
# Not everything in backticks is code. Annotation markers are excluded from overlap.
CODEISH = re.compile(r"^[A-Za-z_@./][\w./+@-]{2,}$")


def code_tokens(text: str) -> set:
    return {t for t in BACKTICK.findall(text) if CODEISH.match(t)}


def cmd_batch(args, cfg):
    """List loop candidates with mechanical evidence about running them in parallel.

    Three signals. **The final call is made by a human and the model** — this only
    supplies evidence.
      depends   the item body names another item, so that one comes first
      overlap   backtick tokens (modules, files, types) are shared, so the two may
                touch the same file
      blocked   the item marks itself as waiting, so it is excluded
    """
    for p, led in _each(args, cfg):
        pending = [i for i in led.items if led.state(i) != S.DONE]
        blocked = {b["key"] for b in led.blockers()}
        cand = [i for i in pending if led.key(i) not in blocked][: args.limit]
        if not cand:
            print(f"[{p['name']}] no candidates. Check whether the {len(blocked)} blocker(s) are in the way")
            continue
        titles = {led.key(i): i["title"] for i in led.items}
        tokens = {led.key(i): code_tokens(i["text"]) for i in led.items}

        print(f"[{p['name']}] {len(cand)} candidate(s), {len(blocked)} blocked item(s) excluded")
        budget = 0.0
        for i in cand:
            k = led.key(i)
            deps = [t for kk, t in titles.items()
                    if kk != k and len(t) > 3 and t in i["text"]]
            budget += i["ai"]
            print(f"  - {k}  AI {i['ai']}  ({led.state(i)}, "
                  f"{led.boxes(i)[0]}/{led.boxes(i)[1]} boxes)")
            if deps:
                print(f"      mentions first: {', '.join(deps[:3])}")
        print(f"  candidate total: {round(budget, 2)} AI-days")

        print("  overlap (may touch the same files):")
        found = False
        for a in range(len(cand)):
            for b in range(a + 1, len(cand)):
                ka, kb = led.key(cand[a]), led.key(cand[b])
                shared = tokens[ka] & tokens[kb]
                if shared:
                    found = True
                    print(f"    {cand[a]['title']} × {cand[b]['title']}"
                          f"  → {', '.join(sorted(shared)[:4])}")
        if not found:
            # Absence of evidence, stated as absence of evidence. This compares backtick
            # tokens in the item text, so it cannot see a shared file under a different
            # name, a generated output, or a manifest both items touch -- and `/hey-run`
            # says in as many words never to decide from this output alone. Printing "these
            # can run in parallel" was the script overruling its own skill.
            print("    no overlap evidence in the item text. Read the code before "
                  "running these together")


def match_marker(keys, marker: str) -> tuple:
    """(the one key this marker names, the candidates when it names several).

    Exactly one of the two is ever non-empty. A marker cannot carry a whole key: the
    pattern that finds it stops at whitespace and every key holds a title, so `closes
    P0|First item` arrives here as `P0|First`. Matching on a fragment is therefore the
    design, not a shortcut -- and a fragment that fits several items is the cost of it.

    Taking the first fit silently was the problem. `closes P0` fits every item in the
    phase, and the report named one of them, chosen by whichever order the dict happened
    to be in. `item` already refuses to guess in exactly this situation and lists what it
    found; this does the same.

    An exact key still wins outright, so a marker that is also a fragment of longer keys
    resolves rather than reading as ambiguous.

    The old test was `marker in k or k.endswith(marker)`. The second half cannot be true
    while the first is false, so it selected nothing extra -- it only suggested there was a
    suffix case being handled, and there is not.
    """
    if marker in keys:
        return marker, []
    hits = sorted(k for k in keys if marker in k)
    return (hits[0], []) if len(hits) == 1 else (None, hits)


def cmd_pr_sync(args, cfg):
    """Collect `closes <item key>` markers from merged PR bodies. Never checks anything off."""
    for p, led in _each(args, cfg):
        root = Path(p["root"])
        raw = _sh(["gh", "pr", "list", "--state", "merged", "--limit", str(args.limit),
                   "--json", "number,title,body,mergedAt"], root)
        if not raw:
            print(f"[{p['name']}] could not read PRs via gh")
            continue
        keys = {led.key(i): i for i in led.items}
        found = 0
        for pr in json.loads(raw):
            marks = re.findall(r"(?:closes|닫음)\s+([^\s,]+)", pr.get("body") or "",
                               flags=re.IGNORECASE)
            if not marks:
                continue
            print(f"[{p['name']}] #{pr['number']} {pr['title']}"
                  f"  ({(pr.get('mergedAt') or '')[:10]})")
            for m in marks:
                hit, ambiguous = match_marker(keys, m)
                if hit:
                    state = Ledger.state(keys[hit])
                    flag = "already closed" if state == S.DONE else "still unchecked"
                    print(f"    {m} -> {hit}  [{flag}]")
                elif ambiguous:
                    print(f"    {m} -> matches {len(ambiguous)} items, so it names none "
                          f"of them:")
                    for k in ambiguous[:5]:
                        print(f"         {k}")
                    if len(ambiguous) > 5:
                        print(f"         and {len(ambiguous) - 5} more")
                else:
                    print(f"    {m} -> not found in ledger")
            found += 1
        if not found:
            print(f"[{p['name']}] no `closes <item key>` markers in the last "
                  f"{args.limit} merged PRs")


def cmd_item(args, cfg):
    """One item's history across every record: when it opened, how long it has been open.

    `carryover` says what is stuck and `variance` says by how much estimates were off.
    Neither answers "what happened to this one", which is the question actually asked when
    an item has been sitting open for a fortnight.
    """
    for p, led in _each(args, cfg):
        keys = {led.key(i): i for i in led.items}
        needle = args.key.lower()
        hits = [k for k in keys if needle in k.lower()]
        if not hits:
            print(f"[{p['name']}] no item matches {args.key!r}. `hey.py progress --phases` "
                  f"lists the phases")
            continue
        if len(hits) > 1 and args.key not in hits:
            print(f"[{p['name']}] {args.key!r} matches {len(hits)} items:")
            for k in sorted(hits)[:10]:
                print(f"  - {k}")
            continue
        key = args.key if args.key in hits else hits[0]
        item = keys[key]
        rows = [r for r in read_stats() if r["project"] == p["name"] and r.get("items")]

        print(f"[{p['name']}] {key}")
        print(f"  now       {led.state(item)}, {led.boxes(item)[0]}/{led.boxes(item)[1]} "
              f"boxes, AI {item['ai']}")
        if Ledger.key(item) in {b["key"] for b in led.blockers()}:
            print("  blocked   marked `[blocked]`, or sitting in a blocker section")

        seen = [(r["date"], i) for r in rows for i in r["items"] if i["k"] == key]
        if not seen:
            print("  history   no record covers this item yet")
            continue
        print(f"  history   {len(seen)} record(s), {seen[0][0]} to {seen[-1][0]}")
        prev = None
        for on, snap in seen:
            marks = []
            if prev is None:
                marks.append(f"first seen {snap['state']}")
            else:
                if snap["state"] != prev["state"]:
                    marks.append(f"{prev['state']} -> {snap['state']}")
                if snap["closed"] != prev["closed"]:
                    marks.append(f"boxes {prev['closed']} -> {snap['closed']}")
                if snap["ai"] != prev["ai"]:
                    marks.append(f"estimate AI {prev['ai']} -> {snap['ai']}")
            if marks:
                print(f"    {fmt_date(on)}  {' · '.join(marks)}")
            prev = snap
        # Open days are counted in records, not calendar days: a day nothing was recorded
        # on is not evidence that the item sat still.
        open_records = sum(1 for _, s in seen if s["state"] != S.DONE)
        if open_records:
            print(f"  open in   {open_records} of {len(seen)} record(s)")


def cmd_context(args, cfg):
    """Where and what you touched yesterday (or a given day). For rebuilding context."""
    on = args.date or (date.today() - timedelta(days=1)).isoformat()
    for p in projects_in_scope(cfg, args.scope, args.project):
        root = Path(p["root"])
        print(f"[{p['name']}] {fmt_date(on)}")
        for w in worktree_roots(root):
            log = _sh(["git", "log", "--all", *day_range(on),
                       "--format=%h %s"], w)
            files = _sh(["git", "log", "--all", *day_range(on),
                         "--name-only", "--format="], w)
            st = _sh(["git", "status", "--short"], w)
            br = _sh(["git", "branch", "--show-current"], w)
            touched = sorted({f for f in files.split("\n") if f.strip()})
            if not (log or st):
                continue
            print(f"  {w}  ({br or 'detached'})")
            for ln in log.split("\n")[:5]:
                if ln.strip():
                    print(f"    commit {ln}")
            for f in touched[: args.files]:
                print(f"    touched {f}")
            if len(touched) > args.files:
                print(f"    ... and {len(touched) - args.files} more")
            if st:
                print(f"    {len(st.split(chr(10)))} uncommitted - this is where to pick up")


def cmd_draft_log(args, cfg):
    """Work-log headings and bullets drafted from git history. Prints; never writes.

    A ledger created today has no past, so the first `/wassup` has nothing to report on a
    repository that may hold months of work. Turning commits into a first draft is
    mechanical and belongs here. Deciding whether a draft is *true* is not: a commit
    subject says what changed, not how far the work got or what is left, and those are the
    two things the work log exists to carry. So this stops at stdout. The skill shows the
    draft, the user corrects it, and only then does anything reach the ledger -- the same
    rule that keeps a box from being ticked by a marker nobody verified.
    """
    for p in projects_in_scope(cfg, args.scope, args.project):
        root = Path(p["root"])
        # Same resolution as code counting, for the same reason: the work log records
        # *your* days, and a shared repository is full of other people's commits.
        author = (args.author or cfg.get("author")
                  or _sh(["git", "config", "user.email"], root))
        if not author:
            print(f"[{p['name']}] no git author resolved, so every author's commits are "
                  f"drafted. Pass --author to narrow it")
        last = date.today()
        first = last - timedelta(days=args.since - 1)
        # Both ends borrowed from `day_range` rather than spelled out again -- it is the
        # one place that knows a day ends at 23:59:59 and not at 23:59.
        span = [day_range(first.isoformat())[0], day_range(last.isoformat())[1]]

        by_day, seen = {}, set()
        for w in worktree_roots(root):
            # Per worktree, because a detached one holds a HEAD that `--all` cannot see
            # from anywhere else -- then deduplicated, because every other ref is shared.
            cmd = ["git", "log", "--all", "--no-merges", *span,
                   "--date=format:%Y-%m-%d", "--format=%cd %h %s"]
            if author:
                cmd.insert(2, f"--author={author}")
            for ln in _sh(cmd, w).split("\n"):
                parts = ln.split(" ", 2)
                if len(parts) < 3 or parts[1] in seen:
                    continue
                seen.add(parts[1])
                by_day.setdefault(parts[0], []).append((parts[1], parts[2]))

        if not by_day:
            print(f"[{p['name']}] no commits by {author or 'anyone'} in the last "
                  f"{args.since} day(s). Nothing to draft")
            continue
        print(f"[{p['name']}] draft from {len(seen)} commit(s) over {len(by_day)} day(s). "
              f"**Not a work log yet** - a commit says what changed, not how far it got")
        for on in sorted(by_day, reverse=True):
            rows = by_day[on]
            print(f"\n### {fmt_date(on)}\n")
            # Five is the ledger's own ceiling for a day's bullets. Past it the draft says
            # how many it left out rather than quietly dropping them, because a day with
            # twenty commits is exactly the day worth writing up by hand.
            for sha, subject in rows[:5]:
                print(f"- {subject} ({sha})")
            if len(rows) > 5:
                print(f"- ... and {len(rows) - 5} more commit(s) this day, not listed")


def main() -> None:
    ap = argparse.ArgumentParser(prog="hey.py", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        sp = sub.add_parser(name, **kw)
        sp.set_defaults(fn=fn)
        return sp

    def scoped(sp):
        sp.add_argument("--project", help="a single project by name")
        sp.add_argument("--scope", choices=["current", "all"], help="defaults to the scope in config")
        return sp

    add("projects", cmd_projects, help="list registered projects")
    sp = add("add", cmd_add, help="register a project")
    sp.add_argument("root")
    sp.add_argument("--ledger", help="ledger path (default: <root>/TASKS.local.md)")
    sp.add_argument("--ledger-log", dest="ledger_log",
                    help="second file holding the append-only sections (work log, notes)")
    sp.add_argument("--name")
    sp.add_argument("--base", help="branch to measure unpushed commits against "
                                  "(default: the remote's own default branch)")
    sp.add_argument("--init", action="store_true",
                    help="create the ledger from templates/LEDGER.md if it is missing")
    sp = add("remove", cmd_remove, help="unregister a project (keeps ledger and history)")
    sp.add_argument("name")
    add("doctor", cmd_doctor, help="report anything misconfigured")
    sp = add("scope", cmd_scope, help="set the default scope")
    sp.add_argument("value", choices=["current", "all"])
    add("resolve", cmd_resolve, help="which project the cwd belongs to")

    sp = scoped(add("progress", cmd_progress, help="progress totals"))
    sp.add_argument("--phases", action="store_true", help="include per-phase rows")
    sp = scoped(add("snapshot", cmd_snapshot, help="record today's state into stats.jsonl"))
    sp.add_argument("--date")
    sp = scoped(add("carryover", cmd_carryover, help="carried-over items and aged blockers"))
    sp.add_argument("--days", type=int, default=3,
                    help="threshold: calendar days for blocker age, consecutive recorded "
                         "snapshots for carried-over items. The two are not the same unit "
                         "-- a run of snapshots ignores the gaps between them")
    scoped(add("variance", cmd_variance, help="estimate vs actual"))
    sp = scoped(add("burndown", cmd_burndown, help="trend of AI-days remaining"))
    sp.add_argument("--days", type=int, default=14)

    sp = scoped(add("note", cmd_note, help="add a note"))
    sp.add_argument("text")
    sp.add_argument("--file", action="append", help="related file (repeatable)")
    sp.add_argument("--doc", action="append", help="related doc or link (repeatable)")
    scoped(add("blockers", cmd_blockers, help="every blocked item, oldest wait first"))
    sp = scoped(add("notes", cmd_notes, help="read notes"))
    sp.add_argument("--since", type=int, default=7, help="how many days back")
    sp = scoped(add("log", cmd_log, help="read the work log"))
    sp.add_argument("--limit", type=int, default=3)
    sp = scoped(add("next", cmd_next, help="what is next up"))
    sp.add_argument("--limit", type=int, default=5)
    sp = scoped(add("dirty", cmd_dirty, help="uncommitted or unpushed work"))
    sp.add_argument("--base", help="override the project's base branch for this call")
    sp = scoped(add("batch", cmd_batch, help="loop candidates and parallel-safety evidence"))
    sp.add_argument("--limit", type=int, default=6)
    sp = scoped(add("pr-sync", cmd_pr_sync, help="collect `closes` markers from merged PRs"))
    sp.add_argument("--limit", type=int, default=10)
    sp = scoped(add("item", cmd_item, help="one item's history across the records"))
    sp.add_argument("key", help="`<phase>|<name>`, or any part of it")
    sp = scoped(add("context", cmd_context, help="worktrees, branches and files touched on a date"))
    sp.add_argument("--date")
    sp.add_argument("--files", type=int, default=6)
    sp = scoped(add("draft-log", cmd_draft_log,
                    help="work-log entries drafted from git history. Prints, never writes"))
    sp.add_argument("--since", type=int, default=14, help="how many days back")
    sp.add_argument("--author", help="defaults to the repository's `user.email`")

    args = ap.parse_args()
    args.fn(args, load_config())


if __name__ == "__main__":
    main()
