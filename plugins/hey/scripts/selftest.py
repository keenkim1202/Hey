#!/usr/bin/env python3
"""Self-test — run every hey command against a throwaway fixture.

Touches nothing real: HEY_HOME and the project both live in a temp directory, and the
transcript directory is pointed at an empty path so token counting has nothing to read.

    python3 scripts/selftest.py
    python3 scripts/selftest.py --lang ko
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
LEDGER = """# fixture ledger

**Progress (boxes): 0/0 (0%)**

> Last synced: 2026-01-01 · main `0000000` · no open PRs

## Notes

## PR log

| PR | Title | Opened | Merged | Checklist impact |
|---|---|---|---|---|

## Work log

### {today}

- seeded fixture entry

### Next up

1. **First item** — start here

## Summary

| Phase | Items | Done | Progress (boxes) | MD | AI |
|---|---|---|---|---|---|

## P0. Foundations (6 MD / AI 1.0)

- [ ] **First item** — touches `Modules/Alpha` — 3 MD / AI 0.4
  - [x] part one
  - [X] part two
  - [ ] part three
- [ ] **Second item** — touches `Scripts/Beta` — 3 MD / AI 0.6
- [ ] **Third item** — depending on the account API — 1 MD / AI 0.2
- [x] **Settled earlier** — finished before recording began — 2 MD / AI 0.5

## Blockers

- [ ] **Server contract** — backend owns this — **needs decision**
"""

# 8 boxes, 3 of them closed. `part two` uses `[X]`, so an implementation that only
# accepts `[x]` drops it from both halves of that count.
BOXES = "3/8 boxes"

WIDTH_PROBE = """
import sys; sys.path.insert(0, {here!r})
import board as b
got = {{s: b._w(s) for s in ('───', '…', '█', '한글', 'abc')}}
want = {{'───': 3, '…': 1, '█': 1, '한글': 4, 'abc': 3}}
assert got == want, got
assert b._w(b.head('proj', '2026-08-05 (Wed)')) == b.WIDTH
"""

BLOCKER_PROBE = """
import sys; sys.path.insert(0, {here!r})
import strings as s
# Substring matching used to fire on `depending` and on `대기업`.
for text in ('Screens depending on the account API', '대기업 제휴', '미정리 코드'):
    assert not s.blocker_hit(text), text
for text in ('server API is pending', '결제 대기 화면', '대기중인 항목', '확인 필요함'):
    assert s.blocker_hit(text), text
"""

STATS_PROBE = """
import json, os
rows = [json.loads(l) for l in
        open(os.path.join(os.environ['HEY_HOME'], 'stats.jsonl')) if l.strip()]
by_date = {{r['date']: r for r in rows}}
first, second = by_date[{yesterday!r}], by_date[{today!r}]
# The first record has nothing to diff against, so it carries no closed-work number.
assert first.get('baseline') is True, first
assert 'earned_ai' not in first, first
assert 'earned_ai' in second, second
# `snapshot` ran after `collect` on the same day; neither may erase the other's fields.
for key in ('code', 'tokens', 'items'):
    assert key in second, (key, sorted(second))
"""


def run(cmd: list, env: dict, cwd: Path) -> tuple:
    p = subprocess.run([sys.executable, *cmd], env=env, cwd=str(cwd),
                       capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en", choices=["en", "ko"])
    ap.add_argument("--keep", action="store_true", help="keep the temp directory")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="hey-selftest-"))
    proj, home, empty = tmp / "proj", tmp / "home", tmp / "no-transcripts"
    origin, side = tmp / "origin.git", tmp / "side-worktree"
    proj.mkdir()
    empty.mkdir()
    today = date.today().isoformat()
    (proj / "TASKS.local.md").write_text(LEDGER.format(today=today))

    env = {**os.environ, "HEY_HOME": str(home), "HEY_LANG": args.lang,
           "HEY_TRANSCRIPTS": str(empty)}
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        env[var] = "selftest"
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        env[var] = "selftest@example.com"

    def git(*cmd, cwd: Path = proj) -> None:
        subprocess.run(["git", *cmd], cwd=str(cwd), env=env,
                       capture_output=True, text=True)

    # The fixture repository defaults to `main` and has a remote, one commit that never
    # reached it, and a linked worktree outside the project root. All three are states
    # the plugin has to handle and none of them used to be exercised here.
    git("init", "-q", "--bare", str(origin), cwd=tmp)
    git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/main")
    (proj / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (proj / ".git" / "info" / "exclude").write_text("TASKS.local.md\n")
    (proj / "seed.txt").write_text("seed\n")
    git("add", "-A")
    git("commit", "-qm", "seed")
    git("remote", "add", "origin", str(origin))
    git("push", "-q", "-u", "origin", "main")
    git("remote", "set-head", "origin", "-a")
    (proj / "unpushed.txt").write_text("never left\n")
    git("add", "-A")
    git("commit", "-qm", "unpushed")
    git("worktree", "add", "-q", str(side), "-b", "side")

    hey, board = str(HERE / "hey.py"), str(HERE / "board.py")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    probes = {
        "stats": STATS_PROBE.format(yesterday=yesterday, today=today),
        "display width": WIDTH_PROBE.format(here=str(HERE)),
        "blocker word boundaries": BLOCKER_PROBE.format(here=str(HERE)),
    }

    # Third entry, when present, is a substring the output must contain. These assertions
    # are all on English mechanical output, so they hold in either language.
    cases = [
        ([hey, "add", str(proj), "--name", "fixture"], "register", "base:   origin/main"),
        ([hey, "projects"], "list projects"),
        ([hey, "resolve"], "resolve cwd"),
        ([hey, "progress", "--phases"], "progress", BOXES),
        ([hey, "note", "a note", "--file", "Modules/Alpha/A.swift:1"], "add note"),
        ([hey, "notes", "--since", "3"], "read notes"),
        ([hey, "log"], "read log"),
        ([hey, "next"], "next up"),
        ([hey, "dirty"], "dirty: base branch detected", "1 commit(s) ahead of origin/main"),
        ([hey, "dirty"], "dirty: linked worktree seen", side.name),
        ([hey, "dirty", "--base", "nope"], "dirty: unresolved base is not silent",
         "were NOT checked"),
        ([hey, "batch"], "loop candidates"),
        ([hey, "context", "--date", today], "context"),
        ([board, "collect", "--date", yesterday], "collect (yesterday)", "baseline"),
        ([board, "collect", "--date", today], "collect (today)"),
        ([hey, "snapshot"], "snapshot"),
        (["-c", probes.pop("stats")], "first record is a baseline"),
        ([hey, "rank"], "rank"),
        ([hey, "carryover", "--days", "1"], "carry-over"),
        ([hey, "variance"], "variance: settled-earlier item excluded",
         "no item has been seen closing yet"),
        ([hey, "burndown"], "burndown"),
        ([board, "show"], "board: closed"),
        ([board, "show", "--metric", "code"], "board: code"),
        ([board, "show", "--metric", "tokens"], "board: tokens"),
        ([board, "streak"], "streak"),
        ([board, "goal", "--set", "5.0"], "set goal"),
        ([board, "goal"], "goal pace"),
        ([board, "brief"], "morning card"),
        ([board, "wrap"], "evening card"),
        ([hey, "scope", "all"], "scope all"),
    ]
    cases += [(["-c", src], label) for label, src in probes.items()]

    failed = []
    for case in cases:
        cmd, label = case[0], case[1]
        want = case[2] if len(case) > 2 else None
        code, out = run(cmd, env, proj)
        ok = code == 0 and (want is None or want in out)
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
        if not ok:
            failed.append((label, out if want is None or code else
                           f"expected to find {want!r} in:\n{out}"))

    # The blocker must be detected in whichever language the ledger uses, and only the
    # one real blocker -- `Third item` says "depending", which must not count.
    code, out = run([hey, "batch"], env, proj)
    if "1 blocked item(s) excluded" not in out:
        failed.append(("blocker detection", out))
        print("  FAIL blocker detection")
    else:
        print("  ok   blocker detection")

    for label, out in failed:
        print(f"\n--- {label} ---\n{out}")
    if args.keep:
        print(f"\ntemp dir kept: {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(cases) + 1 - len(failed)}/{len(cases) + 1} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
