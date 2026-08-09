# ABOUTME: tests for gh_comment pure functions (diff split/parse, anchors, marker, dedup)
# ABOUTME: no network and no real gh calls; only the pure helpers are exercised

import json

import gh_comment as gh

PR_DIFF = """diff --git a/api.py b/api.py
index 111..222 100644
--- a/api.py
+++ b/api.py
@@ -10,3 +10,4 @@ def handler():
 context line
-old line
+added one
+added two
 trailing
diff --git a/new.py b/new.py
new file mode 100644
index 000..333
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+brand new
+second line
"""


def test_split_files_keys_on_new_path():
    files = gh.split_files(PR_DIFF)
    assert set(files) == {"api.py", "new.py"}
    assert files["api.py"].startswith("@@ -10,3 +10,4 @@")


def test_split_files_ignores_file_header_lookalike_in_hunk_body():
    diff = """diff --git a/api.py b/api.py
index 111..222 100644
--- a/api.py
+++ b/api.py
@@ -10,3 +10,4 @@ def handler():
 context line
-old line
+added one
+++ b/fake.py
+added two
 trailing
"""
    files = gh.split_files(diff)
    assert set(files) == {"api.py"}
    assert "+++ b/fake.py" in files["api.py"]


def test_parse_diff_lines_numbers_new_side():
    lines = gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])
    added = [e["new_line"] for e in lines if e["kind"] == "added"]
    assert added == [11, 12]


def test_find_anchor_added_and_context_hit_removed_miss():
    lines = gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])
    assert gh.find_anchor(lines, 11) == 11   # added
    assert gh.find_anchor(lines, 10) == 10   # context
    assert gh.find_anchor(lines, 999) is None


def test_nearest_addressable_orders_by_distance():
    lines = gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])
    assert gh.nearest_addressable(lines, 11, count=2) == [10, 12]


def test_ensure_marker_is_idempotent():
    once = gh.ensure_marker("hello")
    assert once.startswith("> **From Claude:**")
    assert gh.ensure_marker(once) == once


def test_find_duplicates_matches_marker_path_line():
    comments = [
        {"id": 1, "body": "> **From Claude:** x", "path": "api.py", "line": 11},
        {"id": 2, "body": "human", "path": "api.py", "line": 11},
        {"id": 3, "body": "> **From Claude:** y", "path": "api.py", "line": 99},
    ]
    assert gh.find_duplicates(comments, "api.py", 11) == [1]


def test_load_items_reads_manifest(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"file": "api.py", "line": 11, "body": "hi"}]))
    args = type("A", (), {"manifest": str(manifest), "general": False, "target": None})()
    assert gh.load_items(args) == [{"path": "api.py", "line": 11, "body": "hi"}]


def test_check_items_is_all_or_nothing():
    index = {"api.py": gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])}
    items = [
        {"path": "api.py", "line": 11, "body": "clean"},
        {"path": "missing.py", "line": 5, "body": "no such file"},
        {"path": "api.py", "line": 999, "body": "no such line"},
    ]

    ready, problems = gh.check_items(items, index, [], allow_duplicate=False)

    assert len(ready) == 1
    assert ready[0]["path"] == "api.py" and ready[0]["line"] == 11
    assert ready[0]["anchor"] == 11
    assert len(problems) == 2
    assert any("missing.py" in p and "not in this PR's diff" in p for p in problems)
    assert any("api.py:999" in p for p in problems)


def test_check_items_blocks_duplicate_unless_allowed():
    index = {"api.py": gh.parse_diff_lines(gh.split_files(PR_DIFF)["api.py"])}
    items = [{"path": "api.py", "line": 11, "body": "clean"}]
    comments = [{"id": 42, "body": "> **From Claude:** x", "path": "api.py", "line": 11}]

    ready, problems = gh.check_items(items, index, comments, allow_duplicate=False)
    assert ready == []
    assert len(problems) == 1
    assert "already has a From Claude comment" in problems[0]

    ready, problems = gh.check_items(items, index, comments, allow_duplicate=True)
    assert len(ready) == 1
    assert problems == []
