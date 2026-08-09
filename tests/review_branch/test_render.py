# ABOUTME: tests for render_html composition and the render subcommand
# ABOUTME: covers cards, escaping, diff links, asset inlining, baked state, git commit

import json

import pytest

import review_tool

REVIEW_TOML = """
[review]
title = "MR 124 review - <refs>"
vcs = "glab"
number = 124
url = "https://gitlab.example.com/g/p/-/merge_requests/124"
source_branch = "feat"
target_branch = "main"
commits = 4
files = "20 (+1752 / -43)"

[overall]
body = "Overall with `code`."

[[assets]]
type = "svg"
path = "diagram.svg"
caption = "Flow"

[[findings]]
id = "f1"
severity = "high"
title = "Bad <validation>"
file = "api.py"
lines = "10-20"
lenses = ["security"]
body = "Explanation."
snippet = "if x < 1: pass"
fix = "Clamp it."
comment = "Draft one."
anchor = "api.py:20"

[[findings]]
id = "f2"
severity = "info"
title = "Context only"
file = "b.py"
body = "FYI."
commentable = false

[[findings]]
id = "f3"
severity = "high"
title = "Already posted"
file = "c.py"
lines = "7"
body = "Posted earlier."
comment = "Posted draft."
posted_url = "https://gitlab.example.com/note/42"
posted_at = "2026-08-08T00:00:00Z"
posted_body = "Final posted text."

[[coverage]]
surface = "API 422"
covered = ""
gap = "f1"
"""


@pytest.fixture
def round_dir(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-124" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(REVIEW_TOML)
    (d / "diagram.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><title>seq</title></svg>')
    (d / "state.json").write_text(
        json.dumps({"findings": {"f1": {"disposition": "post", "note": "soften", "note_rev": 0}}})
    )
    return d


def test_render_html_composition(round_dir):
    page = review_tool.render_html(round_dir, served=True)
    assert "MR 124 review - &lt;refs&gt;" in page          # escaped title
    assert 'data-fid="f1"' in page and 'data-rev="1"' in page
    assert "diffs#diff-content-" in page                    # diff link
    assert "<title>seq</title>" in page                     # svg inlined
    assert "if x &lt; 1: pass" in page                      # snippet escaped
    assert 'class="post-chk" checked' in page               # post toggle checked from state
    assert '"served": true' in page
    assert "API 422" in page                                # coverage table
    assert 'id="save-status"' in page                        # always-visible save-status indicator
    assert 'id="index-link"' in page and 'href="/"' in page  # link back to the daemon index


def test_f2_has_no_comment_area(round_dir):
    page = review_tool.render_html(round_dir, served=True)
    # slice from f2's card to the next h2 (the coverage table heading)
    f2_chunk = page.split('data-fid="f2"')[1].split("<h2>")[0]
    assert "textarea" not in f2_chunk


def test_posted_finding_renders_frozen(round_dir):
    page = review_tool.render_html(round_dir, served=True)
    f3_chunk = page.split('data-fid="f3"')[1].split("<h2>")[0]
    assert 'badge posted' in f3_chunk
    assert "https://gitlab.example.com/note/42" in f3_chunk
    assert "Final posted text." in f3_chunk
    assert "textarea" not in f3_chunk
    assert "comment-view" not in f3_chunk


def test_comment_view_renders_markdown_and_textarea_carries_raw_source(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-21" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(
        '''
[review]
title = "Comment markdown"

[[findings]]
id = "f1"
severity = "med"
title = "Has markdown comment"
file = "a.py"
lines = "1"
body = "x"
comment = "Use `x` here"
'''
    )
    page = review_tool.render_html(d, served=True)
    assert '<div class="comment-view" tabindex="0">' in page
    assert "<code>x</code>" in page
    assert '<textarea class="comment" hidden>Use `x` here</textarea>' in page


def test_post_toggle_unchecked_by_default(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-20" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(
        '''
[review]
title = "Toggle default"

[[findings]]
id = "f1"
severity = "med"
title = "No disposition yet"
file = "a.py"
lines = "1"
body = "x"
comment = "Draft."
'''
    )
    page = review_tool.render_html(d, served=True)
    assert 'class="post-chk"' in page
    assert 'class="post-chk" checked' not in page


def test_stale_note_renders_applied_div(round_dir):
    page = review_tool.render_html(round_dir, served=True)
    f1_chunk = page.split('data-fid="f1"')[1].split('data-fid="f2"')[0]
    assert 'class="applied"' in f1_chunk
    assert "applied: soften" in f1_chunk
    assert 'class="note" placeholder="tell Claude how to adjust this"></textarea>' in f1_chunk


def test_summary_shows_med_zero_hides_low_zero(round_dir):
    page = review_tool.render_html(round_dir, served=True)
    assert '<div class="num high">2</div>' in page
    assert '<div class="num med">0</div>' in page
    assert 'num low' not in page
    assert '<div class="num info">1</div>' in page


def test_malicious_severity_and_url_are_neutralized(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-13" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(
        '''
[review]
title = "Injection attempt"

[[findings]]
id = "f1"
severity = 'x" onmouseover="y'
title = "Bad severity"
file = "a.py"
lines = "1"
body = "x"
comment = "Draft."
posted_url = "javascript:alert(1)"
posted_at = "2026-08-08T00:00:00Z"
posted_body = "final"
'''
    )
    page = review_tool.render_html(d, served=True)
    assert '<span class="badge x" onmouseover="y">' not in page
    assert '<div class="finding x" onmouseover="y"' not in page
    assert 'class="badge info"' in page
    assert 'href="#">posted</a>' in page


def test_asset_path_escaping_round_dir_raises(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-14" / "round-1"
    d.mkdir(parents=True)
    (d.parent / "secret.txt").write_text("shh")
    (d / "review.toml").write_text(
        '''
[review]
title = "Escaping asset"

[[assets]]
type = "html"
path = "../secret.txt"
'''
    )
    with pytest.raises(SystemExit):
        review_tool.render_html(d, served=True)


def test_unknown_severity_renders_without_raising(env):
    d = review_tool.data_root() / "proj-abcd" / "mr-9" / "round-1"
    d.mkdir(parents=True)
    (d / "review.toml").write_text(
        """
[review]
title = "Odd severity review"

[[findings]]
id = "f1"
severity = "medium"
title = "Weird severity value"
file = "a.py"
lines = "1"
body = "x"
comment = "Draft."
"""
    )
    page = review_tool.render_html(d, served=True)
    assert "Weird severity value" in page


def test_cmd_render_writes_file_and_commits(round_dir, capsys):
    assert review_tool.main(["render", str(round_dir)]) == 0
    out_path = round_dir / "review.html"
    assert out_path.exists()
    page = out_path.read_text()
    assert '"served": false' in page
    log = review_tool.git(review_tool.data_root(), "log", "--oneline")
    assert "proj-abcd mr-124 round-1: render" in log
    assert str(out_path) in capsys.readouterr().out
