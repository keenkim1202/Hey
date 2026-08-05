---
name: wassup
description: Start-of-day briefing — what happened yesterday, today's load, where to pick up, and the output board. Use on "wassup", "what should I do today", "what did I do yesterday", "starting work", "morning". Read-only; never edits the ledger.
---

# Start-of-day briefing

Read-only. **Never edit the ledger.** `/seeya` and `/hey-sync` do the writing.

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
BOARD="$ROOT/scripts/board.py"
HEY="$ROOT/scripts/hey.py"
```

## 1. One call for the card

```bash
LC_TIME=C date "+%Y-%m-%d (%a)"
python3 "$BOARD" brief
```

`brief` gathers yesterday's log, loose worktrees, notes, progress, weekly pace, the
output board and blockers in a single pass. **Do not fire the individual commands
instead** — that costs ten round trips and floods the context for the same information.

**Then paste what it printed, verbatim, in a fenced code block, as the first thing in
your reply.** The user does not see tool output; if you summarise the card instead of
showing it, they never see the card at all — which is the one thing they asked for.
Reproduce it exactly: no re-headed markdown, no rebuilt table, no dropped section. Your
judgement goes underneath it, in step 2.

Read the ledger conventions from the `hey-ledger` skill if scope or paths are unclear.
With scope `all`, `brief` prints one card per project — paste each one.

Only reach for these when the card raises a specific question:

```bash
python3 "$HEY" context --date <yesterday>   # which files were touched, in detail
python3 "$HEY" carryover --days 3           # stuck for 3+ consecutive recorded days
python3 "$HEY" batch                        # what could run in parallel
```

`carryover` counts **recorded days, not calendar days** — a day nothing was recorded on is
not a gap. Report it the way the script phrases it.

## 2. What to write underneath the card

The card is the data, and it is already on screen. Add judgement below it — that is the
part a script cannot do.

### Yesterday

If the work log has no entry for the previous working day, the card falls back to
commits. Say which one you are looking at. **Never invent an entry that is not there.**
"Yesterday" means the **previous working day** — Friday if today is Monday.

### Where to pick up

If a worktree holds commits with no PR, or uncommitted files, **lead with that.** It is
the state most easily lost. Point at the directory and branch; do not switch to it.

### Today's load

- Take items in `Next up` order. **Never reorder it on a whim**
- Skip anything whose prerequisite is unfinished, and **say that you skipped it**
- Fill up to `AI 1.0` (8 hours) from the top, and stop short — leave room for
  verification and PR work
- For an item with subitems, take **the subitems you can actually close**, not the whole item
- If a subitem has no estimate, divide the parent's across its subitems and **say it is
  a rough split**
- Multiplier-1x work (external consoles, accounts, certificates, store review,
  reproducing against a live server) does not shrink with tooling. If it is mixed in, say so

```
[Today  8h = AI 1.0]
1. Wire the app root — OnboardingView + toast host in OrchardApp     AI 0.1
2. Extend CartStore — expose loading state, 3-stage error handler        AI 0.3 (rough split)
   Total AI 0.4. You are 0.2 behind the weekly pace, so there is room for one more.
```

### Blockers

Only if there are any. Give the **number of days** something has been stuck, and split
them into what you can unblock, what someone else must, and what needs a decision.

### One closing line

The board already printed a line with personality. Add at most one sentence of your own,
grounded in the numbers that actually printed. **If the user is behind, say so** and name
the one item that would recover it.

## Wording

**How you word what you add is in the `hey-ledger` skill**, under "How to write what you add" — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never edit the ledger. Brief only
- Never answer without the card. Summarising it in prose is not showing it
- Never guess the date. Call `date`
- Never recompute estimates. Use the ledger's numbers, and flag rough splits
- Never invent a log entry. Only report what git confirms
- Never load more than 8 hours into today
- Never switch branches, check out, or commit. Point at where to resume
