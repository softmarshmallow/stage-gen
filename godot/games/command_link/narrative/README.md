# Command Link mission content

The `.scenario` source owns mission dialogue, branches, effects, required contact
and progression. Its catalog defines typed data presets; the compiled program and
source map are derived artifacts. The game owns the compiler entry point:

```sh
uv run --group games python godot/games/command_link/tools/compile_mission.py
uv run --group games python godot/games/command_link/tools/compile_mission.py --check
```

Run from the repository root. Installed mechanism parameters are defined in
`presentation/scenario_capabilities.json` outside this content directory.
`game.gd` binds the actual stage, resources and input to Session; the independent
Presentation Lab directly studies controllers without becoming mission content.

See the [game guide](../README.md), [source syntax](../../../packages/scenario_runtime/authoring/README.md)
and [invocation contract](../../../packages/scenario_runtime/docs/contract.md).
