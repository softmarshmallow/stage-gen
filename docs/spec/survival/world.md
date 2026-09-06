# Survival world generation

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/components/worldgen/` (the generator),
> `src/stage_gen/recipes/oblique_survival/layout.py` (the binding) and
> `src/stage_gen/recipes/oblique_survival/survival_request.py` (the loader);
> the authored files are `world.toml` and the `placement` blocks in
> `props.toml`, `actors.toml` and `ground.toml` of an
> [oblique-survival package](generation-v1.md). The words are laid out in
> [the vocabulary note](../../research/world-generation-vocabulary.md).

## What the world is

A world is a square of authored extent with a coast inside it, four biomes
solved to their authored shares, a rules-only height, a road, a handful of
**set pieces** (compositions sited whole: the camp the player spawns on, two
boulder rings a walk away) and a **population**: every scattered prop, the mob
and the forage sheet, each standing where its own `placement` block says.
Everything in the population is a thing the player can act on: a prop with an
interaction, the mob, a forage cell that yields an item. The loader refuses a
scattered prop that offers nothing and a sheet of pieces nobody can take
([decision 0060](../../decisions/0060-the-world-places-nothing-the-player-cannot-act-on.md));
a set-piece member may stand inert, because it is a landmark the map marks.

The generator that lays it is a component with no vocabulary. It knows
regions as integers, objects as id strings, and everything else as a number:
a habitat weight, a density, a cluster's parents and size and radius, a
spacing, an attachment, a quota, a keep-out. The recipe binds the package's
words to those numbers and turns the answer into the layout record. Nothing
in `src/stage_gen/components/worldgen/` names a prop, a family, a biome or a
camp, and a test scans it to keep it that way.

The layout is local and free: no provider is called, and the same package
lays the same world byte for byte. Every random draw is **addressed** by
(seed, object, cell, index) rather than taken from a stream, so an edit to one
object's block moves that object's points and, within one footprint of them,
nothing else. A pinned digest names the world the library package lays.

## What is authored, and where

| File | Table | What it says |
| --- | --- | --- |
| `world.toml` `[world]` | `seed`, `size_meters` (64..1024) | the extent; plates cap at 1024 cells, so a 512 m world draws 0.5 m cells |
| `[landmass]` | `land_share`, `coast_noise_lattice`, `coast_crinkle`, `shore_margin_meters`, `height_octave_lattice`, `height_octave_weight` | the coast, solved to its share; the height, 0 at the coast and 1 inland, with one finer octave |
| `[biomes]` | `islet_lattice`, `islet_share` | the second, finer octave that makes each biome a patchwork inside the others; the plates and shares stay in `ground.toml` |
| `[spawn]` | `set_piece` | the set piece the player spawns on, at its `spawn` offset |
| `[[set_pieces]]` | `set_piece_id`, `count`, `at` (`"origin"` or `{ distance_meters = [near, far] }`), `biome`, `clearing_radius_meters`, `pad_decal`, `spawn`, `members` (`prop`, `state`, `dx`, `dz`, `pad_scale`) | compositions sited whole; exactly one stands at the origin and is the spawn; the rest draw an area-uniform site in their band on their biome and refuse by name when none exists |
| `[population]` | `order` | an optional explicit order; empty means hosts before what attaches to them, avoided before avoiders, then by id |
| `props.toml` `[props.placement]` | the placement block | where and how the prop is scattered; absent means never (a station is built, a camp prop is a member) |
| `props.toml` | `canopy_radius_meters` | the soft disc of shade the plate carries under a placed instance in a starting look; 0 means none |
| `actors.toml` `[mob.placement]` | the placement block | the hounds: their packs, their count, what they keep away from |
| `ground.toml` `[forage.placement]`, a cell's `placement` | the placement block | how the forage sheet's cells are scattered; a cell may carry its own block and become an object of its own (`forage/8`) |

### The placement block

```toml
[props.placement]
habitat = { forest_floor = 1.0, mossy_bog = 0.45, dry_meadow = 0.15 }   # weight per biome; absent = 0
# exactly one process:
density_per_100m2 = 0.2          # Poisson: this many per 100 m² where the weight is 1
cluster = { parents_per_100m2 = 0.07, mean_size = 7.0, radius_meters = 7.0 }   # Matérn cluster
spacing_meters = 11.0            # alone: a jittered grid, even cover thinned by the habitat
near = { host = "pine", radius_meters = 2.5, mean = 0.8, chance = 0.6 }        # attached to a host's points
# shaping:
edge = { of = "water", within_meters = 5.0, falloff_meters = 3.0, outside = 0.0 }   # of: water | biome | road | set_piece
height = { min = 0.0, max = 0.35, falloff = 0.1 }
chance = 0.9                     # rarity: per cluster, else per point
min_per_world = 100              # quota; the minimum tops up, the maximum truncates
max_per_world = 600
avoid = [ { target = "campfire", radius_meters = 30.0 } ]
clearing_radius_meters = 0.0     # ground the object keeps free once placed
```

A density is **where the habitat weight is 1**, proportionally fewer where it
is lower, none where it is 0. A cluster's density is parents × mean size ×
chance. `spacing_meters` beside a Poisson density is the object's own hard
core; alone it is the process. `near` and `avoid` name any placed object, the
mob, the forage sheet, or a set-piece member by its prop id; a cycle is refused.

## What the generator does

1. **Fields.** Regions from one value-noise field per non-base biome,
   thresholded to its share and corrected over sixteen rounds, plus the islet
   octave; every region fades out over the spawn's clearing, so the spawn
   stands on the base biome by rule. The coast from noise and a radial
   falloff, solved to `land_share`, with a bump under the spawn. The height
   from the coast's relief without the bump, the coast at 0 and the 99th
   percentile of the land at 1. Distances (a chamfer transform on a 2 m
   analysis grid) to the water, to a biome's edge, to the road, to a set piece.
2. **Set pieces**, then the road out of the spawn's clearing.
3. **Objects, in order.** Candidates from the object's process, each flagged
   by whether it survived the random thins; sorted by a hashed priority so
   acceptance never depends on generation order; **tier 1**, the object's own
   spacing, greedy; the quota on that set (the maximum truncates the priority
   order, the minimum tops up from the thinned-out reserve by intensity);
   **tier 2**, every earlier object's footprint and the `avoid` rules, which
   only ever deletes. A drop never promotes, so an edit cannot cascade.
4. **Marks.** Each point carries hashed unit floats the binding turns into the
   instance seed (and so the variant look), the sheet cell, the turn and the
   scale.
5. **Plates.** The world splat (road in red, canopy in green from the
   attribute, land in alpha) and the biome plate, streamed row by row.
6. **Measurement.** Per object, the same pipeline with its process replaced by
   plain Poisson, nine times from a fixed salt, is the null: `r_mc` is the
   mean nearest-neighbour distance over the null's, `k_ratio` the neighbours
   within the cluster radius over the null's. A cluster block that came out
   random (`r_mc > 0.85` and `k_ratio < 1.4`), or a spacing that came out
   random (`r_mc < 1.15`), is a refusal; under thirty points it is reported
   and never refused. The textbook Clark–Evans index is not used: on a
   habitat shattered into islets it measures the support, not the pattern.

## What the record carries

`package/world/layout.json`, embedded verbatim in the manifest as `layout`:
the `entities` (with `cluster`, the grove or host an instance came with, and
`set_piece`, the instance it is a member of), `set_pieces`, the forage pieces
(`forage`), the decals (pads under members, skirts, puddles), the road polyline,
`counts`, `biome_shares`, `land_share`, `cell_meters`, and a `report` per
object: the placement tally (candidates, reserve, dropped by its own core, by a
neighbour, truncated, topped up) and the measurement (`r_mc`, `k_ratio`,
`verdict`). The manifest also publishes `world` (the seed, the extent, the
set pieces as authored) and `cell_meters` on both plates, so a host never
infers a cell size.

## What is refused, offline

A `[world]` table in `survival.toml`, `density_share`, `biome_weights`,
`gameplay.mob_count` or a sheet's `density_per_100m2`: all moved to the
object's block, and named as such. A `[clutter]` or `[plants]` sheet, and a
scattered prop with no interaction: decoration, which the world does not
place. An unknown key anywhere. A habitat naming
a biome nobody drew, a `near` or `avoid` naming nothing, two processes in one
block, a maximum below a minimum, a set piece with a member in no declared
state or a pad with no pad decal, two origins, a spawn that is not the origin.
At layout time: a cell expectation beyond the sampler, a grove packed denser
than its own spacing allows, a cluster radius wider than the patches its
habitat comes in, a set piece with no site, a quota the reserve cannot meet,
a pattern that did not come out as authored. A refused world never reaches
the manifest.

## Non-goals, this pass

Biome adjacency rules (which biome may touch which); rendered relief (the
height is a rule, not a picture); progression gating; worlds past 512 m,
which need the host to stream cards; a road between set pieces (the one track
still leaves the spawn); a semantic designer over the generator.

## Dated log

- 2026-09-07: the population is only what the player can act on; the litter
  and plant sheets and the inert fern clump are refused (decision 0060).
- 2026-09-06: landed. The first world generator was a single random stream,
  uniform inside a biome, with the camp in code and a family density budget;
  this replaces it with the component, the object-owned `placement` block,
  `world.toml`, set pieces, a 512 m Ember Hollow at the first world's card
  count, and the Monte-Carlo pattern gate.
