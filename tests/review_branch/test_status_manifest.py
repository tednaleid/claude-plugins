# ABOUTME: tests for the status and manifest subcommands
# ABOUTME: covers merged JSON output, post filtering, excludes, and anchor fallback

import json

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 9"
vcs = "glab"
url = "https://gitlab.example.com/g/p/-/merge_requests/9"

[[findings]]
id = "f1"
severity = "high"
title = "A"
file = "a.py"
lines = "10-20"
body = "x"
comment = "Comment A."
anchor = "a.py:20"

[[findings]]
id = "f2"
severity = "med"
title = "B"
file = "b.py"
lines = "30-41"
body = "x"
comment = "Comment B."

[[findings]]
id = "f3"
severity = "info"
title = "C"
file = "c.py"
lines = "1"
body = "x"
commentable = false
"""


@pytest.fixture
def round_dir(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text(REVIEW_TOML)
    (d / "state.json").write_text(
        json.dumps(
            {
                "findings": {
                    "f1": {"disposition": "post"},
                    "f2": {"disposition": "post"},
                    "f3": {"disposition": "post"},
                }
            }
        )
    )
    return d


def test_status_shape(round_dir, capsys):
    assert review_tool.main(["status", str(round_dir)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["review"]["title"] == "MR 9"
    assert [f["id"] for f in data["findings"]] == ["f1", "f2", "f3"]
    assert data["findings"][0]["postable_body"] == "Comment A."


def test_manifest_filters_and_anchors(round_dir, capsys):
    assert review_tool.main(["manifest", str(round_dir)]) == 0
    entries = json.loads(capsys.readouterr().out)
    # f3 is commentable = false, so only f1 and f2; f2 anchor falls back to end of lines
    assert entries == [
        {"file": "a.py", "line": 20, "body": "Comment A."},
        {"file": "b.py", "line": 41, "body": "Comment B."},
    ]


def test_manifest_excludes_finding_with_post_toggle_off(round_dir):
    # f1's toggle is on ("post"); f2's is off (no disposition key at all,
    # matching what the page sends when the checkbox is unchecked).
    (round_dir / "state.json").write_text(
        json.dumps({"findings": {"f1": {"disposition": "post"}, "f2": {}}})
    )
    entries = review_tool.cmd_manifest(round_dir, exclude=set())
    assert entries == [{"file": "a.py", "line": 20, "body": "Comment A."}]


def test_manifest_exclude(round_dir, capsys):
    assert review_tool.main(["manifest", str(round_dir), "--exclude", "f2"]) == 0
    entries = json.loads(capsys.readouterr().out)
    assert [e["file"] for e in entries] == ["a.py"]


def test_parse_anchor_fallbacks():
    assert review_tool.parse_anchor({"anchor": "x/y.py:12", "file": "z.py", "lines": "1"}) == ("x/y.py", 12)
    assert review_tool.parse_anchor({"file": "z.py", "lines": "5-9"}) == ("z.py", 9)
    assert review_tool.parse_anchor({"file": "z.py"}) == ("z.py", None)
