# Authored map-generation contract

> **Contract maturity: exact-current authored, generation, manifest, and consumer contract.**
>
> This document is the canonical source of truth for the current authored map
> input. It defines `game-map-v4` as one compound map-generation contract
> for one map, level, or gameplay scene. Prepared-package resolution validates
> the complete source and reference closure before provider work; the scrolling
> recipe executes its typed branches; `prepared-game-runtime-v5` projects the
> exact map closure; and the prepared web adapter consumes that projection.
> This implementation status does not assert that any particular live output
> has passed semantic review or publication gates.

## Authority and purpose

One map produces several visually dependent assets and one exact terrain
composition. Its layers, ground atlas direction, occupancy, ladder, and portal
presentation must be authored and reviewed together, so they remain inside one
`maps/<map_id>.toml` source instead of becoming independent entries under
`content/`.

The contract is generation-facing. It owns the visual inputs and composition
needed to produce a map asset bundle. It does not own why or when the game uses
that map.

| Contract | Owns | Does not own |
| --- | --- | --- |
| `game.toml` | Game identity, shared art direction, and digest-locked package membership | Stage flow or provider execution |
| `gameplay.toml` | Entry map, transition relationships, climb permission, encounters, population, combat, loot, interactions, and map-specific usage | Map image generation or map composition |
| `maps/<map_id>.toml` | Map references, view envelope, visual continuity, ordered layers, binary terrain occupancy, ground generation, ladder geometry and placement, portal presentation and endpoint anchors, and map-bundle review | Transition destinations, movement permission, spawning, NPC placement, dialogue, soundtrack usage, physics values, or engine scene objects |
| Recipe | Supported modes, deterministic prompt scaffolding, provider calls, validation, repair, and artifact assembly | Authored creative choices absent from the map |
| Consumer | Coordinate projection, collision bodies, camera controller, rendering, input, and simulation | Missing occupancy, ladder/portal placement, transition relationships, or inferred layer roles |

“Map” is the persisted term. Product language may call the same authored unit
a level or gameplay scene, but `scene` is not used in the schema because it is
already overloaded by runtime scenes and cutscenes.

## Package location and identity

The current package keeps maps beneath the selected game root:

```text
library/games/<game_id>/
├── game.toml
├── gameplay.toml
├── soundtrack.toml
├── maps/
│   ├── <map_id>.toml
│   └── ...
├── content/
├── sequences/
└── references/
```

There is no `maps/index.toml`. `game.toml` catalogs each map source and
locks its exact authored bytes. `gameplay.toml` references those maps only by
stable `map_id`.

Each `game-map-v4` source carries `game_id`, `map_id`, `revision`, and
`display_name`. `map_id` is lower-kebab-case and matches the TOML filename.
Reference image filenames are independent: there is no requirement for
`<map_id>.png`, one reference per map, or one reference per layer.

## Complete example

```toml
schema_version = 4
kind = "game-map-v4"
game_id = "the-sky-remembers"
map_id = "summer-field"
revision = 1
display_name = "Summer Field"

[view]
profile = "side_view_2d"
gameplay_space = "side_plane"
camera_behavior = "scrolling"
scroll_axis = "x"

[continuity]
seamless_axis = "x"

[[references]]
reference_id = "field_composition"
source = "references/field-composition.png"
source_sha256 = "<sha256>"
rights_status = "unreviewed"
rights_basis = ["User-supplied original map concept selected for this package."]

[[references]]
reference_id = "cloud_detail"
source = "references/cloud-study.webp"
source_sha256 = "<sha256>"
rights_status = "unreviewed"
rights_basis = ["User-supplied original cloud study selected for this package."]

[[references]]
reference_id = "ground_material"
source = "references/field-ground.jpg"
source_sha256 = "<sha256>"
rights_status = "unreviewed"
rights_basis = ["User-supplied original ground-material study selected for this package."]

[[layers]]
layer_id = "sky_base"
reference_ids = ["field_composition"]
plane = "background"
order = 0
parallax = 0.0
alpha_mode = "opaque"
prompt = """
Reconstruct the uninterrupted blue-sky plate behind the other elements.
Remove the sun, cloud masses, terrain, buildings, and vegetation while
completing newly exposed sky consistently with the reference.
"""

[[layers]]
layer_id = "sunlit_clouds"
reference_ids = ["field_composition", "cloud_detail"]
plane = "background"
order = 1
parallax = 0.15
alpha_mode = "transparent"
prompt = """
Separate the sunlit cloud masses from the references. Preserve their placement,
scale, palette, and pixel-art treatment. Exclude terrain, buildings, vegetation,
and foreground objects.
"""

[[layers]]
layer_id = "near_plants"
reference_ids = ["field_composition"]
plane = "foreground"
order = 0
parallax = 1.4
alpha_mode = "transparent"
prompt = """
Separate only the close grass and flowers that frame the lower edge. Preserve
their relationship to the playfield and omit sky, clouds, town, and distant
terrain.
"""

[ground]
mode = "terrain-atlas-3x3-minimal-v1"
reference_ids = ["field_composition", "ground_material"]
occupancy = [
  "0000000000000000",
  "0000000000000000",
  "0000000000000000",
  "0000000000000000",
  "0000000111100000",
  "0000000000000000",
  "0000000000000000",
  "0000000000000000",
  "1111111111111111",
  "1111111111111111",
]
prompt = """
Create the walkable ground material visible in the references: warm rural soil,
short golden grass along the surface, and darker compacted earth beneath it.
"""

[ladder]
mode = "ladder-4-tile-v1"
reference_ids = ["field_composition"]
prompt = """
Create one sturdy, front-facing field ladder from sun-warmed wood and simple
rope bindings, without characters, scenery, text, or loose items.
"""

[[ladder.placements]]
ladder_id = "field_ladder"
normalized_x = 0.5
bottom_surface = "terrain"
rise_tiles = 4

[portal]
mode = "portal-pair-1x2-v1"
reference_ids = ["field_composition"]
prompt = """
Create a matched pair of field-stone portal arches. Keep the entry calm and
cool and the exit warmer and more luminous, without text or unrelated scenery.
"""

[[portal.endpoints]]
anchor = "west_gate"
normalized_x = 0.1
role = "entry"

[[portal.endpoints]]
anchor = "east_gate"
normalized_x = 0.9
role = "exit"
```

## View and continuity

The initial producer supports one complete combination:

| Field | Initial value | Meaning |
| --- | --- | --- |
| `view.profile` | `side_view_2d` | Current side-view asset-generation profile; it is a profile identifier, not a claim that camera pose, projection, and gameplay space are synonyms |
| `view.gameplay_space` | `side_plane` | Composition reserves a readable longitudinal and world-up playfield; it does not grant movement abilities |
| `view.camera_behavior` | `scrolling` | The generated composition must remain valid while the camera advances |
| `view.scroll_axis` | `x` | Camera progression is horizontal in the generated image plane |
| `continuity.seamless_axis` | `x` | Every layer output must be admitted or repaired as a verified horizontal repeat unit |

`seamless_axis` describes visual continuity. It never means that the player,
simulation, or logical map wraps at an edge. Jumping, ladders, air movement,
and other traversal abilities remain gameplay policy.

The ground does not reuse the layer repeat contract. Its selected generation
mode owns tile joins, material periodicity, topology, and runtime compatibility.

## Reference closure

The human or authoring agent is responsible for selecting the image references
before ingest. The standard prepared-package path never invents, chooses, or
silently discovers a map reference.

Rules:

1. A map declares one or more `[[references]]` records.
2. Every layer, the ground, and each declared ladder or portal bundle declare at least one `reference_id`.
3. A reference may be used by one layer, several layers, ground, ladder, portal, or several maps.
4. A layer may bind several ordered references. Order is semantic and participates in generation identity.
5. Sources are confined package-relative paths to decoded PNG, JPEG, or WebP images.
6. Every source must exist, be a regular non-symlink file, match `source_sha256`, decode successfully, and have a documented rights basis before any provider operation begins.
7. Unknown and unreferenced image files have no effect on generation.
8. Editing a reference file without updating its digest makes the package invalid; it never produces an implicit new run.

These are manually prepared inputs. Their content digest, inline origin/rights
basis, and digest-bound semantic review are the evidence contract. They do not
need adjacent `.meta.json`, `.source.meta.json`, or `.LICENSE.md` files. Those
sidecars belong only to pipeline-generated outputs whose artifact contracts use
them.

The reference set may contain one overall composition image, separate images
for every layer, material studies, or any combination the author finds useful.
There is no mandatory master map image and no filename pairing convention.

## Layer contract

Each `[[layers]]` record owns one generated visual layer:

| Field | Contract |
| --- | --- |
| `layer_id` | Unique lower-snake-case identity within the map |
| `reference_ids` | Non-empty ordered references resolved through the map catalog |
| `plane` | `background` or `foreground`; the playfield is inserted between the two planes |
| `order` | Contiguous zero-based order inside its plane |
| `parallax` | Finite nonnegative camera-relative motion coefficient; motion never determines painter order |
| `alpha_mode` | `opaque` or `transparent`; transparent layers request native alpha from a capable image route |
| `prompt` | Non-empty authored instruction describing what to retain, separate, or reconstruct from the selected references |

The initial scrolling producer accepts one to eight layers. This is a paid-work
safety ceiling, not an aesthetic prescription. The author may omit foreground
layers and may use any supported number of background layers.

Exactly one layer is the opaque full-coverage base. It is a background at
`order = 0` and `parallax = 0.0`. Every other layer is transparent. Background
and foreground roles are explicit and must not be inferred from parallax.

`prompt` is portable creative direction, not the final provider prompt. The
recipe adds versioned mechanical clauses for output dimensions, alpha,
isolation, loop continuity, contamination avoidance, and provider capability.
Those clauses are not copied into every authored map.

## Ground contract

`[ground]` is required for the initial scrolling producer:

| Field | Contract |
| --- | --- |
| `mode` | Exactly `terrain-atlas-3x3-minimal-v1` initially |
| `reference_ids` | Non-empty ordered references resolved through the map catalog |
| `occupancy` | Required top-to-bottom rectangular rows containing only `0` and `1`; row length is the map width in cells |
| `prompt` | Non-empty authored description of the desired surface, edge, and fill appearance |

`terrain-atlas-3x3-minimal-v1` names the current stable generation contract. It
generates one opaque cap-and-fill material source, then deterministically
projects that appearance through the packaged 47-mask topology-silhouette
template and authoritative lookup into 120-by-120 RGBA cells. The provider does
not generate topology, alpha, cells, or connectors. Binary map occupancy and
all eight neighbors select runtime cells, and dynamic tilemaps admit only
`direct_pass` connector continuity. See [the terrain-atlas contract](../tileset.md).

`occupancy` is authored gameplay geometry, not an image-model instruction. The
first string is the top row. `1` means occupied terrain and `0` means empty
space. All rows have the same 8-to-512-cell width; height is 2 to 64 rows. At
least one cell in the bottom row is occupied. In the current non-lethal-fall
runtime, every gameplay column must have a bottom-supported escape floor and
adjacent bottom-supported surfaces may differ by at most two tiles: that is the
maximum rise the authored double jump proves recoverable. Three-tile pits and
bottomless gameplay columns fail package validation before generation. Atlas
selection derives from this matrix, while consumer pixel size, physics bodies,
filtering, and camera scale remain outside the authored map.

For a normalized X position, the canonical column is
`floor(normalized_x * width)`. Because positions are strictly between zero and
one, the result is always inside the matrix. A **bottom-supported surface** is
the top cell of an unbroken occupied stack reaching the bottom row. Portal
endpoints and the lower end of every ladder must resolve to such a surface;
they cannot silently land over a hole or floating tile.

Future ground modes belong under the same `[ground]` table. A new field or mode
must not be accepted until its producer, validation, manifest, and consumer
path are implemented; unknown values fail before paid work.

## Ladder contract

`[ladder]` is optional. Its presence means this map generates one reusable
ladder appearance and places one or more climbable instances:

| Field | Contract |
| --- | --- |
| `mode` | Exactly `ladder-4-tile-v1` |
| `reference_ids` | Non-empty ordered map references used for visual direction |
| `prompt` | Non-empty authored appearance direction; recipe clauses own canvas, isolation, alpha, and fitting |
| `placements` | One to eight stable ladder instances |

Each `[[ladder.placements]]` record has a unique lower-snake-case `ladder_id`,
a unique `normalized_x`, `bottom_surface = "terrain"`, and `rise_tiles = 4`.
The lower endpoint must resolve to bottom-supported terrain. At that same
column, occupancy must contain an exposed occupied cell exactly four rows above
the lower surface; that cell is the upper deck. The cell immediately above the
deck must be empty. This binds the visible ladder to real authored terrain
instead of asking the consumer to invent a platform graph.

The map declares that the ladder exists and where it connects. Whether the
player may climb remains `gameplay.toml` navigation policy. The player content
contract owns climb-motion coverage. The consumer owns activation tolerances,
collision bodies, input, velocity, and pixel projection.

## Portal contract

`[portal]` is optional. `mode = "portal-pair-1x2-v1"` generates one matched,
transparent 1-by-2 pair for the map: entry in the left cell and exit in the
right. `reference_ids` and `prompt` provide map-local visual direction. The
recipe owns exact canvas, cell geometry, alpha, isolation, and validation.

One or two `[[portal.endpoints]]` records place that presentation:

| Field | Contract |
| --- | --- |
| `anchor` | Unique lower-snake-case identity referenced by gameplay transitions and destination spawns |
| `normalized_x` | Unique horizontal placement; must resolve to bottom-supported terrain |
| `role` | Unique `entry` or `exit`; selects the corresponding generated cell and does not define a destination |

The map owns each endpoint's anchor, placement, and visual role. Root
`gameplay.toml` alone connects a source `(map_id, from_anchor)` to another map
and spawn, grants interaction semantics, and controls stage flow. The consumer
owns contact geometry, activation input, prompts, shimmer, and travel execution.

## Generation and review unit

For a resolved map, layer, ground, ladder, and portal first attempts may run
concurrently when their authored blocks exist. Each branch independently
completes its own deterministic validation and persistence. Occupancy is local
contract data and performs no provider call. The map review waits for all
required terminal assets:

```text
resolved map
├── layer generation[*]
│   └── alpha + seam validation/repair[*]
├── ground generation
│   └── terrain-atlas topology validation + occupancy evidence
├── optional ladder generation
│   └── alpha + silhouette validation
├── optional portal-pair generation
│   └── alpha + two-cell validation
└── layer + occupancy-ground composite assembly

{composite, optional ladder validation, optional portal validation}
└── whole-map semantic review
```

The whole-map review verifies the authored planes and order, reference fidelity,
major-element coverage, omission and duplication, occupancy agreement, ladder
and portal grounding, scale and placement, palette and style coherence,
playfield readability, and visible seams. Independent branch validation does
not substitute for the composite verdict.

The composed review image is evidence, not a runtime layer and not a substitute
for the individual generated assets.

## Identity, cache, and provenance

The package closure binds the exact map source and every reference byte. Cache
identity remains granular:

- changing shared map view or continuity invalidates every affected map output;
- changing one layer record or one of its references invalidates that layer and the composite review, not unrelated layers;
- changing ground appearance direction invalidates the atlas and composite review;
- changing occupancy invalidates package closure, composed terrain evidence, the layer-and-ground composite, gameplay binding, manifest projection, and map review without changing the appearance-only atlas call;
- changing any ladder or portal authored record, including placement, invalidates that presentation branch and the map review; the current graph deliberately binds the complete block to its image call;
- composite identity binds occupancy and the ordered final layer and ground artifacts, while map-review identity additionally waits for and binds every declared ladder or portal validation; and
- every generated artifact records the map source digest, selected reference digests, effective prompt, provider/model identity, validation, and derivation.

Generated provenance contains only portable package-relative references. It
never persists temporary paths, signed URLs, credentials, or an unbound image
discovered from the directory.

## Usage boundary

`game-map-v4` does not contain:

- stage order or entry-map status;
- spawn zones, spawn tables, population targets, or respawn policy;
- mob, NPC, item, or interactive-prop placement;
- combat, loot, dialogue, quest, transition relationships, or climb permission;
- soundtrack selection or playback policy;
- consumer pixels, collision bodies, activation tolerances, camera tuning, or engine object paths.

`game.toml` declares that the map belongs to the package. `gameplay.toml`
declares how the game uses the map. This keeps the same visual map reusable in
different gameplay flow without regenerating it.

## Prepared and prompt-only entry paths

The prepared directory or ZIP package is the primary ingest contract. It must
already contain valid map TOMLs and all referenced images.

The optional prompt-only demonstration is a separate bootstrap path. It may
synthesize a candidate package, including reference images and map contracts,
before invoking standard ingest. Standard ingest itself never falls back to a
prompt, invents missing references, or asks a central world-design operation to
choose the authored layer plan.

## Current-only cutover

This was a breaking exact-current transition. The map, package, gameplay, graph,
manifest, and prepared-consumer identities moved together; the prepared path has
no map-book translation or compatibility alias. Obsolete or mixed prepared
closures fail closed.

Successful input validation proves only authored closure. A playable build still
requires successful provider and local graph execution, the required independent
semantic reviews, provider-free integration of every runtime artifact, and exact
`prepared-game-runtime-v5` consumer admission.
