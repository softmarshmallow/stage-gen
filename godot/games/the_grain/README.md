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
- `narrative/` owns rich Scenario source, catalog and compiled playback data.
- `authoring/` owns compiler source maps for diagnostics and freshness checks.
- `tests/` and `tools/` own this game's regressions, replay and capture helpers.
- `addons/demo_support` links to the private shared implementation used by these games.
- `addons/scenario_runtime` selects the independent [Scenario framework](../../packages/scenario_runtime/README.md); gameplay, dialogue UI and save policy stay here.

## Scenario invocation

“The way in” (`e1_way_in`) now plays from [authored rich content](narrative/e1_way_in.scenario)
through the current Scenario Host. The other five conversations retain their v2
prepared programs. The game's installed selection lives in `scenes/common/dialogue_player.gd`.

Existing v2 declarations, scripts and prepared program bytes remain supported.
`demo_game_tools.scenario` owns production metadata and preparation; the addon's
compatibility reader executes these programs through the current Session.
New rich source authoring belongs to the [Scenario compiler](../../packages/scenario_runtime/authoring/README.md).

The case owns room order, durable facts and saves. A dialogue leaf may suspend
its input/audio without pausing the SceneTree. Its `configure_presentation` can
select no portrait or a left/right portrait, with reflow or explicit reservation;
portrait selection is independent of the full cast stage. New dialogue saves use
a fingerprinted compatibility snapshot. Historical raw saves receive structural
checks only; invalid saved data is refused rather than silently restarted.

## Rich presentation demonstration

Open the complete “The way in” scene directly, using the same content and player
selected by the case after the motor court:

```sh
godot --path godot/games/the_grain res://scenes/dialogue_scene/main.tscn -- --run "$PWD/out/the-grain-scene-a" --scenario e1_way_in
```

The scene demonstrates location dissolves, cast entrances and repositioning,
a Winter Room camera settle, and closer framing when Lydia speaks. Its 47 lines,
two established case facts and `first_bell` outcome are preserved. All artwork
comes from the existing prepared run.

Click or press Space to finish the current transition and reveal its text; press
again to advance. Natural playback reveals text over time. In the case, Backlog
suspends the invocation's motion and text clocks without pausing the SceneTree.
Rich saves retain the exact Session and reconstruct authored transition progress.
An older v2 checkpoint inside this migrated scene is refused with a restart
message; its file is preserved. Saves in the other scenes retain their existing reader.

`presentation/scenario_capabilities.json` defines the installed `grain_frame` noun;
the catalog supplies explicit origin/target frames and durations. Binding code
resolves stages and actors against the prepared bundle before playing. It never
selects direction by a story-node ID. [Integration details](docs/rich-presentation.md).

Recompile edited direction without generation:

```sh
uv run --group games python godot/games/the_grain/tools/compile_narrative.py
```

## Checks

Run this game's native regressions from the repository root:

```sh
python3 godot/tools/run_native_suite.py --project the_grain
uv run --group games python godot/tools/check.py --owner the_grain --include-media --grain-scene-run "$PWD/out/the-grain-scene-a"
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
