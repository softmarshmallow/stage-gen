# Scene profiles and gameplay components

> **Checked by:** `tests/contract/test_current_game_docs.py`.

> **Contract maturity: exact-current prepared gameplay and consumer boundary.**

The prepared game separates visual/static map composition from semantic game
use. `gameplay.toml` is the portable simulation contract; each
`maps/<map_id>.toml` supplies visual layers and static topology; the web runtime
adapts both from `prepared-game-runtime-v12` into Phaser objects.

## Ownership

| Layer | Owns | Must not own |
| --- | --- | --- |
| `game-contract-v9` | Shared identity, art direction, genre members carrying presentation, cast IDs, and package membership | Simulation or engine state |
| `gameplay-contract-v1` | Navigation, player start, progression, inventory semantics, combat, map use, transitions, population, loot, placements, interactions, quests, and effects | Map image generation or Phaser objects |
| `game-map-v10` | Map references/layers, per-layer runtime presentation, the terrain request a generator answers, the climbable roster, and portal presentation/anchors | Movement permission, destinations, spawning, interactions, or the generated geometry itself |
| `map-terrain-v1` | Generated occupancy, walk-surface row, and climbable placements for one map | Any authored intent; it is an artifact, not a source |
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
| `crouch` | Player crouch motion; grounded Left/Right movement uses the slower crouch speed |
| `climb` | A player climb motion per placed climbable role plus at least one map-local climbable placement |

The current prepared runtime constructs terrain collision from the map’s binary
occupancy and 47-mask atlas. It projects map-local ladders relative to terrain
and enables climbing only when gameplay permits it. Upward input may attach an
airborne player anywhere inside the ladder's horizontal activation width and
vertical span. Jumping from ladder support returns to ordinary air support, so
the same rule naturally permits a later airborne re-grab; ladder attachment
resets the ordinary air-jump budget like any other stable support. Portal art and endpoint
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

Layer contrast, saturation, atmospheric wash, and detail blur are consumer-only
presentation. The browser transforms each decoded repeat texture once, wraps
blur sampling on the seamless X axis, clamps on Y, and preserves source alpha.
Global contact shadows are likewise runtime-only: they follow the terrain
surface under players, NPCs, mobs, and props and soften or contract with height.
Neither treatment enters an image prompt or provider cache identity.

Interaction affordances belong to their world target. The active portal owns
its world-anchored entry prompt, and the nearest NPC with an authored sequence
owns the matching world-anchored talk prompt above its name. The prepared scene
does not use a shared screen-center interaction label.

The top-left HP/inventory text is a consumer debugging layer, not gameplay UI.
It is hidden by default and toggles only through Command+Backtick. The player
health bar and inventory panel remain the authoritative gameplay presentation.
When a run publishes more than one playable kit the overlay also names the one
in force and marks it as an override when it is not the published one.

The kit itself is selectable in the consumer, and only there. A developer may
play one published run as any kit that run can actually support, through the
console below the canvas or by cycling with K; both reach one scene entry point,
so there is no second version of the switch that could drift from the first. The
switch acts on the running scene rather than reloading it. The override never
reaches the parsed gameplay contract: it applies where the runtime decides which
class it is holding, so the manifest, its digests and every artifact stay exactly
the bytes the pipeline wrote. It is refused outright under fixed-frame automation, because
a capture is a recording of one published run and its transcript carries no
record of an override. What is offered comes from what the run published - a run
that drew no projectile has one kit and no console - and the runtime never
invents a projectile binding the contract did not name.

## Player state selection

The consumer chooses one semantic state from authoritative simulation:

- movement and grounded state select idle, move, jump, crouch, or climb;
- attacks and skill casts temporarily override locomotion, and the published
  weapon class decides which of the two poses an attack plays;
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
maintains the authored population without exceeding caps. Spawn zones own
placement and population lifecycle only; they do not own an actor's pursuit
navigation.

Combat resolves attempted/applied damage and defeat before presentation.
Gameplay publishes a weapon class, not a reach: the consumer owns what each
named class costs in damage, cadence, distance, and how a blow is delivered.

A class that strikes instantly connects only when the attacker's and target's
foot coordinates are on the same terrain/platform level or within one tile
vertically; jumping above that band is a valid dodge. A class that throws
resolves against the thrown object's own position instead, because foot level
describes a reach the attacker has already let go of. Mob attacks are always
instant and always foot-banded, and a mob does not begin a new strike while
outside the band.

A throwing class must name the catalog item it puts in the air, and the
consumer refuses a package whose named item is absent from the published
catalog.
After a connected nonfatal hit, the player receives a fixed invulnerability
window and blinks for its duration. The hurt strip is visual feedback rather
than a stun: movement and traversal remain available while repeated hits are
rejected. Defeat alone locks player control.
Autonomous mob locomotion remains on its current terrain
shelf and turns at both rises and drops. Player-applied knockback is the only mob
movement allowed to carry it over a descending shelf edge. After such forced
displacement settles, the mob adopts the disconnected landing shelf as its new
local home because autonomous movement cannot jump or climb back to the authored
spawn shelf. Deterministic reset still restores the authored spawn territory.
Displacement that remains on the same connected shelf does not change home;
boundary resolution permits normal-speed inward travel and blocks further
outward travel, rather than clamping the actor back to the home range in one
frame.
Returning from a finite attack or hurt presentation must restore the looping
locomotion strip.
Mob actors compose stateful class-based behavior nodes for independently tunable
decisions. A terrain-lane navigation node derives one connected shelf from
occupancy; rises, drops, pits, and world edges terminate it, while ladder metadata
is deliberately irrelevant. Within that shelf, separate in-code boundaries own
the natural patrol radius and pursuit territory. These current movement values
are consumer policy, not authored `gameplay.toml` tuning.

The awareness node acquires the player inside its aggression and pursuit bounds.
When either interest or pursuit territory ends, it emits `return_home`; a
dedicated return node selects the spawn point and walks there before normal
patrol resumes. A mob therefore never stands indefinitely at its pursuit edge.
Direct pursuit targets the player only while their terrain levels can interact;
otherwise the pursuit-target node sweeps between points on either side of the
player, using an arrival radius and remembered target side so crossing the
player's exact X cannot reverse facing every frame. Blocked-side memory tries an
alternate route once and holds a stable facing when both directions are blocked;
successful travel makes that side eligible again. Each mob samples bounded
deterministic per-instance variation once at spawn for movement speed,
pursuit-corridor width, and initial target side. Runtime updates never sample
random frame noise, so mobs separate naturally without visual jitter or
nondeterministic replays. A separate action-timing node samples bounded wind-up
and cooldown variation once per committed attack, preventing multiple nearby
mobs from repeatedly acting on the same frames while preserving deterministic
replay and automation. The interval after a strike is an explicit
`attack_recovery` state; it preserves the committed attack facing and cannot
fall through to patrol while the cooldown is active.

A dedicated facing node is the sole authority for mob sprite mirroring.
Navigation nodes request movement, while locomotion facing follows only the
displacement that terrain resolution actually applied. Blocked movement cannot
turn the sprite. Combat can explicitly face a target, but target movement inside
a small in-code dead zone preserves the current direction. Patrol heading and
visual facing are separate state, so a trapped actor may reconsider movement
without visibly reversing every frame. These are consumer stability policies,
not authored generation controls.
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
