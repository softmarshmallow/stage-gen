class_name PlayerState
extends RefCounted

## The player. Not an entity: it lives on the world and is drawn separately
## (viewer index.html:487-501).

## Position, metres.
var x: float = 0.0
var z: float = 0.0
## Velocity, metres per second.
var vx: float = 0.0
var vz: float = 0.0
## One of front / back / left / right.
var facing: String = "front"
## Animation state key into `manifest.actors[player_id].states`.
var state: String = "idle"
## Seconds in the current state.
var elapsed: float = 0.0
## `{state, elapsed, entity, interaction, spec, hits, tool_slot}` or
## `{state, elapsed, entity, take = true}`, or null when free.
var busy: Variant = null
## `{entity, stall}` — a committed walk — or null.
var approach: Variant = null
var health: float = 100.0
var hunger: float = 100.0
## The third vital: the cold takes it, a fire gives it back.
var warmth: float = 100.0
## Seconds of i-frames left.
var invulnerable: float = 0.0
## Collision radius, metres.
var radius: float = 0.34
