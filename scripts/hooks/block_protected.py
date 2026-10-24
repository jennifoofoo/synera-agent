#!/usr/bin/env python3
"""PreToolUse hook: block writes to the kit and secrets (exit 2 = block, stderr goes back to Claude)."""

import json
import sys
from pathlib import Path

PROTECTED_DIRS = ("data", "starter_agent", "benchmark")
root = Path(__file__).resolve().parents[2]
path = Path(json.load(sys.stdin).get("tool_input", {}).get("file_path", "")).resolve()
try:
    top = path.relative_to(root).parts[0]
except ValueError:
    sys.exit(0)  # outside the repo
if top in PROTECTED_DIRS or path.name == ".env":
    print(
        f"Blocked: {path.relative_to(root)} is protected (kit code, data or secrets). Put new code in building_agent/.",
        file=sys.stderr,
    )
    sys.exit(2)
