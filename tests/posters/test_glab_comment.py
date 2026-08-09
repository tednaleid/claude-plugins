# ABOUTME: tests for glab_comment pure functions (diff parsing, anchors, marker, dedup)
# ABOUTME: no network and no real glab calls; only the pure helpers are exercised

import json

import glab_comment as gc

DIFF = """@@ -10,3 +10,4 @@
 context line
-removed line
+added line one
+added line two
 trailing context"""


def test_parse_diff_lines_tracks_old_and_new_numbers():
    lines = gc.parse_diff_lines(DIFF)
    added = [e for e in lines if e["kind"] == "added"]
    assert [e["new_line"] for e in added] == [11, 12]
    removed = [e for e in lines if e["kind"] == "removed"]
    assert removed[0]["old_line"] == 11


def test_find_anchor_added_line_uses_new_line():
    lines = gc.parse_diff_lines(DIFF)
    assert gc.find_anchor(lines, 11) == {"new_line": 11}


def test_find_anchor_context_line_uses_both():
    lines = gc.parse_diff_lines(DIFF)
    anchor = gc.find_anchor(lines, 10)
    assert anchor == {"old_line": 10, "new_line": 10}


def test_find_anchor_missing_line_returns_none():
    lines = gc.parse_diff_lines(DIFF)
    assert gc.find_anchor(lines, 999) is None


def test_ensure_marker_prepends_once():
    body = gc.ensure_marker("hello")
    assert body.startswith("> **From Claude:**")
    assert gc.ensure_marker(body) == body  # idempotent


def test_nearest_addressable_orders_by_distance():
    lines = gc.parse_diff_lines(DIFF)
    assert gc.nearest_addressable(lines, 11, count=2) == [10, 12]


def test_find_duplicates_matches_marker_and_position():
    discussions = [
        {"id": "d1", "notes": [{"body": "> **From Claude:** x",
                                 "position": {"new_path": "a.py", "new_line": 11}}]},
        {"id": "d2", "notes": [{"body": "human note",
                                 "position": {"new_path": "a.py", "new_line": 11}}]},
    ]
    assert gc.find_duplicates(discussions, "a.py", 11) == ["d1"]


def test_load_items_reads_manifest(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"file": "a.py", "line": 11, "body": "hi"}]))
    args = type("A", (), {"manifest": str(manifest), "general": False, "target": None})()
    items = gc.load_items(args)
    assert items == [{"path": "a.py", "line": 11, "body": "hi"}]


def test_check_items_is_all_or_nothing():
    index = {"a.py": {"lines": gc.parse_diff_lines(DIFF), "old_path": None}}
    items = [
        {"path": "a.py", "line": 11, "body": "clean"},
        {"path": "missing.py", "line": 5, "body": "no such file"},
        {"path": "a.py", "line": 999, "body": "no such line"},
    ]

    ready, problems = gc.check_items(items, index, [], allow_duplicate=False)

    assert len(ready) == 1
    assert ready[0]["path"] == "a.py" and ready[0]["line"] == 11
    assert ready[0]["anchor"] == {"new_line": 11}
    assert len(problems) == 2
    assert any("missing.py" in p and "not in this MR's diff" in p for p in problems)
    assert any("a.py:999" in p for p in problems)


def test_check_items_blocks_duplicate_unless_allowed():
    index = {"a.py": {"lines": gc.parse_diff_lines(DIFF), "old_path": None}}
    items = [{"path": "a.py", "line": 11, "body": "clean"}]
    discussions = [
        {"id": "d1", "notes": [{"body": "> **From Claude:** x",
                                 "position": {"new_path": "a.py", "new_line": 11}}]},
    ]

    ready, problems = gc.check_items(items, index, discussions, allow_duplicate=False)
    assert ready == []
    assert len(problems) == 1
    assert "already has a From Claude comment" in problems[0]

    ready, problems = gc.check_items(items, index, discussions, allow_duplicate=True)
    assert len(ready) == 1
    assert problems == []
