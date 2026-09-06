class_name SimFixture
extends RefCounted

## Shared setup for the simulation tests: one opened run package, one world
## per caller, and builders for the entity shapes `World.create` produces.
## Not a test file (the runner only picks up `test_*.gd`).

const STEP := 1.0 / 60.0

static var _package: RunPackage = null


## The full-v66 package, opened once for the whole suite.
static func package() -> RunPackage:
	if _package == null:
		_package = RunPackage.open(TestHarness.RUN_DIR)
	return _package


## A world on the real run, with the camera looking down +z (yaw 0) and the
## player standing at the origin with no input.
static func world() -> World:
	var pkg := package()
	if pkg == null:
		return null
	var w := World.create(pkg, 7, {})
	w.camera_yaw = 0.0
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.vx = 0.0
	w.player.vz = 0.0
	return w


## An empty stage: no entities, no pack, nothing pressed.
static func bare(w: World) -> void:
	w.entities.clear()
	w.slots.clear()
	w.drops.clear()
	w.events.clear()
	w.selected = 0
	release(w)


## Clear every input the host would sample.
static func release(w: World) -> void:
	w.input["x"] = 0.0
	w.input["z"] = 0.0
	w.input["interact"] = false
	w.input["light"] = false
	w.input["craft_toggle"] = false
	w.input["menu_move"] = 0
	w.input["menu_confirm"] = false
	w.input["use"] = false
	w.input["drop"] = false
	w.input["select"] = null
	w.input["cycle"] = 0
	w.input["menu_select"] = null
	w.input["click_entity"] = null
	w.input["click_point"] = null


## A prop entity in the shape `World.create` builds (viewer 484-503).
static func prop(w: World, id: String, prop_id: String, state: String, x: float, z: float) -> Dictionary:
	var template: Dictionary = (w.manifest["props"] as Dictionary)[prop_id]
	return {
		"id": id, "kind": "prop", "prop_id": prop_id, "state": state, "baseline": state,
		"x": x, "z": z, "seed": 1,
		"radius": float(template.get("footprint_radius_meters", 0.0)),
		"hits": 0, "regrow": 0.0, "burn": 0.0, "dirty": false,
	}


## A mob entity in the shape `World.create` builds (viewer 503-512).
static func mob(w: World, id: String, actor_id: String, x: float, z: float) -> Dictionary:
	var actor: Dictionary = (w.manifest["actors"] as Dictionary)[actor_id]
	var radius := float(actor.get("footprint_radius_meters", 0.0))
	if radius == 0.0:
		radius = 0.3
	return {
		"id": id, "kind": "mob", "actor_id": actor_id, "state": "idle",
		"x": x, "z": z, "home_x": x, "home_z": z, "vx": 0.0, "vz": 0.0,
		"facing": "right", "elapsed": 0.0, "cooldown": 0.0, "seed": 1,
		"radius": radius, "dirty": false,
	}


## A forage entity in the shape `World.create` builds (viewer 516-530).
static func forage(w: World, id: String, cell_index: int, x: float, z: float) -> Dictionary:
	var cell: Dictionary = ((w.manifest["ground"] as Dictionary)["forage"] as Dictionary)["cells"][cell_index]
	return {
		"id": id, "kind": "forage", "index": 0, "cell": cell_index,
		"item_id": str(cell["item_id"]), "count": int(cell.get("count", 1)),
		"regrow_seconds": float(cell.get("regrow_seconds", 120.0)),
		"x": x, "z": z, "taken": false, "picked": false, "hidden": false,
		"regrow": 0.0, "radius": 0.0, "dirty": false,
	}


## The authored season spec by id (summer / winter in full-v66).
static func season_spec(w: World, season_id: String) -> Dictionary:
	for spec in ((w.manifest["seasons"] as Dictionary)["seasons"] as Array):
		if str((spec as Dictionary)["season_id"]) == season_id:
			return spec as Dictionary
	return {}


## Hold the season still, so a test measures one condition and not the
## calendar. The `season` system leaves a forced season that already matches
## alone; the spec is written directly so a test never depends on that system.
static func force_season(w: World, season_id: String) -> void:
	var spec := season_spec(w, season_id)
	w.season["force"] = season_id
	w.season["id"] = season_id
	w.season["spec"] = spec
	w.season["turns"] = 1


## Every event of one type that the world has queued.
static func events_of(w: World, type_name: String) -> Array:
	var found: Array = []
	for event in w.events:
		if str((event as Dictionary).get("type", "")) == type_name:
			found.append(event)
	return found
