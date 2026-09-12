# The Grain

A maintained investigation game with case, room and dialogue scenes that consumes Stage Gen asset runs.
This project owns its gameplay, content interpretation and Godot composition.

From the repository root, import the project once after cloning or moving scripts,
then launch an existing generated run:

```sh
godot --headless --editor --path godot/games/the_grain --quit
godot --path godot/games/the_grain -- --run "$PWD/out/the-grain-episode-one"
```

Use the mouse for room interactions and case controls; Space advances dialogue.

The run directory is explicit. Starting the game never generates assets. The
example path above uses existing local output; a fresh clone has no `out/` media.
Authored inputs live in `inputs/` and asset preparation starts with
`pipeline/prepare.py --help`. Existing TOML is this game's configuration.

## Source ownership

- `main.gd` and `main.tscn` compose this game's entry scene.
- `gameplay/` owns the deterministic simulation and game-specific supporting systems.
- `scenes/` owns rendering, input, camera, audio and interface code.
- `tests/` and `tools/` own this game's regressions, replay and capture helpers.
- `addons/demo_support` links to the private shared implementation used by these games.
- `addons/scenario_runtime` selects the independent [scenario interpreter](../../packages/scenario_runtime/README.md); gameplay, dialogue UI and save policy stay here.

Run this game's native regressions from the repository root:

```sh
python3 godot/tools/run_native_suite.py --project the_grain
```

The case owns its leaf scenes. To inspect an existing room or dialogue run independently:

```sh
godot --path godot/games/the_grain res://scenes/pointclick_room/main.tscn -- --run "$PWD/out/the-grain-window-a4"
godot --path godot/games/the_grain res://scenes/dialogue_scene/main.tscn -- --run "$PWD/out/the-grain-scene-a" --scenario e1_office
```

For a movable source project with real addon files, use:

```sh
python3 godot/tools/package_game_project.py --project the_grain --destination /tmp/the_grain-project
```

That command copies source only. Pass or distribute prepared assets separately
under their existing provenance and publication rules.
