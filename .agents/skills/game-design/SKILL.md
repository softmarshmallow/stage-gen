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
7. [Web preview](../../../docs/web-preview.md), for what a named gameplay
   choice actually looks like once the consumer runs it

Resolve [`library/games/main.toml`](../../../library/games/main.toml) and inspect
its selected package as the live example. Do not revive obsolete compatibility
shapes.

## Keep ownership clear

- `game.toml`: identity, visual direction, and package membership by exact
  source path.
- `gameplay.toml`: map use, transitions, spawns, population, combat, loot,
  interactions, and map audio.
- `maps/<map_id>.toml`: visual generation of one environment only: camera,
  movement, ground, layers, references, and their prompts.
- `content/*.toml`: asset identities and generation direction. These carry no
  gameplay *numbers* and no placement, but they are not free of gameplay: a few
  fields are closed names the package validator holds against `gameplay.toml`,
  and `player.equipment` is the one to watch. See below.
- `sequences/*.toml`: authored dialogue and control sequences.
- `soundtrack.toml`: music identities and generation direction.

Use stable `lower_snake_case` IDs. Keep every cross-reference explicit.

## The character and the kit are one decision

`gameplay.toml`'s `[combat] weapon_class` says how the character fights;
`content/player.toml`'s `equipment` says what they are drawn carrying. They are
one fact authored in two files, so for a combat-enabled package the validator
refuses the pairings that cannot both be true - a `hand_weapon_v1` figure cannot
fight as `ranged_dps_v1`, and a `thrown_kit_v1` figure cannot swing.

Decide these together, and decide them before the cover, because the cover is
the identity source every later strip is generated from. A cover showing a sword
commits the package to melee; changing your mind afterwards means re-selecting
the cover and re-rendering the whole player domain, not editing one line.

The equipment name is only the *class* of thing. The player `prompt` still names
the specific object, and the recipe supplies the structural direction - that it
appears in every frame, or that it is never drawn at all. Do not repeat the
structural direction in the prose; do name the object.

`weapon_class = "ranged_dps_v1"` additionally requires a `projectile_id`
resolving into `content/projectiles.toml`, and a melee class must not name one.

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
Read the player prompt against the declared `equipment` and against the pinned
cover: the validator compares two closed names and cannot read prose, so prose
that contradicts the declaration passes closure and fails in the pixels.
Record the required independent semantic review for accepted generated media.

Run the canonical closure validator from the repository root:

```sh
uv run python scripts/validate_game_package.py --root .
```

It verifies TOML parsing, confined paths, exact path membership, the authored
evidence and reference image digests, resolvable references, and orphaned
entries. Before serving a committed canonical demo, also run it with
`--require-committed`. If the ratified schema is newer than the implemented
validator, report that gap; never downgrade the authored package to a legacy
shape just to pass. Stop at a complete authored input package: do not implement
the pipeline or claim that the game has been generated.
