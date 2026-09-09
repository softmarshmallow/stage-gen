class_name FamilyNavSteering
extends RefCounted

## What to press this frame, given the move being executed.
##
## A port of `web/lib/families/navigation/steering.ts`, and the second half of
## navigation — deliberately the smaller one: the graph decides *which* traversal
## to attempt and this decides how to perform it. A behaviour appears in neither.
##
## The buttons come back through an `intent_of` builder rather than as this
## family's own record, because the intent record is the `intent` family's and its
## keys are the genre's — the platformer's ten and the runner's four are both
## legitimate. Steering therefore names the six buttons a navigator can ask for
## and hands them to whoever owns the record.

## `arriveRadiusUnits`: within this distance of a destination the navigator stops
## asking to move. `runBeyondUnits`: beyond this it runs rather than walks.
## `launchWindowUnits`: how close to a launch point the jump is committed.
## `climbAlignUnits`: how closely a climb must be lined up before the grab.
const DEFAULT_TUNING := {
	"arriveRadiusUnits": 14.0,
	"runBeyondUnits": 190.0,
	"launchWindowUnits": 40.0,
	"climbAlignUnits": 12.0,
}


static func _walk_toward(
	self_state: Dictionary,
	target_x: float,
	arrive_radius: float,
	run_beyond: float,
	extra: Dictionary,
	intent_of: Callable
) -> Dictionary:
	var delta := target_x - float(self_state["x"])
	if absf(delta) <= arrive_radius:
		return intent_of.call(extra)
	var buttons := extra.duplicate()
	buttons["left"] = delta < 0.0
	buttons["right"] = delta > 0.0
	buttons["run"] = absf(delta) > run_beyond
	return intent_of.call(buttons)


## The buttons this frame, given the move being executed.
##
## `self_state` is `{x, footY, vx, vy, airborne, support, airJumpsUsed}` and an
## empty `link` means the destination is on the shelf already occupied, so the
## whole of navigation collapses to walking toward it — which is the common case
## and should read like one.
##
## The air jump is spent on the first frame the arc stops rising. That is not a
## heuristic: it is the same moment `simulate_jump_arc` spends it when proving the
## link reachable, so the arc actually flown is the arc that was proved. Any other
## moment would make the graph a promise the steering quietly breaks.
static func steer(
	self_state: Dictionary,
	link: Dictionary,
	target_x: float,
	capabilities: Dictionary,
	tuning: Dictionary,
	intent_of: Callable
) -> Dictionary:
	var arrive := float(tuning["arriveRadiusUnits"])
	var run_beyond := float(tuning["runBeyondUnits"])
	if link.is_empty():
		return _walk_toward(self_state, target_x, arrive, run_beyond, {}, intent_of)
	var move := String(link["move"])
	match move:
		FamilyNavGraph.MOVE_WALK, FamilyNavGraph.MOVE_STEP_DOWN:
			return _walk_toward(
				self_state, float(link["toX"]), arrive, run_beyond, {}, intent_of
			)
		FamilyNavGraph.MOVE_JUMP, FamilyNavGraph.MOVE_DOUBLE_JUMP:
			if bool(self_state["airborne"]):
				var spend_air_jump := (
					move == FamilyNavGraph.MOVE_DOUBLE_JUMP
					and float(self_state["vy"]) >= 0.0
					and int(self_state["airJumpsUsed"]) == 0
					and float(capabilities.get("airJumpVelocity", FamilyNavGraph.NO_AIR_JUMP)) > 0.0
				)
				return _walk_toward(
					self_state,
					float(link["toX"]),
					0.0,
					run_beyond,
					{"jump": spend_air_jump},
					intent_of
				)
			var at_launch := (
				absf(float(self_state["x"]) - float(link["fromX"]))
				<= float(tuning["launchWindowUnits"])
			)
			return _walk_toward(
				self_state,
				float(link["toX"]) if at_launch else float(link["fromX"]),
				0.0,
				run_beyond,
				{"jump": at_launch},
				intent_of
			)
		FamilyNavGraph.MOVE_CLIMB:
			var upward := float(link["rise"]) > 0.0
			var on_climbable := String(self_state["support"]) == "climbable"
			var aligned := (
				absf(float(self_state["x"]) - float(link["fromX"]))
				<= float(tuning["climbAlignUnits"])
			)
			if on_climbable or aligned:
				return intent_of.call({"up": upward, "down": not upward})
			return _walk_toward(
				self_state, float(link["fromX"]), 0.0, run_beyond, {}, intent_of
			)
		FamilyNavGraph.MOVE_DROP_THROUGH:
			var over := absf(float(self_state["x"]) - float(link["fromX"])) <= arrive
			if not over:
				return _walk_toward(
					self_state, float(link["fromX"]), arrive, run_beyond, {}, intent_of
				)
			return intent_of.call({"down": true, "jump": true})
	return intent_of.call({})
