# Repository directory preview

This is the implemented ownership layout for the asset-pipeline product and its
consumers. It shows directories at the level where responsibility changes. It is
not a proposed universal taxonomy, and it does not imply that every capability
already has an end-to-end generation example.

## The whole repository

```text
stage-gen/
├── src/
│   ├── gnode/                         # Execution SDK: no Stage Gen or game imports
│   └── stage_gen/                     # SDK, components, workflows, CLI
├── library/                           # Committed, approved character-3d examples
├── web/                               # One Bun workspace: ui/, viewer/ and site/
├── godot/
│   ├── packages/                      # Reusable, bounded runtime SDKs
│   ├── templates/                     # Copyable application starting points
│   ├── games/                         # Named games and their private shared support
│   └── tools/                         # Godot workspace/package operations
├── apps/
│   └── concept_studio/                # Optional concept-authoring Python application
├── concept-studio/                    # Existing concept docs, gallery and local drafts
├── scripts/                           # Product/repository maintenance and verification
├── tests/                             # Tests selected by product or consumer ownership
├── docs/                              # Cross-cutting guides, SDK, policy, specs and history
├── .agents/skills/                    # Asset authoring and consumer-specific workflows
├── .github/workflows/                # Separate product and consumer gates
├── pyproject.toml                     # Core distribution and local workspace metadata
└── uv.lock                            # Repository development workspace lock
```

`library/characters/` holds the committed, approved character-3d examples (Nami, Riko
and Helix), which the catalog builds from their tracked files. The game inputs belong
to their individual Godot games; each workflow's sample inputs belong to its folder.
Users supply external input, output and cache directories rather than registering
projects inside this checkout.

`concept-studio/` remains the existing concept-content workspace, with its ignored
drafts and curated media rights records. Its executable application is separately
packaged under `apps/`; the core distribution does not require either workspace.

## Product implementation

```text
src/
├── gnode/
│   ├── contracts/                     # Public execution and persistence contracts
│   ├── reliability/                   # Retry and failure mechanics
│   ├── modalities/                    # Ring 1: typed capability specs and services
│   │   ├── image/
│   │   ├── video/
│   │   ├── structured/
│   │   ├── tool_loop/
│   │   ├── background_removal/
│   │   ├── music/
│   │   ├── sound_effect/
│   │   └── speech/
│   └── providers/                     # Ring 2: first-party provider adapters
│       ├── openai/
│       ├── openrouter/
│       ├── fal/
│       └── elevenlabs/
└── stage_gen/
    ├── pipeline/                      # The SDK: define / plan / run / inspect, GraphDocument
    ├── components/                    # Reusable components and bounded formats
    ├── workflows/                     # One folder per product deliverable
    ├── recipes/character_3d/          # Frozen character-3d implementation path
    ├── examples.py                    # The public example contract
    ├── runs.py                        # Run discovery and derived views for the viewer
    ├── media/                         # Shared inspection and transforms
    ├── orchestration/                 # Composition root: services, GraphExecutor, routing
    ├── providers/                     # Application provider adapters (character_3d)
    ├── interfaces/                    # The stage-gen CLI: one verb set, lazy commands
    ├── application/                   # Generic output/cache roots and reporting
    └── resources/                     # Explicitly packaged support resources
```

GNode scheduling, topology, trace, cache identity and provenance mechanisms remain
in place. The SDK composes them. It does not add another graph engine.
Provider construction stays at the application boundary; workflows can receive
services without taking ownership of credentials or provider selection.

The wheel contains `gnode` and `stage_gen`. Optional demo and concept packages have
their own project metadata. The core source distribution removes workspace-only
metadata, so installing it does not require absent demo directories.

## Components: where reusable work belongs

```text
src/stage_gen/components/
├── actor_content/                     # Actor asset content and admission
├── character_profile/                 # Reusable identity/profile input
├── portrait_motion/                   # Portrait processing, rendering and validation
├── movie_sprite/                      # Transparent body-loop finishing and spatial controls
├── sideview_actor/                    # Sprite geometry, scale and locomotion assets
├── sideview_layers/                   # Layer processing and parallax parameters
├── sideview_map_design/               # Constrained spatial/layout generation
├── sideview_terrain/                  # Side-view terrain asset geometry
├── painted_terrain/                   # Painted ground, including structural pieces
├── worldgen/                          # Spatial generation primitives and fields
├── image_repeat/                      # Repeat admission and conditioned repair
├── ui_art/                            # Requested UI artwork roles and validation
├── screen_art/                        # Screen plates, layouts and admission
├── effects_art/                       # Effect imagery and portable geometry
├── music/                             # Individual generated music assets
├── voice_profile/                     # Reusable voice definitions
├── sound_effect/                      # Individual sound-effect requests
├── speech/                            # Individual speech requests
├── audio_normalization/               # Explicit audio transforms
└── video_clip/                        # Video processing with explicit frame constraints
```

These names describe actual component families. A component need not be fully
agnostic about its medium: a sprite component can understand frames and foot
anchors, and a terrain component can understand occupancy. It must not infer a
complete game's combat, quests, camera controller or runtime state.

The structural ground algorithm was promoted out of the runner. Actor scale now
accepts an explicit pixels-per-unit contract, with old player/tile calibration in
the game-owned adapter. UI, effects, screens, music and voices were split from their
former game aggregates. Game readers still supply game-specific role sets,
event triggers and playback bindings to those independent capabilities.

The `.scenario` contract is owned by the Godot Scenario package, including its
independent authoring distribution. The game invokes its sequence through explicit
bindings; the asset product does not depend on that format. Sprite playback,
portrait animation and movie sprite assets retain their own bounded roles.

## Workflows and inputs

```text
src/stage_gen/workflows/
├── _registry.py, _catalog.py, _checks.py   # Discovery, catalog export, drift checks
├── looping_parallax/
│   ├── workflow.py, workflow.toml     # Code facts; what code cannot know
│   ├── page.mdx, contract.md          # The reader's page; the exact contract
│   ├── cli.py, example.py             # plan/run flags; example importer
│   ├── pipeline.py                    # The implementation
│   └── inputs/supplied_layers/        # Real offline layer normalization and preview
├── movie_sprite/                      # Endpoint video generation and local loop finishing
│   └── inputs/supplied_clip/          # Original procedural clip; no provider calls
├── portrait_motion/                   # Generation, qualification, budgets and recovery
│   └── inputs/                        # The four-card and face-crop specifications
├── universe/                          # No example.py; executor modules, not pipeline.py
│   └── inputs/lantern_ferry/          # Existing self-contained storyworld input
└── character_3d/                      # Declaration, CLI and importer only; no inputs/
    └── examples/tavi-parts.mdx        # Prose for one pinned example

src/stage_gen/recipes/character_3d/    # Frozen: run lineage binds this path

docs/sdk/pipelines/
├── local_media.py                     # Arbitrary graph: PNG + WAV + catalog
└── portrait_processing.py             # Component composition and preserved-pixel proof
```

Every workflow folder has the shape `looping_parallax/` shows, less the files a workflow
does not need; the tree lists only what differs. Sample inputs and their scripts live in a
workflow's `inputs/`; cross-component
SDK samples live in `docs/sdk/pipelines`. A future component example should likewise live
beside that component. Documentation links these owners instead of creating a second
implementation under a central examples framework.

The looping-parallax workflow accepts supplied layers. It produces repeating images,
canvas/offset/order/scroll metadata and a preview frame. It does **not** yet extract
hidden layers from one finished reference image. That operation can be added as a bounded
upstream generation stage with its own validation, while the repeat/composition/preview
stages remain reusable.

The universe workflow keeps its own scoped TOML. Portrait motion's pipeline belongs to its
workflow; component-level crop/render/reconstruction remains in the component. Universe seals
a `GraphDocument` (`stage_gen.pipeline.graph_document`) and runs through `GraphExecutor`
(`stage_gen.orchestration.graph_executor`) at the composition root, because it builds
`RunServices`; it does not define the SDK.

Examples are not committed. `stage-gen example promote` and `demo-games example export`
write frozen exports into the local, gitignored store `out/examples/<owner>/<id>/`, and each
owner's manifest pins them by digest.

## Documentation

`docs/` holds only what crosses workflows: [getting started](getting-started.md), the
[glossary](glossary.md), the [viewer](viewer.md) and [site](site.md) guides, the
[SDK guide](sdk/guide.md) and its samples, provider notes under `models/`, policy
(storage, publication, IP), cross-cutting specifications under `spec/`, and the history
under `decisions/`, `plans/` and `research/`. A workflow's guide and contract live in its
own `page.mdx` and `contract.md`; a game's documents live under its folder.

## Preview and runtime consumers

```text
web/                                   # One Bun workspace and the only Node boundary
├── ui/
│   ├── contracts/                     # Catalog, example and run-view parsers and fixtures
│   └── players/                       # Framework-free page players: mount(el, config)
├── viewer/                            # stage-gen view: read-only client over run folders
│   ├── app/                           # Run, workflow and artifact pages
│   └── lib/shell/                     # Confined read-only access to persisted runs
└── site/                              # Static landing and documentation (Next export)

godot/
├── games/
│   ├── afterlight/                    # Authored Scenario episode and game bindings
│   ├── command_link/                  # Authored Scenario mission and independent Lab
│   ├── bellweather/                   # Own project, gameplay and prepared-run binding
│   │   ├── inputs/
│   │   │   ├── default/               # Complete original input closure
│   │   │   └── waves/                 # Complete variant closure
│   │   ├── gameplay/                 # Platformer simulation and exclusive support
│   │   ├── scenes/                   # Camera, controls, rendering and HUD
│   │   ├── pipeline/
│   │   │   ├── prepare.py            # Explicit input/variant selection
│   │   │   └── src/bellweather_pipeline/
│   │   ├── tools/                    # Map and terrain authoring, captures and parity
│   │   ├── tests/                    # Native game regression checks
│   │   └── docs/                     # Map formats and asset build graph
│   ├── iron_petal_unit/
│   │   ├── inputs/                   # Runner authored closure
│   │   ├── gameplay/                 # Runner rules and exclusive support
│   │   ├── scenes/                   # Runner presentation
│   │   ├── pipeline/src/iron_petal_unit_pipeline/
│   │   ├── tools/
│   │   ├── tests/
│   │   └── docs/                     # Track, audio, voice and effect bindings
│   ├── ember_hollow/
│   │   ├── inputs/                   # Survival authored closure
│   │   ├── gameplay/                 # Survival simulation and exclusive support
│   │   ├── scenes/                   # World, camera and UI
│   │   ├── pipeline/src/ember_hollow_pipeline/
│   │   ├── tools/                    # Fixture, capture and cache-golden maintenance
│   │   ├── tests/
│   │   └── docs/                     # World, seasons, crafting, ground and generation
│   ├── the_grain/
│   │   ├── inputs/                   # Case, rooms, scenarios and story together
│   │   ├── gameplay/
│   │   │   ├── case/
│   │   │   ├── dialogue_scene/
│   │   │   └── pointclick_room/
│   │   ├── scenes/                   # Case shell and its room/dialogue leaves
│   │   ├── pipeline/src/the_grain_pipeline/
│   │   ├── tools/
│   │   ├── tests/
│   │   └── docs/
│   └── _shared/                      # Private reuse among the named games
│       ├── runtime/
│       │   ├── addons/demo_support/
│       │   │   ├── simulation/       # Reused deterministic kernel and families
│       │   │   ├── io/               # Common loading and confinement
│       │   │   └── testing/          # Game-independent native test harness
│       │   └── tests/
│       ├── python/src/demo_game_tools/
│       │   ├── scenario/             # Supported v2 production metadata and adapters
│       │   ├── input_formats/        # Shared readers with actual callers
│       │   ├── media/                # Shared game UI and soundtrack binding helpers
│       │   ├── io/                   # Package capture
│       │   └── application/          # Shared preparation services
│       └── docs/                     # Shared input and manifest format references
├── packages/
│   ├── scenario_runtime/             # VN-oriented invocation framework
│   │   ├── addons/scenario_runtime/  # Program, Session, bindings and presenters
│   │   ├── authoring/                # Independent Python compiler and content tools
│   │   ├── conformance/, examples/   # Shared fixtures and runnable consumers
│   │   └── tests/, tools/, docs/     # Owned verification, assembly and contract
│   ├── game_presentation/            # Independent lower presentation mechanisms
│   ├── content_io/                   # Confined local media/data access
│   └── sideview_rendering/           # Independent layer/parallax rendering
├── templates/
│   ├── asset_consumer/               # Explicit PNG import and local GDScript display
│   └── vn/                           # Copyable game with authored Scenario content
└── tools/
    └── python/src/demo_game_collection/
                                        # Collection CLI and cross-game fixture census
```

Each of the four run-consuming games has `project.godot`, its own `main.tscn`,
`pipeline/prepare.py` and a separately packaged Python builder. The tree expands
Bellweather's preparation entry point once to avoid repeating identical mechanics.
Afterlight and Command Link keep their working project organization and game-local
Labs; this is not a mandatory directory schema for a new game.

Inputs live with each game. Game inputs have no root `main.toml` selector and no
`library`, `legacy` or empty `demos` tier; `library/` holds only the approved
character-3d examples. Existing TOML member paths, identities and
cache semantics remain supported by the same consuming game. Gameplay parameters
may move into GDScript or resources later, independently for each game.

`_shared` is private implementation with actual multiple-game callers. Single-game
rules, rendering and builders stay with their game. Shared code imports no named
game. The collection CLI under `godot/tools/` can import all game preparation
packages; its `demo-games` commands support existing format inspection and fixture
maintenance. The optional `games` installation group keeps all of this outside the
public product's default environment and distributions.

The viewer accepts the public pipeline envelope with arbitrary pipeline identity.
It retains persisted readers, displays unknown metadata and supports application
preview annotations. Parallax is one inspector. Generic MIME handling permits
unfamiliar assets without adding a workflow enum.

The asset-consumer template copies a selected asset and its verified provenance;
its GDScript loads that local content. A game can extend preparation to create
resources, bind animations and wire scenes. Starting Godot reads prepared assets
and does not start a provider operation. Existing `out/` runs remain at their
current locations and are selected explicitly.

Maintained game format documents live under their game or `_shared/docs`.
The current [Scenario directory preview](../godot/packages/scenario_runtime/docs/layout.md)
expands authoring, execution and game binding ownership. Side-view map design
remains in `docs/spec/`; its former Scenario page points to the Godot owner. Historical decisions remain records of their original context. The
[Godot ownership record](plans/godot-consumer-layout.md) details the migration.

## Choosing the owner of a new change

| Change | Owner |
|---|---|
| Scheduling, graph state, generic provenance | GNode ring 0 |
| A modality protocol or retry-owning service | GNode ring 1 |
| Provider request/response adaptation | GNode ring 2 |
| Asset-specific processing and admission | Component |
| Several asset stages with a bounded output | Workflow |
| User-specific graph composition | External Python definition or SDK example |
| Workflow asset parameters | Workflow-owned TOML or Python inputs |
| A specialized preview | Viewer inspector or bounded runtime package |
| VN-oriented narrative authoring and invocation | Godot Scenario package |
| Episode direction and installed game capabilities | Consuming game |
| Resource import and asset-to-scene binding | Consumer's preparation script |
| Combat, progression, quest state or scene control | Consumer's code |
| Existing game TOML or whole-game build maintenance | Named game preparation package; shared reader only where reused |

The gates follow these owners. The default gate verifies the product without
installing or invoking Godot and Bun. Optional scopes verify their consumers, and
`--scope all` exercises the entire repository. See [verification](../VERIFICATION.md)
and the [implementation ledger](plans/repository-reshape.md).
