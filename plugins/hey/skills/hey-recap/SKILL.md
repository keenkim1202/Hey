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
2026-07-23 ~ 2026-08-05 · 14 days · net change -0.40
```

**A shape, not a rate, and the delta is a net change rather than work delivered.** The
line moves on closed work, added scope, removed scope and re-estimates alike. Never divide
a finish date out of it. A flat or rising week is a question to ask rather than a verdict:
were items not closed, or did scope grow? Say which you think it was, and say you are
inferring.

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
P0|codegen pipeline        est AI 0.4 -> 8 business day(s) open
```

**Elapsed, not effort. There is no multiplier and you may not compute one.** The days
counted are days the item was open, and in them it waited for review, ran alongside other
items and paused on blockers. Averaging those ratios would fold all of that into a number
that looks like calibration. Take them **one at a time** and ask what share of the span
actually went to the item — that answer is the user's, not yours.

Variance only measures items **seen unfinished before they closed.** Anything already
complete when recording began is excluded, so early on this list is short or empty. That is
correct, not a bug — do not describe those items as instant wins.

### Output

Three figures for the day, and nothing to compare them against.

```
closed   0.85 AI-days
code     1,204 lines
tokens   1.9M tokens
```

**There is no best day, no rank and no streak. Do not invent one.** Closed work rests on
estimates the tool cannot calibrate; code and tokens measure activity rather than
accomplishment, since a refactor that deletes a bad implementation and a session that
retried three times each push them up. These say what shape the week had. They are not
scores, and comparing them across days reads a bookkeeping choice as a result.

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

**How you word what you add is in the `hey-wording` skill** — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never edit the ledger. A recap is read-only
- Never state a trend when snapshots are too few, and never divide a runway out of the burndown
- Never average the variance rows into a multiplier. They are elapsed days, not effort
- Never invent an accomplishment the log does not show
- Never soften a bad metric by pivoting to a better one. If closed work is 0, say 0
- Never build an Artifact unless asked
