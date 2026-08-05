---
name: hey-ledger
description: The hey plugin's ledger conventions and shared commands. Use when registering a project, setting scope, creating a ledger, or when the user asks "set up hey", "register this project", "make me a ledger", or "how does hey work". Other hey skills read this to confirm the conventions.
---

# hey — ledger conventions

`hey` revolves around **one markdown ledger a human reads and edits**. No database, no
server. Scripts do all the counting; skills never count by hand.

## Paths

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
BOARD="$ROOT/scripts/board.py"
```

Config and history live in `~/.hey/`.

| File | What |
|---|---|
| `config.json` | registered projects with their base branch and goals, default scope, language |
| `stats.jsonl` | daily snapshots. Ranking, burndown, carry-over and variance derive from these |

## Projects and scope

A user may run several projects at once, so commands take a **scope**.

```bash
python3 "$HEY" projects                    # registered projects, and which one you are in
python3 "$HEY" add <project root>          # register. Ledger defaults to <root>/TASKS.local.md
python3 "$HEY" add <root> --init           # register and create the ledger from the template
python3 "$HEY" add <root> --ledger <path>  # when the ledger lives elsewhere
python3 "$HEY" add <root> --base <branch>  # when the remote's default branch is not it
python3 "$HEY" remove <name>               # unregister. Ledger and history are kept
python3 "$HEY" scope current|all           # default scope
python3 "$HEY" doctor                      # what is misconfigured, all of it at once
```

**Use `--init` rather than copying the template yourself.** It refuses to register a
linked worktree and it puts the ledger at the registered path, which are the two rules
this file spends the most words on. Still ask the user before creating one.

When something reports nothing and you cannot see why, run `doctor` before guessing. It
checks the base branch, the ledger's headings, estimates, and the history file, and every
one of those failures otherwise shows up as an empty answer rather than an error.

- `current` — the project you are standing in. **Resolves to the main repo root even
  from inside a linked git worktree**
- `all` — every registered project. For a morning sweep across several
- Any command takes `--scope all` or `--project <name>` to override for that call

`add` also records a **base branch** — what unpushed commits are measured against. It is
read from the remote's own default branch, and stored as `base` in `config.json`. If it
cannot be resolved, `dirty` says unpushed commits were not checked rather than reporting
zero. **Never read that message as "nothing to push"**; it means tell the user to set
`base`.

If the cwd is not a registered project the command says so and stops. **Never register
one silently.** Ask, and if the ledger is missing, ask before copying
`templates/LEDGER.md` into place.

## Ledger structure

`templates/LEDGER.md` is the reference. Five sections are found by name, and **each name
is matched against every language alias**, so Korean and English ledgers both work:

| Section (aliases) | Written by |
|---|---|
| `## Notes` / `## 메모` | `/hey` inserts under today's date |
| `## PR log` / `## PR 기록` | `/hey-sync` appends rows |
| `## Work log` / `## 작업 로그` | `/seeya` inserts under today's date |
| `### Next up` / `### 다음 착수 순서` | `/hey-sync` reorders; `/wassup` and `/seeya` read |
| `## Summary` / `## 진행 요약` | `/hey-sync` fills the totals |

Checklist item convention:

```markdown
- [ ] **Item name** — description — 3 MD / AI 0.4
  - [x] finished subitem (#12)
  - [ ] remaining subitem
```

- **Estimates are read from the top-level item line only**, as `N MD / AI M`. Never put
  them on subitems
- A box is `[ ]`, `[x]` or `[X]`. Anything else is not a box and is counted nowhere
- `MD` is a traditional man-day; `AI` is the man-day equivalent when using tooling.
  `AI 1.0` = one 8-hour day
- Item state comes from its subitems — all closed is `done`, some closed is `wip`,
  none is `todo`
- An item's key is `<phase>|<item name>`. **Renaming it breaks the link to past
  snapshots**, which is what carry-over and variance tracking rely on
- To mark something blocked, put a waiting word in the item text (`waiting`, `blocked`,
  `TBD`, `needs decision`, `pending`, or the Korean equivalents). Blocked items drop out
  of `/hey-run` candidates and get aged by `/wassup`. The word has to stand on its own —
  `depending` is not `pending`, and `대기업` is not `대기`

## Aggregation

```bash
python3 "$HEY" progress --phases            # boxes, estimates, per-phase rows
python3 "$BOARD" collect                    # record today's closed/code/token totals
python3 "$BOARD" brief                      # morning card, one call
python3 "$BOARD" wrap                       # end-of-day card, one call
python3 "$BOARD" goal --set 5.0 --daily 0.4 # this project's weekly and daily targets
```

**Goals belong to a project, not to the machine.** `goal --set` writes to whatever is in
scope, so with several projects registered set each one separately rather than sharing one
number across all of them.

Prefer `brief` and `wrap` over firing the individual commands. They exist because ten
separate calls cost ten round trips and ten blocks of output in the context window.

```bash
python3 "$HEY" item "<phase>|<name>"   # one item's history: when it opened, what changed
```

`item` accepts any part of a key. Reach for it when the question is "what happened to this
one" — `carryover` says what is stuck and `variance` says how far off the estimates were,
neither answers that.

**Closed work is not backfillable.** The ledger only holds its current state, so daily
output only exists from the day `collect` starts running. Passing a past `--date` still
gives exact code and token numbers from git and the transcripts, but **closed work prints
as 0**. Do not hide that from the user.

The **first record of a project is a baseline** and carries no closed figure at all — it
prints `baseline` instead of a number, and it is excluded from ranking and streaks. Say so
plainly on day one rather than presenting it as a zero day. From the second record on the
numbers are real.

## Language

English is the default. To switch, set `"lang": "ko"` in `~/.hey/config.json` or export
`HEY_LANG=ko`. Only user-facing text changes; stored data stays language-neutral.

## Card width

The card is 78 columns by default, and `HEY_WIDTH` widens it to at most 120. On a wide
terminal that is worth setting: lines fold less, and fewer descriptions get clipped to a
`…`. `doctor` prints the width in effect and where it came from.

**You cannot measure the terminal for them.** Your shell has no tty, so every probe fails,
each in its own misleading way:

| Probe | What you get |
|---|---|
| `tput cols` | `80` — its fallback, whatever the terminal really is |
| `shutil.get_terminal_size()` | `columns=80` — the same fallback |
| `stty size` | fails with `stdin isn't a terminal`, exit 1 |
| `echo $COLUMNS` | `0` — a number, and a useless one |

`sys.stdout.isatty()` is `False`, and that is the one honest answer in the set: it says
there is nothing here to measure. A user running `tput cols` themselves in the session hits
the same fallback, so their answer is no better than yours.

Do not set a width off any of those numbers, and note that they mislead in *different*
directions. A command that errors looks broken, which makes the one answering `80` look
like it measured something. `0` looks like a value you could pass straight through, and
`HEY_WIDTH=0` is accepted — `isdigit()` takes it, then the floor clamps it to 72.

Measure it by asking. Print a ruler in a fenced block and have the user read it back:

```bash
python3 -c "
N=240
print(''.join(str(t*10).rjust(10) for t in range(1, N//10+1)))
print(''.join(str((i+1)%10) for i in range(N)))
"
```

Ask which number is the last one visible before the line wraps. That measures the width
**inside a fenced code block**, which is the only number that matters — a card you paste
into the reply is bounded by the block, not by the terminal. Then set `HEY_WIDTH` a little
under what they report, to leave room for the margin, and put it in the `env` block of
`~/.claude/settings.json` so it survives the session:

```json
"env": { "HEY_WIDTH": "120" }
```

Setting `HEY_WIDTH` turns terminal detection off, so a user who often resizes is better
off leaving it unset and letting the card measure a real terminal on its own.

## Skill map

| Skill | When |
|---|---|
| `/hey-ledger` | this file — register a project, set scope, create a ledger |
| `/wassup` | start of day — yesterday, today's load, where to pick up, board |
| `/seeya` | end of day — log today, record output, preview tomorrow |
| `/hey` | capture a note right now, with date, branch and files attached |
| `/hey-plan` | turn a spec into a checklist with MD and AI estimates |
| `/hey-tune` | adjust estimates with the user, recording why |
| `/hey-sync` | update the ledger — checks, totals, PR log, next-up order |
| `/hey-run` | run a scoped loop of items and report a summary |
| `/next` | brief the single next item and ask whether to start it |
| `/hey-recap` | weekly review — burndown, carry-over, estimate variance |
| `/hey-standup` | three lines for a standup, no metrics |

## How to write what you add

The card is the data. Everything you write around it is read by a person who is about to
start or finish a day's work, so it reads like a colleague talking, not like a report.

**Print the card before you write anything.** Script output is not visible to the user —
in most harnesses a tool result is shown to the model and not to the person. A card that
is only summarised is a card the user never saw. So paste the block verbatim, inside a
fenced code block, above your prose. Never paraphrase it into markdown headings, never
rebuild it as a table, never trim a section because it looks redundant. The box drawing,
the bar glyphs and the column alignment are the format; re-typing them by hand breaks
them. Your writing goes **under** the card, never in place of it.

**Shape.** At most three blocks. Each is a one-line heading and two to four bullets. One
closing sentence, and only if it says something the numbers do not.

**Headings are bracket labels** — `[Pick up]`, `[Today  8h = AI 1.0]`, `[Blocked]` — not
markdown headings. A `##` renders as one more weight of bold in a terminal, which does not
separate anything next to a card built out of box drawing. Brackets read as labels at a
glance and stay out of the card's way.

**One divider, and only one.** A rule between the card and your prose marks where script
output ends and judgement begins. Do not put rules between the prose blocks — with three
blocks the labels already separate them, and more rules turn into the noise they were
meant to cut. Never draw a `─── heading ───` rule of your own: that is the card's shape,
and borrowing it blurs which lines a script produced.

```
🚧 막힌 것 6
   · 백엔드에 2xx 선언 추가 요청

────────────────────────────────────────────

[Pick up]
- lane-a-client-transport  keen-ios/client-transport
  The lane for today's item 1. Resume there

[Today  8h = AI 1.0]
1. SamanthaClient transport      AI 0.5 (rough split)
2. codegen post-processing       AI 0.1 (rough split)
   AI 0.6 total. Item 3 skipped — its prerequisite is unfinished

[Blocked]
- Blocks item 1 today: X-Region undecided
- Someone else must clear: 2xx on 34 ops, code enum, prod host
```

**Words to drop.** These are the tells that something was generated rather than said:

- `살펴보겠습니다` `요약하면` `핵심은` `참고로` — presentation filler
- `~할 수 있을 것 같습니다` — stacked hedging. If it is unknown, say it is unknown, once
- `확인 필요.` `진행 예정.` — a noun standing in for a sentence. End on a verb
- `좋습니다` `훌륭합니다` `잘 진행되고 있습니다` — praise. The user can see the numbers
- `또한` `더불어` `나아가` in consecutive sentences

**Words to use.** Short declaratives, one fact each. Verbs over nouns. The user's own
vocabulary from the ledger, unparaphrased — renaming their item makes it unsearchable. Bad
news first, with no cushion in front of it.

**Numbers** come from the script output, copied. Never recomputed, never rounded by eye.

**Emoji** belong to the card, which uses a fixed set of seven as section markers. Do not
add your own, do not put one inside a line that has to line up with the line above it, and
do not decorate your prose with them — the card already carries the scanning aids.

## Never

- Never commit the ledger. It is local; `.git/info/exclude` is the default home for it
- Never create a second copy of the ledger inside a worktree. One registered path only
- Never write a number by eye. Copy the script output
- Never send user data anywhere. Ranking compares **only against the user's own past**
