# Scene profiles and gameplay components

> **Contract maturity: exact-current prepared gameplay and consumer boundary.**

The prepared game separates visual/static map composition from semantic game
use. `gameplay.toml` is the portable simulation contract; each
`maps/<map_id>.toml` supplies visual layers and static topology; the web runtime
adapts both from `prepared-game-runtime-v5` into Phaser objects.

## Ownership

| Layer | Owns | Must not own |
| --- | --- | --- |
| `game-contract-v5` | Shared identity, art direction, cast IDs, and package membership | Simulation or engine state |
| `gameplay-contract-v1` | Navigation, player start, progression, inventory semantics, combat, map use, transitions, population, loot, placements, interactions, quests, and effects | Map image generation or Phaser objects |
| `game-map-v4` | Map references/layers, binary terrain occupancy, ladder geometry/placement, and portal presentation/anchors | Movement permission, destinations, spawning, or interactions |
| Content/UI/sequence contracts | Actor/item/prop presentation, interface presentation, and authored control flow | Physics or mutable runtime state |
| Recipe and manifest | Generated artifacts, portable contract projection, digests, and provenance | Browser lifecycle or hidden gameplay defaults |
| Consumer | Rendering, input, collision, camera, audio, object lifecycle, and simulation | Missing authored semantics or generation |

## Current gameplay contract

The root source is exactly `schema_version = 1` and
`kind = "gameplay-contract-v1"`. Its main sections are:

- `entry_map_id` and `entry_spawn_id`;
- `[navigation]` with explicit movement permissions, world-wrap policy, and
  fall recovery;
- `[player]`, `[progression]`, `[inventory]`, `[combat]`, and `[combat_text]`;
- `map_uses`, `spawns`, and directional `transitions`;
- map-scoped mob-population zones and weighted actor IDs;
- boss encounters and loot rules;
- NPC and prop placements;
- interactions bound to sequence IDs; and
- quests plus typed effects.

Every map, anchor, actor, item, prop, track, sequence, quest, and effect
reference is resolved against the prepared package before provider work.

## Navigation and static topology

Movement permission and presentation coverage are separate requirements:

| Gameplay movement | Required presentation/static contract |
| --- | --- |
| `move_left`, `move_right` | Player move state and walkable occupancy |
| `jump` | Player jump state and terrain collision |
| `crouch` | Player crouch motion; V1 is a stationary feet-planted posture |
| `climb` | Player climb motion plus at least one map-local ladder placement |

The current prepared runtime constructs terrain collision from the map’s binary
occupancy and 47-mask atlas. It projects map-local ladders relative to terrain
and enables climbing only when gameplay permits it. Portal art and endpoint
anchors come from the map; destination relationships and target spawns come
from gameplay.

## Runtime composition

The prepared web scene is a consumer composition root. Its dependencies flow
from static presentation toward simulation:

```text
manifest and asset validation
  -> layer and terrain rendering
  -> terrain/platform/ladder collision
  -> player traversal and state presentation
  -> map portals and transitions
  -> NPC/prop placements and interactions
  -> population, combat, loot, inventory, quests, and effects
  -> UI, soundtrack, dialogue, death, and diagnostics
```

Map transition tears down map-scoped objects, resolves the target spawn, and
rebuilds the next map without changing game-global player/inventory/quest
state. An unsupported or malformed required contract fails closed. Missing
presentation media may use an explicit visible diagnostic fallback where the
runtime defines one; it does not disable otherwise valid gameplay semantics.

## Player state selection

The consumer chooses one semantic state from authoritative simulation:

- movement and grounded state select idle, move, jump, crouch, or climb;
- attacks and skill casts temporarily override locomotion;
- applied damage selects hurt;
- zero health selects the once-only death presentation before recovery; and
- authored playback mode determines whether selected frames hold, loop, play
  once, or follow gameplay progress.

Generation sample count is not runtime playback count. A four-frame generated
sheet may intentionally publish one held idle frame, while crouch may consume
all four canonical frames as a six-frames-per-second loop.

## Population, combat, and feedback

Population zones are gameplay-owned half-open map fractions with explicit
targets, caps, respawn delay, and weighted mob IDs. The consumer derives legal
terrain positions from occupancy, prefers appropriate offscreen placement, and
maintains the authored population without exceeding caps.

Combat resolves attempted/applied damage and defeat before presentation.
Player and mob attacks connect only when their foot coordinates are on the same
terrain/platform level or within one tile vertically; jumping above that band
is a valid dodge, and a mob does not begin a new strike while outside the band.
After a connected nonfatal hit, the player receives a fixed invulnerability
window and blinks for its duration. The hurt strip is visual feedback rather
than a stun: movement and traversal remain available while repeated hits are
rejected. Defeat alone locks player control.
Autonomous mob locomotion remains on its current terrain
shelf and turns at both rises and drops. Player-applied knockback is the only mob
movement allowed to carry it over a descending shelf edge. Returning from a
finite attack or hurt presentation must restore the looping locomotion strip.
Floating combat text consumes that resolution; whiffs, invulnerability, and
zero applied damage do not emit a number. Loot rolls reference exact authored
mob/item rules, update inventory, and can advance quest conditions. Presentation
never becomes the authority for health, defeat, inventory, or quest state.

## Verification boundary

Offline contract tests cover exact parsing, cross-reference closure, runtime
manifest admission, terrain/ladder/portal projection, state playback, combat,
population, inventory, dialogue, and teardown. Browser evidence proves selected
integration paths, but a screenshot alone does not establish simulation or
contract correctness.

See [Authored game maps](../game-maps.md),
[Canonical prepared game package](../game-package.md), and
[Canonical game-generation pipeline](game/generation-pipeline.md).
