# Bellweather asset build

Scenario preparation uses the private `demo_game_tools.scenario` adapter over
the independent Godot-owned authoring package. Existing v2 source, production
metadata and prepared bytes remain supported; playback uses Scenario's single
Session executor through its compatibility reader. Compilation does not generate
media and is separate from the asset build described below.

The platformer owns its maps, gameplay input reader, manifest adapter and the way its
assets are built. `inputs/default` and `inputs/waves` are complete separate packages.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The game's folder is a gnode project. `gnode.yaml` names the routes, `gnode.lock` pins the
node types in `pipeline/nodes/`, and `pipeline/workflow.py:build` reads a package with the
game's own reader and writes one group of steps per asset. From the game's folder:

```sh
cd godot/games/bellweather
gnode plan pipeline/workflow.py:build --arg package=inputs/default
gnode run pipeline/workflow.py:build --arg package=inputs/default --live --max-usd 175 \
  --deliver package=../../../out/bellweather/{key}
```

Planning is offline and spends nothing; `--live` is the explicit provider opt-in, and
launching the Godot project never generates assets. Runs land in `out/runs/bellweather/`
and the call cache in `out/gnode-cache/`, so a second run pays only for what changed.
`--arg part=world`, `content` or `soundtrack` builds one part and outputs its files;
`--arg reviews=no` leaves the reviews out. `--deliver` copies the runtime package (every
published file and `manifest.json`) out of a successful whole build. Another package works
the same way as long as it sits inside this folder: its references are project files, read
by content.

The installable Python source lives under `src/`. It depends on the public asset product
and the private shared game tools (the step families in `demo_game_tools.steps`). It does
not import another named game or the collection's developer CLI.

- `briefs.py` writes every brief the build sends a model and the shape of every review.
- `assets.py` holds the pixel gates, the repacks and the review boards; the judges and the
  publishing steps call the same functions.
- `bindings.py` resolves the gameplay and scenario bindings and the coverage matrix.
- `prepared_manifest.py` owns the runtime closure and the manifest the Godot host reads.

See [the pipeline doc](../docs/generation-pipeline.md) for the steps and the checked plan
contract.
