# Review diagrams

One or more diagrams at the top of a review help the reviewer understand what
the branch does before reading findings. Pick the shape from what the change
actually is; skip diagrams for trivial or docs-only branches.

## Choosing the diagram

- Sequence diagram (default): control flow across components, request paths,
  new interactions between services or layers.
- ER-style diagram: schema changes, new tables, relationship changes.
- State diagram: lifecycle changes, new status fields, transition rules.
- Component diagram: architectural moves, new services, dependency direction.

Multiple diagrams are fine when the branch does more than one thing; order
them most-important first. When SVG is the wrong tool, an `html` asset passes
a fragment through verbatim.

## Authoring rules

Write the SVG file into the round directory and reference it from
`[[assets]]` with a caption. The renderer inlines it.

- Canvas: width 1000, height as needed. `viewBox` set, no fixed pixel
  width/height attributes beyond the viewBox.
- Palette (matches the tracker theme): background transparent, boxes
  `#1c2030` with `#2a3042` borders, text `#e6e8ee`, muted text `#9aa3b2`,
  accents `#7aa2f7` (primary), `#f7768e` (problem areas), `#9ece6a` (new or
  added elements), `#e0af68` (changed elements).
- Text: minimum font size 12, `font-family="ui-monospace, SFMono-Regular,
  Menlo, monospace"` for identifiers, sans-serif for prose labels.
- Label the diagram in terms of this branch: mark new elements ("new"),
  changed elements ("changed"), and the finding ids they relate to (e.g.
  "f3") where relevant.
- No emojis. No decoration that does not carry information.
