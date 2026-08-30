# Side-view platformer terrain atlas

The prepared-game ground contract is `terrain-atlas-3x3-minimal-v1`. It is a
Godot-compatible 3x3-minimal terrain topology carried in a 12-column by 4-row
atlas. It is not a 9-slice and it does not encode true smooth slopes.

## Ownership

- `stage_gen.media.guide_lattice` owns reusable guide detection and cell
  extraction for the attributed topology template and provider paintovers.
- `stage_gen.recipes.sideview_platformer.terrain_atlas` owns strict paintover
  prompting and admission, deterministic chroma-alpha extraction and connector
  harmonization, 47-mask lookup admission, and structural previews.
- `maps/<map_id>.toml` owns the exact top-to-bottom binary occupancy matrix.
- `web/lib/sideview-platformer/terrain-atlas.ts` owns eight-neighbor peering,
  atlas-coordinate selection, collision identity, engine import metadata, and
  dynamic-versus-baked behavior for that authored matrix.

No generic component imports side-view terrain semantics. The image model owns
biome material and rendering appearance only. Deterministic code owns topology,
alpha, packing, validation, lookup, and composition.

## Provider paintover contract

The provider receives the attributed 12-by-4 template as the strict first edit
target, the attributed Godot grid crop as redundant topology-only input, and
then map-authorized concept images as appearance references. This exact ordering
is part of the generation contract. It produces one opaque atlas paintover:

- all 13 vertical and 5 horizontal cyan guides remain regular;
- pure magenta remains outside terrain silhouettes;
- all 48 cells retain their topology role and checker placeholder;
- cap and fill are biome roles rather than hard-coded grass and dirt; and
- cell interiors receive contextual hand-painted edges, corners, bevels, and
  restrained material variation at one scale and light direction.

The image model owns RGB appearance inside the cells. It does not own final
alpha, packing, lookup, placeholder transparency, or connector admission.

## Local topology and assembly contract

The local topology template is a modified derivative of the official Godot
documentation terrain example and retains CC BY 3.0 attribution in
`docs/terrain-atlas-provenance.md`. It carries:

- 13 straight cyan vertical guides and 5 straight cyan horizontal guides;
- 48 cell interiors arranged as 12 columns by 4 rows;
- one locked terrain silhouette for each of the 47 reachable 3x3-minimal
  peering masks; and
- a checker placeholder at zero-based coordinate `(10, 1)`.

Local code detects and extracts both lattices, rejects excessive provider
topology drift, preserves the provider-painted cell interiors, deterministically
derives alpha from the provider-painted magenta chroma, harmonizes three pixels
at legal connector edges, clears the placeholder, and packs 120-by-120 RGBA
cells without gutters into the canonical 1440-by-480 runtime atlas. Missing or
irregular guides fail closed.
The current deterministic assembly identity is
`terrain-atlas-paintover-canonicalization-v3`; any output-affecting compositor
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
| Provider fitted-guide residual | at most 1.5 px |
| Rectifiable guide residual | at most 0.025 of fitted spacing; cells are independently normalized before the unchanged direct-pass checks |
| Provider topology alpha mismatch | at most 0.10 globally |
| Painted material variation | at least 2.0 mean RGB standard-deviation units |
| Paintover/template alpha mismatch | at most 0.10 globally |
| Connector alpha mismatch | at most 0.005 over the central 20% band |
| Direct connector mean RGB error | at most 3.0 channel values |

Runtime classification is deterministic: `direct_pass` only when every source,
template-alpha, placeholder, and direct-connector check passes; otherwise
`reject`. There is no generated-atlas repair fallback. Dynamic engine tilemaps
require `direct_pass`.

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
moves the atlas's transparent side and bottom contours outside the camera while leaving authored
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
