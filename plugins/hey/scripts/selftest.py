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
        fenced = False
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            low = line.lower()
            if any(d in low for d in DENIALS):
                continue
            for term in REMOVED_FEATURES:
                if term in low:
                    # Every skill's file is named SKILL.md, so the basename alone does not
                    # say which one failed.
                    where = path.relative_to(root)
                    out.append((f"{where}:{n} names `{term}`, which no script prints",
                                line.strip()))
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
        "tokens are charged to a project by path, not by string prefix":
            TOKEN_SCOPE_PROBE.format(here=str(HERE)),
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
        ([hey, "context", "--date", today], "context"),
        ([board, "collect", "--date", yesterday], "collect (yesterday)", "baseline"),
        ([board, "collect", "--date", today], "collect (today)"),
        ([hey, "snapshot"], "snapshot"),
        (["-c", probes.pop("stats")], "first record is a baseline"),
        # Re-collecting a day already behind a recorded one must not restate box state:
        # the ledger holds only today, so it would move the baseline and zero the newer day.
        ([board, "collect", "--date", two_days_ago], "collect: a past day keeps its hands off "
         "box state", "not collected - a later day is already recorded"),
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
                         ("docs claim no removed feature", removed_feature_checks)):
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
    check("add: a re-add with no --base reports the base it kept, not `unresolved`",
          code == 0 and "origin/trunk  (kept)" in out, out)

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
