class_name PlatformerProgression
extends RefCounted

## What a run has earned, and what the next rank costs.
##
## A port of the rules half of `web/lib/sideview-platformer/progression.ts`. The
## gameplay contract names a curve and a growth — `experience_curve` and
## `stat_growth` — and stops there, so the numbers behind those names live in
## one place and a package that names a curve nobody implements is refused
## rather than levelled on a guess.
##
## A genre module rather than a family: levelling is not genre-neutral until a
## second genre asks for it, and none has. The host contract's charter is that a
## system with one consumer stays that genre's and is promoted when a second
## arrives.

## `base_cost` is what the first level-up costs; `growth` multiplies each
## successive one. Gentle is roughly nine common kills to level two, and the
## climb doubles every three levels.
const CURVES := {
	"gentle_rpg_v1": {"base_cost": 24.0, "growth": 1.28},
	"steady_rpg_v1": {"base_cost": 32.0, "growth": 1.4},
	"brisk_rpg_v1": {"base_cost": 16.0, "growth": 1.18},
}

const DEFAULT_GROWTH := "balanced_novice_v1"

## A published string field, or the fallback.
##
## `String(x)` is not a cast in GDScript — it is a constructor, and it does not
## exist for null. A package may publish a field as null rather than omitting it,
## and `Dictionary.get`'s default only fires on a *missing* key, so the pair took
## a whole run down at the first creature that carried an explicit null.
static func named(source: Dictionary, key: String, fallback: String) -> String:
	var value: Variant = source.get(key)
	return value if value is String else fallback


## What one kill is worth, by the rank the package already publishes for it. A
## game earns experience in proportion to what it actually fought without
## authoring a second set of numbers, and an unrecognised rank is worth the
## common award rather than nothing — a rank the runtime has not caught up with
## is not a creature worth zero.
const AWARD_BY_RANK := {"boss": 90, "elite": 30, "uncommon": 12}
const DEFAULT_AWARD := 6


## What killing this creature is worth.
static func award_for_rank(rank: String) -> int:
	return int(AWARD_BY_RANK.get(rank, DEFAULT_AWARD))


## Bank a kill and settle whatever it buys. Returns
## `{awarded, levelsGained, state}`; a disabled progression awards nothing and
## hands the state back untouched.
static func grant(state: Dictionary, amount: int, policy: Dictionary, base_health: int) -> Dictionary:
	if not bool(policy.get("enabled", false)) or amount <= 0:
		return {"awarded": 0, "levelsGained": 0, "state": state}
	var maximum_level := int(policy.get("maximum_level", 1))
	var curve := String(policy.get("experience_curve", ""))
	var level := int(state["level"])
	var into_level := int(state["experienceIntoLevel"]) + amount
	var for_next: Variant = state["experienceForNext"]
	var levels := 0
	while for_next != null and into_level >= int(for_next) and level < maximum_level:
		into_level -= int(for_next)
		level += 1
		levels += 1
		for_next = null
		if level < maximum_level:
			var cost: Variant = cost_of_next(level, curve)
			for_next = null if KernelRefusal.is_refusal(cost) else cost
	# A body at the ceiling banks nothing towards a level it can never reach.
	if for_next == null:
		into_level = 0
	var pool: Variant = maximum_health(
		base_health, level, named(policy, "stat_growth", DEFAULT_GROWTH)
	)
	return {
		"awarded": amount,
		"levelsGained": levels,
		"state":
		{
			"level": level,
			"experienceIntoLevel": into_level,
			"experienceForNext": for_next,
			"totalExperience": int(state["totalExperience"]) + amount,
			"maximumHealth": base_health if KernelRefusal.is_refusal(pool) else int(pool),
		},
	}


## What the step from `level` to the one above it costs, or a refusal.
static func cost_of_next(level: int, curve: String) -> Variant:
	if level < 1:
		return KernelRefusal.of(
			"platformer/progression", "an experience cost needs a level of at least one"
		)
	if not CURVES.has(curve):
		return KernelRefusal.of(
			"platformer/progression", "unknown experience curve %s" % curve, "experience_curve"
		)
	var rule: Dictionary = CURVES[curve]
	return int(round(float(rule["base_cost"]) * pow(float(rule["growth"]), float(level - 1))))


## The health pool a body of this rank carries, or a refusal.
##
## A fifth of the authored pool per level, never less than one: a growth that
## rounded to nothing would make levelling a body with a small pool free.
static func maximum_health(base_health: int, level: int, growth: String = DEFAULT_GROWTH) -> Variant:
	if base_health < 1:
		return KernelRefusal.of(
			"platformer/progression", "stat growth needs a positive authored health pool"
		)
	if level < 1:
		return KernelRefusal.of(
			"platformer/progression", "stat growth needs a level of at least one"
		)
	if growth != DEFAULT_GROWTH:
		return KernelRefusal.of(
			"platformer/progression", "unknown stat growth %s" % growth, "stat_growth"
		)
	var per_level := maxi(1, int(round(float(base_health) * 0.2)))
	return base_health + (level - 1) * per_level
