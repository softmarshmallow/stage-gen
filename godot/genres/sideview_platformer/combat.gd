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
