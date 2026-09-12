# Ember Hollow

A maintained survival game that consumes Stage Gen asset runs.
This project owns its gameplay, content interpretation and Godot composition.

From the repository root, import the project once after cloning or moving scripts,
then launch an existing generated run:

```sh
godot --headless --editor --path godot/games/ember_hollow --quit
godot --path godot/games/ember_hollow -- --run "$PWD/out/ember-hollow-v13"
```

WASD moves; Space interacts; X uses the selected item.

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

Run this game's native regressions from the repository root:

```sh
python3 godot/tools/run_native_suite.py --project ember_hollow --run /tmp/ember-hollow-fixture
```

First create the offline fixture with
`uv run --group games python godot/games/ember_hollow/tools/make_fixture_run.py /tmp/ember-hollow-fixture`.

For a movable source project with real addon files, use:

```sh
python3 godot/tools/package_game_project.py --project ember_hollow --destination /tmp/ember_hollow-project
```

That command copies source only. Pass or distribute prepared assets separately
under their existing provenance and publication rules.
