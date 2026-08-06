# <project> work ledger (local only)

**Progress (boxes): 0/0 (0%)** — every checkbox in this file.

**Progress (estimate): 0.0 / 0 AI-days closed · 0 in progress · 0 left**

> Do not commit this file. Add it to `.git/info/exclude` and keep it local.
>
> Estimate basis: <date>. `MD` is a traditional man-day; `AI` is the man-day equivalent
> with tooling. `AI 1.0` = one 8-hour day.
>
> **How AI is derived**: split each item into code work and human-gated work, then apply
> multipliers separately. Code runs 3-7x (scaffolding and mapping 6-7x, UI with a settled
> spec 5-6x, API-wired screens 3-4x, state machines 1.5-3x). Human-gated work is 1x —
> external consoles, accounts, certificates, store review, reproducing against a live server.
>
> Last synced: <date> · <default branch> `<commit>` · no open PRs

---

## Notes

Whatever comes to mind. `/hey <text>` inserts under today's date. **Newest first.**
Date, time, branch and commit are attached automatically. Never deleted, only appended.

---

## PR log

A running record. **Never delete or compress rows; append.** `/hey-sync` adds rows and
fills in merge dates.

| PR | Title | Opened | Merged | Checklist impact |
|---|---|---|---|---|

**No open PRs.**

## Work log

A running record by date. **Newest first.** Work that never became a PR goes here too —
which worktree, which branch, how far it got. `/seeya` appends at the end of the day and
`/wassup` reads it in the morning.

### Next up

1. <item> — <one sentence of reasoning>

---

## Summary

`Items` and `Done` count top-level items; `Progress` counts every checkbox including
subitems. The two differ, so a phase with 0 done can still show non-zero progress.
Paste the output of `hey.py progress --phases` here.

| Phase | Items | Done | Progress (boxes) | MD | AI |
|---|---|---|---|---|---|
| **Total** | | | | | |

### Calendar conversion

21 business days per month, 80% effective utilisation. Waiting on servers or external
dependencies is not included.

| Staffing | Raw | With 10% buffer |
|---|---|---|
| 1 dedicated | | |
| 2 (parallel efficiency 0.8) | | |

---

## P0. <first phase> (0 MD / AI 0)

- [ ] **<item name>** — <description> — 3 MD / AI 0.4
  - [ ] <subitem>

> Leave one line of reasoning per estimate: what it was compared against, what was
> assumed, and **what was left out.**

---

## Blockers (clear before starting)

Things you cannot resolve yourself. Put a waiting word in the text — `waiting`, `blocked`,
`TBD`, `needs decision`, `pending` — and the scripts will treat it as a blocker, drop it from
`/hey-run` candidates and count how long it has been stuck.

Say when the wait started with `[since YYYY-MM-DD]`. The age is what decides which blocker
to go chase, and without the marker it can only be inferred once several days are on
record — which a blocker that predates this file will never have. `[since unknown]` when
the start genuinely cannot be found: that is a settled answer, and it stops the tools
asking again.

- [ ] <what is blocked> — <who has to clear it> — **needs decision** `[since YYYY-MM-DD]`

---

## Out of scope

| Item | Why |
|---|---|
