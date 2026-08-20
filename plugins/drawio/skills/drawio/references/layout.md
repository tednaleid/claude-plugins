# Layout

Every heuristic here exists because of a specific way diagrams fail. The
failure mode is the reason to follow it, and it is what tells you whether the
rule applies to a case not listed.

## Never place an element between two things you have connected

**Failure:** the element covers the arrow, and the relationship silently
vanishes from the diagram. A reader does not notice a missing edge; they
conclude the two things are unrelated.

Legends, notes and callouts are the usual culprits, because they get positioned
last, into whatever gap is left, and a gap between two connected boxes is
exactly where the edge runs.

Put annotations in a reserved margin: a column down one side or a strip along
the bottom. Then no annotation can ever land on the graph.

## An edge is a claim about a real path

**Failure:** the diagram teaches a wrong model, and someone acts on it.

If a request goes browser to load balancer to service, an edge from browser
straight to service is not a simplification, it is an assertion that the load
balancer is not in the path. Someone will read that diagram while debugging and
lose an hour.

Verify topology against the source of truth (terraform, config, routing rules),
not memory. This is the single highest-value check in the whole workflow,
because it is the only error class that survives being beautiful.

**Check the specific instance the diagram depicts, not a sibling that resembles
it.** Reading the source of truth is not sufficient if you read the wrong one.
One system had in-repo modules path-routed on a shared origin and federated
remotes on separate origins resolved from build-time environment variables.
Both are real, both live in the same repo, and the first one opened was not the
one being drawn. Where a system has more than one deployment shape, name on the
diagram which one it is about.

## Long cross-canvas edges mean the layout is wrong

**Failure:** the router picks a path through unrelated shapes, and you spend
your time adding waypoints to fight it.

An edge that has to traverse the whole page is telling you that two closely
related things are far apart. Move them together, or split the page. Adding
waypoints treats the symptom.

## Reserve gutters for edge labels

**Failure:** an edge label renders on top of a band title or another label.

A label wants 150 to 250px of clear space along its edge. Whitespace between
rows of boxes is not slack to be minimized; it is where the labels go. If two
bands are 40px apart, an edge crossing between them has nowhere to put its
text, and draw.io will put it somewhere anyway.

## Over-allocate height, but not by much

**Failure:** the label spills outside the shape, or with `overflow=hidden`
disappears with no cue.

draw.io never grows a shape to fit its label. Size the box for the text you
actually wrote, then confirm in a render. The linter's estimate is deliberately
crude and it does not model every shape: `shape=note` loses width to its folded
corner, `shape=cylinder3` loses height to its cap, and a swimlane's label lives
in the title bar rather than the body. Treat a clean lint as "no obvious
overflow", not "it fits".

**The opposite failure is more common and less obvious.** Over-allocating
pushes toward note boxes several times taller than their copy, which read as
something that failed to load. Size boxes once the copy is final rather than
reserving space up front, and re-check on the render. The linter reports this
as `underfilled`, but only above a minimum height, so a box that is merely a
bit roomy will not trip it and will not be caught by anything except looking.

## Balance text density between siblings of different widths

**Failure:** a narrow box crammed with four dense lines beside a wide box
holding one line and acres of space. Both are individually correct and together
they look broken.

When siblings must differ in width because they align to something else, move
shared or optional content into the wider one rather than splitting it evenly.

## Give a container padding

**Failure:** boxes placed at the container's own coordinate sit flush against
its border and read as a rendering bug.

This happens when the container and its first child are authored from the same
number. Use a consistent inset on all four sides, around 40px at the scales
above. Where a container sits above or below ungrouped siblings, align the
*children* with those siblings and let the container overhang, not the reverse.

Reported as `container-padding`. A swimlane's usable top edge is its title bar,
not zero.

## A container's title collides with anything entering the top

**Failure:** arrows entering a container from above cross its title text.

Two fixes, chosen by shape:

- **Label the container along the bottom** with
  `verticalAlign=bottom;spacingBottom=14`. Correct when arrows enter the top and
  nothing exits the bottom. It reads naturally, like a bracket label.
- **Keep the title short enough to fit a clear zone.** Necessary when arrows
  both enter and exit, so neither edge is free.

## Compute the clear zones before writing a band title

**Failure:** a centred band title looks fine in isolation and lands on two of
the eight arrows crossing the band.

When N vertical channels cross a horizontal band, the only place text can live
is the gaps between them. Enumerate the channel x positions, find the widest
gap, and size the title to it. With channels at
`300, 580, 1090, 1370, 1830, 2110, 2570, 2850`, the widest interior gap is
`1370-1830`, so a centred title must stay under about 440px, which is roughly 19
characters at 27px bold.

This is arithmetic, not judgement. Do it before writing the title rather than
discovering the collision in the render.

## Put markers at the midpoint of a gutter

**Failure:** a numbered step disc overlapping the border of the band its arrow
just left.

A 56px disc centred 10px below a band overlaps it by 18px. Place a marker at the
midpoint of the gutter it sits in and check its radius against both edges. The
linter reports this as `straddle`, because a small shape crossing a border
covers too little of the larger shape to register as an overlap.

## Derive channel positions from box centre lines

Hand-placed arrow positions read as approximate. Deriving them makes the same
drawing read as a grid:

```
down_channel = col_x + col_width/2 - k
up_channel   = col_x + col_width/2 + k
```

Every box then has its two arrows symmetric about its own midpoint, and boxes
that share channels line up automatically. Choosing `k` once per page is the
only decision left.

## Paint order is a layout tool and a hazard

Later cells cover earlier ones. Draw bands first and their contents after, and
the bands read as a backdrop. Get it backwards and a band erases everything
inside it.

The same rule makes a legend dangerous: it is authored last, so it is on top of
everything. The linter reports a shape that is substantially covered by one
drawn after it.

There is a third position, and it says something no label can. Order a line
*between* a container and its contents:

```
band  ->  the return arrow  ->  the boxes inside the band
```

The arrow is visible crossing the band's background and disappears behind the
specific box it does not interact with. That encodes "the response travels back
over this connection, and this component does not act on it" with no annotation
at all. The ordering is unobvious and easy to get backwards, so write it down
when you use it.

## Bands and columns

Layers as horizontal bands, ownership as vertical columns. The payoff is that
**emptiness becomes information**: a band populated in only one column shows at
a glance that the layer belongs to one team, with no prose at all.

This only works if the columns are honest. A column that exists to balance the
picture destroys the property that makes the grid worth using.

## Grid discipline

Pick a step (10 or 20px) and put every x, y, width and height on it. Diagrams
drift out of alignment one hand-nudge at a time, and misalignment reads as
carelessness long before anyone can say why.

Give sibling boxes identical dimensions unless a difference means something.
Varying box sizes implies varying importance, so if size does not carry
meaning, hold it constant.

## Sizing the page

Set `pageWidth` and `pageHeight` to something the content fits inside. Image
export crops to the content, so an oversized page costs nothing there, but PDF
export and the editor's page-break guides both use it, and a diagram that
straddles a page break is annoying to work with.

## When it will not fit

Splitting into pages is nearly always better than shrinking the font or
tightening the gutters. A dense page that is technically legible at 100% zoom
becomes unreadable the moment someone pastes it into a document at half size.
