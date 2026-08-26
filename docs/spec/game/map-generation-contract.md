# Authored map-generation contract

> **Contract maturity: exact-current input validation implemented; generation pending.**
>
> This document is the canonical source of truth for the next authored map
> input. It defines `game-map-v3` as one compound visual-generation contract
> for one map, level, or gameplay scene. Prepared-package resolution now
> validates this complete source and reference closure before provider work.
> Layer generation, manifest projection, and consumer binding remain pending.

## Authority and purpose

One map produces several visually dependent assets. Its layers and ground must
be directed, generated, and reviewed as one composition, so they remain inside
one `maps/<map_id>.toml` source instead of becoming independent entries under
`content/`.

The contract is generation-facing. It owns the visual inputs and composition
needed to produce a map asset bundle. It does not own why or when the game uses
that map.

| Contract | Owns | Does not own |
| --- | --- | --- |
| `game.toml` | Game identity, shared art direction, and digest-locked package membership | Stage flow or provider execution |
| `gameplay.toml` | Entry map, transitions, encounters, population, combat, loot, interactions, and map-specific usage | Map image generation |
| `maps/<map_id>.toml` | Map references, view envelope, visual continuity, ordered layers, ground generation, and map-bundle review | Spawning, NPC placement, dialogue, soundtrack usage, collision geometry, or engine scene objects |
| Recipe | Supported modes, deterministic prompt scaffolding, provider calls, validation, repair, and artifact assembly | Authored creative choices absent from the map |
| Consumer | Runtime terrain geometry, camera controller, collision, rendering, and simulation | Missing map direction or inferred layer roles |

“Map” is the persisted term. Product language may call the same authored unit
a level or gameplay scene, but `scene` is not used in the schema because it is
already overloaded by runtime scenes and cutscenes.

## Package location and identity

The target package keeps maps beneath the selected game root:

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

There is no target `maps/index.toml`. `game.toml` catalogs each map source and
locks its exact authored bytes. `gameplay.toml` references those maps only by
stable `map_id`.

Each `game-map-v3` source carries `game_id`, `map_id`, `revision`, and
`display_name`. `map_id` is lower-kebab-case and matches the TOML filename.
Reference image filenames are independent: there is no requirement for
`<map_id>.png`, one reference per map, or one reference per layer.

## Complete target example

```toml
schema_version = 3
kind = "game-map-v3"
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
mode = "tileset-12x4-v1"
reference_ids = ["field_composition", "ground_material"]
prompt = """
Create the walkable ground material visible in the references: warm rural soil,
short golden grass along the surface, and darker compacted earth beneath it.
"""
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
2. Every layer and the ground declare at least one `reference_id`.
3. A reference may be used by one layer, several layers, the ground, or several maps.
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
| `mode` | Exactly `tileset-12x4-v1` initially |
| `reference_ids` | Non-empty ordered references resolved through the map catalog |
| `prompt` | Non-empty authored description of the desired surface, edge, and fill appearance |

`tileset-12x4-v1` names the current stable generation contract: a generated
12-column by 4-row material atlas, the recipe-owned wireframe prior, and the
deterministic semantic role and alpha mask. The recipe and consumer continue to
own heightfield geometry, collision, platform graphs, and runtime terrain
painting.

`tileset-material-synthesis-v1` is an internal, typed recovery after a narrowly
classified full-sheet failure. It is not an authored ground mode and cannot be
selected by the map.

Future ground modes belong under the same `[ground]` table. A new field or mode
must not be accepted until its producer, validation, manifest, and consumer
path are implemented; unknown values fail before paid work.

## Generation and review unit

For a resolved map, layer first attempts and the ground may run concurrently.
Each layer independently completes generation, alpha validation, repeat
admission or repair, and persistence. The map review waits for all required
terminal assets:

```text
resolved map
├── layer generation[*]
│   └── alpha + seam validation/repair[*]
├── ground generation
│   └── tileset topology validation/recovery
└── composite assembly
    └── whole-map semantic review
```

The whole-map review verifies the authored planes and order, reference fidelity,
major-element coverage, omission and duplication, scale and placement, palette
and style coherence, playfield readability, and visible seams. Independent
per-layer validation does not substitute for the composite verdict.

The composed review image is evidence, not a runtime layer and not a substitute
for the individual generated assets.

## Identity, cache, and provenance

The package closure binds the exact map source and every reference byte. Cache
identity remains granular:

- changing shared map view or continuity invalidates every affected map output;
- changing one layer record or one of its references invalidates that layer and the composite review, not unrelated layers;
- changing ground direction invalidates ground and the composite review;
- composite identity binds the ordered final layer and ground artifact digests; and
- every generated artifact records the map source digest, selected reference digests, effective prompt, provider/model identity, validation, and derivation.

Generated provenance contains only portable package-relative references. It
never persists temporary paths, signed URLs, credentials, or an unbound image
discovered from the directory.

## Usage boundary

`game-map-v3` does not contain:

- stage order or entry-map status;
- spawn zones, spawn tables, population targets, or respawn policy;
- mob, NPC, item, or interactive-prop placement;
- combat, loot, dialogue, quest, or transition semantics;
- soundtrack selection or playback policy;
- terrain coordinates, collision bodies, camera tuning, or engine object paths.

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

## Cutover policy

This is a breaking exact-current transition. Implementation must introduce the
new map, package, request, gameplay, and public manifest identities together;
remove the map-book binding rather than preserve aliases; migrate the canonical
repository game; and reject every obsolete or mixed closure.

The package resolver portion of this cutover has landed. Until producer,
manifest, and consumer work lands, the generation graph must continue to label
`game-map-v3` generation as pending rather than implying that successful input
validation produced a map bundle.
