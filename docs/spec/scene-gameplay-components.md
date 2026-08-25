# Scene profiles and gameplay components

This specification separates portable scene intent from one optional demo runtime. `stage-gen`
remains an asset generator: the Python core validates what a level requires and recipes publish
that intent with generated artifacts, while a consumer decides how to realize movement, physics,
camera motion, combat, and presentation in an engine.

There is no `maple_story`, `hunting_ground_engine`, or other game-specific umbrella mode. A level
is composed from orthogonal, versioned facts. A consumer can support that combination, reject it
before provider work, or implement it differently without changing the authored game.

## Ownership

| Layer | Owns | Must not own |
| --- | --- | --- |
| `game-contract-v3` | game-wide art direction and gameplay policies | per-map geometry or Phaser values |
| `game-map-v2` | map identity and one complete `level-profile-v1` | generated terrain or engine objects |
| recipe | supported combinations, generation semantics, coordinate projection, manifest composition | browser lifecycle or hidden gameplay defaults |
| manifest | verified resolved blocks and provenance | mutable runtime state |
| consumer | engine implementation, timing, physics, UI styling, pooling, accessibility | generation or reusable Python contracts |

`role` is descriptive metadata. It never switches mechanisms implicitly. A `social_hub` without
`interaction_model = "proximity_dialogue"` has no dialogue, and a `combat_field` without a combat
model has no combat. This keeps additions compositional instead of turning every role into a
consumer-specific preset.

## Per-map level profile

`game-map-v2` embeds one complete profile. The current scrolling consumer supports the following
shape:

```toml
schema_version = 2
kind = "game-map-v2"
game_id = "example-game"
map_id = "field-one"
revision = 1
display_name = "Field One"
soundtrack_track_ids = ["field_day", "field_night"]

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
transition_model = "bidirectional_portals"
interaction_model = "none"
```

These are model names, not tunable engine constants. Pixel speeds, jump impulses, camera dead-zone
coordinates, terrain seeds, and the scrolling demo's `ascent`/`gauntlet`/`spires` layout choices
remain consumer or recipe-adapter data. Likewise, spawn-zone column ranges are a scrolling
coordinate projection rather than a universal level coordinate system.

Singleton enums are deliberate. Adding a schema member states only that the core can represent
it; every recipe and consumer maintains its own support matrix. A required unsupported value is a
validation error before image generation, never a request to approximate it with the nearest
implemented behavior.

## Gameplay subsystem aggregation

Only `game-contract-v3` is accepted. It composes gameplay subsystems
independently: population direction is optional, while combat text materializes
to an explicit, default-on canonical block even when the author omits the table:

```toml
[gameplay.combat_text]
schema_version = 1
kind = "combat-text-v1"
enabled = true
```

Only the policy toggle is portable. The bundled font, palette, outline, motion curve, object cap,
and reduced-motion behavior are static choices in the optional web demo. This prevents a generic
asset contract from becoming a Phaser styling API while still letting an agent turn the feedback
mechanism off for a game.

The existing population policy continues to be authored independently. A future coordinate-space
contract may move spatial zones into map files. Until then, the scrolling recipe owns the meaning
of column coordinates and validates them against its map width and walkable surfaces.

## Manifest composition

Manifest v7 composes blocks by their own version and kind:

```text
schema_version = 7
map_book.schema_version = 2
map_book.kind = game-map-book-manifest-v2
map_book.maps[*].level_profile.kind = level-profile-v1
gameplay.combat_text.kind = combat-text-v1
gameplay.mob_population.kind = mob-population-v1  # only when authored
```

Consumers require the exact top-level manifest V7 identity, then validate each
present block against its exact current version and kind. When an optional
system is omitted, its block is absent; omission does not authorize parsing an
obsolete schema or inferring an authored policy. A bound `game-contract-v3`
always projects the materialized combat-text policy explicitly.

## Runtime components

The web demo keeps `StageScene` as its composition root and uses an explicit allowlist of systems.
It does not load arbitrary plugins. Stage-scoped systems implement the lifecycle they need from:

```text
create -> update -> snapshot -> dispose
```

Dependency order is explicit: terrain, traversal, population, combat, then combat feedback.
Portal travel disposes stage-scoped state before rebuilding the next world. A map ID may select
one of the demo's existing geometry blueprints, but identity never supplies scene semantics; the
resolved level profile does.

## Floating combat text

Floating combat text consumes authoritative damage resolutions rather than inspecting HP after an
animation. A resolution records whether the hit connected, attempted and applied damage, HP before
and after, and whether the target was defeated. Whiffs, invulnerability, and zero applied damage do
not emit a number.

The default demo presentation is world-space UI above the target: a bundled rounded display font,
warm ivory-gold outgoing damage, coral incoming damage, a deep outline, a short scale punch,
bounded glyph-only micro-shake, upward drift, and opacity fade. Motion is driven solely by supplied
simulation time. Reduced-motion mode retains the value and fade but removes displacement, scale
animation, and shake. Camera shake is not part of this system.

Verification covers default-on and explicit-off authoring, invalid schema combinations, block-local
manifest parsing, deterministic motion samples, connected-hit edges, rapid-hit bounds, stage
teardown, reduced motion, font readiness, production type checking/building, and a canvas-only
1280x720 outgoing-hit sequence at impact, punch, and fade. Incoming, lethal, and disabled cases
remain deterministic contract/harness checks rather than claimed visual-capture evidence.
