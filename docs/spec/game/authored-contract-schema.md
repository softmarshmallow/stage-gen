# Authored game contract schema

> **Contract maturity: implemented.**
>
> This specification documents the currently executable `game.toml` contract,
> including its exact current version, closed vocabulary, validation rules, recipe
> binding, and manifest projection. The canonical game-domain model and ownership
> boundaries live in the [Game contract](../../game-contract.md).

## Scope

An authored game contract fixes direction that must remain coherent across the
assets generated for one game:

- the camera projection for which the assets are authored;
- the reviewed style words appended to every image prompt;
- the body proportions shared by the cast;
- the render profile of each supported cast role;
- versioned gameplay direction; and
- the rights basis of the authored contract.

The current schema describes one camera and the roles implemented by the
scrolling-preview recipe. It is not a general scene graph, a camera-rig format,
or a declaration that other game-view profiles are supported. Proposed target
terminology is defined separately in the
[Game view and style taxonomy](view-and-style-taxonomy.md).

## Library location and identity

Every authored contract has exactly one path shape:

```text
library/games/<game_id>/game.toml
```

The resolver checks that the directory name and declared `game_id` agree. Reads
are confined to the operator-selected game-library root, and a symlink anywhere
along the path is rejected rather than followed outside that root.

The source is strictly parsed, canonicalized to JSON, digest-bound into the run,
and projected into consumer manifests. The generated run retains portable
identity and provenance; it never persists credentials, private absolute paths,
or temporary paths.

## Complete `game-contract-v3` example

```toml
schema_version = 3
kind = "game-contract-v3"
game_id = "whimsical-storybook-fantasy"
revision = 3
display_name = "Whimsical Storybook Fantasy"

[camera]
projection = "side_view_2d"

[style]
keywords = [
  "hand-painted gouache",
  "warm dusk palette",
  "soft diffuse light",
  "rounded friendly shapes",
  "visible brush texture",
  "gentle and welcoming mood",
]
avoid = ["photographic depth of field", "3D rendering", "cast ground shadows"]

[proportion]
heads_tall = 2.0

[proportion.by_body_kind]
avian = 2.4

[cast.player]
body_kind = "human"
orientation = "side"
animation = "strip"

[cast.resident]
body_kind_default = "human"
orientation = "front"
animation = "still"
allow_pose = true
allow_held_prop = true

[gameplay.combat_text]
schema_version = 1
kind = "combat-text-v1"
enabled = true

[gameplay.mob_population]
schema_version = 1
kind = "mob-population-v1"
update_interval_ms = 250
max_spawn_batch_per_update = 2

[[gameplay.mob_population.maps]]
map_id = "stage-1-approach"
seed_salt = 1103

[[gameplay.mob_population.maps.zones]]
zone_id = "approach-west"
surface = "terrain"
left_column = 10
right_column_exclusive = 90
initial_population = 3
target_population = 4
population_cap = 4
respawn_delay_ms = 7000
respawn_variance_ms = 1500
spawn_interval_ms = 500
spawn_batch_size = 1
retry_delay_ms = 750
spawn_visibility = "offscreen_preferred"
camera_margin_px = 128
min_player_distance_px = 320
minimum_spawn_separation_px = 128
wander_radius_px = 100
pursuit_leash_px = 256
replacement_policy = "reroll_spawn_table"

[[gameplay.mob_population.maps.zones.spawn_table]]
mob_tier = 1
weight = 3
min_alive = 1
max_alive = 3

[[gameplay.mob_population.maps.zones.spawn_table]]
mob_tier = 2
weight = 1
min_alive = 0
max_alive = 2

[rights]
status = "unreviewed"
notice = "Original repository-authored game direction; no publication approval is implied."
basis = ["Original repository-authored text with no external game or media reference."]
```

## Current contract

Only `game-contract-v3` is accepted. Every other schema version or kind fails
validation; the resolver never upgrades, translates, or infers an obsolete
document.

The current contract requires the versioned combat-text policy and makes
`gameplay.mob_population` optional. Omitting the whole `gameplay` table or only
`combat_text` materializes the canonical `combat-text-v1` block with
`enabled = true`. This default is persisted in canonical JSON and projected into
manifest V7; it is not an implicit consumer guess.

### `[camera]`

`camera` is required. Its currently implemented `projection` vocabulary contains
only `side_view_2d` because that is the only projection accepted by the
scrolling-preview recipe.

The projection is a field rather than a filename convention so it can be
validated, rejected before provider work, carried into provenance, and checked
by each recipe. `side_view_2d` is the current executable identifier, not a
precedent for future taxonomy design.

### `[style]`

`style.keywords` contains three to ten unique entries from the packaged closed
vocabulary. At least one entry must have the `medium` facet. Order is preserved
because it becomes prompt order, so reordering the list is a contract edit that
changes the run identity.

`style.avoid` contains unique entries from the approved avoidance vocabulary.
The resulting clause is appended to every image prompt in the directed run:

```text
Game art direction — hand-painted gouache, warm dusk palette, soft diffuse light,
rounded friendly shapes, visible brush texture, gentle and welcoming mood.
Avoid: photographic depth of field; 3D rendering; cast ground shadows.
```

This game-owned direction is intentionally separate from the canonical
[image style anchor](../../image-style-anchor.md). The anchor selects a tracked
rendering medium; the game contract supplies durable art direction above it.

### `[proportion]`

`proportion.heads_tall` gives the game-wide default body build. It is rounded to
one decimal place and must be between 2.0 and 8.0 heads. The player and every
resident resolve from this shared value, preventing a model-selected resident
build from changing runtime height by accident.

`proportion.by_body_kind` supplies explicit exceptions for bodies whose anatomy
cannot use the default meaningfully. A request may carry an authored game
contract or the recipe-local `character_heads_tall` input, never both.

### `[cast]`

`cast.player` and `cast.resident` are different models because their generated
artwork has different invariants.

- The player is currently a side-oriented animated strip actor. Its
  `orientation = "side"` and `animation = "strip"` values are stated and pinned.
- A directed resident defaults to `orientation = "front"` and
  `animation = "still"`. Pose and held-prop direction can be independently
  allowed or disabled.

An animated resident strip is valid only with side orientation. Front and
three-quarter orientations are still-only in the current schema. These are
capability constraints of the implemented recipe, not general definitions of
those view terms.

### `[gameplay]`

`gameplay` is an aggregate of independent, versioned policies rather than a
genre preset. In the current `game-contract-v3`, `gameplay.combat_text` is
materialized explicitly and population direction remains independent and
optional.

#### Floating combat text

`combat-text-v1` contains one portable policy: `enabled`. Under
`game-contract-v3`, omission materializes the explicit canonical default with
`enabled = true`; authoring `enabled = false` suppresses damage numbers.

Font family, colors, outline, motion curve, local glyph shake, lifetime, object
pool limits, and engine settings are deliberately not authored here. They are
static presentation decisions owned by a consumer, so the portable policy does
not become the optional browser demo's styling API.

#### Hunting-ground population

`gameplay.mob_population` owns what should populate each authored map. The
consumer adapter owns how terrain columns become runtime spawn positions.

The subsystem uses these terms precisely:

- A **spawn zone** is a half-open map-space range,
  `[left_column, right_column_exclusive)`, that owns a population and its legal
  terrain candidates.
- A **spawn table** is the weighted set of generated mob tiers eligible for a
  zone. A one-based `mob_tier` is resolved to a consumer's zero-based slot only
  at manifest projection.
- A **respawn ticket** is created once when a live mob dies. Placement retries
  retain the same ticket instead of creating additional population.
- `initial_population`, `target_population`, and `population_cap` define warm
  start, replenishment target, and the hard live-plus-reserved ceiling.
- Spawn cadence and batch fields bound catch-up work after a suspended consumer
  resumes.
- Visibility, camera margin, player distance, and separation fields prevent
  visible or overlapping pop-in.
- Patrol radius and pursuit leash define movement relative to a spawn home; the
  leash must be at least the patrol radius.
- Replacement policy either preserves the defeated archetype or deterministically
  rerolls the spawn table.

Validation rejects duplicate map or zone IDs, overlapping zones, invalid ranges,
non-positive cadences, empty or duplicate spawn tables, impossible minima or
maxima, and any violation of
`initial_population <= target_population <= population_cap`. Recipe projection
also rejects map IDs outside the bound map book when one is present,
out-of-range columns, and mob tiers absent from the resolved world roster. When
a v2 map book declares
`encounter_model = "continuous_population"`, local map-book resolution requires
the population map IDs to match those combat fields exactly before any provider
stage runs. Manifest assembly repeats the invariant as a final defense, and the
runtime validates it again before scene construction.

### `[rights]`

`rights` is required and has the same strict shape as character-profile rights.
`status = "unreviewed"` is the correct default for an unreviewed authored
contract and must not claim a licence or review time. This block records the
rights basis of the authored direction; it does not authorize generated-media
publication.

## Closed vocabulary

`src/stage_gen/resources/prompting/game_vocabulary_v1.json` is the executable
closed list for authored words. Its digest is part of run identity, so changing
the meaning or membership of the vocabulary invalidates reuse of artwork it
directed.

| Section | Constrains | Consumer |
| --- | --- | --- |
| `style_keywords` | `style.keywords`, faceted as `medium`, `palette`, `light`, `shape`, `surface`, or `mood` | Art-direction prompt clause |
| `style_avoidances` | `style.avoid` | Art-direction prompt clause |
| `body_kinds` | Cast bodies and proportion exceptions | Anatomy and proportion direction |
| `resident_stances` | Directed resident stance | Resident still prompt |
| `resident_props` | Directed resident held object | Resident still prompt |

The vocabulary is an implemented allowlist, not the proposed scientific
classification of presentation profiles. The taxonomy specification defines
the future conceptual axes; a later executable vocabulary must be derived from
ratified terms and separately versioned.

## Resident render profile

A contract-directed resident uses the current dedicated front-facing still
profile:

| Property | Current directed resident |
| --- | --- |
| Stage | `village-npc-<i>-still` |
| Artifact | `npc_<tag>_<i>_still.png` |
| Canvas | 800×1200, one cell |
| Runtime image | Whole canvas |
| Facing review | Front-facing |
| Frame symmetry | Not applicable |
| Build and scale gates | Required |
| Runtime mirroring | Disabled |

A directed roster additionally carries vocabulary-constrained `body_kind`,
`stance`, and `holding` values. Two residents may not share both a stance and a
held prop. Body kinds may repeat because a coherent town does not require every
resident to have different anatomy.

## Authoring and binding

Validate and digest the authored source before binding it:

```bash
uv run stage-gen game validate \
  --input library/games/whimsical-storybook-fantasy/game.toml \
  --game-library-root .

uv run stage-gen game digest \
  --input library/games/whimsical-storybook-fantasy/game.toml \
  --game-library-root .
```

A generation request binds the exact source bytes:

```toml
prompt = "whimsical storybook fantasy"

[game]
schema_version = 1
kind = "game-contract-binding-v1"
ref = "library/games/whimsical-storybook-fantasy/game.toml"
source_sha256 = "…"
```

The root may also come from `STAGE_GEN_GAME_LIBRARY_ROOT`. The resolver checks
the digest before parsing and writes canonical `game_<tag>.json` into the run so
the result remains auditable after the authored library changes.

See the runnable
[game-directed scrolling request](../../../examples/scrolling-preview/game-directed-village.toml).
Game-global music and map identity remain separately digest-bound sibling
contracts; see [Authored game soundtracks](../../game-soundtrack.md) and
[Authored game maps](../../game-maps.md).

## Recipe and manifest projection

`game-resolve` runs before provider-backed generation. The scrolling recipe
rejects unsupported projections there, then makes a hash of the portable
binding reference and the vocabulary digest part of the run tag. Source and
canonical contract digests remain enforced through the binding, artifacts, and
provenance rather than being encoded in the directory name.

A resolved `game-contract-v3` publishes only scrolling manifest V7, adds
`contract_schema_version = 3` to the verified `game_contract` identity, and
publishes independent policies under `gameplay`. Population is present only
when authored; combat text is always explicit because the current default is
materialized before canonicalization.

Manifest V7 is a composition envelope rather than a monolithic gameplay
schema. `combat_text`, optional `mob_population`, and the current map-book V2
projection each retain their own exact version and kind, and consumers validate
those blocks locally. Consumers reject every other top-level manifest version
and do not infer gameplay policy from an obsolete envelope.

The directed village block uses schema version 2 and publishes its render shape:

```json
{
  "schema_version": 2,
  "render": {
    "frames": 1,
    "orientation": "front",
    "animation": "still",
    "state": "still"
  },
  "npcs": [
    {"slot": 0, "name": "…", "role_label": "…", "lines": ["…", "…", "…"]}
  ]
}
```

Consumers must require the exact current village schema. `frames` controls
sprite slicing, and `orientation` determines whether horizontal mirroring is
meaningful. A contradictory render block is rejected rather than reconciled.

## Executable authority

The implementation is authoritative for acceptance and rejection behavior:

- `src/stage_gen/components/game_contract/models.py` — contract models and
  version rules;
- `src/stage_gen/components/game_contract/gameplay.py` — versioned gameplay
  policy aggregate and combat-text policy;
- `src/stage_gen/components/game_contract/vocabulary.py` — vocabulary model and
  digest;
- `src/stage_gen/components/game_contract/library.py` — confined resolution;
- `src/stage_gen/recipes/scrolling_preview/game.py` — recipe binding and accepted
  projection; and
- `src/stage_gen/recipes/scrolling_preview/manifest.py` — consumer projection.

Documentation contract tests compare this specification with those live models
so an implemented field or vocabulary section cannot remain undocumented.
