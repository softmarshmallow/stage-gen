class_name PlatformerMobBehavior
extends RefCounted

## How one creature differs from the next of its kind.
##
## A port of `MobBehaviorVariation` in
## `web/lib/sideview-platformer/mob-behavior.ts`. The values are sampled **once**
## from a per-instance seed rather than once per frame, and that is the whole
## point: per-frame randomness makes sprites jitter and makes replays diverge,
## while per-instance variation gives each creature its own tempo and patrol
## width and stays reproducible.
##
## The noise is this module's own — a different mixer from the particle family's,
## kept because changing it would move every creature that has ever been spawned
## from a given seed.

const MASK := 0xFFFFFFFF
const DIVISOR := 4294967296.0

const CHANNEL_SPEED := 0x243f6a88
const CHANNEL_SWEEP := 0x85a308d3
const CHANNEL_DIRECTION := 0x13198a2e
const CHANNEL_WINDUP := 0xa4093822
const CHANNEL_COOLDOWN := 0x299f31d0

## The golden ratio in 32 bits, which is what turns one creature's seed into a
## different draw for each action it commits.
const SEQUENCE_MIX := 0x9e3779b1


## The per-instance seed, when the spawner does not hand one down.
static func seed_for(spawn_column: int, ladder_index: int) -> int:
	return (
		KernelHash.imul(spawn_column + 1, 0x45d9f3b)
		^ KernelHash.imul(ladder_index + 1, 0x119de1f3)
	) & MASK


## `{movementSpeedScale, pursuitSweepScale, initialDirection}` for one creature.
static func variation(seed_value: int, profile: Dictionary) -> Dictionary:
	return {
		"movementSpeedScale": _symmetric(
			unit_noise(seed_value, CHANNEL_SPEED),
			float(profile["movementSpeedVarianceRatio"])
		),
		"pursuitSweepScale": _symmetric(
			unit_noise(seed_value, CHANNEL_SWEEP),
			float(profile["pursuitSweepVarianceRatio"])
		),
		"initialDirection": -1 if unit_noise(seed_value, CHANNEL_DIRECTION) < 0.5 else 1,
	}


static func unit_noise(seed_value: int, channel: int) -> float:
	var value := (seed_value ^ channel) & MASK
	value = KernelHash.imul(value ^ (value >> 16), 0x7feb352d)
	value = KernelHash.imul(value ^ (value >> 15), 0x846ca68b)
	value = (value ^ (value >> 16)) & MASK
	return float(value) / DIVISOR


static func _symmetric(unit: float, variance: float) -> float:
	return 1.0 + (unit * 2.0 - 1.0) * variance


## How long the `sequence`-th action of this creature takes, counting from zero.
##
## Drawn once per committed action rather than once per creature, and both halves
## come off the one draw index, so a swing and the pause after it move together.
## Two creatures of a kind, born in different columns, never wind up in lockstep —
## which is the whole reason the number is not simply the profile's.
##
## Rounded rather than floored, and the rounding is the browser's: half goes up.
## Both delays are non-negative, so away-from-zero and towards-positive agree, and
## the distinction only matters if a profile ever publishes a negative one.
static func action_timing(
	seed_value: int, sequence: int, windup_ms: float, cooldown_ms: float, variance: float
) -> Dictionary:
	var mixed := (seed_value ^ KernelHash.imul(sequence + 1, SEQUENCE_MIX)) & MASK
	return {
		"windupMs": roundf(windup_ms * _symmetric(unit_noise(mixed, CHANNEL_WINDUP), variance)),
		"cooldownMs": roundf(
			cooldown_ms * _symmetric(unit_noise(mixed, CHANNEL_COOLDOWN), variance)
		),
	}


## Which way a creature is looking, and what may change it.
##
## Two ways in, and they are not the same. A *deliberate* turn — a swing, a
## flinch — comes with a target and has a dead zone: a body crossing the
## creature's own x does not flip it every frame. An *incidental* turn follows
## the displacement navigation actually allowed, so a step a terrain face refused
## leaves the pose untouched while a step that moved the body turns it.
const FACING_TARGET_DEADZONE_PX := 8.0
const FACING_MOVEMENT_EPSILON_PX := 0.01


## Turn towards a target, unless it is inside the dead zone.
static func face_target(facing: int, from_x: float, target_x: float) -> int:
	var delta := target_x - from_x
	if absf(delta) > FACING_TARGET_DEADZONE_PX:
		return 1 if delta > 0.0 else -1
	return facing


## Turn with the movement that survived navigation.
static func follow_movement(facing: int, previous_x: float, current_x: float) -> int:
	var delta := current_x - previous_x
	if absf(delta) > FACING_MOVEMENT_EPSILON_PX:
		return 1 if delta > 0.0 else -1
	return facing


## Which way a struck creature looks: at whoever swung, which is the opposite of
## the way the blow threw it.
static func hit_facing(knockback_direction: int) -> int:
	return -1 if knockback_direction == 1 else 1


## Where a creature walking home goes this step, never past home.
##
## `{targetX, direction, arrived}`. The overshoot clamp is what stops a fast
## creature oscillating around its own doorstep for the rest of the run.
static func return_home_step(
	home_x: float, mob_x: float, arrival_radius: float, speed_px: float, speed_scale: float,
	dt_seconds: float
) -> Dictionary:
	var delta := home_x - mob_x
	var direction := 1 if delta >= 0.0 else -1
	if absf(delta) <= arrival_radius:
		return {"targetX": home_x, "direction": direction, "arrived": true}
	var distance := minf(absf(delta), speed_px * speed_scale * dt_seconds)
	return {
		"targetX": mob_x + float(direction) * distance,
		"direction": direction,
		"arrived": is_equal_approx(distance, absf(delta)),
	}


## Where a chasing creature actually walks to.
##
## A creature that cannot reach the player's foot level must not seek the
## player's exact x: doing so crosses that one coordinate every step and reverses
## the pose every frame. Instead it remembers one side of a corridor around the
## player, walks *through* the player to that endpoint, and takes the other side
## on arrival. The side it starts on is its own current facing, so a group
## arriving together does not collapse onto one flank.
##
## `pursuit` is the creature's own memory — `{side, blocked}` — and is written in
## place. Returns `{targetX, direction, sweeping}`.
static func pursuit_target(
	pursuit: Dictionary,
	mob_x: float,
	player_x: float,
	attack_level_reachable: bool,
	facing: int,
	half_width: float,
	arrival_radius: float
) -> Dictionary:
	if attack_level_reachable:
		reset_pursuit(pursuit)
		return {
			"targetX": player_x,
			"direction": _toward(mob_x, player_x, facing),
			"sweeping": false,
		}
	if pursuit.get("side") == null:
		pursuit["side"] = facing
	var side := int(pursuit["side"])
	var target := player_x + float(side) * half_width
	var reached := (
		mob_x >= target - arrival_radius if side == 1 else mob_x <= target + arrival_radius
	)
	if reached:
		side = -side
		pursuit["side"] = side
		target = player_x + float(side) * half_width
	return {
		"targetX": target,
		"direction": _toward(mob_x, target, facing),
		"sweeping": true,
	}


## A terrain face invalidates the endpoint the creature was walking to: mark this
## side, take the alternate once, and hold rather than oscillate when both fail.
static func report_pursuit_blocked(pursuit: Dictionary) -> void:
	if pursuit.get("side") == null:
		return
	var side := int(pursuit["side"])
	var blocked: Dictionary = pursuit["blocked"]
	blocked[side] = true
	if not blocked.has(-side):
		pursuit["side"] = -side


## Travel that actually happened proves the current side is viable again.
static func report_pursuit_progress(pursuit: Dictionary) -> void:
	if pursuit.get("side") == null:
		return
	(pursuit["blocked"] as Dictionary).erase(int(pursuit["side"]))


static func reset_pursuit(pursuit: Dictionary) -> void:
	pursuit["side"] = null
	pursuit["blocked"] = {}


static func _toward(from_x: float, target_x: float, fallback: int) -> int:
	if is_equal_approx(target_x, from_x):
		return fallback
	return 1 if target_x > from_x else -1
