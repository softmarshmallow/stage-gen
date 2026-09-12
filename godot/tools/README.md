# Godot workspace tools

These tools maintain the collection of games and independent Godot packages.
They are optional consumers of the asset product. Install `uv sync --group games`
for commands that import game preparation packages.

| Tool | Responsibility |
| --- | --- |
| `check.py` | Coordinate every maintained owner with explicit offline, prepared-media and native-rendering coverage |
| `check_suites.py` | Declare suite execution conventions and enforce complete discovery |
| `run_native_suite.py` | Run native regression suites in their owning game or shared-support project |
| `write_game_contract_identities.py` | Derive the identity census from the game readers |
| `write_game_model_policy_snapshot.py` | Maintain the game collection's routing snapshot |
| `write_game_graph_contract.py` | Maintain game build-graph snapshots |
| `package_game_project.py` | Assemble a game with real addon source and no inputs or generated output |
| `parity_diff.py` | Compare deterministic runtime traces |
| `unused_assets.py` | Report tracked game media or catalogs unreachable from source and catalogs |
| `python/src/demo_game_collection/` | The optional `demo-games` CLI and cross-game inspection |

Game-specific tools live with the game. Bellweather owns map/terrain authoring,
ladder proofs and platformer capture. Ember Hollow owns survival fixtures and cache
goldens. Iron Petal Unit and The Grain own their captures and parity scripts.
Collection input validation lives at
[`validate_game_package.py`](validate_game_package.py), with an explicit `--input` root.

Run the credential-free Godot checks from this workspace:

```sh
cd godot
../.venv/bin/python tools/check.py
../.venv/bin/python tools/check.py --list
../.venv/bin/python tools/check.py --owner command_link --only manpu_loop_checks
```

The [verification guide](../docs/verification.md) owns coverage, prerequisite
reporting and the opt-in commands for prepared media and native rendering. The
default summary lists deferred suites explicitly; it is an offline verdict.

Each script supports `--help`. Read-only checks remain offline. A `--write` option
updates a maintained snapshot; provider-backed authoring retains explicit opt-in.
The neutral document-block helpers and independent universe graph writer remain
in [`scripts/write_pipeline_graph_contract.py`](../../scripts/write_pipeline_graph_contract.py).
