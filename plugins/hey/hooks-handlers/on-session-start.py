#!/usr/bin/env python3
"""SessionStart hook — reports only the state that is easiest to lose.

If a worktree holds changes with no commit and no PR, that gets surfaced. Otherwise it
says nothing at all. This fires every session, so **silence is the default.**
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

    out = subprocess.run([sys.executable, str(HEY), "dirty"],
                         cwd=cwd, capture_output=True, text=True)
    text = out.stdout.strip()
    if not text or "nothing uncommitted" in text:
        return

    print("There is work that is neither committed nor pushed. "
          "That state is the easiest to lose, so it comes first.\n")
    print(text)
    print("\nStarting your day? `/wassup` adds yesterday's context.")


if __name__ == "__main__":
    main()
