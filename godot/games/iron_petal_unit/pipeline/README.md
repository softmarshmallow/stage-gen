# Iron Petal Unit asset build

The runner owns its track, gameplay, avatar/boss content, effects, audio triggers and the
way its assets are built. The prepared source in `inputs/` keeps its original game ID and
file formats.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The game's folder is a gnode project. `gnode.yaml` names the routes, `gnode.lock` pins the
node types in `pipeline/nodes/`, and `pipeline/workflow.py:build` reads the package with the
game's own reader and writes one group of steps per asset. From the game's folder:

```sh
cd godot/games/iron_petal_unit
gnode plan pipeline/workflow.py:build --arg package=inputs
gnode run pipeline/workflow.py:build --arg package=inputs --live --max-usd 80 \
  --deliver package=../../../out/iron-petal/{key}
```

Planning is offline and spends nothing; `--live` is the explicit provider opt-in, and
launching the Godot project never generates assets. Runs land in `out/runs/iron-petal-unit/`
and the call cache in `out/gnode-cache/`, so a second run pays only for what changed.
`--deliver` copies the runtime package (every published file and `manifest.json`) out of
a successful run. Another package works the same way as long as it sits inside this
folder: its references are project files, read by content.

The installable Python source lives under `src/`. It depends on the public asset product
and the private shared game tools (the step families in `demo_game_tools.steps`). It does
not import another named game or the collection's developer CLI.

- `admission.py` holds what a painting must be to be admitted, and how a catalog sprite is
  trimmed; the judges and the publishing steps call the same functions.
- `manifest.py` owns the runtime projection of gameplay, audio, ground, calibration and
  the published validation records.
- `runner_prompts.py` compiles the art direction and every prompt the builder sends.

See the [runner doc](../docs/runner.md) for the steps and the checked plan contract, and the
[Python dependency review](../../../docs/python-dependencies.md) for the remaining private
Stage Gen calls.
