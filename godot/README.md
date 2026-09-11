# The Godot tree

One directory of Godot 4.7 projects in three tiers, plus the legacy run consumer.
The rule is in the [topology proposal](../docs/research/game-presentation-sdk-topology.md).

```text
packages/    shared code. Each package is an addon project: project.godot, the
             payload at addons/<name>/, its own tests, tools and history.
templates/   agnostic starting points, one per recipe. A branded game is copied
             from one; each plays that recipe's content and nothing branded.
games/       branded games. Complete, free to consume any package, consumed by
             nothing.
runtime/     legacy: the generated-run consumer, one project with a host per
             recipe, moved here intact. Its README is its manual.
```

| Project | What it is | Run it |
| --- | --- | --- |
| [`packages/game_presentation/`](packages/game_presentation/README.md) | the presentation SDK: camera, actors, Manpu, transitions, effects, text, audio and contact for staged 2D scenes | `python3 godot/packages/game_presentation/tools/check_sdk_package.py` |
| [`templates/vn/`](templates/vn/README.md) | The Signal Room: the agnostic visual-novel starting point, one editable `main.gd` | `Godot --path godot/templates/vn` |
| [`games/afterlight/`](games/afterlight/README.md) | Bishōjo: Afterlight, *The Address Beyond*: a 57-beat ensemble adventure with its own Lab | `Godot --path godot/games/afterlight -- --language ko` |
| [`games/command_link/`](games/command_link/README.md) | Command Link: a tactical commander-led story with a video opening and its own Lab | `Godot --path godot/games/command_link` |
| [`runtime/`](runtime/README.md) | legacy run consumer | `Godot --path godot/runtime -- --run <absolute run directory>` |

A game or template never contains a package. It links the payload into its own
`addons/` directory:

```text
games/<id>/addons/<name> -> ../../../packages/<name>/addons/<name>
```

Godot follows the link and Git tracks it; a checkout on Windows needs symlink
support. The package's assembler copies real bytes when it builds a new project
from a template, so a shipped project carries no link.
`tests/contract/test_godot_boundaries.py` refuses a link that points anywhere but
a package payload and requires every package to carry its project and payload.

Every project owns its `project.godot`, canvas, renderer and main scene; suites
sit in each project's `tests/` and run with
`Godot --headless --path <project> --script res://tests/<suite>.gd`.
