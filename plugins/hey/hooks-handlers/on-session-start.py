#!/usr/bin/env python3
"""SessionStart hook — reports only the state that is easiest to lose.

If a worktree of **the project this session was opened in** holds changes with no commit
and no push, that gets surfaced. Otherwise it says nothing at all. This fires every
session, so **silence is the default.**

One project, deliberately, whatever the configured scope says: the report claims the work
is about to be lost, and that is a claim about where you are working right now.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).parent.parent))
HEY = PLUGIN_ROOT / "scripts" / "hey.py"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()

    # Not a registered project: exit quietly.
    probe = subprocess.run([sys.executable, str(HEY), "resolve"],
                           cwd=cwd, capture_output=True, text=True)
    if probe.returncode != 0:
        return

    # Scoped to the session's own project. The default scope is a config value and may be
    # `all`, and a session opened in one project has no business opening with another's
    # state -- the message below claims the work is about to be lost, which is a claim
    # about where you are working right now.
    out = subprocess.run([sys.executable, str(HEY), "dirty", "--scope", "current"],
                         cwd=cwd, capture_output=True, text=True)

    # Decided line by line rather than with a substring. `dirty` prints one block per
    # project and its all-clear is itself a line reading "nothing uncommitted or unpushed",
    # so `"nothing uncommitted" in text` went quiet whenever *any* project in scope was
    # clean -- which, under scope `all`, is exactly when another one was not. Scoping to one
    # project makes that unreachable today; deciding structurally keeps it unreachable.
    lines = [ln for ln in out.stdout.split("\n") if ln.strip()]
    unchecked = [ln for ln in lines if "were NOT checked" in ln]
    loose = [ln for ln in lines
             if "nothing uncommitted" not in ln and "were NOT checked" not in ln]
    if not loose and not unchecked:
        return

    if loose:
        print("There is work that is neither committed nor pushed. "
              "That state is the easiest to lose, so it comes first.\n")
        print("\n".join(loose))
    if unchecked:
        # Not an alarm. Nothing was found, but nothing was fully looked at either, so the
        # line above would be a lie -- and staying silent would hide that the check for
        # unpushed commits never ran at all.
        print(("\n" if loose else "") + "\n".join(unchecked))
        print("`hey.py doctor` says what to set.")
    print("\nStarting your day? `/wassup` adds yesterday's context.")


if __name__ == "__main__":
    main()
