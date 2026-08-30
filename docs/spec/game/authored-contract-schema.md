# Authored game contract schema

> **Contract maturity: exact-current prepared-package root.**
>
> This document specifies `game-contract-v7`, the root `game.toml` accepted by
> prepared-package ingest. The complete package closure and transport rules live
> in [Canonical prepared game package](../../game-package.md); execution order
> and provider fan-out live in the [Canonical generation pipeline](generation-pipeline.md).

## Purpose

`game.toml` is the membership root for one prepared game, naming every member
by exact source path. It owns shared identity and art direction, catalogs the
cast and maps, and names every direct contract and evidence source. It does not
contain generated paths, provider configuration, execution order, map-use
rules, or runtime objects.

The canonical path is:

```text
library/games/<game_id>/game.toml
```

Only `schema_version = 7` and `kind = "game-contract-v7"` are accepted. The
resolver does not translate another document shape.

## Root shape

The exact fields are:

```toml
schema_version = 7
kind = "game-contract-v7"
game_id = "example-game"
revision = 1
display_name = "Example Game"

[universe]
source = "universe.md"

[presentation]
view_profile = "side_view_2d"
gameplay_space = "side_plane"

[presentation.contact_shadows]
enabled = true
opacity = 0.18
softness_screen_pixels = 6.0

[style]
label = "concise authored style name"
keywords = ["ordered visual direction", "another visual direction"]
avoid = ["undesired visual property"]

[proportion]
heads_tall = 2.25

[proportion.by_body_kind]
dwarf = 2.1

[scale]
unit = "player_height"
player_height_tiles = 2.40
minimum = 0.25
steps = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]

[scale.ranks]
common = 0.5
boss = 1.5

[cast]
player_id = "player_one"
mob_ids = ["mob_one"]
npc_ids = ["npc_one"]

[gameplay]
source = "gameplay.toml"

[ui]
source = "ui.toml"

[soundtrack]
source = "soundtrack.toml"

[[maps]]
map_id = "first-map"
source = "maps/first-map.toml"

[content.player]
source = "content/player.toml"

[content.mobs]
source = "content/mobs.toml"

[content.npcs]
source = "content/npcs.toml"

[content.props]
source = "content/props.toml"

[content.items]
source = "content/items.toml"

# Optional, and the only optional content family. A game whose weapons throw
# nothing omits the section and ships no projectile artwork.
[content.projectiles]
source = "content/projectiles.toml"

[sequences]
index_source = "sequences/index.toml"

[evidence.cover]
artifact_source = "references/cover.png"
artifact_sha256 = "<sha256>"
provenance_source = "references/cover.provenance.json"
provenance_sha256 = "<sha256>"
review_source = "references/cover.visual-review.md"
review_sha256 = "<sha256>"

[rights]
status = "unreviewed"
basis = ["Original authored package direction."]
```

## Field invariants

- `game_id` is a portable game identifier and agrees with the selected package
  identity; `revision` is at least one and `display_name` is trimmed text.
- Presentation is currently exactly `side_view_2d` in `side_plane` gameplay
  space. `contact_shadows` is a consumer-only grounding treatment: `opacity`
  is zero through one and `softness_screen_pixels` is zero through 32.
- Style keywords and avoidances are ordered, unique, trimmed lists. Their order
  is prompt-significant.
- Default and body-specific proportions are between 1.5 and 12 heads tall.
- `scale` states the game's size vocabulary. `unit` is exactly `player_height`: the player
  is `1.0` by definition and every other subject declares `height_units` as a multiple of
  it. `player_height_tiles` is the one place the unit meets a render projection.
  `minimum` is the legibility floor nothing interactive resolves below, `steps` is an
  ascending unique ladder at or above that floor, and `[scale.ranks]` maps a mob rank to a
  magnitude so silhouette height carries threat. `scale` and `proportion` answer different
  questions and are never reconciled: magnitude is a property of the world, build is a
  property of the art style.
- Player, mob, and NPC IDs are unique `lower_snake_case` identifiers. Cast IDs
  must resolve to their respective content catalogs. `content.projectiles` is
  optional; when declared it must resolve to `content/projectiles.toml`.
- The universe, gameplay, UI, soundtrack, content, and sequence-catalog paths
  have fixed package-relative locations.
- Every map source is exactly `maps/<map_id>.toml`; map IDs and sources are
  unique.
- Evidence keys are `lower_snake_case`. Each evidence triple lives under
  `references/`, uses the required provenance/review suffixes, and is unique.
- Evidence digests are authored: each artifact, provenance, and review file is
  bound by the SHA-256 of its exact reviewed bytes. Member digests are computed
  at ingest and are never authored here. Unknown fields are rejected.
- Rights status is `unreviewed`, `restricted`, or
  `redistribution-approved`; the nonempty basis records authored-input rights,
  not generated-media publication approval.

## Composition boundaries

The root catalogs subordinate contracts; it does not absorb their fields:

| Contract | Authority |
| --- | --- |
| `gameplay.toml` | Movement, entry map, transition relationships, population, combat, loot, interactions, quests, and effects |
| `ui.toml` | Generated interface presentation and layout |
| `maps/<map_id>.toml` | Visual/static map composition, terrain occupancy, ladder placement, and portal presentation/anchors |
| Content catalogs | Player, mob, NPC, prop, item, and projectile identities, visual references, motion presentation, the player's drawn equipment, and NPC catalog-wide world orientation |
| `soundtrack.toml` | Track identities, creative briefs, and playback policy |
| Sequence catalog and sources | Dialogue/cutscene graph and outcomes |

In particular, a map owns ladder and portal composition per map, while
`gameplay.toml` owns climb permission and portal destinations. Gameplay
`crouch` authorizes the posture; the player catalog supplies its motion frames
and playback contract. Gameplay `[combat] weapon_class` says how the character
fights; the player catalog's `equipment` says what they are drawn carrying.
Both are closed names, so unlike the pairings above this one is enforced rather
than merely owned: for a combat-enabled package, resolution rejects a
combination the vocabularies do not admit as `player_equipment_mismatch`.

## Resolution and projection

Prepared-package resolution captures the selected directory or ZIP once,
computes every member digest at capture, validates all cross-contract
identities locally, and rejects malformed input before a provider operation.
Membership stays exact: a member named here but absent is rejected as
`missing_package_file`, and a captured file no contract names is rejected as
`orphan_package_file`. Resolution then digests the exact captured closure of
every member path, digest, and byte size as `closure_sha256`, which appears in
the resolved package identity and in the `game-package-validation-v4` report.
The scrolling DAG consumes this resolved package and integration emits only
`prepared-game-runtime-v10`.

Validate the canonical package with:

```sh
uv run stage-gen package validate --input library/games/bellweather
uv run stage-gen package digest --input library/games/bellweather
uv run stage-gen package plan --input library/games/bellweather
```

The executable authority is
`src/stage_gen/components/game_contract/package.py` together with
`src/stage_gen/orchestration/game_package.py`. The canonical Bellweather source
is the integration fixture; documentation examples do not replace executable
validation.
