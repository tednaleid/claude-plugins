# ABOUTME: guards that review_tool.__version__ tracks the plugin.json version
# ABOUTME: sync-marketplace.ts stamps it via the SYNC_PLUGIN_VERSION marker
import json
from pathlib import Path

import review_tool

PLUGIN_JSON = (
    Path(__file__).resolve().parents[2]
    / "plugins" / "review-branch" / ".claude-plugin" / "plugin.json"
)


def test_version_matches_plugin_json():
    declared = json.loads(PLUGIN_JSON.read_text())["version"]
    assert review_tool.__version__ == declared, (
        f"review_tool.__version__ {review_tool.__version__} != "
        f"plugin.json {declared}; run `just sync`"
    )
