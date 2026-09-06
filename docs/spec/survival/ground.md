# Survival ground

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/recipes/oblique_survival/layout.py` and
> `src/stage_gen/recipes/oblique_survival/gates.py`; the authored file is
> `ground.toml` in an [oblique-survival package](generation-v1.md).

The ground is the one asset in this recipe that is a **material rather than a
picture**. Everything recognisable — a tuft, a twig, a stone, a flower — stands
on it as its own cutout with its own contact, and nothing identifiable is
painted into the surface. That separation is what lets a season whiten the
ground and cap the plants in the same frame, and it is the rule every plate
brief is written against.

## The layer stack

Seven layers, six generated and one algorithmic, composed by the consumer in one
shader over the two structural plates the layout writes.

| Layer | Authored as | Span | What it is |
| --- | --- | --- | --- |
| biome plates | `[[biomes]]`, `material = "field"` or `"fabric"` | 2 m | one material plate per biome, tiled by the consumer |
| weather cover | `weather.toml [conditions.<id>.cover]` | 2 m | a pale plate laid over every biome by the condition's factor through a torn erosion |
| macro field | `[macro]` | 24 m, read over `period_meters` | value only, in the turf's own hue: the plate's luma over its measured mean, at an authored strength |
| litter sheet | `[clutter]` | one cell per piece | flat cutouts scattered by the layout, re-aimed on a camera turn, darkened under canopy |
| forage sheet | `[forage]` | one cell per pickup | the litter's twin, drawn a step brighter and heavier; each cell names the item it yields |
| standing plants | `[plants]` | one cell per plant | the mid-scale: knee- to waist-high cards stood up on the ground, sized from each cell's gated box |
| road, water | `[road]`, `[water]` | 2 m, 6 m | a track plate laid on the splat's red channel; a plane below the coast with its own depth |

**The two structural plates the layout writes.** `world/splat.png` carries the
road in red, the under-canopy shade in green, and the land mask in alpha.
`world/biomes.png` carries one biome per channel, solved to its authored share.
Four biomes is therefore the capacity, and the loader refuses a fifth with that
sentence rather than emitting a plate no consumer can blend.

A biome is a continent on a coarse lattice plus islets on a finer one, both
thresholds solved together so the authored shares still hold. The islet octave
fades out over the camp clearing, so the spawn never lands on a patch the fine
noise happened to drop at the world's centre.

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
| cell isolation | litter `(0.02, 0.60)`, plants `(0.03, 0.85)`, inset `0.03` | an empty cell, an overflowing cell, or a cell touching a guide line |
| sheet seam | searched `0.15` either side of each half line | a cut through a drawing rather than through the emptiest gap |
| decal | soft-edge share `0.05`; irregularity `0.12` | a hard-edged decal, and a ground patch that is a perfect disc |

A field plate and a fabric plate are measured by the same metric with different
limits, because they are different materials: a field is a mostly plain surface
with sparse marks, a fabric is a drawn stroke in every square metre.

## What the manifest publishes

Per biome: the plate's path, its span in metres, its measured mean and its
authored target, and its material. Per sheet: the atlas, the cell windows, and
each cell's gated box, so a consumer sizes a card from the drawing rather than
from the cell. Plus the macro field, the road, the water and its depth, the
decals with their uses, the two structural plates, and the whole `[blend]`
table as mixing.

## Non-goals

- A directional road surface. A splat road has no direction, so its ruts cannot
  follow the track; that is correct for packed earth and wrong for planks. The
  ribbon along the layout's polyline is the fix and is not built.
- A real cliff side. The coast is a mask, not a polyline; the depth band on the
  water says most of what a raised slab would.
- A heightmap. There is no low ground, so puddles are scattered rather than
  solved, and the same hollows fill every storm.

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
