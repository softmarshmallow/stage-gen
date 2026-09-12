class_name PlatformerSetPieceSystem
extends RefCounted

## The authored gates, advanced one frame at a time.
##
## Armed until the body reaches the anchor, engaged while the thing standing in
## it is alive, and ended when it is not — at which point the track the gate was
## fought to is put back.
##
## A port of `stepSetPieces` in `web/lib/sideview-platformer/prepared-scene.ts`.
## The rules it reads live in `PlatformerDirector`; what is here is the frame.

const DIAGNOSTIC_SOURCE := "platformer/set-piece"


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "director/set-piece",
			"contract_version": "set-piece-system-v1",
			"reads": ["player", "mobs"],
			"owns": ["setPieces"],
			"emits": ["encounter-started", "encounter-ended"],
		}
	)


## Put every gate this map declares in the session, arming the ones it has never
## seen and re-arming any that was mid-fight when the map was torn down.
##
## A player who walks out of the map during the fight has not beaten it, and a
## gate stuck on `engaged` with nothing standing in it would never fire again.
## Whatever it had swapped is put back on the way, because the run it swapped for
## is over.
static func open_on(world: PlatformerWorld) -> void:
	for entry: Variant in (world.package["bossEncounters"] as Array):
		var authored: Dictionary = entry
		if String(authored.get("map_id", "")) != world.map_id:
			continue
		var encounter_id := String(authored.get("encounter_id", ""))
		if not world.set_pieces.has(encounter_id):
			world.set_pieces[encounter_id] = PlatformerDirector.armed()
			continue
		var state: Dictionary = world.set_pieces[encounter_id]
		if String(state["phase"]) != PlatformerDirector.PHASE_ENGAGED:
			continue
		_restore_pool(world, state)
		state["phase"] = PlatformerDirector.PHASE_ARMED
		state["phaseStartedAt"] = null


## Advance every gate on this map by one frame.
static func step(world: PlatformerWorld, frame_step: Dictionary) -> void:
	if world.hold:
		return
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	var now_ms := float(frame_step["now"])
	for entry: Variant in (world.package["bossEncounters"] as Array):
		var authored: Dictionary = entry
		if String(authored.get("map_id", "")) != world.map_id:
			continue
		var encounter_id := String(authored.get("encounter_id", ""))
		var state: Dictionary = world.set_pieces.get(encounter_id, {})
		if state.is_empty():
			continue
		if PlatformerDirector.spent(state, String(authored.get("respawn_policy", ""))):
			continue
		if String(state["phase"]) == PlatformerDirector.PHASE_ARMED:
			_arm(world, frame_step, authored, state, map, now_ms)
			continue
		if String(state["phase"]) != PlatformerDirector.PHASE_ENGAGED:
			continue
		var body: Dictionary = world.set_piece_bodies.get(encounter_id, {})
		if not body.is_empty() and bool(body["alive"]):
			continue
		world.set_piece_bodies.erase(encounter_id)
		_restore_pool(world, state)
		PlatformerDirector.end(state, now_ms, PlatformerDirector.OUTCOME_WON)
		PlatformerTranscript.record(
			world,
			"encounter-ended",
			int(frame_step["frame"]),
			now_ms,
			{"encounterId": encounter_id, "outcome": PlatformerDirector.OUTCOME_WON}
		)


## One armed gate, this frame: has the body reached it, and if so what stands up.
static func _arm(
	world: PlatformerWorld,
	frame_step: Dictionary,
	authored: Dictionary,
	state: Dictionary,
	map: Dictionary,
	now_ms: float
) -> void:
	var encounter_id := String(authored.get("encounter_id", ""))
	var anchor := PlatformerDirector.anchor_x(map, String(authored.get("anchor", "")))
	# An anchor nobody published is a package defect and not a reason to stop
	# playing: the gate is retired, and the world says why rather than standing
	# armed for a place that does not exist.
	if anchor < 0.0:
		push_warning(
			"%s: %s names unknown anchor %s; the gate is retired rather than left armed"
			% [DIAGNOSTIC_SOURCE, encounter_id, String(authored.get("anchor", ""))]
		)
		PlatformerDirector.end(state, now_ms, PlatformerDirector.OUTCOME_WON)
		return
	if not FamilyDirector.trigger_reached(anchor, float(world.player["x"])):
		return
	var body := _place(world, String(authored.get("mob_id", "")), anchor, map)
	if body.is_empty():
		push_warning(
			"%s: %s could not place %s; the gate is retired rather than left armed"
			% [DIAGNOSTIC_SOURCE, encounter_id, String(authored.get("mob_id", ""))]
		)
		PlatformerDirector.end(state, now_ms, PlatformerDirector.OUTCOME_WON)
		return
	world.set_piece_bodies[encounter_id] = body
	# The one swap this genre has, and the authored fact the runtime that came
	# before never used at all: the pool is narrowed to the piece the gate is
	# fought to, and the map's own pool is put back when it ends.
	PlatformerDirector.engage(state, now_ms, map["trackIds"])
	_bind_pool(world, PackedStringArray([String(authored.get("track_id", ""))]))
	PlatformerTranscript.record(
		world,
		"encounter-started",
		int(frame_step["frame"]),
		now_ms,
		{"encounterId": encounter_id, "x": int(round(anchor))}
	)


## Put the thing the gate stands behind on the map, at the gate.
static func _place(
	world: PlatformerWorld, mob_id: String, anchor: float, map: Dictionary
) -> Dictionary:
	var slot := PlatformerMobsSystem.slot_of(world, mob_id)
	if slot < 0:
		return {}
	var spec: Dictionary = (world.package["mobs"] as Array)[slot]
	var heights: PackedInt32Array = map["heights"]
	var column := clampi(
		int(floor(anchor / PlatformerMaps.TILE_PX)), 0, maxi(0, heights.size() - 1)
	)
	# No director instance, and that is what makes it a boss rather than one more
	# creature on the road: an instance id is the population director's name for
	# something it is managing, and nobody is managing this one. Its behaviour
	# seed therefore comes from where it stands rather than from a counter.
	var body := PlatformerMob.create(
		PlatformerMobBehavior.seed_for(column, slot),
		"mob_%d" % world.next_mob_bot_id,
		"",
		slot,
		PlatformerMobsSystem.aggression_of(spec),
		PlatformerMobsSystem.health_of(
			spec, PlatformerNumberScale.profile_of(world.package["combat"])
		),
		float(column) * PlatformerMaps.TILE_PX + PlatformerMaps.TILE_PX / 2.0,
		PlatformerVertical.terrain_surface_y(
			heights[column], PlatformerMaps.TILE_PX, PlatformerMaps.BASELINE_Y
		),
		map
	)
	body["instanceId"] = null
	world.next_mob_bot_id += 1
	world.mobs.append(body)
	return body


## Put the map's own pool back, if the gate held one.
static func _restore_pool(world: PlatformerWorld, state: Dictionary) -> void:
	var pool := PackedStringArray()
	for track: Variant in (state.get("trackPool", []) as Array):
		pool.append(String(track))
	state["trackPool"] = []
	if pool.is_empty():
		return
	_bind_pool(world, pool)


## Narrow or widen what may play, and republish what that decided.
##
## The bag is the world's, so the answer is a slice rather than a call: a pool
## bound over a track that is not in it retires the current one, and a one-track
## pool that has already been heard is finished — both of which the bag decides
## and this only reports.
static func _bind_pool(world: PlatformerWorld, pool: PackedStringArray) -> void:
	if world.music == null or pool.is_empty():
		return
	world.music.bind_pool(pool)
	if not bool(world.soundtrack.get("started", false)):
		world.soundtrack = {
			"current_track_id": null,
			"next_track_id": PlatformerWorld._or_null(world.music.planned()),
			"started": false,
		}
		return
	var playing := world.music.take()
	world.soundtrack = {
		"current_track_id": PlatformerWorld._or_null(playing),
		"next_track_id": PlatformerWorld._or_null(world.music.planned()),
		"started": true,
	}
