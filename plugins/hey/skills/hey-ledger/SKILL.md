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
python3 "$HEY" add <root> --ledger-log <path>  # prose sections in a second file
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

python3 "$HEY" add <root> --ledger <path>  # when the ledger lives elsewhere
python3 "$HEY" add <root> --ledger-log <path>  # prose sections in a second file
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
  - [ ] remaining subitem `[AI 0.3]`
```

- **Estimates are read from the top-level item line only**, as `N MD / AI M`. Never put
  them on subitems
- **A subitem may claim a share of that estimate with `[AI n]`.** Every box otherwise
  carries an even slice, which is wrong exactly when it matters: the last subitem of a
  ten-box module is often the whole remaining job, and a tenth of the estimate both
  under-reports the day and makes `/wassup` split the number by hand. Claim only where the
  even split lies — annotating everything is the same work as estimating every subitem
  - **A closed box keeps its plain even share no matter what you write.** Only the open
    unclaimed boxes divide what is left. This is what makes it safe to annotate an item
    that is already half done: past snapshots have banked those closed boxes, and moving
    them would land as a lost day or a double-counted one
  - So the shares can total **more** than the item's estimate, and that is a finding, not
    a fault — it says the item was under-estimated by the difference. `doctor` reports it,
    and re-estimating the item with `/hey-tune` is what clears it. The same report catches
    `[AI 3]` typed for `[AI 0.3]`
- A box is `[ ]`, `[x]` or `[X]`. Anything else is not a box and is counted nowhere
- `MD` is a traditional man-day; `AI` is the man-day equivalent when using tooling.
  `AI 1.0` = one 8-hour day
- Item state comes from its subitems — all closed is `done`, some closed is `wip`,
  none is `todo`
- An item's key is `<phase>|<item name>`. **Renaming it breaks the link to past
  snapshots**, which is what carry-over and variance tracking rely on
  - The name stops at the first ` — ` or ` - `, and a trailing `(...)` is dropped: that
    bracket is nearly always a list of what the item covers, and dropping it is what turns
    a line into a name. The exception is a bracket that opens early in a sentence carrying
    on afterwards — there the tail is kept, because cutting would leave a fragment
- To mark something blocked, put a waiting word in the item text (`waiting`, `blocked`,
  `TBD`, `needs decision`, `pending`, or the Korean equivalents). Blocked items drop out
  of `/hey-run` candidates and get aged by `/wassup`. The word has to stand on its own —
  `depending` is not `pending`, and `대기업` is not `대기`
- **Name the branch an item's work lives on with `[branch <name>]`**, on the item line or
  on the subitem that becomes that branch. Without it the two halves never meet: `batch`
  knows the items, `dirty` and the card know the worktrees, and which item a loose branch
  belongs to survives only as prose in the work log. With it, `dirty` and the card's
  pick-up section name the item at risk instead of only a directory. `doctor` reports a
  marker whose branch git no longer has — a typo, or a branch deleted after merging
- **Date a blocker with `[since YYYY-MM-DD]`.** Age is the number that decides whether to
  go chase it, and `carryover` can only infer it after several days are on record — while a
  blocker is often older than the ledger. With a date the card shows the wait from day one.
  `hey.py blockers` lists every one of them, oldest first, which is what the card's
  `and N more` points at
  - **`[since unknown]` when the start cannot be found**, which is a different thing from
    writing nothing. It records that the question was asked and answered, so `blockers`
    stops counting it among the ones still to fill in. Prefer it to a guessed date: a date
    reads as evidence, and one nobody can source is worse than an admitted gap

## Aggregation

```bash
python3 "$HEY" progress --phases            # boxes, estimates, per-phase rows
python3 "$BOARD" collect                    # record today's closed/code/token totals
python3 "$BOARD" brief                      # morning card, one call
python3 "$BOARD" wrap                       # end-of-day card, one call
```

**There is no goal, streak, rank or board.** Days used to be scored against each other
here. Closed AI-days rest on estimates the tool cannot calibrate, and code and tokens
measure activity rather than accomplishment, so every one of those numbers dressed a
bookkeeping choice as a result. What is recorded is still recorded; nothing ranks it.

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
prints `baseline` instead of a number. Say so plainly on day one rather than presenting it
as a zero day. From the second record on the numbers are real.

## Language

English is the default. To switch, set `"lang": "ko"` in `~/.hey/config.json` or export
`HEY_LANG=ko`. Only user-facing text changes; stored data stays language-neutral.

## Card width

The card is 78 columns by default. `HEY_WIDTH` overrides that, clamped to 72-120, and
`doctor` prints the width in effect and where it came from.

That is the whole feature. If a card looks too narrow for the terminal, set `HEY_WIDTH`
in the `env` block of `~/.claude/settings.json` so it survives the session:

```json
"env": { "HEY_WIDTH": "120" }
```

**Do not try to measure the terminal.** Every probe available from here returns a
fallback rather than a reading -- `tput cols` and `shutil.get_terminal_size()` both say
`80` whatever the terminal is, `stty size` fails outright, and `$COLUMNS` reads `0`.
Asking the user to run one of those does not delegate the measurement: their shell in
this session is the same shell as yours, so the answer is the same fallback. The number
that actually matters is the width of the fenced block a card is pasted into, which is
not the terminal's width either. Nothing here depends on getting it right, so leave the
default alone unless the user asks.

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

**Headings are bold bracket labels, padded inside** — `**[ Pick up ]**`,
`**[ Today  8h = AI 1.0 ]**`, `**[ Blocked ]**` — never markdown headings. A `##` renders
as one more weight of bold in a terminal, which separates nothing next to a card built out
of box drawing. The brackets read as labels at a glance, the inner spaces keep the bracket
off the first word, and the bold carries the weight a heading would have given.

The asterisks are the markdown, not part of the label: what the reader sees is a bold
`[ Pick up ]`.

This holds for **every** block you write, not only the ones named in the examples. A
heading you invent for the occasion — `**[ Verified in code ]**`, `**[ What changed ]**` —
takes the same form.

**One divider, and only one.** A rule between the card and your prose marks where script
output ends and judgement begins. Do not put rules between the prose blocks — with three
blocks the labels already separate them, and more rules turn into the noise they were
meant to cut. Never draw a `─── heading ───` rule of your own: that is the card's shape,
and borrowing it blurs which lines a script produced.

```
🚧 막힌 것 6
   · 백엔드에 2xx 선언 추가 요청

────────────────────────────────────────────

**[ Pick up ]**
- lane-a-client-transport  keen-ios/client-transport
  The lane for today's item 1. Resume there

**[ Today  8h = AI 1.0 ]**
1. SamanthaClient transport      AI 0.5 (rough split)
2. codegen post-processing       AI 0.1 (rough split)
   AI 0.6 total. Item 3 skipped — its prerequisite is unfinished

**[ Blocked ]**
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
