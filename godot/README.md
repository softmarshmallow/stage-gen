# The Godot tree

Godot owns playable consumers, runtime integration, and consumer templates. The Python product
provides asset pipelines and the SDK; a game decides which outputs it uses and how they become
scenes, animation, presentation, or gameplay. There is no canonical whole-game contract for new
consumers.

```text
packages/    reusable Godot SDK packages, each with its own addon, tests, and tools
templates/   editable project starting points with consumer-owned preparation and bindings
games/       complete authored games with their own content and behavior
demos/       small independent consumer demonstrations; currently only an ownership README
legacy/     preserved generated-game builders, inputs, tooling, and the shared runtime
```

| Project | Responsibility | Entry point |
| --- | --- | --- |
| [game_presentation](packages/game_presentation/README.md) | Presentation SDK: camera, actors, transitions, effects, text, audio, and contact for staged scenes | `python godot/packages/game_presentation/tools/check_sdk_package.py` |
| [asset_consumer](templates/asset_consumer/README.md) | Minimal image consumer; its own script prepares a supplied PNG and its own scene displays it | `godot --path godot/templates/asset_consumer` |
| [vn](templates/vn/README.md) | The Signal Room, an editable visual-novel starter using the presentation SDK | `godot --path godot/templates/vn` |
| [afterlight](games/afterlight/README.md) | Bishōjo: Afterlight, The Address Beyond, an authored adventure and Lab | `godot --path godot/games/afterlight -- --language ko` |
| [command_link](games/command_link/README.md) | Command Link, an authored tactical story and Lab | `godot --path godot/games/command_link` |
| [legacy runtime](legacy/runtime/README.md) | Historical generated-run hosts and their shared simulation families | `godot --path godot/legacy/runtime -- --run <absolute run directory>` |

## Legacy ownership

`godot/legacy/python/stage_gen_legacy` contains the historical game builders, components, and
contracts. `godot/legacy/inputs` preserves their existing TOML packages. `godot/legacy/runtime`
contains the shared Godot kernel, families, genres, and hosts. [Legacy tools](legacy/tools/README.md)
maintain their input packages, graph snapshots, and parity evidence. These retain old demos
without making their gameplay schemas requirements of the product or of a new game.

## Package and project boundaries

A project can link a package's addon payload during development, for example:

```text
games/<id>/addons/<name> -> ../../../packages/<name>/addons/<name>
```

The package assembler copies real bytes into a distributable project. The boundary test allows
only links to package payloads and requires each package to own its project and payload. This is
a code-sharing rule; media crosses a real consumer boundary by copying, with its provenance and
rights intact.

Every project owns its renderer, canvas, main scene, configuration, preparation scripts, and
runtime bindings. Tests live with that project and run with
`godot --headless --path <project> --script res://tests/<suite>.gd`. A template may consume one
asset without linking any package. A game may compose several packages without requiring an
asset-generation recipe to understand its behavior.
