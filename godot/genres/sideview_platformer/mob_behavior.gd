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
