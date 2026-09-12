class_name RunnerObstaclesSystem
extends RefCounted

## What the body hit, cleared and picked up this frame.
##
## A port of `web/lib/sideview-runner/obstacles.ts`. Three passes, and they are
## separate on purpose: a hazard can be struck and then cleared, and a pickup
## the body is both past and touching is a miss rather than a catch.
##
## Every box comparison is **strict** on all four edges, so touching is not
## colliding. That is the browser's rule and changing it would move every
## near-miss in every replay.

## How far inside its cell a pickup's box sits.
const PICKUP_CELL_INSET := 0.2
## Columns either side of the body a candidate must be within to be considered.
const REACH_COLUMNS := 2.0


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/obstacles",
		"contract_version": "obstacles-system-v4",
		"reads": ["segments", "avatar"],
		"owns": ["obstacles"],
		"emits": ["hazard-contact", "hazard-cleared", "collected"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	var obstacles := world.obstacles
	obstacles["hazardContact"] = false
	obstacles["collectedThisFrame"] = []
	obstacles["missedThisFrame"] = 0
	# Last frame's phase: the session is sealed after this, so a run that ended
	# stops collecting on the frame after it ended rather than during it.
	if String(world.run["phase"]) != "running":
		return

	var config := world.config
	var body := avatar_box(world.avatar, config)
	var distance := float(world.avatar["distanceColumns"])
	var heights: Dictionary = config["propHeightUnits"]

	for entry: Variant in RunnerSegments.streamed_hazards(world.segments):
		var hazard: Dictionary = entry
		var column := int(hazard["worldColumn"])
		if absf(float(column) - distance) > REACH_COLUMNS:
			continue
		var surface := RunnerSegments.surface_row_at(world.segments, column)
		if surface < 0:
			continue
		var height_rows := (
			float(heights.get(String(hazard["propId"]), 1.0)) * float(config["playerHeightTiles"])
		)
		if not _overlaps(body, hazard_box(hazard, surface, height_rows, config)):
			continue
		obstacles["hazardContact"] = true
		var key := hazard_key(hazard)
		if not (obstacles["struck"] as Dictionary).has(key):
			(obstacles["struck"] as Dictionary)[key] = true
			world.events.emit({"type": "hazard-contact", "key": key})

	# A second full scan, with no proximity cull: a hazard is cleared once the
	# body is past its far edge, whether or not it was ever struck.
	for entry: Variant in RunnerSegments.streamed_hazards(world.segments):
		var hazard: Dictionary = entry
		if distance < float(hazard["worldColumn"]) + 1.0:
			continue
		var key := hazard_key(hazard)
		if (obstacles["cleared"] as Dictionary).has(key):
			continue
		(obstacles["cleared"] as Dictionary)[key] = true
		world.events.emit({"type": "hazard-cleared", "key": key})

	var collection := FamilyLoot.collect_drops(
		RunnerSegments.streamed_pickups(world.segments),
		Callable(RunnerObstaclesSystem, "pickup_key"),
		obstacles["collected"],
		obstacles["missed"],
		func(drop: Variant) -> bool:
			return float((drop as Dictionary)["worldColumn"]) + 1.0 < distance - 0.5,
		func(drop: Variant) -> bool:
			var pickup: Dictionary = drop
			if absf(float(pickup["worldColumn"]) - distance) > REACH_COLUMNS:
				return false
			return _overlaps(
				body, pickup_box(int(pickup["worldColumn"]), int(pickup["row"]))
			)
	)
	obstacles["collectedThisFrame"] = (collection["taken"] as Array).duplicate()
	obstacles["missedThisFrame"] = (collection["missed"] as Array).size()
	for entry: Variant in (collection["taken"] as Array):
		world.events.emit({"type": "collected", "key": pickup_key(entry)})


## Where a pickup is, as a key a ledger can hold.
static func pickup_key(pickup: Variant) -> String:
	var drop: Dictionary = pickup
	return "%d:%d:%s" % [int(drop["worldColumn"]), int(drop["row"]), String(drop["itemId"])]


static func hazard_key(hazard: Dictionary) -> String:
	return "%d:%s" % [int(hazard["worldColumn"]), String(hazard["propId"])]


## The body's box, ducked or standing.
static func avatar_box(avatar: Dictionary, config: Dictionary) -> Dictionary:
	var height := float(config["playerHeightTiles"])
	if bool(avatar["sliding"]) and String(config["duckProfile"]) != "":
		height = height * float(config["duckedHeightFraction"])
	var half := float((config["arithmetic"] as Dictionary)["avatarHalfWidthColumns"])
	var distance := float(avatar["distanceColumns"])
	return {
		"left": distance - half,
		"right": distance + half,
		"top": float(avatar["y"]) - height,
		"bottom": float(avatar["y"]),
	}


## A hazard's box. An overhead hazard hangs its clearance above the surface.
static func hazard_box(
	hazard: Dictionary, surface_row: int, height_rows: float, config: Dictionary
) -> Dictionary:
	var bottom := float(surface_row)
	if String(hazard["anchor"]) == "overhead":
		bottom = float(surface_row) - float(hazard["clearanceRows"])
	var inset := float((config["arithmetic"] as Dictionary)["hazardColumnInset"])
	var column := float(hazard["worldColumn"])
	return {
		"left": column + inset,
		"right": column + 1.0 - inset,
		"top": bottom - height_rows,
		"bottom": bottom,
	}


static func pickup_box(column: int, row: int) -> Dictionary:
	return {
		"left": float(column) + PICKUP_CELL_INSET,
		"right": float(column) + 1.0 - PICKUP_CELL_INSET,
		"top": float(row) + PICKUP_CELL_INSET,
		"bottom": float(row) + 1.0 - PICKUP_CELL_INSET,
	}


static func _overlaps(a: Dictionary, b: Dictionary) -> bool:
	return (
		float(a["left"]) < float(b["right"])
		and float(b["left"]) < float(a["right"])
		and float(a["top"]) < float(b["bottom"])
		and float(b["top"]) < float(a["bottom"])
	)
