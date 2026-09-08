class_name FamilyTraversal
extends RefCounted

## What a body can do besides walk and jump: crouch, climb, and drop through a
## one-way deck.
##
## A port of `web/lib/families/sideview/traversal/capabilities.ts`. The runner
## composes none of this — it auto-runs on a heightfield — and the platformer
## composes all of it, which is exactly the split that makes it a family: one
## genre asked, the second one needed it, and nothing was copied.

const CAPABILITIES := ["climb", "one-way-decks", "crouch", "drop-through", "wrap"]
const LOCOMOTIONS := ["ground_v1", "momentum_v1", "thrust_v1"]
## Named and refused rather than silently absent: a map that asks for wrapping
## should hear that this build does not do it.
const UNIMPLEMENTED := ["wrap"]


## Keep a crouch directional but never faster than the cap.
static func resolve_crouch_horizontal_velocity(velocity: float, cap: float) -> float:
	return signf(velocity) * minf(absf(velocity), cap)


## The deck a given x stands over, or an empty dictionary between decks.
static func deck_at_x(decks: Array, x: float) -> Dictionary:
	for entry: Variant in decks:
		var deck: Dictionary = entry
		if x >= float(deck["left"]) and x <= float(deck["right"]):
			return deck
	return {}


## Is a body still falling through the deck it asked to drop through?
##
## Two ways to still be inside the drop, and either is enough: the timer has not
## expired, or the feet have not yet cleared the deck by `clearance`. The second
## is what stops a slow fall being re-caught by the deck it just left.
static func drop_through_active(
	now_ms: float, expires_at_ms: float, foot_y: float, deck_y: float, clearance: float
) -> bool:
	return now_ms <= expires_at_ms or foot_y <= deck_y + clearance


## Which climbable a body may take this frame, and in which direction.
##
## Three ways in, and they are not symmetric because the endpoints are not: from
## the ground you take the bottom end by pressing up while standing near it,
## from the air you take the middle by pressing up while inside it, and from a
## deck you take the top end by pressing down while standing exactly on the deck
## the zone hangs from. Pressing both directions takes nothing, which is what
## makes the rule edge-free and re-askable every frame.
##
## Returns `{zone, direction}` or an empty dictionary.
static func climb_entry_at(
	zones: Array,
	geometry_of: Callable,
	endpoint_tolerance: float,
	support: String,
	support_id: Variant,
	x: float,
	foot_y: float,
	up: bool,
	down: bool
) -> Dictionary:
	for entry: Variant in zones:
		var zone: Dictionary = entry
		var geometry: Dictionary = geometry_of.call(zone)
		if absf(x - float(geometry["centerX"])) > float(geometry["activationHalfWidth"]):
			continue
		if (
			support == FamilyContact.SUPPORT_TERRAIN
			and up
			and not down
			and absf(foot_y - float(geometry["lowerY"])) <= endpoint_tolerance
		):
			return {"zone": zone, "direction": "up"}
		if (
			support == FamilyContact.SUPPORT_AIR
			and up
			and not down
			and foot_y >= float(geometry["upperY"])
			and foot_y <= float(geometry["lowerY"])
		):
			return {"zone": zone, "direction": "up"}
		if (
			support == FamilyContact.SUPPORT_PLATFORM
			and support_id != null
			and String(support_id) == String(geometry["deckId"])
			and down
			and not up
			and is_equal_approx(foot_y, float(geometry["upperY"]))
		):
			return {"zone": zone, "direction": "down"}
	return {}


## Advance an attached body, with the endpoints clamping it.
##
## Returns `{footY, vy, exit}` where `exit` is "platform" at the top, "terrain"
## at the bottom, and "" while still on the zone.
static func advance_climb_motion(
	geometry: Dictionary, speed: float, foot_y: float, delta_seconds: float, up: bool, down: bool
) -> Dictionary:
	var direction := 0.0
	if up != down:
		direction = -1.0 if up else 1.0
	var vy := direction * speed
	var next := foot_y + vy * delta_seconds
	if next <= float(geometry["upperY"]):
		return {"footY": float(geometry["upperY"]), "vy": 0.0, "exit": "platform"}
	if next >= float(geometry["lowerY"]):
		return {"footY": float(geometry["lowerY"]), "vy": 0.0, "exit": "terrain"}
	return {"footY": next, "vy": vy, "exit": ""}


## The velocity of a jump off a climbable.
##
## Direction comes from held intent when there is any, and from facing when
## there is not, so a body that lets go without steering falls off the side it
## was looking at rather than dropping straight down the axis it is locked to.
static func climb_jump_off_velocity(
	jump_velocity: float, horizontal_speed: float, left: bool, right: bool, facing: String
) -> Dictionary:
	var direction := 1.0
	if left != right:
		direction = -1.0 if left else 1.0
	elif facing == "left":
		direction = -1.0
	return {"vx": direction * horizontal_speed, "vy": jump_velocity}
