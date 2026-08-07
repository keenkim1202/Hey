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
```

`variance` measures business days from an item first starting to finishing, against its
estimate.

```
P0|codegen pipeline        est AI 0.4 -> 3 business day(s) open
P11|locale resolution      est AI 0.6 -> 4 business day(s) open
```

**These are elapsed days, not effort, and there is no mean to apply.** An item that was
open three days may have had four hours of work in it: it waited for review, shared the
days with other items, paused on a blocker. Walk them one at a time and **ask the user
what share of each span went to the item.** That answer is the evidence; the span is only
the prompt for asking.

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
```

- What the total moved from and to
- How the calendar conversion shifts, stating utilisation and parallel efficiency

## 5. Correcting the method rather than the items

If several items in the same category came in the same way off, the category may be the
problem rather than the estimates. **The evidence for that is the user's account of where
the time went, item by item — never a mean of the `variance` rows.** Those rows are
elapsed days, each confounded by review waits, parallel work and blockers, so averaging
them produces a confident-looking number built out of noise. There is no such mean any
more, and you may not compute one.

Record the change and what it rests on:

```markdown
> **Estimate basis change 2026-08-05**: code factor for generator work drops from 6x to 4x.
> Four items in this category ran long. Asked on each: roughly 60% of the elapsed days
> were hands-on, and the generator work needed judgement that scaffolding does not.
```

## Wording

**How you word what you add is in the `hey-wording` skill** — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never change an item the user did not mention
- Never change a number without a reason line. No reason, no change
- Never absorb unfinished work as a bigger estimate. That is a carry-over
- Never derive a mean from the `variance` rows. They are elapsed days and each is confounded
- Never re-estimate in bulk. One item, one reason, confirmed
