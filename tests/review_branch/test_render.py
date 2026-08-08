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
    assert 'name="dispo-f1"' in page and "checked" in page  # disposition radio state
    assert '"served": true' in page
    assert "API 422" in page                                # coverage table


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


def test_cmd_render_writes_file_and_commits(round_dir, capsys):
    assert review_tool.main(["render", str(round_dir)]) == 0
    out_path = round_dir / "review.html"
    assert out_path.exists()
    page = out_path.read_text()
    assert '"served": false' in page
    log = review_tool.git(review_tool.data_root(), "log", "--oneline")
    assert "proj-abcd mr-124 round-1: render" in log
    assert str(out_path) in capsys.readouterr().out
