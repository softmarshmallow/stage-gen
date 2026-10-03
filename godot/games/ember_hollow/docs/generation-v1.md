# Oblique-survival generation V1

> **Scope: game consumers.** This document describes the formats used by these Godot games.
> The public asset SDK and new games do not require this authoring format.

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`, `tests/unit/games/oblique_survival/test_workflow.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: the gnode build `godot/games/ember_hollow/pipeline/workflow.py` over
> `godot/games/ember_hollow/pipeline/src/ember_hollow_pipeline/`. The camera vocabulary it
> implements is ratified in the
> [view and style taxonomy](../../_shared/docs/formats/view-and-style-taxonomy.md) and its
> namespace segment in the [asset taxonomy](../../../../docs/spec/asset-taxonomy.md). The
> committed fixture package is `godot/games/ember_hollow/inputs`. The ground, the
> calendar and the crafting table have their own contracts beside this one:
> [ground](ground.md), [world](world.md), [seasons](seasons.md), [crafting](crafting.md).

## What this recipe is

`oblique-survival` builds one survival world seen from a fixed elevated-oblique
perspective camera: 2D billboard cards standing on a 3D ground plane. Nothing in
it is modelled. Every tree, rock, actor, pickup and bolt is a flat drawing that
turns to face the lens; the ground below them is a shader over generated
material plates; the depth relationship between the two is the camera's, not a
layer order. A run publishes the art, the measurements a consumer needs to lay
it down at true scale, and the authored rules of play — foraging, an authored
crafting table, tools that wear, three vitals, a season calendar, weather, music
and sound.

The recipe is judged on whether one place holds together: whether a generated
card and a generated ground read as the same world, at one scale, with a
believable contact where they meet. That is a semantic question and it is
answered by review, not by a gate.

## Presentation profile and namespace

| Axis | Value |
| --- | --- |
| Presentation profile | `elevated_oblique_perspective_ground_plane_v1` |
| Scene dimensionality | `spatial_2_5d` — a relationship between representation and interaction, never a camera |
| Camera pose / projection | `elevated_oblique` / `perspective`, pitched 55° at 18 m, 35° field of view |
| Camera behaviour | `free` in yaw only: 45° detents, authored by `[camera] rotation_allowed` and `yaw_step_degrees` |
| Gameplay space | `ground_plane` |
| Occlusion | `depth_buffer` |
| Asset view | `three_quarter_front`, pictorial pitch `above` (about 30°) |
| Directional coverage | `four_way` for the player; `single_mirrored` for a mob |

`obliqueview` is the camera alias the
[asset taxonomy](../../../../docs/spec/asset-taxonomy.md) binds to the profile above: a
segment's authority is its binding, and an unbound informal label never becomes one. The
build's step types are this project's own, in `pipeline/nodes/`, beside the shared steps
it reuses.

**The scene pitch and the pictorial pitch are deliberately different numbers.**
A screen-aligned billboard is not foreshortened by the camera at all, so the
sprite has to carry its own top-down while the ground carries the real one. The
mismatch shows only at the base, and the contact-shadow ellipse covers it. The
authored `[camera] asset_pitch_degrees` states the pictorial one so a prompt and
a reviewer are asking the same question.

Rotation makes a billboard world cheaper to turn, not more expensive: every prop
is a card that turns with the camera, so no prop is ever seen from behind and no
extra art is drawn. What rotation does cost is a constraint on the art — a prop
drawn with a strong directional light or a cast shadow is wrong from behind — so
the look contract states one light for every asset in the package and forbids
mirroring outside an actor's facing.

## Source package

An authored survival package is a directory holding `survival.toml` and the
siblings it names. It is a package root of its own kind; it is never a member of
a `game.toml` closure.

| File | Kind | What it says |
| --- | --- | --- |
| `survival.toml` | `oblique-survival-package-v2` | the root: `[presentation]`, the `[look]` contract (one light, ground-piece aim, jitter), `[style]` with the style plate, `[scale]` (player height in metres), `[camera]`, `[gameplay]` (hunger, health, warmth, torch, night, mob, campfire), `[rights]` |
| `world.toml` | `oblique-survival-world-v1` | the world: `[world]` (seed, size), `[landmass]`, `[biomes]` (islets), `[spawn]`, `[[set_pieces]]`, `[population]` — see [world](world.md). Where each object stands is that object's own `placement` block in props.toml, actors.toml and ground.toml |
| `actors.toml` | `oblique-survival-actors-v1` | one entry per drawn actor: role, appearance reference, motion states, the facing set, the side view |
| `props.toml` | `oblique-survival-props-v3` | every prop, its states, what can be done to it as `[[props.interactions]]` in priority order (each `from` the states it applies to, with its verb and yield), its sheet or variants, and its per-look season overrides; a scattered prop must offer an interaction |
| `ground.toml` | `oblique-survival-ground-v2` | the biome plates, the macro field, the road, the water, the forage sheet (the one sheet of ground pieces, each cell sized), the decals, and the `[blend]` mixing the consumer reads — see [ground](ground.md) |
| `items.toml` | `oblique-survival-items-v1` | every item, its pickup brief and its use or tool, and the `[icons]` sheet — see [crafting](crafting.md) |
| `crafting.toml` | `oblique-survival-crafting-v2` | the pack, the start, the stations and the recipes; a built prop names the look it is built in and is placed by the player — see [crafting](crafting.md) |
| `seasons.toml` | `oblique-survival-seasons-v1` | the calendar and what each season holds — see [seasons](seasons.md) |
| `weather.toml` | `oblique-survival-weather-v1` | the world conditions and the layers each one drives |
| `music.toml` | — | one instrumental loop per clock cue, and the `[transition]` between them |
| `ui.toml` | `game-ui-v5` | optional: the screen-fixed interface — the `panel_frame` and `button_rect` nine-slice sheets and the `preview_icons` grid the host's HUD is dressed in, and the `cursor_set` it is played with, each pointer with the hotspot the gate measured — the shared [authored game UI contract](../../_shared/docs/formats/ui.md), planned through the game_ui component's own triplet; no `inventory_panel`, the host draws its slots as plain wells inside the generated frame |
| `shell.toml` | `game-shell-v3` | optional: the screens around the game — the opening cinematic's shot list, each shot drawn as a still or filmed as a clip, the title screen's backdrop and text-free emblem, and the loading screen — the shared [authored game shell contract](shell.md), planned through the game_shell component's own triplet. Every string on them is composited by the host in the package's declared typeface, never drawn into a plate |
| `sounds.toml` | — | one clip per thing the player does, with its exact duration and its playback gain |

`publication_authorized` is `false` in every manifest the build writes. A package cannot authorize its own publication, and
neither can a run.

**Takes, and why some of them are local.** An adopted take is an auditioned
draw kept inside the package and admitted through the same gate a fresh draw
faces, at zero provider operations — the image, music and sound routes have no
seed, so a brief is a draw rather than a sound. A take is declared two ways: a
bare path, which is read and digested from disk, or the inline table
`take = { path = "...", sha256 = "..." }`, which declares the digest instead.
The declared digest enters the package's digest ledger exactly as the file's
own would, the file is verified against it whenever it is present, and its
absence is allowed and recorded — so the build plans and prices itself from the
committed text alone, and the adopt step refuses at execution, naming the take
and the digest it wanted.

That rule is what lets the fixture package obey the
[repository storage policy](../../../../docs/repository-storage.md): the two reference
images are tracked, and the ground, item, weather, music and sound takes are
first-party draws that stay local and untracked, declared by digest. Planning
and the machine-checked contract below need only the declaration; a run needs
the bytes.

## Facings

A billboard has no back unless one is drawn, so "which way is this actor
facing" is a question the art has to answer with a separate drawing per answer.

| Set | Drawn | Who |
| --- | --- | --- |
| `four_way` | `front`, `back`, `left`, `right`: one strip per state per facing | the player, always — the loader refuses anything else for a player |
| `single_mirrored` | one turned three-quarter card, mirrored for leftward motion, reused toward and away | actors that need less detail; a mob's default |

A facing is named from the **camera**, never from the world. `front` faces the
viewer; `back` faces away; `left` and `right` face the screen's sides. The
camera turns in detents and the consumer resolves an actor's world heading
against the camera's yaw, so the same four cards serve every detent and nothing
about a facing depends on a world direction.

**Selection.** The heading is split into its screen-right and toward-camera
components. The side facing wins whenever the sideways part is at least as
large as the other, so a perfect diagonal shows the side card, and `front` or
`back` show only when the motion is mostly toward or away from the camera.
Standing still keeps the last facing.

**How the four are drawn.** A four-way actor draws its `front` strip off the
concept sheet alone, then `back`, `left` and `right` off the concept **and the
gated front strip**, matching it pose for pose and cell for cell. Cross-facing
agreement is the unreliable part, and a pose reference is the lever, at the cost
of one strip's depth on the critical path. Strips land at
`package/actors/<id>/states/<state>.<facing>.png`, the rebase keys its groups
`state.facing` against `idle.front`, and the manifest publishes each state's
four specs under `facings` with the front's fields repeated at the top level, so
a consumer that knows one strip per state still reads it.

## The build

The game's folder is a gnode project. `pipeline/workflow.py:build` reads the package with
the game's own reader and writes one group of steps per asset. One build serves every
scope: a scope selects which assets are built and changes nothing about the ones it
keeps, so a narrow build's answers are the wide build's too.

| Scope | Image | Structured | Agent episode | Sound | Music | Video |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `minimal` | 21 | 0 | 5 | 0 | 0 | 0 |
| `props` | 75 | 11 | 11 | 0 | 0 | 0 |
| `actors` | 96 | 16 | 11 | 0 | 0 | 0 |
| **`full`** | **103** | **17** | **11** | **3** | **0** | **0** |

Paid calls at first takes, counted from the committed fixture package with every plate,
track and clip take adopted; the music and video counts are zero for that reason. An
agent episode is one anchor placement, however many turns it takes (at most six). Video
is where adoption matters most: a ten-second clip is a dollar, so the three adopted
opening shots are the difference between 134 billable calls and 137. Drop a shot's
`take` and it goes back to being filmed. The `full` row is the block below, and the
table is checked against the plans the builder makes.

`minimal` draws what a played demo needs on screen: each minimal prop's baseline
state, the state its interaction leaves behind (a chopped tree is a stump, and
without the stump the tree would simply vanish), the items those interactions
yield, and the items the forage sheet lets the player pick up. Everything else
waits for `props`, the interface and the shell included: the `ui.toml` sheets and
the `shell.toml` plates and shots are built from `props` up, because the frame
around the screen is part of the rest of what is on screen and nothing about it
bears on the oblique clause `minimal` exists to prove.

The groups, in dependency order: the paintover lattice templates; the props, one image
per state (or one sheet cut at its emptiest seams into its looks), each gated, finished
and given one agent-placed anchor; the season looks, one paintover per prop state off its
summer sprite; the items and the inventory icon sheet; the ground as its layers — biome
material plates, the macro colour field, the road and the water plates, each gated and
mirrored to tile, the forage sheet as a lattice paintover gated cell by cell, and the
decals; the actor concept sheet, then per-state motion strips per facing, gated,
repacked and rebased against a judging plate; the flame-cycle paintover and the dust
sheet; the music; the weather layers; the sound effects; one contact sheet and one
semantic review per family; the interface sheets (the shared UI sheet steps, wrapped in
this package's own style words with the style plate as a reference); the shell's plates
and shots; the algorithmic world layout; and the package step, which lays every
published file out where the manifest names it and writes `manifest.json`.

**Every painting is judged and drawn again when it fails.** A judge holds each draw to
its family's pixel gate (below); a refusal is a redraw, at most six takes, and the
refused takes stay in the run's records. The publishing step runs the same gate,
finishes the picture (alpha lifted, a plate mirrored, a strip repacked, a sheet cut) and
writes the record the manifest reads. Auditioned takes are adopted through the same
gate instead of drawn.

**Routes are the game's.** `gnode.yaml` binds each kind of call to one route; a step that
needs a feature its route lacks (a transparent background, say) is refused while
planning, before any key is checked, and nothing replaces a failed or uncredentialed
provider automatically. The opening's clips publish through an ffmpeg built with
libtheora, declared as the `ffmpeg-theora` tool (`GNODE_TOOL_FFMPEG_THEORA`).

**Reviews are evidence, never gates.** A family review that rejects is recorded, and the
build goes on; only a review that contradicts itself (a failed check naming no finding)
is asked again.

## Identity: what re-bills what

A step's identity is what it is asked and shown: its type, its inputs by content (pictures
by their bytes) and its parameters, and for a paid call the route. A build reuses every
answer whose question has not changed, so an edit re-bills exactly the steps whose
question it changes.

| Edit | Effect |
| --- | --- |
| `crafting.toml` — any of it | mixing: reaches the manifest, re-bills nothing |
| an item's `use`, `tool`, `stack_max` | mixing (`display_name` is painted into the icon sheet, so it bills the icons) |
| an interaction's `tool` | mixing |
| `ground.toml [blend]`, `[macro] period_meters`, per-biome display `level` | mixing: the consumer's numbers, read by no step that draws |
| `music.toml [transition]`, a sound cue's `gain` or `pitch_jitter` | mixing: a fade is a cue switch, not a redraw |
| a prop state's prompt, an item's pickup brief, a plate's material clause, a season look's `season_prompt` | the step that reads it redraws; an item without an icon brief of its own also redraws the icon sheet, which draws it from its pickup brief |
| the style plate's bytes | every image drawn against it redraws |
| `ui.toml`, a role's prompt or reference, the package's `[style]` words | that interface sheet redraws; the slot count and the HUD's layout are the host's and re-bill nothing |
| `shell.toml`, a plate's prompt or reference, the package's `[style]` words | that plate redraws. Moving a reserved region re-bills the plate that has to keep it quiet; the host's choreography — parallax, easing, dwell — re-bills nothing |
| a summer prop state | that state **and** its winter twin, which is painted over the summer's published sprite |
| `world.toml`, any `placement` block, a prop's `canopy_radius_meters` | the layout re-lays (a local step) and the manifest follows; no paid call moves — see [world](world.md) |
| the scope | selects steps; it never moves the identity of a step it keeps |

## Deterministic gates

Every threshold here is refusal-bearing — a gate that only reports is not a
gate, and the two that only report say so. A refusal is a redraw: the judge sends
the take back, at most six takes, and each provider call keeps its own single
retry owner inside that.

| Gate | Threshold | What it refuses |
| --- | --- | --- |
| border alpha | `BORDER_ALPHA_MAX = 16`, mean `0.5` | a full-bleed picture returned instead of a cutout |
| visible fraction | `VISIBLE_FRACTION_MIN = 0.01` | a subject that wastes its canvas |
| bottom padding | `BOTTOM_PADDING_MIN_PX = 8` | a subject with no clear space under its feet, so the runtime's foot row is the object's own |
| ground contact | `GROUND_CONTACT_MIN = 0.55` | an object standing in the air on its own card |
| floor plate | `FLOOR_PLATE_WIDENING_MIN = 1.6`, fill `0.55` | advisory only: a painted floor plate under the subject, surfaced to the reviewer |
| cell height spread | `0.12` for a cycle state, `0.55` for an action | a re-framed strip cell; height alone cannot tell a bend from a zoom |
| feet line | `CELL_FEET_LINE_SPREAD = 0.06` | the re-framing height cannot see: a pose keeps its feet |
| ground value band | field `(0.30, 0.84)`, fabric `(0.20, 0.84)`, water `(0.14, 0.60)`, cover `(0.55, 0.97)` | a plate too dark to lift without banding, or too pale to be what it is |
| block uniformity | `GROUND_BLOCK_DEVIATION_MAX = 0.12` over `4` blocks | a plate with a bright or dark quarter |
| corner ratio | `(0.90, 1.10)` | a vignette baked into a tiling plate |
| busy-ness at play zoom | field `0.062`, fabric `0.14`, measured at `PLAY_PX_PER_METER = 70` | speckle that reads as noise rather than as ground |
| macro no-ink | `MACRO_EDGE_MEAN_MAX = 0.02`, value `(0.36, 0.68)`, half deviation `0.22` | drawing inside a plate whose whole job is a colour field |
| tile edge | `TILE_EDGE_DELTA_MAX = 6/255` | a visible seam where a plate meets its own repeat |
| cell isolation | pieces `(0.02, 0.60)`, icons `(0.05, 0.75)`, inset `0.03` | a sheet cell that is empty, that overflows, or that touches a guide line |
| sheet seam | searched over `SHEET_SEAM_SEARCH_SHARE = 0.15` either side of each half line | a cut through a drawing: a sheet is cut at its emptiest seam, not on the arithmetic midline |
| decal feather | soft-edge share `0.05`, irregularity `0.12` over `180` radius samples | a hard-edged decal, and a ground patch that is a disc |
| lattice residual | `LATTICE_RESIDUAL_MAX_PX = 3.0` | a paintover that moved the guide grid it was drawn over |
| flame cycle | coverage `(0.05, 0.85)`, consecutive-frame overlap `(0.45, 0.98)`, base drift `0.10` | a jump cut, a duplicated frame, or a flame that jitters vertically |
| look shape | `LOOK_ASPECT_RATIO = (0.72, 1.2)` | a season look that is a different drawing; its scale and its placement are corrected rather than refused |
| sound duration | `SOUND_DURATION_TOLERANCE_SECONDS = 0.5` | a truncated clip, as distinct from frame quantization |

## Runtime manifest

A run publishes `oblique-survival-manifest-v3` at `manifest.json`, beside the
`package/` tree it names. Its blocks:

`style`, `scale`, `camera`, `look`, `ground_contact`, `ground`, `actors`,
`props`, `items`, `icons`, `ui`, `crafting`, `fx`, `music`, `weather`, `sounds`,
`seasons`, `layout`, `gameplay`, `reviews`, `run`, `status`, and
`publication_authorized`.

`ui` is the shared block every consumer of the game_ui component reads — one
`ui.<role>` entry per sheet with the geometry the gate detected (cells, insets,
content and safe rects, band fill, draw scale; for the cursor set, a measured
hotspot per glyph) and the sheet's `asset` — and it is `null` for a package
that authors no `ui.toml`; `status.ui` says `none` then, and `missing` when the
scope drew no sheets. The host dresses every panel and button from it, installs
its pointers from `ui.cursor_set`, and falls back to plain boxes under the
system pointer when it is null.

`status.shell` reads the same way, and a package that authors no `shell.toml` boots straight into the world — which is what every run before the shell landed did.

`scale` is the unit and the floor: `player_height_meters`, the
`minimum_height_units` every thing the player can act on keeps (a prop's
height, a pickup's height, a forage piece's span) in units and in metres, and
— when `[camera] reference_height_px` states the window the rig was tuned in —
`screen_px_per_meter` at play zoom and the floor in screen pixels, so an author
sees what the number means. `ground.forage.cells[]` carry the per-cell
calibration ([ground](ground.md)); there is no other sheet of ground pieces
([decision 0060](../../../../docs/decisions/0060-the-world-places-nothing-the-player-cannot-act-on.md)).

Three of them carry the rules a consumer must not invent for itself.
`ground_contact` is the authored seam between a billboard and the ground: the
consumer sets its shadow strength from it and never chooses a seam of its own.
`look` states that every asset was drawn under one light, that a ground piece
keeps its lower edge toward the camera with an authored jitter about that aim,
and that nothing is mirrored except an actor's facing. `status` reports one word
per family — `ok`, `partial`, `missing` or `none` — so a run that lost one
family is still playable and says which.

`run` carries the package and scope it was built for (as `run_id`), the scope and the
package's source digest; `graph_sha256` is null, since the build's record is the gnode
run's. A block published at a version a consumer does not read must be refused by name
rather than skipped.

The manifest is a consumer contract and nothing else: it carries no credentials,
no signed URLs, no absolute paths, and every artifact path in it is a portable
path below the delivered folder. The host that plays it is
[the Godot host](runtime.md).

## Running it

From `godot/games/ember_hollow`, offline, no provider, no credentials:

```bash
gnode plan pipeline/workflow.py:build --arg package=inputs --arg scope=full
```

A build is the same command run, with `--live` as the explicit provider opt-in and a
spending cap:

```bash
gnode run pipeline/workflow.py:build --arg package=inputs --arg scope=full --live \
  --max-usd 40 --deliver package=../../../out/<tag>/{key}
```

Runs land in `out/runs/` and the call cache in `out/gnode-cache/`, so a second build
pays only for what changed; `--deliver` copies the folder the host plays out of a
successful build. Budget the widest scope at roughly **USD 19–34** at first takes for the
committed fixture, from the planner's own low estimate; the build's ceiling, every take
redrawn, is USD 220. That is a planning allowance, not a quote: redraws and deliberate
semantic regenerations change the charge, and a semantic regeneration is not a provider
retry.

## Machine-checked plan contract

The block below is derived, never transcribed. Regenerate it with
`uv run python godot/tools/write_game_graph_contract.py --write`; the gate is
`tests/contract/test_generation_pipeline_docs.py`, which also checks the scope
table above against the plans the builder makes. A change to the build's steps,
fan-out, dependencies or routes invalidates it and must be regenerated in the
same change.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "oblique-survival-gnode-plan-contract-v1",
  "fixture_ref": "godot/games/ember_hollow/inputs",
  "builder": "pipeline/workflow.py:build",
  "arguments": {
    "scope": "full"
  },
  "workflow_id": "ember-hollow",
  "topology_sha256": "11e85ddd55a719764986770834ea9d23f5d93b98563642c992a3b6392c6b0d61",
  "node_count": 1656,
  "step_count": 466,
  "first_take_operation_counts": {
    "agent.turn": 11,
    "image.edit": 100,
    "image.generate": 3,
    "local": 332,
    "sound.generate": 3,
    "structured.generate": 17
  },
  "outputs": [
    "package"
  ],
  "type_ids": [
    "./pipeline/nodes/actors.py#publish_rebase",
    "./pipeline/nodes/actors.py#rebase_admit",
    "./pipeline/nodes/actors.py#rebase_plate",
    "./pipeline/nodes/actors.py#rebase_record",
    "./pipeline/nodes/actors.py#rebase_schema",
    "./pipeline/nodes/actors.py#rebase_verify_admit",
    "./pipeline/nodes/actors.py#rebase_verify_plate",
    "./pipeline/nodes/actors.py#rebase_verify_record",
    "./pipeline/nodes/audio.py#admit_audio",
    "./pipeline/nodes/audio.py#adopt_audio",
    "./pipeline/nodes/audio.py#publish_audio",
    "./pipeline/nodes/interface.py#admit_ui_sheet",
    "./pipeline/nodes/interface.py#publish_ui_sheet",
    "./pipeline/nodes/interface.py#ui_review_schema",
    "./pipeline/nodes/interface.py#ui_template",
    "./pipeline/nodes/pictures.py#admit_picture",
    "./pipeline/nodes/pictures.py#adopt_picture",
    "./pipeline/nodes/pictures.py#cut_look",
    "./pipeline/nodes/pictures.py#finish_picture",
    "./pipeline/nodes/pictures.py#lattice_template",
    "./pipeline/nodes/pictures.py#lay_sheet",
    "./pipeline/nodes/props.py#place_anchor",
    "./pipeline/nodes/reviews.py#admit_review",
    "./pipeline/nodes/reviews.py#review_record",
    "./pipeline/nodes/reviews.py#review_schema",
    "./pipeline/nodes/reviews.py#review_sheet",
    "./pipeline/nodes/shell.py#admit_shell_plate",
    "./pipeline/nodes/shell.py#admit_shell_review",
    "./pipeline/nodes/shell.py#adopt_clip",
    "./pipeline/nodes/shell.py#clip_record",
    "./pipeline/nodes/shell.py#publish_clip",
    "./pipeline/nodes/shell.py#publish_shell_plate",
    "./pipeline/nodes/shell.py#publish_typeface",
    "./pipeline/nodes/shell.py#shell_review_brief",
    "./pipeline/nodes/shell.py#shell_review_record",
    "./pipeline/nodes/shell.py#shell_review_schema",
    "./pipeline/nodes/world.py#package_manifest",
    "./pipeline/nodes/world.py#world_layout",
    "gnode/image.edit@1",
    "gnode/image.generate@1",
    "gnode/sound.generate@1",
    "gnode/structured.generate@1"
  ]
}
```
<!-- pipeline-graph-contract:end -->

## Change protocol

Update this document and its embedded contract in the same change whenever
package inputs, step fan-out, dependencies, routes, judges, persisted outputs, or
manifest prerequisites change. Run:
`uv run pytest tests/contract/test_generation_pipeline_docs.py` and
`uv run python scripts/check_docs.py`. Live latency, price, quota, and semantic
media acceptance are dated evidence; they must not be silently promoted into
permanent graph truth.

## Known limits

- **A mob has no `back` facing.** `single_mirrored` is the admitted coverage
  for an actor that needs less detail, so walking away from the camera shows a
  turned three-quarter card. Deliberate, and stated here rather than hidden.
- **No provider-side pitch measurement exists.** Nothing in a single flat
  picture recovers the angle it was drawn from, so pictorial-pitch consistency
  is a reviewer's question and no gate can see it.
- **Drift between a look's drawn size and its authored size is recorded, not
  gated.** A floor on that ratio would burn attempts on something the
  calibration already corrects.
- **Prop state swaps are instantaneous.** A tree becomes a stump between
  frames, with a dust puff over the change. That reads acceptably and is not
  animation.
- **Four biomes is the capacity.** A fifth needs a second weight plate and a
  second sampler set in the consumer's shader; the loader refuses it with that
  sentence rather than producing art nobody can blend.
- **The wall clock of a run is one redraw chain, not the build.** The scheduler
  runs wide and the build is finished long before whichever strip is failing its
  spread gate. The lever is the prompt or the gate, never the scheduler.
- **Set pieces are compositions, not designs.** The camp and the boulder rings
  are members at authored offsets, sited by the generator; nothing composes one.
- **Generated visual output is unreviewed until a non-producer reviews it**, and
  an audio quality claim needs a separately recorded listening verdict. A run's
  own `reviews` block records the build's semantic reviews; it is not that
  independent verdict.
