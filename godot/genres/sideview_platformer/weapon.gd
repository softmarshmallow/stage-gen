class_name PlatformerWeapon
extends RefCounted

## What the player swings or throws, and when the blow leaves.
##
## A port of the rules half of `web/lib/sideview-platformer/weapon-class.ts` and
## `attack-window.ts`. The generator publishes a class *name* per package and the
## runtime tables what it means, which is the same division the aggression
## profiles keep: a package names what it authored, and what that word is worth
## is the consumer's.
##
## Two classes, and the difference that matters is not damage — both deal one —
## but where the blow lands and how long committing to it costs. A swing reaches
## a tile and a half and is over in a third of a second; a throw commits for four
## tenths and the object leaves the hand on the release frame, which is why its
## window opens twice as late.

const CLASSES := {
	"melee_dps_v1":
	{
		"motionState": "basic_attack",
		"pose": "attack",
		"damage": 1.0,
		"actionDurationMs": 333.0,
		"hitWindowFromMs": 80.0,
		"hitWindowToMs": 250.0,
		"delivery": "instant",
		"reachTiles": 1.4,
		"maxTargetsPerAction": 1,
		"hitsPerAction": 1,
		"hitIntervalMs": 0.0,
	},
	"ranged_dps_v1":
	{
		"motionState": "skill_cast",
		"pose": "ranged_attack",
		"damage": 1.0,
		# Four frames at the ten per second the cast is authored at: a throw is
		# genuinely slower to commit to than a swing, which is what pays for the
		# reach.
		"actionDurationMs": 400.0,
		"hitWindowFromMs": 160.0,
		"hitWindowToMs": 260.0,
		"delivery": "projectile",
		"reachTiles": 0.0,
		"maxTargetsPerAction": 1,
		"hitsPerAction": 1,
		"hitIntervalMs": 0.0,
	},
}

const DEFAULT_CLASS := "melee_dps_v1"


static func profile(weapon_class: String) -> Dictionary:
	return CLASSES.get(weapon_class, CLASSES[DEFAULT_CLASS])


## One frame of the attack window.
##
## Returns `{attackUntil, attackStarted, attacking, committed, attackActive}`.
## `attacking` is the pose — the whole action — and `attackActive` is the slice
## of it during which a blow may land, which is why a throw looks like a throw
## for four hundred milliseconds and can only release for a hundred of them.
static func step_window(
	weapon: Dictionary, state: Dictionary, now_ms: float, requested: bool, blocked: bool
) -> Dictionary:
	var committed := (
		requested
		and not blocked
		and not bool(state["attackActive"])
		and now_ms >= float(state["attackUntil"])
	)
	var until := (
		now_ms + float(weapon["actionDurationMs"]) if committed else float(state["attackUntil"])
	)
	var started := now_ms if committed else float(state["attackStarted"])
	var attacking := now_ms < until
	var elapsed := now_ms - started
	return {
		"attackUntil": until,
		"attackStarted": started,
		"attacking": attacking,
		"committed": committed,
		"attackActive": (
			attacking
			and elapsed >= float(weapon["hitWindowFromMs"])
			and elapsed <= float(weapon["hitWindowToMs"])
		),
	}


## The index of the blow due now, or -1 when none is.
##
## A single-blow class is the degenerate case: tick zero is due the moment the
## window opens and nothing follows it. At most one tick per call, so a long
## frame spreads a combo over frames rather than collapsing it into one — which
## is what keeps the numbers readable as separate blows.
static func next_hit_tick(
	weapon: Dictionary, state: Dictionary, now_ms: float, ticks_fired: int
) -> int:
	if not bool(state["attackActive"]):
		return -1
	if ticks_fired < 0 or ticks_fired >= int(weapon["hitsPerAction"]):
		return -1
	var elapsed := now_ms - float(state["attackStarted"])
	var due_at := float(weapon["hitWindowFromMs"]) + float(ticks_fired) * float(weapon["hitIntervalMs"])
	if elapsed < due_at or elapsed > float(weapon["hitWindowToMs"]):
		return -1
	return ticks_fired
