# Ember Hollow asset preparation

The survival game owns its generation graph, world layout, game shell and manifest adaptation. Its authored source stays in `inputs/`.

Install the optional game tools from the repository root:

```sh
uv sync --group games
```

The discoverable script selects this game's own inputs. Its default is offline:

```sh
uv run --group games python godot/games/ember_hollow/pipeline/prepare.py
```

Exercise scheduling and artifact contracts with deterministic fake operations:

```sh
uv run --group games python godot/games/ember_hollow/pipeline/prepare.py --dry-run --output out/ember_hollow-smoke
```

Use `--scope` to select an existing bounded survival generation scope. The default
is `full`. Use `--live --output out/ember-hollow-assets` for an explicitly authorized
provider run.

`--input` explicitly overrides the game-local source. Output directories are
explicit and must be new. Existing TOML values, node identities, cache namespaces
and validated asset bytes retain their meaning. Gameplay consumes the resulting
assets through this game's Godot scripts.

The installable Python source lives under `src/`. It depends on the public asset
product and the private shared game input/media tools. It does not import another
named game or the collection's developer CLI.

`preparation_media.py` owns deterministic seasonal alignment, review rasters and
biome gate policy; `cache_admission.py` owns restored-image canvas checks.
`manifest.py` continues to own the runtime document. The preparation handler
composes these operations and retains provider execution and publication.
See the [Python dependency review](../../../docs/python-dependencies.md) for the
remaining private Stage Gen calls and their ownership decisions.
