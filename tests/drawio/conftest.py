# ABOUTME: pytest path setup for the drawio plugin script
# ABOUTME: makes plugins/drawio/scripts importable as drawio_tool

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "plugins" / "drawio" / "scripts"),
)
