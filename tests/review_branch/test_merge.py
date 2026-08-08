# ABOUTME: tests for review.toml/state.json loading and the merge/staleness rules
# ABOUTME: covers postable body selection, stale notes and edits, posted flags

import json

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 124 review - refs"
vcs = "glab"
number = 124
url = "https://gitlab.example.com/g/p/-/merge_requests/124"
source_branch = "feat"
target_branch = "main"

[overall]
body = "Overall prose."

[[findings]]
id = "f1"
severity = "high"
title = "Bad validation"
file = "api.py"
lines = "10-20"
lenses = ["security"]
body = "Explanation."
comment = "Draft one."
comment_rev = 2
anchor = "api.py:20"

[[findings]]
id = "f2"
severity = "low"
title = "Naming nit"
file = "b.py"
lines = "5"
lenses = ["naming"]
body = "Nit."
comment = "Draft two."
posted_url = "https://gitlab.example.com/note/1"
posted_at = "2026-08-08T00:00:00Z"
"""


@pytest.fixture
def round_dir(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text(REVIEW_TOML)
    return d


def write_state(d, findings):
    (d / "state.json").write_text(json.dumps({"findings": findings}))


def test_missing_state_yields_defaults(round_dir):
    merged = review_tool.merged_findings(
        review_tool.load_review(round_dir), review_tool.load_state(round_dir)
    )
    f1 = merged[0]
    assert f1["disposition"] is None
    assert f1["postable_body"] == "Draft one."
    assert f1["posted"] is False
    assert merged[1]["posted"] is True


def test_current_edit_wins(round_dir):
    write_state(round_dir, {"f1": {"disposition": "post", "edited_comment": "Mine.", "edited_comment_rev": 2}})
    f1 = review_tool.merged_findings(
        review_tool.load_review(round_dir), review_tool.load_state(round_dir)
    )[0]
    assert f1["postable_body"] == "Mine."
    assert f1["edited_stale"] is False
    assert f1["disposition"] == "post"


def test_stale_edit_and_note_are_flagged_and_ignored(round_dir):
    write_state(
        round_dir,
        {"f1": {"note": "soften", "note_rev": 1, "edited_comment": "Old.", "edited_comment_rev": 1}},
    )
    f1 = review_tool.merged_findings(
        review_tool.load_review(round_dir), review_tool.load_state(round_dir)
    )[0]
    assert f1["postable_body"] == "Draft one."
    assert f1["edited_stale"] is True
    assert f1["note_stale"] is True
    assert f1["note"] == "soften"


def test_bad_toml_exits_with_path_in_message(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text("[review\n")
    with pytest.raises(SystemExit) as exc:
        review_tool.load_review(d)
    assert "review.toml" in str(exc.value)
