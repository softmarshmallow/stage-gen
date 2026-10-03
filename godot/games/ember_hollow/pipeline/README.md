# Ember Hollow asset build

The survival game owns its asset build, world layout, game shell and manifest adaptation.
Its authored source stays in `inputs/`.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The game's folder is a gnode project. `gnode.yaml` names the routes, `gnode.lock` pins the
node types in `pipeline/nodes/`, and `pipeline/workflow.py:build` reads the package with the
game's own reader and writes one group of steps per asset, at one rung of the scope ladder
(`minimal`, `props`, `actors`, `full`; the default is `full`). From the game's folder:

```sh
cd godot/games/ember_hollow
gnode plan pipeline/workflow.py:build --arg package=inputs --arg scope=minimal
gnode run pipeline/workflow.py:build --arg package=inputs --arg scope=full --live \
  --max-usd 40 --deliver package=../../../out/ember-hollow/{key}
```

Planning is offline and spends nothing; `--live` is the explicit provider opt-in, and
launching the Godot project never generates assets. Runs land in `out/runs/` and the call
cache in `out/gnode-cache/`, so a second run pays only for what changed. `--deliver`
copies the folder the host plays (`package/`, `ui/`, `shell/`, the review records and
`manifest.json`) out of a successful build. A package must sit inside this folder: its
references and takes are project files, read by content. The opening's clips publish
through an ffmpeg built with libtheora: set `GNODE_TOOL_FFMPEG_THEORA` to it (Homebrew's
`ffmpeg@7` has it).

The auditioned takes the package adopts are first-party media kept beside the package,
not in git. A build that reaches a missing one refuses that step and names the take.

The installable Python source lives under `src/`. It depends on the public asset product
and the private shared game tools (the step families in `demo_game_tools.steps`). It does
not import another named game or the collection's developer CLI.

- `build.py` names every gate and finish the build's steps call, and keeps each record in
  the shape the manifest reads.
- `anchor.py` is the anchor episode's words, picture, admission and record.
- `reviews.py` is a family review's answer and its coherence rule.
- `gates.py`, `templates.py`, `preparation_media.py` and `layout.py` are the pixel gates,
  the paintover lattices, the seasonal and review rasters, and the world generator.
- `manifest.py` owns the runtime document.

See [the generation document](../docs/generation-v1.md) for the steps and the checked plan
contract, and the [Python dependency review](../../../docs/python-dependencies.md) for the
remaining private Stage Gen calls and their ownership decisions.
