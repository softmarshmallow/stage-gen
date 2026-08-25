# Authored game maps

Authored game maps give a game a durable, ordered set of map identities and, in
`game-map-v2`, one complete engine-neutral **Level Profile** per map. A profile classifies the
view, camera behavior, traversal model, and gameplay mechanisms a level requires. It does not
describe how Phaser, Unity, Godot, Unreal, or another consumer realizes them.

The game-global [`soundtrack.toml`](game-soundtrack.md) catalog continues to own track identity,
generation intent, and playback policy. The
[`game.toml`](spec/game/authored-contract-schema.md) contract continues to
own game-wide art direction and gameplay policies such as population zones and combat-text
enablement. The map owns identity, its soundtrack pool, and its level semantics.

Static terrain geometry, collision bodies, portal coordinates, encounter placement, platform
graphs, camera pixel bounds, physics constants, layout names, and engine scene objects remain
recipe-adapter or consumer data. A Level Profile states requirements; it is not a serialized
engine scene.

## Library layout

Maps live beside the game and soundtrack contracts under the same game directory:

```text
library/games/<game_id>/game.toml
library/games/<game_id>/soundtrack.toml
library/games/<game_id>/maps/index.toml
library/games/<game_id>/maps/<map_id>.toml
```

`maps/index.toml` is the ordered book. It does not embed map definitions; each entry locks one
fixed-path source by SHA-256. This keeps individual map edits reviewable while making the book a
reproducible selection of exact source bytes.

The repository example is
[`library/games/whimsical-storybook-fantasy/maps/`](../library/games/whimsical-storybook-fantasy/maps/).

## Per-map contract

The only accepted authored map is `game-map-v2`, and it embeds one complete
`level-profile-v1`:

```toml
schema_version = 2
kind = "game-map-v2"
game_id = "whimsical-storybook-fantasy"
map_id = "stage-1-approach"
revision = 2
display_name = "The Approach"
soundtrack_track_ids = ["highwhim_spires", "sunpetal_road"]

[level_profile]
schema_version = 1
kind = "level-profile-v1"
role = "combat_field"

[level_profile.view]
projection = "orthographic_2d"
viewpoint = "side_on"

[level_profile.camera]
tracking_mode = "player_follow"
framing_mode = "dead_zone"
scroll_axes = ["horizontal", "vertical"]

[level_profile.traversal]
ground_model = "heightfield"
platform_model = "one_way"
affordances = ["ground_move", "jump", "air_jump", "drop_through", "ladder_climb"]

[level_profile.mechanisms]
encounter_model = "continuous_population"
combat_model = "real_time_action"
loot_model = "defeat_drops"
interaction_model = "none"
transition_model = "bidirectional_portals"
```

The current map identity rules are:

- `game_id` must match the containing `library/games/<game_id>/` directory.
- `map_id` is stable lower-kebab-case identity and must match the source filename exactly.
- `revision` begins at 1 and is raised when authored map metadata or its profile changes.
- `display_name` is non-empty trimmed presentation text, at most 160 characters.
- `soundtrack_track_ids` contains 2 to 64 unique lower-snake-case IDs from the game-global
  soundtrack catalog. Order is not semantic and canonical JSON sorts it.
- Unknown fields are rejected.

A map references soundtrack identities; it never copies a track's creative brief, provider,
model, artifact path, or provenance.

## Level Profile taxonomy

The profile uses orthogonal dimensions instead of one genre-specific scene type:

| Dimension | Fields | Current vocabulary |
| --- | --- | --- |
| **Scene role** | `role` | `social_hub`, `combat_field` |
| **View model** | `view.projection`, `view.viewpoint` | `orthographic_2d`, `side_on` |
| **Camera model** | `tracking_mode`, `framing_mode`, `scroll_axes` | `player_follow`, `dead_zone`, `horizontal`, `vertical` |
| **Traversal model** | `ground_model`, `platform_model`, `affordances` | `heightfield`; `none` or `one_way`; movement capabilities |
| **Gameplay mechanism set** | `encounter_model`, `combat_model`, `loot_model`, `interaction_model`, `transition_model` | explicit, independently validated mechanism names |

`view.projection` and `view.viewpoint` are the durable equivalents of an ambiguous
`camera_angle`. `ground_model` and `platform_model` deliberately replace a single `ground_type`:
a heightfield can have no upper platforms or can be combined with one-way platforms without
inventing a new compound enum for every pairing.

Singleton enums are intentional. `orthographic_2d`, `side_on`, `player_follow`, `dead_zone`,
`heightfield`, and `bidirectional_portals` are the only implemented members today, but authoring
them gives future members a versioned extension point and makes an unsupported request fail before
provider work. Adding a representable enum member does not claim that every recipe or consumer
supports it; each consumer owns an explicit support matrix.

The profile also validates semantic dependencies:

- `scroll_axes` and `affordances` are unique and use canonical order.
- `air_jump` requires `jump`.
- `drop_through` and `ladder_climb` require `platform_model = "one_way"`.
- `loot_model = "defeat_drops"` requires real-time combat.
- `role` is descriptive metadata and never enables mechanisms by implication. Every mechanism is
  still authored explicitly.

The bundled scrolling demo supports two complete combinations:

| Role | Camera axes | Platforms and traversal | Mechanisms |
| --- | --- | --- | --- |
| `social_hub` | horizontal | no upper platforms; ground movement and jump | no encounters, combat, or loot; proximity dialogue; bidirectional portals |
| `combat_field` | horizontal and vertical | one-way platforms; ground movement, jump, air jump, drop-through, ladder climb | continuous population, real-time action combat, defeat drops, no dialogue, bidirectional portals |

The recipe and web adapter reject any other complete combination even if its individual enum
values are valid in the core model. This prevents a consumer from approximating required gameplay
with a nearby preset.

## Static geometry remains consumer-owned

The Level Profile does not contain `ascent`, `gauntlet`, or `spires`; terrain seeds; mob stride;
pixel speed; jump impulse; dead-zone coordinates; platform vertices; or spawn coordinates. Those
are implementation data in the optional scrolling adapter.

That adapter keeps an allowlisted static blueprint registry keyed by `map_id`. Identity selects a
known geometry implementation, while the resolved profile supplies the semantics that geometry
must satisfy. The adapter checks that both agree: for example, a `social_hub` profile cannot be
joined to a vertical hunting blueprint. An unknown map ID fails closed rather than receiving
invented geometry.

This is an adapter boundary, not a core promise. Another consumer may realize the same profile
with a different platform graph, coordinate system, camera component, and encounter director.

## Ordered map book

The only accepted authored index is `game-map-book-v1`. It orders and digest-locks
`game-map-v2` sources:

```toml
schema_version = 1
kind = "game-map-book-v1"
game_id = "whimsical-storybook-fantasy"
revision = 2
entry_map_id = "village-hub"

[[maps]]
map_id = "village-hub"
source_sha256 = "<sha256 of maps/village-hub.toml>"

[[maps]]
map_id = "stage-1-approach"
source_sha256 = "<sha256 of maps/stage-1-approach.toml>"
```

The list contains 2 to 64 unique map IDs. Its order is semantic and is preserved in the resolved
artifact and public manifest. `entry_map_id` must equal the first list entry. Each source is read
only from `maps/<map_id>.toml`, and the index digest lock must match the exact bytes read.

Resolution refuses index or map drift, symlink traversal, cross-game sources, filename/identity
disagreement, duplicate IDs, a non-first entry map, and every map schema other than
`game-map-v2`. The canonical resolved document is always
`resolved-game-map-book-v2`.

## Offline validation and digest workflow

Validate or digest one map at its fixed path:

```sh
uv run stage-gen map validate \
  --input library/games/whimsical-storybook-fantasy/maps/village-hub.toml \
  --game-library-root .

uv run stage-gen map digest \
  --input library/games/whimsical-storybook-fantasy/maps/village-hub.toml \
  --game-library-root .
```

Validate or digest the ordered book:

```sh
uv run stage-gen map-book validate \
  --input library/games/whimsical-storybook-fantasy/maps/index.toml \
  --game-library-root .

uv run stage-gen map-book digest \
  --input library/games/whimsical-storybook-fantasy/maps/index.toml \
  --game-library-root .
```

Both digest commands print the SHA-256 of the exact authored input bytes. Book validation resolves
and checks every locked map before succeeding and calls no provider.

After editing a map:

1. Run `stage-gen map digest` for that map.
2. Replace its `source_sha256` in `maps/index.toml`.
3. Run `stage-gen map-book validate`, then `stage-gen map-book digest`.
4. Replace the map-book binding digest in the scrolling request.

The scrolling recipe additionally checks that every map track ID exists in the exact bound
soundtrack catalog and that each profile is a supported scrolling-preview combination. In the
current resolved book, maps whose profile declares `encounter_model = "continuous_population"`
must exactly match
the `gameplay.mob_population.maps` identities in the bound game contract. Missing, duplicate, and
unexpected population entries fail during local resolution before provider-backed generation.

## Scrolling-preview binding and pipeline

A map book is bound separately from `game.toml` and `soundtrack.toml`:

```toml
[game]
schema_version = 1
kind = "game-contract-binding-v1"
ref = "library/games/whimsical-storybook-fantasy/game.toml"
source_sha256 = "<game source sha256>"

[soundtrack]
schema_version = 1
kind = "game-soundtrack-binding-v1"
ref = "library/games/whimsical-storybook-fantasy/soundtrack.toml"
source_sha256 = "<soundtrack source sha256>"

[map_book]
schema_version = 1
kind = "game-map-book-binding-v1"
ref = "library/games/whimsical-storybook-fantasy/maps/index.toml"
source_sha256 = "<map index source sha256>"
```

All bindings must name the same `library/games/<game_id>/` owner. A map-book binding without both
game and soundtrack bindings is invalid. The complete example is
[`examples/scrolling-preview/game-directed-village.toml`](../examples/scrolling-preview/game-directed-village.toml).

The local, provider-free resolution stage is:

```text
game-resolve + soundtrack-resolve -> map-book-resolve -> manifest
post-split + soundtrack-resolve    -> soundtrack-generate -> manifest
```

It writes a canonical `map_book_<tag>.json` artifact plus provenance. Map-book and soundtrack
inputs do not alter visual prompts or visual artifact bytes.

## Manifest projection v2

The current resolved map book publishes `game-map-book-manifest-v2` inside
scrolling manifest V7. The authored index remains `game-map-book-v1`, every
member is `game-map-v2`, and the soundtrack projection is
`game-soundtrack-manifest-v2`.

```json
{
  "schema_version": 7,
  "soundtrack": {
    "schema_version": 2,
    "kind": "game-soundtrack-manifest-v2",
    "game_id": "whimsical-storybook-fantasy"
  },
  "map_book": {
    "schema_version": 2,
    "kind": "game-map-book-manifest-v2",
    "game_id": "whimsical-storybook-fantasy",
    "revision": 2,
    "entry_map_id": "village-hub",
    "source": {
      "path": "map_book_<tag>.json",
      "provenance_path": "map_book_<tag>.json.meta.json",
      "source_sha256": "<map index source sha256>",
      "canonical_sha256": "<resolved map book sha256>"
    },
    "soundtrack": {
      "source_sha256": "<soundtrack source sha256>",
      "canonical_sha256": "<canonical soundtrack sha256>"
    },
    "maps": [
      {
        "map_id": "stage-1-approach",
        "revision": 2,
        "display_name": "The Approach",
        "soundtrack_track_ids": ["highwhim_spires", "sunpetal_road"],
        "source_ref": "library/games/whimsical-storybook-fantasy/maps/stage-1-approach.toml",
        "source_sha256": "<map source sha256>",
        "canonical_sha256": "<canonical map sha256>",
        "level_profile": {
          "schema_version": 1,
          "kind": "level-profile-v1",
          "role": "combat_field",
          "view": { "projection": "orthographic_2d", "viewpoint": "side_on" },
          "camera": {
            "tracking_mode": "player_follow",
            "framing_mode": "dead_zone",
            "scroll_axes": ["horizontal", "vertical"]
          },
          "traversal": {
            "ground_model": "heightfield",
            "platform_model": "one_way",
            "affordances": ["ground_move", "jump", "air_jump", "drop_through", "ladder_climb"]
          },
          "mechanisms": {
            "encounter_model": "continuous_population",
            "combat_model": "real_time_action",
            "loot_model": "defeat_drops",
            "interaction_model": "none",
            "transition_model": "bidirectional_portals"
          }
        }
      }
    ]
  }
}
```

The excerpt omits track artifacts and additional maps. The block preserves map order and binds
the index, every map source, and the soundtrack catalog whose IDs the maps reference. Consumers
require the exact top-level manifest V7 identity and then validate the exact current map-book V2
block. An incomplete or malformed book fails closed.

## Web Level Profile adapter

The optional browser preview keeps its adapter in `web/lib/runtime/`:

1. `parseMapBookManifest` validates only `game-map-book-manifest-v2`, checks source
   and soundtrack digest bindings, and parses every `level_profile-v1`.
2. `assertScrollingDemoLevelProfileSupported` checks the complete profile against the demo's
   allowlisted support matrix.
3. `buildStageBook` joins authored identity, display name, soundtrack pool, and semantics to the
   consumer-owned static blueprint with the same `map_id`, rejecting contradictions.

Profile fields determine hub versus combat-field behavior, vertical traversal
enablement, and whether an encounter spawner may run; the map ID still selects
geometry. Portal travel, scene construction, physics, and rendering remain
browser-owned.

## Current absence semantics

- When `map_book` is omitted, manifest V7 omits the `map_book` block and the
  current no-map consumer mode owns its stage selection.
- When a soundtrack is present without a map book, the current
  `game-soundtrack-manifest-v2` block supplies one run-global shuffle pool.
- A declared map book requires one profile on every `game-map-v2` source and
  fails on an unsupported complete combination.
- Rerunning the same tag without a map book excludes stale map-book artifacts
  from the new manifest.
- A declared malformed block fails closed; omission never authorizes parsing an
  obsolete schema.

No map validation, digest, resolution, or manifest assembly command calls a media provider. Music
generation remains a separate, explicitly authorized operation.

## Related

- [Scene profiles and gameplay components](spec/scene-gameplay-components.md) — ownership and
  composition rules for Level Profiles and gameplay policies.
- [Authored game contract schema](spec/game/authored-contract-schema.md) — game-wide art direction,
  population policy, and combat-text enablement.
- [Optional web preview adapter](web-preview.md) — the static-geometry and runtime consumer.
