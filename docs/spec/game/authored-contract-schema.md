# Authored game contract schema

> **Contract maturity: exact-current prepared-package root.**
>
> This document specifies `game-contract-v6`, the root `game.toml` accepted by
> prepared-package ingest. The complete package closure and transport rules live
> in [Canonical prepared game package](../../game-package.md); execution order
> and provider fan-out live in the [Canonical generation pipeline](generation-pipeline.md).

## Purpose

`game.toml` is the membership and digest-closure root for one prepared game. It
owns shared identity and art direction, catalogs the cast and maps, and locks
every direct contract and evidence source. It does not contain generated paths,
provider configuration, execution order, map-use rules, or runtime objects.

The canonical path is:

```text
library/games/<game_id>/game.toml
```

Only `schema_version = 6` and `kind = "game-contract-v6"` are accepted. The
resolver does not translate another document shape.

## Root shape

The exact fields are:

```toml
schema_version = 6
kind = "game-contract-v6"
game_id = "example-game"
revision = 1
display_name = "Example Game"

[universe]
source = "universe.md"
source_sha256 = "<sha256>"

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

[cast]
player_id = "player_one"
mob_ids = ["mob_one"]
npc_ids = ["npc_one"]

[gameplay]
source = "gameplay.toml"
source_sha256 = "<sha256>"

[ui]
source = "ui.toml"
source_sha256 = "<sha256>"

[soundtrack]
source = "soundtrack.toml"
source_sha256 = "<sha256>"

[[maps]]
map_id = "first-map"
source = "maps/first-map.toml"
source_sha256 = "<sha256>"

[content.player]
source = "content/player.toml"
source_sha256 = "<sha256>"

[content.mobs]
source = "content/mobs.toml"
source_sha256 = "<sha256>"

[content.npcs]
source = "content/npcs.toml"
source_sha256 = "<sha256>"

[content.props]
source = "content/props.toml"
source_sha256 = "<sha256>"

[content.items]
source = "content/items.toml"
source_sha256 = "<sha256>"

[sequences]
index_source = "sequences/index.toml"
index_sha256 = "<sha256>"

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
- Player, mob, and NPC IDs are unique `lower_snake_case` identifiers. Cast IDs
  must resolve to their respective content catalogs.
- The universe, gameplay, UI, soundtrack, content, and sequence-catalog paths
  have fixed package-relative locations.
- Every map source is exactly `maps/<map_id>.toml`; map IDs and sources are
  unique.
- Evidence keys are `lower_snake_case`. Each evidence triple lives under
  `references/`, uses the required provenance/review suffixes, and is unique.
- Every direct source and evidence file is bound by the SHA-256 of its exact
  bytes. Unknown fields are rejected.
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
| Content catalogs | Player, mob, NPC, prop, and item identities, visual references, motion presentation, and NPC catalog-wide world orientation |
| `soundtrack.toml` | Track identities, creative briefs, and playback policy |
| Sequence catalog and sources | Dialogue/cutscene graph and outcomes |

In particular, a map owns ladder and portal composition per map, while
`gameplay.toml` owns climb permission and portal destinations. Gameplay
`crouch` authorizes the posture; the player catalog supplies its motion frames
and playback contract.

## Resolution and projection

Prepared-package resolution captures the selected directory or ZIP once,
checks every digest and exact closure member, validates all cross-contract
identities locally, and rejects malformed input before a provider operation.
The scrolling DAG consumes this resolved package and integration emits only
`prepared-game-runtime-v8`.

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
