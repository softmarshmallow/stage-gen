# Canonical prepared game package

> **Implementation status:** exact-current package validation, prepared execution,
> provider-free integration, and prepared runtime consumption are implemented.
>
> Directory and ZIP ingestion, contract parsing, digest closure, media decoding,
> cross-contract validation, repository selection, both typed scrolling DAGs, and
> `prepared-game-runtime-v12` / `sideview-runner-runtime-v13` assembly are executable.
> Successful package validation
> is still authored-input truth only; it does not prove that a live run completed,
> passed semantic review, is playable, or is approved for publication.

The canonical prepared package is selected by
[`library/games/main.toml`](../library/games/main.toml). The selector points
directly to one package-root `game.toml`; there is no examples request wrapper
or map-book index:

```text
library/games/main.toml
└── library/games/iron-petal-unit/game.toml
    ├── universe.md
    ├── runner/{gameplay,track,audio,soundtrack}.toml
    ├── runner/content/{avatar,props,items}.toml
    └── references/*
```

`game.toml` is the membership root. It names every direct contract and
evidence member by exact source path. Map and content contracts in turn name
the image references they actually use; the scenario catalog names every
scenario, and each scenario names the script it signs for. A named member that is absent is rejected; an unreferenced file is
rejected too, rather than becoming implicit input.

## Exact-current identities

Only these prepared-package identities are accepted by the resolver:

| Boundary | Current identity |
| --- | --- |
| Repository selector | `game-package-v4` |
| Package root | `game-contract-v9` |
| Runner gameplay | `runner-gameplay-v4` |
| Runner track | `runner-track-v4` |
| Runner avatar catalog | `runner-avatar-v3` |
| Runner audio | `runner-audio-v4` |
| Game voices | `game-voices-v1` |
| Gameplay | `gameplay-contract-v1` |
| Map generation | `game-map-v10` |
| Soundtrack | `game-soundtrack-v1` |
| UI | `game-ui-v4` |
| Player catalog | `player-content-v3` |
| Mob catalog | `mob-content-v2` |
| NPC catalog | `npc-content-v3` |
| Prop catalog | `prop-content-v2` |
| Item catalog | `item-content-v2` |
| Projectile catalog | `projectile-content-v2` (optional) |
| Scenario catalog | `scenario-catalog-v1` |
| Scenario | `scenario-v2` |

Successful provider-free integration of the platformer member emits
`prepared-game-runtime-v12`; a runner member's run emits
`sideview-runner-runtime-v13` from its own local manifest assembly.
Prepared consumers reject older or mixed runtime identities rather than translating them.

The resolver does not upgrade, translate, or infer another shape. In
particular, package ingest does not reconstruct a prompt request, `WorldSpec`,
`VillageSpec`, or map book.

## Directory and ZIP input

A package may be supplied directly as a directory:

```sh
uv run stage-gen package validate --input library/games/iron-petal-unit
uv run stage-gen package digest --input library/games/iron-petal-unit
```

Or as a ZIP whose archive root is the package itself or one wrapper directory
named for the game:

```sh
uv run stage-gen package validate --input /path/to/iron-petal-unit.zip
uv run stage-gen package digest --input /path/to/iron-petal-unit.zip
```

Both forms capture every closure byte once and produce the same
`closure_sha256`, canonical game digest, stable IDs, and file identities.
Later stages consume that captured closure rather than reopening mutable input
or retaining a temporary extraction path.

The directory, ZIP filename, and optional ZIP wrapper are transport names and
do not determine game identity. `game_id` comes only from the validated root
contract. `package_sha256` is the SHA-256 of the exact root `game.toml` bytes.
Membership is by exact source path, and the resolver hashes every captured
member itself at ingest, so editing a member needs no digest bookkeeping
elsewhere in the package. `closure_sha256` digests the exact captured closure:
every member path, its digest, and its byte size. `stage-gen package digest`
prints it.

## Pre-provider validation

Resolution is local and provider-free. Before it returns a package it verifies:

- strict TOML parsing and exact unknown-field rejection;
- the root game identity and every member schema identity;
- every authored evidence and image-reference digest against captured bytes;
- shared `game_id` ownership;
- map, actor, item, prop, UI, soundtrack, quest, effect, and scenario references;
- map layer ordering, alpha base, ground mode, binary occupancy, ladder geometry,
  portal endpoint support, and complete reference closure;
- content state, facing, expression, and reference closure;
- scenario admission: label reachability, reachable endings, declared cast,
  stages and flags, and the script digest, proven before any spend;
- the cast and expressions a scenario names against the actors this game can
  draw, and each interaction's bound outcomes and effects;
- image decoding for every selected visual reference;
- JSON syntax for selected evidence provenance and nonempty UTF-8 review text;
- exact closure membership, rejecting both a missing member and an
  unreferenced file; and
- portable paths with no traversal, symlink, ambiguous archive root, duplicate
  ZIP entry, encryption, or unsafe size/compression behavior.

The resolver imports no provider or composed runtime module, and the one recipe
module it composes per genre (`recipes/<recipe>/validation.py`) is held to the
same rule by a contract test. A malformed package therefore cannot perform a
paid operation.

`resolve_prepared_package` is the genre-neutral capture boundary and accepts a
runner-only root or a platformer-containing root. `resolve_game_package` is the
explicitly platformer-required narrowing used by that recipe. The runner recipe
resolves its own member from the common captured package; it does not require or
manufacture a dummy platformer member.

## Actor motion and playback ownership

Player, mob, and NPC content owns the runtime presentation of every declared motion. A motion
entry names its semantic `state`, `playback_mode`, ordered `canonical_frame_indices`, and—only for
timeline playback—`frames_per_second`. Supported modes are `hold`, `loop`, `once`, and
`gameplay_driven`. The player climb states `climb_ladder` and `climb_rope` are the only
current gameplay-driven states. A motion may also declare `anchor`, which is `bottom` or `top` and
defaults to `bottom`: it selects which edge of its cell the motion's frames register against.

Registration is authored where facing is not, and the difference is that facing is knowable before
generation while registration is not. Facing follows from the camera and is decided up front; the
anchor depends on what the model actually drew - whether a climb tucked to hip height or to the
chest, whether the feet left the bounding box's extreme - so it needs a knob at the point where a
human has seen the output. A grounded actor registers on its feet; one hanging from its hands does
not, and registering it on its feet pins them and swings its head instead.

This authored playback contract does not control provider sampling. The scrolling recipe currently
requests four candidate poses for every motion state except the player climbs, which request two,
validates and repacks that many canonical frames, then projects the authored selection into the
runtime manifest. A player idle may therefore hold
canonical frame zero while generation still benefits from a regular four-pose request. Playback
changes must not invalidate concept, motion, contact-sheet, or semantic-review cache identity.

The NPC catalog alone owns a catalog-wide `world_orientation`; its current exact value is
`front`. Each NPC uses the same `motions` vocabulary as players and mobs. Bellweather keeps one
authored `idle` motion with `playback_mode = "hold"` and `canonical_frame_indices = [0]`: the
provider and canonicalizer still produce four front-facing candidates, while runtime presentation
holds frame zero without installing a timeline animation. Front-facing NPC sources are never
horizontally mirrored.

For the current side-view package, gameplay movement `crouch` and player motion `crouch` are two
linked but separately owned declarations. Gameplay owns posture permission and mechanics; player
content owns the generated visual. V1 requests four samples of one stationary, feet-planted low
crouch and plays them as a 6 fps loop. It does not accept `crawl` as an alias. A canonical prepared
build publishes `content/players/<player_id>/states/crouch.png`; a consumer may diagnose and show a
visible fallback for incomplete presentation without disabling crouch mechanics.

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

The `game-package-validation-v6` report keeps authored, repository, and
generated truth separate:

- `source_status = "current"` means the complete prepared closure validates;
- `repository.status` reports whether those exact bytes are tracked or committed;
- `generated_status = "not_checked"` means generation and playability have not
  been claimed; and
- `package_sha256`, `closure_sha256`, and `closure` identify the validated
  bytes.

An internally valid package may still have absent, stale, unreviewed, or
unpublished generated output. Validation never promotes media or activates a
consumer.

## Ownership

Python under `src/stage_gen/` owns package contracts and resolution. The
scrolling recipe owns generation from the resolved closure, and `web/`
is a consumer of the resulting public manifest. Neither recipe nor
consumer may reinterpret missing authored direction.

The [canonical generation pipeline](spec/game/generation-pipeline.md) owns the
execution graph. The [map-generation contract](spec/game/map-generation-contract.md)
owns one map's visual inputs, layers, continuity, binary terrain, ladder
geometry and placement, portal presentation and anchors, and review unit.
`gameplay.toml` alone owns map use, movement permissions, transition
relationships, spawning, encounters, loot, placements, interactions, quests,
and effects.
Root `ui.toml` owns generated interface presentation only; its current inventory
panel contract is specified in [Authored game UI](spec/game/ui.md).

## Not a game package

`library/games/<id>/universe.toml` is a package root of its own kind, read by
the [universe recipe](spec/universe/generation-v1.md). It is never a member of
a `game.toml` closure: [universe taxonomy V0](spec/universe/taxonomy-v0.md)
declines to ratify that question, and the selected prepared-game closure must
not carry universe-only files. The two roots sit side by side under
`library/games/` and are resolved by different code.
