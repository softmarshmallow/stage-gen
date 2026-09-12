# Legacy game tools

These commands maintain preserved demo inputs and their historical gameplay contracts. They
are not required to author or run a new asset pipeline. Run them from the repository root with
the Stage Gen Python environment; commands that import historical builders add the explicit
legacy source directory to their process only.

| Tool | Owner and purpose |
| --- | --- |
| `write_contract_identities.py` | Derived census of legacy demo contract identities |
| `write_model_policy_snapshot.py` | Full historical demo model-policy snapshot |
| `author_terrain.py` | Platformer-specific terrain/ladder authoring against the demo camera and traversal rules |
| `design_map.py` | Platformer map design, validation, rendering, and compilation against the legacy traversal profile |
| `validate_game_package.py` | Historical selected game-input closure validation |
| `write_oblique_survival_cache_keys.py` | Ember Hollow cache-key golden maintenance |
| `write_pipeline_graph_contract.py` | Historical platformer, runner, survival, and Ember Hollow storefront graph snapshots |
| `godot_parity_diff.py` | Comparison of preserved runtime parity traces |
| `prove_climbable_bands.py` | Legacy platformer ladder-band geometry proof |
| `render_asset_scale_figures.py` | Documentation figures derived from a legacy platformer package |

Each script supports `--help`. Read-only checks remain offline. Explicit live generation options
on map-design tools retain their existing opt-in requirements. A `--write` option changes a
maintained snapshot and should be used after reviewing the reason for that change.

The neutral document-block helpers and universe graph snapshot writer remain in
`scripts/write_pipeline_graph_contract.py`. Their continued use does not import these gameplay
builders or make a game fixture part of the product contract.
