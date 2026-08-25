# Canonical game package

The repository ships one authored-source demonstration selected by
[`library/games/main.toml`](../library/games/main.toml). That selector is the
single source of truth for which game request CI, tests, future hosted demos,
and release tooling should validate.

The selector does not embed a game. It digest-locks one scrolling-preview
request, and that request binds the game-owned sources:

```text
library/games/main.toml
└── examples/scrolling-preview/game-directed-village.toml
    ├── library/games/whimsical-storybook-fantasy/game.toml
    ├── library/games/whimsical-storybook-fantasy/soundtrack.toml
    └── library/games/whimsical-storybook-fantasy/maps/index.toml
        ├── maps/village-hub.toml
        ├── maps/stage-1-approach.toml
        ├── maps/stage-2-gauntlet.toml
        └── maps/stage-3-spires.toml
```

The soundtrack is game-global. Each map owns only its ordered pool of allowed
track IDs. This keeps track identity and generation intent independent from map
identity while allowing map-aware playback.

## Current-only policy

Only the versions implemented by the live models are accepted:

- selector `game-package-v1`;
- request `contract_version = 2`;
- `game-contract-v3`;
- `game-soundtrack-v1`;
- `game-map-book-v1` containing only `game-map-v2` sources; and
- scrolling manifest envelope V7 with soundtrack and map-book projection V2.

These independently versioned identities do not imply support for earlier
versions. When an authored schema changes, update or regenerate the canonical
package and drop stale development games. Validators never upgrade or infer old
contracts.

Optional recipe systems remain optional in general. The selector's
`required_features` list makes the canonical demo stricter: every selected
feature must be present and valid.

## Validation

Validate authored sources without consulting Git state:

```sh
uv run python scripts/validate_game_package.py --root .
```

Before committing or serving the canonical demo, require every closure byte to
match `HEAD`:

```sh
uv run python scripts/validate_game_package.py --root . --require-committed
```

The JSON report distinguishes three independent states:

- `source_status` proves the authored closure is current and internally valid;
- `repository.status` reports whether those exact bytes are committed; and
- `generated_status` reports generated-demo freshness.

`generated_status = "not_checked"` is not a successful generation claim. The
authored package can be valid while generated output is absent, stale,
unreviewed, or unpublished.

The validator fails closed for an invalid selector or request digest, missing
required feature, old schema, symlink or path escape, cross-game identity,
unknown soundtrack reference, stale map lock, orphan TOML source, untracked
closure source, or committed-byte mismatch.

## Authoring workflow

1. Edit one current authored source.
2. If a map changed, update its SHA-256 in `maps/index.toml`.
3. Update the changed binding SHA-256 in the selected request.
4. If the request changed, update `request_sha256` in `library/games/main.toml`.
5. Run the validator with `--require-committed` after committing.

Use the public commands for a focused authored source:

```sh
uv run stage-gen game validate --input library/games/whimsical-storybook-fantasy/game.toml --game-library-root .
uv run stage-gen soundtrack validate --input library/games/whimsical-storybook-fantasy/soundtrack.toml --game-library-root .
uv run stage-gen map validate --input library/games/whimsical-storybook-fantasy/maps/village-hub.toml --game-library-root .
uv run stage-gen map-book validate --input library/games/whimsical-storybook-fantasy/maps/index.toml --game-library-root .
```

Each command also provides `digest`. Validation and digest both resolve the
complete relevant source boundary; `map-book digest` therefore rejects a stale
locked map instead of merely hashing `index.toml`.

## Ownership and publication

Python under `src/stage_gen/` owns the contract, resolver, producer, and package
validator. `web/` is an optional consumer and is not schema authority.

The canonical authored package is intended to be Git-tracked. Generated audio,
images, archives, and hosted-demo activation remain separate publication
decisions governed by rights review, storage limits, semantic verification, and
explicit authorization.
