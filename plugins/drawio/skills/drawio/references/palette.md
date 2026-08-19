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
document and small enough that an agent reading its own export at `--scale 2`
can struggle. Start at:

| Role | Size |
|---|---|
| Page title | 20px, `fontStyle=1` |
| Band or section title | 15px, `fontStyle=1` |
| Box label | 13px |
| Edge label | 12px |

Use `fontStyle=1` (bold) for the first line of a box and a `<font color>` span
in the muted color for the detail lines. That gives a readable hierarchy inside
a box without a second shape.
