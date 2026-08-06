---
name: next
description: Brief the single next item and ask whether to start it. Use on "next", "what's next", "what do I do now", "give me the next one", "다음", "다음 작업". Read-only until the user says go.
---

# The next one item

`/wassup` fills a day. This fills the next slot. One item, enough context to start it, and a
question. **Never start work without an answer.**

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}"   # Codex names it PLUGIN_ROOT
HEY="$ROOT/scripts/hey.py"
```

## 1. Read the order

```bash
python3 "$HEY" next
python3 "$HEY" dirty
```

Read the ledger conventions from the `hey-ledger` skill if scope or paths are unclear.

**Loose work outranks the list.** If `dirty` reports unpushed commits or uncommitted
files, that is the next item — say so and name the worktree and branch. Work that only
exists on one machine is the one thing that can vanish.

Otherwise take `Next up` in the order written. **Never reorder it on a whim.** Walk down
until you hit the first item that is actually startable, and skip anything whose
prerequisite is unfinished or that a blocker gates. **Say what you skipped and why** — a
skipped item that goes unmentioned looks finished.

## 2. Read the item before describing it

Open the ledger and find the item. If it has subitems, the next thing is **the first open
subitem, not the whole item.** Then look at the code it touches, so the briefing names real
files rather than restating the ledger.

**Never invent a file path.** If you have not confirmed it exists, say where you would
expect it and mark that as a guess.

## 3. The briefing

Four blocks at most, bracket labels, no card here — this is not `/wassup`.

```
**[ Next ]**  Heading anchors — collision suffixes           AI 0.25 (rough split)

**[ Why now ]**
- P0 renderer, item 2 of 4. The TOC renderer below it waits on this
- #14 landed the slug generator, so the collision case is the only gap left

**[ Where ]**
- Modules/Render/Sources/Slug.swift — the generator, no collision handling
- Modules/Render/Tests/SlugTests.swift — 6 cases, none with a duplicate title

**[ Watch for ]**
- The suffix scheme changes anchor URLs. Anything already linking to a page anchor breaks
```

- The estimate comes from the ledger. If the subitem has none, divide the parent's across
  its subitems and **say it is a rough split**
- `[Watch for]` only when there is something real — a blocker, a decision not made, an
  interface someone else depends on. **Never pad it**
- If the item is human-gated (external console, certificate, store review), say that
  tooling will not speed it up

## 4. Ask, then stop

End with one question and **wait**:

```
Start this, or take a different one?
```

- If they say go, do the work. When it is done, **do not check the box yourself** — the
  ledger is `/hey-sync`'s job. Say what changed and let them run it
- If they name a different item, brief that one the same way and ask again
- If they say no, stop. Do not offer a substitute unprompted

## Wording

**How you word what you add is in the `hey-ledger` skill**, under "How to write what you add" — three blocks at most, no praise, no filler, numbers copied from the script.

## Never

- Never start work before the user answers
- Never brief more than one item. `/wassup` is the one that fills a day
- Never edit the ledger. Not the boxes, not the order, not the estimates
- Never recompute an estimate. Use the ledger's number, and flag rough splits
- Never name a file you have not confirmed exists
- Never skip an item silently
- Never commit, push or open a PR on your own
