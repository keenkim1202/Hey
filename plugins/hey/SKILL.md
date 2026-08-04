---
name: hey-ledger
description: The hey plugin's ledger conventions and shared commands. Use when registering a project, setting scope, creating a ledger, or when the user asks "set up hey", "register this project", "make me a ledger", or "how does hey work". Other hey skills read this to confirm the conventions.
---

# hey — ledger conventions

`hey` revolves around **one markdown ledger a human reads and edits**. No database, no
server. Scripts do all the counting; skills never count by hand.

## Paths

```bash
HEY="${CLAUDE_PLUGIN_ROOT}/scripts/hey.py"
BOARD="${CLAUDE_PLUGIN_ROOT}/scripts/board.py"
```

Config and history live in `~/.hey/`.

| File | What |
|---|---|
| `config.json` | registered projects and their base branch, default scope, weekly goal, language |
| `stats.jsonl` | daily snapshots. Ranking, burndown, carry-over and variance derive from these |

## Projects and scope

A user may run several projects at once, so commands take a **scope**.

```bash
python3 "$HEY" projects                    # registered projects, and which one you are in
python3 "$HEY" add <project root>          # register. Ledger defaults to <root>/TASKS.local.md
python3 "$HEY" add <root> --ledger <path>  # when the ledger lives elsewhere
python3 "$HEY" add <root> --base <branch>  # when the remote's default branch is not it
python3 "$HEY" scope current|all           # default scope
```

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
python3 "$HEY" progress --phases   # boxes, estimates, per-phase rows
python3 "$BOARD" collect           # record today's closed/code/token totals
python3 "$BOARD" brief             # morning card, one call
python3 "$BOARD" wrap              # end-of-day card, one call
```

Prefer `brief` and `wrap` over firing the individual commands. They exist because ten
separate calls cost ten round trips and ten blocks of output in the context window.

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
| `/hey-recap` | weekly review — burndown, carry-over, estimate variance |

## Never

- Never commit the ledger. It is local; `.git/info/exclude` is the default home for it
- Never create a second copy of the ledger inside a worktree. One registered path only
- Never write a number by eye. Copy the script output
- Never send user data anywhere. Ranking compares **only against the user's own past**
