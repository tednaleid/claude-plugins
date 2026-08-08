# ABOUTME: pytest path setup and shared fixtures for review-branch script tests
# ABOUTME: makes plugins/review-branch/scripts importable and provides temp env/repos

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "review-branch" / "scripts"),
)
