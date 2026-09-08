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
static func update(world: PlatformerWorld, step: Dictionary) -> void:
	if not bool(world.player["defeated"]):
		world.defeated_at_ms = null
		return
	if world.defeated_at_ms == null:
		world.defeated_at_ms = float(step["now"])
		PlatformerTranscript.record(
			world, "player-defeated", int(step["frame"]), float(step["now"]), null
		)
		return
	if not _confirmed(world):
		return
	_respawn(world, step)


## Put the body back where the package calls home.
static func _respawn(world: PlatformerWorld, step: Dictionary) -> void:
	var home := String(world.package["entrySpawnId"])
	var spawn := PlatformerMaps.spawn_position(world.package, home)
	if spawn.is_empty():
		return
	world.defeated_at_ms = null
	world.open_on(String(spawn["mapId"]))
	PlatformerMapEntrySystem.place(world, float(spawn["x"]), float(spawn["y"]))
	# The pool is refilled rather than topped up: a body that came back on one
	# point would die to the first thing it met, which reads as a punishment for
	# having died rather than as a second try.
	world.player["hp"] = int(world.progression.get("maximumHealth", world.player["maxHp"]))
	world.player["maxHp"] = int(world.player["hp"])
	world.player["defeated"] = false
	world.player["state"] = PlatformerPlayer.STATE_IDLE
	world.player["gauge"] = KernelGauge.create(int(world.player["maxHp"]))
	world.camera = PlatformerCameraSystem.snapped(
		float(world.player["x"]),
		PlatformerCameraSystem.bounds_of(world),
		float(world.player["y"])
	)
	PlatformerTranscript.record(
		world,
		"player-respawned",
		int(step["frame"]),
		float(step["now"]),
		{"mapId": world.map_id}
	)


static func _confirmed(world: PlatformerWorld) -> bool:
	for key: Variant in CONFIRM_KEYS:
		if bool(world.intent.get(String(key), false)):
			return true
	return false
