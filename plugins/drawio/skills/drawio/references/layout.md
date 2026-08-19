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

## Over-allocate height, because draw.io will not

**Failure:** the label spills outside the shape, or with `overflow=hidden`
disappears with no cue.

draw.io never grows a shape to fit its label. Size the box for the text you
actually wrote, then confirm in a render. The linter's estimate is deliberately
crude and it does not model every shape: `shape=note` loses width to its folded
corner, `shape=cylinder3` loses height to its cap, and a swimlane's label lives
in the title bar rather than the body. Treat a clean lint as "no obvious
overflow", not "it fits".

## Paint order is a layout tool and a hazard

Later cells cover earlier ones. Draw bands first and their contents after, and
the bands read as a backdrop. Get it backwards and a band erases everything
inside it.

The same rule makes a legend dangerous: it is authored last, so it is on top of
everything. The linter reports a shape that is substantially covered by one
drawn after it.

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
