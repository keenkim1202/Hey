#!/usr/bin/env python3
"""Self-test — static checks, then every hey command against a throwaway fixture.

Touches nothing real: HEY_HOME and the project both live in a temp directory, and the
transcript directory is pointed at an empty path so token counting has nothing to read.

    python3 scripts/selftest.py
    python3 scripts/selftest.py --lang ko
"""

from __future__ import annotations

import argparse
import json
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
  - [ ] part three `[AI 0.3]` `[branch side]`
- [ ] **Second item** — touches `Scripts/Beta` — 3 MD / AI 0.6 `[branch deleted-long-ago]`
- [ ] **Third item** — depending on the account API — 1 MD / AI 0.2
- [x] **Settled earlier** — finished before recording began — 2 MD / AI 0.5
- [x] **Groundwork** — done long ago, deliberately never estimated

## Blockers

- [ ] **Server contract** — backend owns this — **needs decision** `[since 2020-01-01]`
- [ ] **Legacy quirk** — waiting on someone who left `[since unknown]`
- [ ] **Fresh doubt** — pending, nobody has dated it
- [ ] **Mistyped date** — blocked on a date that does not exist `[since 2020-13-45]`
- [ ] **Not yet** — blocked from a day that has not arrived `[since 2099-01-01]`
"""

# 13 boxes across 10 items, 4 of them closed: five item lines carry subitems or stand
# alone, and the four blockers are one box each. `part two` uses `[X]`, so an
# implementation that only accepts `[x]` drops it from both halves of that count.
BOXES = "4/13 boxes"

WIDTH_PROBE = """
import sys, unicodedata; sys.path.insert(0, {here!r})
import board as b, strings as s
got = {{x: b._w(x) for x in ('───', '…', '█', '한글', 'abc')}}
want = {{'───': 3, '…': 1, '█': 1, '한글': 4, 'abc': 3}}
assert got == want, got
assert b._w(b.head('proj', '2026-08-05 (Wed)')) == b.WIDTH

# Section markers must be one codepoint wide-by-declaration. A variation selector makes a
# glyph measure narrow and draw wide, which silently shifts every aligned row under it.
for name, mark in s.MARK.items():
    assert len(mark) == 1, (name, mark, 'more than one codepoint')
    eaw = unicodedata.east_asian_width(mark)
    assert eaw == 'W', (name, mark, eaw)
    assert b._w(mark) == 2, (name, mark, b._w(mark))

# Folding must never hand back a line wider than the card.
long_ko = '다국어 파이프라인 완성해 머지했고 ' * 6
for limit in (1, 2, 3):
    for line in b.fold(long_ko, '   · ', '     ', limit=limit):
        assert b._w(line) <= b.WIDTH, (limit, b._w(line), line)
    assert len(b.fold(long_ko, '   · ', '     ', limit=limit)) <= limit
# A token with no space to break on still has to fit.
for line in b.fold('x' * 200, '   · ', '     '):
    assert b._w(line) <= b.WIDTH, (b._w(line), line)

# A run of symbols joined by `/` or `·` carries no space, so it has to break at those
# separators. Two names long enough to force the break inside the second one: an even
# backtick count per line is what says the break landed between names, not through one.
BT = chr(96)
run = BT + 'A' * 38 + BT + '/' + BT + 'B' * 38 + BT
folded = b.fold(run, '   ', '      ', limit=3)
assert all(line.count(BT) % 2 == 0 for line in folded), folded
assert any('A' * 38 in line for line in folded), folded
assert any('B' * 38 in line for line in folded), folded
"""

CARD_WIDTH_PROBE = """
import os, sys; sys.path.insert(0, {here!r})
import hey

def w(val):
    os.environ.pop('HEY_WIDTH', None) if val is None else os.environ.update(HEY_WIDTH=val)
    return hey.card_width()

# This probe runs on a pipe, so there is no terminal to measure and the default stands.
# Anything that is not a plain number has to fall back rather than raise or read as zero.
assert not sys.stdout.isatty()
for junk in (None, '', '   ', 'wide', '-10', '9.5', '1e2'):
    assert w(junk) == (hey.CARD_W, 'default'), (junk, w(junk))

assert w('96') == (96, 'HEY_WIDTH'), w('96')
assert w(' 96 ') == (96, 'HEY_WIDTH'), w(' 96 ')
assert w(str(hey.CARD_MIN)) == (hey.CARD_MIN, 'HEY_WIDTH')
assert w(str(hey.CARD_MAX)) == (hey.CARD_MAX, 'HEY_WIDTH')

# Out of range is clamped, and the source says so instead of reporting the value as asked
# for -- `doctor` prints this, and a silent clamp there reads as the setting being honoured.
assert w('10') == (hey.CARD_MIN, 'HEY_WIDTH=10, clamped'), w('10')
assert w('999') == (hey.CARD_MAX, 'HEY_WIDTH=999, clamped'), w('999')
# `$COLUMNS` reads as 0 in a shell with no tty, so 0 is what gets passed through by anyone
# who trusts it. It is a digit, so it clamps rather than falling back -- and has to say so.
assert w('0') == (hey.CARD_MIN, 'HEY_WIDTH=0, clamped'), w('0')

# The card has to lay out at whatever the resolver returns, at both ends of the range.
# `WIDTH` binds at import, so the module is reloaded per width rather than reassigned.
for val in (str(hey.CARD_MIN), '96', str(hey.CARD_MAX)):
    os.environ['HEY_WIDTH'] = val
    sys.modules.pop('board', None)
    import board as b
    assert b.WIDTH == int(val), (val, b.WIDTH)
    assert b._w(b.head('proj', '2026-08-05 (Wed)')) == int(val), (val, b.WIDTH)
    # The progress rows are why the floor is 72: labels alone take a fixed 51 columns.
    assert b.WIDTH - 60 >= 12, (val, b.WIDTH)

# Reading the session's pty is allowed to come up empty -- a CI runner has no tty in its
# ancestry -- but never to raise, and never to answer with something unusable.
cols = hey.terminal_columns()
assert cols is None or (isinstance(cols, int) and cols > 0), cols

# `doctor` offers a wider card only when one is reachable. At the ceiling, or on a terminal
# no wider than the card already is, there is nothing to act on and it must stay quiet --
# a warning the user cannot clear is noise that trains them to ignore the rest. This calls
# the real decision rather than restating it, or a broken ceiling would still pass here.
w = hey.wider_card_available
assert w(78, 154) == hey.CARD_MAX, w(78, 154)   # capped at the ceiling, not 152
assert w(78, 100) == 98, w(78, 100)
assert w(hey.CARD_MAX, 154) is None, 'at the ceiling there is nothing to suggest'
assert w(78, 80) is None, 'a standard terminal already fits the default'
assert w(hey.CARD_MIN, 72) is None, 'a terminal narrower than the floor cannot help'
assert w(78, None) is None, 'no reading means no suggestion'
assert w(78, 0) is None, 'a zero reading is not a suggestion'
"""

SHARE_PROBE = """
import sys; sys.path.insert(0, {here!r})
from datetime import date
from hey import Ledger, load_config, earned_ai

led = Ledger(load_config()['projects'][0])
by = {{i['title']: i for i in led.items}}

# `First item` is AI 0.4 over 4 boxes, two of them already closed. `part three` claims 0.3.
# The closed boxes keep their plain even 0.1 -- nothing written now may change what a box
# already banked -- and the one open unclaimed box gets whatever is left, which is nothing.
first = by['First item']
assert Ledger.boxes(first) == (2, 4), Ledger.boxes(first)
shares = [round(x, 4) for x in Ledger.box_ai(first)]
assert shares == [0.0, 0.1, 0.1, 0.3], shares
assert Ledger.earned(first) == 0.2, Ledger.earned(first)
# The shares now total 0.5 against an estimate of 0.4, and that is the finding: the item
# was under-estimated by 0.1. Rescaling to hide it is what would move a closed box.
assert Ledger.overclaimed(first) == 0.1, Ledger.overclaimed(first)

# The property the whole design turns on: annotating an item must not restate what it has
# already earned. Same item, same closed boxes, claim added to the open one.
plain = {{'ai': 1.0, 'done': False, 'kids': [True] * 8 + [False], 'kid_ai': [None] * 9}}
claimed = dict(plain, kid_ai=[None] * 8 + [0.3])
assert Ledger.earned(plain) == Ledger.earned(claimed), (Ledger.earned(plain),
                                                        Ledger.earned(claimed))
# And closing the claimed box is then worth exactly what it claimed.
after = dict(claimed, kids=[True] * 9)
assert round(Ledger.earned(after) - Ledger.earned(claimed), 4) == 0.3

# An item with no claims anywhere splits evenly, which is what keeps every ledger written
# before shares existed scoring exactly as it did.
second = by['Second item']
assert Ledger.box_ai(second) == [0.6], Ledger.box_ai(second)
assert Ledger.earned(second) == 0.0, Ledger.earned(second)
assert Ledger.overclaimed(second) == 0.0

# Claims beyond the item's own estimate must not turn the leftover share negative -- that
# would have unclosed boxes subtracting from the day. The boxes that claimed nothing score
# nothing, `doctor` reports the excess, and the arithmetic stays traceable to the file.
over = {{'ai': 1.0, 'done': False, 'kids': [False, True], 'kid_ai': [0.6, 0.7]}}
assert Ledger.box_ai(over) == [0.0, 0.6, 0.7], Ledger.box_ai(over)
assert Ledger.overclaimed(over) == 0.3, Ledger.overclaimed(over)
assert Ledger.earned(over) == 0.7, Ledger.earned(over)

# Diffing banked totals is what makes a weighted box score its own worth. Closing only
# `part three` earns 0.3, where the old count-based split would have called it 0.1.
def snap(earned):
    return {{'items': [{{'k': 'P0|First item', 'ai': 0.4, 'closed': 2, 'boxes': 4,
                        'earned': earned}}]}}
assert earned_ai(snap(0.2), snap(0.5)) == 0.3, earned_ai(snap(0.2), snap(0.5))
# Records written before shares existed have no `earned`, and must still be readable.
old = {{'items': [{{'k': 'P0|First item', 'ai': 0.4, 'closed': 1, 'boxes': 4}}]}}
new = {{'items': [{{'k': 'P0|First item', 'ai': 0.4, 'closed': 2, 'boxes': 4}}]}}
assert earned_ai(old, new) == 0.1, earned_ai(old, new)

# `unknown` is a recorded answer, not a missing one: no age, but nothing left to ask.
by_t = {{x['title']: x for x in led.blockers('2020-01-11')}}
assert by_t['Legacy quirk']['since'] == 'unknown', by_t['Legacy quirk']
assert by_t['Legacy quirk']['days'] is None
# Nothing written at all stays distinguishable from it, which is what the hint counts.
assert by_t['Fresh doubt']['since'] is None, by_t['Fresh doubt']
assert by_t['Fresh doubt']['days'] is None

# A blocker's age comes off the line, so it works on a machine with no history at all.
b = {{x['title']: x for x in led.blockers('2020-01-11')}}['Server contract']
assert b['since'] == '2020-01-01', b
assert b['days'] == 10, b
# A date in the future is not an age. Reporting a negative wait would be worse than none.
assert {{x['title']: x for x in led.blockers('2019-01-01')}}['Server contract']['days'] is None

# `[since 2020-13-45]` matches the marker's shape and then fails to parse. That used to read
# as "no age" while the line looked answered, so nothing anywhere would ever mention it --
# and it also fell out of the hint that chases undated blockers. It is now its own answer.
by_t = {{x['title']: x for x in led.blockers('2020-01-11')}}
assert by_t['Mistyped date']['bad_since'] is True, by_t['Mistyped date']
assert by_t['Mistyped date']['days'] is None, by_t['Mistyped date']
# And the well-formed ones must not be swept up with it -- including `unknown`, which is a
# recorded answer, and the undated one, which is a question nobody has asked yet.
for t in ('Server contract', 'Legacy quirk', 'Fresh doubt'):
    assert by_t[t]['bad_since'] is False, (t, by_t[t])
"""

TITLE_CLIP_PROBE = """
import sys; sys.path.insert(0, {here!r})
from hey import Ledger, clip_to, display_width as dw

t = Ledger._title
# Markers are metadata and the name is half the key, so annotating an item must not rename
# it. This is the invariant that makes `[AI n]`, `[since]` and `[branch]` safe to add to a
# ledger that already has history.
for marker in ('`[AI 0.3]`', '`[since 2020-01-01]`', '`[since unknown]`',
               '`[branch feat/x]`'):
    for line in ('**Item** — a description — 3 MD / AI 0.4',
                 '**Item** (a list, of things)',
                 'Plain item with no emphasis'):
        assert t(line + ' ' + marker) == t(line), (marker, line, t(line + ' ' + marker))
        assert t(marker + ' ' + line) == t(line), (marker, line)
# A trailing parenthetical is a list of what the item covers, and dropping it is what turns
# a line into a name.
assert t('**Scaffold** (Alpha, Beta, Gamma)') == 'Scaffold'
assert t('**Scaffold** — notes (Alpha)') == 'Scaffold'
# But when the bracket opens early in a sentence that carries on, cutting there keeps a
# fragment and throws the sentence away. Two-to-one is the line: past it the head is not a
# title, it is the first couple of words of one.
long_tail = 'media-bff (the third backend) exists or not, and whether OpenAPI exposes it'
assert t(long_tail) == long_tail, t(long_tail)
# Just under the ratio still cuts, so the rule does not quietly swallow the common case.
assert t('Scaffolding here (x) short') == 'Scaffolding here', t('Scaffolding here (x) short')

# Clipping ends on a word when one is close, and never returns more than it was given.
cut = clip_to('alpha bravo charlie delta', 18)
assert dw(cut) <= 18, (dw(cut), cut)
assert cut == 'alpha bravo…', cut
# A single unbroken token has no space to back off to, so it keeps the hard cut rather
# than collapsing to nothing.
hard = clip_to('x' * 40, 12)
assert dw(hard) <= 12 and hard.startswith('xxx'), hard
# A space too far back to be worth reaching for is left alone: backing off to it would
# throw away most of the line to gain a word boundary.
far = clip_to('ab ' + 'x' * 40, 30)
assert far.count('x') > 20, far
# Text that fits is returned untouched, ellipsis included.
assert clip_to('short', 40) == 'short'
"""

SPLIT_PROBE = """
import os, sys; sys.path.insert(0, {here!r})
from pathlib import Path
from hey import Ledger

NL = chr(10)
tmp = Path(os.environ['HEY_HOME']) / 'split'
tmp.mkdir(exist_ok=True)
main, comp = tmp / 'TASKS.local.md', tmp / 'TASKS.log.local.md'
# The checklist half keeps the boxes; the append-only half keeps the prose.
main.write_text(NL.join(['## P0. Phase (1 MD / AI 0.5)', '',
                         '- [ ] **Only item** -- 1 MD / AI 0.5', '']))
comp.write_text(NL.join(['## Work log', '', '### 2026-08-05 (Wed)', '', '- did a thing', '',
                         '## Notes', '', '- a note', '']))

led = Ledger({{'name': 'x', 'ledger': str(main), 'ledger_log': str(comp)}})
# Boxes come from the primary file only, so a split cannot double-count progress.
assert len(led.items) == 1, led.items
assert Ledger.boxes(led.items[0]) == (0, 1), Ledger.boxes(led.items[0])
# Prose sections are found in the companion.
assert led.has_section('log'), 'work log not found across the halves'
assert [d for d, _ in led.log_days()] == ['2026-08-05'], led.log_days()
assert any('a note' in x for x in led.section_body('notes')), led.section_body('notes')

# Without the second path nothing changes, which is what keeps every existing ledger safe.
plain = Ledger({{'name': 'x', 'ledger': str(main)}})
assert not plain.has_section('log')
assert plain.log_days() == []
assert len(plain.items) == 1

# A configured path that is not there reads as empty rather than raising.
gone = Ledger({{'name': 'x', 'ledger': str(main), 'ledger_log': str(tmp / 'nope.md')}})
assert gone.log_path is None and gone.log_days() == []
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
# A day that earned something is not the baseline. `merge_stats` keeps whatever the row
# already held, so the flag has to be actively cleared or the row claims to be both.
assert 'baseline' not in second, second

# The flag is cleared at the source too, which is what protects a history written before
# that was enforced: a row already marked baseline must lose the mark once it earns.
import sys as _s; _s.path.insert(0, {here!r})
from hey import Ledger, load_config, record_progress, today_str
snap = record_progress(Ledger(load_config()['projects'][0]), today_str())
assert 'earned_ai' in snap, sorted(snap)
assert snap.get('baseline', 'MISSING') is None, snap.get('baseline', 'MISSING')
# `snapshot` ran after `collect` on the same day; neither may erase the other's fields.
for key in ('code', 'tokens', 'items'):
    assert key in second, (key, sorted(second))
"""


def run(cmd: list, env: dict, cwd: Path) -> tuple:
    """Run one command to completion with no input.

    `stdin=DEVNULL` is not optional: the session-start hook reads a JSON payload from
    stdin, so an inherited stdin that nobody closes leaves it blocking forever. Passing
    the terminal through happens to work when stdin is already at EOF, which is how that
    hangs only outside an interactive shell.
    """
    p = subprocess.run([sys.executable, *cmd], env=env, cwd=str(cwd),
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def _frontmatter(path: Path) -> dict | None:
    """The YAML frontmatter of a skill, parsed just enough to check the two keys."""
    text = path.read_text()
    if not text.startswith("---\n"):
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    meta = {}
    for ln in parts[1].splitlines():
        if ":" in ln and not ln.startswith((" ", "\t", "-")):
            key, value = ln.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta


def static_checks() -> list:
    """Manifest and frontmatter checks. No fixture, no subprocess, no network.

    The component-name check is here because two components claiming one name is not a
    syntax error anywhere: the manifest validates, the plugin loads, and one of them
    silently shadows the other.
    """
    plugin = HERE.parent
    out = []

    docs = sorted((plugin / "skills").glob("*/SKILL.md"))
    if (plugin / "SKILL.md").exists():
        docs.append(plugin / "SKILL.md")

    names: dict[str, list] = {}
    for doc in docs:
        rel = doc.relative_to(plugin)
        meta = _frontmatter(doc)
        if meta is None:
            out.append(("skill frontmatter", f"{rel} has no frontmatter block"))
            continue
        for key in ("name", "description"):
            if not meta.get(key):
                out.append(("skill frontmatter", f"{rel} declares no `{key}`"))
        if meta.get("name"):
            names.setdefault(meta["name"], []).append(str(rel))
    for cmd in sorted((plugin / "commands").glob("*.md")):
        names.setdefault(cmd.stem, []).append(str(cmd.relative_to(plugin)))
    for name, claimed_by in sorted(names.items()):
        if len(claimed_by) > 1:
            out.append(("component names",
                        f"`{name}` is claimed by {' and '.join(claimed_by)}"))

    manifest = plugin / ".claude-plugin" / "plugin.json"
    try:
        if not json.loads(manifest.read_text()).get("name"):
            out.append(("plugin manifest", "declares no `name`"))
    except (OSError, ValueError) as exc:
        out.append(("plugin manifest", f"{manifest}: {exc}"))

    # Absent from an installed copy, which ships the plugin directory on its own.
    market = plugin.parent.parent / ".claude-plugin" / "marketplace.json"
    if market.exists():
        try:
            data = json.loads(market.read_text())
            for entry in data.get("plugins", []):
                source = entry.get("source")
                if isinstance(source, str) and source.startswith("./"):
                    if not (market.parent.parent / source).is_dir():
                        out.append(("marketplace", f"source does not exist: {source}"))
        except ValueError as exc:
            out.append(("marketplace", f"{market}: {exc}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en", choices=["en", "ko"])
    ap.add_argument("--keep", action="store_true", help="keep the temp directory")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="hey-selftest-"))
    proj, home, empty = tmp / "proj", tmp / "home", tmp / "no-transcripts"
    origin, side = tmp / "origin.git", tmp / "side-worktree"
    second = tmp / "second-project"
    proj.mkdir()
    empty.mkdir()
    second.mkdir()
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
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()
    probes = {
        "stats": STATS_PROBE.format(yesterday=yesterday, today=today, here=str(HERE)),
        "display width": WIDTH_PROBE.format(here=str(HERE)),
        "card width: env, clamp and fallback": CARD_WIDTH_PROBE.format(here=str(HERE)),
        "subitem shares and blocker age": SHARE_PROBE.format(here=str(HERE)),
        "split ledger: prose in a second file": SPLIT_PROBE.format(here=str(HERE)),
        "titles and clipping": TITLE_CLIP_PROBE.format(here=str(HERE)),
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
        ([hey, "dirty"], "dirty: an upstream makes the count unpushed", "1 commit(s) unpushed"),
        ([hey, "dirty"], "dirty: linked worktree seen", side.name),
        ([hey, "dirty"], "dirty: names the item a loose branch belongs to", "First item"),
        ([hey, "doctor"], "doctor: flags a marker whose branch is gone",
         "name a branch git does not have: deleted-long-ago"),
        ([hey, "dirty", "--base", "nope"], "dirty: unresolved base is not silent",
         "were NOT checked"),
        ([hey, "batch"], "loop candidates"),
        ([hey, "context", "--date", today], "context"),
        ([board, "collect", "--date", yesterday], "collect (yesterday)", "baseline"),
        ([board, "collect", "--date", today], "collect (today)"),
        ([hey, "snapshot"], "snapshot"),
        (["-c", probes.pop("stats")], "first record is a baseline"),
        # Re-collecting a day already behind a recorded one must not restate box state:
        # the ledger holds only today, so it would move the baseline and zero the newer day.
        ([board, "collect", "--date", two_days_ago], "collect: a past day keeps its hands off "
         "box state", "not collected - a later day is already recorded"),
        ([hey, "rank"], "rank"),
        ([hey, "carryover", "--days", "1"], "carry-over"),
        # The blocker is dated 2020 on its own line, and the fixture has two days of
        # history. Reading the age off the records would call it a day or two old; the
        # ledger is what knows it has been sitting for years, and both commands have to
        # agree on that. `from the ledger` is the assertion that the marker won.
        ([hey, "carryover", "--days", "1"], "carry-over: a dated blocker ages from the ledger",
         "days, from the ledger"),
        ([hey, "variance"], "variance: settled-earlier item excluded",
         "no item has been seen closing yet"),
        ([hey, "item", "First item"], "item history", "first seen"),
        ([hey, "item", "P0"], "item: an ambiguous key lists the matches", "matches 5 items"),
        ([hey, "item", "nope"], "item: no match says so", "no item matches"),
        ([hey, "burndown"], "burndown"),
        ([board, "show"], "board: closed"),
        ([board, "show", "--metric", "code"], "board: code"),
        ([board, "show", "--metric", "tokens"], "board: tokens"),
        ([board, "streak"], "streak"),
        ([board, "goal", "--set", "5.0", "--daily", "0.4"], "set goal: per project",
         "weekly 5.0 · daily 0.4"),
        ([board, "goal"], "goal pace"),
        ([board, "streak"], "streak: uses the project's daily goal", "goal of 0.4"),
        ([board, "brief"], "morning card"),
        ([board, "wrap"], "evening card"),
        ([hey, "blockers"], "blockers: lists them all", "5 blocked"),
        ([hey, "blockers"], "blockers: nags only about the unanswered ones",
         "1 with no start recorded"),
        ([hey, "doctor"], "doctor"),
        ([hey, "doctor"], "doctor: flags a `[since]` that is not a real date",
         "are not a real date"),
        ([hey, "scope", "all"], "scope all"),
    ]
    cases += [(["-c", src], label) for label, src in probes.items()]

    failed, total = [], 0

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal total
        total += 1
        print(f"  {'ok  ' if passed else 'FAIL'} {label}")
        if not passed:
            failed.append((label, detail))

    for label, detail in static_checks():
        check(f"static: {label}", False, detail)
    if not failed:
        check("static: manifests and component names", True)

    for case in cases:
        cmd, label = case[0], case[1]
        want = case[2] if len(case) > 2 else None
        code, out = run(cmd, env, proj)
        passed = code == 0 and (want is None or want in out)
        check(label, passed, out if want is None or code else
              f"expected to find {want!r} in:\n{out}")

    # Blockers must be detected in whichever language the ledger uses, and only the real
    # ones -- three sit in the blocker section, while `Third item` says "depending", which
    # is not `pending` and must not count.
    code, out = run([hey, "batch"], env, proj)
    check("blocker detection", "5 blocked item(s) excluded" in out, out)

    # A `[since]` naming a day that has not arrived is a deliberate statement that the wait
    # has not started. The records would happily supply an age -- the item has been sitting
    # in the fixture's snapshots since the first one -- and using it would answer a question
    # the line already answered, with the opposite answer.
    code, out = run([hey, "carryover", "--days", "1"], env, proj)
    check("carry-over: a future `[since]` is not aged from the records",
          "Not yet" not in out, out)

    # The session-start hook is the only always-on component, and silence is its default.
    # With no stdin it falls back to the cwd, which is what these two cases exercise.
    hook = [str(HERE.parent / "hooks-handlers" / "on-session-start.py")]
    hook_env = {**env, "CLAUDE_PLUGIN_ROOT": str(HERE.parent)}
    code, out = run(hook, hook_env, proj)
    check("hook: reports unpushed work", "neither committed nor pushed" in out, out)
    code, out = run(hook, hook_env, tmp)
    check("hook: silent outside a registered project", code == 0 and not out.strip(), out)

    # One project is one repository, so a linked worktree must not register on its own.
    code, out = run([hey, "add", str(side), "--name", "wt"], env, proj)
    check("add: refuses a linked worktree", code != 0 and "linked worktree" in out, out)

    # `--init` puts the template in place; `remove` is the inverse of `add`. Both run last
    # because they change what is registered.
    code, out = run([hey, "add", str(second), "--name", "second", "--init"], env, proj)
    check("add --init: creates the ledger from the template",
          code == 0 and "created from template" in out, out)
    check("add --init: ledger is on disk", (second / "TASKS.local.md").exists(),
          f"{second / 'TASKS.local.md'} was not written")
    code, out = run([hey, "remove", "second"], env, proj)
    check("remove: unregisters and keeps the ledger",
          code == 0 and "unregistered: second" in out, out)
    check("remove: ledger survived", (second / "TASKS.local.md").exists(), "")

    # A squash merge leaves the branch holding commits the base never saw while the content
    # is fully merged. Reproduced by committing on a branch, then squashing that same
    # content onto the base: `dirty` must stop calling it unpushed, and `doctor` must call
    # it deletable.
    git("checkout", "-q", "-b", "squashed")
    (proj / "squashed.txt").write_text("merged by squash\n")
    git("add", "-A")
    git("commit", "-qm", "work on the branch")
    git("checkout", "-q", "main")
    git("merge", "-q", "--squash", "squashed")
    git("commit", "-qm", "squashed onto main (#99)")
    git("push", "-q", "origin", "main")
    git("checkout", "-q", "squashed")
    code, out = run([hey, "dirty"], env, proj)
    # Match the per-worktree phrasing, not the word: the all-clear line is itself
    # "nothing uncommitted or unpushed", which a bare substring test would trip over.
    check("dirty: a squash-merged branch is not unpushed work",
          "commit(s) unpushed" not in out and "never pushed" not in out, out)

    # The bug this replaced: a branch that IS pushed is still ahead of the base, and the
    # card used to file it under work about to be lost -- with a `no PR` label nothing had
    # checked. Pushed-but-unmerged has to read as its own state, and not as unpushed.
    git("checkout", "-q", "-b", "in-review")
    (proj / "reviewed.txt").write_text("pushed, awaiting review\n")
    git("add", "-A")
    git("commit", "-qm", "work awaiting review")
    git("push", "-q", "-u", "origin", "in-review")
    code, out = run([hey, "dirty"], env, proj)
    check("dirty: a pushed branch is not called unpushed",
          "pushed but not in origin/main" in out and "commit(s) unpushed" not in out, out)
    # The card reads its own worktree state, so assert there too -- `dirty` passing does
    # not prove the card stopped calling a pushed branch loose.
    probe = ("import sys; sys.path.insert(0, %r)\n"
             "import board as b\n"
             "from pathlib import Path\n"
             "rows = b._worktree_state(Path(%r), 'main')\n"
             "hit = [r for r in rows if r[1] == 'in-review']\n"
             "assert hit, [r[1] for r in rows]\n"
             "w, br, dirty, gone, has_up = hit[0]\n"
             "assert (gone, has_up) == (0, True), (gone, has_up)\n"
             % (str(HERE), str(proj)))
    code, out = run(["-c", probe], env, proj)
    check("card: a pushed branch counts as zero unpushed", code == 0, out)

    # Put the fixture back where the checks below expect to find it.
    git("checkout", "-q", "squashed")
    code, out = run([hey, "doctor"], env, proj)
    check("doctor: names the squash leftover as deletable",
          "already merged into origin/main" in out, out)
    # `Groundwork` is closed and `Server contract` is a blocker; both are meant to carry no
    # estimate, so neither may be reported as a missing one.
    check("doctor: no estimate warning for closed items or blockers",
          "carry no estimate" not in out, out)
    git("checkout", "-q", "main")

    # A remote's default branch is not always the branch work merges into. Put `develop`
    # well ahead of `main` and work on it: with base still `main`, every report would count
    # commits that were pushed long ago, so `doctor` has to say so. Last, because it
    # rewrites the fixture's branches.
    git("checkout", "-q", "-b", "develop")
    for n in range(11):
        git("commit", "-q", "--allow-empty", "-m", f"develop {n}")
    git("push", "-q", "origin", "develop")
    run([hey, "add", str(proj), "--name", "fixture", "--base", "main"], env, proj)
    code, out = run([hey, "doctor"], env, proj)
    check("doctor: flags a base the working branch has left behind",
          "If `develop` is what work merges into" in out, out)

    for label, detail in failed:
        print(f"\n--- {label} ---\n{detail}")
    if args.keep:
        print(f"\ntemp dir kept: {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{total - len(failed)}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
