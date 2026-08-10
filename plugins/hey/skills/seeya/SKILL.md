---
name: seeya
description: End-of-day wrap-up — log today into the ledger, record output (closed work, code, tokens), show the board, and preview tomorrow. Use on "seeya", "clocking off", "wrap up today", "end of day", "done for today".
---

# End-of-day wrap-up

The other half of `/wassup`. **Write** today down, **record** the output, preview tomorrow.

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
BOARD="$ROOT/scripts/board.py"
HEY="$ROOT/scripts/hey.py"
```

**Write first, then read.** The card reports today's work log and today's recorded
output, so a card printed before those exist reports neither — it falls back to raw
commits and shows no closed work at all. So the order below is: write the log, record the
output, and only then render the card.

The card is still **the first thing in your reply**. Generated last, shown first.

```bash
LC_TIME=C date "+%Y-%m-%d (%a)"
```

## 1. Write today into the work log

**Newest first.** Insert directly under the work-log heading. Never delete a past day.

```markdown
### 2026-08-05 (Wed)

- Wired the app root: OnboardingView + toast host in OrchardApp (#21)
- CartStore: loading state done. **3-stage error handler not started** — worktree `wt-checkout`,
  branch `feat/cart-state`, 2 commits unpushed
- Sheet source typo still unfixed (carried from yesterday)
```

- One line per bullet, five at most. Group beyond that
- **Keep a bullet under about 130 columns** — roughly 65 Korean characters, or 130 English
  ones. That is two folded lines on the narrowest card, and past it the card clips the
  bullet with a `…`. What gets thrown away is the end of the sentence, which is where the
  outcome usually is.
  - Budget for the narrow card even when yours is wide. A wide `HEY_WIDTH` holds far more,
    but the ledger is read again months later, on other machines, by `/wassup` and
    `/hey-recap` as much as by you. The entry outlives the terminal it was written on
  - **Split a long bullet into two rather than trimming words out of it.** Two facts stated
    plainly beat one sentence compressed until it has to be read twice. Compression that
    drops the subject, the number or the outcome has cost more than the clipping would
- **Number anything that shipped as a PR**
- **For unfinished work, say how far it got and what is left** — worktree, branch, whether
  it is committed
- **Never drop a carry-over.** If yesterday flagged it and today did not fix it, write it again
- If changes exist with no commit, or commits no remote has, **say so explicitly**. Losing the working
  tree loses the work

Today's notes are evidence too. Processed notes become results; unprocessed ones become
carry-overs. A note is not a log entry by itself.

Checking boxes and recomputing totals is **not this skill's job — hand that to
`/hey-sync`**. But `collect` reads box state, and it runs in the next step, so **if items
closed today, ask about `/hey-sync` now.** Afterwards the day is recorded and a late box
does not backfill into it.

## 2. Record the output

```bash
python3 "$BOARD" collect
```

Three things get counted:

| Metric | Source |
|---|---|
| closed | boxes closed in the ledger today, converted to AI-days |
| code | lines added and removed today, across every worktree of the project |
| tokens | Claude Code transcript usage today. Cache reads excluded |

`collect` writes the day into `~/.hey/stats.jsonl` and prints a four-line receipt — not a
board, and not the card's Output section:

```
[orchard] 2026-08-05 (Wed) recorded
  closed  0.85 AI-days
  code    +812 -392 (7 commits)
  tokens  1.9M (241 turns)
```

This receipt is confirmation for you, not output for the user; the card in step 3 carries
the same numbers in the shape they should read them. Report the figures **as printed** and
never recompute one.

**A closed value of 0 is a real 0.** It means no box closed today. If code went up
anyway, ask whether there is a subitem that should have been closed, or whether items are
sized too large. **Never substitute another metric to make the day look productive.**

## 3. One call for the card

```bash
python3 "$BOARD" wrap
```

Last, so it sees the log from step 1 and the record from step 2. `wrap` gathers today's
log, loose worktrees, today's notes, progress, the day's output and blockers in one pass.
Use it instead of the individual commands.

**Paste what it printed, verbatim, in a fenced code block, as the first thing in your
reply.** The user does not see tool output; a card you only summarise is a card they never
saw. Reproduce it exactly — no re-headed markdown, no rebuilt table, no dropped section.
Everything you write goes underneath it.

## 4. Preview tomorrow

- Read `Next up` as written. Never reorder it on a whim
- If today finished an item, show the next three after it
- Pull loose uncommitted or unpushed work out under **"clean up first"**
- Skip candidates blocked by a pending decision, and give the reason in one line

```
**[ Tomorrow  08-06 Thu ]**
1. OrchardClient — declare the 3 openapi packages + AuthMiddleware    AI 0.4
2. Domain/Data Account — country list and social login wiring            AI 0.7

**[ Clean up first ]**
- `wt-checkout` has 2 commits no remote has
```

Close with one sentence, grounded in the numbers that actually printed. There is no pace
or goal to fall behind of, so do not imply one — if the day closed nothing, say that, and
say which item was closest.

## Wording

**How you word what you add is in the `hey-wording` skill** — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never create a ledger inside a worktree. Never commit it
- Never answer without the card. Summarising it in prose is not showing it
- Never delete or merge past log days. The ledger accumulates
- Never write down work that did not happen. Only what git confirms
- Never check boxes or recount progress. That is `/hey-sync`
- Never commit, push or open a PR on your own. Report what is loose and let the user decide
- Never paper over a closed value of 0
