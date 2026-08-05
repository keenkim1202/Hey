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
    before the meter starts, and anything narrower makes them overflow.

    `doctor` reports the source, so returning it beats making the caller re-derive it.
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


def wider_card_available(card: int, terminal: int | None) -> int | None:
    """The width the card could reach on this terminal, when that beats what it has.

    None means there is nothing to act on -- no reading, already at the ceiling, or a
    terminal no wider than the card. A warning the user cannot clear is noise, and noise
    is what teaches them to skim past the warnings that matter.
    """
    if not terminal:
        return None
    could = min(CARD_MAX, terminal - 2)
    return could if could > card else None


def terminal_columns() -> int | None:
    """Columns of the pty this process hangs off, walking up to find one.

    A pipe has no terminal of its own, but the session that spawned it usually does, a few
    parents up. Asking that device directly is the only probe here that returns a real
    number rather than an 80-column fallback.

    `card_width` deliberately does not call this. A pty's window size is not the width of
    the fenced block an agent pastes a card into, and silently guessing wrong there is
    worse than the default. It exists so `doctor` can offer a number to confirm, which is
    cheaper than opening with a ruler when the two usually agree.

    None whenever the answer would be a guess: no tty in the ancestry, an unreadable
    device, or an `stty` that wants the other flag.
    """
    pid, seen = os.getpid(), 0
    while pid > 1 and seen < 12:
        seen += 1
        out = _sh(["ps", "-o", "ppid=,tty=", "-p", str(pid)], Path.cwd())
        if not out:
            return None
        parts = out.split()
        if len(parts) < 2:
            return None
        parent, tty = parts[0], parts[-1]
        if tty not in ("??", "-", "?"):
            # BSD spells the device flag `-f`, GNU spells it `-F`. Neither knows the other.
            for flag in ("-f", "-F"):
                size = _sh(["stty", flag, f"/dev/{tty}", "size"], Path.cwd()).split()
                if len(size) == 2 and size[1].isdigit() and int(size[1]) > 0:
                    return int(size[1])
            return None
        pid = int(parent) if parent.isdigit() else 0
    return None


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
    if len(cfg["projects"]) == 1:
        return list(cfg["projects"])
    return []


def die(msg: str) -> None:
    print(f"hey: {msg}", file=sys.stderr)
    sys.exit(2)


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
    # Which branch an item's work lives on. Branches outlast worktrees, whose paths are
    # temporary, and they are what commits and pull requests actually attach to.
    BRANCH = re.compile(r"\[branch ([^\]\s]+)\]")
    # Every marker, for stripping them back out of anything a person reads.
    MARKERS = re.compile(r"`?\[(?:AI \d+\.?\d*|since (?:\d{4}-\d{2}-\d{2}|unknown)"
                         r"|branch [^\]\s]+)\]`?")

    def __init__(self, project: dict):
        self.project = project
        self.path = Path(project["ledger"])
        self.text = self.path.read_text() if self.path.exists() else ""
        self.lines = self.text.split("\n")
        self.items: list[dict] = []
        self._parse()

    def _parse(self) -> None:
        section, cur = None, None
        for ln in self.lines:
            if ln.startswith("## "):
                section, cur = ln[3:].strip(), None
                continue
            if m := self.ITEM.match(ln):
                est = self.EST.search(m[2])
                cur = {
                    "section": section or "?",
                    "phase": (section or "?").split(".")[0].split(" ")[0],
                    "title": self._title(m[2]),
                    "text": m[2],
                    "done": m[1].lower() == "x",
                    "kids": [],
                    "kid_ai": [],
                    "branches": self.BRANCH.findall(m[2]),
                    "md": float(est[1]) if est else 0.0,
                    "ai": float(est[2]) if est else 0.0,
                }
                self.items.append(cur)
            elif (k := self.KID.match(ln)) and cur is not None:
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
        scoped = [i for i in self.items if i["ai"]]
        cb_done = sum(self.boxes(i)[0] for i in self.items)
        cb_total = sum(self.boxes(i)[1] for i in self.items)
        by_state = {s: [i for i in scoped if self.state(i) == s] for s in (S.DONE, S.WIP, S.TODO)}
        return {
            "cb_done": cb_done,
            "cb_total": cb_total,
            "cb_pct": round(cb_done * 100 / cb_total, 1) if cb_total else 0.0,
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
                "cb_pct": round(cd * 100 / ct, 1) if ct else 0.0,
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
            in_text = S.blocker_hit(it["text"])
            if in_section or in_text:
                m = self.SINCE.search(it["text"])
                days = None
                if m and m[1] != "unknown":
                    try:
                        days = (date.fromisoformat(today) - date.fromisoformat(m[1])).days
                    except ValueError:
                        days = None
                # The title is a key first, and a key that reads well is a coincidence.
                # The listing wants the line as written, minus the markup and the markers.
                shown = self.MARKERS.sub("", it["text"]).replace("**", "").replace("`", "")
                out.append({"key": self.key(it), "title": it["title"],
                            "shown": " ".join(shown.split()),
                            "section": it["section"],
                            "since": m[1] if m else None,
                            "days": days if days is None or days >= 0 else None})
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
        return f"{it['phase']}|{it['title']}"

    # -- section bodies

    def section_body(self, key: str, level: str = "## ") -> list[str]:
        """Body lines of a section, found by any of its language aliases."""
        names = S.section_aliases(key)
        out, inside = [], False
        for ln in self.lines:
            if ln.startswith(level):
                if inside:
                    break
                inside = ln[len(level):].strip().startswith(names)
                continue
            if inside:
                out.append(ln)
        return out

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

    def has_section(self, key: str, level: str = "## ") -> bool:
        """Is the heading present at all? A section can exist and still be empty."""
        names = S.section_aliases(key)
        return any(ln.startswith(level) and ln[len(level):].strip().startswith(names)
                   for ln in self.lines)

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
    hit.update(fields)
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

    entry = {"name": name, "root": str(root), "ledger": str(ledger)}
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
    print(f"registered: {name}\n  root:   {root}\n  ledger: {ledger}{note}")
    if base:
        print(f"  base:   origin/{base}"
              f"{'' if args.base else '  (detected)'}")
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
            say("warn", f"{tool} not found - the PR log step is skipped")
    ok(f"language {S.lang(cfg)}")
    cols, source = card_width()
    ok(f"card width {cols} ({source})")
    real = terminal_columns()
    could = wider_card_available(cols, real)
    if could:
        # The pty is the window and not the width of a fenced block, so this asks for a
        # confirmation rather than telling anyone to write the number down.
        say("warn", f"terminal looks {real} columns wide, so the card could be {could} "
                    f"instead of {cols}. Confirm the usable width, then set HEY_WIDTH")

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
        for key in ("notes", "log", "next", "prs", "summary"):
            level = "### " if key == "next" else "## "
            if not ledger.has_section(key, level):
                names = " / ".join(S.section_aliases(key))
                say("warn", f"no `{names}` heading - whatever reads it returns nothing")
        if not ledger.items:
            say("warn", "no checklist items found. Is the estimate format `N MD / AI M`?")
        else:
            g = ledger.progress()
            ok(f"{len(ledger.items)} item(s), {g['cb_total']} box(es), AI {g['total_ai']}")
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
                            f"`board.py collect --date <day>` recovers code and tokens, "
                            f"but closed boxes are gone -- the ledger only holds today")
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
        die("not inside a registered project. Run `hey.py add <path>`")
    print(json.dumps(p, ensure_ascii=False))


def _each(args, cfg):
    projs = projects_in_scope(cfg, args.scope, args.project)
    if not projs:
        die("no project in scope. Check `hey.py projects`, or pass `--scope all`")
    for p in projs:
        if not Path(p["ledger"]).exists():
            print(f"[{p['name']}] ledger missing: {p['ledger']}")
            continue
        yield p, Ledger(p)


def cmd_progress(args, cfg):
    for p, led in _each(args, cfg):
        g = led.progress()
        print(f"[{p['name']}]")
        print(f"  checklist  {g['cb_done']}/{g['cb_total']} boxes ({g['cb_pct']}%)")
        pct = round(g["done_ai"] * 100 / g["total_ai"], 1) if g["total_ai"] else 0
        print(f"  effort     {g['done_ai']}/{g['total_ai']} AI-days closed ({pct}%) · "
              f"{g['wip_ai']} in progress · "
              f"{round(g['wip_ai'] + g['todo_ai'], 2)} left")
        print(f"  items      {g['done_n']} done · {g['wip_n']} in progress · {g['todo_n']} not started")
        if args.phases:
            for ph in led.phases():
                part = f" ({ph['partial']} partial)" if ph["partial"] else ""
                print(f"    {ph['phase']:6} {ph['items']:3} items  {ph['done']:2} done{part:12}"
                      f"  {ph['cb_done']}/{ph['cb_total']} boxes ({ph['cb_pct']}%)"
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


def cmd_rank(args, cfg):
    """Today ranked against your own past records. Never against other people."""
    on = args.date or today_str()
    for p, _ in _each(args, cfg):
        rows = [r for r in read_stats() if r["project"] == p["name"] and "earned_ai" in r]
        if not rows:
            need_history(p["name"], "ranking today against your past", len(rows), 1)
            continue
        today = next((r for r in rows if r["date"] == on), None)
        past = [r for r in rows if r["date"] != on]
        if today is None:
            print(f"[{p['name']}] no snapshot for {on}. Run `hey.py snapshot` first")
            continue
        # Ranked inside a pool that includes today. Excluding today gives "#5 of 4".
        pool = past[-args.window:] + [today]
        ranked = sorted(pool, key=lambda r: (-r["earned_ai"], r["date"]))
        rank = next(i + 1 for i, r in enumerate(ranked) if r["date"] == on)
        avg = round(sum(r["earned_ai"] for r in pool) / len(pool), 3)
        best = ranked[0]["earned_ai"]
        print(f"[{p['name']}] today {today['earned_ai']} AI-days — "
              f"#{rank} of {len(pool)} recorded days (avg {avg} · best {best})")
        # A day that closed nothing is not a personal best, even when every recorded day
        # closed nothing. The ledger's own rule is that a zero is reported as a zero.
        if today["earned_ai"] and today["earned_ai"] >= best:
            print("  personal best.")


def cmd_carryover(args, cfg):
    """Items stuck in progress across snapshots, and blockers that have aged."""
    for p, led in _each(args, cfg):
        rows = [r for r in read_stats() if r["project"] == p["name"]]
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
        first_seen: dict[str, str] = {}
        for r in rows:
            for k in r.get("blockers", []):
                first_seen.setdefault(k, r["date"])
        old = sorted(
            ((k, (date.fromisoformat(rows[-1]["date"]) - date.fromisoformat(d)).days)
             for k, d in first_seen.items() if k in rows[-1].get("blockers", [])),
            key=lambda x: -x[1])
        # The unit is **snapshot count**, not calendar days. Days with no snapshot are not counted.
        span = f"{rows[0]['date']} ~ {rows[-1]['date']}"
        print(f"[{p['name']}]  {len(rows)} snapshots ({span})")
        if stale:
            print(f"  in progress for {args.days}+ consecutive snapshots:")
            for k, n in stale:
                print(f"    - {k}  ({n} in a row)")
        if old and old[0][1] >= args.days:
            print("  long-standing blockers (days since first recorded):")
            for k, n in old[:8]:
                if n >= args.days:
                    print(f"    - {k}  ({n} days)")
        if not stale and not (old and old[0][1] >= args.days):
            print(f"  nothing stuck for {args.days}+")


def cmd_variance(args, cfg):
    """Estimate vs actual: business days between an item first starting and finishing.

    **Only items seen unfinished before they closed are measured.** An item already
    complete in the first record was finished before tracking began, so its duration is
    unknown; scoring it as one day would drag the multiplier toward zero and turn the
    advice upside down.
    """
    for p, _ in _each(args, cfg):
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
        print(f"[{p['name']}] estimate vs actual (business days; assumes one item at a time)")
        ratios = []
        for k, (ai, wd) in results.items():
            ratio = wd / ai if ai else 0
            ratios.append(ratio)
            print(f"  {k:44} est AI {ai:5} -> actual {wd}d  x{ratio:.1f}")
        avg = sum(ratios) / len(ratios)
        print(f"  mean multiplier x{avg:.2f} ({len(results)} measurement(s))"
              f" — multiply estimates by this to land nearer reality"
              f"{' (estimates were optimistic)' if avg > 1.2 else ''}")


def cmd_burndown(args, cfg):
    bars = " ▁▂▃▄▅▆▇█"
    for p, _ in _each(args, cfg):
        rows = [r for r in read_stats() if r["project"] == p["name"]]
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
              f"burned {round(vals[0] - vals[-1], 2)}")
        burn = (vals[0] - vals[-1]) / max(1, len(rows) - 1)
        if burn > 0:
            print(f"  {round(burn, 3)} AI-days/day -> the remaining {vals[-1]} is about "
                  f"{int(vals[-1] / burn)} days (plain division, not business days)")
        else:
            print("  nothing burned in this window, so no runway can be computed")


def cmd_note(args, cfg):
    """Insert a note at the top of the ledger's notes section, under today's date."""
    projs = projects_in_scope(cfg, "current", args.project)
    if not projs:
        die("not inside a registered project. Pass `--project <name>`")
    p = projs[0]
    path = Path(p["ledger"])
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
        # Only the ones nobody has answered are worth nagging about. Counting the settled
        # `unknown` ones alongside them turns the hint into a permanent line of noise.
        unasked = sum(1 for b in rows if b["since"] is None)
        print(f"[{p['name']}] {len(rows)} blocked")
        for b in rows:
            if b["days"] is not None:
                age = f'{b["days"]}d'
            else:
                age = "?" if b["since"] == "unknown" else "—"
            print(f"  {age:>5}  {clip_to(b['shown'], card_width()[0] - 9)}")
        if unasked:
            print(f"  {unasked} with no start recorded. Add `[since YYYY-MM-DD]`, "
                  f"or `[since unknown]` when it cannot be found")


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
            print("    none - by item text these can run in parallel")


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
                hit = next((k for k in keys if m in k or k.endswith(m)), None)
                if hit:
                    state = Ledger.state(keys[hit])
                    flag = "already closed" if state == S.DONE else "still unchecked"
                    print(f"    {m} → {hit}  [{flag}]")
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
        if S.blocker_hit(item["text"]):
            print("  blocked   the item text marks itself as waiting")

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
            log = _sh(["git", "log", "--all", f"--since={on} 00:00",
                       f"--until={on} 23:59", "--format=%h %s"], w)
            files = _sh(["git", "log", "--all", f"--since={on} 00:00",
                         f"--until={on} 23:59", "--name-only", "--format="], w)
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
    sp = scoped(add("rank", cmd_rank, help="today ranked against your own past"))
    sp.add_argument("--date")
    sp.add_argument("--window", type=int, default=14)
    sp = scoped(add("carryover", cmd_carryover, help="carried-over items and aged blockers"))
    sp.add_argument("--days", type=int, default=3,
                    help="threshold in consecutive recorded days, not calendar days")
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

    args = ap.parse_args()
    args.fn(args, load_config())


if __name__ == "__main__":
    main()
