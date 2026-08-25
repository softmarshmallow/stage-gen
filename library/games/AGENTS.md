# Canonical game library

`main.toml` is the single promotion point for the repository's bundled demo game. It selects one
recipe request; the digest-bound request and its game directory form the complete authored source
closure.

- Only one designated curator may edit the selected canonical closure at a time.
- Concurrent experiments must copy the closure to
  `spikes/game-forks/<owner>-<slug>/`, preserving the relative `library/` and `examples/` layout
  and using an isolated `out/` directory.
- Forks must contain real copies, never symlinks into the canonical closure. Fork metadata and
  generated outputs are never promoted.
- Promotion changes `main.toml` or its selected closure deliberately and re-locks every edited
  digest. Never migrate or silently rewrite an old schema; update it to the exact current schema
  or drop it.
- Validate source closure with
  `uv run python scripts/validate_game_package.py --root .`. Add `--require-tracked` to require
  Git membership, and `--require-committed` before publication or deployment to prove that the
  validated bytes exactly match `HEAD`.
