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
