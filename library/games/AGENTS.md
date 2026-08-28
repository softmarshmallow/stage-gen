# Canonical game library

`main.toml` is the single promotion point for the repository's bundled demo game. It selects one
prepared package by the exact path of its root `game.toml`; that root names the complete authored
source closure by exact source path.

- Only one designated curator may edit the selected canonical closure at a time.
- Concurrent experiments must copy the closure to
  `spikes/game-forks/<owner>-<slug>/`, preserving the relative `library/` and `examples/` layout
  and using an isolated `out/` directory.
- Forks must contain real copies, never symlinks into the canonical closure. Fork metadata and
  generated outputs are never promoted.
- Promotion changes `main.toml` or its selected closure deliberately and keeps the member path list
  exact. Never migrate, infer, or preserve an old schema; update the complete package to the exact
  current schema or drop it.
- Prepared packages contain root `game.toml` and `gameplay.toml`, map generation sources, content
  catalogs, sequences, soundtrack direction, narrative source, and explicitly referenced evidence.
  They do not depend on an examples request wrapper or `maps/index.toml`.
- Authors name members by exact source path and never record member digests; ingest computes every
  member digest at capture, plus `closure_sha256` over the captured closure. The resolver rejects a
  missing member (`missing_package_file`) and an unreferenced file (`orphan_package_file`), so the
  closure stays exact without being pinned in the authored text.
- Prepared image inputs carry their exact digest and inline origin/rights basis in the authored
  contract, with digest-bound semantic review. Those reference digests and the `evidence` digests
  are the only digests an author records by hand, and they bind an acceptance verdict and a rights
  claim to exact reviewed bytes. Do not add `.meta.json`, `.source.meta.json`, or `.LICENSE.md`
  sidecars; generated outputs may retain operational provenance under their own artifact
  contracts.
- Validate the authored closure from the repository root with
  `uv run python scripts/validate_game_package.py --root .`. It parses every TOML, confines every
  path, checks exact path membership, verifies the authored evidence and reference digests, resolves
  every cross-reference, and rejects orphaned files.
