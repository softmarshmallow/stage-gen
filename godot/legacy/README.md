# Legacy demo workspace

This directory owns the former canonical game system. It is retained so existing
demos and authored TOML inputs continue to work. It does not define how a user must
build an asset pipeline or a new game.

```text
legacy/
├── inputs/                  # Existing demo inputs and selected-package TOML
├── python/
│   └── stage_gen_legacy/
│       ├── components/      # Game rules, aggregates and contract readers
│       ├── recipes/         # Five complete demo generation recipes
│       ├── orchestration/   # Demo package selection, capture and case binding
│       ├── interfaces/      # Legacy command family
│       └── application/     # Demo-specific application helpers
├── runtime/                 # Existing Godot hosts and their regression suite
└── tools/                   # Demo authoring and contract maintenance utilities
```

Install the optional Python workspace with `uv sync --group legacy`. Use
`stage-gen legacy ...` or `stage-gen-legacy ...`; for example:

```sh
uv run --group legacy stage-gen legacy package plan --input godot/legacy/inputs/bellweather --genre platformer
uv run --group legacy python scripts/check.py --scope legacy
```

The old prepared-package commands accept a directory or ZIP whose root contains `game.toml`. Their `--dry-run` path uses deterministic fake operations. There is no bare-prompt fallback. A live package run without `--dry-run` fails before provider
work when its old prepared-input closure is invalid. These are legacy command rules,
not the public asset harness's input format.

[Game contract](../../docs/game-contract.md),
[package](../../docs/game-package.md), and
[host contract](../../docs/spec/game/host-contract.md) describe these demos only.
New games should own a local preparation script, GDScript and scenes under their
Godot project, using public asset components and recipes as needed.

Maintain compatibility here without rewriting every existing TOML. Extract a useful
capability into the product only after its inputs, outputs and validation can stand
alone; keep demo adapters importing that capability. Never import this package from
the product. Existing generated media retains its rights and review status.
