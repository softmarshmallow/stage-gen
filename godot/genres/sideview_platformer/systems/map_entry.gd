class_name PlatformerMapEntrySystem
extends RefCounted

## The gate between two maps: asked for by a press, taken at the end of a frame.
##
## A port of `updateInteractionPrompt`'s gate half and `applyPendingMapEntry` in
## `web/lib/sideview-platformer/prepared-scene.ts`. Two halves and the split is
## the whole design: standing in a gate's mouth and pressing up *asks*, and the
## world is rebuilt after every other system has run, because a stage replaced
## mid-frame would leave the systems below it reading a world that no longer
## matches the events they are about to consume.
##
## Two rules the golden taught the port rather than the other way round:
##
## **The body does not step on the frame it arrives.** A map entry rebuilds the
## stage mid-frame, so the body steps neither in the world it just left nor in
## the one it has this instant arrived in. `column` is derived from `x`, so it
## has to be re-derived by hand on arrival — the step that would have done it is
## the step that is skipped.
##
## **A gate fired once is spent for the run.** The browser latches the portal it
## fired and never clears it, so a door already walked through offers nothing
## for the rest of the run, the one on the far side included. Without it the body
## bounces straight back through the arrival gate. Reproduced rather than
## corrected: the golden is the reference, and if it is a defect it is the
## incumbent's and belongs in its own record.

## Which keys ask a gate to open.
##
## `upPressed` and not `up`: climbing holds the key and a gate is asked once, so
## a body that walked into a doorway with the climb key down would be taken
## through it without asking. The browser reads the same key twice for the same
## reason — as a level for the ladder and with `JustDown` for the gate.
const OPEN_KEYS := ["upPressed", "interact", "enter"]


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "map/entry",
			"contract_version": "map-entry-system-v1",
			"reads": ["hold", "intent", "player"],
			"writes": ["mapId", "player", "camera", "portals", "npcPrompts", "soundtrack"],
			"emits": ["map-entered"],
		}
	)


## Ask, if the body is standing in a gate's mouth and a key says so.
static func ask(world: PlatformerWorld) -> void:
	if world.hold or not world.pending_map.is_empty():
		return
	if not _pressed(world):
		return
	var transition := PlatformerMaps.transition_at(
		world.package, world.map_id, float(world.player["x"])
	)
	if transition.is_empty():
		return
	world.pending_map = transition


## Take it, after everything else this frame has run.
static func apply(world: PlatformerWorld, step: Dictionary) -> void:
	if world.pending_map.is_empty():
		return
	var transition := world.pending_map
	world.pending_map = {}
	var spawn := PlatformerMaps.spawn_position(
		world.package, String(transition["toSpawnId"])
	)
	if spawn.is_empty():
		return
	world.open_on(String(spawn["mapId"]))
	place(world, float(spawn["x"]), float(spawn["y"]))
	world.camera = PlatformerCameraSystem.snapped(
		float(world.player["x"]),
		PlatformerCameraSystem.bounds_of(world),
		float(world.player["y"])
	)
	PlatformerTranscript.record(
		world,
		"map-entered",
		int(step["frame"]),
		float(step["now"]),
		# The map and where the body was put down, which is what a consumer needs
		# to draw an arrival. The transition's own id is not in it: the browser
		# names the destination rather than the door, and a run can reach one map
		# through more than one.
		{"mapId": world.map_id, "startX": float(world.player["x"])}
	)


## The body, put down at the spawn and stopped.
##
## Everything a step would have settled is settled here instead, because the
## body does not take one this frame: the column from the new x, the support
## from the new ground, and the motion cleared so an arrival does not carry the
## departure's run into the next map.
static func place(world: PlatformerWorld, x: float, y: float) -> void:
	var player: Dictionary = world.player
	player["x"] = x
	player["y"] = y
	player["vx"] = 0.0
	player["vy"] = 0.0
	player["state"] = PlatformerPlayer.STATE_IDLE
	player["airborne"] = false
	player["support"] = FamilyContact.SUPPORT_TERRAIN
	player["supportId"] = null
	player["ladderId"] = null
	player["platformId"] = null
	player["airJumpsUsed"] = 0
	player["column"] = int(floor(x / PlatformerMaps.TILE_PX))


static func _pressed(world: PlatformerWorld) -> bool:
	for key: Variant in OPEN_KEYS:
		if bool(world.intent.get(String(key), false)):
			return true
	return false
