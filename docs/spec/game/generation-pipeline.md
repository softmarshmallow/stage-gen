# Canonical game-generation pipeline

> **Contract maturity: current executable overview.**
>
> This is the canonical human overview of prepared-game generation. The typed package graph is
> the machine authority, and the compact graph contract embedded below is checked against the
> Bellweather fixture. Text-only prompt planning, `WorldSpec`, `VillageSpec`, map books, and the
> former Wave A/Wave B stage barriers are not inputs to this pipeline.

## Authority and source topology

| Boundary | Current authority |
| --- | --- |
| Authored package membership and cross-contract closure | [`game_package.py`](../../../src/stage_gen/orchestration/game_package.py) |
| Asset-level fan-out, dependencies, outputs, cache inputs, and provider routes | [`package_graph.py`](../../../src/stage_gen/recipes/scrolling_preview/package_graph.py) |
| Dependency scheduling, resource gates, result contracts, and trace | [`execution_graph.py`](../../../src/stage_gen/orchestration/execution_graph.py) |
| Scrolling-preview resolve/plan/dispatch composition | [`package_executor.py`](../../../src/stage_gen/recipes/scrolling_preview/package_executor.py) |
| Prepared-package map execution, canonicalization, cache, and review | [`prepared_world.py`](../../../src/stage_gen/recipes/scrolling_preview/prepared_world.py) |
| Prepared-package cast, catalog, UI, soundtrack, binding, and review execution | [`prepared_content.py`](../../../src/stage_gen/recipes/scrolling_preview/prepared_content.py) |
| Leaf provider retries, decoding, validation, and atomic persistence | Provider-neutral components and adapters |
| Runtime artifact binding and atomic publication | [`prepared_manifest.py`](../../../src/stage_gen/recipes/scrolling_preview/prepared_manifest.py) |

The scrolling-preview executor is deliberately thin. It resolves one directory or ZIP, asks the
recipe to construct the graph, and gives that graph to generic orchestration. It does not plan a
game, hide asset fan-outs inside a coarse stage, or implement provider retry loops.

`stage-gen generate` now requires `--input` pointing to a prepared directory or ZIP whose root
contains `game.toml`. There is no bare-prompt fallback. `--checkpoint world` executes only the
map-review targets and their complete dependency closure. `--checkpoint content` independently
executes cast, catalog, UI, soundtrack, and stable-ID binding targets and their dependency closure.
Neither paid bounded checkpoint can assemble a manifest. `--checkpoint integration` is a
provider-free terminal operation over accepted artifact roots. It validates the complete
package-derived runtime closure, applies caller-ordered corrective-run precedence, atomically
publishes one run whose tag is immutable by default, and emits `prepared-game-runtime-v9`. The
`--dry-run` path still exercises the complete graph with deterministic fake operations.

## Current boundary graph

```mermaid
flowchart TD
    PKG["directory or ZIP"] --> PR["package-resolve · local"]

    PR --> ML["map layer raw generate[*]"]
    PR --> MG["map ground 47-mask paintover generate[*]"]
    ML --> MLC["admit loop, else mirror or bridge[*]"]
    MLC --> MLV["repeat validate, vertical trim + placement measure[*]"]
    MG --> MGV["validate paintover + deterministically canonicalize 47-mask atlas[*]"]
    PR --> LG["optional map climbable atlas generate[*]"]
    PR --> PG["optional map portal-pair generate[*]"]
    MLV --> MC["map composite[*]"]
    MGV --> MC
    LG --> LGV["alpha-component repack + climbable validate[*]"]
    PG --> PGV["alpha-component repack + portal-pair validate[*]"]
    MC --> MR["whole-map review[*]"]
    LGV --> MR
    PGV --> MR

    PR --> PC["player concept"]
    PC --> PS["player state generate[*]"]
    PC --> PD["player dialogue art"]
    PS --> PV["alpha-component repack + validate[*]"]
    PD --> PV
    PV --> PCR["player contact sheet + review"]

    PR --> XC["mob / NPC concepts[*]"]
    XC --> XS["mob states / NPC world + dialogue[*]"]
    XS --> XV["alpha-component repack + validate[*]"]
    XV --> XR["per-entity contact sheet + review[*]"]

    PR --> PI["prop + item generate[*]"]
    PI --> PIV["isolation validate[*]"]
    PIV --> PIR["catalog contact sheets + reviews"]

    PR --> UI["inventory panel generate"]
    UI --> UIV["layout + alpha validate"]
    UIV --> UIR["inventory panel review"]

    PR --> ST["soundtrack generate[*]"]
    ST --> STV["audio validate[*]"]
    PR --> GB["gameplay + sequence bindings validate"]

    MR --> MF["manifest-assemble · terminal"]
    PCR --> MF
    XR --> MF
    PIR --> MF
    UIR --> MF
    STV --> MF
    GB --> MF
```

`[*]` means a package-derived fan-out. Each concrete entity, state, layer, ground, prop, item, UI
role, and track is a stable typed node. The terminal manifest depends on every enabled branch; it is never
written after a partial required run.

## Machine-checked graph contract

The embedded contract is intentionally content-insensitive where content does not change
topology. A changed prompt, image byte, or selected model changes node cache keys and
`graph_sha256`, but not `topology_sha256`. Adding a map, entity, state, or dependency changes the
topology and therefore this checked snapshot.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "prepared-game-execution-graph-contract-v1",
  "fixture_ref": "library/games/bellweather",
  "graph_schema_version": 1,
  "topology_sha256": "f04f84d2dc99ed5b124034c14e0c395756f13d2b7362b255156989be91119c7b",
  "node_count": 215,
  "terminal_node_id": "manifest-assemble",
  "operation_counts": {
    "local": 102,
    "image_generation": 92,
    "structured_generation": 18,
    "music_generation": 3
  },
  "resources": [
    {
      "resource_id": "local",
      "max_in_flight": 32,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openai-image",
      "max_in_flight": null,
      "requests_per_minute": 150,
      "rate_limit_owner": "provider_adapter"
    },
    {
      "resource_id": "openrouter-structured",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "openrouter-music",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    }
  ]
}
```
<!-- pipeline-graph-contract:end -->

For this exact digest-locked Bellweather snapshot, the content-sensitive execution-plan identity is
`graph_sha256 = 68a8c2b6b1d12b566e4bdd3abe218fc2da8001aa4721d1a2d31ccf7ab412dae7`.
Unlike the embedded topology contract, that value changes when prompt, reference, model, or other
cache-key input bytes change without adding or removing a node.

Remote provider resources have no scheduler concurrency ceiling. The direct OpenAI adapter owns
the configured 150-IPM request-start pacing for this Tier 4 deployment and intentionally allows
earlier slow requests to remain in flight. Other deployments must set their active project tier;
the value is not a universal model constant.

## Bellweather operation topology

The normal first-pass graph contains 110 provider operations. Provider transport retries and
later semantic regenerations are not counted as new graph nodes; their actual calls must be
reported by the owning node.

| Domain | Concrete expansion | Image | Structured | Music | Local |
| --- | --- | ---: | ---: | ---: | ---: |
| Maps | 2 maps × (4 layers + 1 ground), 4 provider-assisted and 4 local loop passes, 2 map-local portal pairs, 1 map-local climbable atlas, validation, composite, map review | 17 | 2 | 0 | 19 |
| Player | concept, 11 canonical-source states, dialogue, validations, board, review | 13 | 1 | 0 | 13 |
| Mobs | 6 mobs × (concept + 5 states + validations + board + review) | 36 | 6 | 0 | 36 |
| NPCs | 4 NPCs × (concept + front-facing world atlas + dialogue + validations + board + review) | 12 | 4 | 0 | 12 |
| Props | 8 isolated props, validations, one board, one review | 8 | 1 | 0 | 9 |
| Items | 5 isolated items, validations, one board, one review | 5 | 1 | 0 | 6 |
| UI | one inventory panel, deterministic layout/alpha validation, one review | 1 | 1 | 0 | 1 |
| Soundtrack | 3 generated tracks and technical validations | 0 | 0 | 3 | 3 |
| Package / gameplay / manifest | package closure, bindings, terminal assembly | 0 | 0 | 0 | 3 |
| **Total** | **211 nodes** | **91** | **16** | **3** | **101** |

Each state image is one accepted state-strip operation, not one call per animation frame. Actor
motion has one recipe-owned source facing rather than authored left/right coverage. Concept nodes
intentionally precede actor state nodes to anchor identity; unrelated actors, maps, catalogs, and
tracks do not wait for one another.

Actor-content playback is a separate identity boundary from generation sampling. Each authored
motion resolves `hold`, `loop`, `once`, or `gameplay_driven` playback, an ordered subset of
canonical frame indices, and timeline cadence when applicable. The recipe still requests four
source poses and the canonicalizer still publishes four frames. `manifest-assemble` projects both
facts as `source_frame_count` and `playback`; runtime consumers must not infer selection, cadence,
or repetition from actor role or state names.

NPC `world_orientation` is catalog-wide because the current NPC catalog has one shared world
camera treatment. Bellweather sets it to `front`. Each NPC still authors an ordinary `motions`
entry: its `idle` generation requests four front-facing candidates, while `hold` playback selects
canonical frame zero. The front-facing source is not mirrored. This reuses the player/mob playback
vocabulary rather than introducing an NPC-only still-animation taxonomy.

Structured actor review receives that exact playback projection. A `hold` motion is judged for
motion semantics only at its selected canonical frame; unselected generated candidates remain
subject to identity, facing, scale, registration, and alpha checks but are not runtime motion
coverage.

Player `crouch` is the current explicit vocabulary boundary: gameplay authorizes the posture while
player content requests its visual motion. The provider receives four stationary, feet-planted low
crouch phases—not crawl locomotion—and the authored playback consumes all four as a 6 fps loop.
Canonical generation publishes the state like every other player motion. Consumers may retain
crouch mechanics and show a diagnostic fallback when presentation media is incomplete.

The package-resolution edge into each independent domain is a scheduling barrier, not cache
lineage. It proves the entire package was validated before provider work can start, while each node
hashes only the authored bytes and upstream artifacts it actually consumes. Consequently a
playback-only package edit changes package and manifest identity without invalidating image,
structured-review, or music nodes. Content-producing dependencies such as actor concept to motion
generation remain cache-lineage dependencies.

The live World checkpoint is the exact 31-node closure rooted at both map-review nodes: one
package capture, 13 image generations or edits, 15 map-local canonicalization/composition
operations, and two
structured reviews. It cannot schedule any cast, catalog, soundtrack, gameplay-binding, or
manifest node. Each layer, ground, climbable, and portal generation writes a retained `*.raw.png`;
only its dependent validator may write the canonical runtime-facing PNG.

Each ground image operation receives the attributed 12-by-4 topology template as its strict first
edit target, the attributed Godot grid crop as redundant topology-only input, and its map-authorized
visual references as appearance-only inputs. The request asks the
model to paint contextual cap, fill, exposed sides, bevels, corners, and concavities inside all 47
terrain cells while preserving the cyan lattice, magenta empty regions, and checker placeholder.
Cap and fill are biome roles rather than hard-coded grass and dirt. The retry-owning image component
validates the fitted guide lattice, topology drift, painted variation, and direct connector alpha.
Its dependent local node extracts deterministic magenta chroma alpha to
**deterministically assemble 47-mask atlas** cells, harmonizes legal connector
edges, clears the placeholder, validates direct connectors, and emits the canonical
1440-by-480 atlas plus `ground.evidence.png` composed from that map's authored occupancy. The current
local compositor is `terrain-atlas-paintover-canonicalization-v3`. Its identity and the template,
topology-reference, and lookup digests participate in generation and local assembly cache keys;
occupancy changes the local
evidence, composite, review, bindings, and manifest projection without invalidating the
appearance-only paintover call.

Optional map-local climbable and portal branches begin alongside layers and ground. `climbable-atlas-v1`
requests one complete tall native-alpha subject and deterministically repacks it into a canonical
1-by-1 canvas. `portal-pair-1x2-v1` requests exactly two isolated native-alpha structures, entry on
the left and exit on the right, and repacks them into a canonical 1-by-2 canvas. The validators
enforce transparent borders, subject count, functional silhouette or compatible pair scale, and
persist per-asset validation reports. The map review waits for every declared presentation
validator as well as the layer-and-ground composite. Gameplay still owns climb permission and
transition relationships; generation does not infer either from appearance.

The terrain node is the one place a camera declaration reaches generation. `[camera]` is a
runtime block and enters no image digest, but a walkable surface the runtime cannot bring into
frame is unplayable, so `camera.follow_axes` bounds the designer's framing ceiling and is part of
the terrain node's identity. Retuning the camera therefore re-composes geometry and leaves every
appearance call untouched. This is why the camera was moved out of `[view]`: while it lived there
it entered `map_direction`, and a field no prompt reads re-billed every layer, ground, climbable,
and portal image for the map.

Climbable cache identity is split the same way the ground's is. The atlas draws each declared
variant exactly once, so its mode, selected references, and the declared ladders and ropes with
their prompts are generation identity: the variant count is the atlas cell count and the prompts
are the request. `climbable.placements` is placement-only. Where an instance stands cannot change
how the variant is drawn, so moving a climbable changes the local isolation validator, composite,
map review, bindings, and manifest projection without invalidating the appearance-only atlas call.
Placement geometry is still checked on every edit: bottom-supported terrain attachment and the
exposed upper deck exactly `rise_tiles` above it are enforced against the map's authored occupancy
when the package resolves, ahead of any node.

The live Content checkpoint is the exact 174-node closure rooted at every cast/catalog/UI review,
every soundtrack validation, and `gameplay-bindings-validate`: 75 image operations, 14 structured
reviews, three music operations, and 82 local nodes including package capture. It cannot schedule
map or manifest nodes. Twenty-five identity/catalog/UI images are initially independent; each actor's
state and dialogue descendants become ready immediately after that actor's concept succeeds.
Soundtrack generation, gameplay binding, unrelated actors, and unrelated catalogs overlap.

The UI inventory branch consumes root `ui.toml`, its selected package references, and the exact
packaged `inventory_template.png` bytes. Its image request asks for native alpha only outside the
panel and explicitly requires alpha 255 throughout the panel middle and all eight empty slots. The
template alpha already encodes that transparent-exterior/opaque-panel boundary so high-fidelity
image editing does not receive conflicting pixel evidence. The local validator verifies the
1536-by-1024 RGBA canvas, requires alpha 16 or below at the canvas border and across at least 10% of
the canvas, and requires the inset panel core and slot interiors at alpha 250 or above. It then
normalizes only already-transparent pixels to alpha 0 and the core to alpha 255; it does not infer a
silhouette or perform AI background removal. One independent structured review judges style and layout. The
runtime manifest publishes the resolved V1 geometry and alpha policy with the artifact.

Every actor motion-state provider output is retained as a native-alpha 4-column by 1-row
`*.source.png`. Before runtime publication, its local validation node runs
`alpha-component-repack-v1`: threshold native alpha at greater than 16, find 8-connected
components, retain candidates whose area is at least 2% of thresholded visible area (with a
32-pixel floor), select the largest required count, order them by source row and horizontal
centroid, and translate them without rescaling into equal canonical cells with 12-pixel transparent
gutters. The resulting `*.png`, not the provider source, is the runtime artifact.

This deliberately simple default is stronger than equal-XY slicing but is not semantic instance
ownership. It can drop detached weapons, projectiles, magic, debris, or other components below the
selection boundary. When more candidates exist than required, it retains the largest required
count and records a warning; when fewer principal components exist than required, it fails closed.
The validation record binds source/output digests, placements, rejected-component facts, retained
alpha, and this caveat. Smarter component attachment or segmentation is not silently invoked.

Ordinary side-view states contain four right-facing frames; the runtime mirrors that canonical
source for left-facing play. The player climb states are the explicit exception: `climb_ladder` and
`climb_rope` are rear-facing and are not mirrored during climbable traversal. They are also the only
states that leave the shared four-cell 1536x1024 strip, because a climb has two distinct poses and a
four-cell strip spends two of its cells on near-duplicates: each carries two cells on a 2464x3328
canvas, which keeps the same cell aspect while giving the figure roughly eleven times the painted
area. Which of the two a map requires is decided by the climbable roles it places, not by the
`climb` movement alone, so a package that places a rope while declaring only `climb_ladder` is
rejected rather than silently drawn as a ladder climb. They are also the only states that register
against the top of their cell rather than the bottom: a climber hangs from its hands, so the grip is
what stays put while the feet rise to meet it. That is authored as `anchor` on the motion rather
than decided by the recipe, because unlike facing it depends on what the model actually drew. Facing is therefore a recipe/runtime projection contract, not
authored game-content input, and `content/player.toml` has no `required_facings` field. Generating
both directions is intentionally forbidden by the canonical path because it adds cross-row
consistency work without a runtime consumer. Separately authored directions may become an explicit
future opt-in for asymmetric handedness, but are not accepted silently.

Dialogue provider atlases use a deterministic row-major 2-by-2 or 3-by-N requested layout derived
from the authored expression count. Their local validation nodes apply the same alpha-component
repacker with centered placement and permit only the declared leading cells; unused canonical cells
remain transparent. Local validators persist dimensions, source and canonical digests, component
selection, cell placement, source facing where applicable, runtime-mirroring policy,
state/expression stable IDs, and alpha facts; they never use AI background removal. Prop and item
nodes produce one isolated native-alpha asset per stable ID. Contact sheets consume repacked
atlases and remain deterministic review artifacts, not runtime atlases.

## Scheduling semantics

The generic executor repeatedly starts every node whose declared prerequisites succeeded:

- ready siblings run concurrently; only local work uses a resource semaphore;
- a node never starts before all prerequisites finish successfully;
- one failure marks only its descendants `skipped`;
- unrelated running or ready siblings are not cancelled;
- the scheduler calls a node handler once and never retries provider work;
- provider components remain the sole retry owners, with at most six attempts;
- provider adapters retain their request-start pacing; and
- full-run success requires `manifest-assemble` to succeed; a bounded checkpoint succeeds only
  when every explicit target succeeds.

The resource-aware Bellweather projection uses planning assumptions of 120 seconds per image,
30 seconds per structured review, and 180 seconds per music operation. With the Tier 4
adapter-owned 150 image starts per minute, the projected terminal offset is **297.25 seconds
(4m 57.25s)**. This is a scheduling estimate, not a live latency claim.

The graph carries a broad **USD 4.02–21.88 budgetary allowance**: USD 0.04–0.20 per image,
USD 0.005–0.08 per structured operation, and USD 0.10–0.80 per music operation. These are
conservative planning inputs, not a canonical provider price sheet. Current provider pricing and
returned usage remain operational evidence and must be refreshed at the live-provider gate.

## Cache identity and retry ownership

Every node cache key includes its stable ID and operation contract version, selected provider and
model, digests of validated authored inputs and references, and ordered prerequisite cache keys.
Consumer-only presentation is an explicit exception at the paid boundary: root contact-shadow
settings and per-layer contrast, saturation, atmospheric wash, and detail blur are excluded from
generation, local layer admission, map composite, and semantic-review cache identities. They enter
only package resolution and provider-free `manifest-assemble`, so tuning the accepted runtime look
cannot schedule or invalidate a provider call.
Cache admission additionally validates actual upstream artifact digests as lineage. Path
existence alone is never a hit. A changed model, prompt, reference byte, dependency contract, or
upstream artifact invalidates the relevant reuse boundary.

Prop contact measurement is a local validation and publication boundary, not an image-generation
operation. The prop PNG remains unchanged. The validator thresholds native alpha, rejects tiny
detached fragments, retains meaningful components, and publishes the lowest meaningful contact as
`ground_contact_y_normalized`. The runtime uses that explicit coordinate as its vertical origin;
it does not align the transparent canvas edge or infer contact independently.

`attempts` in a trace belongs to the component-owned provider operation. The scheduler does not
wrap it in another retry loop. A semantic regeneration is a new provider operation and must
increase `provider_operations`; it is not disguised as a transport retry. The base projection
counts one successful provider operation per provider node.

## Persisted execution evidence

| File | Contract |
| --- | --- |
| `package.json` | Captured package identity, stable IDs, and root digests |
| `execution-plan.json` | Nodes, dependencies, resources, outputs, cache keys, models, and estimates |
| `execution-projection.json` | Resource spans, critical path, call counts, time, and budget range |
| `execution-trace.jsonl` | Immutable run/node events with queue, duration, cache, attempts, calls, and errors |
| `execution-summary.json` | Terminal status and per-node result projection |
| `maps/*/layers/*.raw.png` | Retained provider layer output and provider provenance |
| `maps/*/layers/*.png` | Deterministically canonicalized horizontal repeat unit |
| `maps/*/layers/*.repeat.png` | Three-repeat checkerboard evidence for visual review |
| `maps/*/ground.raw.png` | Retained provider-generated 47-mask ground paintover and provider provenance |
| `maps/*/ground.png` | Canonical 1440-by-480 47-mask terrain atlas with 120-by-120 RGBA cells |
| `maps/*/ground.evidence.png` | Deterministic composition of the canonical atlas through the map-authored occupancy |
| `maps/*/climbable.raw.png`, `climbable.png`, `climbable.validation.json` | Optional map-local climbable atlas source, canonical isolated 1-by-N presentation, and deterministic per-variant cell facts |
| `maps/*/portal.raw.png`, `portal.png`, `portal.validation.json` | Optional map-local portal source, canonical isolated 1-by-2 pair, and deterministic facts |
| `maps/*/composite.png`, `review.json` | Whole-map composition and structured semantic verdict |
| `content/{players,mobs,npcs}/*/concept.png` | Canonical generated actor identity and provider provenance |
| `content/{players,mobs}/*/states/*.source.png` | Retained native-alpha provider motion source and provider provenance |
| `content/{players,mobs}/*/states/*.png`, `*.validation.json` | Alpha-component-repacked 4-by-1 runtime strip plus selection, placement, loss, and lineage facts |
| `content/{players,npcs}/*/dialogue.source.png` | Retained native-alpha provider dialogue source and provider provenance |
| `content/{players,npcs}/*/dialogue.png`, `dialogue.validation.json` | Row-major alpha-component-repacked authored-expression atlas plus deterministic report |
| `content/{players,mobs,npcs}/*/contact-sheet.png`, `review.json` | Deterministic actor board and independent structured verdict |
| `content/{props,items}/*.png` | One native-alpha isolated asset per stable ID |
| `content/props/*.validation.json` | Deterministic alpha-component ground contact for each prop; tiny detached and low-alpha contamination is excluded |
| `content/{props,items}/contact-sheet.png`, `review.json` | Deterministic catalog board and independent structured verdict |
| `ui/inventory_panel.png` | Canonical inventory panel with validated layout and alpha contract |
| `content/coverage-matrix.json`, `gameplay.bindings.json` | Required authored coverage and verified stable-ID relationships |
| `soundtrack/*.mp3`, `*.validation.json` | Generated audio, provider provenance, duration/container facts, and explicit listening status |
| `dry-run/*.json` | Fake artifacts used to validate content and lineage cache behavior |
| `manifest.json` | Portable `prepared-game-runtime-v9` authored projection, runtime-only layer/contact-shadow presentation, prop ground contacts, front-facing NPC playback, and SHA-bound runtime closure |

Trace records contain portable artifact references, hashes, and sanitized errors. They do not
contain credentials, authorization headers, signed URLs, temporary paths, or absolute inputs.

```bash
uv run stage-gen package plan --input library/games/bellweather
uv run stage-gen generate \
  --input library/games/bellweather \
  --dry-run \
  --output /tmp/bellweather-dry-run

uv run stage-gen generate \
  --input library/games/bellweather \
  --checkpoint world \
  --output /tmp/bellweather-world

uv run stage-gen generate \
  --input library/games/bellweather \
  --checkpoint content \
  --output /tmp/bellweather-content

uv run stage-gen generate \
  --input library/games/bellweather \
  --checkpoint integration \
  --artifact-root /tmp/bellweather-actor-correction \
  --artifact-root /tmp/bellweather-content \
  --artifact-root /tmp/bellweather-world \
  --output out/bellweather-prepared-v1
```

`--failure-node <node_id>` injects a deterministic dry-run failure. Reusing `--cache-dir` proves
content-and-lineage validated warm-cache behavior. Package planning and dry-run do not call a
provider. `--checkpoint world` requires direct OpenAI image and OpenRouter structured
capabilities. `--checkpoint content` additionally requires OpenRouter music generation and local
`ffprobe` technical inspection. Listening acceptance remains a separate human verdict and is
never inferred from a valid audio container. `--checkpoint integration` performs no provider
operations and requires no provider credential; it fails before publication when any expected
runtime artifact is absent or unsafe.

A published run tag names exactly one byte set, because prose, reviews, and research cite runs by
digest. Integration is deterministic, so republishing an identical closure over an existing output
directory is a no-op reported as `disposition: unchanged` rather than a conflict. Publishing
*different* bytes under a tag that already exists changes what every citation of it means, so it
requires `--replace-output`; the report then carries `disposition: replaced` and the
`replaced_manifest_sha256` that was destroyed. Replacement retires the previous run to a sibling
temporary directory only after the new run is fully assembled, and restores it if the install
fails, so a tag never resolves to a partial run.

## Change protocol

Update this document and its embedded contract in the same change whenever package inputs, node
fan-out, dependencies, provider multiplicity, resources, scheduling, retries, cache identity,
trace fields, persisted outputs, or manifest prerequisites change. Run:

```bash
uv run pytest tests/contract/test_generation_pipeline_docs.py
uv run python scripts/check_docs.py
```

Live latency, price, quota, and semantic media acceptance are dated evidence. They must not be
silently promoted into permanent graph truth.
