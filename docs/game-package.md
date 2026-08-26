# Canonical prepared game package

> **Implementation status:** exact-current package validation is implemented.
>
> Directory and ZIP ingestion, contract parsing, digest closure, media decoding,
> cross-contract validation, and repository selection are executable. Provider
> scheduling and generation from the resolved package remain the next pipeline
> checkpoint; successful package validation is not a generation claim.

The canonical prepared package is selected by
[`library/games/main.toml`](../library/games/main.toml). The selector points
directly to one package-root `game.toml`; there is no examples request wrapper
or map-book index:

```text
library/games/main.toml
└── library/games/bellweather/game.toml
    ├── universe.md
    ├── gameplay.toml
    ├── soundtrack.toml
    ├── maps/<map_id>.toml
    ├── content/{player,mobs,npcs,props,items}.toml
    ├── sequences/index.toml
    ├── sequences/<sequence_id>.toml
    └── references/*
```

`game.toml` is the membership and digest-closure root. It locks every direct
contract and evidence member. Map and content contracts in turn lock the image
references they actually use; the sequence catalog locks every sequence.
Unreferenced files are rejected rather than becoming implicit input.

## Exact-current identities

Only these prepared-package identities are accepted by the resolver:

| Boundary | Current identity |
| --- | --- |
| Repository selector | `game-package-v2` |
| Package root | `game-contract-v4` |
| Gameplay | `gameplay-contract-v1` |
| Map generation | `game-map-v3` |
| Soundtrack | `game-soundtrack-v1` |
| Player catalog | `player-content-v1` |
| Mob catalog | `mob-content-v1` |
| NPC catalog | `npc-content-v1` |
| Prop catalog | `prop-content-v1` |
| Item catalog | `item-content-v1` |
| Sequence catalog | `game-sequence-catalog-v1` |
| Sequence | `game-sequence-v1` |

The resolver does not upgrade, translate, or infer another shape. In
particular, package ingest does not reconstruct a prompt request, `WorldSpec`,
`VillageSpec`, or map book.

## Directory and ZIP input

A package may be supplied directly as a directory:

```sh
uv run stage-gen package validate --input library/games/bellweather
uv run stage-gen package digest --input library/games/bellweather
```

Or as a ZIP whose archive root is the package itself or one wrapper directory
named for the game:

```sh
uv run stage-gen package validate --input /path/to/bellweather.zip
uv run stage-gen package digest --input /path/to/bellweather.zip
```

Both forms capture every closure byte once and produce the same
`package_sha256`, canonical game digest, stable IDs, and file identities.
Later stages consume that captured closure rather than reopening mutable input
or retaining a temporary extraction path.

The directory, ZIP filename, and optional ZIP wrapper are transport names and
do not determine game identity. `game_id` comes only from the validated root
contract. `package_sha256` is the SHA-256 of the exact root `game.toml` bytes.
That root locks the rest of the closure, so changing any member requires
relocking its owner and then relocking the root selector as applicable.

## Pre-provider validation

Resolution is local and provider-free. Before it returns a package it verifies:

- strict TOML parsing and exact unknown-field rejection;
- the root game identity and every member schema identity;
- every locked source digest;
- shared `game_id` ownership;
- map, actor, item, prop, soundtrack, quest, effect, and sequence references;
- map layer ordering, alpha base, ground mode, and reference closure;
- content state, facing, expression, and reference closure;
- sequence node reachability, targets, outcomes, speakers, expressions, and effects;
- image decoding for every selected visual reference;
- JSON syntax for selected evidence provenance and nonempty UTF-8 review text;
- exact closure membership with no orphan file; and
- portable paths with no traversal, symlink, ambiguous archive root, duplicate
  ZIP entry, encryption, or unsafe size/compression behavior.

The resolver imports no provider, recipe, or composed runtime module. A
malformed package therefore cannot perform a paid operation.

## Canonical repository validation

Validate the repository-selected package without consulting provider state:

```sh
uv run python scripts/validate_game_package.py --root .
```

Before committing or serving the canonical package, require its exact closure
to be tracked and equal to Git `HEAD`:

```sh
uv run python scripts/validate_game_package.py --root . --require-committed
```

The report keeps authored, repository, and generated truth separate:

- `source_status = "current"` means the complete prepared closure validates;
- `repository.status` reports whether those exact bytes are tracked or committed;
- `generated_status = "not_checked"` means generation and playability have not
  been claimed; and
- `package_sha256` and `closure` identify the validated bytes.

An internally valid package may still have absent, stale, unreviewed, or
unpublished generated output. Validation never promotes media or activates a
consumer.

## Ownership

Python under `src/stage_gen/` owns package contracts and resolution. The
scrolling recipe will own generation from the resolved closure, and `web/`
will remain a consumer of the resulting public manifest. Neither recipe nor
consumer may reinterpret missing authored direction.

The [canonical generation pipeline](spec/game/generation-pipeline.md) owns the
execution graph. The [map-generation contract](spec/game/map-generation-contract.md)
owns one map's visual inputs, layers, continuity, ground, and review unit.
`gameplay.toml` alone owns map use, spawning, transitions, encounters, loot,
placements, interactions, quests, and effects.
