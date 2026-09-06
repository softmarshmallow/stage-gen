# Survival ground

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/recipes/oblique_survival/layout.py` and
> `src/stage_gen/recipes/oblique_survival/gates.py`; the authored file is
> `ground.toml` in an [oblique-survival package](generation-v1.md).

The ground is the one asset in this recipe that is a **material rather than a
picture**. Everything recognisable — a tuft, a twig, a stone — stands on it as
its own cutout with its own contact, and nothing identifiable is painted into
the surface. That separation is what lets a season whiten the ground and cap
the props in the same frame, and it is the rule every plate brief is written
against.

And **nothing lies on the ground that the player cannot act on**
([decision 0060](../../decisions/0060-the-world-places-nothing-the-player-cannot-act-on.md)).
The one sheet of ground pieces is the forage, every cell of which yields an
item and carries its size. A litter sheet of decorative cutouts and a
standing-plant sheet stood here through ground-v1, and in play a decorative
stone beside a forage stone was two things the eye could not tell apart; the
loader refuses both by name now, and what the ground looks like between the
things on it is the plates' job.

## The layer stack

Five layers, four generated and one algorithmic, composed by the consumer in one
shader over the two structural plates the layout writes, and the forage sheet
laid over them as instanced quads.

| Layer | Authored as | Span | What it is |
| --- | --- | --- | --- |
| biome plates | `[[biomes]]`, `material = "field"` or `"fabric"` | 2 m | one material plate per biome, tiled by the consumer |
| weather cover | `weather.toml [conditions.<id>.cover]` | 2 m | a pale plate laid over every biome by the condition's factor through a torn erosion |
| macro field | `[macro]` | 24 m, read over `period_meters` | value only, in the turf's own hue: the plate's luma over its measured mean, at an authored strength |
| forage sheet | `[forage]` | one cell per pickup, `cell_meters` the lattice's drawing scale | flat cutouts scattered by the layout, re-aimed on a camera turn, darkened under canopy; each cell names the item it yields and its `size_units` |
| road, water | `[road]`, `[water]` | 2 m, 6 m | a track plate laid on the splat's red channel; a plane below the coast with its own depth |

**The two structural plates the layout writes.** `world/splat.png` carries the
road in red, the under-canopy shade in green (from each prop's authored
`canopy_radius_meters`, never a family rule), and the land mask in alpha.
`world/biomes.png` carries one biome per channel, solved to its authored share.
Four biomes is therefore the capacity, and the loader refuses a fifth with that
sentence rather than emitting a plate no consumer can blend. Both plates cap at
1024 cells a side and publish their `cell_meters`, so a 512 m world draws 0.5 m
cells and no host infers the size.

A biome is a continent on a coarse lattice plus islets on a finer one, both
thresholds solved together so the authored shares still hold. Every region
fades out over the spawn's clearing, so the spawn stands on the base biome by
rule. The islet lattice and share are `world.toml [biomes]`; how anything is
scattered over the plates is [world](world.md).

## The material contract

A plate brief asks for a material and never for a scene. The clause is: mostly
bare, at least three quarters plain ground colour, marks close to the ground's
own tone. Two rules constrain how it is written:

- **State span and largest feature in centimetres.** A plate is a piece of
  ground at a stated size, and the largest mark on it is stated in the same
  units. Value drops as detail gets finer: past a point the marks stop being
  ground and start being noise.
- **Never say "dark" or "darker" in a plate prompt.** Contrast is carried by
  hue; value is set afterwards by the consumer's gain. A brief that asks for
  value fights the leveller and loses.

**Levelling is a consumer lever.** Each plate's measured mean travels in the
manifest and the consumer applies `target / mean` as a linear gain, clamped to
`[0.5, 2.5]`. A leveller is the right runtime lever and the wrong substitute for
a plate that arrives at its value; a plate that hits the clamp is an authoring
problem, not a mixing one.

**Colour space.** A data plate is data: the splat, the biome weights and the
macro field are linear and must not be treated as colour. A colour plate is
colour. A consumer whose custom shader forgets the renderer's own encode shows
the whole world too dark, and that failure is invisible to every gate here
because it happens after the manifest.

## `[blend]` is mixing

Every field in `ground.toml [blend]`, `[macro] period_meters`, and the per-biome
display `level` override is **mixing**: it reaches the manifest and no cache key
reads it. Edge softness and tear, the carpet shadow and its width, the cut's ink
and its width, the texture-bombing cell size and turn, the field strength and
period, the ground exposure, the decal gain and the cliff depth are all numbers
a consumer applies and a person retunes for free.

The line between mixing and spend is the whole reason the split exists: retuning
an edge costs nothing, and redrawing a plate costs an image operation.

## Gates

Every plate and every sheet cell is measured before it is accepted; the
thresholds are in `src/stage_gen/recipes/oblique_survival/gates.py` and the
[recipe spec](generation-v1.md) tabulates them beside the rest. The ones that
belong to the ground:

| Gate | Threshold | Refuses |
| --- | --- | --- |
| value band | field `(0.30, 0.84)`; fabric `(0.20, 0.84)`; water `(0.14, 0.60)`; cover `(0.55, 0.97)` | a plate too dark to lift without banding, or a cover darker than what it hides |
| block uniformity | deviation `0.12` over `4` blocks | a plate with a bright or dark quarter |
| corner ratio | `(0.90, 1.10)` | a vignette baked into a tiling plate |
| busy-ness at play zoom | field `0.062`, fabric `0.14`, measured at 70 px per metre | speckle that reads as noise; **a fabric has its own limit because the field limit would refuse a drawn turf** |
| macro no-ink | edge mean `0.02`, value `(0.36, 0.68)`, half deviation `0.22` | drawing inside a plate whose job is a colour field |
| tile edge | `6/255` | a seam where a plate meets its own repeat |
| cell isolation | pieces `(0.02, 0.60)`, inset `0.03` | an empty cell, an overflowing cell, or a cell touching a guide line |
| sheet seam | searched `0.15` either side of each half line | a cut through a drawing rather than through the emptiest gap |
| decal | soft-edge share `0.05`; irregularity `0.12` | a hard-edged decal, and a ground patch that is a perfect disc |

A field plate and a fabric plate are measured by the same metric with different
limits, because they are different materials: a field is a mostly plain surface
with sparse marks, a fabric is a drawn stroke in every square metre.

## What the manifest publishes

Per biome: the plate's path, its span in metres, its measured mean and its
authored target, and its material. For the forage sheet: the atlas, and per
cell the cut, the painted `box` inside it, the authored `size_meters`, the
`px_per_meter` that calibrates the one to the other, and `drawn_size_meters`
— the drawing's opinion at the lattice's shared scale, a recorded drift and
never a gate, as a prop's `drawn_height_meters` is. A consumer sizes a piece
from the box and the ruler; the cell is the cut. Plus the macro field, the
road, the water and its depth, the decals with their uses, the two structural
plates, and the whole `[blend]` table as mixing. The manifest's `scale` block
publishes the floor every placed thing keeps, `minimum_height_units`, in
metres and — when `[camera] reference_height_px` is stated — in screen pixels
at play zoom beside `screen_px_per_meter`.

## Non-goals

- A directional road surface. A splat road has no direction, so its ruts cannot
  follow the track; that is correct for packed earth and wrong for planks. The
  ribbon along the layout's polyline is the fix and is not built.
- A real cliff side. The coast is a mask, not a polyline; the depth band on the
  water says most of what a raised slab would.
- Rendered relief. The world has a rules-only height now (0 at the coast, 1
  inland; reeds read it), but no low ground is drawn, so puddles are scattered
  rather than solved, and the same hollows fill every storm.

## Dated log

- **2026-09-05.** The reference set was read layer by layer and the first four
  consumer-side passes landed: two-scale biome layout, texture bombing, the
  own-hue value-only macro field, and carpet edges — all mixing, no operations.
  The display encode was found missing in the consumer, which had shown every
  plate gamma-dark; the value band's ceiling moved once the display was honest.
- **2026-09-06.** The frames were measured rather than eyeballed, against
  reference play shots: ours read twice as bright, half as saturated, at a tenth
  of the local contrast. Two plates were re-briefed as fabrics and adopted from
  an audition; the fabric bands were added because the field limit would have
  refused the reference itself. The mid-scale landed as `[plants]`, and the camp
  was moved onto the base biome. Fourteen audition draws; the adopted takes cost
  nothing.
- **2026-09-06, later.** The scatter became a generator: the litter, forage and
  plants are objects of the world generator with their own `placement` blocks,
  the canopy shade is a prop attribute, and the world is 512 m. See
  [world](world.md).
- **2026-09-07.** The litter and the plants are gone, and the fern clump with
  them: the world places nothing the player cannot act on. A forage cell
  carries `size_units` above the package floor and the manifest calibrates it
  from its painted box; nine pickups rose to the floor. Zero operations. The
  drawing-ruler spread that makes the small things' ink vanish (78 to 1,900
  px/m against a 79 px/m screen) is measured in decision 0060 and left as the
  next redraw's brief.
