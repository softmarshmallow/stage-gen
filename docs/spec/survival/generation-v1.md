# Oblique-survival generation V1

> **Checked by:** `tests/contract/test_generation_pipeline_docs.py`.

> **Contract maturity: exact-current authored contracts.** Executable
> authority: `src/stage_gen/recipes/oblique_survival/`. The camera vocabulary it
> implements is ratified in the
> [view and style taxonomy](../game/view-and-style-taxonomy.md) and its
> namespace segment in the [asset taxonomy](../asset-taxonomy.md). The
> committed fixture package is `library/games/ember-hollow`. The ground, the
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

Type ids live at `2d/obliqueview/survival/<module>.<step>`. `obliqueview` is a
camera alias bound to the profile above, which is what the
[asset taxonomy](../asset-taxonomy.md) requires of a new camera segment: a
segment's authority is its binding, and an unbound informal label never becomes
one.

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
| `ui.toml` | `game-ui-v5` | optional: the screen-fixed interface — the `panel_frame` and `button_rect` nine-slice sheets and the `preview_icons` grid the host's HUD is dressed in, and the `cursor_set` it is played with, each pointer with the hotspot the gate measured — the shared [authored game UI contract](../game/ui.md), planned through the game_ui component's own triplet; no `inventory_panel`, the host draws its slots as plain wells inside the generated frame |
| `sounds.toml` | — | one clip per thing the player does, with its exact duration and its playback gain |

`publication_authorized` is `false` in every graph this recipe seals and in
every manifest it writes. A package cannot authorize its own publication, and
neither can a run.

**Takes, and why some of them are local.** An adopted take is an auditioned
draw kept inside the package and admitted through the same gate a fresh draw
faces, at zero provider operations — the image, music and sound routes have no
seed, so a brief is a draw rather than a sound. A take is declared two ways: a
bare path, which is read and digested from disk, or the inline table
`take = { path = "...", sha256 = "..." }`, which declares the digest instead.
The declared digest enters the package's digest ledger exactly as the file's
own would, the file is verified against it whenever it is present, and its
absence is allowed and recorded — so the graph plans, prices and keys itself
from the committed text alone, and the adopt node refuses at execution with the
digest it wanted.

That rule is what lets the fixture package obey the
[repository storage policy](../../repository-storage.md): the two reference
images are tracked, and the ground, item, weather, music and sound takes are
first-party draws that stay local and untracked, declared by digest. Planning,
graph identity and the machine-checked contract below need only the digest; a
live run needs the bytes.

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

## The graph

One graph serves every scope. A scope selects a subset of the nodes and changes
nothing about the ones it keeps, so a narrow run warms the cache for a wide one
instead of paying twice.

| Scope | Nodes | Image | Structured | Tool loop | Music | Sound | Local |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `minimal` | 64 | 21 | 0 | 5 | 0 | 0 | 38 |
| `props` | 186 | 74 | 7 | 11 | 0 | 0 | 94 |
| `actors` | 236 | 95 | 12 | 11 | 0 | 0 | 118 |
| **`full`** | **278** | **102** | **13** | **11** | **0** | **3** | **149** |

Counted from the committed fixture package with every plate, track and clip take
adopted; the music count is zero for that reason. The `full` row is the block
below, and both are derived rather than transcribed.

`minimal` draws what a played demo needs on screen: each minimal prop's baseline
state, the state its interaction leaves behind (a chopped tree is a stump, and
without the stump the tree would simply vanish), the items those interactions
yield, and the items the forage sheet lets the player pick up. Everything else
waits for `props`, the interface included: the four `ui.toml` sheets are drawn
from `props` up, because the frame around the screen is part of the rest of
what is on screen and nothing about it bears on the oblique clause `minimal`
exists to prove.

The phases, in dependency order: source lock and the paintover lattice
templates; prop sprites, one image per state, each gated and then given one
tool-loop anchor; items and the inventory icon sheet; the ground as its layers —
biome material plates, the macro colour field, the road plate and the water
plate, each gated and made tileable, then the forage sheet as a lattice
paintover gated cell by cell; decals; the actor concept sheet,
then per-state motion strips per facing, gated, repacked and rebased against a
judging plate; the flame-cycle paintover and the dust sheet; the weather layers;
the season looks, one paintover per prop state; one contact sheet and one
semantic review per family; the interface sheets, the shared game_ui triplet
(generate, pixel gate, review) over the panel frame, the button state sheet, the
preview icon grid and the cursor set, each hanging off the source lock and
wrapped in this package's own style words with the style plate as reference
image 1; the
algorithmic world layout; the manifest.

**One image route, not two.** The engine's binding table declares at most one
route per operation, so a transparent route beside an opaque one would mean two
operation names, two services and two retry owners for one modality. Every image
goes through the OpenAI route — the only one with native alpha — and the ground
plates and the flame strip ask that same route for an opaque background.

**Reviews succeed whether they admit or reject.** A rejection is a recorded
result, not a failure, so the scheduler still reaches the manifest and a run that
is refused is still readable.

## Identity: what re-bills what

A node's cache key hashes its id, its type id, its operation, its route, its
sorted input digests, its dependency keys and its contract version. Two rules
govern what goes where, and both were earned rather than designed:

- **Anything that decides what a node produces is an input digest, not a
  parameter.** The engine does not hash a node's `params`, so a value that
  changes the answer and rides `params` would restore the old answer and report
  a cache hit.
- **A hard acceptance rule belongs to the digest of the tier it refuses.** A
  gate threshold nobody shows the model is still part of the question that node
  is being asked.

| Edit | Effect |
| --- | --- |
| `crafting.toml` — any of it | mixing: reaches the manifest, re-bills nothing |
| an item's `use`, `tool`, `stack_max` | mixing (`display_name` is painted into the icon sheet, so it bills the icons) |
| an interaction's `tool` | mixing |
| `ground.toml [blend]`, `[macro] period_meters`, per-biome display `level` | mixing: the consumer's numbers, read by no node |
| `music.toml [transition]`, a sound cue's `gain` or `pitch_jitter` | mixing: a fade is a cue switch, not a redraw |
| a prop state's prompt, an item's pickup brief, a plate's material clause, a season look's `season_prompt` | identity: the node that reads it redraws |
| the style plate's bytes | identity for every generative image node — each digests the plate's bytes, not just its own prompt, because the prompt does not change when the picture does |
| `ui.toml`, a role's prompt or reference, the package's `[style]` words | identity for that interface sheet's triplet: the role's direction, the reference's digest and the style wrapper's words are its cache inputs, exactly as the game_ui component declares them; the slot count and the HUD's layout are the host's and re-bill nothing |
| a summer prop state | identity for that state **and** its winter twin, which hangs off the summer's gated sprite |
| `world.toml`, any `placement` block, a prop's `canopy_radius_meters` | the layout re-lays (`world-layout`, a local node) and the manifest follows; no provider node moves, and an edit to one object's block moves that object's points and nothing beyond one footprint of them — see [world](world.md) |
| the scope | selects nodes; it never moves the key of a node it keeps |

**The contract-version prefix is frozen.** Every node type's
`contract_version` is built from `CONTRACT_VERSION_PREFIX` in
`src/stage_gen/recipes/oblique_survival/survival_types.py`, and a contract
version is one of the inputs of a cache key. It is deliberately not the recipe
word: renaming it would move every key in the graph and re-bill a run that has
already been paid for. The recipe word, the document kinds and the CLI verb are
`oblique-survival`; the frozen prefix is its own string and stays put.

## Deterministic gates

Every threshold here is refusal-bearing — a gate that only reports is not a
gate, and the two that only report say so. A refusal is retried inside the
node's own single retry owner, within its attempt budget; it is never a nested
loop and never a second provider adapter.

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

A run publishes `oblique-survival-manifest-v2` at `manifest.json`, beside the
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

`scale` is the unit and the floor: `player_height_meters`, the
`minimum_height_units` every thing the player can act on keeps (a prop's
height, a pickup's height, a forage piece's span) in units and in metres, and
— when `[camera] reference_height_px` states the window the rig was tuned in —
`screen_px_per_meter` at play zoom and the floor in screen pixels, so an author
sees what the number means. `ground.forage.cells[]` carry the per-cell
calibration ([ground](ground.md)); there is no other sheet of ground pieces
([decision 0060](../../decisions/0060-the-world-places-nothing-the-player-cannot-act-on.md)).

Three of them carry the rules a consumer must not invent for itself.
`ground_contact` is the authored seam between a billboard and the ground: the
consumer sets its shadow strength from it and never chooses a seam of its own.
`look` states that every asset was drawn under one light, that a ground piece
keeps its lower edge toward the camera with an authored jitter about that aim,
and that nothing is mirrored except an actor's facing. `status` reports one word
per family — `ok`, `partial`, `missing` or `none` — so a run that lost one
family is still playable and says which.

`run` carries the run id, the graph digest, the scope and the package's source
digest. A block published at a version a consumer does not read must be refused
by name rather than skipped.

The manifest is a consumer contract and nothing else: it carries no credentials,
no signed URLs, no absolute paths, and every artifact path in it is a portable
path below the run directory. The host that plays it is
[the Godot host](../../godot-host.md).

## Running it

Offline, no provider, no credentials:

```bash
uv run stage-gen oblique-survival plan --input library/games/ember-hollow --scope full
```

```bash
uv run stage-gen oblique-survival generate --input library/games/ember-hollow \
  --output out/ember-hollow-dry --scope minimal --dry-run --invocation-id dry-1
```

`plan` prints the sealed graph and its projection; adding `--cache-dir` reports
which provider operations that cache would restore, statically and for free,
before any spend. `--dry-run` writes node stubs rather than artifacts: it proves
the graph, not the art.

Live is simply the absence of `--dry-run`. The executor asks for the
capabilities the resolved package actually needs and refuses on missing
credentials before a run directory exists:

```bash
uv run stage-gen oblique-survival generate --input library/games/ember-hollow \
  --output out/ember-hollow-v1 --scope full --cache-dir out/.oblique-survival-cache
```

Budget the widest scope at roughly **USD 4–25** for the committed fixture, from
the planner's own low and high estimates. That is a planning allowance, not a
quote: retries and deliberate semantic regenerations change the charge, and a
semantic regeneration is not a provider retry.

Two commands are provider-free by construction. `import-run` replays a prior
run's artifacts into a cache, key by key, so a run that has already been paid
for is restored rather than redrawn; `finalize` rebuilds one run's manifest from
what it has on disk.

## Machine-checked graph contract

The block below is derived, never transcribed. Regenerate it with
`uv run python scripts/write_pipeline_graph_contract.py --write`; the gate is
`tests/contract/test_generation_pipeline_docs.py`, which also checks the scope
table above against the graphs the code builds. Changing recipe stages, asset
fan-out, dependencies, provider multiplicity, resources, scheduling, retries,
cache identity, trace fields, persisted outputs, or manifest prerequisites
invalidates it and must be regenerated in the same change.

<!-- pipeline-graph-contract:start -->
```json
{
  "kind": "oblique-survival-execution-graph-contract-v1",
  "fixture_ref": "library/games/ember-hollow",
  "scope": "full",
  "graph_schema_version": 1,
  "topology_sha256": "484879b1b2797be51eec8486412d6d1f72f268a7dadbd07693f1ee3230cb54ca",
  "node_count": 278,
  "terminal_node_id": "package-manifest",
  "operation_counts": {
    "local": 149,
    "image_generation": 102,
    "structured_generation": 13,
    "tool_loop": 11,
    "music_generation": 0,
    "sound_effect_generation": 3
  },
  "resources": [
    {
      "resource_id": "local",
      "max_in_flight": null,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "survival-openai-image",
      "max_in_flight": null,
      "requests_per_minute": 150,
      "rate_limit_owner": "provider_adapter"
    },
    {
      "resource_id": "survival-openrouter-structured",
      "max_in_flight": 4,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "survival-openrouter-tool-loop",
      "max_in_flight": 2,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "survival-openrouter-music",
      "max_in_flight": 2,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    },
    {
      "resource_id": "survival-elevenlabs-sound",
      "max_in_flight": 2,
      "requests_per_minute": null,
      "rate_limit_owner": "none"
    }
  ]
}
```
<!-- pipeline-graph-contract:end -->

## Change protocol

Update this document and its embedded contract in the same change whenever
package inputs, node fan-out, dependencies, provider multiplicity, resources,
scheduling, retries, cache identity, trace fields, persisted outputs, or
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
- **The wall clock of a run is one retry chain, not the graph.** The scheduler
  runs wide and the graph is finished long before whichever strip is failing its
  spread gate. The lever is the prompt or the gate, never the scheduler.
- **Set pieces are compositions, not designs.** The camp and the boulder rings
  are members at authored offsets, sited by the generator; nothing composes one.
- **Generated visual output is unreviewed until a non-producer reviews it**, and
  an audio quality claim needs a separately recorded listening verdict. A run's
  own `reviews` block records the graph's semantic reviews; it is not that
  independent verdict.
