# ABOUTME: tests for the pure compose() function - HTML string composition with no I/O
# ABOUTME: calls compose() directly with plain in-memory dicts, no data root or tmp files

import json

import review_tool


def test_default_disposition_leaves_post_toggle_unchecked():
    review = {
        "review": {"title": "t"},
        "findings": [
            {"id": "f1", "severity": "med", "title": "T", "file": "a.py", "lines": "1", "body": "x", "comment": "Draft."}
        ],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert 'class="post-chk"' in page
    assert 'class="post-chk" checked' not in page


def test_control_row_places_post_toggle_before_collapse_body():
    review = {
        "review": {"title": "t"},
        "findings": [
            {"id": "f1", "severity": "med", "title": "T", "file": "a.py", "lines": "1", "body": "x", "comment": "Draft."}
        ],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert page.index('class="post-chk"') < page.index('<div class="collapse-body">')


def test_posted_finding_renders_frozen():
    review = {
        "review": {"title": "t"},
        "findings": [
            {
                "id": "f1",
                "severity": "high",
                "title": "T",
                "file": "a.py",
                "lines": "1",
                "body": "x",
                "comment": "Draft.",
                "posted_url": "https://example.com/note/1",
                "posted_body": "Final text.",
            }
        ],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    f1_chunk = page.split('data-fid="f1"')[1].split('<div id="kbd-help"')[0]
    assert "badge posted" in f1_chunk
    assert "Final text." in f1_chunk
    assert "textarea" not in f1_chunk
    assert "comment-view" not in f1_chunk


def test_baked_state_echoes_served_route_token_inputs():
    review = {"review": {"title": "t"}, "findings": []}
    state = {"findings": {"f1": {"disposition": "post"}}}
    page = review_tool.compose(review, state, "", "my/route/here", "abc123tok", False)
    baked_json = page.split("window.BAKED = ")[1].split(";</script>")[0]
    baked = json.loads(baked_json)
    assert baked == {"served": False, "route": "my/route/here", "token": "abc123tok", "state": state}


def test_unknown_severity_does_not_raise():
    review = {
        "review": {"title": "t"},
        "findings": [{"id": "f1", "severity": "weird", "title": "T", "file": "a.py", "lines": "1", "body": "x"}],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert 'class="badge info"' in page


def test_finding_body_markdown_is_rendered_and_escaped():
    review = {
        "review": {"title": "t"},
        "findings": [
            {
                "id": "f1",
                "severity": "low",
                "title": "T",
                "file": "a.py",
                "lines": "1",
                "body": "Use `<script>` carefully.",
            }
        ],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert "<code>&lt;script&gt;</code>" in page


def test_assets_html_input_is_embedded_verbatim():
    review = {"review": {"title": "t"}, "findings": []}
    page = review_tool.compose(review, {"findings": {}}, "<figure>marker-xyz</figure>", "route", "tok", True)
    assert "<figure>marker-xyz</figure>" in page


def test_compose_never_touches_filesystem_or_data_root(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("compose must not touch the filesystem or data root")

    monkeypatch.setattr(review_tool, "data_root", boom)
    monkeypatch.setattr(review_tool, "route_for", boom)
    monkeypatch.setattr(review_tool, "version_token", boom)
    monkeypatch.setattr(review_tool, "assets_html", boom)
    review = {"review": {"title": "t"}, "findings": []}
    review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)


def test_minor_notes_render_in_collapsed_section_without_post_toggle():
    review = {
        "review": {"title": "t"},
        "findings": [],
        "minor": [
            {"lens": "naming", "file": "a.py", "line": "12", "note": "shadowed `x`"},
        ],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert "<details" in page and "Minor notes (1)" in page
    assert "a.py:12" in page and "shadowed" in page
    # the minor block itself carries no finding controls
    start = page.index('<details class="minor"')
    block = page[start:page.index("</details>", start)]
    assert "data-fid" not in block and "post-chk" not in block


def test_summary_counts_minor_separately_from_findings():
    review = {
        "review": {"title": "t"},
        "findings": [{"id": "f1", "severity": "high", "title": "boom", "file": "a.py"}],
        "minor": [{"lens": "naming", "file": "a.py", "note": "n1"},
                  {"lens": "coverage", "file": "b.py", "note": "n2"}],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert '<div class="num low">2</div>' in page  # the Minor notes card shows 2


def test_finding_also_list_renders_extra_sites():
    review = {
        "review": {"title": "t"},
        "findings": [{"id": "f1", "severity": "high", "title": "log interp",
                      "file": "postgres.py", "lines": "110",
                      "also": ["memory.py:79", "omni_projects.py:201"]}],
    }
    page = review_tool.compose(review, {"findings": {}}, "", "route", "tok", True)
    assert "memory.py:79" in page and "omni_projects.py:201" in page
