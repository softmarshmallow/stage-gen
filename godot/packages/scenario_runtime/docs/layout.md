# Scenario directory preview

This is the implemented layout, grouped by responsibility. Files are shown only
where they clarify an ownership boundary. The [contract](contract.md) owns
semantics; the [Godot charter](../../../CHARTER.md) owns the product boundary.

```text
godot/
├── CHARTER.md                         # Maintained example project, separate from Stage Gen
├── packages/
│   ├── scenario_runtime/
│   │   ├── addons/scenario_runtime/
│   │   │   ├── program/              # V3 program and catalog admission
│   │   │   ├── execution/            # Session progression, clocks, gates, operations, transport
│   │   │   ├── bindings/             # Capability host, channel grants, 2D/3D anchors
│   │   │   ├── presentation/         # Front-stage/cast/feed, dialogue and particle adapters
│   │   │   │   └── front_types.json # Installed front-stage capability schema
│   │   │   ├── content/              # Local immutable content-package admission
│   │   │   ├── compatibility/        # Supported v2 document/state adaptation
│   │   │   ├── program.gd            # Retained v2 reader entry point
│   │   │   ├── runtime.gd            # Retained v2 API facade over Session
│   │   │   └── sdk.json              # Payload/dependency and execution-version inventory
│   │   ├── authoring/                # Independent stagegen-scenario Python distribution
│   │   │   ├── src/scenario_authoring/
│   │   │   │   ├── syntax.py         # Concise source and bounded sequence expansion
│   │   │   │   ├── compiler.py       # Stable IR, digests and source maps
│   │   │   │   ├── catalog.py        # Named and inline typed definitions
│   │   │   │   ├── program.py        # Portable flow and reference admission
│   │   │   │   ├── content.py        # Explicit local content closure and assembly
│   │   │   │   ├── cli.py            # Check, compile, inspect, preview-input, pack
│   │   │   │   └── compatibility/v2/ # Retained narrative-only compiler
│   │   │   └── tests/               # Compiler, installed wheel and content-package tests
│   │   ├── conformance/              # Shared source/program/catalog fixtures
│   │   ├── examples/
│   │   │   ├── minimal/             # Small v2 compatibility example
│   │   │   ├── combat_dialogue/     # Game simulation continues; dialogue is invoked
│   │   │   ├── world_bubbles/       # Moving 3D subjects and host-camera projection
│   │   │   ├── catalog_effects/     # Named and explicit parameters share a mechanism
│   │   │   └── _shared/             # Private example host, not part of the addon
│   │   ├── tests/                   # Native execution, embedding and adapter checks
│   │   │   └── python/             # Starter assembly and cross-language content checks
│   │   ├── tools/                   # Compiler helpers, real-player preview, VN source assembly
│   │   └── docs/                    # Current contract, integration and compatibility
│   ├── game_presentation/           # Independent motion/effect/text/audio mechanisms
│   ├── content_io/                  # Confined local file/resource access
│   └── sideview_rendering/          # Independent layer and parallax rendering
├── games/
│   ├── afterlight/
│   │   ├── narrative/              # Episode source, catalog, compiled program and map
│   │   ├── narrative_binding.gd    # Installed capabilities and game resource binding
│   │   ├── text/, voice/, assets/   # Game-owned text, recordings and art catalogs
│   │   ├── tools/                  # Content compilation and explicit media preparation
│   │   └── tests/                  # Episode behavior and artistic integration checks
│   ├── command_link/
│   │   ├── narrative/              # Mission source, catalog, compiled program and map
│   │   ├── presentation/           # Game presenter and installed capability schema
│   │   ├── lab/                    # Direct mechanism studies, separate from mission
│   │   └── tests/                  # Mission, application and presentation regressions
│   ├── the_grain/
│   │   ├── inputs/                 # Retained scenarios, case and room authoring
│   │   ├── pipeline/               # Game-specific preparation and art bindings
│   │   ├── gameplay/case/          # Rooms, facts, case outcomes and durable saves
│   │   └── scenes/common/          # Game-owned dialogue/room presentation
│   ├── bellweather/
│   │   ├── inputs/{default,waves}/ # Retained supported game input variants
│   │   ├── pipeline/               # Game-owned preparation and prepared manifests
│   │   ├── gameplay/               # Platformer, interaction and world-hold policy
│   │   └── scenes/hud/             # Portrait/dialogue integration
│   ├── iron_petal_unit/             # Retained runner; no required Scenario adoption
│   ├── ember_hollow/                # Retained survival game; no required adoption
│   └── _shared/python/
│       └── src/demo_game_tools/scenario/
│                                   # V2 game metadata, file resolution and production envelopes
├── templates/vn/
│   ├── narrative/                  # Signal Room source, catalog, compiled program and map
│   ├── bindings/                   # Installed game capability schema
│   ├── text/                       # Localized content
│   ├── main.gd                     # Game objects, rendering, input and capability drivers
│   └── tests/                      # Freshness, two replies, contact and lifecycle behavior
└── tools/, tests/, docs/            # Godot collection coordination and ownership

src/stage_gen/                      # Asset product; no Scenario/compiler dependency
src/gnode/                          # Asset graph SDK; no Godot/game dependency
```

A game's `narrative/` contains executable *data*, never downloaded GDScript or a
capability implementation. Bindings and their installed schemas belong to the
player. Existing game roots need not acquire identical subdirectories: the tree
shows actual responsibilities, not a mandatory game template taxonomy.
