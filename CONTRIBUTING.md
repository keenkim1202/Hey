# Contributing

Thanks for looking. This is a small plugin — pure Python and the standard library, no
dependencies, no build step.

## The gate

Everything is checked by one script. Both languages have to pass:

```bash
python3 plugins/hey/scripts/selftest.py
python3 plugins/hey/scripts/selftest.py --lang ko
```

About thirteen seconds each. CI runs exactly these two commands and nothing else, across
ubuntu (python 3.9 and 3.13) and macos (3.13).

Your local run covers one of those three. It is the fastest way to find a mistake, but it
is not the matrix: **Python 3.9 is the floor**, and 3.10+ syntax passes happily on a newer
interpreter and then fails in CI. No `match`, no `X | Y` in a runtime position. Annotations
are free — every module already has `from __future__ import annotations`.

If you have a 3.9 to hand, one more run closes most of the gap:

```bash
python3.9 plugins/hey/scripts/selftest.py
```

Otherwise `python3 -m py_compile plugins/hey/scripts/*.py` under 3.9 catches the syntax
half of it, and CI catches the rest — a red matrix job is a normal part of a pull request,
not a failure of etiquette.

## Adding a test

Confirm it **fails on the unfixed code before you trust it.** Revert the change, run the
self-test, see `FAIL`, then restore. A check that cannot fail is not a check, and this
suite has caught several of its own that could not.

Most tests are entries in the `cases` list, or a `*_PROBE` string run as a subprocess
against a throwaway fixture. Nothing touches real state: `HEY_HOME`, `HEY_TRANSCRIPTS` and
the project all live in a temp directory, and every `HEY_*` from your shell is stripped so
your settings cannot change what is tested.

## Things that will catch you out

- **A new `[marker]` on an item line must also be added to `Ledger.MARKERS`.** That regex
  strips markers back out of the title, and the title is half an item's key — miss it and
  the item is silently renamed, which severs everything recorded against it.
- **`strings.py` holds every user-facing string in English and Korean.** Add to both. The
  self-test statically compares keys and `{placeholder}` names across languages, because a
  key that exists in one language raises `KeyError` only for the user who set that one.
- Mechanical errors stay in English so they can be searched for. Only the cards are
  localised.
- **Numbers are never written by hand.** If a skill needs a figure, a script computes it.
  A skill that counts something itself is a bug, not a shortcut.

## What the scripts are for

- `hey.py` — parses the ledger, aggregates, records. Every number originates here.
- `board.py` — the daily record and the two cards.
- `strings.py` — user-facing text, per language.
- `selftest.py` — the gate.

Skills under `plugins/hey/skills/` are markdown. A skill body is loaded in full when it
fires, so it is worth keeping short: if a skill needs one section of another skill, that
file is cut in the wrong place and should be split.

## Commits and pull requests

Explain **why** in the commit message — what was wrong, and what the change makes true.
The diff already shows what changed.

Open an issue first for anything that changes behaviour a ledger depends on: the marker
syntax, the recorded shape of `stats.jsonl`, or what a command prints.

## Licence

By contributing you agree that your contribution is licensed under the Apache License 2.0,
the same as the rest of the project.
