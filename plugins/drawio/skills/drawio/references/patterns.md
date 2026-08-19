# Diagram patterns

Structures worth reaching for, and what each one buys.

## Bands on one axis, ownership on the other

Horizontal bands for layers, vertical columns for who owns them.

The reason to prefer this over a free-form graph is that it makes absence
readable. A band populated in only one column says "this layer is one team's
problem" without a sentence of explanation, and a column that is empty in a
band says that team does not participate at that layer. You get those claims
for free, and they are usually the claims a reader most wants.

The cost is that the grid must be honest. Do not add a column to balance the
composition, and do not move a box out of its true band because the true band
is crowded.

## A question per band

Put a callout on each band stating the question that layer answers:
"Who is this user?", "Which modules may they reach?", "What may they do in
there?".

This is cheap and it survives being screenshotted out of context, which is what
actually happens to diagrams. It also disciplines the diagram: a band whose
question you cannot write in one line is probably two bands.

Keep the callouts in the reserved annotation margin. A callout dropped into the
graph covers an edge (see `layout.md`).

## Multi-page: context, then detail, then sequence

Different readers want different zoom levels, and one canvas cannot serve them
all without becoming unreadable for everyone.

A shape that works:

1. System map. Everything, at low detail.
2. The part you are changing, at high detail.
3. One page per interesting sequence.

Pages live in the same file (repeated `<diagram>` elements), so the set travels
as a unit while any single page can still be exported and sent alone.

## Sequence diagrams where ordering carries the meaning

Box-and-arrow diagrams cannot say "this happens before that", and ordering is
usually where the surprises are: the double-provisioning, the request that
arrives before the record exists, the retry that hits a different backend.

If the interesting thing about a flow is its order, a box diagram will hide
exactly the thing you are trying to show.

Use `shape=umlLifeline` for the participants. Lifeline x-coordinates and
message y-coordinates are arithmetic, which makes these the best candidate for
generation.

## Generate repetitive structure, then stop

A sequence diagram's coordinates are a loop. So are a grid of modules and a
matrix of services. Writing that XML by hand is error-prone in a way that a
20-line script is not.

**The generator is scaffolding.** The moment a human opens the file and nudges
anything, the script is stale, and a stale generator that still looks
authoritative is worse than no generator. Delete it, or commit it clearly
marked as the thing that produced the first draft and is not maintained.

Do not build a generator for a diagram you will only write once.

## Ship `.drawio.svg`

```sh
drawio --export --format svg --embed-diagram --embed-svg-fonts false \
  --output arch.drawio.svg arch.drawio
```

One file that is simultaneously a valid SVG (renders in a README, a Confluence
page, a GitHub comment) and a draw.io source that reopens fully editable.

This removes the drift problem. The alternative is a `.drawio` source plus an
exported `.png` that someone forgets to regenerate, after which the image
everyone looks at and the source everyone edits disagree, and no one can tell
which is current.

## Colour as category, not decoration

Assign each colour a meaning and put the mapping in a legend. Verified fills
are in `palette.md`.

The test: if you can swap two colours and the diagram means the same thing, the
colours are decoration and are costing the reader attention for nothing. Either
give them meaning or make everything one neutral fill.

## Say what a box is, not just what it is called

`Forge Core API` with a muted second line reading
`GET /api/v1/me/access -- the Layer 2 answer` is worth three boxes of prose. A
box label that is only a proper noun forces the reader to already know the
system, which defeats the diagram.

Bold first line, muted detail lines under it, using a `<font color>` span.
