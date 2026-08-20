#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# ABOUTME: `drawio_tool` renders .drawio pages to PNG via the desktop app so an agent can Read its own diagram
# ABOUTME: also lints for defects a render cannot reveal: low contrast, overflow, overlap, bad escaping

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.2.0"  # SYNC_PLUGIN_VERSION kept in step with plugin.json by scripts/sync-marketplace.ts

# Where the Electron binary lives when `drawio` is not on PATH. The Homebrew
# cask adds a shim, but a .dmg install leaves only the bundle.
BINARY_CANDIDATES = (
    "/Applications/draw.io.app/Contents/MacOS/draw.io",
    "~/Applications/draw.io.app/Contents/MacOS/draw.io",
    "/usr/bin/drawio",
    "/usr/local/bin/drawio",
    "/opt/drawio/drawio",
)

# draw.io's defaults when a style omits the key, confirmed by exporting probes
# and sampling pixels. They are why an unstyled diagram is not neutral: a cell
# with no fillColor is white, and an edge label sits on an opaque white bar.
DEFAULT_FILL = "#ffffff"
DEFAULT_FONT = "#000000"
DEFAULT_EDGE_LABEL_BG = "#ffffff"
DEFAULT_PAGE_BG = "#ffffff"
DEFAULT_FONT_SIZE = 12.0

# WCAG AA for normal text. Text below this is not "a bit low" -- at ratios near
# 1 it is genuinely gone, which is the failure this linter exists to catch.
CONTRAST_FAIL = 3.0
CONTRAST_WARN = 4.5

# Helvetica-ish advance width and line box, as fractions of font size. Used only
# to estimate whether a label fits; draw.io never grows a box to make it fit.
CHAR_WIDTH_RATIO = 0.52
LINE_HEIGHT_RATIO = 1.35
VERTICAL_PADDING = 8.0

# A box several times taller than its copy reads as a failure to load. Only
# applied above a minimum height so badges and one-line chips do not trip it.
UNDERFILL_RATIO = 0.5
UNDERFILL_MIN_HEIGHT = 150.0

# Inset a container's children need before they stop looking flush.
CONTAINER_PADDING = 15.0

# A small shape hanging over the border of a larger one, as a fraction of the
# small shape. Between these bounds it straddles rather than sits inside.
STRADDLE_MIN = 0.05
STRADDLE_MAX = 0.95
STRADDLE_MAX_AREA_RATIO = 0.25

PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}|\{[A-Z][A-Z0-9_]{2,}\}|\bTODO\b|\bFIXME\b|\bXXX\b")
TAG_RE = re.compile(r"<[^>]+>")
ESCAPED_TAG_RE = re.compile(r"&lt;/?[a-zA-Z][^&]*&gt;")
STYLED_TAG_RE = re.compile(r"<(b|strong|i|em|u)\b([^>]*)>", re.IGNORECASE)
INLINE_COLOR_RE = re.compile(r"style\s*=\s*([\"'])[^\"']*\bcolor\s*:[^\"']*\1", re.IGNORECASE)


@dataclass
class Finding:
    level: str  # "error" or "warn"
    check: str
    page: str
    cell: str
    message: str

    def format(self, path):
        return f"{path}: {self.level}: [{self.check}] page {self.page!r} cell {self.cell!r}: {self.message}"


# --------------------------------------------------------------------------
# color
# --------------------------------------------------------------------------


def parse_color(value):
    """Hex color to an (r, g, b) tuple, or None when it is not a plain hex color.

    draw.io also accepts `none`, `default`, and named colors. Those resolve
    against the theme rather than the file, so contrast cannot be judged from
    the XML alone and the caller treats them as unknown.
    """
    if not value:
        return None
    v = value.strip().lower()
    if not v.startswith("#"):
        return None
    v = v[1:]
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6 or any(c not in "0123456789abcdef" for c in v):
        return None
    return tuple(int(v[i : i + 2], 16) for i in (0, 2, 4))


def relative_luminance(rgb):
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    a, b = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def parse_style(style):
    """draw.io style string to a dict. Bare tokens like `swimlane` map to True."""
    out = {}
    for part in (style or "").split(";"):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        out[key.strip()] = value.strip() if sep else True
    return out


def plain_text(value):
    """A cell's rendered text: unescape once, strip HTML, collapse whitespace.

    draw.io stores labels XML-escaped and then interprets the result as HTML,
    so `&lt;b&gt;Hi&lt;/b&gt;` renders as a bold "Hi" and measures as 2 chars.
    """
    if not value:
        return ""
    text = TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return " ".join(text.split())


def read_pages(path):
    """Every <diagram> in the file, as (index, name, mxGraphModel) 1-based."""
    tree = ET.parse(path)
    root = tree.getroot()
    diagrams = root.findall(".//diagram") if root.tag != "diagram" else [root]
    pages = []
    for i, d in enumerate(diagrams, start=1):
        model = d.find("mxGraphModel")
        pages.append((i, d.get("name") or f"page {i}", model, d))
    return pages


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------


def geometry_of(cell):
    geo = cell.find("mxGeometry")
    if geo is None:
        return None
    try:
        return (
            float(geo.get("x") or 0),
            float(geo.get("y") or 0),
            float(geo.get("width") or 0),
            float(geo.get("height") or 0),
        )
    except ValueError:
        return None


def check_contrast(page_name, cell, style, page_bg, findings):
    """Is this label actually legible against whatever sits behind it?

    Covers the whole family in one measurement: a filled box with no fontColor
    (black on near-black), a transparent box on a dark page, and white edge
    label text on draw.io's opaque white default label background.
    """
    text = plain_text(cell.get("value"))
    if not text:
        return

    is_edge = cell.get("edge") == "1"
    raw_font = style.get("fontColor")

    if is_edge:
        raw_bg = style.get("labelBackgroundColor")
        if raw_bg == "none":
            # No bar is drawn, so the label sits on the page with the edge line
            # running through it.
            backdrop, where = page_bg, "the page background (label background is none)"
        elif raw_bg:
            backdrop, where = parse_color(raw_bg), f"labelBackgroundColor {raw_bg}"
        else:
            backdrop, where = parse_color(DEFAULT_EDGE_LABEL_BG), "the default white edge label background"
    else:
        raw_fill = style.get("fillColor")
        if raw_fill == "none":
            backdrop, where = page_bg, "the page background (fill is none)"
        elif raw_fill:
            backdrop, where = parse_color(raw_fill), f"fillColor {raw_fill}"
        elif style.get("text") or style.get("label"):
            backdrop, where = page_bg, "the page background (unfilled text)"
        else:
            backdrop, where = parse_color(DEFAULT_FILL), "the default white fill"

    if backdrop is None:
        return

    if raw_font:
        font = parse_color(raw_font)
        if font is None:
            return
        candidates = [(raw_font, contrast_ratio(font, backdrop))]
    else:
        # An unset fontColor is not black, it is undecided: the desktop app
        # resolves it against the editor theme (white in dark theme) while
        # `--export` resolves it to black. The same cell is therefore legible in
        # one context and gone in the other, which is why the author never sees
        # it. Judge the worst case, because both cases ship.
        candidates = [
            (f"{c} (fontColor unset, resolved by context)", contrast_ratio(parse_color(c), backdrop))
            for c in (DEFAULT_FONT, "#ffffff")
        ]

    fg_hex, ratio = min(candidates, key=lambda c: c[1])
    if ratio >= CONTRAST_WARN:
        return

    level = "error" if ratio < CONTRAST_FAIL else "warn"
    findings.append(
        Finding(
            level,
            "contrast",
            page_name,
            cell.get("id", "?"),
            f"text {fg_hex} on {where} has contrast {ratio:.2f}:1 "
            f"(want {CONTRAST_WARN}:1) -- {text[:48]!r}",
        )
    )


def label_metrics(cell, style):
    """How much room the label wants against how much the shape gives it.

    Crude by necessity: it models a proportional face at one weight and knows
    nothing about a note's folded corner or a cylinder's cap. Good enough to
    separate "obviously will not fit" from "obviously swimming in space", which
    are the two ends a render makes you squint at.
    """
    if cell.get("vertex") != "1":
        return None
    text = plain_text(cell.get("value"))
    if not text:
        return None
    geo = geometry_of(cell)
    if not geo:
        return None
    _, _, w, h = geo
    if w <= 0 or h <= 0:
        return None

    try:
        font_size = float(style.get("fontSize") or DEFAULT_FONT_SIZE)
    except (TypeError, ValueError):
        font_size = DEFAULT_FONT_SIZE

    # `horizontal=0` rotates the label, so the text flows along the shape's
    # height and wraps against its width. Swap them rather than reading a tall
    # vertical band label as a wildly underfilled box.
    if style.get("horizontal") == "0":
        w, h = h, w

    # A swimlane's label lives in its title bar, not the whole shape.
    if style.get("swimlane"):
        try:
            h = float(style.get("startSize") or 23)
        except (TypeError, ValueError):
            h = 23.0

    char_w = font_size * CHAR_WIDTH_RATIO
    line_h = font_size * LINE_HEIGHT_RATIO
    spacing = 4.0  # draw.io's default horizontal label padding, both sides

    usable_w = max(w - 2 * spacing, 1.0)
    chars_per_line = max(int(usable_w / char_w), 1)
    lines_needed = max(1, -(-len(text) // chars_per_line))
    # The label block is inset vertically too, so a box whose height is exactly
    # N line-heights fits N-1 lines and clips the last one.
    lines_available = max(int((h - VERTICAL_PADDING) / line_h), 1)

    return {
        "text": text,
        "font_size": font_size,
        "width": w,
        "height": h,
        "line_height": line_h,
        "lines_needed": lines_needed,
        "lines_available": lines_available,
        "text_height": lines_needed * line_h + VERTICAL_PADDING,
    }


def check_overflow(page_name, cell, style, findings):
    """Will the label fit? draw.io never grows a box to make room.

    Without wrapping the text runs out the sides; with `whiteSpace=wrap` it
    spills past the top and bottom border; with `overflow=hidden` it is cut off
    with no visual cue at all, which is the only silent case.
    """
    m = label_metrics(cell, style)
    if m is None or m["lines_needed"] <= m["lines_available"]:
        return
    text, font_size, w, h = m["text"], m["font_size"], m["width"], m["height"]
    lines_needed, lines_available = m["lines_needed"], m["lines_available"]

    hidden = style.get("overflow") == "hidden"
    level = "error" if hidden else "warn"
    fate = (
        "overflow=hidden will silently truncate it"
        if hidden
        else "the text will spill outside the shape"
    )
    findings.append(
        Finding(
            level,
            "overflow",
            page_name,
            cell.get("id", "?"),
            f"{len(text)} chars need about {lines_needed} lines at {font_size:g}px but "
            f"{w:g}x{h:g} holds {lines_available}; {fate}",
        )
    )


def check_underfilled(page_name, cell, style, container_ids, findings):
    """The opposite of overflow, and the one the render makes you squint at.

    "Over-allocate height" pushes toward boxes several times taller than their
    copy, which read as something that failed to load. The linter is silent on
    an empty box unless it looks for one, so this is the inverse of the overflow
    check: size boxes once the copy is final, then confirm on the render.
    """
    # A shape sized to hold other things is not underfilled, whatever its own
    # label does. That covers XML parents, bands drawn as a backdrop for
    # siblings painted on top, and a lifeline whose height is the timeline.
    if cell.get("id") in container_ids or style.get("swimlane"):
        return
    if style.get("shape") == "umlLifeline":
        return
    m = label_metrics(cell, style)
    if m is None:
        return
    h = m["height"]
    if h < UNDERFILL_MIN_HEIGHT:
        return
    ratio = m["text_height"] / h
    if ratio >= UNDERFILL_RATIO:
        return
    findings.append(
        Finding(
            "warn",
            "underfilled",
            page_name,
            cell.get("id", "?"),
            f"about {m['text_height']:.0f}px of text in a {h:g}px box "
            f"({100 * ratio:.0f}% full); an empty-looking box reads as a "
            f"failure to load",
        )
    )


def check_container_padding(page_name, cells, findings):
    """A child flush against its container's border reads as a rendering bug.

    Container children use coordinates relative to the container, so this is a
    direct comparison. A swimlane's usable top edge is its title bar, not zero.
    """
    by_id = {c.get("id"): c for c in cells}
    for cell in cells:
        if cell.get("vertex") != "1":
            continue
        parent = by_id.get(cell.get("parent"))
        if parent is None or parent.get("vertex") != "1":
            continue
        geo, pgeo = geometry_of(cell), geometry_of(parent)
        if not geo or not pgeo:
            continue
        gnode = cell.find("mxGeometry")
        if (gnode.get("relative") or "0") == "1":
            continue
        x, y, w, h = geo
        _, _, pw, ph = pgeo

        pstyle = parse_style(parent.get("style"))
        top = 0.0
        if pstyle.get("swimlane"):
            try:
                top = float(pstyle.get("startSize") or 23)
            except (TypeError, ValueError):
                top = 23.0

        gaps = {
            "left": x,
            "top": y - top,
            "right": pw - (x + w),
            "bottom": ph - (y + h),
        }
        tight = {k: v for k, v in gaps.items() if v < CONTAINER_PADDING}
        if not tight:
            continue
        worst = min(tight, key=lambda k: tight[k])
        findings.append(
            Finding(
                "warn",
                "container-padding",
                page_name,
                cell.get("id", "?"),
                f"sits {gaps[worst]:.0f}px from the {worst} edge of "
                f"{parent.get('id', '?')} (want {CONTAINER_PADDING:g}px); flush "
                f"children read as a rendering bug",
            )
        )


def check_backdrop(page_name, model, cells, findings):
    """A non-default page background needs a real rectangle behind the content.

    `background` on `mxGraphModel` is honoured by the CLI export, but it is a
    model property rather than a shape, so anything that composes its own
    backdrop can ignore it. When that happens the boxes survive, because they
    carry their own `fillColor`, and every unfilled text cell disappears. A
    rectangle painted first is a shape, so nothing can drop it, and it also pins
    the exported extent to the page rather than to the content bounds.

    Only checked when the page actually declares a dark background, since a
    diagram on white already matches everyone's default.
    """
    bg = parse_color(model.get("background"))
    if bg is None or relative_luminance(bg) > 0.5:
        return

    tops = []
    for cell in cells:
        if cell.get("vertex") != "1" or cell.get("parent") != "1":
            continue
        geo = geometry_of(cell)
        if not geo or geo[2] <= 0 or geo[3] <= 0:
            continue
        tops.append((cell, geo))
    if len(tops) < 2:
        return

    first, fgeo = tops[0]
    fstyle = parse_style(first.get("style"))
    covers = all(contains(fgeo, geo, slack=0.0) for _, geo in tops[1:])
    opaque = fstyle.get("fillColor") not in (None, "none")

    if covers and opaque:
        return

    findings.append(
        Finding(
            "warn",
            "no-backdrop",
            page_name,
            first.get("id", "?"),
            f"page declares background {model.get('background')} but the first "
            f"shape is not an opaque rectangle covering the content; unfilled "
            f"text cells vanish wherever that background is not applied",
        )
    )


def contains(outer, inner, slack=1.0):
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox - slack
        and iy >= oy - slack
        and ix + iw <= ox + ow + slack
        and iy + ih <= oy + oh + slack
    )


def backdrop_ids(cells):
    """Vertices that fully contain a sibling painted after them.

    That is the signature of a band or group drawn as a background rectangle
    rather than as a real container, which is common and invisible to anything
    that only reads the `parent` attribute.
    """
    by_parent = {}
    for cell in cells:
        if cell.get("vertex") != "1":
            continue
        geo = geometry_of(cell)
        if not geo or geo[2] <= 0 or geo[3] <= 0:
            continue
        gnode = cell.find("mxGeometry")
        if (gnode.get("relative") or "0") == "1":
            continue
        by_parent.setdefault(cell.get("parent"), []).append((cell, geo))

    found = set()
    for siblings in by_parent.values():
        for i, (under, gu) in enumerate(siblings):
            for _, go in siblings[i + 1 :]:
                if contains(gu, go):
                    found.add(under.get("id"))
                    break
    return found


def check_overlap(page_name, cells, findings):
    """Find shapes that occlude other shapes.

    mxGraph paints in document order, so a later cell covers an earlier one.
    That distinction is the whole check: a band drawn before the boxes that sit
    on it is a backdrop, while the same geometry drawn after them is hiding
    them. Only cells with the same parent are comparable, since a container's
    children use coordinates relative to that container.
    """
    by_parent = {}
    for index, cell in enumerate(cells):
        if cell.get("vertex") != "1":
            continue
        geo = geometry_of(cell)
        if not geo or geo[2] <= 0 or geo[3] <= 0:
            continue
        if (cell.find("mxGeometry").get("relative") or "0") == "1":
            continue
        by_parent.setdefault(cell.get("parent"), []).append((index, cell, geo))

    for siblings in by_parent.values():
        for i, (_, under, gu) in enumerate(siblings):
            for _, over, go in siblings[i + 1 :]:
                ux, uy, uw, uh = gu
                ox, oy, ow, oh = go
                w = min(ux + uw, ox + ow) - max(ux, ox)
                h = min(uy + uh, oy + oh) - max(uy, oy)
                if w <= 0 or h <= 0:
                    continue

                # The earlier shape is a backdrop for the later one, which is
                # the normal way to draw bands, groups, and legends.
                if contains(gu, go):
                    continue

                area = w * h
                under_area = uw * uh
                covered = area / under_area
                if contains(go, gu):
                    findings.append(
                        Finding(
                            "error",
                            "overlap",
                            page_name,
                            under.get("id", "?"),
                            f"is drawn under {over.get('id', '?')}, which covers it "
                            f"completely; nothing of it will be visible",
                        )
                    )
                elif covered >= 0.10:
                    findings.append(
                        Finding(
                            "warn",
                            "overlap",
                            page_name,
                            under.get("id", "?"),
                            f"is {100 * covered:.0f}% covered by {over.get('id', '?')} "
                            f"({area:.0f}px^2), which is drawn on top of it",
                        )
                    )
                else:
                    # A step marker or badge hanging off the edge of a band
                    # covers too little of it to register above, but the
                    # straddle is the whole defect. Judge it from the small
                    # shape instead.
                    over_area = ow * oh
                    if over_area > STRADDLE_MAX_AREA_RATIO * under_area:
                        continue
                    inside = area / over_area
                    if not STRADDLE_MIN <= inside <= STRADDLE_MAX:
                        continue
                    findings.append(
                        Finding(
                            "warn",
                            "straddle",
                            page_name,
                            over.get("id", "?"),
                            f"is {100 * inside:.0f}% inside {under.get('id', '?')}, so it "
                            f"sits across that border rather than in or out of it",
                        )
                    )


def check_escaping(page_name, cell, findings):
    """Catch a generator that escaped a label twice.

    The parser has already undone one level of escaping by the time we see the
    value, so correct markup arrives as a real `<b>` tag. A tag still sitting
    there as `&lt;b&gt;` means the file stored `&amp;lt;b&amp;gt;`, and draw.io
    will render the characters `<b>` instead of applying them.

    A lone `&lt;` is left alone: that is how you correctly label something
    "a < b".
    """
    value = cell.get("value") or ""
    match = ESCAPED_TAG_RE.search(value)
    if match:
        findings.append(
            Finding(
                "error",
                "escaping",
                page_name,
                cell.get("id", "?"),
                f"value is double-escaped; {match.group(0)!r} will render as "
                f"literal text instead of markup",
            )
        )


def check_markup_colors(page_name, cell, findings):
    """Find `<b>`/`<i>` elements with no colour of their own.

    The VS Code draw.io extension's stylesheet sets a colour on `b` directly. A
    rule on the element beats a colour inherited from the cell's `fontColor` or
    from an enclosing `<font color>`, so a bare `<b>` renders dark grey there
    while the desktop app and `--export` render it correctly. Measured: the bold
    word paints #373737 regardless of the fill behind it.

    An inline `style="color:..."` on the element itself outranks the stylesheet
    and renders correctly everywhere. So does dropping the tag in favour of
    `<span style="font-weight:bold;color:...">`, or making the whole label bold
    with `fontStyle=1` in the cell style.
    """
    value = cell.get("value") or ""
    for match in STYLED_TAG_RE.finditer(value):
        tag, attrs = match.group(1), match.group(2)
        if INLINE_COLOR_RE.search(attrs):
            continue
        findings.append(
            Finding(
                "warn",
                "uncolored-markup",
                page_name,
                cell.get("id", "?"),
                f"<{tag.lower()}> has no colour of its own, so a renderer that "
                f"styles <{tag.lower()}> overrides the inherited one; use "
                f'<{tag.lower()} style="color:..."> or fontStyle=1',
            )
        )
        return


def check_placeholders(page_name, cell, findings):
    text = plain_text(cell.get("value"))
    match = PLACEHOLDER_RE.search(text)
    if match:
        findings.append(
            Finding(
                "error",
                "placeholder",
                page_name,
                cell.get("id", "?"),
                f"unresolved placeholder {match.group(0)!r} left in the label",
            )
        )


def lint_file(path):
    findings = []
    try:
        pages = read_pages(path)
    except ET.ParseError as e:
        # A raw `<` or a bare `&` inside a value attribute lands here. The app
        # reports this far less helpfully than the parser does.
        return [
            Finding(
                "error",
                "xml",
                "-",
                "-",
                f"not well-formed XML: {e}. A literal '<' or '&' in a value "
                f"attribute is the usual cause; escape it as &lt; or &amp;",
            )
        ]

    if not pages:
        return [Finding("error", "xml", "-", "-", "no <diagram> elements found")]

    for _, name, model, diagram in pages:
        if model is None:
            body = (diagram.text or "").strip()
            findings.append(
                Finding(
                    "error",
                    "compressed",
                    name,
                    "-",
                    "page has no <mxGraphModel>; it is stored compressed"
                    if body
                    else "page has no <mxGraphModel>",
                )
            )
            continue

        page_bg = parse_color(model.get("background")) or parse_color(DEFAULT_PAGE_BG)
        if not model.get("background"):
            findings.append(
                Finding(
                    "warn",
                    "background",
                    name,
                    "-",
                    "mxGraphModel has no background; the export inherits the "
                    "viewer's backdrop instead of the one you designed against",
                )
            )

        root = model.find("root")
        cells = list(root.iter("mxCell")) if root is not None else []
        # A cell holding children is sized for them, not for its own label.
        # Bands are often drawn as a backdrop with their contents as siblings
        # painted on top, so XML parentage alone does not find them.
        container_ids = {c.get("parent") for c in cells if c.get("parent")}
        container_ids |= backdrop_ids(cells)
        for cell in cells:
            style = parse_style(cell.get("style"))
            check_contrast(name, cell, style, page_bg, findings)
            check_overflow(name, cell, style, findings)
            check_underfilled(name, cell, style, container_ids, findings)
            check_escaping(name, cell, findings)
            check_markup_colors(name, cell, findings)
            check_placeholders(name, cell, findings)
        check_overlap(name, cells, findings)
        check_container_padding(name, cells, findings)
        check_backdrop(name, model, cells, findings)

    order = {"error": 0, "warn": 1}
    findings.sort(key=lambda f: (order[f.level], f.check, f.page))
    return findings


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------


def find_binary():
    found = shutil.which("drawio") or shutil.which("draw.io")
    if found:
        return found
    for candidate in BINARY_CANDIDATES:
        p = Path(candidate).expanduser()
        if p.exists() and os.access(p, os.X_OK):
            return str(p)
    raise SystemExit(
        "draw.io desktop not found. Install it (macOS: brew install --cask drawio) "
        "or set DRAWIO_BINARY to the executable inside the app bundle."
    )


def export_page(binary, path, page, out, fmt, scale, theme, timeout):
    cmd = [
        binary,
        "--export",
        "--format", fmt,
        "--page-index", str(page),
        "--scale", str(scale),
        "--output", str(out),
        str(path),
    ]
    if theme:
        cmd += ["--theme", theme]

    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SystemExit(f"export timed out after {timeout}s (Electron can be slow to boot)")

    stderr = (proc.stderr or "").strip()
    if "MachPortRendezvousServer" in stderr or "bootstrap_look_up" in stderr:
        raise SystemExit(
            "draw.io could not start its renderer:\n"
            f"  {stderr.splitlines()[0]}\n"
            "Electron needs Mach port access that a sandboxed shell denies. Re-run "
            "this command with the sandbox disabled."
        )

    # An out-of-range page exits 0 and writes the LAST page instead, so the exit
    # code alone does not tell you the render is the page you asked for. The
    # caller validates the index before we get here; this catches the rest.
    if proc.returncode != 0:
        raise SystemExit(f"export failed (exit {proc.returncode}): {stderr or proc.stdout}")
    if not out.exists() or out.stat().st_size == 0:
        raise SystemExit(f"export reported success but wrote no file at {out}")
    return out


def cmd_export(args):
    path = Path(args.file).resolve()
    if not path.exists():
        raise SystemExit(f"{path} does not exist")

    pages = read_pages(path)
    count = len(pages)
    binary = os.environ.get("DRAWIO_BINARY") or find_binary()

    if args.all:
        wanted = list(range(1, count + 1))
    else:
        wanted = args.page or [1]
        for p in wanted:
            if p < 1:
                raise SystemExit(f"page {p} is invalid: pages are numbered from 1")
            if p > count:
                # draw.io would silently hand back the last page here.
                raise SystemExit(f"page {p} is out of range: {path.name} has {count} page(s)")

    out_dir = Path(args.out_dir).resolve() if args.out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for p in wanted:
        name = pages[p - 1][1]
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"page{p}"
        suffix = f"-{args.theme}" if args.theme else ""
        out = out_dir / f"{path.stem}-{p:02d}-{slug}{suffix}.{args.format}"
        export_page(binary, path, p, out, args.format, args.scale, args.theme, args.timeout)
        written.append(out)
        print(out)

    print(f"exported {len(written)} page(s) from {path.name}", file=sys.stderr)


def cmd_lint(args):
    total_errors = 0
    for name in args.file:
        path = Path(name).resolve()
        if not path.exists():
            raise SystemExit(f"{path} does not exist")
        findings = lint_file(path)
        for f in findings:
            print(f.format(path.name))
        errors = sum(1 for f in findings if f.level == "error")
        warns = len(findings) - errors
        total_errors += errors
        print(f"{path.name}: {errors} error(s), {warns} warning(s)", file=sys.stderr)
    return 1 if total_errors else 0


def cmd_pages(args):
    path = Path(args.file).resolve()
    for index, name, model, _ in read_pages(path):
        bg = (model.get("background") if model is not None else None) or "unset"
        print(f"{index}\t{name}\tbackground={bg}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="drawio_tool", description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    e = sub.add_parser("export", help="render pages to images so you can look at them")
    e.add_argument("file")
    e.add_argument("--page", type=int, action="append", help="1-based page number, repeatable")
    e.add_argument("--all", action="store_true", help="export every page")
    e.add_argument("--format", default="png", choices=["png", "svg", "pdf", "jpg"])
    e.add_argument("--scale", default="2", help="2 keeps 10-11px labels legible when read back")
    e.add_argument("--theme", choices=["light", "dark"], help="apply draw.io's theme transform")
    e.add_argument("--out-dir", help="defaults to the diagram's directory")
    e.add_argument("--timeout", type=int, default=180)
    e.set_defaults(func=cmd_export)

    li = sub.add_parser("lint", help="check for defects a render cannot show")
    li.add_argument("file", nargs="+")
    li.set_defaults(func=cmd_lint)

    p = sub.add_parser("pages", help="list pages with their 1-based index")
    p.add_argument("file")
    p.set_defaults(func=cmd_pages)

    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
