<div align="center">

```
        ─── hey ─────────────────────────  2026-08-05 (Wed)

         Yesterday   CSV import pipeline merged (#20)
         Pick up     wt-checkout  1 commit(s), no PR
         Checklist   36 / 155 boxes    ████░░░░░░░░░░░░░░
         Today       AI 0.4 of 1.0     two subitems you can close
```

# hey

**Run your work off one markdown ledger.** Checklist, estimates, a morning briefing
and an end-of-day record — printed from a file you can read and edit by hand.

[![license](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
[![stars](https://img.shields.io/github/stars/keenkim1202/Hey?style=flat-square&color=e3b341)](https://github.com/keenkim1202/Hey/stargazers)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-d97757?style=flat-square)](https://code.claude.com/docs/en/plugins)
[![python](https://img.shields.io/badge/python-3.9%2B-3776ab?style=flat-square)](https://www.python.org/)
[![no server](https://img.shields.io/badge/data-stays%20local-2ea043?style=flat-square)](#where-data-lives)

</div>

---

## Before / after

**Before.** It is Wednesday morning. What did you do on Tuesday? You scroll `git log`,
open three worktrees to find the one with uncommitted changes, guess how much of the
sprint is left, and start on whatever is loudest.

**After.** One command, one card.

```
─── orchard ───────────────────────────────────── 2026-08-05 (Wed)

 Yesterday  08-04 (Tue)
   · CSV import pipeline merged (#20). 603 rows mapped to the catalog
   · Currency entity merged (#19)

 Pick up here
   · wt-checkout  feat/csv-import  1 commit(s), no PR
       Modules/Catalog/Sources/CsvImporter.swift

 Checklist   36 / 155 boxes closed      (23.2%)  ████░░░░░░░░░░░░░░
 Effort      0.0 / 81.25 AI-days closed 81.25 left · 7.5 in progress · 1 AI-day = 8h
 This week   0.0 / 5.0 AI-days          3.0 behind pace (Mon-Fri)

 Output  08-04 (Tue)
   closed   0.00 AI-days        best 1.64 on 07-29 (Wed)
   code     38,330 lines        best 38,330 lines on 08-04 (Tue)
   tokens   1.9M                best 4.2M on 07-30 (Thu)
```

The numbers come from scripts, not from the model reading and adding things up. The
judgement on top of them — what to pick up, what to skip, what is actually blocked —
is the part a script cannot do.

---

## How it works

Three pieces, and only one of them is yours to maintain.

**The ledger** is one markdown file in your project, `TASKS.local.md`. Checkboxes,
estimates, a work log, a notes section. You read and edit it like any other file. It is
never committed.

```markdown
- [ ] **Social login, 4 providers** — Apple / Google / GitHub / Microsoft — 6 MD / AI 3.4
  - [x] Apple Sign In
  - [ ] Google Sign In
```

**The scripts** parse it and do every calculation — box counts, effort totals, daily
output, ranking, burndown, estimate variance. `hey.py` and `board.py`, python and the
standard library, nothing else.

**The skills** are the part the model reads. They say which script to call and how to
read the result, and they are strict about what the model may not do: never write a
number by eye, never invent a log entry, never commit anything on your behalf.

That split is the whole design. Scripts are exact, so the model is left to do the thing
it is good at.

---

## Install

In a terminal, one line:

```bash
claude plugin marketplace add keenkim1202/Hey && claude plugin install hey@hey
```

Or from inside Claude Code:

```
/plugin marketplace add keenkim1202/Hey
/plugin install hey@hey
```

`hey@hey` reads oddly but is right: it is `<plugin>@<marketplace>`, and both are named
`hey`. The first command registers the catalog, the second installs from it — installing
needs the catalog, so the order matters. Re-running either is safe.

Then register a project and get a ledger:

```
/hey-ledger      # register this project, create the ledger
/hey-plan        # paste a spec or task list; get a checklist with estimates
/wassup          # tomorrow morning, start here
```

To develop against a local checkout, register the path instead:

```bash
claude plugin marketplace add /path/to/hey && claude plugin install hey@hey
```

---

## Commands

| Command | What |
|---|---|
| `/hey-ledger` | register a project, set the scope, create a ledger. The conventions the rest read |
| `/wassup` | start of day — yesterday, today's load, where to pick up, the board |
| `/seeya` | end of day — log today, record output, preview tomorrow |
| `/hey <text>` | capture a note now. Date, branch and commit attach automatically |
| `/hey-plan` | turn a spec into a checklist with MD and AI estimates |
| `/hey-tune` | adjust estimates, recording why in the ledger |
| `/hey-sync` | update the ledger — checks, totals, PR log, next-up order |
| `/hey-run` | run a scoped loop of items and report a summary; recommends parallel work |
| `/hey-recap` | weekly review — burndown, carry-over, estimate variance |

One session-start hook. It speaks **only when work is sitting uncommitted with no PR** —
the state that is easiest to lose. Otherwise it says nothing at all.

---

## Estimates

Two numbers per item, because one is not enough to argue with.

| | Meaning |
|---|---|
| `MD` | a traditional man-day, without tooling |
| `AI` | the man-day equivalent with tooling. `AI 1.0` is one 8-hour day |

`/hey-plan` splits an item into code work and human-gated work and applies multipliers
separately, because they do not shrink at the same rate.

| Kind | Multiplier |
|---|---|
| Scaffolding, mapping, boilerplate | 6-7x |
| UI with a settled spec | 5-6x |
| Screens wired to an API | 3-4x |
| State machines, concurrency | 1.5-3x |
| **Human-gated** — consoles, accounts, certificates, store review | **1x** |

The last row is the point. External waiting does not get faster with better tooling, so
an estimate that folds it into the rest is wrong in a way that compounds. Every total
reports what share of it sits at 1x.

---

## Metrics

`/seeya` records three things once a day.

| Metric | Source |
|---|---|
| closed | boxes closed in the ledger that day, converted to AI-days |
| code | lines added and removed, across every worktree of the project |
| tokens | Claude Code transcript usage, across every worktree. Cache reads excluded |

Ranking compares **against your own past records**. No user data is sent or received.

```
Today  code 38,330 lines    #1 of last 5 days

 1  08-04 (Tue)  ████████████████████  38,330 lines  peak
 2  08-03 (Mon)  ██████▋               12,846 lines
 3  07-31 (Fri)  ████▉                 9,356 lines
    avg          ██████▌               12,553 lines

New high. Turns out today's output wasn't slop.  (38,330 lines)
```

The very first record is a **baseline** and carries no closed figure. There is no earlier
day to compare it against, so counting its closed boxes would credit work finished before
recording began, and that number would then be the peak every later day is measured
against. Code and token counts are exact from day one.

Where the three metrics disagree, that is information. High code and token counts with
zero closed work means the work happened but no item closed — either items are sized too
large, or boxes are not being checked. `/seeya` asks which instead of quietly picking the
flattering number.

---

## Things to know

- **Closed work cannot be backfilled.** The ledger holds only its current state, so daily
  output exists from the day recording starts. Code and token counts do backfill, since git
  and the transcripts keep history. For the same reason, estimate variance only measures
  items seen unfinished before they closed
- **Unpushed commits are measured against the remote's default branch**, detected at
  registration and stored as `base`. When it cannot be resolved, the report says so instead
  of printing zero — a wrong base makes the comparison fail silently, which is how work
  that never left your machine goes unnoticed
- **Item names are keys.** Past snapshots link through `<phase>|<item name>`, so renaming an
  item severs carry-over and variance tracking
- **Estimates go on the top-level item line only**, as `N MD / AI M`. Never on subitems
- A box is `[ ]`, `[x]` or `[X]`. Anything else is not a box and is counted nowhere
- Several projects can run at once. `scope current` is the one you are standing in,
  `scope all` is every registered project
- Ledger sections and blocker keywords are matched against **every language alias**, so an
  English ledger and a Korean one both work with no configuration

---

## Language

English by default. Set `"lang": "ko"` in `~/.hey/config.json`, or export `HEY_LANG=ko`, to
switch the interface. Only user-facing text changes; stored data stays language-neutral.
Korean documentation lives in [docs/ko/README.ko.md](docs/ko/README.ko.md).

A new language pack goes in `plugins/hey/scripts/strings.py`. Add a key for the language to
each table keyed by language — `WEEKDAYS`, `METRIC_LABELS`, `UNITS`, `CARD`, `FLAIR`,
`STREAK`, `STATE_LABELS`, `BLOCKER_WORDS`, `BLOCKER_SECTIONS` — and append the translated
heading to each row of `SECTIONS`, which is keyed by section instead. If the language has no
word boundary the way Hangul does not, extend `_bounded` alongside it. The tone rules for
the personality lines are documented at the top of the file.

---

## Where data lives

```
~/.hey/config.json          registered projects and their base branch, default scope,
                            weekly goal, language
~/.hey/stats.jsonl          daily snapshots. Ranking, burndown, carry-over, variance
<project>/TASKS.local.md    the ledger
```

Nothing else, and nothing leaves the machine. A project's `base` is filled in when you
register it; to change it, edit `config.json` or re-register with `--base <branch>`.

---

## Development

```
plugins/hey/
├── SKILL.md              ledger conventions; the other skills read this
├── skills/               one directory per skill
├── commands/hey.md       /hey, the note capture command
├── scripts/
│   ├── hey.py            ledger parsing, aggregation, recording
│   ├── board.py          daily output, leaderboards, the two cards
│   ├── strings.py        every user-facing string, per language
│   └── selftest.py       every command against a throwaway fixture
├── hooks/                the session-start hook
└── templates/            LEDGER.md, LEDGER.ko.md
```

The self-test builds a fixture project with a git remote, a linked worktree and a seeded
ledger, then runs every command against it. Nothing real is touched — `HEY_HOME` and the
transcript directory both point into a temp directory.

```bash
python3 plugins/hey/scripts/selftest.py
python3 plugins/hey/scripts/selftest.py --lang ko
```

Validate the manifests before pushing:

```bash
claude plugin validate .
claude plugin validate ./plugins/hey
```

**Requirements:** python3 3.9 or newer (which macOS ships) and git. `gh` is used only for
the PR log; without it that step is skipped.

---

## FAQ

**Does anything leave my machine?**
No. There is no server and no telemetry. Ranking compares today against your own past
records in `~/.hey/stats.jsonl`.

**Do I have to commit the ledger?**
No, and you should not. It is per-user local state. `.git/info/exclude` is the usual home
for it.

**Why two estimate numbers instead of one?**
Because `MD` is the number other people already think in, and `AI` is the number you
actually deliver against. Keeping both makes a schedule negotiable — you can point at
which multiplier you disagree with.

**Why does the closed metric say 0 when I clearly worked all day?**
Because no checkbox closed. That is usually items sized too large to close in a day. The
metric is deliberately not smoothed; a zero is reported as a zero.

**Can the model just edit my ledger however it likes?**
The skills forbid it. Recaps and briefings are read-only, `/hey-sync` edits only the lines
that changed, estimates are never recomputed without a reason, and nothing is committed or
pushed on your behalf.

**Does it work with a monorepo, or several projects at once?**
Yes. Register each project and set `scope all` for a morning sweep across them.

---

## License

MIT. See [LICENSE](LICENSE).
