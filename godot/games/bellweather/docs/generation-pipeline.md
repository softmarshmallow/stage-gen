# Canonical game-generation pipeline

> **Scope: game consumers.** This document describes the formats used by these Godot games.
> The public asset SDK and new games do not require this authoring format.

> **Checked by:** `tests/contract/test_current_game_docs.py`, `tests/contract/test_generation_pipeline_docs.py`,
> `tests/unit/games/sideview_platformer/test_workflow.py`.

> **Contract maturity: current executable overview.**
>
> This is the canonical human overview of Bellweather's asset build, the side-view platformer
> (`2d/sideview/platformer` in the [asset taxonomy](../../../../docs/spec/asset-taxonomy.md)).
> The [runner](../../iron_petal_unit/docs/runner.md) builds the same way, from its own game
> folder. The [dialogue-scene](../../the_grain/docs/dialogue-scene-assets.md),
> [point-and-click room](../../the_grain/docs/pointclick-room.md) and
> [oblique-survival](../../ember_hollow/docs/generation-v1.md) recipes still declare their own
> graph documents. [Universe](../../../../src/stage_gen/workflows/universe/contract.md) is not a
> game at all: it builds a storyworld package to read rather than one to play.

The game's folder is a gnode project. `gnode.yaml` names the routes, the node folder and the
packages whose source counts as the nodes' source; `gnode.lock` pins every node type to that
source. The builder, [`pipeline/workflow.py`](../pipeline/workflow.py), reads the game's own TOML
package with the game's reader, unchanged, and writes one group of steps per asset. The node
types live in [`pipeline/nodes/`](../pipeline/nodes): the game's own (maps, content, ground
evidence, bindings, the package) beside the shared step families it hosts
(`demo_game_tools.steps`: layers, the 47-mask atlas, painted terrain, rebase, soundtrack, the
interface sheets and the inventory panel). Every brief a model is sent is written in
[`briefs.py`](../pipeline/src/bellweather_pipeline/briefs.py) and every pixel gate,
canonicalization and review board in [`assets.py`](../pipeline/src/bellweather_pipeline/assets.py).

## Building the assets

Plan from the game's folder; a plan never spends:

```bash
cd godot/games/bellweather
uv run gnode plan pipeline/workflow.py:build --arg package=inputs/default
```

A live build needs the owner's go and a ceiling. It runs every step, draws again what a judge
refuses, and delivers the runtime folder the Godot host plays:

```bash
uv run gnode run pipeline/workflow.py:build --arg package=inputs/default --live --max-usd 175 --deliver package=../../../out/bellweather/{key}
godot --path godot/games/bellweather -- --run out/bellweather
```

`--arg part=world` (or `content` or `soundtrack`) builds that part alone and outputs its files
instead of the package; the next whole build answers it from the cache, so a part is how an edit
is paid for in proportion to the edit. `--arg reviews=no` leaves the reviews out: each one is a
structured judgement of a board of what was made, kept as evidence, and nothing downstream reads
its verdict. `inputs/waves` is the second package; it plans the same steps over its own content.

## The steps

| Group | Per entity | Judged by |
| --- | --- | --- |
| `maps.<map>.terrain` | the brief composed as a chunk sentence (structured), the game's validator, the compiled `map-terrain-v1` geometry | `check`: the map's own rules; a refused composition is composed again, at most 3 times, told what the validator said |
| `maps.<map>.layers.<layer>` | the layer painted from the map's references, its loop (a seam repaint for a repaint construction, falling back to the deterministic one), the trimmed and placed unit | `admit`: the canvas and alpha the host's floors require |
| `maps.<map>.ground` | the 47-mask atlas painted over the packed template and assembled, and its evidence through the generated occupancy; or, for painted terrain, one painting per segment of the occupancy, stitched | the sheet must slice on its fixed cells, or a segment must keep its guide's silhouette |
| `maps.<map>.portal`, `.climbable` | the sheet, repacked one subject per cell | a clean border and exactly the declared subjects, each with the silhouette its role admits |
| `maps.<map>` | the board (every layer and the ground where the runtime places them, folded into strips) and its review | — |
| `actors.<kind>_<id>` | the identity concept; a strip per state (an NPC's single world strip), repacked; the dialogue atlas; the player's two rebase readings; the board and its review | a clean cut-out; every required cell drawn; the reading covers every state and holds idle at 1 |
| `props`, `items`, `projectiles` | one cut-out per stable ID, the family's board and review | a clean cut-out; a projectile is also exactly one connected subject |
| `interface` | the inventory panel and each UI sheet role, painted over their templates, normalized, reviewed | the panel's alpha boundary, each role's family gate |
| `soundtrack.<track>` | the track, its measurement | a playable MP3 |
| `bindings`, `package` | every gameplay and scenario reference resolved; the runtime folder and `manifest.json` | — |

Every painting and every track is drawn at most six times: its judge refuses, the next take is
drawn. A refusal is a new provider operation, counted as a take, never a transport retry; the
provider adapter stays the one retry owner inside each take.

## Machine-checked plan contract

The contract below is derived from the plan the builder makes of the default package by
[`write_game_graph_contract.py`](../../../tools/write_game_graph_contract.py). Its topology is
every planned step instance, later takes included, and what each one reads; a changed prompt or
picture moves step identities but not the topology. Adding a map, entity, state or dependency
moves it.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "sideview-platformer-gnode-plan-contract-v1",
  "fixture_ref": "godot/games/bellweather/inputs/default",
  "builder": "pipeline/workflow.py:build",
  "workflow_id": "bellweather",
  "topology_sha256": "b4fc7adf1648a3eb23bcb21d4dc55f7818be5aae7531afc830f977db50b23a61",
  "node_count": 1329,
  "step_count": 351,
  "first_take_operation_counts": {
    "image.edit": 100,
    "local": 224,
    "music.generate": 3,
    "structured.generate": 24
  },
  "outputs": [
    "package"
  ],
  "type_ids": [
    "./pipeline/nodes/content.py#admit_cutout",
    "./pipeline/nodes/content.py#admit_frames",
    "./pipeline/nodes/content.py#admit_projectile",
    "./pipeline/nodes/content.py#contact_sheet",
    "./pipeline/nodes/content.py#publish_dialogue",
    "./pipeline/nodes/content.py#publish_strip",
    "./pipeline/nodes/content.py#review_schema",
    "./pipeline/nodes/ground.py#admit_atlas",
    "./pipeline/nodes/ground.py#assemble_atlas",
    "./pipeline/nodes/ground.py#atlas_paint_target",
    "./pipeline/nodes/ground.py#ground_evidence",
    "./pipeline/nodes/interface.py#admit_inventory",
    "./pipeline/nodes/interface.py#admit_ui_sheet",
    "./pipeline/nodes/interface.py#inventory_review_schema",
    "./pipeline/nodes/interface.py#inventory_template",
    "./pipeline/nodes/interface.py#publish_inventory",
    "./pipeline/nodes/interface.py#publish_ui_sheet",
    "./pipeline/nodes/interface.py#ui_review_schema",
    "./pipeline/nodes/interface.py#ui_template",
    "./pipeline/nodes/layers.py#admit_layer",
    "./pipeline/nodes/layers.py#publish_layer",
    "./pipeline/nodes/layers.py#repaint_loop_layer",
    "./pipeline/nodes/maps.py#admit_presentation",
    "./pipeline/nodes/maps.py#check_terrain",
    "./pipeline/nodes/maps.py#composite",
    "./pipeline/nodes/maps.py#map_review_schema",
    "./pipeline/nodes/maps.py#publish_presentation",
    "./pipeline/nodes/maps.py#terrain",
    "./pipeline/nodes/maps.py#terrain_schema",
    "./pipeline/nodes/package.py#assemble_package",
    "./pipeline/nodes/package.py#bindings",
    "./pipeline/nodes/rebase.py#rebase_admit",
    "./pipeline/nodes/rebase.py#rebase_plate",
    "./pipeline/nodes/rebase.py#rebase_record",
    "./pipeline/nodes/rebase.py#rebase_schema",
    "./pipeline/nodes/rebase.py#rebase_verify_admit",
    "./pipeline/nodes/rebase.py#rebase_verify_plate",
    "./pipeline/nodes/rebase.py#rebase_verify_record",
    "./pipeline/nodes/soundtrack.py#admit_track",
    "./pipeline/nodes/soundtrack.py#record_track",
    "gnode/image.edit@1",
    "gnode/music.generate@1",
    "gnode/structured.generate@1"
  ]
}
```
<!-- pipeline-graph-contract:end -->

## Bellweather operation topology

The first takes of the default package's plan make 127 provider calls: 100 image edits (92
paintings and a seam repaint for each of the 8 layers, which a layer that already loops skips),
24 structured calls and 3 tracks. Later takes are not counted here; they are drawn only when a
judge refuses.

| Domain | Concrete expansion | Image | Structured | Music | Local |
| --- | --- | ---: | ---: | ---: | ---: |
| Maps | 2 maps × (terrain composition, 4 layers and their seam repaints, the atlas), 2 portal pairs, 1 climbable sheet, judges, boards, reviews | 21 | 4 | 0 | 40 |
| Player | concept, 11 states, dialogue, two rebase readings, board, review | 13 | 3 | 0 | 34 |
| Mobs | 6 mobs × (concept + 5 states + board + review) | 36 | 6 | 0 | 78 |
| NPCs | 4 NPCs × (concept + front-facing world strip + dialogue + board + review) | 12 | 4 | 0 | 28 |
| Props | 8 cut-outs, one board, one review | 8 | 1 | 0 | 10 |
| Items | 5 cut-outs, one board, one review | 5 | 1 | 0 | 7 |
| Projectiles | 1 single-subject cut-out, one board, one review; absent for a package with no projectile catalog | 1 | 1 | 0 | 3 |
| Interface | the inventory panel and three sheet roles (`panel_frame`, `button_rect`, `preview_icons`), templates, gates, reviews | 4 | 4 | 0 | 16 |
| Soundtrack | 3 tracks, judged and measured | 0 | 0 | 3 | 6 |
| Package | bindings, the runtime folder | 0 | 0 | 0 | 2 |
| **Total** | **351 steps** | **100** | **24** | **3** | **224** |

## Cache identity

A step's identity is its settings, the digests of the files it reads and the identities of the
steps it reads from; a paid call is keyed by its exact request on its route. Nothing a provider
cannot draw reaches a paid step: a layer's placement, display scale and runtime presentation, an
actor's magnitude and playback, a projectile's flight and impact, and the map's generated terrain
are read by local steps only, so retuning any of them re-runs those steps and bills nothing. The
terrain is composed from the map's brief alone, so reshaping a level never repaints its art, and
a changed loop construction or fallback re-runs that layer's loop and nothing before it. The
builder test holds each of these.

## Per-block versions

`manifest.json` is a set of named blocks, and its root carries a `blocks` table: block key to
the block's own version, `platformer-<key>-block-v1` today for every block the consumer parses
(`presentation`, `scale`, `maps`, `player`, `mobs`, `npcs`, `props`, `items`, `projectiles`,
`ui`, `soundtrack`, `gameplay`, `scenarios`, `closure`), plus two a package authors or leaves
out - `score` and `timers`, absent from the table and the document when not authored, so the
runtime's `score` and `timers` families seal quiet. A block whose shape moves bumps its own
version in `PLATFORMER_MANIFEST_BLOCKS` and in the parser that reads it; nothing else moves. The
document's `kind` moves on structural change only - the set of blocks or the root fields - which
is contract rule C-R3 in [game-contract.md](../../_shared/docs/game-contract.md). The consumer gates every
block it parses and its refusal names the block. The current table is generated into
[contract-identities.md](../../../../docs/contract-identities.md). The root once carried `style`, `proportion`,
`universe` and `canonical_game_sha256`; no consumer read them, and under C-R6 they left in
v12 rather than gain a version.

## Runtime closure roles

Every artifact in `manifest.json`'s closure declares what it is published for. The role is chosen
at the publication site in [`prepared_manifest.py`](../pipeline/src/bellweather_pipeline/prepared_manifest.py)
and stated once, beside the path, in `runtime_artifact_closure`.

| Role | Meaning | Members |
| --- | --- | --- |
| `asset` | Media this package publishes as its own content. Bound by name somewhere in the manifest, and a consumer enumerating what the game is made of must account for all of them. | Map layers, ground atlas, optional climbable and portal sheets, actor concepts, motion atlases, dialogue atlases, props, items, projectiles, inventory panel, nine-slice atlas roles, soundtrack tracks |
| `provenance` | Records and judged plates the run ships so it can be re-derived and audited. Their readable values are already inlined in the manifest, so nothing fetches them to present the game. | `maps/*/layers/*.validation.json`, `maps/*/climbable.validation.json`, `maps/*/terrain.json`, `content/players/*/motion-rebase*.json`, `content/players/*/motion-rebase*-plate.png`, `ui/*.validation.json` |

Nothing observable separates the two, which is why the role is declared rather than inferred: a
judged comparison plate is a PNG under `content/` exactly like the artwork it was composed from,
and a measured placement record is JSON exactly like generated terrain geometry.

The package step enforces the partition before it writes anything: every `asset` must be bound by the
manifest, and every manifest binding must be published as an `asset`. Adding an artifact to the
closure therefore means choosing its role, and a consumer never has to guess. Consumers validate
the vocabulary and may present, list, or ignore an artifact by role, but must not classify by
filename, directory, or media type.

The package step lays out exactly the closure `runtime_artifact_paths` names, refusing a
missing or extra file, and `assemble_prepared_runtime` writes `manifest.json`
(`prepared-game-runtime-v12`) over it; the delivered folder is what `verify_prepared_runtime`
accepts.

## Change protocol

Update this document and its embedded contract in the same change whenever package inputs, step
fan-out, dependencies, provider multiplicity, judges, cache identity, persisted outputs or
manifest prerequisites change. Run:

```bash
uv run python godot/tools/write_game_graph_contract.py --write
uv run pytest tests/contract/test_generation_pipeline_docs.py tests/unit/games/sideview_platformer/test_workflow.py
uv run python scripts/check_docs.py
```

Live latency, price, quota, and semantic media acceptance are dated evidence. They must not be
silently promoted into permanent graph truth.
