---
name: hey-tune
description: Adjust ledger estimates together with the user. Use on "this is 5 days not 3", "re-estimate this", "bump this item", "check my estimate variance", "it actually took longer". Always records why the number changed.
---

# Tuning estimates

**The user owns the final number.** This skill gathers the evidence, applies the decision
to the ledger, and records why it changed.

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
BOARD="$ROOT/scripts/board.py"
```

## 1. Show the measurements first

Never tune on instinct. Look at how finished items compared to their estimates.

```bash
python3 "$HEY" variance
python3 "$HEY" carryover --days 3
python3 "$BOARD" show --window 30
```

`variance` measures business days from an item first starting to finishing, against its
estimate.

```
P0|codegen pipeline        est AI 0.4 -> actual 3d  x7.5
P11|locale resolution      est AI 0.6 -> actual 4d  x6.7
mean multiplier x7.1 — multiply estimates by this to land nearer reality (estimates were optimistic)
```

**Do not take that multiplier at face value.** It assumes one item at a time, so parallel
work inflates it. Say so, and ask what share of those days actually went to the item.

## 2. Classify what changed

Every tuning request is one of three things. **Decide which before touching anything** —
they are handled differently.

| Kind | What to change |
|---|---|
| **Scope grew** | Raise the estimate, and spell out the added scope as subitems |
| **Estimate was wrong** | Change only the number, and note which multiplier was misjudged |
| **Work did not finish** | Leave the estimate alone. Handle it as a `/seeya` carry-over |

Mistaking the third for the second inflates estimates forever and the plan stops meaning
anything.

## 3. Change it, and record why

```markdown
- [ ] **CSV import pipeline** — column mapping and row validation — 8 MD / AI 3.2
```

One line directly underneath:

```markdown
> Estimate changed 2026-08-05: AI 1.6 -> 3.2. Per-row error reporting and the retry queue
> were never in the original scope. Scope growth, not a bad multiplier.
```

- Put **date, old -> new, reason and kind** on that one line
- Fix the section heading total and the summary table too. Recount with `/hey-sync`
- Tuning several items means **one reason line per item**. Never one lumped note

## 4. State the knock-on effect

```bash
python3 "$HEY" progress
python3 "$BOARD" goal
```

- What the total moved from and to
- How the calendar conversion shifts, stating utilisation and parallel efficiency
- Whether the weekly goal needs resetting — propose `board.py goal --set` and confirm first

## 5. Correcting a multiplier itself

If the `variance` mean keeps leaning the same way, **fix the method, not the items.** Name
which category in `/hey-plan`'s multiplier table was wrong and record it in the ledger's
estimate-basis section.

```markdown
> **Multiplier correction 2026-08-05**: "scaffolding and mapping 6-7x" drops to 4-5x.
> Measured mean over 4 items: x4.3. Writing generators involves more judgement than
> scaffolding, so the multiplier is lower.
```

## Never

- Never change an item the user did not mention
- Never change a number without a reason line. No reason, no change
- Never absorb unfinished work as a bigger estimate. That is a carry-over
- Never multiply everything by the `variance` mean in bulk. Confirm item by item
- Never propose a multiplier correction on 2 or fewer measurements. The sample is too small
