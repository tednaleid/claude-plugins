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


def test_diff_link_rejects_non_http_url():
    meta = {"vcs": "glab", "url": "javascript:alert(1)//"}
    assert review_tool.diff_link(meta, "a.py", 1) is None


@pytest.mark.parametrize(
    "value",
    [
        "Yes, and it is the first in this series.",
        "No, nothing.",
        "Yep; the grant chips gain a level.",
        "None of it reaches a user today.",
        "Not really, the column is inert.",
        "It does not change anything today.",
        "It isn't visible anywhere yet.",
    ],
)
def test_tldr_warns_on_answer_shaped_openers(value):
    warnings = review_tool.tldr_warnings({"behavior_change": value})
    assert len(warnings) == 1
    assert "behavior_change" in warnings[0] and "Today" in warnings[0]


@pytest.mark.parametrize(
    "value",
    [
        "No user-visible change today; the column is written but unread.",
        "Nothing changes for any user. Every row backfills to read-write.",
        "Administrators gain a level control in Grant Management.",
        "None but the migration touches production data.",
        "Item counts now exclude archived rows.",
    ],
)
def test_tldr_does_not_warn_on_prose_that_merely_starts_with_a_negative(value):
    assert review_tool.tldr_warnings({"behavior_change": value}) == []


def test_tldr_warns_per_field_and_ignores_non_strings():
    warnings = review_tool.tldr_warnings(
        {"what": "Yes, it lands.", "why": "The column was missing.", "scope": False}
    )
    assert [w.split()[1] for w in warnings] == ["what"]


def test_render_prints_tldr_warning_to_stderr(env, capsys):
    d = review_tool.data_root() / "proj-abcd" / "mr-1" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(
        '[review]\ntitle = "t"\n\n[tldr]\nbehavior_change = "No, nothing."\n'
    )
    review_tool.cmd_render(d)
    captured = capsys.readouterr()
    assert "warning: [tldr] behavior_change opens with 'No,'" in captured.err
    assert (d / "review.html").exists()


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
