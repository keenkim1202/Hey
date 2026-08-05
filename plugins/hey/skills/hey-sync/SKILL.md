---
name: hey-sync
description: Bring the ledger up to date — check boxes, recount progress, append to the PR log, reorder what is next. Use on "update the ledger", "sync the checklist", "recount progress", "reflect current status", "pull in the merged PRs". Edits in place; never creates a new file.
---

# Updating the ledger

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
BOARD="$ROOT/scripts/board.py"
```

**Never rewrite the whole file.** Edit only the lines that changed. Estimates, unfinished
items, blocker tables and out-of-scope tables have reasoning behind them — never delete or
recompute them on a whim.

## 1. Find what landed

The "last synced" line at the top of the ledger holds the reference commit. Look past it.

```bash
cd <project root>
git fetch origin --quiet
git log --oneline <reference commit>..origin/<default branch>
gh pr list --state all --limit 30 --json number,title,createdAt,mergedAt,state \
  -q '.[] | [.number, (.createdAt|split("T")[0]), (if .mergedAt then (.mergedAt|split("T")[0]) else "-" end), .state, .title] | @tsv' | sort -n
```

**Never trust a PR title.** One titled "module scaffold" may be two lines of
`Placeholder.swift`. Run `git show --stat <commit>` and see what actually landed.

**Confirm completion in the code**, by file listing or symbol presence — not by title.

If PR bodies carry `closes <item key>` markers, collect them:

```bash
python3 "$HEY" pr-sync
```

That command **only finds them; it never checks anything off.** Verify in the code first.

## 2. Append to the PR log

The PR log is a ledger. **Never delete or compress rows; append.**

- Add a row for a new PR; fill the merge date once merged. Dates as `MM-DD`
- Leave an unmerged one as `-` and fill it on the next run
- The impact column says **which phase and which item moved**, not a restatement of the title
- With squash merges the branch commits never appear on the default branch. Do not judge by
  `git branch --merged`; use `gh pr view <n> --json state`

## 3. Check boxes

- **Only mark `[x]` what is completely finished**
- **For partial work, leave the parent alone and add subitems.** Keep the PR number

  ```markdown
  - [ ] **Country selection** — ... — 3 MD / AI 0.5
    - [x] screen and view model (#17). State field only for US, confirm gating
    - [ ] country list from the server API (currently a 27-entry stub)
  ```

- Where plan and reality diverge, **write the real name**. If the planned `generate.sh` is
  actually `generate-api-client.sh`, say so
- **Do not rename items casually.** The key is `<phase>|<name>`, so a rename severs the
  link to past snapshots. If it must change, tell the user
- Change an estimate **only if the scope actually changed** — and that belongs to `/hey-tune`

## 4. Recount

Run this **after** all box edits. The wrong order bakes in stale numbers.

```bash
python3 "$HEY" progress --phases
```

Put the output in three places. **Never count by hand.**

| Output | Goes to |
|---|---|
| `checklist N/M boxes (P%)` | the top `Progress (boxes)` line |
| `effort closed / in progress / left` | the top `Progress (estimate)` line |
| per-phase rows | the summary table's item, done and progress columns, plus the total row |

- The summary's done column shows partials as `0 (3 partial)`. Never inflate it
- If item sums and table totals disagree, **say which side is rounded** and leave the
  estimates alone

## 5. Reorder what is next

```bash
python3 "$HEY" next
python3 "$HEY" carryover --days 3
python3 "$HEY" dirty
```

Order on these four, **one sentence of reasoning each**:

- The order an architecture doc or plan already prescribes
- Prerequisites — what must finish before this can start
- Work sitting uncommitted or unpushed — easily lost, so clean it up first
- Carried-over items — how many days they have been stuck

Where the prescribed order and reality diverge, **write that down.** A skipped item does
not disappear.

## 6. Record output last

```bash
python3 "$BOARD" collect
```

Run it after the checks land, or today's closed work will be undercounted. If `/seeya`
comes next, one `collect` between the two is enough.

## Wording

**How you word what you add is in the `hey-ledger` skill**, under "How to write what you add" — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never create a ledger inside a worktree
- Never rewrite the file wholesale
- Never commit the ledger
- Never mark `[x]` without verifying. A `pr-sync` marker alone is not verification
- Never recompute estimates without a reason
- Never write a total by eye
- Never delete or merge past log and PR rows
