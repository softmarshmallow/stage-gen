# Afterlight narrative content

`episode.scenario` is the sole authored episode. `catalog.json` gives its typed
presentation configurations reusable names. `program.json` and `program.map.json`
are compiled artifacts, maintained by the game-owned tool:

```sh
uv run --group games python godot/games/afterlight/tools/compile_narrative.py
uv run --group games python godot/games/afterlight/tools/compile_narrative.py --check
```

Run from the repository root. The installed capability schema belongs to
`packages/scenario_runtime/addons/scenario_runtime/presentation/front_types.json`;
Afterlight binds geometry/resources through `narrative_binding.gd`. This directory
contains data, not an installed capability or downloaded GDScript. Text and voice
remain in their game-owned directories. `story_beats.gd` exposes a read-only
review/inventory projection; Session alone progresses the graph.

See the [game guide](../README.md), [source syntax](../../../packages/scenario_runtime/authoring/README.md)
and [invocation contract](../../../packages/scenario_runtime/docs/contract.md).
