# ABOUTME: tests for drawio_tool contrast/overflow/overlap/escaping lint checks,
# ABOUTME: style and label parsing, page enumeration, and export index validation
import json
from pathlib import Path

import pytest

import drawio_tool as dt

PLUGIN_JSON = (
    Path(__file__).resolve().parents[2]
    / "plugins" / "drawio" / ".claude-plugin" / "plugin.json"
)
EXAMPLE = (
    Path(__file__).resolve().parents[2]
    / "plugins" / "drawio" / "skills" / "drawio" / "examples" / "palette-sheet.drawio"
)

DARK_BG = "#0f1117"


def diagram(cells, background=DARK_BG, name="Page"):
    """A one-page .drawio document wrapping the given cell XML."""
    bg = f' background="{background}"' if background else ""
    return f"""<mxfile host="test">
  <diagram id="d1" name="{name}">
    <mxGraphModel dx="800" dy="600" pageWidth="800" pageHeight="600"{bg}>
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        {cells}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
"""


def box(cell_id, style, value="Some label text", x=0, y=0, w=200, h=60, parent="1"):
    return (
        f'<mxCell id="{cell_id}" value="{value}" style="{style}" vertex="1" parent="{parent}">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry" /></mxCell>'
    )


def lint_source(tmp_path, source, name="d.drawio"):
    path = tmp_path / name
    path.write_text(source)
    return dt.lint_file(path)


def checks(findings):
    return sorted({f.check for f in findings})


def ids(findings, check):
    return sorted(f.cell for f in findings if f.check == check)


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("#ffffff", (255, 255, 255)),
        ("#000", (0, 0, 0)),
        ("#14243F", (20, 36, 63)),
        ("none", None),
        ("default", None),
        ("", None),
        (None, None),
        ("#12345", None),
        ("#gggggg", None),
    ],
)
def test_parse_color(value, expected):
    assert dt.parse_color(value) == expected


def test_contrast_ratio_extremes():
    white, black = (255, 255, 255), (0, 0, 0)
    assert dt.contrast_ratio(white, black) == pytest.approx(21.0, abs=0.01)
    assert dt.contrast_ratio(white, white) == pytest.approx(1.0, abs=0.01)


def test_contrast_ratio_is_symmetric():
    a, b = (20, 36, 63), (232, 237, 245)
    assert dt.contrast_ratio(a, b) == pytest.approx(dt.contrast_ratio(b, a))


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def test_parse_style_splits_pairs_and_bare_tokens():
    style = dt.parse_style("swimlane;startSize=34;fillColor=#16202e;html=1;")
    assert style["swimlane"] is True
    assert style["startSize"] == "34"
    assert style["fillColor"] == "#16202e"


def test_parse_style_tolerates_empty():
    assert dt.parse_style("") == {}
    assert dt.parse_style(None) == {}


def test_plain_text_strips_markup():
    # The XML parser has already turned the stored &lt;b&gt; into a real tag.
    assert dt.plain_text("<b>Browser</b> and client") == "Browser and client"


def test_plain_text_collapses_breaks_and_whitespace():
    assert dt.plain_text("a<br>b   c") == "a b c"


def test_plain_text_measures_double_escaped_markup_as_visible_characters():
    """`&lt;b&gt;` renders as the literal text `<b>`, so it counts toward width."""
    assert dt.plain_text("&lt;b&gt;Bold&lt;/b&gt;") == "<b>Bold</b>"


def test_plain_text_of_empty_is_empty():
    assert dt.plain_text(None) == ""
    assert dt.plain_text("") == ""


# --------------------------------------------------------------------------
# contrast
# --------------------------------------------------------------------------


def test_unset_font_color_on_dark_fill_is_an_error(tmp_path):
    """Export resolves an unset fontColor to black, which vanishes on a dark fill."""
    src = diagram(box("b", "rounded=1;fillColor=#14161c;strokeColor=#6f9bf0;"))
    findings = lint_source(tmp_path, src)
    assert ids(findings, "contrast") == ["b"]
    assert findings[0].level == "error"


def test_unset_font_color_on_pale_fill_is_an_error(tmp_path):
    """The desktop app resolves it to white, which vanishes on a pale fill.

    The same missing attribute breaks in opposite contexts, so the worst case is
    what matters.
    """
    src = diagram(box("b", "rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"))
    assert ids(lint_source(tmp_path, src), "contrast") == ["b"]


def test_explicit_font_color_with_good_contrast_passes(tmp_path):
    src = diagram(box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;"))
    assert ids(lint_source(tmp_path, src), "contrast") == []


def test_explicit_font_color_matching_the_fill_is_an_error(tmp_path):
    src = diagram(box("b", "rounded=1;fillColor=#14243f;fontColor=#14243f;"))
    assert ids(lint_source(tmp_path, src), "contrast") == ["b"]


def test_transparent_fill_is_judged_against_the_page_background(tmp_path):
    dark = diagram(box("b", "rounded=1;fillColor=none;fontColor=#101010;"))
    assert ids(lint_source(tmp_path, dark), "contrast") == ["b"]

    light = diagram(
        box("b", "rounded=1;fillColor=none;fontColor=#101010;"), background="#ffffff"
    )
    assert ids(lint_source(tmp_path, light), "contrast") == []


def test_missing_fill_defaults_to_white_not_transparent(tmp_path):
    """A vertex with no fillColor renders white, so white text on it is invisible."""
    src = diagram(box("b", "rounded=1;fontColor=#ffffff;"))
    assert ids(lint_source(tmp_path, src), "contrast") == ["b"]


def test_white_edge_label_without_background_is_an_error(tmp_path):
    """Edge labels get an opaque white background by default: 1.00:1."""
    edge = (
        '<mxCell id="e" value="OIDC" style="html=1;fontColor=#ffffff;" edge="1" '
        'parent="1"><mxGeometry relative="1" as="geometry" /></mxCell>'
    )
    findings = lint_source(tmp_path, diagram(edge))
    assert ids(findings, "contrast") == ["e"]
    assert "1.00:1" in findings[0].message


def test_edge_label_with_matching_background_passes(tmp_path):
    edge = (
        '<mxCell id="e" value="OIDC" style="html=1;fontColor=#e8edf5;'
        'labelBackgroundColor=#0f1117;" edge="1" parent="1">'
        '<mxGeometry relative="1" as="geometry" /></mxCell>'
    )
    assert ids(lint_source(tmp_path, diagram(edge)), "contrast") == []


def test_edge_label_background_none_falls_back_to_the_page(tmp_path):
    edge = (
        '<mxCell id="e" value="OIDC" style="html=1;fontColor=#e8edf5;'
        'labelBackgroundColor=none;" edge="1" parent="1">'
        '<mxGeometry relative="1" as="geometry" /></mxCell>'
    )
    assert ids(lint_source(tmp_path, diagram(edge)), "contrast") == []


def test_unlabelled_cell_is_not_checked(tmp_path):
    src = diagram(box("b", "rounded=1;fillColor=#14161c;", value=""))
    assert ids(lint_source(tmp_path, src), "contrast") == []


def test_non_hex_colors_are_skipped_rather_than_guessed(tmp_path):
    src = diagram(box("b", "rounded=1;fillColor=red;fontColor=darkred;"))
    assert ids(lint_source(tmp_path, src), "contrast") == []


# --------------------------------------------------------------------------
# overflow
# --------------------------------------------------------------------------


def test_long_label_in_a_small_box_warns(tmp_path):
    src = diagram(
        box("b", "rounded=1;whiteSpace=wrap;fontColor=#e8edf5;fillColor=#14243f;",
            value="x" * 400, w=120, h=40)
    )
    findings = lint_source(tmp_path, src)
    assert ids(findings, "overflow") == ["b"]
    assert [f.level for f in findings if f.check == "overflow"] == ["warn"]


def test_overflow_hidden_escalates_to_error(tmp_path):
    """Spilling text is visible in a render; truncated text is not."""
    src = diagram(
        box("b", "rounded=1;whiteSpace=wrap;overflow=hidden;fontColor=#e8edf5;"
                 "fillColor=#14243f;",
            value="x" * 400, w=120, h=40)
    )
    findings = [f for f in lint_source(tmp_path, src) if f.check == "overflow"]
    assert [f.level for f in findings] == ["error"]


def test_label_that_fits_does_not_warn(tmp_path):
    src = diagram(
        box("b", "rounded=1;whiteSpace=wrap;fontColor=#e8edf5;fillColor=#14243f;",
            value="Short", w=200, h=60)
    )
    assert ids(lint_source(tmp_path, src), "overflow") == []


def test_swimlane_overflow_measures_the_title_bar(tmp_path):
    """A swimlane's label lives in its title bar, not its 400px body."""
    src = diagram(
        box("b", "swimlane;startSize=30;whiteSpace=wrap;fontColor=#e8edf5;"
                 "fillColor=#16202e;",
            value="A swimlane title that is far too long to fit in this narrow lane",
            w=120, h=400)
    )
    assert ids(lint_source(tmp_path, src), "overflow") == ["b"]


# --------------------------------------------------------------------------
# overlap
# --------------------------------------------------------------------------


def test_backdrop_drawn_before_its_contents_is_not_an_overlap(tmp_path):
    """A band rectangle under its boxes is the normal way to draw layers."""
    src = diagram(
        box("band", "rounded=0;fillColor=#16202e;fontColor=#e8edf5;",
            value="Layer 1", x=0, y=0, w=600, h=200)
        + box("inner", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              x=40, y=40, w=200, h=60)
    )
    assert ids(lint_source(tmp_path, src), "overlap") == []


def test_shape_drawn_over_an_earlier_one_is_an_error(tmp_path):
    """Same geometry, reversed order: the band now erases its contents."""
    src = diagram(
        box("inner", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
            x=40, y=40, w=200, h=60)
        + box("band", "rounded=0;fillColor=#16202e;fontColor=#e8edf5;",
              value="Layer 1", x=0, y=0, w=600, h=200)
    )
    findings = [f for f in lint_source(tmp_path, src) if f.check == "overlap"]
    assert [(f.cell, f.level) for f in findings] == [("inner", "error")]


def test_partial_overlap_warns(tmp_path):
    src = diagram(
        box("a", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;", x=0, y=0, w=200, h=100)
        + box("b", "rounded=1;fillColor=#152a1d;fontColor=#e8edf5;", x=100, y=0, w=200, h=100)
    )
    findings = [f for f in lint_source(tmp_path, src) if f.check == "overlap"]
    assert [(f.cell, f.level) for f in findings] == [("a", "warn")]


def test_adjacent_shapes_do_not_overlap(tmp_path):
    src = diagram(
        box("a", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;", x=0, y=0, w=200, h=100)
        + box("b", "rounded=1;fillColor=#152a1d;fontColor=#e8edf5;", x=200, y=0, w=200, h=100)
    )
    assert ids(lint_source(tmp_path, src), "overlap") == []


def test_cells_in_different_parents_are_not_compared(tmp_path):
    """Container children use relative coordinates, so the numbers are not comparable."""
    src = diagram(
        box("band", "swimlane;startSize=30;fillColor=#16202e;fontColor=#e8edf5;",
            value="Band", x=0, y=0, w=600, h=200)
        + box("child", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              x=0, y=0, w=200, h=60, parent="band")
    )
    assert ids(lint_source(tmp_path, src), "overlap") == []


def test_small_shape_straddling_a_border_warns(tmp_path):
    """A step marker hanging off a band covers too little of it to register as
    an overlap, but the straddle is the whole defect."""
    src = diagram(
        box("band", "rounded=0;fillColor=#16202e;fontColor=#e8edf5;",
            value="Layer", x=0, y=0, w=800, h=300)
        + box("marker", "ellipse;fillColor=#d9a441;fontColor=#0f1117;",
              value="3", x=100, y=280, w=56, h=56)
    )
    findings = lint_source(tmp_path, src)
    assert ids(findings, "straddle") == ["marker"]


def test_shape_fully_inside_does_not_straddle(tmp_path):
    src = diagram(
        box("band", "rounded=0;fillColor=#16202e;fontColor=#e8edf5;",
            value="Layer", x=0, y=0, w=800, h=300)
        + box("marker", "ellipse;fillColor=#d9a441;fontColor=#0f1117;",
              value="3", x=100, y=100, w=56, h=56)
    )
    assert ids(lint_source(tmp_path, src), "straddle") == []


# --------------------------------------------------------------------------
# underfilled
# --------------------------------------------------------------------------


def test_tall_sparse_box_warns(tmp_path):
    """The inverse of overflow: a box several times taller than its copy."""
    src = diagram(
        box("b", "rounded=1;whiteSpace=wrap;fillColor=#14243f;fontColor=#e8edf5;",
            value="Two short lines of copy.", w=600, h=300)
    )
    findings = lint_source(tmp_path, src)
    assert ids(findings, "underfilled") == ["b"]
    assert [f.level for f in findings if f.check == "underfilled"] == ["warn"]


def test_well_filled_box_passes(tmp_path):
    src = diagram(
        box("b", "rounded=1;whiteSpace=wrap;fillColor=#14243f;fontColor=#e8edf5;",
            value="x" * 900, w=600, h=200)
    )
    assert ids(lint_source(tmp_path, src), "underfilled") == []


def test_short_box_is_exempt_so_badges_do_not_trip_it(tmp_path):
    src = diagram(
        box("b", "rounded=1;whiteSpace=wrap;fillColor=#14243f;fontColor=#e8edf5;",
            value="3", w=56, h=56)
    )
    assert ids(lint_source(tmp_path, src), "underfilled") == []


def test_a_container_is_sized_for_its_children_not_its_label(tmp_path):
    src = diagram(
        box("band", "swimlane;startSize=34;fillColor=#16202e;fontColor=#e8edf5;",
            value="Layer 1", x=0, y=0, w=800, h=400)
        + box("child", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Inside", x=40, y=60, w=200, h=72, parent="band")
    )
    assert ids(lint_source(tmp_path, src), "underfilled") == []


# --------------------------------------------------------------------------
# container padding
# --------------------------------------------------------------------------


def test_child_flush_against_its_container_warns(tmp_path):
    src = diagram(
        box("band", "rounded=0;fillColor=#16202e;fontColor=#e8edf5;",
            value="Layer", x=0, y=0, w=800, h=300)
        + box("child", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Inside", x=0, y=0, w=200, h=72, parent="band")
    )
    findings = lint_source(tmp_path, src)
    assert ids(findings, "container-padding") == ["child"]


def test_inset_child_passes(tmp_path):
    src = diagram(
        box("band", "rounded=0;fillColor=#16202e;fontColor=#e8edf5;",
            value="Layer", x=0, y=0, w=800, h=300)
        + box("child", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Inside", x=40, y=40, w=200, h=72, parent="band")
    )
    assert ids(lint_source(tmp_path, src), "container-padding") == []


def test_swimlane_top_padding_is_measured_from_the_title_bar(tmp_path):
    """y=40 clears the frame but sits only 6px under a 34px title bar."""
    src = diagram(
        box("band", "swimlane;startSize=34;fillColor=#16202e;fontColor=#e8edf5;",
            value="Layer", x=0, y=0, w=800, h=300)
        + box("child", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Inside", x=40, y=40, w=200, h=72, parent="band")
    )
    findings = lint_source(tmp_path, src)
    assert ids(findings, "container-padding") == ["child"]
    assert "top edge" in findings[0].message


# --------------------------------------------------------------------------
# backdrop
# --------------------------------------------------------------------------


def test_dark_page_without_a_backdrop_rectangle_warns(tmp_path):
    src = diagram(
        box("t", "text;html=1;fontColor=#e8edf5;", value="Title", x=20, y=20, w=300, h=30)
        + box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Box", x=20, y=80, w=300, h=60)
    )
    findings = lint_source(tmp_path, src)
    assert ids(findings, "no-backdrop") == ["t"]


def test_backdrop_rectangle_satisfies_the_check(tmp_path):
    src = diagram(
        box("bg", "rounded=0;fillColor=#0f1117;strokeColor=none;", value="",
            x=0, y=0, w=400, h=200)
        + box("t", "text;html=1;fontColor=#e8edf5;", value="Title", x=20, y=20, w=300, h=30)
        + box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Box", x=20, y=80, w=300, h=60)
    )
    assert ids(lint_source(tmp_path, src), "no-backdrop") == []


def test_backdrop_must_actually_cover_the_content(tmp_path):
    """A page whose content outgrew its declared size gets a bright strip."""
    src = diagram(
        box("bg", "rounded=0;fillColor=#0f1117;strokeColor=none;", value="",
            x=0, y=0, w=200, h=200)
        + box("t", "text;html=1;fontColor=#e8edf5;", value="Title", x=20, y=20, w=300, h=30)
        + box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Box", x=20, y=80, w=300, h=60)
    )
    assert ids(lint_source(tmp_path, src), "no-backdrop") == ["bg"]


def test_transparent_first_shape_is_not_a_backdrop(tmp_path):
    src = diagram(
        box("bg", "rounded=0;fillColor=none;strokeColor=none;", value="",
            x=0, y=0, w=400, h=200)
        + box("t", "text;html=1;fontColor=#e8edf5;", value="Title", x=20, y=20, w=300, h=30)
        + box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
              value="Box", x=20, y=80, w=300, h=60)
    )
    assert ids(lint_source(tmp_path, src), "no-backdrop") == ["bg"]


def test_light_page_needs_no_backdrop(tmp_path):
    """White already matches every renderer's default, so there is nothing to lose."""
    src = diagram(
        box("t", "text;html=1;fontColor=#101010;", value="Title", x=20, y=20, w=300, h=30)
        + box("b", "rounded=1;fillColor=#e3edfb;fontColor=#101010;",
              value="Box", x=20, y=80, w=300, h=60),
        background="#ffffff",
    )
    assert ids(lint_source(tmp_path, src), "no-backdrop") == []


# --------------------------------------------------------------------------
# escaping, placeholders, structure
# --------------------------------------------------------------------------


def test_double_escaped_markup_is_an_error(tmp_path):
    src = diagram(
        box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
            value="&amp;lt;b&amp;gt;Bold&amp;lt;/b&amp;gt;")
    )
    assert ids(lint_source(tmp_path, src), "escaping") == ["b"]


def test_correctly_escaped_markup_passes(tmp_path):
    src = diagram(
        box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
            value="&lt;b&gt;Bold&lt;/b&gt; and &amp;amp; too")
    )
    assert ids(lint_source(tmp_path, src), "escaping") == []


def test_a_literal_less_than_is_not_flagged_as_double_escaping(tmp_path):
    """`a &lt; b` in the file is the correct way to label "a < b"."""
    src = diagram(
        box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;",
            value="latency &amp;lt; 100ms")
    )
    assert ids(lint_source(tmp_path, src), "escaping") == []


def test_malformed_xml_reports_one_actionable_finding(tmp_path):
    path = tmp_path / "bad.drawio"
    path.write_text(diagram(box("b", "rounded=1;", value="a < b")))
    findings = dt.lint_file(path)
    assert [f.check for f in findings] == ["xml"]
    assert "&lt;" in findings[0].message


# Ground truth for these cases came from screenshotting one probe file in the
# VS Code draw.io extension and measuring the glyph pixels. Rows A and B render
# dark grey there; C through H render correctly.


def test_bare_bold_warns(tmp_path):
    """Row A: <b> taking its colour from the cell's fontColor."""
    src = diagram(
        box("b", "rounded=1;fillColor=#1b2130;fontColor=#e8edf5;",
            value="&lt;b&gt;AAAA&lt;/b&gt; plain")
    )
    findings = lint_source(tmp_path, src)
    assert ids(findings, "uncolored-markup") == ["b"]
    assert [f.level for f in findings if f.check == "uncolored-markup"] == ["warn"]


def test_font_tag_wrapping_bold_still_warns(tmp_path):
    """Row B: an enclosing <font color> does not reach the <b>."""
    value = "&lt;font color=&quot;#e8edf5&quot;&gt;&lt;b&gt;BBBB&lt;/b&gt; tail&lt;/font&gt;"
    src = diagram(box("b", "rounded=1;fillColor=#1b2130;fontColor=#e8edf5;", value=value))
    assert ids(lint_source(tmp_path, src), "uncolored-markup") == ["b"]


def test_inline_color_on_the_bold_passes(tmp_path):
    """Row C: an inline style on the element outranks a stylesheet rule."""
    value = "&lt;b style=&quot;color:#e8edf5&quot;&gt;CCCC&lt;/b&gt; tail"
    src = diagram(box("b", "rounded=1;fillColor=#1b2130;fontColor=#e8edf5;", value=value))
    assert ids(lint_source(tmp_path, src), "uncolored-markup") == []


def test_span_font_weight_passes(tmp_path):
    """Row D: no <b> element exists, so no rule can target it."""
    value = "&lt;span style=&quot;font-weight:bold;color:#e8edf5&quot;&gt;DDDD&lt;/span&gt;"
    src = diagram(box("b", "rounded=1;fillColor=#1b2130;fontColor=#e8edf5;", value=value))
    assert ids(lint_source(tmp_path, src), "uncolored-markup") == []


def test_font_style_bold_passes(tmp_path):
    """Row E: whole-label bold via the cell style, no markup at all."""
    src = diagram(
        box("b", "rounded=1;fillColor=#1b2130;fontColor=#e8edf5;fontStyle=1;", value="EEEE")
    )
    assert ids(lint_source(tmp_path, src), "uncolored-markup") == []


@pytest.mark.parametrize("tag", ["i", "em", "strong", "u"])
def test_other_styled_tags_warn(tmp_path, tag):
    src = diagram(
        box("b", "rounded=1;fillColor=#1b2130;fontColor=#e8edf5;",
            value=f"&lt;{tag}&gt;text&lt;/{tag}&gt;")
    )
    assert ids(lint_source(tmp_path, src), "uncolored-markup") == ["b"]


def test_one_warning_per_cell_not_per_tag(tmp_path):
    value = "&lt;b&gt;one&lt;/b&gt; &lt;b&gt;two&lt;/b&gt; &lt;i&gt;three&lt;/i&gt;"
    src = diagram(box("b", "rounded=1;fillColor=#1b2130;fontColor=#e8edf5;", value=value))
    assert len([f for f in lint_source(tmp_path, src) if f.check == "uncolored-markup"]) == 1


@pytest.mark.parametrize("value", ["{{SERVICE_NAME}}", "{PLACEHOLDER}", "TODO name this"])
def test_unresolved_placeholders_are_errors(tmp_path, value):
    src = diagram(box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;", value=value))
    assert ids(lint_source(tmp_path, src), "placeholder") == ["b"]


def test_missing_page_background_warns(tmp_path):
    src = diagram(
        box("b", "rounded=1;fillColor=#14243f;fontColor=#e8edf5;"), background=None
    )
    findings = lint_source(tmp_path, src)
    assert [f.check for f in findings] == ["background"]
    assert findings[0].level == "warn"


def test_compressed_page_is_reported(tmp_path):
    src = """<mxfile host="test">
  <diagram id="d1" name="Squished">7VpZk9o4EP41VO0+DIVtjOFxYI7sVmZ3ajO12TxKtrBVIyxHFtf8+m3ZLR8YCJAJIVUJVaC+1Gp1fzqamOTPy8dbSYv0XsRMDJxhvBmQ64HjOL7rwZfmrJEz9YLIsBLJY9RrGA/8mSFziNwZj1nZUlRCCMWLNjMSec4i1eJRKcWyrTYVor1qQRPWYTxEVHS5//NYpXaHzrDh/8F4kmqvrTGSaqUmnB6/f7uPn4WkC0/nT/tNmn2zNufyRWiMwUqA+CqvJmO4zsWk1qUJVXOaEbwzu16lXLGHgkZmxSusOLQlas5AsqDpxKI3IEK5eIfsyG6mFtoDHTHF1PZjZg9Wdcy1ZAt10cyIVFyE9GKlkNZQZ81utnCzUyi5ovAHIWSKX/E1Rq1nHm4B3+jSyz7DXe70DXeXWNfnG/7bSc44wR9wLp1FpwTz+ntxo3AqdRPzz1TxKPjIhWKfBFmuxeOnTvj71pdWadV1jTaovnYc6M6znDwaQNwsWWTIhOQvFVo1SbCC7bU4v/5rWNfa3+/CyeeTdt5vE4d19OuruEsJ4Ho9y6q7bJ1gW4vJHKKtHtaxNJZTRdvT0/lU6uCg4/vxdF1lYVIMawf9ZuwXFY9BbfJfmMzhc/5J8zAxvFFTGhkkqQiuLnjXbjCUSTHLY6ZfDW2AsFOFXfl3hHz3z+dSKGb0zSjJdyRZWfz1YuT7Zg2sqcC1jhx4dU57NKUsHDBUuJDoU1v2wnAmoJt5nMTFYb/RGCP0Y4QVCcUcREl1yPGGoiO/gy4bhu4XKKcOoK8LKrz5hnJqAP0FTelASWiOd0nl2GnHU1zbXQXtLDJnsWCMxDeTHb+/Ba6eBQ//SzUZlEJXfPxrEZ8ai/BX9OJ2CGDVaFV9m9UutO/9SwFyzZlSj0aWEEmpBIkVi63xIsE0k4EnjhCPy1zSPa4tqJnU+++6zbc4hJ2vLKQ5Ldbb0qKgeQKMzWLdE1RVWy9J1O0mUb+bmDrDTx1MnbdQPTUCG4C2vHtcGqLPtn+D9V88NGsuCkT78CmSpKcpolmkyvW2p3wLBtHrEyDaWTFOgOMlbT29gmiIH0O2E9m3jr1WjXTIrjTx7DYUxNhrDwFRnFVztWtHbUJ0GtOKLTe2fN+P7EJoq5bGkGWTUXtEZuUxxUlBhr0DGZE64GbPRP1nyixnJ7RFm+Xx0kxaVLcx9m/9zHnZ3ijk8LqUpz+r2Ur//B9J71ODW9dCPFJdE7Y5+3rnkfvL78o0uBd/qFtDA9j95kfz8H4X4EYtu4G09q4EFCX7RXjm3F4EIU9dodBJfNM4jmYuGGyjmB68wIhVJTuoWZI+Zpj0/mgFuG0FIymTMLPmMbLu78GHUqfHpP6RzHl9SU3xXnFVKr0VmSTV/2/8kf9DstUvcEUw9d9YlOa1Zvj8FpuGXZfW4uzD7YSb8i+FoZFhBWvbYnPnHWDb/nuOveuGXhtEr49B22MtaNv2LuNvfR2XLuFqPnv/o+D9d9/vwsK6Zb8Z6M3ULMxs+G34gy8+/w8=</diagram>
</mxfile>
"""
    findings = lint_source(tmp_path, src)
    assert [f.check for f in findings] == ["compressed"]


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------


def test_read_pages_is_one_based_with_names(tmp_path):
    src = """<mxfile host="test">
  <diagram id="a" name="One"><mxGraphModel background="#000000"><root>
    <mxCell id="0" /><mxCell id="1" parent="0" /></root></mxGraphModel></diagram>
  <diagram id="b" name="Two"><mxGraphModel background="#000000"><root>
    <mxCell id="0" /><mxCell id="1" parent="0" /></root></mxGraphModel></diagram>
</mxfile>
"""
    path = tmp_path / "d.drawio"
    path.write_text(src)
    pages = dt.read_pages(path)
    assert [(i, name) for i, name, _, _ in pages] == [(1, "One"), (2, "Two")]


# --------------------------------------------------------------------------
# export argument validation
# --------------------------------------------------------------------------


def two_page_file(tmp_path):
    path = tmp_path / "d.drawio"
    path.write_text(
        """<mxfile host="test">
  <diagram id="a" name="One"><mxGraphModel background="#000000"><root>
    <mxCell id="0" /><mxCell id="1" parent="0" /></root></mxGraphModel></diagram>
  <diagram id="b" name="Two"><mxGraphModel background="#000000"><root>
    <mxCell id="0" /><mxCell id="1" parent="0" /></root></mxGraphModel></diagram>
</mxfile>
"""
    )
    return path


def test_export_rejects_page_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAWIO_BINARY", "/nonexistent")
    path = two_page_file(tmp_path)
    with pytest.raises(SystemExit, match="numbered from 1"):
        dt.main(["export", str(path), "--page", "0"])


def test_export_rejects_a_page_past_the_end(tmp_path, monkeypatch):
    """draw.io would exit 0 and silently render the last page instead."""
    monkeypatch.setenv("DRAWIO_BINARY", "/nonexistent")
    path = two_page_file(tmp_path)
    with pytest.raises(SystemExit, match="out of range: d.drawio has 2 page"):
        dt.main(["export", str(path), "--page", "3"])


def test_export_reports_a_missing_input(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAWIO_BINARY", "/nonexistent")
    with pytest.raises(SystemExit, match="does not exist"):
        dt.main(["export", str(tmp_path / "nope.drawio")])


# --------------------------------------------------------------------------
# shipped assets
# --------------------------------------------------------------------------


def test_bundled_example_is_clean():
    """The palette sheet is the reference output; it must pass its own linter."""
    assert dt.lint_file(EXAMPLE) == []


def test_version_matches_plugin_json():
    assert dt.VERSION == json.loads(PLUGIN_JSON.read_text())["version"]
