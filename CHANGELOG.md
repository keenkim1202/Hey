# Changelog

English · [한국어](CHANGELOG.ko.md)

Claude Code installs from the branch, so every commit reaches it and this file is how you
find out what changed. Codex pins a version in `.codex-plugin/plugin.json`, so a release
here is what a Codex user actually receives.

## Unreleased

Claude Code has these already; Codex receives them when the pinned version is next raised.

### New

- `open-items` prints every open item's own words, in ledger order, with nothing sorted and
  nothing cut. `next` and `batch` both answer "what now", so both stop early; a question
  about the shape of the whole plan needs the tail as well. Blocked items are marked, not
  dropped.
- `catalog` lists the plugins and skills the marketplaces on this machine offer and that are
  not installed. **It matches nothing, ranks nothing and installs nothing** — `/hey-plan`
  step 7 hands the list and the plan to the model, which is the only party that can read a
  Korean item against an English description. An earlier attempt scored plan words against
  plugin tags and produced zero suggestions from every ledger it saw: 2 of 291 catalogue
  entries carry a `keywords` list, so there was nothing to score. All 291 carry a
  description.
- `/hey-plan` gained step 7, which runs both, once, after the items land — never daily and
  never weekly. Two suggestions at most, each quoting the ledger item that produced it and
  naming the marketplace it came from, and each saying the description is the vendor's own.
  Nothing fitting is the ordinary outcome and is reported in one line rather than in
  silence, which is indistinguishable from a broken step.
- `CLAUDE_CONFIG_DIR` is honoured when locating marketplaces, so the catalogue and the host
  do not describe two different machines.

- **A base branch is a ref, and `origin/` is one place to look for it.** Every comparison
  used to spell the remote copy into the name, so a repository without a remote could not
  resolve a base at all — even though it still has a branch work lands on, and still
  accumulates commits that have not reached it. The remote copy is preferred where both
  exist; a local branch is used where it is all there is. `dirty` reports that count as
  `not yet in main` rather than as work at risk, because with nowhere to push, "unpushed"
  is every commit in the repository and never goes down.
- **`add` names any repository it finds below a directory that is not one.** Registering
  `Project/` when the code is in `Project/Sources/` is an easy miss. It prints the path and
  stops — one project is one repository, and adopting one nobody named would file its
  commits under a project that never held them. Two levels deep, skipping dot-directories
  and vendored trees.

### Fixes worth naming

- **A repository with no remote no longer fails `doctor`.** It reported
  `origin/<base> does not exist` and told you to re-add with a base branch — which cannot
  help, because there is no remote for a base to live on. Every route through that check
  failed and none of them had a fix. It is now a warning that says what is true: work
  cannot leave this machine, so unpushed commits are not a measure here. Commits, code
  counts and worktrees are unaffected. A base that really is misconfigured — a remote
  exists and `origin/<base>` is missing — still fails, and still tells you the one thing
  that fixes it.
- **`dirty` tells "nothing to check" apart from "not checked".** Three different states
  printed one sentence: a directory that is not a repository, a repository with nowhere to
  push, and a genuinely unresolved base. Only the last is a misconfiguration, and only the
  last now asks you to set anything.
- **`add` no longer names things that are not there.** Registering a directory that is not
  a git repository printed `base: unresolved — re-run with --base <branch>` and told you to
  edit a `.git/info/exclude` that does not exist. The checklist half of this tool never
  needed git, and registration now says so instead.

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
