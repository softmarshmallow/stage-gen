class_name PlatformerCombat
extends RefCounted

## What a creature is like, and what a blow costs.
##
## A port of the rules half of `web/lib/sideview-platformer/combat.ts`. An
## aggression is a whole temperament rather than a speed: how far it notices, how
## fast it closes, how long it winds up, what it does when hurt, and how much
## two creatures of one kind are allowed to differ from each other.

## Horizontal shove applied to the player on a hit, in pixels per second.
const PLAYER_KNOCKBACK_VX := 260.0
## Upward component, so a blow lifts the player slightly rather than sliding
## them along the floor.
const PLAYER_KNOCKBACK_VY := -180.0

const DEFAULT_AGGRESSION := "territorial"

## Every temperament a creature may be declared with.
const PROFILES := {
	# The one that does not fight at all, and the archetype a creature gets when
	# its rank does not earn it another. `hostile` false is the first rung of the
	# intent ladder, so a passive creature never chases, never swings and does no
	# damage — and the whole roster of common things on a route is passive.
	"passive": {
		"aggroRadiusPx": 64.0,
		"chaseSpeedPx": 48.0,
		"strikeRangePx": 0.0,
		"windupMs": 0.0,
		"cooldownMs": 0.0,
		"damage": 0.0,
		"flees": false,
		"hostile": false,
		"inaccessibleSweepHalfWidthPx": 96.0,
		"pursuitArrivalRadiusPx": 12.0,
		"movementSpeedVarianceRatio": 0.1,
		"pursuitSweepVarianceRatio": 0.2,
		"actionTimingVarianceRatio": 0.0,
	},
	"skittish": {
		"aggroRadiusPx": 192.0,
		"chaseSpeedPx": 96.0,
		"strikeRangePx": 0.0,
		"windupMs": 0.0,
		"cooldownMs": 0.0,
		"damage": 0.0,
		"flees": true,
		"hostile": true,
		"inaccessibleSweepHalfWidthPx": 96.0,
		"pursuitArrivalRadiusPx": 12.0,
		"movementSpeedVarianceRatio": 0.1,
		"pursuitSweepVarianceRatio": 0.2,
		"actionTimingVarianceRatio": 0.0,
	},
	"territorial": {
		"aggroRadiusPx": 256.0,
		"chaseSpeedPx": 72.0,
		"strikeRangePx": 72.0,
		"windupMs": 320.0,
		"cooldownMs": 1400.0,
		"damage": 1.0,
		"flees": false,
		"hostile": true,
		"inaccessibleSweepHalfWidthPx": 96.0,
		"pursuitArrivalRadiusPx": 12.0,
		"movementSpeedVarianceRatio": 0.1,
		"pursuitSweepVarianceRatio": 0.2,
		"actionTimingVarianceRatio": 0.2,
	},
	"hunting": {
		"aggroRadiusPx": 448.0,
		"chaseSpeedPx": 108.0,
		"strikeRangePx": 80.0,
		"windupMs": 260.0,
		"cooldownMs": 1100.0,
		"damage": 1.0,
		"flees": false,
		"hostile": true,
		"inaccessibleSweepHalfWidthPx": 112.0,
		"pursuitArrivalRadiusPx": 12.0,
		"movementSpeedVarianceRatio": 0.12,
		"pursuitSweepVarianceRatio": 0.24,
		"actionTimingVarianceRatio": 0.16,
	},
	"relentless": {
		"aggroRadiusPx": 768.0,
		"chaseSpeedPx": 132.0,
		"strikeRangePx": 88.0,
		"windupMs": 200.0,
		"cooldownMs": 900.0,
		"damage": 2.0,
		"flees": false,
		"hostile": true,
		"inaccessibleSweepHalfWidthPx": 128.0,
		"pursuitArrivalRadiusPx": 12.0,
		"movementSpeedVarianceRatio": 0.14,
		"pursuitSweepVarianceRatio": 0.28,
		"actionTimingVarianceRatio": 0.12,
	},
}


static func profile(aggression: Variant) -> Dictionary:
	var name := DEFAULT_AGGRESSION if aggression == null else String(aggression)
	return PROFILES.get(name, PROFILES[DEFAULT_AGGRESSION])


## The critical profiles a package may name: how often a blow doubles, and by
## how much.
const CRITICAL_PROFILES := {
	"none": {"chance": 0.0, "multiplier": 1.0},
	"rare_v1": {"chance": 0.06, "multiplier": 2.5},
	"standard_v1": {"chance": 0.18, "multiplier": 2.0},
	"frequent_v1": {"chance": 0.32, "multiplier": 1.75},
}


## The seed one blow is drawn against: the sequence, where it was struck, and
## who it was struck on.
##
## Every blow in a run draws once from a counter that never resets, so two blows
## on the same creature at the same place still differ — which is what stops a
## critical from being a property of a position.
static func blow_seed(sequence: int, x: float, target_index: int) -> int:
	return (
		(
			KernelHash.imul(sequence, 2654435761)
			+ KernelHash.imul(int(x), 2246822519)
			+ KernelHash.imul(target_index + 1, 3266489917)
		)
		& KernelHash.MASK
	)


## Whether one blow lands double, and what it lands for.
static func critical_damage(base_amount: float, profile_name: String, seed_value: int) -> Dictionary:
	if base_amount <= 0.0:
		return {"amount": base_amount, "critical": false}
	var rule: Dictionary = CRITICAL_PROFILES.get(profile_name, CRITICAL_PROFILES["none"])
	var chance := float(rule["chance"])
	if chance <= 0.0 or unit_roll(seed_value) >= chance:
		return {"amount": base_amount, "critical": false}
	return {
		"amount": maxf(1.0, round(base_amount * float(rule["multiplier"]))), "critical": true
	}


## One draw on [0, 1) from a blow's seed. Not a generator: a blow is drawn from
## its own seed rather than from a stream, so the order blows are resolved in
## cannot change what any one of them rolls.
static func unit_roll(seed_value: int) -> float:
	var mixed := seed_value & KernelHash.MASK
	mixed = (mixed ^ (mixed >> 16)) & KernelHash.MASK
	mixed = KernelHash.imul(mixed, 0x7feb352d)
	mixed = (mixed ^ (mixed >> 15)) & KernelHash.MASK
	mixed = KernelHash.imul(mixed, 0x846ca68b)
	mixed = (mixed ^ (mixed >> 16)) & KernelHash.MASK
	return float(mixed) / 4294967296.0
