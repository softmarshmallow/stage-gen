# Iron Petal Unit

A maintained runner that consumes Stage Gen asset runs.
This project owns its gameplay, content interpretation and Godot composition.

From the repository root, import the project once after cloning or moving scripts,
then launch an existing generated run:

```sh
godot --headless --editor --path godot/games/iron_petal_unit --quit
godot --path godot/games/iron_petal_unit -- --run "$PWD/out/iron-petal-c1-parity"
```

Space, Up or W jumps; Down or S ducks.

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
- `addons/sideview_rendering` selects independent [layer layout and image presentation](../../packages/sideview_rendering/README.md); run-file interpretation and depth ordering stay here.

Run this game's native regressions from the repository root:

```sh
python3 godot/tools/run_native_suite.py --project iron_petal_unit
```

For a movable source project with real addon files, use:

```sh
python3 godot/tools/package_game_project.py --project iron_petal_unit --destination /tmp/iron_petal_unit-project
```

That command copies source only. Pass or distribute prepared assets separately
under their existing provenance and publication rules.
