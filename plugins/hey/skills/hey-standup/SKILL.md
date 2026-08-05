---
name: hey-standup
description: Three lines for a standup, built from the ledger - what landed, what is next, what is blocked. Use on "standup", "daily", "what do I say in standup", "status update", "write my scrum update". Read-only; never edits the ledger.
---

# Standup lines

Read-only. **Never edit the ledger.** This produces text a person will paste into a chat
or say out loud, so it is short and it contains no numbers that were not printed.

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
BOARD="$ROOT/scripts/board.py"
```

## 1. Gather

```bash
LC_TIME=C date "+%Y-%m-%d (%a)"
python3 "$BOARD" brief
```

`brief` already carries the previous working day's log, loose worktrees, next-up order and
blockers. **Do not fire the individual commands** unless the card raises a question, in
which case:

```bash
python3 "$HEY" log --limit 2                # the exact log wording
python3 "$HEY" carryover --days 2           # what has been open across records
python3 "$HEY" item "<phase>|<name>"        # one item's history, when asked why
```

Here the card is a **source, not output** — the one exception to the print-the-card rule
in `hey-ledger`. `/wassup` and `/seeya` paste it; a standup does not. What leaves this
skill is three lines a person can say out loud.

Read the ledger conventions from the `hey-ledger` skill if scope or paths are unclear.

## 2. Three lines, in this order

```
Yesterday   CSV import pipeline merged (#20). Currency entity merged (#19)
Today       Finish the Google provider, then the country list from the server
Blocked     Server header contract undecided - waiting on backend since Monday
```

- **Yesterday** means the previous working day. Friday if today is Monday. Say which day
  you are reporting on if it is not literally yesterday
- **Today** comes from `Next up` order, trimmed to what fits the hours left. Never
  reorder it to make the line sound better
- **Blocked** appears only if something is. Name **who** has to clear it and **how long**
  it has been open, in records, not guessed calendar days
- Drop the Blocked line entirely when there is nothing blocked. An empty line invites a
  question that has no answer

## 3. What not to put in

- **No metrics.** Closed AI-days, code volume and token counts belong in `/hey-recap`, not
  a standup. Nobody in a standup can act on them
- **No percentages.** "23% of the checklist" tells the room nothing about today
- **No estimates**, unless someone asked for a date. `AI 0.4` is internal shorthand
- **No apology and no padding.** If yesterday produced nothing, the line is one sentence
  saying what stopped it

## 4. Uncommitted work is a standup item

If a worktree holds commits with no PR, that belongs on the Today line, first. It is the
thing most likely to surprise someone else. Point at the branch; do not push it.

## Wording

**How you word what you add is in the `hey-ledger` skill**, under "How to write what you add" — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never edit the ledger, check a box, or commit anything
- Never invent an accomplishment the log does not contain. If the log is empty, say the
  log is empty and report what git shows instead
- Never turn a carry-over into a fresh accomplishment by rewording it
- Never exceed three lines unless the user asks for more
