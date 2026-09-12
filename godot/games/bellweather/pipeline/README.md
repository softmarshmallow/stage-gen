# Bellweather asset preparation

The platformer owns the existing world/content graph, maps, gameplay input reader and manifest adapter. `inputs/default` and `inputs/waves` are complete separate variants.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The discoverable script selects this game's own inputs. Its default is offline:

```sh
uv run --group games python godot/games/bellweather/pipeline/prepare.py
```

Exercise scheduling and artifact contracts with deterministic fake operations:

```sh
uv run --group games python godot/games/bellweather/pipeline/prepare.py --dry-run --output out/bellweather-smoke
```

Use `--variant waves` to prepare the Waves variant. Paid generation remains bounded
by the existing checkpoints:

```sh
uv run --group games python godot/games/bellweather/pipeline/prepare.py --live --checkpoint world --output out/bellweather-world
uv run --group games python godot/games/bellweather/pipeline/prepare.py --live --checkpoint content --output out/bellweather-content
```

Restore validated cached artifacts and assemble a runtime manifest without calling providers:

```sh
uv run --group games python godot/games/bellweather/pipeline/prepare.py --checkpoint integration --output out/bellweather-integration --assets-output out/bellweather-prepared
```

Select an existing cache with `--cache-dir`. The integration step refuses missing
artifacts; a successful fake dry run does not populate playable media.

`--input` explicitly overrides the game-local source. Output directories are
explicit and must be new. Existing TOML values, node identities, cache namespaces
and validated asset bytes retain their meaning. Gameplay consumes the resulting
assets through this game's Godot scripts.

The installable Python source lives under `src/`. It depends on the public asset
product and the private shared game input/media tools. It does not import another
named game or the collection's developer CLI.
