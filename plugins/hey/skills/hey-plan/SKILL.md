---
name: hey-plan
description: Turn a spec document or task list into a checklist with MD and AI estimates, and put it in the ledger. Use on "estimate this", "break down this spec", "make me a checklist", "how long will this take", "plan this out". Always records the reasoning behind each estimate.
---

# Spec to checklist and estimates

The input can be a spec document, meeting notes, a pasted task list, an issue link —
anything. The output is **a checklist shaped for the ledger, with estimates and the
reasoning behind them.**

```bash
HEY="${CLAUDE_PLUGIN_ROOT}/scripts/hey.py"
```

## 1. Read it, then find what is undecided

**Finding the undecided parts comes before estimating.** An unknown hidden inside an
estimate turns into a delay later.

- Screens, states or error paths the spec does not cover
- Work that needs a server API that does not exist yet
- Anything requiring an external account, console or certificate
- Anything waiting on another team's decision

Make these items anyway, but **put a waiting word in the text** (`waiting`, `blocked`,
`TBD`, `needs decision`, `pending`). The scripts then treat them as blockers: they drop out
of `/hey-run` candidates and `/wassup` starts counting how long they have been stuck.

## 2. Break it into items

Size an item to **what can be closed within a day**. Anything over `AI 1.0` gets subitems.

```markdown
## P1. Auth and onboarding (27.5 MD / AI 8.3)

- [ ] **Social login, 4 providers** — Apple / Google / GitHub / Microsoft + server token exchange — 6 MD / AI 3.4
  - [ ] Apple Sign In
  - [ ] Google Sign In
  - [ ] GitHub
  - [ ] Microsoft
- [ ] **Duplicate account** — same email on another provider, notice modal — 1 MD / AI 0.2
```

- Estimates go **on the top-level item line only**, never on subitems
- The section heading total must match the sum of its items. Verify with
  `python3 "$HEY" progress --phases`
- Keep item names short and unique. **The key is `<phase>|<name>`, so renaming later
  breaks the link to past snapshots**

## 3. Estimate

Produce two numbers:

| | Meaning |
|---|---|
| `MD` | a traditional man-day, without tooling |
| `AI` | the man-day equivalent with tooling. `AI 1.0` = one 8-hour day |

**Split each item into two kinds of work and apply the multipliers separately.**

| Kind | Multiplier | Example |
|---|---|---|
| Scaffolding, mapping, boilerplate | 6-7x | module setup, DTO mapping, generators |
| UI with a settled spec | 5-6x | screens whose design is final |
| Screens wired to an API | 3-4x | anything shaped by server responses |
| State machines, concurrency | 1.5-3x | streaming, cancel and retry policy |
| **Human-gated** | **1x** | external consoles, accounts, certificates, store review, reproducing against a live server |

Human-gated work **does not shrink with better tooling**. Where it is mixed in, break it out.

```
StoreKit 2 = 5 MD code @4x + 3 MD console and sandbox @1x = 8 MD / AI 4.25
```

When totalling, **state what percentage sits at 1x.** That is the floor tooling cannot move.

## 4. Record the reasoning

An estimate with no recorded reasoning cannot be renegotiated later. One line per item or
per section:

- What it was compared against — a similar implementation, another platform's code, spec volume
- What was assumed — "assumes the server API exists", "assumes the design is final"
- **What was left out.** This matters most

```markdown
> **This estimate is optimistic.** The 8 MD / AI 1.6 does not include per-row error
> reporting or the retry queue for partial imports. Re-estimate after wiring one piece.
```

## 5. Convert to calendar time

```
21 business days per month, 80% effective utilisation. Waiting on servers is not included.

| Staffing | Raw 81.5 | With 10% buffer, 90 |
|---|---|---|
| 1 dedicated | ~4.8 months | ~5.4 months |
| 2 (parallel efficiency 0.8) | ~3.0 months | ~3.3 months |
```

- **State the utilisation and parallel efficiency.** Calculating at 100% is always wrong
- Keep external waiting out of it. It is not person-effort
- For a domain whose spec is still being revised, add a separate buffer and say why

## 6. Put it in the ledger

If there is no ledger, copy `templates/LEDGER.md`. **Confirm with the user first.** If one
exists, add items to the right section and let `/hey-sync` recompute the summary.

Then report:

- Totals as `N MD / AI M`, and the share sitting at 1x
- Undecided and waiting items — **how many, and who has to decide what**
- The three largest items and why they are large
- What the estimate excludes

## Never

- Never write a number with no reasoning. If it is a rough split, say "rough"
- Never estimate an undecided thing as if it were decided. Make it an item and mark it waiting
- Never fold 1x work into another multiplier
- Never invent items outside the scope the user gave. Put them in an "out of scope" table and ask
- Never create a ledger without the user's confirmation
