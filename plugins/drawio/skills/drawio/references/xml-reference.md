# .drawio XML reference

## File shape

```xml
<mxfile host="app.diagrams.net">
  <diagram id="unique-id" name="1 - System map">
    <mxGraphModel dx="1400" dy="900" grid="0" gridSize="10" guides="1"
                  page="1" pageScale="1" pageWidth="1240" pageHeight="880"
                  background="#0f1117">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        <!-- your cells, all with parent="1" or a container id -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

`mxCell` `0` and `1` are structural and always present. Cell `0` is the model
root; cell `1` is the default layer. Every shape you author descends from `1`
or from a container.

Keep the XML **uncompressed**. draw.io will happily store each page as a single
base64 blob, which defeats diffing, grepping and hand-editing. A page with no
`<mxGraphModel>` child is compressed; the linter reports it.

## Escaping, the failure that stops the file opening

`value` is an XML attribute holding HTML. draw.io unescapes the attribute once,
then renders the result as HTML. So bold text is stored as:

```xml
value="&lt;b&gt;Browser&lt;/b&gt; and client"
```

Consequences for anything generating these files:

- A literal `<b>` in the attribute is **invalid XML** and the file will not
  open. The app's error is far less useful than a parser's.
- Exactly one escaping pass. Escaping twice stores `&amp;lt;b&amp;gt;`, which
  renders the literal characters `<b>` as visible text. The linter flags this.
- A bare `&` is also invalid. `&amp;` renders as `&`.
- Do not write a partial escaper that "lets known tags through". Escape the
  whole string, then, if you want markup, compose it from already-escaped
  pieces.

Useful inline markup, all of it escaped the same way: `<b>`, `<i>`, `<br>`,
`<font color="#9aa7bd">`.

Give every `<b>`, `<i>`, `<strong>`, `<em>` and `<u>` its own inline colour:

```
<b style="color:#e8edf5">Name</b>
```

A bare `<b>` inherits its colour, and the VS Code draw.io extension styles `b`
directly, which beats inheritance and renders the word dark grey. The desktop
app and `--export` are both unaffected, so you cannot see it from either. See
`palette.md`.

An exported SVG carries a dark-mode counterpart for the colours you authored,
emitted as CSS `light-dark(authored, auto-darkened)`: `#e8edf5` ships as
`light-dark(#e8edf5, #1d2229)`. The effect to plan around is that **an SVG
embedded in a page renders inverted for a reader whose browser is in dark
colour-scheme** -- measured in headless Chromium, the whole diagram flips
together, background and fills and text, the same way `--theme dark` behaves.

Nothing in the style string opts out; all nine authoring mechanisms tested
produce it. So a diagram authored dark will look light to a dark-mode reader.
If a specific appearance matters more than adapting, export PNG, which is
rendered once at export time and cannot flip.

**Validate with a parser before opening the file.** `drawio_tool lint` does
this first and reports the line and column.

## Geometry

```xml
<mxCell id="svc" value="Service" style="rounded=1;..." vertex="1" parent="1">
  <mxGeometry x="40" y="100" width="220" height="72" as="geometry" />
</mxCell>
```

- A child of a container uses coordinates **relative to that container**, not
  the page. This is the most common source of a shape landing somewhere
  unexpected.
- Order in the document is paint order. A later cell is drawn on top of an
  earlier one. That is how a band works: draw the band first, then the boxes on
  it. It is also how a legend accidentally erases a node.
- Edge waypoints go in an `Array` inside the geometry:

```xml
<mxGeometry relative="1" as="geometry">
  <Array as="points">
    <mxPoint x="400" y="200" />
    <mxPoint x="400" y="320" />
  </Array>
</mxGeometry>
```

- An edge with no `source`/`target` needs explicit `sourcePoint` and
  `targetPoint` children instead.

## Styles

A style is a semicolon-separated list. Bare tokens are shape selectors; the
rest are `key=value`.

```
rounded=1;whiteSpace=wrap;html=1;fillColor=#14243f;strokeColor=#6ea1e8;fontColor=#e8edf5;fontSize=13;
```

Keys worth knowing:

| Key | Effect |
|---|---|
| `whiteSpace=wrap` | wrap the label instead of running it off the sides |
| `html=1` | interpret the label as HTML; required for `<b>`, `<br>` |
| `overflow=hidden` | clip the label to the shape, silently |
| `verticalAlign` | `top`, `middle`, `bottom` |
| `align`, `spacingLeft` | `align=left;spacingLeft=10` for body-text blocks |
| `horizontal=0` | rotate the label 90 degrees, for a label spanning bands |
| `dashed=1` | dashed line, for a secondary or asynchronous relationship |
| `startSize` | height of a swimlane's title bar |
| `strokeWidth` | line weight; default 1 is thin, prefer 2 |
| `boundedLbl=1` | keep a label inside a shape that would otherwise center it oddly |

## Text sizing behaviour

draw.io never grows a shape to fit its label. What happens instead depends on
the style, and only one of the three is silent:

| Style | Result when the text is too big |
|---|---|
| default (no wrap) | the line runs out both sides of the shape |
| `whiteSpace=wrap` | the text spills past the top and bottom borders |
| `overflow=hidden` | the text is cut off with no visual cue at all |

The first two are obvious the moment you look at a render. The third is not, so
prefer wrapping and over-allocate height.

## Shapes

| Need | Style |
|---|---|
| Titled container | `swimlane;startSize=34;` |
| Annotation | `shape=note;size=16;` |
| Pointer to a thing | `shape=callout;perimeter=calloutPerimeter;` |
| Datastore | `shape=cylinder3;boundedLbl=1;` |
| Sequence lifeline | `shape=umlLifeline;perimeter=lifelinePerimeter;` |
| Plain canvas text | `text;html=1;` (no fill, so set `fontColor` deliberately) |

## Pages

Multiple `<diagram>` elements inside one `<mxfile>` are the tabs along the
bottom of the editor. This is almost always the right answer to "should this be
one diagram or several": separate page, same file. One file travels as a unit,
and a single page can still be exported and sent alone.

`--page-index` is **1-based** in draw.io 27.0.2 and later, 0-based before it.
Two failure modes, only one of which is loud:

- Index `0` exits non-zero with `Invalid page index: pages are numbered from 1`.
- An index **above** the page count exits **0** and writes the **last** page.
  Verified: exporting page 3 of a 2-page file produces a byte-identical copy of
  page 2. Nothing in the output says so.

`drawio_tool export` counts the `<diagram>` elements and refuses an out-of-range
index rather than handing you a confidently wrong render.

## Layers

A layer is an `mxCell` with `parent="0"`, and shapes on that layer use its id as
their parent. Toggle them in Edit > Layers.

```xml
<mxCell id="0" />
<mxCell id="1" parent="0" />                        <!-- base -->
<mxCell id="notes" value="Annotations" parent="0" /> <!-- overlay -->
```

One constraint shapes how you can use them: a child of a container inherits
that container's layer, so you cannot independently layer the contents of a
swimlane. Keep structure on the base layer and use layers for annotation
overlays that should toggle as a unit.

## Exporting a file that is also its own source

```sh
drawio --export --format svg --embed-diagram --output arch.drawio.svg arch.drawio
```

`--embed-diagram` is the CLI equivalent of "Include a copy of my diagram" in the
SVG export dialog. The result is a valid SVG that renders anywhere and a
draw.io source that reopens fully editable. Committing that single file removes
the drift between a diagram and the image of it that everyone actually looks at.

Add `--embed-svg-fonts false` unless you need the exact typeface to survive on a
machine that lacks it. Fonts are embedded by default and dominate the file: one
palette sheet measured 1,033,464 bytes with them and 60,497 without, a 17x
difference for output that looks identical anywhere Helvetica resolves.
