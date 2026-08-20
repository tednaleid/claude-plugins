# Palettes and contrast

## The rule

**Every cell that carries a label MUST set `fontColor`. Every edge that carries
a label MUST also set `labelBackgroundColor`.**

This is not a style preference, and it is not about supporting dark mode. It is
about a value that has no single definition.

## Why an unset fontColor is a bug, not a default

When `fontColor` is absent, draw.io does not fall back to a fixed color. It asks
the rendering context, and the two contexts you will actually use disagree:

| Context | Unset `fontColor` resolves to |
|---|---|
| Desktop app, dark theme | white |
| `--export` (any `--theme`) | black |

So one cell is legible where you authored it and invisible where you ship it,
and you will only ever look at one of those. Verified on draw.io 31.1.8 with a
13-case probe: a pale `#dae8fc` fill with no `fontColor` is unreadable in the
app and fine in the export, while a near-black `#14161c` fill with no
`fontColor` is fine in the app and unreadable in the export. Same file, same
missing attribute, opposite symptom.

The linter models this by scoring an unset `fontColor` against **both** black
and white and reporting the worse of the two. There is no fill that survives
both, which is the point: the only fix is to state the color.

## Why an edge label needs a background

An edge label sits on top of a line. draw.io gives it an opaque **white**
background by default, so on a dark diagram you get a white bar with the line
disappearing behind it, and `fontColor=#ffffff` on that bar is invisible at a
contrast ratio of exactly 1.00.

`labelBackgroundColor=none` is not the fix either: with no bar, the edge is
drawn straight through the middle of the text, which reads as a strikethrough.

Set `labelBackgroundColor` to whatever the label sits on, usually the page
background or the enclosing band's fill.

## The same trap one level down: a bare `<b>` in a label

A bold segment written as `<b>Green</b>` takes its colour by inheritance, from
the cell's `fontColor` or an enclosing `<font color>`. **The VS Code draw.io
extension's stylesheet sets a colour on `b` directly, and a rule on the element
beats an inherited colour.** The bold word renders dark grey there while the
rest of the same label renders correctly.

Measured in the extension: the bold word paints `#373737`, flat and opaque, the
same value over a green fill and a blue one. The desktop app and `--export`
both render it correctly, so this is one editor disagreeing with two other
renderers, and it is invisible from either of the other two.

Wrapping the tag does **not** help, because inheritance is exactly what loses:

```
<font color="#e8edf5"><b>Green</b></font>     still dark in the extension
```

Three things do work, verified by screenshotting a probe in the extension and
measuring the glyphs:

```
<b style="color:#e8edf5">Green</b>                        inline style outranks the rule
<span style="font-weight:bold;color:#e8edf5">Green</span> no <b> element to target
fontStyle=1 in the cell style                             whole-label bold, no markup
```

**Give every `<b>`, `<i>`, `<strong>`, `<em>` and `<u>` in a label its own
inline `color`**, or avoid the tag. The linter reports the rest as
`uncolored-markup`.

Plain text alongside a coloured span is fine and needs no wrapper: only the
styled tags are targeted by the rule.

## Other theme-dependent values

`fillColor` also has a context-sensitive default. A vertex with no `fillColor`
is **white**, not transparent, so an unstyled box on a dark page renders as a
white slab. Use `fillColor=none` when you actually want the page to show
through, and remember that the label then sits on the page background.

Set `background` on `mxGraphModel`. Without it the export inherits whatever
backdrop the viewer supplies, so the one thing every element is composed
against is the one thing you did not specify.

## A dark page also needs a real rectangle

`background` is a model property, not a shape. The CLI export honours it, but
anything that composes its own backdrop can ignore it, and the desktop app's
File > Export As dialog is reported to do exactly that.

The symptom is distinctive, and it is what makes this worth a rule: **the boxes
survive and the page-level text disappears.** Anything with its own `fillColor`
is unaffected; every `fillColor=none` text cell (page title, subtitle, section
headings, free-floating captions) renders dark on dark. If a reviewer says "some
of the text is missing" and the boxes look fine, this is almost always it, and
it is not a `fontColor` bug.

Emit a backdrop as the **first cell of every page**:

```xml
<mxCell id="backdrop" value=""
  style="rounded=0;whiteSpace=wrap;html=1;fillColor=#0f1117;strokeColor=none;
         movable=0;resizable=0;rotatable=0;deletable=0;editable=0;connectable=0;"
  vertex="1" parent="1">
  <mxGeometry x="0" y="0" width="{W}" height="{H}" as="geometry"/>
</mxCell>
```

- **The lock flags are not decoration.** Without them the rectangle is the
  easiest thing on the canvas to select and drag, being underneath everything
  and filling the page.
- **Size it from content bounds, not just `pageWidth`/`pageHeight`.** Use
  `max(pageWidth, maxX + margin)` across every vertex. A page whose content
  outgrew its declared size gets a bright strip down one edge, which reads as a
  rendering artefact and is worse than no backdrop.
- **Keep `background` as well.** It is what makes the editor canvas look right
  while authoring. The rectangle is for everyone else.

A useful side effect: the rectangle pins the exported extent to the page.
Without it the exporter crops to content, so the same page exports at a
different size as its contents change.

`drawio_tool lint` reports this as `no-backdrop`, and only for pages that
declare a dark background, since a diagram on white already matches every
renderer's default.

Do not try to verify this with `--transparent`. That was measured and it does
not discriminate: the CLI honours `background` either way, so a file with no
backdrop still exports opaque with the right corner pixel. The lint rule is the
check.

## What `--theme dark` does

It applies a lightness inversion across fill, stroke, background and
`fontColor` together, preserving hue. Measured on a single probe cell:

| authored | default export | `--theme dark` export |
|---|---|---|
| fill `#14161c` | `#14161c` | `#d8dadf` |
| stroke `#6f9bf0` | `#6f9bf0` | `#486eb7` |
| background `#12141a` | `#12141a` | `#dadce1` |
| `fontColor` `#ffffff` | `#ffffff` | `#121212` |

Two consequences. A diagram authored with dark colors renders **light** under
`--theme dark`, because it is being inverted a second time. And the inversion
is uniform, so it never rescues a contrast bug and never introduces one: a
missing `fontColor` is broken in both renders, and a correct diagram is correct
in both. You therefore do not need a dark export to check contrast. The default
export plus the linter covers it.

## Dark palette

A working copy lives at `examples/palette-sheet.drawio`. Open it, or copy style
strings straight out of it.

Base:

| Role | Hex | Notes |
|---|---|---|
| Page background | `#0f1117` | set as `background` on `mxGraphModel` |
| Text | `#e8edf5` | 16.1:1 on the page background |
| Muted text | `#9aa7bd` | 7.8:1 on the page background, for secondary lines |
| Band tier 1 | fill `#16202e`, stroke `#4a6484` | a tint, not a color |
| Band tier 2 | fill `#1d1a2e`, stroke `#6a5f96` | reads as a different layer |

Categories. Each fill is dark enough that `#e8edf5` clears 12:1 on it, so the
color is free to mean something without putting the text at risk:

| Category | Fill | Stroke | Accent | Suggested meaning |
|---|---|---|---|---|
| Slate | `#1b2130` | `#7d93b5` | `#7d93b5` | neutral, the default box |
| Blue | `#14243f` | `#6ea1e8` | `#6ea1e8` | ours, primary |
| Teal | `#0f2b2b` | `#46a89d` | `#46a89d` | infrastructure, transport |
| Green | `#152a1d` | `#5aa86a` | `#5aa86a` | ok, protected, allowed |
| Amber | `#2e2410` | `#d9a441` | `#d9a441` | warning, unprotected |
| Red | `#331a1c` | `#e0736b` | `#e0736b` | danger, boundary, failure |
| Purple | `#241d3d` | `#9a86e0` | `#9a86e0` | theirs, external, federated |
| Magenta | `#331a2b` | `#d97ab5` | `#d97ab5` | data, storage |

Measured text contrast on these fills runs 12.7:1 to 13.7:1 for `#e8edf5` and
6.2:1 to 6.6:1 for `#9aa7bd`. Strokes clear 4.1:1 against their own fill.

The accent column is for text and strokes on the **page** background, such as a
colored word inside a label or an unfilled outline. Do not use an accent as a
fill.

## Light palette

For diagrams that will be embedded in a light document, where a dark diagram
would sit on the page as a black rectangle.

| Role | Hex |
|---|---|
| Page background | `#fbfcfd` |
| Text | `#10141c` |
| Muted text | `#55606f` |

| Category | Fill | Stroke |
|---|---|---|
| Slate | `#eef1f5` | `#5a6b82` |
| Blue | `#e3edfb` | `#2f6bbf` |
| Teal | `#e0f2f0` | `#1f7a70` |
| Green | `#e6f4e8` | `#2e7d3a` |
| Amber | `#fdf1dc` | `#a5701a` |
| Red | `#fce9e7` | `#b03a30` |
| Purple | `#eee9fb` | `#5f4bb0` |
| Magenta | `#fbe9f3` | `#a63b7d` |

Text contrast runs 15.5:1 to 16.5:1, muted text 5.4:1 to 5.7:1. Strokes clear
4.4:1 against their fill except amber at 3.8:1, which is still above the 3:1
that a border needs but is the first one to check if a diagram prints badly.

## Choosing between them

Pick by where the image will be **consumed**, not by the theme you edit in. A
diagram destined for a Confluence page or a README renders on white; a diagram
for a terminal-adjacent doc or a dark deck renders on black. Because the
palettes are explicit, neither one shifts when the viewer's theme changes,
which is the property that makes the choice safe to make once.

## Line weight

Set `strokeWidth=2` on shapes and edges. draw.io defaults to 1, which is thin
enough that a 1px stroke competes poorly with a saturated fill, and thinner
still once the image is scaled down into a document. Dashed edges suffer most:
at width 1 the dashes read as a faint dotted line rather than a deliberate
"secondary relationship".

```
rounded=1;fillColor=#14243f;strokeColor=#6ea1e8;strokeWidth=2;fontColor=#e8edf5;
```

Weight is also available as meaning: hold structure at 2 and push a highlighted
path to 3 or 4. Do that only when the difference is carrying information, since
otherwise it reads as inconsistency.

## Type sizes

draw.io defaults to 12px, which is small once a diagram is scaled down into a
document. A baseline for a canvas up to about 1200px wide:

| Role | Size |
|---|---|
| Page title | 20px, `fontStyle=1` |
| Page subtitle | 14px |
| Band or section title | 15px, `fontStyle=1` |
| Box heading | 13px, bold |
| Box body | 13px |
| Edge label | 12px |
| Prose beneath the diagram | 15px |

**Point size is the wrong unit, so scale these with the canvas.** Legibility
depends on how far the page is scaled down when it is consumed: a 3100px-wide
diagram pasted into a document at 1000px is being read at about a third. At
2500-3500px add 40-60% to every row. On one 3100px build the table above needed
the page title at 30, band titles at 21, box headings at 21-27, body at 19-20
and edge labels at 14-17 before a reviewer stopped asking for it bigger.

Set the body size first, then everything else relative to it, and check
container titles and captions **last**. Two inversions are easy to create by
bumping one row at a time, and both look wrong even though every individual
size is defensible:

- **A container's title must not be smaller than the text inside it.** Bumping
  box text without bumping the band title leaves the band heading shrinking into
  its own contents.
- **Prose beneath a diagram must not be larger than the diagram's own detail
  lines**, or the caption out-shouts the thing it is captioning.

Use `fontStyle=1` (bold) for the first line of a box and a `<font color>` span
in the muted color for the detail lines. That gives a readable hierarchy inside
a box without a second shape. Note that a bare `<b>` needs its own inline
colour, as above.

Render hostnames, URL paths, JSON fragments and identifiers in monospace:

```
<font style="font-family:monospace">/api/v1/me/access</font>
```

It separates a literal from prose at a glance and stops a reader parsing
`/api/v1/me/access` as English. Monospace reads about one step smaller than the
same nominal size in the body face, so bump it or accept the de-emphasis
deliberately.
