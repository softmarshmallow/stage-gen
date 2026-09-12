# Bellweather

A maintained side-scrolling platformer that consumes Stage Gen asset runs.
This project owns its gameplay, content interpretation and Godot composition.

From the repository root, import the project once after cloning or moving scripts,
then launch an existing generated run:

```sh
godot --headless --editor --path godot/games/bellweather --quit
godot --path godot/games/bellweather -- --run "$PWD/out/bellweather-c6-parity"
```

Arrow keys move; Space jumps; E interacts.

The run directory is explicit. Starting the game never generates assets. The
example path above uses existing local output; a fresh clone has no `out/` media.
Authored inputs live in `inputs/default/` and `inputs/waves/` and asset preparation starts with
`pipeline/prepare.py --help`. Existing TOML is this game's configuration.

## Source ownership

- `main.gd` and `main.tscn` compose this game's entry scene.
- `gameplay/` owns the deterministic simulation and game-specific supporting systems.
- `scenes/` owns rendering, input, camera, audio and interface code.
- `tests/` and `tools/` own this game's regressions, replay and capture helpers.
- `addons/demo_support` links to the private shared implementation used by these games.

Run this game's native regressions from the repository root:

```sh
python3 godot/tools/run_native_suite.py --project bellweather
```

For a movable source project with real addon files, use:

```sh
python3 godot/tools/package_game_project.py --project bellweather --destination /tmp/bellweather-project
```

That command copies source only. Pass or distribute prepared assets separately
under their existing provenance and publication rules.
