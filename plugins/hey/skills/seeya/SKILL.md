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

## 1. One call for the card

```bash
LC_TIME=C date "+%Y-%m-%d (%a)"
python3 "$BOARD" wrap
```

`wrap` gathers today's commits, loose worktrees, today's notes, progress, weekly pace,
the board and blockers in one pass. Use it instead of the individual commands.

**Then paste what it printed, verbatim, in a fenced code block, as the first thing in
your reply.** The user does not see tool output; a card you only summarise is a card they
never saw. Reproduce it exactly — no re-headed markdown, no rebuilt table, no dropped
section. Everything you write goes underneath it.

## 2. Write today into the work log

**Newest first.** Insert directly under the work-log heading. Never delete a past day.

```markdown
### 2026-08-05 (Wed)

- Wired the app root: OnboardingView + toast host in OrchardApp (#21)
- CartStore: loading state done. **3-stage error handler not started** — worktree `wt-checkout`,
  branch `feat/cart-state`, 2 commits, no PR
- Sheet source typo still unfixed (carried from yesterday)
```

- One line per bullet, five at most. Group beyond that
- **Number anything that shipped as a PR**
- **For unfinished work, say how far it got and what is left** — worktree, branch, whether
  it is committed
- **Never drop a carry-over.** If yesterday flagged it and today did not fix it, write it again
- If changes exist with no commit and no PR, **say so explicitly**. Losing the working
  tree loses the work

Today's notes are evidence too. Processed notes become results; unprocessed ones become
carry-overs. A note is not a log entry by itself.

Checking boxes and recomputing totals is **not this skill's job — hand that to
`/hey-sync`**. But `collect` reads box state, so if items closed today, ask whether to run
`/hey-sync` first.

## 3. Record the output

```bash
python3 "$BOARD" collect
```

Three things get counted:

| Metric | Source |
|---|---|
| closed | boxes closed in the ledger today, converted to AI-days |
| code | lines added and removed today, across every worktree of the project |
| tokens | Claude Code transcript usage today. Cache reads excluded |

`collect` prints the board again with today's row filled in. **Paste that block verbatim
too** — it is the one part of the wrap-up that did not exist when you printed the card.
Report the numbers **as printed**.

```
 Output  08-05 (Wed)
   closed   0.85 AI-days        best 1.20 on 08-01 (Fri)
   code     1,204 lines         best 3,918 lines on 08-01 (Fri)
   tokens   1.9M                best 4.2M on 07-30 (Thu)
```

**A closed value of 0 is a real 0.** It means no box closed today. If code went up
anyway, ask whether there is a subitem that should have been closed, or whether items are
sized too large. **Never substitute another metric to make the day look productive.**

## 4. Preview tomorrow

- Read `Next up` as written. Never reorder it on a whim
- If today finished an item, show the next three after it
- Pull loose uncommitted or unpushed work out under **"clean up first"**
- Skip candidates blocked by a pending decision, and give the reason in one line

```
Tomorrow (08-06 Thu)
1. OrchardClient — declare the 3 openapi packages + AuthMiddleware    AI 0.4
2. Domain/Data Account — country list and social login wiring            AI 0.7

Clean up first
- `wt-checkout` has 2 commits sitting with no PR
```

Close with one sentence, grounded in the numbers that actually printed. If the day was
behind, say it was behind.

## Wording

**How you word what you add is in the `hey-ledger` skill**, under "How to write what you add" — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never create a ledger inside a worktree. Never commit it
- Never answer without the card. Summarising it in prose is not showing it
- Never delete or merge past log days. The ledger accumulates
- Never write down work that did not happen. Only what git confirms
- Never check boxes or recount progress. That is `/hey-sync`
- Never commit, push or open a PR on your own. Report what is loose and let the user decide
- Never paper over a closed value of 0
