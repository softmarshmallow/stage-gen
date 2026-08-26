# Canonical game library

`main.toml` is the single promotion point for the repository's bundled demo game. It selects one
digest-bound prepared package by its root `game.toml`; that root catalogs and locks the complete
authored source closure.

- Only one designated curator may edit the selected canonical closure at a time.
- Concurrent experiments must copy the closure to
  `spikes/game-forks/<owner>-<slug>/`, preserving the relative `library/` and `examples/` layout
  and using an isolated `out/` directory.
- Forks must contain real copies, never symlinks into the canonical closure. Fork metadata and
  generated outputs are never promoted.
- Promotion changes `main.toml` or its selected closure deliberately and re-locks every edited
  digest. Never migrate, infer, or preserve an old schema; update the complete package to the exact
  current schema or drop it.
- Prepared packages contain root `game.toml` and `gameplay.toml`, map generation sources, content
  catalogs, sequences, soundtrack direction, narrative source, and explicitly referenced evidence.
  They do not depend on an examples request wrapper or `maps/index.toml`.
- Prepared image inputs carry their exact digest and inline origin/rights basis in the authored
  contract, with digest-bound semantic review. Do not add `.meta.json`, `.source.meta.json`, or
  `.LICENSE.md` sidecars; generated outputs may retain operational provenance under their own
  artifact contracts.
- Until the breaking package resolver lands, validate the authored closure structurally: parse
  every TOML, confine every path, verify every declared digest and cross-reference, and reject
  unknown files. Do not run the legacy package validator and misreport its expected schema failure
  as an input defect.
