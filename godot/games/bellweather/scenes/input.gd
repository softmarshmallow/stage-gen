class_name PlatformerInput
extends RefCounted

## The keyboard, as the ten fields the body reads, the four the scene does, and
## the one the host keeps for itself.
##
## Levels are sampled — held is held — and requests are edges: a jump, a throw, a
## drink and the inventory toggle are spent on the frame they are pressed and not
## again until the key comes back up. That split is the intent family's, and it
## is the difference between a jump and a hover.
##
## Read from physical keys rather than through an action map, so a fresh
## checkout plays without anyone having configured anything. A published control
## binding would come through the same nine names.

const LEVELS := {
	"left": [KEY_A, KEY_LEFT],
	"right": [KEY_D, KEY_RIGHT],
	"up": [KEY_W, KEY_UP],
	"down": [KEY_S, KEY_DOWN],
	"run": [KEY_SHIFT],
}

const REQUESTS := {
	"jump": [KEY_SPACE],
	"attack": [KEY_J, KEY_X, KEY_Z],
	"useHealing": [KEY_Q],
	"toggleInventory": [KEY_I],
}

## The four a player presses at the scene rather than through the body: opening
## a conversation, advancing it, asking a gate to open.
const SCENE_KEYS := {
	"interact": [KEY_E],
	"enter": [KEY_ENTER, KEY_KP_ENTER],
	"space": [KEY_SPACE],
}

## Keys the host answers itself, and the body never hears.
##
## Deliberately not in the intent record. Intent is what the character is trying
## to do, and handing the auto-play switch to it would say the body has an action
## called `toggleBot` — it does not, and a record that claimed so would be read by
## the controller, hashed by a golden, and published to a second runtime.
const HOST_KEYS := {
	"toggleBot": [KEY_P],
}

var _down: Dictionary = {}


## This frame's intent. `up` is both a level the body climbs by and an edge the
## gate opens on, so it is sampled as a level and published as an edge too.
func sample() -> Dictionary:
	var made := PlatformerWorld.neutral_intent()
	for name: Variant in LEVELS:
		made[String(name)] = _any(LEVELS[name])
	for name: Variant in REQUESTS:
		made[String(name)] = _edge(String(name), _any(REQUESTS[name]))
	for name: Variant in SCENE_KEYS:
		made[String(name)] = _edge(String(name), _any(SCENE_KEYS[name]))
	# The gate reads `up` as a press rather than as a hold, or walking into a
	# doorway with the climb key down would take it before the player asked.
	made["upPressed"] = _edge("upPressed", _any(LEVELS["up"]))
	return made


## This frame's host keys, as edges. Read by the host, never by the world.
func host_edges() -> Dictionary:
	var made := {}
	for name: Variant in HOST_KEYS:
		made[String(name)] = _edge(String(name), _any(HOST_KEYS[name]))
	return made


static func _any(codes: Array) -> bool:
	for code: Variant in codes:
		if Input.is_physical_key_pressed(int(code)):
			return true
	return false


## True on the frame a key goes down, and not again until it comes back up.
func _edge(name: String, down: bool) -> bool:
	var was := bool(_down.get(name, false))
	_down[name] = down
	return down and not was
