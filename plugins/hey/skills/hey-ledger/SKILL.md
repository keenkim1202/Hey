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
| `config.json` | registered projects with their base branch, default scope, language |
| `stats.jsonl` | daily snapshots. Burndown, carry-over and variance derive from these |

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
python3 "$HEY" draft-log --since 14        # work log drafted from git. Prints, never writes
```

**Use `--init` rather than copying the template yourself.** It refuses to register a
linked worktree and it puts the ledger at the registered path, which are the two rules
this file spends the most words on. Still ask the user before creating one.

### After `--init`, offer the draft

A ledger created today has no past, so the first `/wassup` reports nothing on a repository
that may hold months of work. `draft-log` reads the history and prints work-log entries in
the shape the ledger wants.

**It prints and stops. You paste it in — after the user has read it.** A commit subject
says what changed, not how far the work got or what is left, and those are the two things
the work log exists to carry. So:

1. Run it, show the output as it printed
2. Say plainly that this is drafted from commit subjects, not a record of what happened
3. Let the user cut, merge and correct. **Dates and commit hashes come from git — never
   edit those.** The prose is theirs
4. Only then write it into the work log, newest first

Do not run it unasked on a project that already has a work log. It answers the empty-file
problem, and appending a second version of days already written up is not that.

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

| Heading | Who reads or writes it |
|---|---|
| `## Notes` / `## 메모` | `/hey` inserts under today's date |
| `## Work log` / `## 작업 로그` | `/seeya` inserts under today's date |
| `### Next up` / `### 다음 착수 순서` | `/hey-sync` reorders; `/wassup` and `/seeya` read |
| `## Summary` / `## 진행 요약` | `/hey-sync` fills the totals |
| `## Blockers` / `## 블로커` | every unfinished item under it counts as blocked |

`doctor` checks the first four by name. The fifth is matched differently — anything under
a heading naming blockers is treated as one, wherever that heading sits.

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
- **To mark something blocked, write `[blocked]` on the item line** — or file it under a
  blocker heading, which does the same thing. Blocked items drop out of `/hey-run`
  candidates and get aged by `/wassup`. A waiting word in the prose does **not** block an
  item: text says `waiting on the API` all the time without meaning "hold this", and an
  item removed from the running by accident is one nothing offers you again. `doctor`
  points at lines that read as waiting and carry no marker
- **An item's name is half its key, so `[id <name>]` is what makes it safe to rename.**
  Without one, history is recorded against `<phase>|<title>`, and improving the wording of
  a line severs everything filed under it: carry-over restarts, `item` loses the record,
  and the day of the rename banks the item's closed boxes a second time. With one, the
  wording is free from then on. **It does not recover history already recorded under the
  old name** — once the rename has happened that name is gone from the ledger, and
  matching it back would be a guess. Add ids when you write the items, not when you are
  about to rename one. `doctor` names recorded keys no item answers to, so a severed
  history is reported rather than silent
- **Two items in one phase cannot share a title.** That is one key for both, and the
  recorded row keeps only one of them, so the other's closed work is never counted.
  `doctor` reports it as a failure; give one of them an `[id ...]`
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
| `/hey-sync` | update the ledger — checks, totals, next-up order |
| `/hey-run` | run a scoped loop of items and report a summary |
| `/next` | brief the single next item and ask whether to start it |
| `/hey-recap` | weekly review — burndown, carry-over, estimate variance |
| `/hey-standup` | three lines for a standup, no metrics |

## How to write what you add

**In the `hey-wording` skill.** It was moved there because nine skills referenced this
section alone, and reaching it meant loading everything else on this page.

## Never

- Never commit the ledger. It is local; `.git/info/exclude` is the default home for it
- Never create a second copy of the ledger inside a worktree. One registered path only
- Never write a number by eye. Copy the script output
- Never send user data anywhere. Nothing here reaches the network but `gh`, on request
