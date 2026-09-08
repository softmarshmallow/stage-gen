class_name PlatformerMob
extends RefCounted

## A creature on the route: what it is, where it patrols, and how it moves.
##
## A port of the simulation half of `web/lib/sideview-platformer/mob.ts` and the
## terrain lane of `mob-navigation.ts`. The browser's is a Phaser controller —
## its position lives on a sprite and its facing is a mirror flag — so this is a
## re-derivation, and what is here is the state the golden hashes plus the lane
## it is bounded by.
##
## **The behaviour seed is the instance number, not the spawn column.** The
## constructor falls back to a column-and-slot mix when no seed is passed, and
## `PlatformerMobBehavior.seed_for` ports that fallback — but the population
## director passes the instance number, so a creature's tempo comes from *when*
## it was spawned rather than *where*. Measured: the first two creatures on the
## road step -1.166040014 and -1.127991638 pixels on their spawn frame, which is
## what the instance seed gives and nine decimals away from what the column seed
## does.
##
## What is here is the wander. Chasing, striking, fleeing and returning home are
## `mob-behavior.ts`'s awareness node, and the golden does not reach them until
## the player is inside a creature's notice radius.

## The patrol speed of a creature whose package names none, before its own
## variation is applied.
const DEFAULT_SPEED_PX := 36.0

## How far from home a creature may wander, and how far it may chase.
const PATROL_HOME_RADIUS_TILES := 1.5
const PURSUIT_HOME_RADIUS_TILES := 6.0

## Half the drawn body, kept off the world's edges.
const RENDERED_HALF_WIDTH := 24.0

const STATE_WANDER := "wander"


## A creature standing up at a reservation.
static func create(
	instance: int,
	bot_id: String,
	instance_id: String,
	slot: int,
	aggression: String,
	starting_health: int,
	spawn_x: float,
	spawn_y: float,
	map: Dictionary
) -> Dictionary:
	var profile := PlatformerCombat.profile(aggression)
	var variation := PlatformerMobBehavior.variation(instance, profile)
	var lane := _lane(map, spawn_x)
	return {
		"instanceId": instance_id,
		"botId": bot_id,
		"ladderIndex": slot,
		"aggression": aggression,
		"hp": starting_health,
		"maxHp": starting_health,
		"state": STATE_WANDER,
		"x": spawn_x,
		"y": spawn_y,
		"alive": true,
		# Not published, and not hashed: the lane it patrols, the tempo it was
		# born with, and which way it set off.
		"homeX": spawn_x,
		"patrolMinX": maxf(lane["minX"], spawn_x - roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)),
		"patrolMaxX": minf(lane["maxX"], spawn_x + roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)),
		"speedScale": float(variation["movementSpeedScale"]),
		"patrolDirection": int(variation["initialDirection"]),
	}


## One frame of a creature nobody has noticed. Returns nothing; the body is
## stepped in place, which is what a world of plain dictionaries is for.
static func wander(mob: Dictionary, map: Dictionary, dt_seconds: float) -> void:
	if not bool(mob["alive"]):
		return
	var speed := DEFAULT_SPEED_PX * float(mob["speedScale"])
	var next_x := float(mob["x"]) + float(mob["patrolDirection"]) * speed * dt_seconds
	var walk := _walk(mob, map, next_x)
	mob["x"] = walk["x"]
	# A face turns a patrol the same way the end of its lane does. Reversing
	# rather than standing still is what stops a creature pressed against a rise
	# for the rest of the run, which reads as stuck rather than as bounded.
	if bool(walk["blocked"]):
		mob["patrolDirection"] = -int(mob["patrolDirection"])
	mob["y"] = _surface_at(map, float(mob["x"]))


## The eight fields the golden hashes.
static func snapshot(mob: Dictionary) -> Dictionary:
	return {
		"instanceId": mob["instanceId"],
		"botId": mob["botId"],
		"ladderIndex": mob["ladderIndex"],
		"aggression": mob["aggression"],
		"hp": mob["hp"],
		"maxHp": mob["maxHp"],
		"state": mob["state"],
		"x": mob["x"],
		"y": mob["y"],
		"alive": mob["alive"],
	}


## A step bounded by the patrol lane and then by the terrain, in that order.
static func _walk(mob: Dictionary, map: Dictionary, next_x: float) -> Dictionary:
	var bounded := clampf(next_x, float(mob["patrolMinX"]), float(mob["patrolMaxX"]))
	var stopped := bounded != next_x
	var walk := FamilyContact.resolve_terrain_walk(
		float(mob["x"]),
		bounded,
		_surface_at(map, float(mob["x"])),
		PlatformerMaps.TILE_PX,
		func(column: int) -> float: return _surface_at_column(map, column),
		0.0,
		0.0,
		false
	)
	if bool(walk["blocked"]) or not stopped:
		return walk
	return {"x": walk["x"], "blocked": true, "blockedColumn": -1}


## The shelf a creature was spawned on: the run of columns at its own height.
##
## At tolerance zero adjacent equality chains to equality with the spawn column,
## so the lane is exactly the shelf and a creature never patrols off the ledge it
## stood up on.
static func _lane(map: Dictionary, spawn_x: float) -> Dictionary:
	var heights: PackedInt32Array = map["heights"]
	var columns := heights.size()
	var spawn_column := clampi(int(floor(spawn_x / PlatformerMaps.TILE_PX)), 0, columns - 1)
	var height := heights[spawn_column]
	var left := spawn_column
	while left > 0 and heights[left - 1] == height:
		left -= 1
	var right := spawn_column
	while right + 1 < columns and heights[right + 1] == height:
		right += 1
	var world_min := RENDERED_HALF_WIDTH
	var world_max := float(map["worldWidthPx"]) - RENDERED_HALF_WIDTH
	return {
		"minX": maxf(world_min, float(left) * PlatformerMaps.TILE_PX),
		"maxX": minf(world_max, float(right + 1) * PlatformerMaps.TILE_PX - 1.0),
	}


static func _surface_at(map: Dictionary, x: float) -> float:
	return _surface_at_column(map, int(floor(x / PlatformerMaps.TILE_PX)))


static func _surface_at_column(map: Dictionary, column: int) -> float:
	var heights: PackedInt32Array = map["heights"]
	var height := 0
	if column >= 0 and column < heights.size():
		height = heights[column]
	return PlatformerVertical.terrain_surface_y(
		height, PlatformerMaps.TILE_PX, PlatformerMaps.BASELINE_Y
	)
