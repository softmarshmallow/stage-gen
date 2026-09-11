class_name PlatformerBotNavigation
extends RefCounted

## This genre's binding of the `navigation` family.
##
## A port of `web/lib/sideview-platformer/bot-navigation.ts`. The graph, the
## lanes, the search and the steering are the family's — nothing in them mentions
## a bot. What is this genre's, and what stays here, is the *repertoire*: a
## navigator's model of itself has to be the model its physics uses, so the
## default capabilities are the platformer controller's own constants, and the
## buttons come back as this genre's intent record through the family's
## `intent_of` seam rather than as a record the family invented.

## The repertoire the platformer's own controller has.
##
## Every number here is the constant the physics integrates with, which is the
## point: a route the graph admits is a route the body can fly, because the
## admission ran the same arc the controller will.
const DEFAULT_CAPABILITIES := {
	"walkSpeed": PlatformerVertical.WALK_SPEED,
	"runSpeed": PlatformerVertical.RUN_SPEED,
	"jumpVelocity": PlatformerVertical.JUMP_VELOCITY,
	"airJumpVelocity": PlatformerVertical.AIR_JUMP_VELOCITY,
	"gravity": PlatformerVertical.GRAVITY,
	"stepSeconds": PlatformerVertical.FIXED_STEP_SECONDS,
	"stepUpTolerance": PlatformerVertical.STEP_UP_TOLERANCE,
	"canClimb": true,
	"canDropThrough": true,
}


static func capabilities(overrides: Dictionary = {}) -> Dictionary:
	return FamilyNavGraph.movement_capabilities(DEFAULT_CAPABILITIES, overrides)


## This genre's intent record, from the six buttons a navigator can ask for.
##
## Every unstated field inherits silence, which is what lets a policy that only
## wants to walk right say so and nothing else: adding a future action to the
## record cannot then silently change what an existing source is asking for.
static func intent_of(buttons: Dictionary) -> Dictionary:
	var made := PlatformerWorld.neutral_intent()
	for key: Variant in buttons:
		var field := String(key)
		if made.has(field):
			made[field] = buttons[key]
	return made


## The buttons this frame, in this genre's own intent record.
static func steer(
	self_state: Dictionary, link: Dictionary, target_x: float, caps: Dictionary, tuning: Dictionary
) -> Dictionary:
	return FamilyNavSteering.steer(
		self_state, link, target_x, caps, tuning, Callable(PlatformerBotNavigation, "intent_of")
	)


## The navigator's model of the body, taken from the bot's own view of itself.
static func agent_state(self_view: Dictionary) -> Dictionary:
	return {
		"x": float(self_view["x"]),
		"footY": float(self_view["y"]),
		"vx": float(self_view["vx"]),
		"vy": float(self_view["vy"]),
		"airborne": bool(self_view["airborne"]),
		"support": String(self_view["support"]),
		"airJumpsUsed": int(self_view["airJumpsUsed"]),
	}
