# The Godot tree

Godot owns playable consumers, runtime integration and consumer templates. The
Python product supplies asset pipelines and the SDK. Each game decides how those
assets become scenes, animation and gameplay.

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
│       ├── python/src/demo_game_tools/
│       └── docs/
├── packages/game_presentation/        # Independent presentation SDK
├── templates/
│   ├── asset_consumer/                # Explicit PNG preparation and display
│   └── vn/                            # Copyable presentation project
└── tools/                             # Workspace verification and collection CLI
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

Each game owns its preparation entry point and its input selection. Bellweather's
`default` and `waves` inputs are variants of the same game. No root selector chooses
a game for the repository.

```sh
uv sync --frozen --group games
uv run --group games python godot/games/bellweather/pipeline/prepare.py
uv run --group games python godot/games/iron_petal_unit/pipeline/prepare.py
uv run --group games python godot/games/ember_hollow/pipeline/prepare.py
uv run --group games python godot/games/the_grain/pipeline/prepare.py
```

These defaults plan or validate inputs offline. Run `--help` on the selected
script for generation, deterministic rehearsal and output options. The collection
CLI, `uv run --group games demo-games --help`, maintains existing format inspection
and authoring commands without making those formats part of the public asset SDK.

## Packages and templates

[game_presentation](packages/game_presentation/README.md) provides independently
usable presentation mechanisms. [asset_consumer](templates/asset_consumer/README.md)
and [vn](templates/vn/README.md) are copyable starting projects. A game chooses the
packages it needs; it need not consume all packages or use a particular game schema.

During development, projects link the addon payload of an independent package or
`games/_shared/runtime/addons/demo_support`. Assemblers copy real source files
into distributable projects. Shared support imports no named game. Media crosses
an application boundary through explicit copies with its provenance and rights.

Every game owns its renderer, main scene, configuration and gameplay. Native tests
live with their owner; [workspace tools](tools/README.md) run them together. See the
[detailed layout](../docs/plans/godot-consumer-layout.md) for the ownership map.
