# Scrolling-preview terrain atlas

The prepared-game ground contract is `terrain-atlas-3x3-minimal-v1`. It is a
Godot-compatible 3x3-minimal terrain topology carried in a 12-column by 4-row
atlas. It is not a 9-slice and it does not encode true smooth slopes.

## Ownership

- `stage_gen.media.guide_lattice` owns reusable guide detection and cell
  extraction for the repository-owned topology template. Provider output is
  never treated as a guide lattice.
- `stage_gen.recipes.scrolling_preview.terrain_atlas` owns material-board
  prompting and admission, periodic material sampling, deterministic 12-by-4
  topology assembly, 47-mask lookup admission, connector checks, and
  structural previews.
- `maps/<map_id>.toml` owns the exact top-to-bottom binary occupancy matrix.
- `web/lib/runtime/terrain-atlas.ts` owns eight-neighbor peering,
  atlas-coordinate selection, collision identity, engine import metadata, and
  dynamic-versus-baked behavior for that authored matrix.

No generic component imports side-view terrain semantics. The image model owns
biome material and rendering appearance only. Deterministic code owns topology,
alpha, packing, validation, lookup, and composition.

## Provider material-source contract

The provider receives only the map-authorized visual references and ground
prompt. It produces one opaque 2048-by-1152 appearance board:

- the upper 30 percent is one broad, uninterrupted grass-cap or surface band;
- the lower 70 percent is one matching dirt-fill or structural-fill region;
- both regions use one world scale and light direction; and
- the board contains no atlas, grid, guides, cells, connector shapes,
  transparent background, sky, horizon, scenery, props, or text.

The image model never owns cell topology, alpha silhouettes, packing, or
connectors. The packaged topology template is never uploaded to the provider.

## Local topology and assembly contract

The local topology-silhouette template is an original, brand-neutral raster
built by `scripts/build_terrain_atlas_template.py`. It carries:

- 13 straight cyan vertical guides and 5 straight cyan horizontal guides;
- 48 cell interiors arranged as 12 columns by 4 rows;
- one locked terrain silhouette for each of the 47 reachable 3x3-minimal
  peering masks; and
- a checker placeholder at zero-based coordinate `(10, 1)`.

Local code detects and extracts the template lattice, mirror-periodically
samples the admitted cap and fill regions, applies the exact template alpha to
all 47 terrain cells, clears the placeholder, and packs 120-by-120 RGBA cells
without gutters into the canonical 1440-by-480 runtime atlas. Missing or
irregular local guides fail closed. Because provider pixels never define alpha,
the assembled atlas must have zero exact-template alpha mismatch.
The current deterministic assembly identity is
`terrain-atlas-material-assembly-v2`; any output-affecting compositor change
must advance that identity so cached material sources cannot mask stale atlases.

The machine-readable lookup in
`stage_gen/resources/terrain/godot_3x3_minimal_lookup_v1.json` is authoritative.
Mask order is `nw, n, ne, w, center, e, sw, s, se`. The center bit is always
one. A diagonal bit may be one only when both adjacent cardinal bits are one.
There are exactly 47 reachable masks and 47 unique non-placeholder
coordinates; missing, duplicate, unreachable, reserved, or out-of-range
entries invalidate the contract.

## Admission

The provider caller owns one initial attempt plus at most five retries. Every
attempt includes transport, decode, and material-source admission. The local
assembly runs after one admitted source and fails closed; it is not a provider
retry. Thresholds are versioned recipe constants and are not retuned to admit
failed media:

| Measurement | Threshold |
| --- | --- |
| Provider source dimensions | at least 512 px on both axes |
| Provider alpha | fully opaque, extrema exactly 255/255 |
| Mean material variation | at least 2.0 RGB standard-deviation units per region |
| Cap/fill mean RGB distance | at least 8.0 |
| Local fitted-template-guide residual | at most 1.5 px |
| Exact template-alpha mismatch | exactly 0 |
| Connector alpha mismatch | at most 0.005 over the central 20% band |
| Direct connector mean RGB error | at most 3.0 channel values |

Runtime classification is deterministic: `direct_pass` only when every source,
template-alpha, placeholder, and direct-connector check passes; otherwise
`reject`. There is no generated-atlas repair fallback. Dynamic engine tilemaps
require `direct_pass`.

## Consumer behavior

Required `ground.occupancy` in `game-map-v4` selects one atlas coordinate for every occupied cell
from all eight neighbors. This supports solid ground, genuinely one-cell-high
floating terrain, stair-step shapes, concavities, and holes. Collision comes
from occupancy, not alpha. Runtime import uses exact 120-pixel frames, nearest
sampling, no invented padding, and no dynamic seam repair.

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

The coordinate arrangement has a documented Godot documentation lineage; the
repository template itself is original and does not copy the documentation
image pixels. See [Terrain-atlas provenance](../terrain-atlas-provenance.md).

## Legacy scrolling-demo mode

The older tag-based scrolling demo still contains `tileset-12x4-v1`, its
16-role/three-variant mask, material-synthesis recovery, and continuous-strip
browser treatment. It is a separate legacy recipe path. Prepared
`game-map-v4` packages do not select it, and it must not be interpreted as the
47-mask contract above.

That legacy browser consumer does not register or render per-role atlas frames.
It derives a 512 x 512 toroidal material from a luminance-sorted color palette,
uses 3/7/19/43 harmonic families, paints connected-run fill TileSprites, and
adds runtime-only 12-pixel side bands. Those phrases describe the retained
legacy implementation and are intentionally not requirements of the dynamic
47-mask adapter.
