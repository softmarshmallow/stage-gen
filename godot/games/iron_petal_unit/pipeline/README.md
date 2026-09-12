# Iron Petal Unit asset preparation

The runner owns its track, gameplay, avatar/boss content, effects, audio triggers and runner generation graph. The prepared source in `inputs/` retains its original game ID and file formats.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The discoverable script selects this game's own inputs. Its default is offline:

```sh
uv run --group games python godot/games/iron_petal_unit/pipeline/prepare.py
```

Exercise scheduling and artifact contracts with deterministic fake operations:

```sh
uv run --group games python godot/games/iron_petal_unit/pipeline/prepare.py --dry-run --output out/iron_petal_unit-smoke
```

To generate through configured providers, use `--live --output out/iron-petal-assets`.
The `--live` flag is the explicit provider opt-in; launching the Godot project never
generates assets.

`--input` explicitly overrides the game-local source. Output directories are
explicit and must be new. Existing TOML values, node identities, cache namespaces
and validated asset bytes retain their meaning. Gameplay consumes the resulting
assets through this game's Godot scripts.

The installable Python source lives under `src/`. It depends on the public asset
product and the private shared game input/media tools. It does not import another
named game or the collection's developer CLI.
