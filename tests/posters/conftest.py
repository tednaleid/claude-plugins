# ABOUTME: pytest path setup for the review-branch poster scripts
# ABOUTME: makes plugins/review-branch/scripts importable as glab_comment / gh_comment

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "review-branch" / "scripts"),
)
