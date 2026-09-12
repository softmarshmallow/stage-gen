class_name PlatformerNumberScale
extends RefCounted

## How big the numbers are.
##
## A port of `web/lib/sideview-platformer/number-scale.ts`. The generator
## publishes a *scale name* per package and no numbers, in the shape the critical
## profile and the weapon class already use: whether a common creature has three
## hit points or three hundred is how the game feels, which the consumer owns.
##
## `arcade_v1` is the action-RPG read: the same fight in hundreds, with a little
## per-blow variance so a column of numbers is a column of different numbers. It
## scales the player's blows and the creatures' pools by one factor, so balance is
## exactly what it was at unit scale and only the digits changed. It deliberately
## does not touch the creatures' blows or the player's pool: those are the
## aggression table's and progression's, and a package that wanted the whole fight
## in hundreds would name a second scale that says so rather than have this one
## silently widen.
##
## Every package published before the field existed reads `unit_v1`, the identity,
## so nothing already shipped plays differently — which is also why the parity
## fixture, published at unit scale, could not have caught this file's absence.

const UNIT := "unit_v1"
const ARCADE := "arcade_v1"

## `factor` multiplies outgoing damage and creature health alike; `varianceRatio`
## is the symmetric per-blow variation on outgoing damage, as a ratio around one,
## and zero is exact.
const SCALES := {
	UNIT: {"factor": 1.0, "varianceRatio": 0.0},
	ARCADE: {"factor": 100.0, "varianceRatio": 0.12},
}

## The default when a package publishes no scale — every run predating the field.
const DEFAULT_SCALE := UNIT

## A channel of its own, so the variance and the critical are drawn from the same
## blow seed without agreeing with each other.
const VARIANCE_CHANNEL := 0x5bd1e995


## The profile a package named, or the identity when it named none or one this
## build does not know. An unrecognised name plays at unit scale rather than
## refusing: a scale the runtime has not caught up with is not a game worth
## stopping.
static func profile(name: String) -> Dictionary:
	return SCALES.get(name, SCALES[DEFAULT_SCALE])


## The profile a package's combat block asks for.
static func profile_of(combat: Dictionary) -> Dictionary:
	return profile(str(combat.get("number_scale", DEFAULT_SCALE)))


## One blow's base damage at this scale, before the critical roll.
##
## Seeded from the same blow seed the critical uses, on a different channel, so a
## replayed run rolls the same variance and the same critical for the same blow.
## Rounded and floored at one, as the critical multiplier is, so scaling can never
## round a landed blow away to nothing. The unit scale returns its input
## untouched, which is what keeps every older package's arithmetic exact.
static func outgoing_damage(base_amount: float, scale: Dictionary, seed_value: int) -> float:
	if base_amount <= 0.0:
		return base_amount
	var factor := float(scale["factor"])
	var variance := float(scale["varianceRatio"])
	if is_equal_approx(factor, 1.0) and is_zero_approx(variance):
		return base_amount
	var roll := PlatformerCombat.unit_roll((seed_value ^ VARIANCE_CHANNEL) & KernelHash.MASK)
	return maxf(1.0, round(base_amount * factor * (1.0 + (roll * 2.0 - 1.0) * variance)))


## A creature's health pool at this scale. Exact, so the ladder between ranks is
## preserved.
static func mob_health(base_health: int, scale: Dictionary) -> int:
	if base_health <= 0:
		return base_health
	return int(round(float(base_health) * float(scale["factor"])))
