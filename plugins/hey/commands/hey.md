---
description: Capture what just came to mind into the ledger's notes, with date, branch and commit attached.
argument-hint: <note text> [file or link]
---

Record a note under today's date in the ledger's notes section. `/seeya` and `/hey-recap`
read it later.

What the user wants to note:

$ARGUMENTS

## Steps

1. **Separate out file paths and links.** If the user named a file without a path, find the
   real one and render it as `path/to/file.swift:42`. Never invent a path that does not exist.

2. Record it. Time, branch and commit are attached by the script.

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/hey.py" note "<text>" \
     --file "<path:line>" --doc "[title](link)"
   ```

   `--file` and `--doc` are repeatable; omit them when there is nothing to attach.

3. Print the one result line. No commentary.

## Rules

- **Tidy the wording, never the meaning.** Keep the user's phrasing
- If the ledger has no notes section the script says so. Then **ask** whether to add one
- Outside a registered project, `--project <name>` is required. If it is unclear which
  project, show `hey.py projects` and ask
- A note **only gets recorded.** Never change code or the checklist because of its content.
  If it looks like it should become a task, say so and leave it to `/hey-plan` or `/hey-sync`
- Several thoughts in one message means **several separate notes**, not one crammed line
