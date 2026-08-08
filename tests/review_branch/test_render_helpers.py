# ABOUTME: tests for markdown, escaping, diff-link, version-token, and route helpers
# ABOUTME: covers glab/gh anchor formats, local mode, token change on write, route validation

import hashlib

import pytest

import review_tool


def test_md_html_renders_inline_code():
    assert "<code>x</code>" in review_tool.md_html("has `x` in it")


def test_md_html_escapes_raw_html():
    rendered = review_tool.md_html("<script>alert(1)</script>")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_md_html_still_renders_table():
    rendered = review_tool.md_html("| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "<table>" in rendered


def test_esc_escapes_angle_brackets_and_quotes():
    assert review_tool.esc('<a href="x">') == "&lt;a href=&quot;x&quot;&gt;"


def test_diff_link_glab():
    meta = {"vcs": "glab", "url": "https://gitlab.example.com/g/p/-/merge_requests/9"}
    link = review_tool.diff_link(meta, "runner/api.py", 121)
    sha = hashlib.sha1(b"runner/api.py").hexdigest()
    assert link == f"{meta['url']}/diffs#diff-content-{sha}"


def test_diff_link_gh_includes_right_line():
    meta = {"vcs": "gh", "url": "https://github.com/o/r/pull/42"}
    link = review_tool.diff_link(meta, "runner/api.py", 121)
    sha = hashlib.sha256(b"runner/api.py").hexdigest()
    assert link == f"{meta['url']}/files#diff-{sha}R121"


def test_diff_link_local_is_none():
    assert review_tool.diff_link({"vcs": "local"}, "a.py", 1) is None


def test_version_token_changes_on_state_write(tmp_path):
    d = tmp_path / "round-1"
    d.mkdir()
    (d / "review.toml").write_text('[review]\ntitle = "t"\n')
    t1 = review_tool.version_token(d)
    (d / "state.json").write_text('{"findings": {}}')
    assert review_tool.version_token(d) != t1


def test_route_for_requires_data_root(env, tmp_path):
    d = review_tool.data_root() / "proj-abcd" / "mr-1" / "round-1"
    d.mkdir(parents=True)
    assert review_tool.route_for(d) == "proj-abcd/mr-1/round-1"
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(SystemExit):
        review_tool.route_for(outside)
