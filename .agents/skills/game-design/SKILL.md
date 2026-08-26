---
name: game-design
description: Author or revise a prepared Stage Gen game-input package after its concept is selected. Use for canonical game, gameplay, map, content, sequence, and soundtrack contracts; not for pipeline implementation, runtime code, or exploratory concept work.
---

# Game Design

Author the input under `library/games/<game_id>/`. Read the repository
[`AGENTS.md`](../../../AGENTS.md) and [`library/games/AGENTS.md`](../../../library/games/AGENTS.md) first. For idea exploration or cover selection, use
[`game-concept-studio`](../game-concept-studio/SKILL.md) instead.

## Read the contract

Use these as the source of truth:

1. [Game package](../../../docs/game-package.md)
2. [Game contract](../../../docs/game-contract.md)
3. [Map generation contract](../../../docs/spec/game/map-generation-contract.md)
4. [Asset contracts](../../../docs/spec/asset-contracts.md)
5. [Dialogue and cutscene sequences](../../../docs/spec/game/dialogue-and-cutscene-sequences.md)
6. [Soundtrack contract](../../../docs/game-soundtrack.md)

Resolve [`library/games/main.toml`](../../../library/games/main.toml) and inspect
its selected package as the live example. Do not revive obsolete compatibility
shapes.

## Keep ownership clear

- `game.toml`: identity, visual direction, package membership, and digests.
- `gameplay.toml`: map use, transitions, spawns, population, combat, loot,
  interactions, and map audio.
- `maps/<map_id>.toml`: visual generation of one environment only: camera,
  movement, ground, layers, references, and their prompts.
- `content/*.toml`: pure asset identities and generation direction, without
  gameplay relationships.
- `sequences/*.toml`: authored dialogue and control sequences.
- `soundtrack.toml`: music identities and generation direction.

Use stable `lower_snake_case` IDs. Keep every cross-reference explicit.

## Prepare map references first

The main cover or character concept is art-direction evidence, not a map input.
Before authoring a map, create and review one or more dedicated,
environment-only scene concepts for that map. They may be informed by the
cover, but must not include the player, NPCs, mobs, UI, or text.

Only those dedicated scene images may appear in the map's `[[references]]`.
Each layer and ground prompt must identify what to derive or separate from its
chosen reference. Different layers may use different scene references. Obtain
authorization before any billable image generation, then record exact hashes
and inline origin/rights basis in the authored contract and bind semantic review
to the accepted bytes. Prepared inputs do not need `.meta.json`,
`.source.meta.json`, or `.LICENSE.md` sidecars.

If the map loops, compose its scene references with looping in mind instead of
blindly passing a general concept image. Give each intended depth band compatible
left/right boundary conditions, keep unique landmarks away from the edges, and
use quiet recurring motifs at both sides. The reference only communicates
composition; generated layers still require their own seamlessness validation.

## Review and close the package

Review the authored package as a game design, not only as valid TOML: check that
the content supports the intended gameplay, every relationship has one clear
owner, and each visual reference is suitable for its exact generation role.
Record the required independent semantic review for accepted generated media.

Run the canonical closure validator from the repository root:

```sh
uv run python scripts/validate_game_package.py --root .
```

It verifies TOML parsing, confined paths, exact digests, resolvable references,
and orphaned entries. Before serving a committed canonical demo, also run it
with `--require-committed`. If the ratified schema is newer than the implemented
validator, report that gap; never downgrade the authored package to a legacy
shape just to pass. Stop at a complete authored input package: do not implement
the pipeline or claim that the game has been generated.
