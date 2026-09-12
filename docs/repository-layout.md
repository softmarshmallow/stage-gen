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
│   └── stage_gen/                     # Asset authoring, capabilities and recipes
├── examples/
│   └── pipelines/                     # Public SDK composition examples
├── web/                               # Optional run viewer and asset inspectors
├── godot/
│   ├── packages/                      # Reusable, bounded runtime SDKs
│   ├── templates/                     # Copyable application starting points
│   ├── demos/                         # Consumer-demo guidance; no project yet
│   ├── games/                         # Independently authored playable consumers
│   ├── legacy/                        # Old game contracts, builders, inputs and hosts
│   └── tools/                         # Godot workspace/package operations
├── apps/
│   └── concept_studio/                # Optional concept-authoring Python application
├── concept-studio/                    # Existing concept docs, gallery and local drafts
├── scripts/                           # Product/repository maintenance and verification
├── tests/                             # Tests selected by product or consumer ownership
├── docs/                              # Product guides, scoped references and history
├── .agents/skills/                    # Asset authoring and consumer-specific workflows
├── .github/workflows/                # Separate product and consumer gates
├── pyproject.toml                     # Core distribution and local workspace metadata
└── uv.lock                            # Repository development workspace lock
```

`library/` is gone. Its private folder held no private implementation or assets.
The old game inputs now belong to their legacy Godot consumers; the independent
universe example belongs to its recipe. Users supply external input, output and
cache directories rather than registering projects inside this checkout.

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
    ├── pipeline/                      # define / plan / run / inspect; arbitrary graphs
    ├── components/                    # Reusable capabilities and bounded formats
    ├── recipes/                       # Named compositions producing asset results
    ├── media/                         # Shared inspection and transforms
    ├── orchestration/                 # Concrete services and application configuration
    ├── interfaces/                    # Lazy CLI adapters
    ├── application/                   # Generic output/cache roots and reporting
    └── resources/                     # Explicitly packaged support resources
```

GNode scheduling, topology, trace, cache identity and provenance mechanisms remain
in place. The public harness composes them. It does not add another graph engine.
Provider construction stays at the application boundary; recipes can receive
services without taking ownership of credentials or provider selection.

The wheel contains `gnode` and `stage_gen`. Optional demo and concept packages have
their own project metadata. The core source distribution removes workspace-only
metadata, so installing it does not require absent demo directories.

## Components: where reusable work belongs

```text
src/stage_gen/components/
├── actor_content/                     # Actor asset content and admission
├── character_profile/                 # Reusable identity/profile input
├── dialogue_sequence/                 # Bounded presentation sequence data
├── portrait_motion/                   # Portrait processing, rendering and validation
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
├── video_clip/                        # Video processing with explicit frame constraints
└── scenario/                          # Self-contained narrative program and admission
```

These names describe actual capability families. A component need not be fully
agnostic about its medium: a sprite component can understand frames and foot
anchors, and a terrain component can understand occupancy. It must not infer a
complete game's combat, quests, camera controller or runtime state.

The structural ground algorithm was promoted out of the runner. Actor scale now
accepts an explicit pixels-per-unit contract, with old player/tile calibration in
the legacy adapter. UI, effects, screens, music and voices were split from their
former game aggregates. Legacy readers still supply game-specific role sets,
event triggers and playback bindings to those independent capabilities.

The `.scenario` contract survives independently. Its events can be bound by a
consumer without becoming a mandatory field of every asset pipeline. The same
rule applies to sprite playback, portrait animation and any future Live2D adapter:
keep each contract bounded; do not combine them into a universal game language.

## Recipes and examples

```text
src/stage_gen/recipes/
├── looping_parallax/
│   └── examples/
│       └── supplied_layers/           # Real offline layer normalization and preview
├── portrait_motion/                   # Generation, qualification, budgets and recovery
├── storefront/
│   └── examples/
│       └── minimal/                   # Original procedural input and offline planning
└── universe/
    └── examples/
        └── lantern_ferry/             # Existing self-contained storyworld input

examples/
└── pipelines/
    ├── local_media.py                 # Arbitrary graph: PNG + WAV + catalog
    └── portrait_processing.py         # Component composition and preserved-pixel proof
```

Cross-capability SDK examples live in `examples/pipelines`. Recipe-specific inputs
and scripts live beside their recipe. A future component example should likewise
live beside that component. Documentation links these owners instead of creating
a second implementation under a central examples framework.

The parallax example currently accepts supplied layers. It produces repeating
images, canvas/offset/order/scroll metadata and a working scrolling inspector.
It does **not** yet extract hidden layers from one finished reference image. That
operation can be added as a bounded upstream generation stage with its own
validation, while the repeat/composition/preview stages remain reusable.

The existing universe and storefront graph builders keep their own scoped TOML
and command adapters. Portrait motion's workflow now belongs to its recipe;
component-level crop/render/reconstruction remains in the component. Old internal
executor aliases preserve supported code paths without defining the new SDK.

## Preview and runtime consumers

```text
web/
├── app/                               # Run browsing and inspection UI
└── lib/
    ├── shell/                         # Confined read-only access to persisted runs
    └── run-viewer/                    # Generic graphs, media and bounded inspectors

godot/
├── packages/
│   └── game_presentation/             # Existing independent presentation addon
├── templates/
│   ├── asset_consumer/                # Explicit PNG import + local GDScript display
│   └── vn/                            # Existing presentation starter
├── games/
│   ├── afterlight/                    # Game-owned scripts, scenes, bindings and tools
│   └── command_link/                  # Game-owned scripts, scenes, bindings and tools
├── demos/                             # Guidance for small future consumer demos
└── tools/                             # Workspace/package tooling
```

The viewer accepts the public pipeline envelope with arbitrary pipeline identity.
It retains existing persisted readers, displays unknown metadata, and supports
application-owned preview annotations. Parallax is one inspector, not a gameplay
host. Generic MIME handling permits unfamiliar assets without adding a recipe enum.

The asset-consumer template's own preparation script copies a selected asset and
its verified provenance. Its GDScript loads that local content. A complete game
can extend this script to create resources, bind animation names or wire scenes;
those choices belong to that game. Stage Gen does not emit its gameplay from a
canonical TOML document.

## Retained demo system

```text
godot/legacy/
├── inputs/
│   ├── bellweather/
│   ├── bellweather-waves/
│   ├── iron-petal-unit/
│   ├── ember-hollow/
│   ├── clockmakers_attic/
│   ├── larkfield/
│   └── the_grain/
├── python/
│   └── stage_gen_legacy/
│       ├── components/
│       │   ├── game_contract/         # Existing membership/schema and scale adapter
│       │   ├── platformer_gameplay/   # Game rule vocabulary
│       │   ├── runner_gameplay/       # Game rule vocabulary
│       │   ├── platformer_map/        # Demo map binding and authored closure
│       │   ├── platformer_content/    # Demo asset-to-game closure
│       │   ├── runner_content/        # Demo asset-to-game closure
│       │   ├── runner_track/          # Demo track composition
│       │   ├── runner_audio/          # Triggers and playback realization
│       │   ├── sideview_stage/        # Complete stage composition
│       │   ├── game_ui/               # Demo role-set adapter over ui_art
│       │   ├── game_fx/               # Trigger adapter over effects_art
│       │   ├── game_shell/            # Shell adapter over screen_art
│       │   ├── game_soundtrack/       # Catalog/playback adapter over music
│       │   ├── game_voices/           # Cast adapter over voice_profile
│       │   └── case/                  # Specific investigation-game composition
│       ├── recipes/
│       │   ├── sideview_platformer/
│       │   ├── sideview_runner/
│       │   ├── oblique_survival/
│       │   ├── dialogue_scene/
│       │   └── pointclick_room/
│       ├── orchestration/             # Package selection, capture and case binding
│       ├── interfaces/                # stage-gen legacy / stage-gen-legacy
│       └── application/               # Legacy genre/application helpers
├── runtime/
│   ├── kernel/                        # Existing demo simulation utilities
│   ├── families/                      # Existing runtime families
│   ├── genres/                        # Existing genre logic
│   ├── hosts/                         # Existing Godot bindings
│   ├── tests/                         # Retained regression suite
│   └── tools/                         # Fixture, capture, export and test tools
└── tools/                             # Game authoring and contract maintenance
```

Existing inputs and runtime hosts were relocated without converting every old TOML
to GDScript. The optional legacy package imports public asset capabilities. No
public product package imports it. Its full fixture/model-policy census is also
legacy-owned; the core catalog no longer loads complete games to inspect routes.

Game specifications remain in the documentation reference collection, explicitly
marked as legacy where they describe complete-game contracts. Historical decisions
are records, not instructions to expand those contracts. The root architecture,
new asset-authoring skill and public SDK guide control new work.

## Choosing the owner of a new change

| Change | Owner |
|---|---|
| Scheduling, graph state, generic provenance | GNode ring 0 |
| A modality protocol or retry-owning service | GNode ring 1 |
| Provider request/response adaptation | GNode ring 2 |
| Asset-specific processing and admission | Component |
| Several asset stages with a bounded output | Recipe |
| User-specific graph composition | External Python definition or SDK example |
| Recipe asset parameters | Recipe-owned TOML or Python inputs |
| A specialized preview | Viewer inspector or bounded runtime package |
| Resource import and asset-to-scene binding | Consumer's preparation script |
| Combat, progression, quest state or scene control | Consumer's code |
| Existing game TOML or demo graph maintenance | Godot legacy package |

The gates follow these owners. The default gate verifies the product without
installing or invoking Godot and Bun. Optional scopes verify their consumers, and
`--scope all` exercises the entire repository. See [verification](../VERIFICATION.md)
and the [implementation ledger](plans/repository-reshape.md).
