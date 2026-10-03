# Godot example project

This repository contains two separately owned products: **Stage Gen**, the main
asset-generation SDK and authoring toolkit, and **this Godot example project**,
which demonstrates how those assets become playable applications.

Relative to Stage Gen, `godot/` is an examples directory named for its engine.
Within that scope it is its own maintained project, with runtime packages, games,
templates and tools. Each game owns its gameplay and asset integration. Users can
adopt an example or package without making its game contract part of Stage Gen.

The [project charter](CHARTER.md) defines the continuing goals, responsibilities
and boundaries. Future work on shared gameplay, presentation or visual-novel
systems belongs to this project and can reorganize it on its own. The current
tree below is an implementation of that scope, not a fixed architecture.

The [architecture](docs/architecture.md) describes current internal ownership and
the [verification guide](docs/verification.md) explains the complete check roster.
The [organization review](docs/organization-review.md) records the extraction
rationale; the [roadmap](docs/roadmap.md) separates remaining candidates.

[Movie Sprite Actor](docs/movie-sprite-actor.md) names the prepared body-motion
and independent facial-state representation demonstrated in Afterlight Lab. Its
[independent runtime package](packages/movie_sprite_actor/README.md) owns playback
and compositing; Afterlight owns its art, preparation and performance direction.

```text
godot/
├── games/                            # Named games, maintained as peers
│   ├── afterlight/
│   ├── command_link/
│   ├── bellweather/                   # Platformer, including Waves inputs
│   ├── iron_petal_unit/               # Runner
│   ├── ember_hollow/                  # Survival
│   ├── the_grain/                     # Investigation, rooms and dialogue
│   └── _shared/                       # Private support used by several games
│       ├── runtime/addons/demo_support/
│       ├── runtime/addons/scene_navigation/
│       ├── python/src/demo_game_tools/
│       └── docs/
├── packages/
│   ├── game_presentation/            # Independent presentation controllers
│   ├── content_io/                   # Local content access and decoding
│   ├── movie_sprite_actor/           # Body atlas playback and independent facial states
│   ├── progression/                  # Reward design, ledger, mailbox and claim screens
│   ├── scenario_runtime/             # VN-oriented sessions, compiler and presenters
│   └── sideview_rendering/           # Layers, parallax and pixel presentation
├── templates/
│   ├── asset_consumer/                # Explicit PNG preparation and display
│   └── vn/                            # Copyable game invoking authored Scenario content
├── tools/                            # Workspace verification and collection CLI
├── tests/                            # Godot-owned tooling checks
└── docs/                             # Current architecture, verification and roadmap
```

## Play a game

Run these commands from the repository root. The four run-consuming games require
an already prepared absolute run directory. Starting a game performs no generation.
Use each game's README for input preparation, controls and supported run formats.

After cloning or moving scripts, import the selected project once so Godot builds
its local script-class cache. For example:

```sh
godot --headless --editor --path godot/games/bellweather --quit
```

Use the same project path for its launch below. This step discovers scripts and
imports existing local resources; it makes no provider calls.

| Game | Launch |
| --- | --- |
| [Afterlight](games/afterlight/README.md) | `godot --path godot/games/afterlight -- --language en` |
| [Command Link](games/command_link/README.md) | `godot --path godot/games/command_link` |
| [Bellweather](games/bellweather/README.md) | `godot --path godot/games/bellweather -- --run "$PWD/out/bellweather-c6-parity"` |
| [Iron Petal Unit](games/iron_petal_unit/README.md) | `godot --path godot/games/iron_petal_unit -- --run "$PWD/out/iron-petal-c1-parity"` |
| [Ember Hollow](games/ember_hollow/README.md) | `godot --path godot/games/ember_hollow -- --run "$PWD/out/ember-hollow-v13"` |
| [The Grain](games/the_grain/README.md) | `godot --path godot/games/the_grain -- --run /absolute/path/to/case-run` |

The example `out/` paths name existing local runs; they are not included in a fresh
checkout. Afterlight and Command Link likewise need their separately held bound
media. The game READMEs describe their refusal behavior when content is missing.

## Prepare assets

Each game owns its preparation entry point and its input selection. No root selector
chooses a game for the repository.

Every game's assets build with gnode from the game's own folder, and planning is offline.
Bellweather's `default` and `waves` inputs are variants of the same game; Ember Hollow
plans one rung of its scope ladder at a time:

```sh
uv sync --frozen --group games
cd godot/games/iron_petal_unit && uv run gnode plan pipeline/workflow.py:build --arg package=inputs
cd godot/games/bellweather && uv run gnode plan pipeline/workflow.py:build --arg package=inputs/default
cd godot/games/the_grain && uv run gnode plan pipeline/workflow.py:room --arg package=inputs/rooms/window
cd godot/games/the_grain && uv run gnode plan pipeline/workflow.py:scene --arg package=inputs
cd godot/games/ember_hollow && uv run gnode plan pipeline/workflow.py:build --arg package=inputs --arg scope=full
```

The Grain's `pipeline/prepare.py` proves its case and publishes it over the rooms' and the
scene's delivered folders.

The collection CLI, `uv run --group games demo-games --help`, maintains existing format
inspection and authoring commands without making those formats part of the public asset SDK.

## Packages and templates

[game_presentation](packages/game_presentation/README.md),
[content_io](packages/content_io/README.md),
[movie_sprite_actor](packages/movie_sprite_actor/README.md),
[progression](packages/progression/README.md),
[scenario_runtime](packages/scenario_runtime/README.md) and
[sideview_rendering](packages/sideview_rendering/README.md) provide bounded runtime
capabilities. [asset_consumer](templates/asset_consumer/README.md)
and [vn](templates/vn/README.md) are copyable starting projects. A game chooses the
packages it needs; it need not consume all packages or use a particular game schema.

Scenario is the selected embeddable narrative framework: games invoke authored
sequences and grant installed presentation capabilities while retaining their
world, input, camera and saves. Its compiler is independently installable, and
its data-only content can use new game-defined presets without adding algorithms.
The [Scenario directory preview](packages/scenario_runtime/docs/layout.md) shows
its authoring/runtime/game boundaries; [embedding](packages/scenario_runtime/docs/embedding.md)
covers optional portraits, combat dialogue and 2D/3D actor bubbles.

During development, projects link the addon payload of an independent package or
`games/_shared/runtime/addons/demo_support`. Assemblers copy real source files
into distributable projects. Shared support imports no named game. Media crosses
an application boundary through explicit copies with its provenance and rights.

Every game owns its renderer, main scene, configuration and gameplay. Native tests
live with their owner; [workspace tools](tools/README.md) run them together. See the
[current architecture](docs/architecture.md) for the ownership map.
