# Authored map-generation contract

> **Contract maturity: exact-current authored, generation, manifest, and consumer contract.**
>
> This document is the canonical source of truth for the current authored map
> input. It defines `game-map-v9` as one compound map-generation contract
> for one map, level, or gameplay scene. Prepared-package resolution validates
> the complete source and reference closure before provider work; the scrolling
> recipe executes its typed branches; `prepared-game-runtime-v10` projects the
> exact map closure; and the prepared web adapter consumes that projection.
> This implementation status does not assert that any particular live output
> has passed semantic review or publication gates.

## Authority and purpose

One map produces several visually dependent assets and one exact terrain
composition. Its layers, ground atlas direction, terrain request, climbable roster, and portal
presentation must be authored and reviewed together, so they remain inside one
`maps/<map_id>.toml` source instead of becoming independent entries under
`content/`.

The contract is generation-facing. It owns the visual inputs and composition
needed to produce a map asset bundle. It does not own why or when the game uses
that map.

| Contract | Owns | Does not own |
| --- | --- | --- |
| `game.toml` | Game identity, shared art direction, and package membership | Stage flow or provider execution |
| `gameplay.toml` | Entry map, transition relationships, climb permission, encounters, population, combat, loot, interactions, and map-specific usage | Map image generation or map composition |
| `maps/<map_id>.toml` | Map references, view envelope, visual continuity, ordered layers, ground atlas generation, the terrain request a generator answers, the climbable roster, portal presentation and endpoint anchors, and map-bundle review | Terrain geometry itself, climbable placement, transition destinations, movement permission, spawning, NPC placement, dialogue, soundtrack usage, physics values, or engine scene objects |
| `maps/<map_id>/terrain.json` | Generated `map-terrain-v1` occupancy, walk-surface row, and climbable placements | Any authored intent; it is produced by a run, not written by hand |
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
├── scenarios/
└── references/
```

There is no `maps/index.toml`. `game.toml` catalogs each map source by its
exact package-relative path. `gameplay.toml` references those maps only by
stable `map_id`.

Each `game-map-v9` source carries `game_id`, `map_id`, `revision`, and
`display_name`. `map_id` is lower-kebab-case and matches the TOML filename.
Reference image filenames are independent: there is no requirement for
`<map_id>.png`, one reference per map, or one reference per layer.

## Complete example

```toml
schema_version = 9
kind = "game-map-v9"
game_id = "the-sky-remembers"
map_id = "summer-field"
revision = 1
display_name = "Summer Field"

[view]
profile = "side_view_2d"
gameplay_space = "side_plane"

[camera]
mode = "player_follow"
follow_axes = ["x"]

[continuity]
seamless_axis = "x"
loop_construction = "mirror_repeat"
loop_fallback = "mirror_repeat"

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
vertical_anchor = "canvas_cover"
presentation = { contrast = 1.0, saturation = 1.0, atmosphere_color = "#ffffff", atmosphere_strength = 0.0, detail_blur_screen_pixels = 0.0 }
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
vertical_anchor = "screen_top"
presentation = { contrast = 0.9, saturation = 0.92, atmosphere_color = "#b8e8f4", atmosphere_strength = 0.05, detail_blur_screen_pixels = 0.65 }
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
vertical_anchor = "screen_bottom"
presentation = { contrast = 1.0, saturation = 1.0, atmosphere_color = "#ffffff", atmosphere_strength = 0.0, detail_blur_screen_pixels = 0.0 }
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
vertical_fit = "floor_to_screen_bottom"
walk_surface_row = 8
prompt = """
Create the walkable ground material visible in the references: warm rural soil,
short golden grass along the surface, and darker compacted earth beneath it.
"""

[ladder]
mode = "climbable-atlas-v1"
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

## View, camera, and continuity

`[view]` and `[continuity]` describe the artwork and enter the image cache key. `[camera]`
describes what the runtime does with that artwork and enters no image digest at all, which is why
retuning the camera never re-bills a provider image.

The initial producer supports one complete combination:

| Field | Initial value | Meaning |
| --- | --- | --- |
| `view.profile` | `side_view_2d` | Current side-view asset-generation profile; it is a profile identifier, not a claim that camera pose, projection, and gameplay space are synonyms |
| `view.gameplay_space` | `side_plane` | Composition reserves a readable longitudinal and world-up playfield; it does not grant movement abilities |
| `continuity.seamless_axis` | `x` | Every layer output must be admitted or constructed as a verified horizontal repeat unit |
| `continuity.loop_construction` | `mirror_repeat`, `generated_bridge`, `seam_repaint`, or `fold_repaint` | Map default for how a layer that does not already loop is made to loop |
| `continuity.loop_fallback` | `mirror_repeat` (default) | Construction used when a generative one cannot be completed; validated to be deterministic |
| `layer.loop_construction` | any of the above, or omitted | Optional per-layer override of the map default; omit it to inherit |

### Camera

| Field | Values | Meaning |
| --- | --- | --- |
| `camera.mode` | `player_follow` | The camera tracks the player within a dead zone |
| `camera.follow_axes` | any of `x`, `y`, in that order | Which axes the camera is permitted to follow the player along |

`follow_axes` is the only field a future gameplay shape has to change: a side-scroller declares
`["x"]`, a map whose routes stack above one another `["x", "y"]`, a climbing tower `["y"]`, and a
single-screen arena `[]`. A consumer that cannot honour a declared axis must reject the map rather
than silently ignore the field.

It is a generation input for exactly one reason. A walkable surface the runtime cannot bring into
frame is unplayable, so the terrain designer's framing ceiling is derived from this declaration:
with a vertical axis the whole authored grid is reachable, and without one the reachable world is
only as tall as the viewport less the height of a standing figure. Nothing else about generation
reads it, and it never reaches an image prompt.

This replaces `view.camera_behavior` and `view.scroll_axis`. Those stated a runtime fact inside
the block that directs image generation, so editing the camera re-billed every map image while no
prompt changed; and their art-direction claim — that the composition stays valid as the camera
advances — is carried concretely by `continuity.seamless_axis`, which names the obligation rather
than the camera it follows from.

### Loop construction

Admission runs first on every layer, whichever construction is declared. The image model does
sometimes return a genuinely wrapping plate — Bellweather's two sky layers do — and those are
published untouched at zero provider cost. Construction only applies to a layer that fails
admission.

`mirror_repeat` is the baseline. Appending a horizontal mirror makes every join a reflection, and
a reflection is continuous by definition, so the loop is exact before anything else runs. It cannot
fail and needs no provider. The period doubles and the content reads back on itself, which is the
price of that guarantee.

`generated_bridge` appends one generated span that carries the layer's tail into its own head. The
provider is shown `[ tail context | editable bridge | head context ]` with the bridge masked, and
it paints only the bridge. It costs one image operation per layer that needs it and leaves no
mirrored content; the period grows by the bridge span.

The endpoint treats a mask as a hint rather than a protected region: measured against the
conditioning, the supposedly immutable contexts come back changed by 28 to 48 mean levels on both
OpenRouter and OpenAI. The construction therefore keeps only the bridge span from the return,
discards whatever happened to the contexts, and eases the bridge onto its exact neighbours across
a short anchor band. That is what makes both joins exact regardless of provider drift, and it is
why a naive paste of the contexts is not sufficient.

The provider owns the bridge's alpha as well as its appearance. Reconstructing alpha by
interpolating the two endpoint profiles cannot invent a silhouette, so on a cut-out layer such as
clouds it produces a rectangular blend rather than cloud edges.

Loop construction is excluded from generation cache identity. Switching a map between the two
methods re-runs the loop node only; it never re-bills the layer images, which would come back
byte-identical.

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
| `vertical_anchor` | Required placement vocabulary: `canvas_cover`, `screen_top`, `screen_bottom`, or `walk_surface` |
| `vertical_offset` | Optional author override as a fraction of the layer's own trimmed height, positive pushing down |
| `presentation` | Required consumer-only contrast, saturation, atmospheric wash, and screen-space detail blur |
| `prompt` | Non-empty authored instruction describing what to retain, separate, or reconstruct from the selected references |

The initial scrolling producer accepts one to eight layers. This is a paid-work
safety ceiling, not an aesthetic prescription. The author may omit foreground
layers and may use any supported number of background layers.

Exactly one layer is the opaque full-coverage base. It is a background at
`order = 0` and `parallax = 0.0`. Every other layer is transparent. Background
and foreground roles are explicit and must not be inferred from parallax.

## Vertical placement contract

`plane` is painter order. It is not vertical intent, and conflating the two
leaves a layer with no declared relationship to the ground at all. Vertical
intent is `vertical_anchor`, which names both the edge of the layer that
registers and the datum it registers against:

| `vertical_anchor` | Registers | Against |
| --- | --- | --- |
| `canvas_cover` | Nothing; the layer fills the frame | Reserved for the opaque base |
| `screen_top` | The trimmed raster's top edge | The viewport top |
| `screen_bottom` | The layer's full-coverage line | The viewport bottom |
| `walk_surface` | The layer's full-coverage line | The authored `walk_surface_row` |
| `screen_top` | The layer's *upper* full-coverage line, when it has one | The viewport top |

The two bottom-registered anchors deliberately register the **full-coverage
line** rather than the alpha box's bottom edge. A ragged near-camera silhouette
reaches lower in some columns than others; registering its deepest tip leaves
the gaps between tips uncovered, which is what shows the sky plate through a
foreground frame. The full-coverage line is the lowest row every column still
spans, so registering it is what makes the seal a guarantee.

`screen_top` is the mirror. A canopy hung from the top edge has a ragged upper
edge too: vine tips and leaf points reach above the bar they hang from, and
registering the alpha box's top row puts that sparse fringe against the screen
edge with sky showing through it. The producer lifts the layer so the *first*
row every column spans meets the edge, which resolves to a negative offset. A
top layer with no such row is a fringe rather than a ceiling, and keeps its
alpha-box registration: sky seen through hanging vines is the picture, not a
gap, so it is not refused the way an unsealable `screen_bottom` layer is.

### Measured, not authored

The producer measures four vertical reference frames on every canonical layer
raster and persists them as validation evidence:

| Frame | Definition |
| --- | --- |
| source box | The full raster; this stays the scale datum after trimming |
| alpha box | Bounds of `alpha >= alpha_threshold`; the conventional trim box |
| coverage line | The extreme scanline every column spans at the alpha threshold |
| opaque band | The same "every column" question at the opacity threshold |

Both thresholds are declared parts of the contract. Generated PNGs do not
reliably reach `alpha == 255`, so a literal opacity test finds nothing.

`vertical_offset` therefore exists as an override, not as the normal authoring
path. Omit it and the producer resolves the fraction from the raster it
actually received, because a fraction written before generation is a prediction
about pixels that do not exist yet and goes stale on the next regeneration. An
override that is too small to seal a bottom-registered layer, or too large to
seal a top-registered one, is rejected against the exact measured value rather
than silently leaving a gap. One resolver, `resolve_layer_placement` in the
shared `sideview_layers` component, serves every recipe that places a layer, so
the platformer and the runner cannot drift into two meanings of one anchor.

Each canonical layer is trimmed to its alpha box vertically. Horizontal extent
is never trimmed: a looping layer's width is its repeat period, already owned by
`continuity.seamless_axis`. Trimming never changes apparent size because the
painted frame remains the scale datum.

Placement is applied by exactly one authority. The producer bakes extent — the
vertical trim — and never position; the consumer applies all position from the
resolved manifest values and never re-measures the raster. Measurement is a
fact, not a transform, so there is no double-scaling path.

## Runtime layer presentation

`presentation` is not generation direction. It is a required nested object with
`contrast` from 0.25 to 2, `saturation` from 0 to 2, a six-digit
`atmosphere_color`, `atmosphere_strength` from 0 to 1, and
`detail_blur_screen_pixels` from 0 to 4. Neutral values are `1`, `1`,
`#ffffff`, `0`, and `0`.

Provider-free integration copies these authored values into the prepared
manifest. The web consumer applies them once after decoding the accepted layer
texture. Horizontal blur samples wrap around the admitted repeat period,
vertical samples clamp, and the canonical alpha silhouette remains byte-for-byte
unchanged. The values are screen-space presentation so a parameter adjustment
does not alter the source image, local validation, composite review, or any paid
provider cache key.

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
| `vertical_fit` | Exactly `floor_to_screen_bottom` initially; where the generated grid sits vertically |

### `[terrain]`

Terrain shape is generated the way artwork is generated. The map states which generator to
use and what the level should be; a graph node answers with a `map-terrain-v1` artifact, and
nothing generated is written back into this document.

| Field | Rule |
| --- | --- |
| `mode` | Which generator composes the map. A second dialect is a new mode, never a silent change |
| `brief` | The intent the map designer reads. This is the SHAPE brief, and is deliberately separate from `[ground].prompt`, which directs the material atlas; a map may ask for a village layout painted in winter stone |
| `columns`, `rows` | The grid the generator must fill exactly |
| `walk_surface_row` | The row whose top edge is the main ground plane, and the datum for `walk_surface` anchored layers. Authored rather than derived precisely because painted scenery is pinned to it: a regenerated map must meet the existing art, not move it |

| `prompt` | Non-empty authored description of the desired surface, edge, and fill appearance |

`terrain-atlas-3x3-minimal-v1` names the current stable generation contract. It
generates one opaque cap-and-fill material source, then deterministically
projects that appearance through the packaged 47-mask topology-silhouette
template and authoritative lookup into 120-by-120 RGBA cells. The provider does
not generate topology, alpha, cells, or connectors. Generated map occupancy and
all eight neighbors select runtime cells, and dynamic tilemaps admit only
`direct_pass` connector continuity. See [the terrain-atlas contract](../terrain-atlas.md).

Generated occupancy is gameplay geometry, not an image-model instruction. The
first string is the top row. `1` means occupied terrain and `0` means empty
space. All rows have the same 8-to-512-cell width; height is 2 to 64 rows. At
least one cell in the bottom row is occupied. In the current non-lethal-fall
runtime, every gameplay column must have a bottom-supported escape floor and
adjacent bottom-supported surfaces may differ by at most two tiles: that is the
maximum rise the authored double jump proves recoverable. Three-tile pits and
bottomless gameplay columns fail package validation before generation. Atlas
selection derives from this matrix, while consumer pixel size, physics bodies,
filtering, and camera scale remain outside the authored map.

`vertical_fit` is an enum rather than a coordinate because the walk surface is
already fully determined by `occupancy`; the only open question is where that
grid sits in the frame. `floor_to_screen_bottom` means the deepest authored row
bottoms out at the viewport edge, which makes a gap below the world impossible
by construction instead of merely unlikely. The consumer derives its own
baseline from this declaration; no map declares pixels.

`walk_surface_row` names the occupancy row whose top edge is the main ground
plane, and is the datum for `walk_surface` anchored layers. It must expose a
terrain surface in at least one column. It is an index into authored geometry
rather than a prediction about generated art, so unlike a placement fraction it
remains correct across regeneration.

For a normalized X position, the canonical column is
`floor(normalized_x * width)`. Because positions are strictly between zero and
one, the result is always inside the matrix. A **bottom-supported surface** is
the top cell of an unbroken occupied stack reaching the bottom row. Portal
endpoints and the lower end of every ladder must resolve to such a surface;
they cannot silently land over a hole or floating tile.

Future ground modes belong under the same `[ground]` table. A new field or mode
must not be accepted until its producer, validation, manifest, and consumer
path are implemented; unknown values fail before paid work.

## Climbable contract

`[climbable]` is optional. Its presence means this map generates one atlas of
climbable appearances and places instances of them:

| Field | Contract |
| --- | --- |
| `mode` | Exactly `climbable-atlas-v1` |
| `reference_ids` | Non-empty ordered map references used for visual direction |
| `ladders` | Zero to three ladder variants, each with a stable `variant_id` and its own prompt |
| `ropes` | Zero to three rope variants, same shape |
| `placements` | One to eight instances, each naming a declared `variant_id` |

At least one variant must be declared across the two roles. A variant that is
declared and never placed is rejected: it would be paid generation nobody uses.

The roles are explicit rather than free-form because their geometry differs. A
ladder carries crosswise rungs and a rope is a continuous strand, and their
silhouettes differ by roughly a factor of four. Validation admits each column
against its own aspect envelope, which it can only do because the role is
authored rather than inferred from pixels.

**Atlas order is every ladder left to right, then every rope**, and the cell
index of a variant is its index in that order. That binding is positional: the
producer asks for the roster in order and trusts the order it gets back. What is
verified is that each column holds a silhouette its declared role admits, that
every declared subject survives, and that all variants share one world scale.
Two ladders on the same sheet are not distinguishable to any gate, so a swap
between same-role variants would not be caught. This matches how the dialogue
expression atlas binds its expressions.

Each `[[climbable.placements]]` record has a unique lower-snake-case
`climbable_id`, a `variant_id` naming a declared variant, a unique
`normalized_x`, `bottom_surface = "terrain"`, and `rise_tiles = 4`. The lower
endpoint must resolve to bottom-supported terrain. At that same column,
occupancy must contain an exposed occupied cell exactly four rows above the
lower surface; that cell is the upper deck, and the cell immediately above it
must be empty. This binds every visible climbable to real authored terrain
instead of asking the consumer to invent a platform graph.

### Sizing, and a known limitation

Every variant shares one provider image, sized from the world unit: one tile of
width per column, `rise + 1` tiles of height, converted once at a fixed 4x
supersample of the 64-pixel runtime tile. Six variants therefore always fit a
single sheet, so no map schedules more than one climbable atlas.

Variant count and per-variant resolution compete for the same budget, because
the provider caps one image at 3840 pixels per edge and 8,294,400 pixels in
total. The fixed supersample keeps cost and quality predictable — a map with one
variant and a map with six both get a 256-by-1280 source cell — but the ceiling
it leaves differs: a smaller count could support up to 10x supersample where six
variants top out near 5x. An author who wants maximum fidelity on one signature
ladder should declare fewer variants. The runtime draws a climbable 64 pixels
wide, so the fixed 4x is already four times the final width and the headroom
above it has diminishing value.

The map declares that the climbable exists and where it connects. Whether the
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
- changing only `vertical_anchor` or `vertical_offset` invalidates that layer's local validation, the composite, and the manifest, but never its image call: placement is consumed downstream of generation, so re-anchoring a layer must not re-bill an image that would return byte-identical. `vertical_fit` and `walk_surface_row` are excluded from the ground appearance request for the same reason;
- changing only a layer's `presentation` invalidates provider-free manifest integration and browser presentation only. It does not invalidate layer generation, alpha/repeat admission, the authored review composite, or any provider operation. The consumer applies contrast, saturation, atmospheric color wash, and loop-safe detail blur once after texture decode while preserving the canonical alpha silhouette;
- changing ground appearance direction invalidates the atlas and composite review;
- changing occupancy invalidates package closure, composed terrain evidence, the layer-and-ground composite, gameplay binding, manifest projection, and map review without changing the appearance-only atlas call;
- changing any ladder or portal authored record, including placement, invalidates that presentation branch and the map review; the current graph deliberately binds the complete block to its image call;
- composite identity binds occupancy and the ordered final layer and ground artifacts, while map-review identity additionally waits for and binds every declared ladder or portal validation; and
- every generated artifact records the map source digest, selected reference digests, effective prompt, provider/model identity, validation, and derivation.

Generated provenance contains only portable package-relative references. It
never persists temporary paths, signed URLs, credentials, or an unbound image
discovered from the directory.

## Usage boundary

`game-map-v9` does not contain:

- terrain geometry or climbable placement, both of which are generated into a
  `map-terrain-v1` artifact and bound to the map by digest;
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
`prepared-game-runtime-v10` consumer admission.
