# ABOUTME: pytest path setup for the worktree plugin script
# ABOUTME: makes plugins/worktree/scripts importable as worktree_tool

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "worktree" / "scripts"),
)
