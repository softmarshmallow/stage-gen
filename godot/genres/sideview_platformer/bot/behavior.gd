class_name PlatformerBotKernel
extends RefCounted

## The bot kernel — what a behaviour is, and how one of them wins the frame.
##
## A port of `web/lib/sideview-platformer/bot-behavior.ts`. This file holds no
## opinions about hunting, healing, or any other thing a character might do. It
## defines the contract those opinions are written against and the rule that
## arbitrates between them, and nothing else. That separation is the whole reason
## the system can grow: a new behaviour is a new entry in a roster, and no
## existing line changes.
##
## Arbitration is the `actor-ai` family's priority auction, not a state machine.
## The cost of the auction is that behaviours cannot cooperate within a frame —
## one of them owns the intent — and that is a price worth paying at this size.
##
## Determinism is a hard requirement, not a preference: this runtime verifies
## itself by replaying a fixed-step transcript and comparing frame hashes. Nothing
## here consults a clock it was not handed or a random number at all. Ties break on
## roster order, which is stable.
##
## A behaviour is `{id, consider: Callable(context) -> Dictionary}` and returns an
## empty dictionary to decline the frame, which is the normal outcome for most of
## them. A proposal is `{goal, priority, intent, targetId, reason, memory}`, where
## `memory` is an optional patch the winner alone carries into the next frame.

## What the bot is trying to accomplish, in one word.
##
## Goals are for the person reading a log, not for control flow — nothing branches
## on a goal. Adding one costs a constant and a label.
const GOAL_STAND_DOWN := "stand_down"
const GOAL_HEAL := "heal"
const GOAL_ENGAGE := "engage"
const GOAL_COLLECT := "collect"
const GOAL_PURSUE := "pursue"
const GOAL_PATROL := "patrol"

## Priorities the shipped behaviours bid at. Values are spaced so new ones can
## land between.
const PRIORITY := {
	GOAL_STAND_DOWN: 1000.0,
	GOAL_HEAL: 900.0,
	GOAL_ENGAGE: 700.0,
	GOAL_COLLECT: 500.0,
	GOAL_PURSUE: 400.0,
	GOAL_PATROL: 100.0,
}

## No target. `""` rather than null, because every id this genre names is a
## string and a missing one should not be a different type.
const NO_TARGET := ""

const STAND_DOWN_DECISION_REASON := "no behaviour bid"


## Carried state, kept explicit and small.
##
## Anything a behaviour needs to remember between frames lives here rather than in
## a closure, so the bot's entire mind is one serialisable value: it can be logged
## next to a frame, diffed when a run diverges, and reconstructed exactly.
static func initial_memory() -> Dictionary:
	return {
		# The threat or pickup currently being chased, so the bot does not swap
		# targets every frame.
		"targetId": NO_TARGET,
		# Frames spent asking to move horizontally while going nowhere.
		"stuckFrames": 0,
		# Which way an idle patrol is currently walking.
		"patrolSign": 1,
		"lastGoal": "",
	}


## Advance the bookkeeping every behaviour depends on but none of them owns.
##
## Stuck detection lives here rather than inside a movement behaviour because
## being stuck is a fact about the last frame's outcome, not about this frame's
## plan, and because every behaviour that moves would otherwise need its own copy
## of it. Patrol direction flips at the map edge for the same reason: it is world
## state, not a decision.
static func observe(
	memory: Dictionary, view: Dictionary, previous_intent: Dictionary, tuning: Dictionary
) -> Dictionary:
	var self_view: Dictionary = view["self"]
	var asked_to_move := bool(previous_intent["left"]) != bool(previous_intent["right"])
	var moved_slowly := absf(float(self_view["vx"])) < float(tuning["stuckSpeedUnits"])
	var stuck_frames := 0
	if asked_to_move and moved_slowly and not bool(self_view["airborne"]):
		stuck_frames = int(memory["stuckFrames"]) + 1
	var bounds: Dictionary = view["bounds"]
	var margin := float(tuning["patrolMarginUnits"])
	var patrol_sign := int(memory["patrolSign"])
	if float(self_view["x"]) <= float(bounds["left"]) + margin:
		patrol_sign = 1
	elif float(self_view["x"]) >= float(bounds["right"]) - margin:
		patrol_sign = -1
	var target_id := String(memory["targetId"])
	return {
		"targetId": target_id if _still_there(view, target_id) else NO_TARGET,
		"stuckFrames": stuck_frames,
		"patrolSign": patrol_sign,
		"lastGoal": String(memory["lastGoal"]),
	}


static func _still_there(view: Dictionary, target_id: String) -> bool:
	if target_id == NO_TARGET:
		return false
	for group: Variant in [view["threats"], view["pickups"]]:
		for entry: Variant in (group as Array):
			if String((entry as Dictionary)["id"]) == target_id:
				return true
	return false


## One frame of thought: observe, poll the roster, arbitrate, remember.
##
## Pure, and pure on purpose. The whole decision is a function of the view and the
## memory handed in, so a divergence between two runs is reproducible from two
## values rather than from a host. Returns
## `{intent, goal, targetId, reason, memory}`.
static func decide(
	view: Dictionary,
	memory: Dictionary,
	previous_intent: Dictionary,
	profile: Dictionary,
	reach: Array,
	standing_on: String
) -> Dictionary:
	var tuning: Dictionary = profile["tuning"]
	var observed := observe(memory, view, previous_intent, tuning)
	var context := {
		"view": view,
		"memory": observed,
		"tuning": tuning,
		"capabilities": profile["capabilities"],
		# Cost and opening move to every node, computed once per frame from where
		# the bot stands.
		"reach": reach,
		# The node the bot is standing on, or `""` when the map has no navigable
		# surface at all.
		"standingOn": standing_on,
	}
	var bids: Array = []
	for entry: Variant in (profile["roster"] as Array):
		var behavior: Dictionary = entry
		var consider: Callable = behavior["consider"]
		bids.append(consider.call(context))
	var winner := FamilyAuction.arbitrate(bids)
	if winner.is_empty():
		var quiet := observed.duplicate()
		quiet["lastGoal"] = GOAL_STAND_DOWN
		return {
			"intent": PlatformerWorld.neutral_intent(),
			"goal": GOAL_STAND_DOWN,
			"targetId": NO_TARGET,
			"reason": STAND_DOWN_DECISION_REASON,
			"memory": quiet,
		}
	var carried := observed.duplicate()
	for key: Variant in (winner.get("memory", {}) as Dictionary):
		carried[key] = (winner["memory"] as Dictionary)[key]
	carried["targetId"] = String(winner["targetId"])
	carried["lastGoal"] = String(winner["goal"])
	return {
		"intent": winner["intent"],
		"goal": String(winner["goal"]),
		"targetId": String(winner["targetId"]),
		"reason": String(winner["reason"]),
		"memory": carried,
	}
