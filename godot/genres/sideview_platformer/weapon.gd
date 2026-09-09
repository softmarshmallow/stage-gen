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
##
## Two of the fields are read by nothing that fights: `standOffTiles` is where an
## automated policy stands to use the class and `ammoKind` is what one action
## spends, and both are here rather than in the policy because the reach a bot
## aims for and the reach the runtime resolves are the same number and must not
## become two.

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
		"verticalTiles": 1.0,
		"maxTargetsPerAction": 1,
		"hitsPerAction": 1,
		"hitIntervalMs": 0.0,
		"ammoKind": "",
		# Deliberately shorter than the swing's own 1.4-tile band: a policy walks
		# to a comfortable distance rather than standing at the very edge of its
		# reach and missing whenever the target drifts. A minimum of zero is what
		# keeps it walking all the way in — no distance is too close for a swing.
		"standOffTiles": {"minimum": 0.0, "approach": 0.65625, "maximum": 1.3125},
	},
	"melee_sweep_v1":
	{
		"motionState": "basic_attack",
		"pose": "attack",
		"damage": 1.0,
		"actionDurationMs": 333.0,
		"hitWindowFromMs": 80.0,
		"hitWindowToMs": 250.0,
		"delivery": "instant",
		"reachTiles": 3.0,
		"verticalTiles": 1.0,
		# A sweep is three blows inside one swing, forty-five milliseconds apart,
		# each of which may take up to six creatures. That is the whole
		# difference from `melee_dps_v1`: the same damage, spread over a crowd.
		"maxTargetsPerAction": 6,
		"hitsPerAction": 3,
		"hitIntervalMs": 45.0,
		"ammoKind": "",
		# Wider in step with the reach, so a policy swings from where the band
		# actually connects rather than walking into contact first.
		"standOffTiles": {"minimum": 0.0, "approach": 1.4, "maximum": 2.6},
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
		# A flat throw reaches asymmetrically — the round leaves at chest height,
		# so it clears more above a target than below — and a rule that has to
		# answer before anything is in the air cannot be asymmetric. This is the
		# symmetric band inscribed in it.
		"verticalTiles": 1.2,
		"maxTargetsPerAction": 1,
		"hitsPerAction": 1,
		"hitIntervalMs": 0.0,
		# Empty in this revision. The selector, the spend and the automated
		# decline are all built, but arming them needs a package whose loot rules
		# actually sustain a throw.
		"ammoKind": "",
		# 2.5 tiles is 160px, outside the longest strike range any aggression
		# archetype has once the targeting tolerance is applied, so a policy
		# holding this band stands beyond every creature's swing. `approach`
		# equals `maximum` on purpose: a throw does not improve by walking closer,
		# so a target anywhere in the band is attacked from where the character
		# already stands.
		"standOffTiles": {"minimum": 2.5, "approach": 5.5, "maximum": 5.5},
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


## Which of `targets` one instant blow reaches, in the caller's own order.
##
## A port of `resolveInstantStrike` in `web/lib/sideview-platformer/strike.ts`.
## The band is centred half a reach ahead of the body rather than on it, so a
## swing covers what is in front and nothing behind — and the order is the
## caller's rather than the nearest, because a replay that picked the
## geometrically nearest target would diverge the moment two creatures stood at
## one distance.
##
## `targets` is `[{x, footY}]`. Returns indices into it.
static func instant_targets(
	weapon: Dictionary, attacker_x: float, attacker_foot_y: float, dir_sign: int, targets: Array
) -> Array:
	if String(weapon["delivery"]) != "instant":
		return []
	var reach := PlatformerMaps.TILE_PX * float(weapon["reachTiles"])
	var band_centre := attacker_x + float(dir_sign) * reach * 0.5
	var vertical := PlatformerMaps.TILE_PX * float(weapon["verticalTiles"])
	var hits: Array = []
	for index in range(targets.size()):
		var target: Dictionary = targets[index]
		if absf(float(target["x"]) - band_centre) >= reach:
			continue
		if absf(attacker_foot_y - float(target["footY"])) > vertical:
			continue
		hits.append(index)
		if hits.size() >= int(weapon["maxTargetsPerAction"]):
			break
	return hits
