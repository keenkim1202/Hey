---
name: hey-recap
description: Weekly review — burndown, carry-over patterns, estimate variance and output trends in one screen. Use on "weekly recap", "how did this week go", "recap", "retro", "show me the burndown". Read-only; never edits the ledger.
---

# Weekly recap

Read-only. **Never edit the ledger.** What to change based on the recap is the user's call;
`/hey-tune` or `/hey-sync` apply it.

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
BOARD="$ROOT/scripts/board.py"
```

## 1. Gather the numbers

```bash
LC_TIME=C date "+%Y-%m-%d (%a)"
python3 "$HEY" progress
python3 "$HEY" burndown --days 14
python3 "$HEY" carryover --days 3
python3 "$HEY" variance
python3 "$BOARD" show --window 14
python3 "$BOARD" streak
python3 "$BOARD" goal
python3 "$HEY" log --limit 7
python3 "$HEY" notes --since 7
```

A weekly recap is the one place the extra calls are worth it — but if the user only wants a
quick read, `board.py wrap` covers most of it in one call.

When snapshots are thin the scripts say so. **Never assert a trend on top of that.**

## 2. Five sections

### What got done

Group this week's work-log entries into themes rather than listing them day by day. Keep
the PR numbers. **Never invent something the log does not contain.**

### Burndown

```
AI-days left  81.25 -> 80.85   ▇▇▆▆▅▅▄
2026-07-23 ~ 2026-08-05 · 14 days · burned 0.40
0.029 AI-days/day -> the remaining 80.85 is about 2788 days
```

When the runway comes out absurd, **report it as printed and explain why.** It is usually
one of three things: items are not being closed, scope grew, or the snapshot window is too short.

### Blockers and carry-over

**Blockers first — their age is the sounder number.** A `[since]` date is a calendar fact
that holds even on a machine with no recorded history, and it survives an item being
renamed. Report it in days. For anything past three, **one line on why it is not moving**,
and split them by who has to clear them: you, someone else, or a pending decision.

Carry-over comes second and is counted in **observations, not days** — a run of six means
the item was seen unfinished in six consecutive recorded snapshots, and nothing checks the
dates between them, so six observations can span two months. Say "observations" or
"snapshots", never "days".

Say *unfinished* rather than *stuck* or *unchanged*: the run comes from the WIP state
alone, so an item whose boxes closed every day is still counted. A run breaks when a
snapshot finds the item not in progress, or when its title is edited — the key is
`<phase>|<title>`, so renaming restarts the count at zero and a short run may mean a
rename rather than fresh work.

### Estimate variance

```
mean multiplier x7.1 (2 measurement(s)) — multiply estimates by this to land nearer reality
```

Under three measurements, **write "sample too small" and do not propose a multiplier
correction.** At three or more, name which category was off — scaffolding, UI, or state machine.

Variance only measures items **seen unfinished before they closed.** Anything already
complete when recording began is excluded, so early on this list is short or empty. That is
correct, not a bug — do not describe those items as instant wins.

### Output

One board — closed work — and code and tokens as plain context beneath it.

```
closed   best 1.20 on 08-01   avg 0.64   4-day streak   0.4 behind goal
code     1,204 lines
tokens   1.9M tokens
```

**There is no best day for code or tokens, and do not invent one.** Both measure activity,
not accomplishment: a refactor that deletes a bad implementation and a session that retried
three times each move them, in the direction that looks like more. They are here to say
what shape the week had, not to be won.

**Call out where the three disagree.** Substantial code and token counts with zero closed
work means the work happened but no item closed. That is one of two causes — items sized
too large, or boxes not being checked. **Ask which.**

## 3. One line each on what carries into next week

```bash
python3 "$HEY" next
```

- Whether carry-overs go to the front of next week
- Which items need their estimates tuned (`/hey-tune`)
- Which blockers need a question asked this week

**Propose only.** Never edit the ledger.

## 4. An HTML card, only on request

If the user wants a shareable card, build an Artifact. **Read the `artifact-design` skill
first.** If it includes charts, read `dataviz` too. Otherwise the terminal output is the
deliverable.

The card carries the same five sections. **Never introduce a number that is not in them.**

## Wording

**How you word what you add is in the `hey-ledger` skill**, under "How to write what you add" — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never edit the ledger. A recap is read-only
- Never state a trend, average or runway when snapshots are too few
- Never propose a multiplier correction on fewer than three measurements
- Never invent an accomplishment the log does not show
- Never soften a bad metric by pivoting to a better one. If closed work is 0, say 0
- Never build an Artifact unless asked
