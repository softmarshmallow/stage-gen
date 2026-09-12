# The Grain asset preparation

The investigation game owns its case bindings, room builder and dialogue builder. These are parts of this game, not a canonical game contract for the asset SDK.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The discoverable script selects this game's own inputs. Its default is offline:

```sh
uv run --group games python godot/games/the_grain/pipeline/prepare.py
```

The default command proves the `episode_one` case and its room/scenario bindings
offline. It does not write a run. Select an individual asset composition with:

```sh
uv run --group games python godot/games/the_grain/pipeline/prepare.py --mode room --room window
uv run --group games python godot/games/the_grain/pipeline/prepare.py --mode dialogue
```

Either asset mode supports `--dry-run --output RUN_DIR` or an explicit
`--live --output RUN_DIR`. The dialogue input owns the scenario selection.

After preparing every case beat, assemble the game-owned case document with
`--bundle --beat-run BEAT_ID=RUN_TAG` for each beat, `--output CASE_DIR` and an
explicit `--runs-dir` when the runs are outside the output's parent. The check
requires the exact beat set and existing run directories.

`--input` explicitly overrides the game-local source. Output directories are
explicit and must be new. Existing TOML values, node identities, cache namespaces
and validated asset bytes retain their meaning. Gameplay consumes the resulting
assets through this game's Godot scripts.

The installable Python source lives under `src/`. It depends on the public asset
product and the private shared game input/media tools. It does not import another
named game or the collection's developer CLI.
