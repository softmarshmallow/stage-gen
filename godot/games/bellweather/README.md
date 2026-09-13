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
- `addons/sideview_rendering` selects independent [layer layout and image presentation](../../packages/sideview_rendering/README.md); run-file interpretation and depth ordering stay here.
- `addons/scenario_runtime` selects the independent [Scenario framework](../../packages/scenario_runtime/README.md); gameplay, dialogue UI and save policy stay here.

## Scenario invocation

Existing v2 declarations, scripts and prepared program bytes remain supported.
`demo_game_tools.scenario` owns production metadata and preparation; the addon's
compatibility reader executes these programs through the current Session.
New rich source authoring belongs to the [Scenario compiler](../../packages/scenario_runtime/authoring/README.md).

The game explicitly chooses `world.dialogue_policy.hold_world` (default `true`).
Setting it to `false` allows world/combat updates during conversation. The optional
portrait profile defaults left; it can omit/reflow/reserve the portrait and choose
a speaking expression without requiring the actor on stage. Dialogue snapshot/
restore is a game-owned save slice that resolves its current interaction/program
and does not replay rewards; this adds no general save UI.

## Checks

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
