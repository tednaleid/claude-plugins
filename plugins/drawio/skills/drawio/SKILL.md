---
name: drawio
description: Use when creating or editing a draw.io / diagrams.net diagram, working with .drawio or .drawio.svg files, producing an architecture or topology or sequence diagram that someone will later edit, or when the user asks for an editable diagram rather than inline SVG or Mermaid. Also use when a diagram renders wrong, has unreadable labels, clipped text, or arrows running through boxes.
allowed-tools: Bash(*drawio_tool.py *), Bash(*draw.io*), Read, Write, Edit
---

# drawio

Author draw.io diagrams that are readable and correct, and prove both before
handing the file over.

Two classes of defect account for nearly every bad diagram, and **neither is
visible when you read the XML back**:

- **Invisible text.** A label whose colour matches what is behind it. Parses
  perfectly, renders as an empty box.
- **Layout collisions.** An edge label on a band title. An arrow through an
  unrelated box. A legend covering the very edge it was explaining. Text spilling
  out of a shape. Every one of these is valid XML.

Reading your own XML cannot catch either. The workflow below catches both, using
two different instruments, because neither instrument catches the other's class.

## Workflow

```
PLAN --> AUTHOR --> LINT --> EXPORT --> LOOK --> FIX --> (re-lint, re-export, re-look)
```

`LOOK` means calling `Read` on the exported PNG. You have image input. Use it.

### 1. Plan

Decide before writing XML:

- **Pages.** What are the distinct views? Context, detail, and sequence are
  usually separate pages, not one crowded canvas. Multiple pages live in one
  file.
- **Grid.** Bands for one dimension, columns for the other. See
  `references/patterns.md`.
- **Palette.** Dark or light, chosen by where the diagram will be *consumed*,
  not by your editor theme. See `references/palette.md`.
- **Topology.** Check the real structure against terraform, config, or routing
  rules. Not memory. An edge is a claim about a real path, and a wrong edge is
  the one defect that survives a beautiful render.

### 2. Author

Write uncompressed XML. Structure and gotchas are in
`references/xml-reference.md`; the escaping rules there are the most likely
reason a generated file fails to open at all.

Five requirements, each because the default is not what you would guess:

- **Every labelled cell sets `fontColor`.** Unset does not mean black. It means
  "ask the renderer", and the desktop app answers white while `--export`
  answers black. The same cell is legible in one and invisible in the other.
- **Every labelled edge also sets `labelBackgroundColor`.** Edge labels get an
  opaque white background by default, so white label text on a dark diagram is
  invisible at exactly 1.00:1 contrast.
- **Every `<b>` or `<i>` in a label carries its own inline colour**, as
  `<b style="color:#e8edf5">`. A bare `<b>` inherits, and the VS Code draw.io
  extension styles `b` directly, which beats inheritance and renders the word
  dark grey. The desktop app and `--export` both render it correctly, so this
  one is invisible from the export loop. `fontStyle=1` is the safe way to bold a
  whole label.
- **`mxGraphModel` sets `background`.** Otherwise the export inherits the
  viewer's backdrop, and the one surface everything is composed against is the
  one thing you left unspecified.
- **A dark page also gets a locked backdrop rectangle as its first cell.**
  `background` is a model property, not a shape, so an exporter that composes
  its own backdrop can drop it. When that happens the filled boxes survive and
  every unfilled text cell vanishes. A rectangle cannot be dropped. See
  `references/palette.md` for the style string and sizing.
- **Shapes and edges set `strokeWidth=2`.** The default of 1 is thin against a
  saturated fill and thinner still once the image is scaled into a document.

### 3. Lint

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/drawio_tool.py" lint diagram.drawio
```

Checks well-formedness, contrast against whatever is actually behind each
label, bold runs that inherit a colour a renderer will override, double-escaped
markup, text that will overflow its box and boxes far too large for their text,
shapes covered by shapes drawn after them, small shapes straddling a border,
children flush against a container edge, a dark page with no backdrop
rectangle, unresolved template placeholders, and a missing page background.
Errors mean the diagram is broken; warnings want a look.

Run this first. It is seconds, and it catches the class that a render cannot
show you.

### 4. Export

```bash
"${CLAUDE_PLUGIN_ROOT}/scripts/drawio_tool.py" export diagram.drawio --all --scale 2
```

Use `--page N` for a single page (1-based). Export is slow to start because it
boots Electron; allow a generous timeout.

**Pick the scale from the canvas width.** Under about 1500px use `--scale 2`,
because 11 to 13px labels are not reliably readable at 1x when you read the
image back. Above it use `--scale 1`: a 3150x2720 page at scale 2 is 6300x5440,
which gets downsampled to a fixed width for reading anyway, so the extra pixels
cost detail rather than adding it.

If it fails with `bootstrap_look_up ... MachPortRendezvousServer: Permission
denied (1100)`, Electron is being denied the Mach ports it needs. That is a
sandboxed shell, not a broken install. Re-run with the sandbox disabled
(`dangerouslyDisableSandbox: true` on the Bash call). The tool detects this
error and tells you.

### 5. Look

**`Read` every exported PNG.** This step is the reason the skill exists.

Check specifically:

- Is every label readable? Any box that looks empty is full of invisible text.
- Does any edge pass through a box it has nothing to do with?
- Does any label sit on top of another label, a band title, or a border?
- Is any text spilling outside its shape, or cut off at the edge?
- Do callout tails point at the thing they are about?
- Does any annotation cover an arrow? Trace each relationship you meant to draw
  and confirm you can still see it.
- Is the whole thing legible at the size it will actually be viewed?

**The render is authoritative about appearance. The XML is authoritative about
existence.** Do not use one to answer the other's question. A downsampled export
of a large page will convince you that elements failed to render when they are
present and correct; grep the XML for the id before acting on a "missing"
element, and never conclude a colour is right from reading the style string.

### 6. Fix and re-verify

After any edit, lint and export and look again. A fix that moves a box moves
whatever that box was next to.

Re-lint after any global change in particular. Bumping every font size by two
points pushes exactly one label over its box, and the overflow estimator finds
it in under a second. That class is tedious to spot in a render and free to
catch mechanically.

## Do not skip the look

Reading the XML back is not verification. The XML is where these bugs are
invisible. That is the entire premise.

| Rationalization | Reality |
|---|---|
| "The XML is obviously correct" | Every defect this skill targets is valid XML. Correct XML is the precondition, not the check. |
| "The lint passed" | Lint cannot see collisions, ugly routing, or a callout pointing at nothing. It measures contrast and estimates overflow; it does not have eyes. |
| "It's a small change" | A small change moves things. Moved things collide. |
| "I used the verified palette" | The palette guarantees contrast. It guarantees nothing about layout. |
| "Exporting is slow" | It is one Electron boot against shipping a diagram with three empty-looking boxes. |
| "I'll let the user check it" | The user asked for a diagram, not a draft to proofread. They are also the person least likely to spot a missing edge. |
| "I can't run the export here" | Then say so explicitly and mark the diagram unverified. Do not imply you looked. |

If you genuinely cannot export, state plainly that the diagram is unverified
and which checks were not run. Never describe an unexamined diagram as done.

## Quick reference

```bash
TOOL="${CLAUDE_PLUGIN_ROOT}/scripts/drawio_tool.py"

"$TOOL" pages   diagram.drawio                     # list pages with 1-based indexes
"$TOOL" lint    diagram.drawio                     # defects a render cannot show
"$TOOL" export  diagram.drawio --all --scale 2     # every page to PNG
"$TOOL" export  diagram.drawio --page 3 --scale 2  # one page
"$TOOL" export  diagram.drawio --page 1 --theme dark
```

Then `Read` each printed path.

Shipping a diagram that is both source and image:

```bash
drawio --export --format svg --embed-diagram --embed-svg-fonts false \
  --output arch.drawio.svg arch.drawio
```

## Three renderers, and none of them is the reference

The same file is drawn by the desktop app, the VS Code extension, and
`--export`, and they do not agree. Every colour defect found so far is visible
in some of them and invisible in the others. Measured on draw.io 31.1.8, with
`?` marking a combination not tested rather than one known to be safe:

| Defect | Desktop app | VS Code extension | `--export` |
|---|---|---|---|
| Unset `fontColor` | resolves white | ? | resolves black |
| Bare `<b>` in a label | correct | dark grey | correct |
| Edge label with no `labelBackgroundColor` | no bar drawn | ? | opaque white bar |

So looking at the export proves the export is fine and proves nothing else.
That is not an argument for skipping the look, which is the only thing that
catches layout defects. It is the reason the linter exists alongside it: the
linter reasons about all three, and it is the only check that covers the
renderer you are not currently looking at.

The practical rule this yields: **state every colour explicitly and never let a
renderer choose one.** Each row above is a place where draw.io has a default,
and every default differs somewhere.

## Gotchas worth knowing up front

- **`--page-index` is 1-based** (draw.io 27.0.2+). Index 0 fails loudly. An
  index *above* the page count exits 0 and silently writes the **last** page
  instead. `drawio_tool export` refuses out-of-range indexes for this reason;
  if you call the binary directly, check what you actually got.
- **A vertex with no `fillColor` is white**, not transparent. On a dark page it
  is a white slab. Use `fillColor=none` to let the page through.
- **draw.io never grows a shape to fit its label.** Without wrapping the text
  runs out the sides; with `whiteSpace=wrap` it spills top and bottom; with
  `overflow=hidden` it is truncated silently. Only the last one is invisible in
  a render, so prefer wrapping.
- **Paint order is document order.** A later cell covers an earlier one. Draw
  bands before their contents.
- **Container children use relative coordinates.**
- **`--theme dark` inverts everything uniformly**, including `fontColor`, so it
  never rescues a contrast bug and never creates one. You do not need it to
  check contrast. It is for previewing what a dark-mode viewer sees.
- **Keep the XML uncompressed** so it diffs and greps.

## Bundled resources

### References

- `references/palette.md` -- verified dark and light palettes with measured
  contrast ratios, the contrast rules and why the defaults are traps, type sizes
- `references/xml-reference.md` -- file structure, the escaping rule that
  decides whether a generated file opens, geometry, styles, shapes, pages,
  layers, SVG round-tripping
- `references/layout.md` -- layout heuristics, each with the failure it prevents
- `references/patterns.md` -- diagram structures worth reaching for

### Examples

- `examples/palette-sheet.drawio` -- a working diagram using the dark palette.
  Open it, export it, or copy style strings out of it.

### Script

- `scripts/drawio_tool.py` -- `export`, `lint`, `pages`. Resolves the draw.io
  binary from PATH or the app bundle, so it works whether or not the Homebrew
  cask's `drawio` shim is installed. Override with `DRAWIO_BINARY`.
