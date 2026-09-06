# 0060 — The world places nothing the player cannot act on, and everything it places is sized

## Fact

The survival ground carried three sheets of pieces: a litter sheet of sixteen
decorative cutouts scattered flat, a forage sheet of sixteen pickups scattered
flat, and a standing-plant sheet of sixteen knee- to waist-high cards. Beside
them stood one prop, the fern clump, scattered under the pines with no
interaction at all. Every piece of every sheet was drawn to fill a cell of one
size — 0.42 m for the litter, 0.5 m for the forage, 1.4 m for the plants —
whatever the brief said the thing was, and the host laid each as a square of
that one size: a pebble and a slab of stone were the same 42 cm, a flint chip
and an arm-long branch the same 50 cm, a shin-high heather and a waist-high
reed the same 1.4 m.

The user, playing: "decals (non interactive) ones are too big, they feel like
they were meant to be interacted; the small objects are too small, they feel
like they are decal." And on the drawing: "the stroke size vary — that pencil
stroke is one of the significant role with this specific style of arts, and
they dont align, thus making things wonky — the trees feels perfect, but else
they seem like from other universe."

Measured, all three were the same overlook. A litter stone lay beside a forage
stone at the same size, one answering the hand and one not. The forage pieces'
painted extents stood at 0.14 to 0.25 player heights while the package floor
for a prop was 0.25 and the same stone dropped from the pack lay at 0.24; nine
pickups were authored at 0.20 to 0.24, under the floor a prop keeps. And the
drawing scale of the set ran from 78 px/m (the pine, on a 2x2 sheet) to 1,900
px/m (the berry, alone on a 1024 px canvas) — a 24x spread — against a
play-zoom screen ruler of 79 px/m at the 900 px reference window. The image
model draws its ink line at a few canvas pixels whatever the canvas holds, so
the pine's line reached the screen 5.6 px wide and the grass tuft's 0.2 px:
the trees, drawn within 1.3x of the screen ruler, kept their pencil, and
everything drawn 3x to 24x over it lost it to minification. "Feels perfect"
and "from another universe" are the two ends of one measurement.

## Challenge

The cheap reading is three tunings: shrink the litter, grow the forage, and
ask the small things for a heavier line. Each moves a number the author is
already allowed to move.

None of them is the fix. Shrinking a decoration until it no longer reads as a
thing to click is a race with the eye that decoration cannot win on ground
that also carries things to click; the reference genre has no decoration on
its ground at all, and that is why its ground is legible. Growing the forage
by hand repeats the mistake that sized the sheets in the first place: the
cell was the size, so nothing in the contract said what the thing was. And a
heavier line by adjective buys 2x to 7x where the minification costs 3x to
24x (the flint pickup came back with a 25 px line and reached the screen at
1.4 px); the stroke is a function of the drawing scale, and no clause moves
the scale.

## Ruling

**The world places nothing the player cannot act on.** A scattered object
must be a prop with at least one interaction, the mob, or a forage cell that
yields an item. `ground.toml` is `oblique-survival-ground-v2`: `[clutter]` and
`[plants]` are refused by name, and the forage is the only sheet of ground
pieces. `props.toml` is `oblique-survival-props-v3`: a prop with a
`[props.placement]` block and no `[[props.interactions]]` is refused by name.
A set-piece member may stand inert — it is a landmark the map marks,
composed by hand and placed once — because the rule is about the scatter: the
population is what the player learns the ground by. What the ground looks
like between the things on it is the plates' job, which is what the material
contract already said.

**Everything placed is sized, in one unit, above one floor.** A forage cell
carries `size_units`, its longest extent in player heights, authored like a
prop's `height_units` and for the same reason: an image model returns no
size, and a cell's pixels are only a ruler. The manifest calibrates each cell
from its own painted extent against its number (`box`, `px_per_meter`,
`size_meters`) and keeps the drawing's opinion beside it (`drawn_size_meters`)
as a recorded drift, never a gate — exactly the prop mechanism. The floor,
`[scale] minimum_height_units`, now holds for every thing the player can act
on: a prop's height, a pickup's height, a forage piece's span; the loader
refuses under it, and refuses a piece wider than the cell it is drawn in. The
manifest's `scale` block publishes the floor in metres and — when the camera
block states the window height its numbers were tuned in
(`reference_height_px`) — the play-zoom screen ruler and the floor in screen
pixels, so an author sees what the number means (34 px at 900 px tall).

**The host draws what the manifest sizes.** `oblique-survival-manifest-v2`:
the ground block has one sheet, `layout` has one list of pieces, and a forage
cell without its box and ruler is refused by the host rather than guessed at.
The forage quad is the painted box over the cell's ruler, windowed on the box,
so a flint chip and a bundle of branches lie at their own sizes and centred on
their entries. The litter and plant views, and the leaf burst that borrowed
the litter's fallen cells, are gone with the layers.

**The stroke is measured and reported, and its fix is named.** The drawing
ruler spread is a fact of the set, computable from the manifest alone (each
look's `px_per_meter` against `scale.screen_px_per_meter`). Its fundamental
fix is one drawing ruler for the set: every asset drawn at a canvas or lattice
cell whose pixels per metre sit near one number, so the model's few-pixel ink
line reaches the screen at one weight. That is a redraw of most of the set and
a change to how canvases and lattices are chosen; it is not made here, because
the user has not opted into the spend, and the number this decision leaves
behind is the argument for it: everything drawn within 2x of the screen ruler
reads as one universe, and nothing drawn past 3x does.

## Consequences

- Ember Hollow loses the fern clump (128 instances), the litter (4,314 pieces),
  the plants (3,275 cards) and the winter plant look; nothing else moves. The
  forage sheet's sixteen cells are sized 0.26 to 0.34 player heights on a 0.6 m
  lattice, and nine pickups rise to the floor. Zero provider operations: the
  adopted takes re-admit through the gate, the layout is derived, and the
  cache-key golden shows no image node moved.
- The mid-scale texture the plants gave the meadow is gone. If the meadow wants
  it back, it comes back as things the player can gather, not as decoration.
- Any later "wider sheet" or "drawing ruler" work sizes from `size_units` and
  the screen ruler, never from a cell.
