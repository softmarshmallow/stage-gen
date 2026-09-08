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
