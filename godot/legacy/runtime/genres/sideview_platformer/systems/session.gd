class_name PlatformerSessionSystem
extends RefCounted

## Being beaten, and coming back from it.
##
## A defeat is not the end of a run here: the body is put back at the place the
## package calls home, with its pool refilled and the route repopulated, and what
## it was carrying it keeps. That is the shape the browser has, and the reason
## worth stating is that this game has no save — a run that ended on a defeat
## would end the session, and the package authors a home spawn precisely so it
## does not.
##
## The panel is not asked whether it is on screen. A host draws one and a
## headless replay draws nothing, and both accept the same key: the confirmation
## is a fact about the run, and whether anybody could see the card is a fact
## about the host.

## The keys that accept the card. The same three that advance a conversation,
## because a player who has just died is already holding one of them.
const CONFIRM_KEYS := ["interact", "enter", "space"]

## What this genre calls a place nothing hunts. The word is the package's; that a
## recovery goes to one is the family's.
const SAFE_MAP_ROLE := "safe_village_hub"

## The terminal strip, four frames at eight a second.
const DEATH_STRIP_DURATION_MS := 500.0

## How long a defeated body lies there before it is asked what to do next.
##
## Long enough for the strip to finish and register as an ending rather than a
## stutter — a prompt raised over a still-playing death animation would be
## talking over the one moment that artwork exists for.
const PROMPT_DELAY_MS := DEATH_STRIP_DURATION_MS + 400.0

## How long the card takes to arrive, so it reads as an arrival and not a cut.
const PROMPT_FADE_MS := 260.0

## What the button says before a run has anywhere to name. The world owns the
## card's resting state, so the words come from there rather than from a second
## copy that could drift from it.
const LABEL_AT_REST := PlatformerWorld.DEFEAT_PANEL_AT_REST["buttonLabel"]


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "session/defeat",
			"contract_version": "session-system-v1",
			"reads": ["player", "intent"],
			"writes": ["defeatedAtMs", "mapId"],
			"emits": ["player-defeated", "player-respawned"],
		}
	)


## Notice a defeat, and take the key that ends it.
##
## Returns whether the rest of this frame's player pass is over. A recovery
## rebuilds the world — a new map, a new roster, a body at full health — so
## nothing below it may step a creature that is about to be replaced or resolve a
## blow against a body that is no longer standing where it was hit.
static func update(world: PlatformerWorld, step: Dictionary) -> bool:
	if not bool(world.player["defeated"]):
		world.defeated_at_ms = null
		return false
	if world.defeated_at_ms == null:
		world.defeated_at_ms = float(step["now"])
		PlatformerTranscript.record(
			world, "player-defeated", int(step["frame"]), float(step["now"]), null
		)
	# The card is not up the instant the body goes down, and until it is, the key
	# that would accept it does nothing. Both halves matter: the delay is what
	# makes a death read as an ending, and refusing the key while the card is
	# still arriving is what stops a player who was mid-jump from skipping it
	# without ever seeing it.
	var prompt := FamilyDefeatPrompt.prompt_state(
		float(world.defeated_at_ms), float(step["now"]), PROMPT_DELAY_MS, PROMPT_FADE_MS
	)
	if not bool(prompt["visible"]):
		return false
	# The button names where the run resumes rather than promising "continue",
	# and it is named the moment the card is up rather than when the body fell —
	# the card is the only thing that could have said it.
	world.defeat_panel["buttonLabel"] = _return_label(world)
	if not _confirmed(world):
		return false
	_respawn(world, step)
	return true


## Where a recovery goes, and what to call it.
static func home_spawn(world: PlatformerWorld) -> Dictionary:
	return FamilyCheckpoints.respawn_target(
		String(world.package["entrySpawnId"]),
		world.package["spawns"],
		world.package["maps"],
		SAFE_MAP_ROLE
	)


static func _return_label(world: PlatformerWorld) -> String:
	var home := home_spawn(world)
	if home.is_empty():
		return LABEL_AT_REST
	var map: Dictionary = (world.package["maps"] as Dictionary).get(String(home["mapId"]), {})
	var named := String(map.get("displayName", "")).strip_edges()
	return LABEL_AT_REST if named.is_empty() else "Return to %s" % named


## Ask for the map entry that puts the body back where the package calls home.
##
## Asked rather than taken, and that is what makes a recovery cheap and safe: the
## same transition that carries a portal rebuilds the world at the end of the
## frame, once every system below this one has finished reading the world it
## still has. Nothing here rebuilds anything.
static func _respawn(world: PlatformerWorld, step: Dictionary) -> void:
	var home := home_spawn(world)
	if home.is_empty():
		return
	world.defeated_at_ms = null
	world.pending_map = {"toSpawnId": String(home["spawnId"])}
	PlatformerTranscript.record(
		world,
		"player-respawned",
		int(step["frame"]),
		float(step["now"]),
		{"mapId": String(home["mapId"])}
	)


static func _confirmed(world: PlatformerWorld) -> bool:
	for key: Variant in CONFIRM_KEYS:
		if bool(world.intent.get(String(key), false)):
			return true
	return false
