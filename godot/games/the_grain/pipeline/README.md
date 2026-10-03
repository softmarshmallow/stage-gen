# The Grain asset build

Scenario preparation uses the private `demo_game_tools.scenario` adapter over
the independent Godot-owned authoring package. Existing v2 source, production
metadata and prepared bytes remain supported; playback uses Scenario's single
Session executor through its compatibility reader. Compilation does not generate
media and is separate from the asset build described below.

The investigation game owns its case bindings, room builder and dialogue builder. These
are parts of this game, not a canonical game contract for the asset SDK.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The game's folder is a gnode project. `gnode.yaml` names the routes, `gnode.lock` pins the
node types in `pipeline/nodes/`, and `pipeline/workflow.py` holds two builders: `room` reads
one room package and `scene` reads the dialogue scene, each with the game's own reader.
From the game's folder:

```sh
cd godot/games/the_grain
gnode plan pipeline/workflow.py:room --arg package=inputs/rooms/window
gnode plan pipeline/workflow.py:scene --arg package=inputs
gnode run pipeline/workflow.py:room --arg package=inputs/rooms/window --live --max-usd 25 \
  --deliver package=../../../out/the-grain-window/{key}
gnode run pipeline/workflow.py:scene --arg package=inputs --live --max-usd 150 \
  --deliver package=../../../out/the-grain-scene/{key}
```

Planning is offline and spends nothing; `--live` is the explicit provider opt-in, and
launching the Godot project never generates assets. Runs land in `out/runs/` and the call
cache in `out/gnode-cache/`, so a second run pays only for what changed. `--deliver` copies
the folder the host plays (every published file and the room's `manifest.json` or the
scene's `bundle.json`) out of a successful build. A package must sit inside this folder:
its references are project files, read by content.

The case is not generated. `pipeline/prepare.py` proves the `episode_one` case and its
room and scenario bindings offline:

```sh
uv run --group games python godot/games/the_grain/pipeline/prepare.py
```

After building every beat's room or scene, publish the case document with
`--bundle --beat-run BEAT_ID=RUN_TAG` for each beat and `--output CASE_DIR`, plus
`--runs-dir` when the delivered folders are outside the output's parent. The check
requires the exact beat set and existing delivered folders. `--input` overrides the
game-local source.

The installable Python source lives under `src/`. It depends on the public asset product
and the private shared game tools. It does not import another named game or the
collection's developer CLI.

- `style.py` asks for one approved style mode and turns the answer into the anchor and
  its per-kind clauses.
- `pointclick_room/` reads and proves a room, writes its briefs, and holds the room's
  image gate, narration check and the manifest the Godot host reads.
- `dialogue_scene/` reads and proves the scene, writes its briefs and plans, and holds
  its image gate, sprite finishing and the bundle the Godot host reads.
- `case_binding.py` and `case_bundle.py` prove the case and publish it.

See [the room doc](../docs/pointclick-room.md) and
[the scene doc](../docs/dialogue-scene-assets.md) for the steps and the checked plan
contracts.
