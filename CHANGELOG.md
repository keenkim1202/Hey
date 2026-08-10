# Changelog

English · [한국어](CHANGELOG.ko.md)

Claude Code installs from the branch, so every commit reaches it and this file is how you
find out what changed. Codex pins a version in `.codex-plugin/plugin.json`, so a release
here is what a Codex user actually receives.

## 0.2.0

Seventy-one commits since 0.1.0, and Codex saw none of them — the pinned version was never
raised. It is now, and a check in the self-test stops it happening again.

**If you are on 0.1.0, four behaviour changes are worth knowing before you update.**

### Behaviour changes

- **A blocker is a marker now, not a word.** Writing "waiting on the API" in an item no
  longer classifies it. Use `[blocked]`, or file it under the blocker heading. Prose used
  those words without meaning "hold this", and an item taken out of the running by
  accident is one nothing offers you again. `doctor` names the lines that read as waiting
  and carry no marker, so an old ledger does not go quiet.
- **`snapshot --date` refuses to write box state into the past**, which `collect --date`
  has always refused. The ledger keeps no history of its checkboxes, so stamping today's
  under an earlier date moved the baseline and made every later day read zero.
- **`note` no longer accepts `--scope`.** A note lands in exactly one ledger. The flag
  parsed, changed nothing and said nothing about it.
- **Nothing is ranked any more.** The board, the streak, the weekly pace, the personal
  best and the daily goal are gone. Closed work rests on estimates the tool cannot
  calibrate, and code and token counts measure activity rather than accomplishment — every
  one of those numbers dressed a bookkeeping choice as a result.

### The ledger reads differently

- **Markers.** `[id <name>]` fixes an item's identity so renaming it no longer severs its
  history — worth adding to every item, since a rename otherwise banks its closed boxes a
  second time. `[blocked]`, `[since YYYY-MM-DD]`, `[branch <name>]` and `[AI n]` on a
  subitem all read as data rather than prose.
- **Fenced code blocks are skipped.** A checklist row quoted inside your ledger used to be
  counted as work.
- **Template placeholders are skipped.** A freshly created ledger no longer reports its own
  example rows as an item, a subitem and a blocker.
- **The append-only half can live in a second file** — `add <root> --ledger-log <path>`
  puts the work log and notes there while the checklist stays put.

### New

- `draft-log` builds work-log entries from git history, for a ledger created today on a
  repository that is months old. Prints; writes nothing.
- `import-tasks` converts a spec-kit `tasks.md` into ledger items. `T001` becomes
  `[id t001]`. No estimate is invented.
- `variance` compares each recorded day's closed AI against the span of that day's own
  commits — the one calibration figure here. A floor, and not a record of hours worked.
- `pr-sync` reports how long each merged pull request stayed open, and gathers the items a
  merged PR names that are still unchecked. It proposes; it never ticks.
- Token cost, from rates you put in `config.json` under `token_cost`. No built-in price
  table: one here would be wrong the week it changes. No rates means no cost line.
- `/next` briefs the single next item and asks whether to start it.
- `HEY_WIDTH` spreads the card out on a wide terminal.

### Fixes worth naming

- The ledger and `config.json` are written atomically. Both were one interrupted write
  from being truncated, and the ledger is never committed, so there was no copy to restore.
- Unpushed work is measured against the remote, so a squash-merged branch is no longer
  reported as work about to be lost.
- Tokens are charged to a project by path, so `alpha-ios` no longer lands in `alpha`.
- A commit in the last minute of a day is counted on that day rather than on none.
- Every file read and written names `encoding="utf-8"`. A Korean ledger raised
  `UnicodeDecodeError` on a Windows legacy code page.
- The first record reads as `baseline` on the card, matching what `collect` always said,
  instead of `0.00 AI-days`.

## 0.1.0

First release. Codex support, the standup skill, and per-item history.
