---
name: hey-run
description: Work through checklist items up to an agreed point in a loop, then report a summary. The user can name the scope; otherwise recommend one. Also recommends which items can run in parallel. Use on "take it from here", "run the loop", "handle these items", "how far can you get", "anything that can run in parallel".
---

# Scoped loop

Runs checklist items back to back. Real code changes, so **never start without an approved
scope.**

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
```

## 1. Gather candidates and evidence

```bash
python3 "$HEY" batch --limit 8
python3 "$HEY" next
python3 "$HEY" dirty
```

`batch` supplies three mechanical signals. **Never decide on that output alone.**

| Signal | Meaning | Limit |
|---|---|---|
| mentions first | the item body names another item | misses any dependency not written down |
| overlap | backtick tokens (modules, files, types) are shared | misses the same file under a different name |
| blocked | the item marks itself as waiting | misses anything not marked |

So **read the actual code before fixing the scope.** Check which files each item would
touch and whether the overlap verdict holds. Skipping that and running in parallel means
they overwrite each other.

If `dirty` shows uncommitted work, **do not start the loop.** Ask whether to clean up first.

## 2. Recommend a scope

Use the user's scope if given. Otherwise recommend, on these four:

- **Start where prerequisites are already closed.** Doing a later item first means redoing
  it when the earlier one lands
- **Fit the hours remaining.** `AI 1.0` = 8 hours. Ask how much time is left and take that much
- **End on something verifiable.** The scope boundary must be a point where build and tests pass
- **Leave blocked items out.** If one must go in, say why and get confirmation

```
Recommended scope — 3 sequential items, AI 0.6 total

1. Wire the app root        AI 0.1   no prerequisite. Touches OrchardApp only
2. Extend CartStore            AI 0.3   no overlap with 1. Modules/Shared only
3. OrchardClient package   AI 0.2   after 2. DI registration references CartStore

Parallel candidates — 2 items, no overlap
  A. Extend CartStore          Modules/Shared
  B. codegen post-process   Scripts/API
  These touch different directories, so with separate worktrees they can run at once.

Left out of scope
- Domain/Data Account — OrchardClient has to be real first
- 6 server blockers — undeclared 2xx responses. Not fixable from the client
```

**Get approval, then start.** If the user shrinks or grows the scope, follow it.

## 3. Parallel means separate worktrees

Two items edited in one worktree overwrite each other. When running in parallel, **give each
item its own worktree** — the Agent tool's `isolation: "worktree"`, or the layout the user
already keeps.

Before running anything in parallel, confirm all four:

- The items **do not touch the same file** — both the `batch` overlap verdict and a real code check
- The items **do not regenerate the same artifact** — overlapping generator scripts mean sequential
- The items **do not both edit a shared manifest** — build settings and workspace registration
  files are collision points
- Verification is **independent per item**

If any one fails, run sequentially. **Parallelism is not the goal.**

If the user explicitly asks for large-scale parallelism (dozens of items), a Workflow
pipeline is an option — but **never reach for it unasked.** The default is a few agents, or
sequential.

## 4. The loop

Per item, in this order. **Never skip a step.**

1. Confirm what the item requires, from the spec and the existing code
2. Implement it. **Never touch a file outside the scope**
3. Verify — build, tests, lint. Use the project's own verification command
4. On pass, move to the next item. On failure, **stop and report**
5. Check boxes by `/hey-sync` rules — **only what is completely finished**

### Stop conditions

Any one of these ends the loop on the spot and hands back to the user. **Never push through
on a guess.**

- The same verification failure twice in a row
- A decision is needed that the spec does not cover — mark the item `needs decision` and move on
- A file outside the scope would have to change
- A server or external dependency does not exist yet
- The approved scope is exhausted

## 5. Summary report

```bash
python3 "$HEY" progress
```

One line each, facts only.

```
Loop result — 2 of 3 scoped items done

Done
- App root wired — OnboardingView + toast host in OrchardApp. `make test` passes
- CartStore extended — loading state exposed. 3 tests added, passing

Not done
- OrchardClient package — the 3 openapi declarations landed. AuthMiddleware stopped:
  the server header contract (allowed X-Tenant values) is undecided. Item marked
  `needs decision`

Progress   35/154 (22.7%) -> 39/154 (25.3%)
Estimate   AI 81.25 left -> 80.85

No commits or PRs were created. The changes are in the working tree
```

- **Always split done from not done.** For not done, how far it got and what remains
- Name the verification you ran. If you did not run it, write "not verified"
- Take progress deltas from the script output
- **Never create a commit, push or PR.** Only when the user asks

## Wording

**How you word what you add is in the `hey-ledger` skill**, under "How to write what you add" — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never touch code before the scope is approved
- Never start a loop in a worktree with uncommitted work
- Never run items in parallel without the overlap check, or inside one shared worktree
- Never move to the next item without verifying
- Never edit or delete a test to get around a failure
- Never process an out-of-scope item "while you are in there"
- Never mark an unfinished item `[x]`
- Never create commits or PRs on your own
