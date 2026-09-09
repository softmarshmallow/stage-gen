# Side-view platformer terrain atlas

> **Checked by:** `tests/contract/test_docs_check.py`.

The prepared-game ground contract is `terrain-atlas-3x3-minimal-v1`. It is a
Godot-compatible 3x3-minimal terrain topology carried in a 12-column by 4-row
atlas. It is not a 9-slice and it does not encode true smooth slopes.

## Ownership

- `stage_gen.media.guide_lattice` owns reusable guide detection, used once to
  read the attributed template's own cells when the paint target is packed.
- `stage_gen.components.sideview_terrain.atlas` owns the paint target, strict
  paintover prompting and admission, fixed-pitch slicing and connector
  harmonization, 47-mask lookup admission, and structural previews.
- `maps/<map_id>.toml` owns the exact top-to-bottom binary occupancy matrix.
- `godot/families/sideview/terrain/atlas.gd` owns eight-neighbor peering,
  atlas-coordinate selection, collision identity, engine import metadata, and
  dynamic-versus-baked behavior for that authored matrix.

No generic component imports side-view terrain semantics. The image model owns
biome material and rendering appearance only. Deterministic code owns topology,
registration, packing, validation, lookup, and composition.

## Provider paintover contract

The provider receives `terrain-atlas-paint-target-v1` as the strict first edit
target, and then map-authorized concept images as appearance references. This
exact ordering is part of the generation contract. The request pins an exact
2880-by-960 canvas: twelve by four cells of 240 pixels, twice the publication
pitch, and exactly the 3:1 maximum the image route accepts. It produces one
opaque repaint:

- the 12-by-4 grid stays where it is, edge to edge, with no margin or frame;
- every cell is filled with terrain to all four of its edges;
- each tile keeps the structure the target has -- which sides are finished
  faces, which are interior cuts, which corners are turned;
- every cell shows one material at one scale, light and brightness, so any
  continuing edge may be joined to any other;
- cap and fill are biome roles rather than hard-coded grass and dirt; and
- cell interiors receive contextual hand-painted edges, corners, bevels, and
  restrained material variation at one scale and light direction.

The image model owns RGB appearance inside the cells. It does not own packing,
lookup, placeholder transparency, or connector admission.

The paint target is the template's 48 cells packed at the provider pitch behind a
three-pixel cyan hairline at every cell boundary, and it is derived from the locked
template rather than committed beside it, so the packed sheet cannot drift from the
template it comes from. The fence is not registration -- the exact canvas settles that,
and the line sits at a known coordinate, so the cut is arithmetic and nothing is detected.
It is there to tell the brush where a tile ends. Published without it, the model paints
the sheet as one canvas: colour right across a boundary differed by 2.78 where half a cell
apart differed by 8.35, and cells whose bottom is exposed sat 2.13 from the cell below,
their undersides being the neighbour's material rather than an underside. Restoring it
took those figures to 43.1 and 82.9. Three pixels, in a colour that cannot be terrain: a
hairline reads as a line to keep, while a sixteen-pixel neutral channel -- the width this
was first tried at -- reads as a gap between objects and the model frames every tile.
Four rounds of a locally drawn block guide -- flat bands standing for which of a
cell's faces meet air -- were measured against it and each invented a literalism
from the legend: a rim darker than the fill came back as a shadow gap between
blocks, a corner mark as a stone cube sitting in the cell, a rim lighter than the
fill as a cream frame around every tile. The template needs no legend because it
already carries all forty-seven finishes; only its art is wrong.

## Local topology and assembly contract

The local topology template is a modified derivative of the official Godot
documentation terrain example and retains CC BY 3.0 attribution in
`docs/terrain-atlas-provenance.md`. It carries:

- 13 straight cyan vertical guides and 5 straight cyan horizontal guides;
- 48 cell interiors arranged as 12 columns by 4 rows;
- one locked terrain silhouette for each of the 47 reachable 3x3-minimal
  peering masks; and
- a checker placeholder at zero-based coordinate `(10, 1)`.

Local code packs that template into the paint target, slices the returned canvas
on fixed cell boundaries four pixels inside the fence, clears the placeholder, and packs
120-by-120
RGBA cells without gutters into the canonical 1440-by-480 runtime atlas. A canvas
that is not exactly 2880-by-960 fails closed.

Fence colour is read strictly in a cell's middle and by cast within nine pixels of its
edge. The strict reading alone published 1,611 tinted pixels into one atlas: saturated
fence over cream terrain lands around (180, 215, 210), a pale teal nothing like the line
it came from and with a red channel far above any threshold that would catch the line
itself. Near an edge the test is the cast rather than the colour -- green and blue both
well above red -- which this palette's foliage, stone, soil and brass never are, while the
strict reading away from an edge leaves a turquoise the direction asked for untouched.

Nothing is blended at the joins. The three-pixel median-profile harmonisation
this replaces was written for a chroma-keyed repaint of one template, where every
cell shared a colour and forcing the outermost pixels onto a common profile was
invisible. On a hand-painted sheet that common profile is a colour no cell
actually has, so it stamped a pale lattice down every join, plainly visible in a
composed map and absent from the same map composed straight from the slice.

Published cells are fully opaque. A 3x3-minimal terrain tile fills its cell: the
forty-seven tiles differ in how their sides and corners are finished, not in
shape, so there is no silhouette to key and no keep-out to preserve. The magenta
convention this replaces predates native alpha and had been destroying the sheet:
the locked template paints rock highlights in a pale pink that satisfies the
chroma key, so every atlas published under it carried 31,701 transparent pixels
-- 4.68 per cent of the forty-seven tiles, up to 19.2 per cent of one of them --
punched through solid ground. The per-cell alpha the old admission compared
against was that damage. It is anti-correlated with exposure, open along tops
that are covered and closed along tops that are exposed, and collapses to six
distinct shapes across forty-seven masks.
The current deterministic assembly identity is
`terrain-atlas-paintover-canonicalization-v8`; any output-affecting compositor
change must advance that identity so cached paintovers cannot mask stale atlases.

The machine-readable lookup in
`stage_gen/resources/terrain/godot_3x3_minimal_lookup_v1.json` is authoritative.
The tracked companion
`fixtures/image_gen_templates/terrain_atlas_godot_topology_reference.md`
explains every atlas coordinate and mask beside the attributed reference image;
its cell table is contract-tested against that lookup.
Mask order is `nw, n, ne, w, center, e, sw, s, se`. The center bit is always
one. A diagonal bit may be one only when both adjacent cardinal bits are one.
There are exactly 47 reachable masks and 47 unique non-placeholder
coordinates; missing, duplicate, unreachable, reserved, or out-of-range
entries invalidate the contract.

## Admission

The provider caller owns one initial attempt plus at most five retries. Every
attempt includes transport, decode, and paintover-source admission. The local
assembly runs after one admitted source and fails closed; it is not a provider
retry. Thresholds are versioned recipe constants and are not retuned to admit
failed media:

| Measurement | Threshold |
| --- | --- |
| Provider canvas | exactly 2880-by-960 |
| Painted material variation | at least 2.0 mean RGB standard-deviation units |
| Worst join tone step | at most 65.0 mean channel values |
| Hillside-tile object share | recorded, not refused |
| Buried-tile object share mean | recorded, not refused |
| Mean join tone step | recorded, not refused |
| Connector mean RGB error | recorded, not refused |
| Published transparent pixels outside the placeholder | exactly 0 |

The join tone step averages the twelve-pixel strip either side of every join the
validation maps can make, and compares those averages. The per-pixel connector
comparison stays in the record but does not decide: on hand-painted material it
is dominated by texture, and while the harmoniser existed it was computed after
that blend had overwritten the pixels it samples, so it read zero on every draw
including the patchy ones. The join threshold
is calibrated on published atlases rather than on a new draw -- the two whose
material a semantic reviewer accepted measure 26.3, the one the reviewer
complained about measures 84.6, and a repeat draw that came back visibly patchy
measures 92.8.

The hillside-tile object share reads the one tile a filled mass is built from -- the
all-neighbours mask -- in ten-pixel blocks, and counts the share of them sitting more than
twelve mean channel values from the tile's own median. That square is stamped at the same
place in every repeat, so anything countable inside it becomes a visible lattice, and the
figure is worth comparing across runs.

It is recorded and never refused. Three attempts to gate it produced two regressions and
no working threshold. At 0.10 it refused the published atlas whose material reads best,
0.194, and the contract came back asking for gravel: the largest feature in a 120-pixel
tile fell to 20 pixels against 52 in the atlas it replaced, and a flat body then shows
every join a busy one hides. At 0.45 it fought the fabric the prompt asks for and
exhausted a node's whole retry budget on a material that draws large slabs. And the
ordering never held: the atlas a reviewer liked scores 0.157 on its largest region, a
hillside visibly chained with repeated boulders scores 0.179, and a sheet that reads well
scores 0.345. Whether a repeat is legible -- a course of slabs reads as a wall, one
boulder reads as a copy -- is an aesthetic judgement, and it belongs to the semantic
review rather than to a statistic.

Topology is not stated in the prompt, and two paid rounds establish why. Asked to hold
it in words instead of taking it from the paint target -- once as a table of all
forty-eight cells, once as sixteen prose runs over an exposure-ordered sheet -- the
model followed the wording closely and drew the wording: grooves where the prompt said
"grid", marks where it said "notched", and sky showing through wherever it read
"exposed underside", because a sheet described in words composes as a picture. Nine and
four of the fifty-two faces that must be finished came back unfinished, against one for
the same material drawn over the target. The prompt owns the art; the target owns the
structure.

Runtime classification is deterministic: `direct_pass` only when every source,
placeholder, and opacity check passes; otherwise `reject`.
There is no generated-atlas repair fallback. Dynamic engine tilemaps require
`direct_pass`.

## Consumer behavior

The generated `map-terrain-v1` occupancy selects one atlas coordinate for every occupied cell
from all eight neighbors. This supports solid ground, genuinely one-cell-high
floating terrain, stair-step shapes, concavities, and holes. Collision comes
from occupancy, not alpha. Runtime import uses exact 120-pixel frames, nearest
sampling, no invented padding, and no dynamic seam repair.

The locked template's exposed top edge begins at the 120-pixel cell boundary, so runtime consumers
register rendered cells directly to binary occupancy without a generated-image measurement or
visual inset.

At finite world boundaries, the prepared runtime repeats one visual-only occupancy column beyond
each horizontal edge and one visual-only row below the map before resolving peering masks. This
moves the atlas's painted side and bottom terminations outside the camera while leaving authored
occupancy, collision, world dimensions, and camera bounds unchanged. The top contour remains
authored terrain because it defines the visible walk surface.

Stair-step terrain is a tile topology, not a smooth geometric slope. True
smooth slopes require separately authored visual tiles plus an explicit
collision contract; this atlas must not synthesize or imply them.

## Evidence and publication state

`scripts/render_terrain_atlas_qa.py` renders deterministic structural evidence
for solid, floating, stair, and concave/hole maps. That proves slicing, lookup,
composition, and admission/rejection boundaries; it does not approve generated appearance.

Provider outputs remain `runtime-unreviewed` until independent semantic review
accepts their material, style, readability, and exact bytes. Structural
validity, generated-media review, and repository publication are separate
states. The exploratory handoff atlases are canaries only and are not fixtures
or runtime assets.

The coordinate arrangement and modified paintover template have documented
Godot documentation lineage. See
[Terrain-atlas provenance](../terrain-atlas-provenance.md).
