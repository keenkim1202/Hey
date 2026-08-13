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
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import strings as S  # noqa: E402
LEDGER = """# fixture ledger

**Progress (boxes): 0/0**

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
- [ ] **Marked elsewhere** — outside the blocker section, said outright `[blocked]` — 1 MD / AI 0.1
- [ ] **Reads as blocked** — waiting on a decision nobody marked — 1 MD / AI 0.1

## Blockers

- [ ] **Server contract** — backend owns this — **needs decision** `[since 2020-01-01]`
- [ ] **Legacy quirk** — waiting on someone who left `[since unknown]`
- [ ] **Fresh doubt** — pending, nobody has dated it
- [ ] **Mistyped date** — blocked on a date that does not exist `[since 2020-13-45]`
- [ ] **Not yet** — blocked from a day that has not arrived `[since 2099-01-01]`
"""

# 15 boxes across 12 items, 4 of them closed. `part two` uses `[X]`, so an implementation
# that only accepts `[x]` drops it from both halves of that count.
BOXES = "4/15 boxes"

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

# Width resolution is now the whole of it: an environment variable, a clamp, a default.
# There is no terminal probing left to test -- see the note on `card_width`.
assert not hasattr(hey, 'terminal_columns'), 'terminal probing came back'
assert not hasattr(hey, 'wider_card_available'), 'the width nag came back'
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

ZERO_NOTE_PROBE = """
import sys; sys.path.insert(0, {here!r})
from board import contradicts_zero

# The note says code went up while the checkboxes did not. It may only appear when that is
# actually what happened, or the same card says "no record -- no log, no commits" on one
# line and "work happened" two lines below.
worked = {{'earned_ai': 0.0, 'code': {{'added': 300, 'deleted': 40}}, 'tokens': {{'out': 900}}}}
assert contradicts_zero(worked) is True, worked

# An idle day that was recorded is a plain zero and needs no commentary.
idle = {{'earned_ai': 0.0, 'code': {{'added': 0, 'deleted': 0}}, 'tokens': {{'out': 0}}}}
assert contradicts_zero(idle) is False, idle
# So is one recorded before code and tokens were collected at all.
assert contradicts_zero({{'earned_ai': 0.0}}) is False

# A day that closed something has nothing to explain.
assert contradicts_zero(dict(worked, earned_ai=0.4)) is False
# A baseline carries no closed figure, which is not the same as closing nothing.
assert contradicts_zero({{'code': {{'added': 300, 'deleted': 40}}}}) is False
assert contradicts_zero(None) is False
"""

ITEM_ID_PROBE = """
import sys; sys.path.insert(0, {here!r})
from hey import Ledger, earned_ai

def item(phase, title, ident=None):
    return {{'phase': phase, 'title': title, 'id': ident, 'ai': 1.0, 'done': False,
            'kids': [True, False], 'kid_ai': [None, None]}}

# Without an id the key is the name, which is what every ledger written so far relies on.
assert Ledger.key(item('P0', 'Fix login')) == 'P0|Fix login'
assert Ledger.legacy_key(item('P0', 'Fix login', 'login')) == 'P0|Fix login'

# With one the name is free, and moving the item to another phase does not move its key.
assert Ledger.key(item('P0', 'Fix login', 'login')) == 'login'
assert Ledger.key(item('P9', 'Renamed entirely', 'login')) == 'login'

# Which is the whole point: a rename is invisible to the recorded history, so the day of
# the rename scores the one box that actually closed.
before = {{'items': [{{'k': 'login', 'ai': 1.0, 'closed': 1, 'boxes': 3, 'earned': 0.333}}]}}
after = {{'items': [{{'k': 'login', 'ai': 1.0, 'closed': 2, 'boxes': 3, 'earned': 0.667}}]}}
assert earned_ai(before, after) == 0.334, earned_ai(before, after)

# Renaming without an id is what it protects against: the old key vanishes, the new one is
# a first sighting, and everything the item had already banked is banked a second time.
renamed = {{'items': [{{'k': 'P0|New wording', 'ai': 1.0, 'closed': 2, 'boxes': 3,
                       'earned': 0.667}}]}}
was = {{'items': [{{'k': 'P0|Old wording', 'ai': 1.0, 'closed': 1, 'boxes': 3,
                   'earned': 0.333}}]}}
assert earned_ai(was, renamed) == 0.667, earned_ai(was, renamed)

# Two items in one phase sharing a title claim one key, and a dict keyed on it keeps one.
# That is the collision `doctor` reports as a failure.
clash = [item('P0', 'Fix login'), item('P0', 'Fix login')]
assert len({{Ledger.key(i) for i in clash}}) == 1
# An id on either one separates them.
assert len({{Ledger.key(i) for i in [item('P0', 'Fix login', 'a'), item('P0', 'Fix login')]}}) == 2
"""

CARD_FIT_PROBE = """
import os, sys; sys.path.insert(0, {here!r})
import hey
from hey import load_config, today_str

# Nothing checked that a rendered card fits the card. `head` and `fold` were held to the
# width individually, but every other row is assembled by hand from padded columns, and one
# that overruns pushes the aligned rows under it out of true -- silently, and only in the
# language whose labels happen to be wider.
cfg = load_config()
p = [x for x in cfg['projects'] if x['name'] == 'fixture'][0]

# Checked at the floor as well as the default. The floor is the width the rows were sized
# against, and a column that only just fits at 78 has nowhere to go at 72. `WIDTH` binds at
# import, so the module is reloaded per width rather than reassigned.
for want in (str(hey.CARD_MIN), str(hey.CARD_W)):
    os.environ['HEY_WIDTH'] = want
    sys.modules.pop('board', None)
    import board as b
    assert b.WIDTH == int(want), (want, b.WIDTH)

    seen = 0
    for mode in ('brief', 'wrap'):
        for line in b.card(p, cfg, today_str(), mode):
            seen += 1
            assert b._w(line) <= b.WIDTH, (want, mode, b._w(line), b.WIDTH, line)
    # A card that rendered almost nothing would pass the loop above without testing much.
    assert seen > 20, (want, seen)
"""

LATE_TICK_PROBE = """
import sys; sys.path.insert(0, {here!r})
import os, tempfile
from pathlib import Path
import hey, board

# `/seeya` used to stop halfway and ask the user to go run `/hey-sync` first, on the
# grounds that a box ticked after `collect` "does not backfill into" the day. It does.
# `collect` recomputes today against the previous *record*, so a re-run picks it up -- and
# the day the claim was written into the skill, nothing tested it.
d = Path(tempfile.mkdtemp())
led = d / 'TASKS.local.md'
proj = {{'ledger': str(led), 'root': str(d), 'name': 't'}}

def write(a, b):
    led.write_text('## P0. Phase (2 MD / AI 2.0)\\n\\n'
                   f'- [{{a}}] **One** `[id one]` - x - 1 MD / AI 1.0\\n'
                   f'- [{{b}}] **Two** `[id two]` - y - 1 MD / AI 1.0\\n', encoding='utf-8')

def closed(on):
    snap = hey.record_progress(hey.Ledger(proj), on)
    hey.merge_stats(on, 't', snap)
    return snap.get('earned_ai')

os.environ['HEY_HOME'] = str(d / 'home')
hey.HOME = d / 'home'
hey.STATS = hey.HOME / 'stats.jsonl'

write(' ', ' ')
closed('2026-08-09')                      # baseline, no closed figure
assert closed('2026-08-10') == 0.0
write('x', ' ')
assert closed('2026-08-10') == 1.0, 'a late tick did not reach the day it was ticked on'
write('x', 'x')
assert closed('2026-08-10') == 2.0
# And the real constraint still holds: an earlier day cannot be restated.
assert hey.records_after('t', '2026-08-09'), 'the backdating guard lost its input'
"""

FENCE_PROBE = """
import sys; sys.path.insert(0, {here!r})
import tempfile
from pathlib import Path
from hey import Ledger

d = Path(tempfile.mkdtemp())
p = d / 'TASKS.local.md'
# This tool teaches the checklist syntax, so quoting it back inside the ledger is the
# natural thing to do -- and the quoted row used to be counted as work. One example took
# a 1.0 AI-day ledger to 3.0, with nothing on screen to account for the other 2.0.
p.write_text('## Notes\\n\\n'
             '```markdown\\n'
             '- [ ] **Example item** - how to write one - 5 MD / AI 2.0\\n'
             '  - [ ] a subitem\\n'
             '```\\n\\n'
             '## P0. Real (1 MD / AI 1.0)\\n\\n'
             '- [ ] **Real item** `[id real]` - the only real one - 1 MD / AI 1.0\\n'
             '  - [x] a real subitem\\n', encoding='utf-8')
led = Ledger({{'ledger': str(p), 'root': str(d), 'name': 't'}})
titles = [i['title'] for i in led.items]
assert titles == ['Real item'], titles
g = led.progress()
assert g['total_ai'] == 1.0, g['total_ai']
assert g['cb_total'] == 2, g['cb_total']
"""

ATOMIC_WRITE_PROBE = """
import sys; sys.path.insert(0, {here!r})
import tempfile
from pathlib import Path
from unittest import mock
import hey

d = Path(tempfile.mkdtemp())
target = d / 'TASKS.local.md'
target.write_text('the only copy', encoding='utf-8')

# The ledger is never committed, so a truncated one is gone for good. An interrupted write
# has to leave the previous contents exactly where they were.
with mock.patch.object(Path, 'replace', side_effect=KeyboardInterrupt):
    try:
        hey.write_atomic(target, 'half of a new file')
    except KeyboardInterrupt:
        pass
assert target.read_text(encoding='utf-8') == 'the only copy', target.read_text()
# And the temporary must not be left sitting beside it.
assert not list(d.glob('*.tmp')), [str(x) for x in d.glob('*.tmp')]

hey.write_atomic(target, 'new contents')
assert target.read_text(encoding='utf-8') == 'new contents'
assert not list(d.glob('*.tmp'))

# Two writers must not share one temporary path -- with a fixed one, both write, the first
# renames, and the second renames a path that is no longer there. Captured from the call
# rather than asserted on the docstring: the name is the behaviour.
import os
seen = []
real = Path.replace
with mock.patch.object(Path, 'replace', autospec=True,
                       side_effect=lambda self, t: (seen.append(self.name), real(self, t))[1]):
    hey.write_atomic(target, 'third')
assert seen and str(os.getpid()) in seen[0], seen
assert target.read_text(encoding='utf-8') == 'third'
"""

TOKEN_COST_PROBE = """
import sys; sys.path.insert(0, {here!r})
from board import token_cost, total_tokens

row = {{'tokens': {{'in': 1_000_000, 'out': 1_000_000,
                   'cache_read': 100_000_000, 'cache_write': 1_000_000}}}}
# No rates configured is not a cost of zero. A cost line nobody supplied the numbers for
# is the same failure as a multiplier nobody measured.
assert token_cost(row, {{}}) is None
assert token_cost(row, {{'token_cost': {{}}}}) is None

rates = {{'token_cost': {{'in': 3.0, 'out': 15.0, 'cache_read': 0.3, 'cache_write': 3.75}}}}
got = token_cost(row, rates)
assert abs(got - (3 + 15 + 30 + 3.75)) < 1e-9, got
# The displayed token figure drops cache reads, and cost must not: here they are 100 of
# the 103 million, and thirty of the fifty-two dollars. Leaving them out understates the
# bill by most of it, which is the opposite mistake from the one the display avoids.
assert total_tokens(row) == 3_000_000, total_tokens(row)
assert got > 4 * (3 + 15 + 3.75) / 4, got

# A partial table prices what it names and ignores the rest, rather than charging zero.
part = token_cost(row, {{'token_cost': {{'out': 15.0}}}})
assert abs(part - 15.0) < 1e-9, part
"""

COMMIT_SPAN_PROBE = """
import sys; sys.path.insert(0, {here!r})
from datetime import date
from pathlib import Path
from hey import commit_span

proj = Path({proj!r})
# The fixture commits several times while it is being built, so today has a span.
sp = commit_span(proj, date.today().isoformat(), None)
assert sp is not None, 'a day with several commits produced no span'
lo, hi, mins = sp
assert lo <= hi, sp
assert mins >= 0, sp
# One commit cannot span anything, and neither can none. Returning `(t, t, 0)` there would
# read as a day that held zero minutes, which is a different claim from having no measure.
assert commit_span(proj, '2001-01-01', None) is None, 'a day with no commits spanned'
# An author nobody committed under has no commits, so it has no span either -- rather
# than the whole day's span credited to them.
assert commit_span(proj, date.today().isoformat(), 'nobody@example.com') is None
"""

TOKEN_SCOPE_PROBE = """
import json, os, sys; sys.path.insert(0, {here!r})
from datetime import datetime, timezone
from pathlib import Path
import board as b

home = Path(os.environ['HEY_HOME'])
tdir = home / 'transcripts' / 'a-session'
tdir.mkdir(parents=True, exist_ok=True)
# Two projects, one of whose paths is a character-for-character prefix of the other. That
# is not a contrived case: `alpha` and `alpha-ios` is how these get named.
proj, sibling = home / 'alpha', home / 'alpha-ios'
proj.mkdir(exist_ok=True)
sibling.mkdir(exist_ok=True)

stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
day = datetime.now().date().isoformat()
rows = [{{'timestamp': stamp, 'cwd': str(proj),
          'message': {{'usage': {{'output_tokens': 10}}}}}},
        {{'timestamp': stamp, 'cwd': str(sibling),
          'message': {{'usage': {{'output_tokens': 500}}}}}}]
(tdir / 'one.jsonl').write_text(chr(10).join(json.dumps(r) for r in rows) + chr(10))

b.TRANSCRIPTS = home / 'transcripts'
got = b.token_usage({{'root': str(proj)}}, day)
# Matching on a raw string prefix charged the sibling's 500 tokens to this project.
assert got['out'] == 10, got
assert got['turns'] == 1, got
# And the sibling still gets its own, so the fix is a boundary and not a narrowing.
assert b.token_usage({{'root': str(sibling)}}, day)['out'] == 500

# A path the glob yields but the stat cannot resolve must not take the command down. Every
# live session writes into this directory while `collect` reads it, so a file rotated away
# in between is ordinary -- and `f.open` was already guarded against exactly this, one line
# further on. A dangling symlink reproduces it without racing anything: `glob` lists it by
# name and `stat` then raises `FileNotFoundError`.
(tdir / 'dangling.jsonl').symlink_to(home / 'never-existed.jsonl')
assert b.token_usage({{'root': str(proj)}}, day)['out'] == 10
"""

ADD_PROBE = """
import argparse, contextlib, io, os, subprocess, sys, tempfile
from pathlib import Path

d = Path(tempfile.mkdtemp()).resolve()
# Its own home, set before the import that reads it. `add` writes the config, and a probe
# that wrote into the shared fixture would register projects the cases after it can see.
os.environ['HEY_HOME'] = str(d / 'home')
sys.path.insert(0, {here!r})
import hey


def add(root, **kw):
    args = argparse.Namespace(root=str(root), ledger=None, ledger_log=None, name=None,
                              base=None, init=False)
    for k, v in kw.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        hey.cmd_add(args, hey.load_config())
    return buf.getvalue()


# A project whose code lives one level down. Registering the directory above it is the
# ordinary mistake, and the two lines that used to print here were both about a git that is
# not there: name a base branch nothing would read, edit a `.git` that does not exist.
outer = d / 'outer'
(outer / 'Sources').mkdir(parents=True)
subprocess.run(['git', 'init', '-q', '-b', 'main', '.'], cwd=str(outer / 'Sources'),
               check=True, capture_output=True)
(outer / 'TASKS.local.md').write_text('# ledger' + chr(10), encoding='utf-8')

out = add(outer, name='outer')
assert 'not a git repository' in out, out
assert 'checklist works as normal' in out, out
assert 'a repository sits below' in out and 'Sources' in out, out
assert 're-add with that path' in out, out
# Named, never taken. Adopting it would file its commits under a project nobody pointed at
# that repository.
assert 'registered: outer' in out, out
assert str(outer / 'Sources') not in hey.load_config()['projects'][0]['root'], out
for forbidden in ('--base', '.git/info/exclude', 'unresolved'):
    assert forbidden not in out, (forbidden, out)

# And the repository itself, which has no remote and never will. The base it reports is the
# branch it actually has, with no `origin/` dressed onto a name nothing verified.
sources = outer / 'Sources'
(sources / 'a.txt').write_text('a')
subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', 'add', '-A'],
               cwd=str(sources), check=True, capture_output=True)
subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'x'],
               cwd=str(sources), check=True, capture_output=True)
out = add(sources, name='src', init=True)
assert 'base:   main  (detected)' in out, out
assert 'origin/' not in out, out
assert '.git/info/exclude' in out, out
"""

NO_REMOTE_PROBE = """
import argparse, contextlib, io, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, {here!r})
import hey

# Resolved, because `git rev-parse` answers with the real path and macOS puts temporary
# directories behind a symlink. Comparing the two forms fails on a machine and passes on a
# machine, which is the kind of test that gets deleted rather than fixed.
d = Path(tempfile.mkdtemp()).resolve()
nogit = d / 'nogit'
nogit.mkdir()
local = d / 'local'
local.mkdir()


def git(*a, cwd=None):
    subprocess.run(['git', *a], cwd=str(cwd or local), check=True, capture_output=True)


git('init', '-q', '-b', 'main', '.')
(local / 'a.txt').write_text('hi')
git('add', '-A')
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'first')
# A real one, so `origin` can be pushed to later. Adding a remote that points at nothing is
# enough to answer "is there a remote", and every check up to here only needs that -- but a
# branch that has actually reached a remote is a different state, and it cannot be faked.
git('init', '-q', '--bare', str(d / 'bare'), cwd=d)

for p in (nogit, local):
    (p / 'TASKS.local.md').write_text('# ledger' + chr(10) + chr(10) + '## P0. Phase (0 MD / AI 0)'
                                      + chr(10) + chr(10) + '- [ ] **One** - 1 MD / AI 0.1' + chr(10),
                                      encoding='utf-8')

assert hey.git_root(nogit) is None, hey.git_root(nogit)
assert hey.git_root(local) == local, hey.git_root(local)
# Asked, and answered. This is what separates "nowhere to push" from "not looked at".
assert hey.has_remote(local) is False
git('remote', 'add', 'origin', str(d / 'bare'))
assert hey.has_remote(local) is True
git('remote', 'remove', 'origin')
assert hey.has_remote(local) is False


def out_of(fn, args, cfg):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            fn(args, cfg)
        except SystemExit:
            pass
    return buf.getvalue()


def cfg_for(root):
    return {{'projects': [{{'name': 'p', 'root': str(root),
                           'ledger': str(root / 'TASKS.local.md')}}], 'scope': 'all'}}


ns = argparse.Namespace(project=None, scope='all', base=None)

# Neither state is a fault, and neither can be cleared by naming a base branch -- so
# neither may demand one. A `doctor` that fails over something with no available fix
# teaches the reader to skip its output.
for root in (nogit, local):
    rep = out_of(hey.cmd_doctor, ns, cfg_for(root))
    assert 'FAIL' not in rep, (root.name, rep)
    assert '--base' not in rep and 'Set "base"' not in rep, (root.name, rep)
assert 'no remote' in out_of(hey.cmd_doctor, ns, cfg_for(local))
assert 'not a git repository' in out_of(hey.cmd_doctor, ns, cfg_for(nogit))

# Nothing to check is not the same as not checked, and the difference is the whole reason
# this repository reports a `gh` that cannot answer instead of reading it as a zero.
dirty_nogit = out_of(hey.cmd_dirty, ns, cfg_for(nogit))
assert 'no commits to check' in dirty_nogit, dirty_nogit
assert 'NOT checked' not in dirty_nogit, dirty_nogit
dirty_local = out_of(hey.cmd_dirty, ns, cfg_for(local))
assert 'nothing here can be pushed' in dirty_local, dirty_local
assert 'NOT checked' not in dirty_local, dirty_local

# And the one case that *is* a misconfiguration keeps its failure and its instruction: a
# remote exists, so a base branch is a real thing to set and setting it really fixes this.
git('remote', 'add', 'origin', str(d / 'bare'))
broken = cfg_for(local)
broken['projects'][0]['base'] = 'nope'
rep = out_of(hey.cmd_doctor, ns, broken)
assert 'FAIL' in rep and 'names no branch here' in rep, rep
assert 'NOT checked' in out_of(hey.cmd_dirty, ns, broken)

# The base is a ref, and `origin/` is one place to look for it. A repository with no remote
# still has a branch work lands on, still accumulates commits that have not reached it, and
# that count is the measure the hardcoded `origin/` prefix made unreachable.
git('remote', 'remove', 'origin')
git('checkout', '-q', '-b', 'feature')
(local / 'b.txt').write_text('more')
git('add', '-A')
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'second')

assert hey.base_ref(local, 'main') == 'main', hey.base_ref(local, 'main')
assert hey.base_ref(local, 'nope') is None
assert hey.default_base(local) == 'main', hey.default_base(local)
ahead, ok_ = hey.ahead_of_base(local, 'main')
assert ok_ and len(ahead) == 1, (ok_, ahead)

live = cfg_for(local)
live['projects'][0]['base'] = 'main'
rep = out_of(hey.cmd_dirty, ns, live)
# Counted, and labelled for what it is. `unpushed` would be every commit in the repository
# and would never go down, so it is not asked here at all.
assert 'not yet in main' in rep, rep
assert 'never pushed' not in rep and 'NOT checked' not in rep, rep
assert 'no remote' in rep, rep
assert 'base main (local)' in out_of(hey.cmd_doctor, ns, live)

# Registering the directory above the repository is an easy miss: a project whose code
# lives in `Sources/` looks like the project from outside. `add` names what it finds and
# stops there -- one project is one repository, and adopting one nobody asked for would
# file its commits under a project that never held them.
(nogit / 'node_modules' / 'pkg').mkdir(parents=True)
(nogit / 'node_modules' / 'pkg' / '.git').mkdir()
(nogit / '.hidden').mkdir()
(nogit / '.hidden' / '.git').mkdir()
assert hey.repos_below(d) == [local], hey.repos_below(d)
# A vendored tree is full of repositories and none of them is the project. Neither is
# anything under a dot-directory.
assert hey.repos_below(nogit) == [], hey.repos_below(nogit)

# A branch nobody named `main`. `default_base` guesses from three names and this is none of
# them, so it finds nothing -- which is a thing to say, not a thing to fail over, and the
# branch the user does have resolves the moment they name it.
odd = d / 'odd'
odd.mkdir()
git('init', '-q', '-b', 'trunk', '.', cwd=odd)
(odd / 'a.txt').write_text('a')
git('add', '-A', cwd=odd)
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'first', cwd=odd)
(odd / 'TASKS.local.md').write_text('# ledger' + chr(10), encoding='utf-8')

assert hey.default_base(odd) is None, hey.default_base(odd)

# Every remote candidate before any local one. Asking per candidate mixed the tiers, so a
# repository integrating on a remote `develop` while keeping a stale local `main` answered
# `main` -- and then counted every report against a branch nobody merges into.
tier = d / 'tier'
tier.mkdir()
git('init', '-q', '-b', 'main', '.', cwd=tier)
(tier / 'a.txt').write_text('a')
git('add', '-A', cwd=tier)
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'first', cwd=tier)
git('init', '-q', '--bare', str(d / 'tier-bare'), cwd=tier)
git('remote', 'add', 'origin', str(d / 'tier-bare'), cwd=tier)
git('checkout', '-q', '-b', 'develop', cwd=tier)
git('push', '-q', '-u', 'origin', 'develop', cwd=tier)
git('checkout', '-q', 'main', cwd=tier)
assert hey.default_base(tier) == 'develop', hey.default_base(tier)
rep = out_of(hey.cmd_doctor, ns, cfg_for(odd))
assert 'FAIL' not in rep, rep
assert 'no local `main`, `develop` or `master`' in rep, rep
named = cfg_for(odd)
named['projects'][0]['base'] = 'trunk'
assert 'base trunk (local)' in out_of(hey.cmd_doctor, ns, named)

# A remote exists, and the base names a branch only this machine has. It resolves to the
# local one: the comparison works, so refusing it would withhold a measure over a prefix.
git('remote', 'add', 'origin', str(d / 'bare'))
git('branch', 'integration', 'main')
side = cfg_for(local)
side['projects'][0]['base'] = 'integration'
rep = out_of(hey.cmd_doctor, ns, side)
assert 'base integration' in rep and 'FAIL' not in rep, rep

# And standing on that base, with everything on it absent from every remote. Resolving the
# base was only half the question: `unpushed` used to derive its answer from `base..HEAD`,
# which is empty on the base itself, so the count came back zero while no remote held a
# single one of those commits. A false all-clear over the one state this tool exists to
# surface, and worse than the "could not check" it replaced -- the earlier test asserted
# the base resolved and never asked what was then reported.
git('checkout', '-q', 'integration')
for n in ('c', 'd'):
    (local / (n + '.txt')).write_text(n)
    git('add', '-A')
    git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'never pushed ' + n)
assert hey.unpushed(local, 'integration')[0] == 3, hey.unpushed(local, 'integration')
rep = out_of(hey.cmd_dirty, ns, side)
assert '3 commit(s) on a branch never pushed' in rep, rep
assert 'nothing uncommitted or unpushed' not in rep, rep
# Being the base branch is not a squash merge -- the trees match because it is the same
# commit, and reading that as "already merged" is what zeroed the count.
assert hey.already_merged(local, 'integration') is False

# An upstream is not proof of a push, and cannot stand in for one. `--track` sets tracking
# configuration on a branch that has never left the machine, so a squash-merged branch of
# that shape looks tracked, is not contained anywhere, and had its rewritten commits
# reported as work at risk -- the exact false alarm the exemption exists to prevent.
# Containment is the axis, not tracking: the base here is a remote ref, so the content is
# somewhere safe and only the commits are gone.
git('checkout', '-q', 'main')
git('push', '-q', '-u', 'origin', 'main')
git('switch', '-q', '-c', 'tracked', '--track', 'origin/main')
(local / 'e.txt').write_text('e')
git('add', '-A')
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'work on a tracked branch')
git('switch', '-q', 'main')
git('merge', '-q', '--squash', 'tracked')
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'squashed onto main')
git('push', '-q', 'origin', 'main')
git('switch', '-q', 'tracked')

assert hey.unpushed(local, 'main')[1] is True, 'the branch has an upstream'
assert hey.base_ref(local, 'main') == 'origin/main', hey.base_ref(local, 'main')
assert hey.already_merged(local, 'main') is True, 'the content is in origin/main'
assert hey.unpushed(local, 'main')[0] == 0, hey.unpushed(local, 'main')

# The mirror image, and the reason the test is containment rather than "the trees match":
# a base that lives only on this machine certifies nothing. Work whose net tree equals a
# local branch is still work no remote has, and exempting it there is the all-clear that
# started this -- so the same shape that is silent against `origin/main` above must not be
# silent against a local `integration`.
git('switch', '-q', 'integration')
git('switch', '-q', '-c', 'sidework')
(local / 'f.txt').write_text('f')
git('add', '-A')
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'add f')
(local / 'f.txt').unlink()
git('add', '-A')
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'revert f')

assert hey.base_ref(local, 'integration') == 'integration', hey.base_ref(local, 'integration')
assert hey.already_merged(local, 'integration') is True, 'the net tree does match'
assert hey.unpushed(local, 'integration')[0] > 0, hey.unpushed(local, 'integration')
git('checkout', '-q', 'feature')

# And none of it may depend on the remote being called `origin`. A repository whose only
# remote is `upstream` used to resolve its base locally, and everything downstream then had
# to guess whether that meant no remote held it -- three attempts at that guess, each
# fixing the last one's blind spot. `base_ref` looks at every remote now, so the base
# resolves to `upstream/main` and the guessing has nothing left to do.
far = d / 'far'
far.mkdir()
git('init', '-q', '-b', 'main', '.', cwd=far)
(far / 'a.txt').write_text('a')
git('add', '-A', cwd=far)
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'first', cwd=far)
git('init', '-q', '--bare', str(d / 'far-bare'), cwd=far)
git('remote', 'add', 'upstream', str(d / 'far-bare'), cwd=far)
git('push', '-q', '-u', 'upstream', 'main', cwd=far)
git('switch', '-q', '-c', 'work', cwd=far)
(far / 'b.txt').write_text('b')
git('add', '-A', cwd=far)
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'work', cwd=far)
git('switch', '-q', 'main', cwd=far)
git('merge', '-q', '--squash', 'work', cwd=far)
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'squashed', cwd=far)
git('push', '-q', 'upstream', 'main', cwd=far)
git('switch', '-q', 'work', cwd=far)

assert hey.remotes(far) == ['upstream'], hey.remotes(far)
assert hey.base_ref(far, 'main') == 'upstream/main', hey.base_ref(far, 'main')
assert hey.default_base(far) == 'main', hey.default_base(far)
assert hey.already_merged(far, 'main') is True, 'the content is on upstream'
assert hey.unpushed(far, 'main')[0] == 0, hey.unpushed(far, 'main')

# The same repository once its local base is rewritten while keeping the remote's tree --
# an amend, or a rebase that changed nothing. The base still resolves to the remote copy,
# so the exemption holds. A test phrased as "does any remote contain this commit" answered
# no here, because the local base no longer shares the remote's history.
git('switch', '-q', 'main', cwd=far)
git('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--amend', '--no-edit',
    cwd=far)
git('switch', '-q', 'work', cwd=far)
assert hey.base_ref(far, 'main') == 'upstream/main', hey.base_ref(far, 'main')
assert hey.unpushed(far, 'main')[0] == 0, hey.unpushed(far, 'main')

# With a remote in play, a branch that has never reached it is work at risk again -- the
# wording `dirty` reserves for exactly that, and the one the no-remote case must never use.
risky = out_of(hey.cmd_dirty, ns, live)
assert 'on a branch never pushed' in risky, risky
assert 'not yet in' not in risky, risky
git('remote', 'remove', 'origin')
"""

CATALOG_PROBE = """
import json, sys, tempfile; sys.path.insert(0, {here!r})
from pathlib import Path
import hey

d = Path(tempfile.mkdtemp())
mkt = d / 'somewhere'
(mkt / '.claude-plugin').mkdir(parents=True)
(mkt / '.claude-plugin' / 'marketplace.json').write_text(json.dumps({{'plugins': [
    {{'name': 'already-here', 'description': 'installed, so it needs no suggesting'}},
    {{'name': 'not-here', 'description': 'a thing this machine offers'}},
]}}), encoding='utf-8')

# A plugin ships its skills inside itself, and the description carries the words worth
# matching on. `description: >` with the text on the lines below is the ordinary shape --
# reading the marker line at face value files the skill under a description of `>`, which
# is a skill nobody can match against and looks like one nobody described.
sk = mkt / 'not-here' / 'skills' / 'folded'
sk.mkdir(parents=True)
(mkt / 'not-here' / '.claude-plugin').mkdir()
(mkt / 'not-here' / '.claude-plugin' / 'plugin.json').write_text('{{}}', encoding='utf-8')
(sk / 'SKILL.md').write_text('---' + chr(10) + 'name: folded' + chr(10)
                             + 'description: >' + chr(10)
                             + '  Reads Firestore security rules and' + chr(10)
                             + '  writes the regression tests for them.' + chr(10)
                             + '---' + chr(10), encoding='utf-8')

# `description:` with the text on the lines below is as valid as the folded form, and used
# to parse to no description at all -- which dropped the skill out of the catalogue with no
# error. The catalogue is the bound on what may be named, so a silent omission here makes a
# real capability permanently unnameable.
bare = mkt / 'not-here' / 'skills' / 'bare'
bare.mkdir(parents=True)
(bare / 'SKILL.md').write_text('---' + chr(10) + 'name: bare' + chr(10)
                               + 'description:' + chr(10)
                               + '  Deploys the widget extension.' + chr(10)
                               + '---' + chr(10), encoding='utf-8')

hey.MARKETPLACES = mkt.parent
rows = hey.catalogue({{'already-here@somewhere'}})
names = {{n for _, n, _, _, _ in rows}}
# What is installed needs no suggestion, and saying "you have this" every run is the
# advertisement the whole command exists to avoid.
assert 'already-here' not in names, names
assert {{'not-here', 'folded', 'bare'}} <= names, names

desc = {{n: v for _, n, _, _, v in rows}}
assert desc['folded'].startswith('Reads Firestore'), desc['folded']
assert 'regression tests' in desc['folded'], desc['folded']
assert desc['bare'] == 'Deploys the widget extension.', desc['bare']

# Plugin and marketplace are separate columns because they are separate facts. A skill row
# carrying its plugin where the reader was told to expect a marketplace sends them looking
# for a marketplace that does not exist.
assert [(p, m) for k, n, p, m, _ in rows if n == 'folded'] == [('not-here', 'somewhere')]
assert [(p, m) for k, n, p, m, _ in rows if n == 'not-here'] == [('not-here', 'somewhere')]

# And a plugin whose own skills are visible is filtered out whole -- the skills go with it.
# Offering a skill out of something already installed is the same advertisement, one level
# down, and the harder one to notice.
left = hey.catalogue({{'not-here@somewhere'}})
assert {{n for _, n, _, _, _ in left}} == {{'already-here'}}, left

# A second marketplace shipping the same plugin name. They are two different plugins, and
# keeping only the one whose directory sorts first hands the reader an attribution for a
# thing they did not look at -- which is the one fact the skill is told to pass on.
mkt2 = d / 'elsewhere'
(mkt2 / '.claude-plugin').mkdir(parents=True)
(mkt2 / '.claude-plugin' / 'marketplace.json').write_text(json.dumps({{'plugins': [
    {{'name': 'not-here', 'description': 'same name, different author, different thing'}},
]}}), encoding='utf-8')

# Two plugins in one marketplace, each exporting a skill of the same name. They are distinct
# capabilities, and a key without the owning plugin keeps whichever sorted first -- which
# does not merely mis-attribute the loser, it makes it unnameable, since this list is the
# bound on what may be suggested at all.
twin = mkt / 'other'
(twin / '.claude-plugin').mkdir(parents=True)
(twin / '.claude-plugin' / 'plugin.json').write_text('{{}}', encoding='utf-8')
(twin / 'skills' / 'folded').mkdir(parents=True)
(twin / 'skills' / 'folded' / 'SKILL.md').write_text(
    '---' + chr(10) + 'name: folded' + chr(10) + 'description: a different deploy skill'
    + chr(10) + '---' + chr(10), encoding='utf-8')

owners = sorted(p_ for k, n, p_, m, _ in hey.catalogue(None)
                if n == 'folded' and m == 'somewhere')
assert owners == ['not-here', 'other'], owners

both = [(m, v) for k, n, p_, m, v in hey.catalogue(None) if n == 'not-here']
assert sorted(m for m, _ in both) == ['elsewhere', 'somewhere'], both
assert {{v for m, v in both if m == 'elsewhere'}} == {{'same name, different author, different thing'}}

# Installed is keyed by name *and* marketplace. The same name in another marketplace is a
# different plugin, and marking it installed hides something the user does not have.
other = hey.catalogue({{'not-here@elsewhere'}})
assert {{'not-here', 'folded', 'bare'}} <= {{n for _, n, _, _, _ in other}}, other
assert [m for k, n, p_, m, _ in other if n == 'not-here'] == ['somewhere'], other

# Nobody could be asked, so nothing is filtered -- calling something "not installed" on a
# machine that was never consulted is a claim, not a default. Which of the two it was is
# said by the command, not decided here.
assert 'already-here' in {{n for _, n, _, _, _ in hey.catalogue(None)}}
"""

CATALOG_CMD_PROBE = """
import argparse, contextlib, io, json, os, sys, tempfile
from pathlib import Path

d = Path(tempfile.mkdtemp())
# Set before the import, because the host reads this variable and so must we. A path fixed
# in the source scans the default tree while `claude` answers from another one, and the two
# then describe different machines with nothing on screen to say so.
os.environ['CLAUDE_CONFIG_DIR'] = str(d)
sys.path.insert(0, {here!r})
import hey

assert hey.MARKETPLACES == d / 'plugins' / 'marketplaces', hey.MARKETPLACES
real_installed = hey.installed_plugins

mkt = hey.MARKETPLACES / 'somewhere'
(mkt / '.claude-plugin').mkdir(parents=True)
(mkt / '.claude-plugin' / 'marketplace.json').write_text(json.dumps({{'plugins': [
    {{'name': 'offered', 'description': 'a thing this machine offers'}},
]}}), encoding='utf-8')


def run(**kw):
    args = argparse.Namespace(all=False, names=False, show=None)
    for k, v in kw.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        hey.cmd_catalog(args, {{}})
    return buf.getvalue()


# Three states, and each says which one it is. Reporting "nothing is installed" for a host
# that could not be asked filters nothing while claiming it did, and this repository already
# settled the same argument for `gh`.
hey.installed_plugins = lambda: None
assert 'could not ask' in run(), run()
hey.installed_plugins = lambda: set()
assert 'out of 0 installed' in run(), run()
assert 'could not ask' not in run(), run()
hey.installed_plugins = lambda: {{'offered@somewhere'}}
assert 'out of 1 installed' in run(), run()

# A name that matches nothing is reported on **every** path a caller uses. It was computed
# and then dropped on the two machine-readable ones, which are the two the skill actually
# runs -- so a typo came back as an empty result indistinguishable from a real absence.
hey.installed_plugins = lambda: set()
for form in ({{}}, {{'names': True}}):
    out = run(show=['offered', 'nonesuch'], **form)
    assert 'not in the catalogue: nonesuch' in out, (form, out)
    assert 'offered' in out, (form, out)

# And the same three states at their source, with a real subprocess rather than a stand-in.
# Patching `installed_plugins` tests how the command reads the answer; nothing there notices
# if the function itself turns a crashed host into an empty set.
bin_dir = d / 'bin'
bin_dir.mkdir()
os.environ['PATH'] = str(bin_dir) + os.pathsep + os.environ['PATH']
fake = bin_dir / 'claude'


def host(body, code):
    fake.write_text('#!/bin/sh' + chr(10) + body + chr(10) + 'exit ' + str(code) + chr(10))
    fake.chmod(0o755)


# The real one, kept from before the stand-ins above replaced the name on the module.
hey.installed_plugins = real_installed


host('echo "  \\u276f one@mkt-a"; echo "  \\u276f two@mkt-b"', 0)
assert hey.installed_plugins() == {{'one@mkt-a', 'two@mkt-b'}}, hey.installed_plugins()
# The marketplace half is kept. Dropping it marks `code-review` from a marketplace you do
# not have as installed, on the strength of one you do.
host('echo "  \\u276f code-review@mine"', 0)
assert hey.installed_plugins() == {{'code-review@mine'}}, hey.installed_plugins()

host('echo "config is broken" >&2', 1)
assert hey.installed_plugins() is None, hey.installed_plugins()
host('true', 0)
assert hey.installed_plugins() == set(), hey.installed_plugins()
"""

AGE_MARK_PROBE = """
import sys, unicodedata; sys.path.insert(0, {here!r})
from hey import _blocker_age, display_width

# The age column is right-aligned, so a glyph that measures one column and draws two shifts
# every row under it -- in a CJK terminal only, which is where this plugin is mostly used.
# `strings.MARK` documents the same trap for the section glyphs and the self-test enforces
# it there; the marks in this column had never been held to it, and the em dash that used
# to mean "no start recorded" is East Asian Width `A` exactly like the arrow.
states = [
    {{'days': 3, 'bad_since': False, 'since': '2020-01-01'}},   # a real age
    {{'days': 9999, 'bad_since': False, 'since': '1998-01-01'}},  # 27 years, still fits
    {{'days': None, 'bad_since': True, 'since': '2020-13-45'}},  # not a date
    {{'days': None, 'bad_since': False, 'since': 'unknown'}},    # settled
    {{'days': None, 'bad_since': False, 'since': '2099-01-01'}},  # not started
    {{'days': None, 'bad_since': False, 'since': None}},         # never asked
]
marks = [_blocker_age(s)[0] for s in states]
# Every state has to look different, or the column says nothing.
assert len(set(marks)) == len(marks), marks
for mark in marks:
    for ch in mark:
        eaw = unicodedata.east_asian_width(ch)
        assert eaw in ('Na', 'N', 'H'), (mark, ch, eaw)
    assert display_width(mark) == len(mark), (mark, display_width(mark))
    # And fit the column it is padded into, which `9999d` reaches exactly.
    assert len(mark) <= 5, mark
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


def _sh_out(cmd: list, cwd: Path) -> str:
    """One git command's stdout, stripped. For assertions that need a real sha."""
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return p.stdout.strip()


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


PLACEHOLDER = re.compile(r"{(\w+)}")

# What each FLAIR pool's caller actually passes. Only `zero` is left -- the shortfall pools
# restated a gap the bars beside them already showed, and the bars are gone -- and the card
# calls it with nothing. A line reaching for anything else raises `KeyError` at format time,
# in one language, on one kind of day.
FLAIR_ARGS = {"zero": set()}


def string_pack_checks() -> list:
    """Every language must define the same keys, taking the same placeholders.

    None of this is a syntax error and none of it fails an English run: a key added to one
    language, or a `{placeholder}` renamed in one of them, raises `KeyError` only for the
    user who set that language, and only on the day the branch that prints it fires.
    Running the self-test twice, once per language, does not cover it either -- no fixture
    reaches every card branch, so most of these strings are never formatted at all.

    Checked statically instead: compare the packs to each other, then confirm every key the
    scripts *name* exists. The reverse -- a defined key nobody uses -- is deliberately not
    checked, because keys are routinely selected by expression (`S.card("ahead" if ... else
    "behind")`) and only the first literal is visible to a regex.
    """
    out = []
    langs = sorted(S.WEEKDAYS)
    packs = {"CARD": S.CARD, "FLAIR": S.FLAIR,
             "METRIC_LABELS": S.METRIC_LABELS, "UNITS": S.UNITS,
             "STATE_LABELS": S.STATE_LABELS}

    for name, pack in packs.items():
        absent = [lc for lc in langs if lc not in pack]
        if absent:
            out.append(("strings", f"{name} has no entry for {', '.join(absent)}"))
            continue
        for lc in langs[1:]:
            gap = set(pack[langs[0]]) ^ set(pack[lc])
            if gap:
                out.append(("strings", f"{name} keys differ between {langs[0]} and {lc}: "
                                       f"{', '.join(sorted(gap))}"))
    for lc in langs:
        if len(S.WEEKDAYS[lc]) != 7:
            out.append(("strings",
                        f"WEEKDAYS[{lc}] has {len(S.WEEKDAYS[lc])} entries, not 7"))

    # Everything below indexes a pack by language. A language listed in WEEKDAYS but absent
    # from a pack is already reported above, and reaching for it again here would raise
    # `KeyError` -- a checker that crashes on the very state it exists to diagnose, taking
    # the rest of the findings with it.
    full = [lc for lc in langs if all(lc in pack for pack in packs.values())]
    if not full:
        return out

    for name, pack in (("CARD", S.CARD),):
        for key, text in pack[full[0]].items():
            want = set(PLACEHOLDER.findall(text))
            for lc in full[1:]:
                got = set(PLACEHOLDER.findall(pack[lc].get(key, "")))
                if got != want:
                    out.append(("strings", f"{name}[{key!r}] takes {sorted(want)} in "
                                           f"{full[0]} but {sorted(got)} in {lc}"))
    for kind, allowed in FLAIR_ARGS.items():
        for lc in full:
            for line in S.FLAIR[lc].get(kind, []):
                extra = set(PLACEHOLDER.findall(line)) - allowed
                if extra:
                    out.append(("strings", f"FLAIR[{lc}][{kind!r}] uses {sorted(extra)}, "
                                           f"which the caller does not pass"))
    unknown = sorted(set(S.FLAIR[full[0]]) - set(FLAIR_ARGS))
    if unknown:
        out.append(("strings", f"FLAIR pool(s) {unknown} have no declared caller "
                               f"arguments, so nothing checks what they may reference"))

    src = "\n".join((HERE / f).read_text() for f in ("hey.py", "board.py"))
    named = [(r"\bS\.card\(\s*[\"']([a-z_]+)[\"']", "S.card", S.CARD),
             (r"\bflair\(\s*[\"']([a-z_]+)[\"']", "flair", S.FLAIR)]
    for pattern, label, pack in named:
        for key in sorted(set(re.findall(pattern, src))):
            for lc in full:
                if key not in pack[lc]:
                    out.append(("strings",
                                f"{label}({key!r}) is called, but {lc} has no such key"))
    # `board.section` indexes MARK directly, so a card section with no marker is a KeyError
    # on the card itself rather than a missing glyph.
    for key in sorted(set(re.findall(r"\bsection\(\s*[\"']([a-z_]+)[\"']", src))):
        if key not in S.MARK:
            out.append(("strings", f"section({key!r}) is called, but MARK has no marker"))
    return out


# Features removed on purpose -- board.py's module docstring says why. No script prints any
# of them any more.
REMOVED_FEATURES = ("weekly pace", "주간 페이스", "personal best", "개인 최고",
                    "streak", "스트릭", "ranked", "ranking", "랭킹", "순위",
                    "daily goal", "weekly goal", "일일 목표", "주간 목표")

# Saying the feature does not exist is the point of several of these sentences, not a
# violation of the rule. Checked on the line, which is where the negation sits.
DENIALS = ("no ", "not ", "never", "none of", "nothing", "gone", "used to",
           "없", "않", "예전에는")


ENCODINGLESS = re.compile(r"\.(?:read_text|write_text)\((?![^()]*encoding=)")


def encoding_checks() -> list:
    """Every file the shipped scripts read or write must name its encoding.

    Left to the platform default, a Korean ledger written as UTF-8 raises
    `UnicodeDecodeError` on a Windows console still defaulting to a legacy code page --
    and the ledger, the config and the history are all files this tool wrote itself, so
    the failure lands on data the user cannot see anything wrong with. CI runs Linux and
    macOS, where the default is already UTF-8, so nothing here would ever catch it.

    The self-test itself is exempt: it reads only what it just wrote, on the machine that
    wrote it, and pinning it would add noise without covering a user.
    """
    plugin = HERE.parent
    out = []
    for f in sorted(plugin.rglob("*.py")):
        if f.name == "selftest.py":
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if ENCODINGLESS.search(line):
                out.append((f"{f.relative_to(plugin)}:{n} reads or writes without "
                            f"`encoding=`, so the platform default decides", line.strip()))
    return out


def version_checks() -> list:
    """The pinned Codex version must have a changelog entry, in both languages.

    Claude Code installs from the branch, so every commit reaches it. Codex pins a version
    and only sees an update when that number moves -- and it did not move for seventy-one
    commits, because the rule lived in the README and nothing enforced it. Codex users
    received none of them, the fixes that stop a ledger being truncated included.

    Matched against `CHANGELOG.md` rather than asked of git: CI checks out at depth 1, so
    there is no history here to ask when each last changed. The side effect is the point --
    raising the version now requires writing down what changed, which is the thing a Codex
    user actually needs at the moment the update arrives.
    """
    root = HERE.parent.parent.parent
    manifest = HERE.parent / ".codex-plugin" / "plugin.json"
    if not manifest.exists():
        return []
    try:
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
    except json.JSONDecodeError as e:
        return [("codex plugin.json does not parse", str(e))]
    if not version:
        return [("codex plugin.json has no `version`, and Codex requires one", "")]
    out = []
    for name in ("CHANGELOG.md", "CHANGELOG.ko.md"):
        log = root / name
        if not log.exists():
            out.append((f"{name} is missing, so version {version} would ship with no "
                        f"note of what changed", ""))
        elif f"## {version}" not in log.read_text(encoding="utf-8"):
            out.append((f"{name} has no `## {version}` entry, so the pinned version and "
                        f"the changelog disagree", f"version={version}"))
    return out


def banned_phrases() -> list:
    """The phrases `hey-wording` forbids, read out of that file rather than copied here.

    A second list kept in this script would drift from the rule it enforces the first time
    somebody edits one of them, which is the failure this whole family of checks exists to
    catch. So the rule stays in one place and the check reads it.

    Bullets whose explanation says `consecutive` are skipped: `또한` in one sentence is
    ordinary Korean and only the repetition is a tell, which a substring test cannot see.
    A check that cries wolf is a check nobody reads.
    """
    src = HERE.parent / "skills" / "hey-wording" / "SKILL.md"
    if not src.exists():
        return []
    text = src.read_text(encoding="utf-8")
    try:
        start = text.index("**Words to drop.**")
        end = text.index("**Words to use.**", start)
    except ValueError:
        return []
    out = []
    for line in text[start:end].splitlines():
        if not line.lstrip().startswith("-"):
            continue
        prose = re.sub(r"`[^`]+`", "", line)
        if "consecutive" in prose:
            continue
        out += [t.lstrip("~") for t in re.findall(r"`([^`]+)`", line)]
    return out


def wording_checks() -> list:
    """No skill may contain a phrase `hey-wording` tells the model never to write.

    The rules live in one file and the violations land in another -- `hey-run` was teaching
    a box percentage the product rejects, and nothing connected the two until a reviewer
    read both. Examples in a skill are templates: whatever they show is what gets written.

    `hey-wording` itself is exempt, since listing the phrases is its job.
    """
    plugin = HERE.parent
    phrases = banned_phrases()
    if not phrases:
        return [("hey-wording has no parseable `Words to drop` list, so nothing is "
                 "enforced", "")]
    out = []
    docs = sorted(plugin.glob("skills/*/SKILL.md")) + sorted(plugin.glob("commands/*.md"))
    for path in docs:
        if path.parent.name == "hey-wording":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for phrase in phrases:
                if phrase in line:
                    out.append((f"{path.relative_to(plugin)}:{n} writes `{phrase}`, which "
                                f"`hey-wording` forbids", line.strip()[:120]))
    return out


def scoped_hits(text: str) -> list:
    """Removed-feature terms `text` asserts, ignoring the sentences that deny them.

    Wrapped lines are joined before splitting, because the two failure modes pull in
    opposite directions. A whole line is too coarse: `Never send user data anywhere.
    Ranking compares only against the user's own past` denies one thing and asserts
    another, and the `Never` covered both. A single line is too fine: prose here is
    hard-wrapped, so `... a` / `personal best. All of it is gone.` separates a denial from
    its own term and the paragraph written to say a feature was removed gets reported as
    claiming it.
    """
    hits = []
    for frag in re.split(r"(?<=[.;])\s+", " ".join(text.split())):
        low = frag.lower()
        if any(d in low for d in DENIALS):
            continue
        hits += [t for t in REMOVED_FEATURES if t in low]
    return hits


def removed_feature_checks() -> list:
    """Prose must not describe a feature the scripts no longer have.

    Three days after the ranking layer came out of the code, the README still advertised a
    leaderboard and two skills still told the model to report a `weekly pace` no command
    produces. That last part is the expensive half: a tool whose whole claim is that the
    model never writes a number by eye had its own instructions asking for one, and the
    only place left to get it was invention.

    **Fenced blocks are skipped**, so a stale card *example* still slips through -- the
    banner and the sample output in the README both did. Catching those means parsing card
    layout out of a code fence, which is a different job than this one. Prose is where the
    claims live, and prose is what this covers.
    """
    root = HERE.parent.parent.parent
    files = [root / "README.md", root / "docs" / "ko" / "README.ko.md"]
    files += sorted((HERE.parent / "skills").glob("*/SKILL.md"))
    files += sorted((HERE.parent / "commands").glob("*.md"))

    out = []
    for path in files:
        if not path.exists():
            continue
        # Paragraphs first, then sentences. Neither unit alone works: a whole line is too
        # coarse, because `Never send user data anywhere. Ranking compares only against the
        # user's own past` denies the network and then, in the same breath, describes a
        # feature that had been deleted -- and the line-wide `Never` covered both halves,
        # which is how a Codex review found that sentence and this check did not. A single
        # line is also too fine, because prose here is hard-wrapped: `Days used to be
        # scored ... a` / `personal best. All of it is gone.` puts the denial and the term
        # on different lines, and sentence-splitting per line reports the paragraph that
        # exists to say the feature was removed.
        fenced, para = False, []

        def flush(para=para):
            start = para[0][0] if para else 0
            joined = " ".join(t for _, t in para)
            para.clear()
            for term in scoped_hits(joined):
                # Every skill's file is named SKILL.md, so the basename alone does not say
                # which one failed.
                yield (f"{path.relative_to(root)}:{start} names `{term}`, which no script "
                       f"prints", joined[:160])

        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                out.extend(flush())
                fenced = not fenced
                continue
            if fenced or not line.strip():
                out.extend(flush())
                continue
            para.append((n, line.strip()))
        out.extend(flush())
    return out


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

    # Every `HEY_*` is dropped and only the three the fixture owns are put back. A shell
    # with `HEY_WIDTH=120` set used to run the whole card-layout suite at a width CI never
    # sees, so a row overrunning the 78-column default passed here and failed on somebody
    # else's machine. Dropping the prefix rather than that one name is what keeps the next
    # variable someone adds from leaking in the same way. Probes that care set their own.
    env = {k: v for k, v in os.environ.items() if not k.startswith("HEY_")}
    env.update({"HEY_HOME": str(home), "HEY_LANG": args.lang,
                "HEY_TRANSCRIPTS": str(empty)})
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
    # A bare repo's HEAD follows the machine's `init.defaultBranch`, and this fixture
    # pushes `main`. Where that default is `master` -- CI, and any git before 2.28 -- HEAD
    # points at a ref no push ever creates, so cloning this origin produces a repository
    # with **no HEAD at all**. That is what the `clean` project silently was in CI, passing
    # every check that only asked whether it was dirty.
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=origin)
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
        "blocker age marks are distinct and never draw wide":
            AGE_MARK_PROBE.format(here=str(HERE)),
        "every rendered card row fits the card": CARD_FIT_PROBE.format(here=str(HERE)),
        "an item keeps its history when its name changes":
            ITEM_ID_PROBE.format(here=str(HERE)),
        "the zero note only fires when it has something to explain":
            ZERO_NOTE_PROBE.format(here=str(HERE)),
        "a box ticked after collect still lands on that day":
            LATE_TICK_PROBE.format(here=str(HERE)),
        "markdown quoted inside the ledger is not counted as work":
            FENCE_PROBE.format(here=str(HERE)),
        "an interrupted write leaves the previous file intact":
            ATOMIC_WRITE_PROBE.format(here=str(HERE)),
        "token cost is priced only from rates somebody supplied":
            TOKEN_COST_PROBE.format(here=str(HERE)),
        "a day's commit span is a measure, and its absence is not zero":
            COMMIT_SPAN_PROBE.format(here=str(HERE), proj=str(proj)),
        "tokens are charged to a project by path, not by string prefix":
            TOKEN_SCOPE_PROBE.format(here=str(HERE)),
        "no remote and no repository are answers, not faults":
            NO_REMOTE_PROBE.format(here=str(HERE)),
        "add names a repository below rather than adopting one":
            ADD_PROBE.format(here=str(HERE)),
        "the catalogue skips what is installed and reads a folded description":
            CATALOG_PROBE.format(here=str(HERE)),
        "catalog says whether it could ask, and reports a name it does not have":
            CATALOG_CMD_PROBE.format(here=str(HERE)),
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
        # The overlap signal compares backtick tokens in the item text, so it cannot see a
        # shared file under another name, a generated output, or a manifest both items
        # touch. `/hey-run` says never to decide from it alone -- and the script used to
        # print "these can run in parallel", overruling its own skill.
        ([hey, "batch"], "batch: reports absent evidence, not a parallel-safe verdict",
         "no overlap evidence in the item text"),
        # The input side of a capability match. `next` and `batch` both cut their lists
        # short because they answer "what now"; a question about the shape of the plan has
        # to see the tail as well, and the tail is where an unusual item lives.
        ([hey, "open-items"], "open-items: reaches past where next and batch stop",
         "Not yet"),
        ([hey, "open-items"], "open-items: a blocked item is marked rather than dropped",
         "[blocked] Marked elsewhere"),
        ([hey, "open-items"], "open-items: a closed item is not part of the plan",
         "10 open item(s)"),
        # An item that puts its real work in subitems was arriving as a title and a total.
        # This command is handed over as the whole plan, so the words that name the actual
        # framework or service have to come with it.
        ([hey, "open-items"], "open-items: an item's unfinished subitems come with it",
         "    - part three"),
        ([hey, "context", "--date", today], "context"),
        ([board, "collect", "--date", yesterday], "collect (yesterday)", "baseline"),
        ([board, "collect", "--date", today], "collect (today)"),
        ([hey, "snapshot"], "snapshot"),
        (["-c", probes.pop("stats")], "first record is a baseline"),
        # Re-collecting a day already behind a recorded one must not restate box state:
        # the ledger holds only today, so it would move the baseline and zero the newer day.
        ([board, "collect", "--date", two_days_ago], "collect: a past day keeps its hands off "
         "box state", "not collected - a later day is already recorded"),
        # `snapshot --date` is the same door with no lock on it: it wrote today's boxes
        # under an earlier date, and every later variance, carry-over and closed-work
        # figure was then computed against a state that never existed.
        ([hey, "snapshot", "--date", two_days_ago],
         "snapshot: a past day keeps its hands off box state too",
         "is before a day already recorded"),
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
        ([hey, "item", "P0"], "item: an ambiguous key lists the matches", "matches 7 items"),
        ([hey, "item", "nope"], "item: no match says so", "no item matches"),
        ([hey, "burndown"], "burndown"),
        ([board, "brief"], "morning card"),
        ([board, "wrap"], "evening card"),
        ([hey, "blockers"], "blockers: lists them all", "6 blocked"),
        # `[blocked]` classifies wherever the item sits, so a blocker does not have to
        # be filed under the heading to count.
        ([hey, "blockers"], "blockers: `[blocked]` counts outside a blocker section",
         "Marked elsewhere"),
        # The fixture carries one of every state a blocker's age can be in, and each calls
        # for a different move, so each has to be told apart on the screen you triage from.
        ([hey, "blockers"], "blockers: a typo'd date is not a missing one",
         "is not a real date"),
        ([hey, "blockers"], "blockers: a future date says the wait has not started",
         "dated ahead of today"),
        ([hey, "blockers"], "blockers: `unknown` is a settled answer, not a gap",
         "could not be found"),
        ([hey, "blockers"], "blockers: still nags about the ones nobody has dated",
         "no start recorded"),
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

    # Reported per group so a clean group still says so. Folding them together meant one
    # broken manifest silenced the all-clear for everything else checked statically.
    for group, probe in (("manifests and component names", static_checks),
                         ("language packs agree", string_pack_checks),
                         ("docs claim no removed feature", removed_feature_checks),
                         ("every read and write names its encoding", encoding_checks),
                         ("the pinned version has a changelog entry", version_checks),
                         ("no skill writes what the wording rules forbid", wording_checks)):
        problems = probe()
        for label, detail in problems:
            check(f"static: {label}", False, detail)
        if not problems:
            check(f"static: {group}", True)

    for case in cases:
        cmd, label = case[0], case[1]
        want = case[2] if len(case) > 2 else None
        code, out = run(cmd, env, proj)
        passed = code == 0 and (want is None or want in out)
        check(label, passed, out if want is None or code else
              f"expected to find {want!r} in:\n{out}")

    # `current` means the project you are standing in, and nothing else. It used to answer
    # from the sole registered project whenever the cwd matched none of them, so a card for
    # a ledger you were nowhere near came back looking like yours -- and the same command
    # started failing the day a second project was registered. Only `fixture` is registered
    # this early, which is the one arrangement where that fallback was reachable at all.
    run([hey, "scope", "current"], env, proj)
    code, out = run([board, "brief"], env, tmp)
    check("scope current: the only registered project is not briefed from outside it",
          code == 2 and "fixture" not in out, out)
    # Failing is half of it. The path it names is the main repo root, which from inside a
    # linked worktree is not where you are standing, and is what `add` wants.
    check("scope current: being out of scope says how to get in",
          "hey.py add" in out or "hey.py projects" in out, out)

    # The way out is not the same for every command, and offering the wrong one costs the
    # reader a minute of believing they mistyped a flag. `note` is the sharp case: it takes
    # `--scope` and then ignores it, so advising `--scope all` there fails without a word.
    # `collect` has always called the first record a baseline. The card read the same row
    # and printed `0.00 AI-days`, so the two disagreed about the same day -- and the card
    # is the half a person actually reads, on the one day they have nothing to compare it
    # against. Asserted in whichever language is running, since the word is translated.
    code, out = run([board, "wrap", "--date", yesterday], env, proj)
    check("card: the first record reads as a baseline, not as a day that closed nothing",
          S.card("baseline", args.lang).split(" ")[0] in out and "0.00" not in out, out)

    # A ledger created today has no past, so `draft-log` reads it out of git instead. The
    # author is named rather than resolved: the fixture's commits carry `GIT_AUTHOR_EMAIL`
    # from the environment, while `git config user.email` would find whatever identity the
    # machine running the test happens to have -- which is nothing in CI and a real address
    # on a laptop, so the default would make this pass in one place and fail in the other.
    before = (proj / "TASKS.local.md").read_text()
    code, out = run([hey, "draft-log", "--since", "30",
                     "--author", "selftest@example.com"], env, proj)
    check("draft-log: drafts work-log headings out of git history",
          code == 0 and "###" in out, out)
    # Printing is the whole contract. A commit subject says what changed, not how far the
    # work got, so nothing here is a work-log entry until a person says it is.
    check("draft-log: prints, and leaves the ledger untouched",
          (proj / "TASKS.local.md").read_text() == before, "the ledger was modified")
    # The fixture has a linked worktree, and worktrees share one ref store, so a commit is
    # reachable from both and gets read twice before it is deduplicated.
    shas = re.findall(r"\(([0-9a-f]{7,})\)$", out, re.M)
    check("draft-log: a commit two worktrees can both see is drafted once",
          bool(shas) and len(shas) == len(set(shas)), out)

    # A spec generator stops at `tasks.md`; this tool starts there, so the boundary is a
    # format conversion. `T001` becoming `[id t001]` is the half that matters — it is the
    # stable key a hand-written ledger most often lacks, arriving for free.
    spec = tmp / "tasks.md"
    spec.write_text("# Phase 1: Setup\n\n"
                    "- [x] T001 Create project structure\n"
                    "- [ ] T002 [P] Configure linting in .eslintrc\n\n"
                    "# Final Phase: Polish\n\n"
                    "- [ ] T040 [P] [US1] Update the README\n")
    code, out = run([hey, "import-tasks", str(spec)], env, proj)
    check("import-tasks: task ids arrive as `[id ...]`, and `[x]` survives",
          code == 0 and "`[id t001]`" in out and "- [x] **Create project structure**" in out,
          out)
    check("import-tasks: `[P]` and `[US1]` are kept as text, not dropped",
          "P, US1" in out, out)
    # The column the whole ledger is counted from is the one place to invent nothing.
    check("import-tasks: no estimate is invented for tasks that carry none",
          "AI 0" not in out and "? MD / AI ?" in out, out)
    check("import-tasks: a file with no task lines says so rather than printing nothing",
          run([hey, "import-tasks", str(tmp / "TASKS.local.md")], env, proj)[0] == 2, "")

    # A note lands in one ledger, so `--scope all` never meant anything here. It used to
    # parse and be ignored, which reads as "accepted" to whoever typed it.
    code, out = run([hey, "note", "x", "--scope", "all"], env, proj)
    check("note: rejects `--scope` rather than accepting and ignoring it",
          code != 0 and "unrecognized arguments" in out, out)

    code, out = run([hey, "note", "from nowhere"], env, tmp)
    check("out of scope: a note is sent to `--project`, since it lands in one ledger",
          code == 2 and "--project" in out and "--scope all" not in out, out)
    # `resolve` has neither flag. An escape hatch it does not have is not an escape hatch.
    code, out = run([hey, "resolve"], env, tmp)
    check("out of scope: `resolve` offers neither flag, having neither",
          code == 2 and "--project" not in out and "--scope all" not in out, out)
    run([hey, "scope", "all"], env, proj)

    # Blockers must be detected in whichever language the ledger uses, and only the real
    # ones -- three sit in the blocker section, while `Third item` says "depending", which
    # is not `pending` and must not count.
    code, out = run([hey, "batch"], env, proj)
    check("blocker detection", "6 blocked item(s) excluded" in out, out)

    # The other half of the rule. Words in prose no longer classify: an item can say
    # "waiting on a decision" and still be work you are free to pick up. A false positive
    # here is expensive -- the item leaves the `/hey-run` candidates and starts accruing a
    # wait it was never on.
    code, out = run([hey, "blockers"], env, proj)
    check("blockers: a waiting word without the marker is not a blocker",
          "Reads as blocked" not in out, out)
    # But the change must not be silent on a ledger written under the old rule.
    code, out = run([hey, "doctor"], env, proj)
    check("doctor: names the lines that read as waiting but carry no marker",
          "read as waiting but carry no" in out and "Reads as blocked" in out, out)

    # The removed-feature check has two failure modes and they pull in opposite directions,
    # so both are pinned. Too coarse: a denial anywhere on the line covers an assertion
    # elsewhere on it, which is how `Never send user data anywhere. Ranking compares ...`
    # survived. Too fine: prose is hard-wrapped, so a denial and its term land on different
    # lines and the paragraph written to say a feature is gone gets reported as claiming it.
    check("static check: a denial cannot cover an assertion later in the same line",
          scoped_hits("- Never send user data anywhere. Ranking compares only against "
                      "the user's own past") == ["ranking"],
          "the line-wide denial is back")
    check("static check: a wrapped paragraph's denial still reaches its own term",
          scoped_hits("Days used to be scored against each other here -- a board, a\n"
                      "streak, a weekly pace, a personal best. All of it is gone.") == [],
          "hard-wrapped prose is being reported as claiming what it denies")

    # `[id ...]` used to come up only once a rename had already cost something -- a key two
    # items claim, or a recorded key nothing answers to. Both arrive after the history it
    # protects is already detached, and adding an id then recovers none of it.
    check("doctor: counts the items with no `[id ...]` before a rename costs anything",
          "carry no `[id <name>]`" in out, out)
    # One line for the whole ledger, and informational: a project with two hundred
    # un-idded items would otherwise report two hundred warnings about a file that is
    # working fine, and bury the failures that are not.
    idline = next((l for l in out.splitlines() if "carry no `[id <name>]`" in l), "")
    check("doctor: the id notice is informational, not a warning",
          idline.strip().startswith("info"), idline or out)

    # A `[since]` naming a day that has not arrived is a deliberate statement that the wait
    # has not started. The records would happily supply an age -- the item has been sitting
    # in the fixture's snapshots since the first one -- and using it would answer a question
    # the line already answered, with the opposite answer.
    code, out = run([hey, "carryover", "--days", "1"], env, proj)
    check("carry-over: a future `[since]` is not aged from the records",
          "Not yet" not in out, out)
    # A `[since]` age survives a missing snapshot and a renamed item; the carried-over
    # count survives neither, since its key is `<phase>|<title>`. The weaker signal must
    # not sit above the stronger one, where it reads as the headline.
    blockers_at = out.find("long-standing blockers")
    unchanged_at = out.find("observed unfinished")
    check("carry-over: blocker age is reported above the carried-over count",
          blockers_at != -1 and (unchanged_at == -1 or blockers_at < unchanged_at), out)
    # The unit is snapshots. Calling them days is wrong whenever `collect` skipped one,
    # which is most weeks. Checked on the item rows themselves, where a reader glancing at
    # the number would take the unit from.
    rows_after = out.split("observed unfinished")[-1].split("\n")[1:] if unchanged_at != -1 else []
    item_rows = [ln for ln in rows_after if ln.strip().startswith("- ")]
    check("carry-over: the carried-over unit is observations, not days",
          bool(item_rows) and all("observations" in ln and "days" not in ln
                                  for ln in item_rows), item_rows or out)

    # The session-start hook is the only always-on component, and silence is its default.
    # With no stdin it falls back to the cwd, which is what these two cases exercise.
    hook = [str(HERE.parent / "hooks-handlers" / "on-session-start.py")]
    hook_env = {**env, "CLAUDE_PLUGIN_ROOT": str(HERE.parent)}
    code, out = run(hook, hook_env, proj)
    check("hook: reports unpushed work", "neither committed nor pushed" in out, out)
    code, out = run(hook, hook_env, tmp)
    check("hook: silent outside a registered project", code == 0 and not out.strip(), out)

    # `dirty` prints one block per project in scope, and its all-clear is itself a line
    # reading "nothing uncommitted or unpushed". The scope was set to `all` a few cases
    # back, so with a clean project registered alongside the dirty fixture, a hook that
    # decides with `"nothing uncommitted" in text` goes silent about work at risk. A fresh
    # clone of the fixture's own origin is the clean project: real repository, tracked
    # branch, nothing outstanding.
    clean = tmp / "clean-project"
    subprocess.run(["git", "clone", "-q", str(origin), str(clean)],
                   env=env, capture_output=True, text=True)
    # Excluded first: the ledger is local state, and left untracked it is itself a dirty
    # working tree -- which would make this "clean" project report work at risk and quietly
    # turn the check below into one that passes for the wrong reason.
    (clean / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (clean / ".git" / "info" / "exclude").write_text("TASKS.local.md\n")
    (clean / "TASKS.local.md").write_text(LEDGER.format(today=today))
    run([hey, "add", str(clean), "--name", "clean"], env, proj)

    # Branch and commit describe the project the note is filed under. Run from a directory
    # belonging to *another* repository, `--project` used to carry this one's HEAD into
    # that one's ledger, where nothing marks it as coming from somewhere else. Asserted on
    # the sha: `clean` is a clone, so it has a HEAD of its own to be wrongly credited.
    fixture_head = _sh_out(["git", "rev-parse", "--short", "HEAD"], proj)
    clean_head = _sh_out(["git", "rev-parse", "--short", "HEAD"], clean)
    code, out = run([hey, "note", "filed from elsewhere", "--project", "fixture"], env, clean)
    # `clean_head` empty would make the negative half vacuously false, so it is asserted
    # rather than assumed -- a clone with no HEAD is exactly the fixture bug this found.
    check("note: takes branch and commit from the project it files into, not the cwd",
          code == 0 and clean_head and fixture_head != clean_head
          and fixture_head in out and clean_head not in out,
          f"fixture={fixture_head!r} clean={clean_head!r}\n{out}")
    code, out = run([hey, "dirty"], env, proj)
    check("dirty: the clean project really does report the all-clear line",
          "nothing uncommitted or unpushed" in out, out)
    code, out = run(hook, hook_env, proj)
    check("hook: a clean project elsewhere does not silence the dirty one",
          "neither committed nor pushed" in out, out)
    run([hey, "remove", "clean"], env, proj)

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
    # The template is the first ledger a new user ever sees, and `doctor` is the first thing
    # they are told to run. A heading the template spells differently from the one the
    # scripts look for greets them with a warning about a file they have not touched yet.
    # Sliced to this project's block so it is the template being judged, not the fixture --
    # and it covers whichever template the active language picks.
    code, out = run([hey, "doctor"], env, proj)
    block = out.split("project second\n", 1)[-1].split("\nproject ", 1)[0].split("\nhistory", 1)[0]
    check("add --init: the template satisfies every section doctor looks for",
          "project second\n" in out and "heading" not in block, block)
    # The template ships one example item, one example subitem and one example blocker.
    # Counted, they made the first card a new user ever sees read `0/3 boxes`, `AI 0.4`
    # and `Blocked 1` -- every figure on it invented by the file they had not written yet.
    check("add --init: the template's own example rows are not counted as work",
          "stand-in" in block, block)
    code, out = run([hey, "progress", "--project", "second"], env, proj)
    check("add --init: a fresh ledger has no items, not three",
          "0/0 boxes" in out or "no checklist" in out, out)
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
    # `doctor` tells you to re-add whenever the base is wrong, so this is a path users are
    # actively sent down. It used to rebuild the entry from scratch, discarding everything
    # `add` does not manage -- following the advice destroyed settings. Nothing in the
    # config is optional any more, so the property is observed with a key `add` has never
    # heard of, which is also the case that matters: a field added in a later version.
    cfg_path = home / "config.json"
    cfg_now = json.loads(cfg_path.read_text())
    for entry in cfg_now["projects"]:
        if entry["name"] == "fixture":
            entry["invented_later"] = "keep me"
    cfg_path.write_text(json.dumps(cfg_now, ensure_ascii=False, indent=2) + "\n")
    code, out = run([hey, "add", str(proj), "--name", "fixture", "--base", "main"],
                    env, proj)
    check("add: re-adding says so, and names what it carried forward",
          code == 0 and "updated: fixture" in out and "kept:   invented_later" in out, out)
    kept = [e for e in json.loads(cfg_path.read_text())["projects"]
            if e["name"] == "fixture"][0]
    check("add: a setting it does not manage survives the re-add",
          kept.get("invented_later") == "keep me", kept)
    code, out = run([hey, "doctor"], env, proj)
    check("doctor: flags a base the working branch has left behind",
          "If `develop` is what work merges into" in out, out)

    # `note` writes into whichever half holds the notes heading, and with the halves split
    # that is the companion -- writing to the primary would file the note where nothing
    # reads it back. `SPLIT_PROBE` covers the read side; this is the only thing anywhere
    # that writes to a split ledger. Registered last because it changes what is in scope,
    # and the scope was set to `all` well before this point.
    split = tmp / "split-ledger"
    split.mkdir()
    primary = split / "TASKS.local.md"
    companion = split / "TASKS.log.local.md"
    primary.write_text("## P0. Phase (1 MD / AI 0.5)\n\n"
                       "- [ ] **Only item** -- 1 MD / AI 0.5\n")
    companion.write_text("## Notes\n\nNewest first.\n\n---\n\n## Work log\n")
    untouched = primary.read_text()
    code, out = run([hey, "add", str(split), "--name", "split", "--ledger", str(primary),
                     "--ledger-log", str(companion)], env, proj)
    check("add: registers a split ledger", code == 0 and "log:" in out, out)
    code, out = run([hey, "note", "first note", "--project", "split"], env, proj)
    check("note: a split ledger takes the note in the companion",
          code == 0 and "first note" in companion.read_text(), out)
    check("note: the checklist half is left untouched",
          primary.read_text() == untouched, primary.read_text())
    code, out = run([hey, "note", "second note", "--project", "split"], env, proj)
    body = companion.read_text()
    # A second note the same day belongs under the heading already there. Opening a new one
    # splits the day in two, and `notes` reads them back per date.
    check("note: a second note the same day joins today's heading",
          body.count(f"### {today}") == 1 and "second note" in body, body)

    # This project is not a git repository, so the remote cannot be inspected and detection
    # comes back with nothing. The base already on record is kept -- and has to be reported
    # as kept, because printing "unresolved" would contradict the config just written.
    run([hey, "add", str(split), "--name", "split", "--ledger", str(primary),
         "--base", "trunk"], env, proj)
    code, out = run([hey, "add", str(split), "--name", "split", "--ledger", str(primary)],
                    env, proj)
    # `trunk`, not `origin/trunk`: the config holds a branch name, and dressing it as a
    # remote ref asserted that `origin/trunk` had been found when nothing had looked. The
    # kept value is still reported -- saying "unresolved" would contradict the file this
    # command just wrote -- with what can read it said separately.
    # Closed subitems stay out: they are not what is ahead, and a plan padded with finished
    # work reads as bigger than it is. A negative, so it cannot ride in the `cases` list.
    _, kids_out = run([hey, "open-items"], env, proj)
    check("open-items: a closed subitem is not what is ahead",
          "part three" in kids_out and "part one" not in kids_out
          and "part two" not in kids_out, kids_out)

    check("add: a re-add with no --base reports the base it kept, not `unresolved`",
          code == 0 and "trunk  (kept)" in out and "unresolved" not in out, out)
    check("add: a kept base on a non-repository says nothing reads it",
          "not a git repository, so nothing reads it" in out, out)

    # `git log --until <day> 23:59` means 23:59:00, so a commit made in the last minute of
    # the day fell outside it -- and the next day starts at 00:00, so it fell outside that
    # one too and was counted on no day at all. Its own repository, holding nothing but
    # that commit, so the count cannot be satisfied by anything else.
    late = tmp / "late-commit"
    late.mkdir()
    git("init", "-q", cwd=late)
    (late / "late.txt").write_text("committed in the last minute of the day\n")
    git("add", "-A", cwd=late)
    stamp = f"{today}T23:59:30"
    subprocess.run(["git", "commit", "-qm", "the last minute"], cwd=str(late),
                   env={**env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
                   capture_output=True, text=True)
    probe = ("import sys; sys.path.insert(0, %r)\n"
             "from board import code_lines\n"
             "got = code_lines({'root': %r}, %r, None)\n"
             "assert got['commits'] == 1, got\n"
             "assert got['added'] == 1, got\n"
             % (str(HERE), str(late), today))
    code, out = run(["-c", probe], env, proj)
    check("code: a commit in the last minute of the day is counted on that day",
          code == 0, out)

    # `pr-sync` was the one command with no coverage at all, because it shells out to `gh`
    # and CI has no authenticated one. A stub on PATH is what makes it testable anywhere:
    # it answers `pr list` with a fixed body and fails on anything else, so the test also
    # pins the shape of the call.
    #
    # The body carries one marker of each kind. Note what `closes P0|First item` becomes:
    # the pattern stops at whitespace, so the marker arrives as `P0|First`. Matching on a
    # fragment is the design, and `closes P0` fitting five items is the cost of it.
    fakebin = tmp / "fakebin"
    fakebin.mkdir()
    gh_stub = fakebin / "gh"
    gh_stub.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "pr" ] && [ "$2" = "list" ]; then\n'
        "  cat <<'JSON'\n"
        '[{"number": 42, "title": "wire up alpha",'
        ' "body": "closes P0|First item\\ncloses P0\\ncloses P9|Nope",'
        ' "createdAt": "2026-08-02T09:00:00Z",'
        ' "mergedAt": "2026-08-05T10:00:00Z"}]\n'
        "JSON\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n")
    gh_stub.chmod(0o755)
    gh_env = {**env, "PATH": f"{fakebin}{os.pathsep}{env.get('PATH', '')}"}

    code, out = run([hey, "pr-sync", "--project", "fixture"], gh_env, proj)
    check("pr-sync: reads merged PRs and resolves an unambiguous marker",
          code == 0 and "P0|First -> P0|First item" in out, out)
    check("pr-sync: says whether the item it resolved to is still open",
          "still unchecked" in out, out)
    # The per-PR rows are what a reader skims. A merged PR naming an item that is still
    # open is the one shape here that asks for a decision -- work landed, ledger has not
    # heard -- so it is gathered at the end instead of being left in the scroll.
    # How long the pull request stayed open, computed from two dates that arrived in the
    # same response and stored nowhere. GitHub holds the authoritative copy, and a second
    # one kept here would go stale and then be believed.
    check("pr-sync: says how long the PR was open, without keeping a copy of the dates",
          "3 day(s) open" in out, out)
    check("pr-sync: gathers the still-unchecked items into one closing list",
          "item(s) named by a merged PR and still unchecked" in out
          and "(#42)" in out, out)
    # And it stops there. Proposing is the contract; the tick is the user's.
    check("pr-sync: proposes the tick rather than taking it",
          "ask before ticking" in out, out)
    # The bug: `P0` fits every item in the phase, and the report used to name one of them,
    # picked by whichever order the dict happened to be in.
    check("pr-sync: an ambiguous marker names none of them, and lists what it fits",
          "matches 7 items" in out and "P0|Groundwork" in out, out)
    check("pr-sync: a marker matching nothing says so",
          "P9|Nope -> not found in ledger" in out, out)
    # `_sh` swallows a failed `gh`, so an empty result has to be reported rather than read
    # as "no markers found". Its own stub, rather than whatever `gh` the machine happens to
    # have: leaning on the ambient one makes this pass for a reason that is not the one
    # being tested, and pass differently on a machine where `gh` is missing entirely.
    brokenbin = tmp / "fakebin-broken"
    brokenbin.mkdir()
    (brokenbin / "gh").write_text("#!/bin/sh\nexit 1\n")
    (brokenbin / "gh").chmod(0o755)
    broken_env = {**env, "PATH": f"{brokenbin}{os.pathsep}{env.get('PATH', '')}"}
    code, out = run([hey, "pr-sync", "--project", "fixture"], broken_env, proj)
    check("pr-sync: a gh that cannot answer is reported, not read as zero markers",
          code == 0 and "could not read PRs via gh" in out, out)

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
