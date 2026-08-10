---
name: hey-plan
description: Turn a spec document or task list into a checklist with MD and AI estimates, and put it in the ledger. Use on "estimate this", "break down this spec", "make me a checklist", "how long will this take", "plan this out". Always records the reasoning behind each estimate.
---

# Spec to checklist and estimates

The input can be a spec document, meeting notes, a pasted task list, an issue link —
anything. The output is **a checklist shaped for the ledger, with estimates and the
reasoning behind them.**

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
```

**If the input is a spec-kit `tasks.md`, convert it rather than re-reading it:**

```bash
python3 "$HEY" import-tasks path/to/tasks.md
```

It prints ledger-shaped phases and items and writes nothing. `T001` becomes `[id t001]`,
which is the stable key step 2 asks for, arriving for free. `[P]` and `[US1]` are kept in
the item text. **Estimates are left blank on purpose** — `tasks.md` carries none, and the
estimate column is the one place in this file to invent nothing. Steps 3 and 4 are still
yours to do, on the items it printed.

## 1. Read it, then find what is undecided

**Finding the undecided parts comes before estimating.** An unknown hidden inside an
estimate turns into a delay later.

- Screens, states or error paths the spec does not cover
- Work that needs a server API that does not exist yet
- Anything requiring an external account, console or certificate
- Anything waiting on another team's decision

Make these items anyway, and **mark them `[blocked]`** — or file them under the blocker
heading, which does the same thing. They then drop out of `/hey-run` candidates and their
wait gets counted.

**A word in the text is not a marker.** Writing "waiting on the API" does not block an
item, deliberately: prose uses those words without meaning "hold this", and an item taken
out of the running by accident is one nothing will offer you again. `doctor` points at
lines that read as waiting and carry no marker, so nothing goes quiet.

## 2. Break it into items

Size an item to **what can be closed within a day**. Anything over `AI 1.0` gets subitems.

```markdown
## P1. Auth and onboarding (27.5 MD / AI 8.3)

- [ ] **Social login, 4 providers** `[id social-login]` — Apple / Google / GitHub / Microsoft + server token exchange — 6 MD / AI 3.4
  - [ ] Apple Sign In
  - [ ] Google Sign In
  - [ ] GitHub
  - [ ] Microsoft
- [ ] **Duplicate account** `[id dup-account]` — same email on another provider, notice modal — 1 MD / AI 0.2
```

- **Give every item an `[id <short-name>]` as you write it.** Without one the key is
  `<phase>|<name>`, so tidying the wording months later severs everything filed under it —
  carry-over restarts, `item` finds no history, and the next snapshot banks its closed
  boxes a second time. Adding an id afterwards recovers none of that; it only stops the
  next rename from costing the same. This is the one part of an item that is free to get
  right now and impossible to get right later
- Ids are short, lowercase and stable. Nobody reads them, so they do not have to read
  well — they have to stay put while the title changes
- Estimates go **on the top-level item line only**, never on subitems
- The section heading total must match the sum of its items. Verify with
  `python3 "$HEY" progress --phases`

## 3. Estimate

Produce two numbers:

| | Meaning |
|---|---|
| `MD` | a traditional man-day, without tooling |
| `AI` | the man-day equivalent with tooling. `AI 1.0` = one 8-hour day |

**Split each item into two kinds of work and treat them separately.**

| Kind | How it scales | Example |
|---|---|---|
| Code | faster with tooling, by a factor you have to find | module setup, DTO mapping, screens, state machines |
| **Human-gated** | **1x, always** | external consoles, accounts, certificates, store review, reproducing against a live server |

Human-gated work **does not shrink with better tooling**. Where it is mixed in, break it
out — that split is the part of this method that holds regardless of who is estimating.

**The code factor is yours to measure, and this skill will not hand you one.** There is no
table of ratios here because a ratio depends on the language, the codebase, the model and
the person, and a number that looks authoritative is worse than an admitted guess: it
turns speculation into schedule arithmetic that nobody re-examines.

- **With history**: read `hey.py variance`. Its second block compares each recorded day's
  closed AI against the span of that day's own commits — a ratio above 1 means that day's
  estimates claimed more hours than the day held. Correct by roughly that much, and write
  the factor and where you got it into the ledger's estimate basis.
- **Without history, estimate `AI` directly, in hours, and do not derive it from `MD`.**
  Say "this is about two hours" and divide by eight. Guessing a duration is a guess the
  first day's commit span can check; guessing a ratio to divide `MD` by is a guess with
  nothing to check it against, and it hides inside a number that looks calculated. Write
  `MD` down as its own honest figure — what this would have cost without tooling — and
  keep it out of the arithmetic that produces `AI`.
- Either way, **say plainly that early estimates are guesses**, keep them coarse, and
  revisit after the first day recorded. **Do not invent a multiplier to look precise.**

> A worked failure, from this repository on 2026-08-10. Multipliers of ÷4 to ÷6 were
> assumed off "typical values" — exactly what the paragraph above forbids — and eleven
> items were estimated through them. The first day measured said the day's estimates had
> claimed 11.8 hours against a commit span of 4h 30m: **2.6x too high**, discovered only
> because someone noticed the ledger declaring a full day at three in the afternoon.

```
StoreKit 2 = 5 MD code @4x + 3 MD console and sandbox @1x = 8 MD / AI 4.25
             the 4x is measured, from four finished items of this kind
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

If there is no ledger, create one with `python3 "$HEY" add <project root> --init` rather
than copying the template by hand — it refuses a linked worktree and puts the file at the
registered path. **Confirm with the user first.** If one exists, add items to the right
section and let `/hey-sync` recompute the summary.

Then report:

- Totals as `N MD / AI M`, and the share sitting at 1x
- Undecided and waiting items — **how many, and who has to decide what**
- The three largest items and why they are large
- What the estimate excludes

## 7. Offer what the plan calls for, once

```bash
python3 "$HEY" suggest
```

Run it **after** the items are in the ledger, never before — it reads the plan, so it has
nothing to read until the plan exists. It prints 💡 lines, each naming the item that
produced it, and prints nothing when there is nothing to say.

**Pass its output through, and add to it only under these rules:**

- **Never install, enable or configure anything.** Not the script's job and not yours.
  Print the command; the person runs it or does not
- **Silence beats a weak suggestion.** If they already have something that covers it, say
  nothing — or, if the thing you would suggest is clearly better, say that and why, once
- **Only name a capability you have confirmed exists.** `suggest` reads the marketplaces
  configured on this machine, so what it prints is real. If you want to name something it
  did not print — a Korean plan gives its English catalogue almost nothing to match, so
  this happens — confirm the plugin is really there before naming it. **A recommendation
  the reader cannot find is worse than none:** they go looking, and stop trusting the rest
- **One line of evidence per suggestion**, quoting the item. "Your plan has `X`" is the
  whole argument; without it this is an advertisement

## Wording

**How you word what you add is in the `hey-wording` skill** — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never write a number with no reasoning. If it is a rough split, say "rough"
- Never estimate an undecided thing as if it were decided. Make it an item and mark it waiting
- Never fold 1x work into another multiplier
- Never invent items outside the scope the user gave. Put them in an "out of scope" table and ask
- Never create a ledger without the user's confirmation
