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
