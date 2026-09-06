class_name World
extends RefCounted

## Every fact the simulation owns, and nothing the view owns.
##
## A port of the viewer's `createWorld` (index.html:480-584), field for field,
## with the names carried over into snake_case. Entities are plain Dictionaries
## the way they are plain objects there, with the same keys (`prop_id` for
## `propId`, `home_x` for `homeX`, and so on).

## The whole package contract.
var manifest: Dictionary = {}
## Published by the view every frame: which way the camera is looking. Input
## and facing are screen-space questions, so the simulation needs it. The only
## camera fact the simulation may know.
var camera_yaw: float = 0.0
## The ground plates read back as data. The viewer swapped these in
## asynchronously and lost them on reset; here they are attached at creation
## and carried across a reset.
var masks: Masks = null
## The one simulation PRNG, and the generator that backs it (a Callable holds
## no reference to its object, so the world must).
var rng: Mulberry32 = null
var rand: Callable = Callable()
var seed: int = 0

## Monotonic simulation time, seconds. Advances even when `time_frozen`.
var time: float = 0.0
## Position in the day, [0, 1).
var day_phase: float = 0.12
var day: int = 1
## `night_factor(day_phase, season.spec.night_share)`, [0, 1].
var night: float = 0.0
## Dev freeze: stops the day, not `time`.
var time_frozen: bool = false

## The actor id whose role is `player`, or "" when the run has none.
var player_id: String = ""
var player: PlayerState = null
## Props, mobs and forage from the layout; drops and built props are appended
## at runtime.
var entities: Array = []

## The pack: one entry per slot, `{item, count, uses}` or null.
var slots: Array = []
var base_slots: int = 12
var selected: int = 0
## What is worn rather than carried (not the viewer's, whose pack was the whole
## body): `hand` holds the tool a verb reaches for first, `body` the one worn
## thing whose insulation counts, `back` the one pack whose slots count. Each
## is `{item, count, uses}` or null; `Inventory.equip` and `unequip` move
## things between here and the slots.
var equipment: Dictionary = {"hand": null, "body": null, "back": null}
## A lit torch is a light on the player, not an entity.
var torch: Dictionary = {"remaining": 0.0, "radius": 0.0}
## A warm stone holds the cold off; a heat on the player, not an entity.
var warm: Dictionary = {"remaining": 0.0}

## `{calendar, specs, force, id, index, day_in_season, spec, turns}`.
var season: Dictionary = {}
## The prop look the world shows ("" = the summer sprites).
var look: String = ""
## Edge latch for the freezing message.
var freezing: bool = false

var craft_open: bool = false
var craft_index: int = 0
## Props built this session; the source of the `c1, c2, …` ids.
var built: int = 0

## Yields waiting for a trunk to land: `{at, yields, x, z, dir_x, dir_z, spread}`.
var drops: Array = []
## Counter behind the `i1, i2, …` item ids.
var drop_count: int = 0
## Drained by the view and the ear each frame.
var events: Array = []

## Held: `x`, `z`, `interact`. One-shot (cleared by `Sim` after every step):
## everything else.
var input: Dictionary = {}
## The current interactable, or null.
var target: Variant = null
## The one light in the frame.
var light: Dictionary = {"x": 0.0, "z": 0.0, "radius": 6.0, "on": false}
## `{mode, condition, rain, target, wet, hold, snow, snow_target, hold_snow,
## wet_spell, peak, spell_ends_at, next_strike_at, flash_at, strikes,
## last_strike, pending}`.
var weather: Dictionary = {}
var dead: bool = false
var message: String = ""
var message_at: float = -99.0

## Not the viewer's: its frame loop kept the fixed-step accumulator as a local.
## Hoisting it onto the world keeps `Sim.tick` a pure function of the world.
var accumulator: float = 0.0
## Kept so a reset can rebuild the same world.
var package: RunPackage = null
var options: Dictionary = {}

## Build a world from a run package.
##
## `opts` mirrors the viewer's start modes: `season` (`auto` or a season id),
## `time` (`noon` or `night`), `weather` (a weather mode), and `masks` (a
## `Masks` to adopt instead of rebuilding, which is how a reset keeps them).
static func create(pkg: RunPackage, seed_value: int, opts: Dictionary = {}) -> World:
	var world := World.new()
	world.package = pkg
	world.options = opts.duplicate()
	world.manifest = pkg.manifest
	var manifest := world.manifest
	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else manifest.get("layout", {})
	var rules: Dictionary = manifest.get("gameplay", {})

	world.seed = seed_value
	world.rng = Mulberry32.new(seed_value)
	world.rand = Callable(world.rng, "next")
	world.masks = opts["masks"] if opts.get("masks") is Masks else Masks.from_package(pkg)

	world.entities = _build_entities(manifest, layout)

	var crafting: Dictionary = manifest.get("crafting", {})
	world.base_slots = int(crafting.get("slots", 12)) if crafting.get("slots") else 12

	var spawn: Dictionary = layout.get("player_spawn", {"x": 0.0, "z": 0.0})
	var player := PlayerState.new()
	player.x = float(spawn.get("x", 0.0))
	player.z = float(spawn.get("z", 0.0))
	player.health = _positive(rules.get("health", {}).get("max"), 100.0)
	player.hunger = _positive(rules.get("hunger", {}).get("max"), 100.0)
	player.warmth = _positive(rules.get("warmth", {}).get("max"), 100.0)
	var player_entry := _player_actor(manifest)
	if player_entry.is_empty():
		player.radius = 0.34
	else:
		world.player_id = String(player_entry["id"])
		player.radius = _positive((player_entry["actor"] as Dictionary).get("footprint_radius_meters"), 0.3)
	world.player = player

	world.season = _create_season(manifest, String(opts.get("season", "auto")))
	world.weather = _create_weather(manifest, String(opts.get("weather", "auto")))
	world.input = fresh_input()

	# The viewer's boot applies `?time=night` just before the loop starts
	# (index.html:5296); the host folds it into creation so a fresh world is
	# already at night.
	if String(opts.get("time", "noon")) == "night":
		world.day_phase = 0.72
		world.night = 1.0

	# `crafting.start` is dead code in the viewer (its loop sits after the
	# `return`). The starting kit is authored, so the host applies it.
	var start: Dictionary = crafting.get("start", {}) if crafting.get("start") is Dictionary else {}
	for item_id: String in start.keys():
		world._add_start_item(item_id, int(start[item_id]))
	return world

## A fresh world on a new seed, keeping what a reset keeps: the ground masks
## (which the viewer lost) and the weather mode.
static func reset(old: World) -> World:
	var opts := old.options.duplicate()
	opts["masks"] = old.masks
	opts["weather"] = String(old.weather.get("mode", "auto"))
	opts["season"] = String(old.season.get("force", "auto"))
	return create(old.package, (old.seed + 1) & 0x7FFFFFFF, opts)

## The input bag, with every one-shot cleared.
static func fresh_input() -> Dictionary:
	return {
		"x": 0.0,
		"z": 0.0,
		"interact": false,
		"light": false,
		"craft_toggle": false,
		"menu_move": 0,
		"menu_confirm": false,
		"use": false,
		"drop": false,
		"select": null,
		"cycle": 0,
		"menu_select": null,
		"click_entity": null,
		"click_point": null,
		"equip": false,
		"unequip": null,
	}

## Whether a point may be walked on. Until a run's splat is read, and for a run
## with no coast, everything is land.
func is_land(x: float, z: float) -> bool:
	if masks == null:
		return true
	return masks.is_land(x, z)

## The friction coefficient of the ground under a point.
func friction_at(x: float, z: float) -> float:
	if masks == null:
		return Masks.DEFAULT_FRICTION
	return masks.friction_at(x, z)

func emit(event: Dictionary) -> void:
	events.append(event)

func say(text: String) -> void:
	message = text
	message_at = time

## `manifest.props[entity.prop_id]`, or an empty dictionary.
func prop_spec(entity: Dictionary) -> Dictionary:
	var props: Dictionary = manifest.get("props", {})
	var spec: Variant = props.get(String(entity.get("prop_id", "")))
	return spec if spec is Dictionary else {}

static func _build_entities(manifest: Dictionary, layout: Dictionary) -> Array:
	var entities: Array = []
	var props: Dictionary = manifest.get("props", {})
	var actors: Dictionary = manifest.get("actors", {})
	for raw: Dictionary in layout.get("entities", []):
		var kind := String(raw.get("kind", ""))
		if kind == "prop":
			var prop_id := String(raw.get("prop", ""))
			if not props.has(prop_id):
				# A prop the manifest lost is dropped silently.
				continue
			var prop: Dictionary = props[prop_id]
			var states: Dictionary = prop.get("states", {})
			var state := String(raw.get("state", ""))
			if not states.has(state):
				state = String(prop.get("baseline_state", ""))
			var radius := 0.0
			if raw.get("footprint_radius_meters") != null:
				radius = float(raw["footprint_radius_meters"])
			elif prop.get("footprint_radius_meters") != null:
				radius = float(prop["footprint_radius_meters"])
			entities.append({
				"id": String(raw.get("id", "")),
				"kind": "prop",
				"prop_id": prop_id,
				# The look this instance was placed with: what regrowing
				# returns it to, and what its interaction spends.
				"state": state,
				"baseline": state,
				"x": float(raw.get("x", 0.0)),
				"z": float(raw.get("z", 0.0)),
				"seed": int(raw.get("seed", 0)),
				"radius": radius,
				"hits": 0,
				"regrow": 0.0,
				"burn": 0.0,
				"dirty": false,
				# The grove or host this instance came with, and the set piece it
				# is a member of; "" for a lone one. Carried for the map and the
				# tools; the sim reads neither.
				"cluster": String(raw.get("cluster", "")),
				"set_piece": String(raw.get("set_piece", "")),
			})
		elif kind == "mob":
			var actor_id := String(raw.get("actor", ""))
			if not actors.has(actor_id):
				continue
			var actor: Dictionary = actors[actor_id]
			var x := float(raw.get("x", 0.0))
			var z := float(raw.get("z", 0.0))
			entities.append({
				"id": String(raw.get("id", "")),
				"kind": "mob",
				"actor_id": actor_id,
				"state": "idle",
				"x": x,
				"z": z,
				"home_x": x,
				"home_z": z,
				"vx": 0.0,
				"vz": 0.0,
				"facing": "right",
				"elapsed": 0.0,
				"cooldown": 0.0,
				"seed": int(raw.get("seed", 0)),
				"radius": _positive(actor.get("footprint_radius_meters"), 0.3),
				"dirty": false,
			})
	# The forage: every scattered piece is a thing to take, keyed to its
	# instance on the sheet so the view can hide it while it regrows. No
	# footprint: the player walks over a twig.
	var ground: Dictionary = manifest.get("ground", {})
	var forage_spec: Variant = ground.get("forage")
	var cells: Array = []
	if forage_spec is Dictionary and (forage_spec as Dictionary).get("cells") is Array:
		cells = (forage_spec as Dictionary)["cells"]
	var forage: Array = layout.get("forage", [])
	for index in forage.size():
		var raw: Dictionary = forage[index]
		var cell_index := int(raw.get("cell", -1))
		if cell_index < 0 or cell_index >= cells.size():
			continue
		var cell: Dictionary = cells[cell_index]
		if String(cell.get("item_id", "")) == "":
			# A cell with no item is not an entity.
			continue
		entities.append({
			"id": "f%d" % index,
			"kind": "forage",
			"index": index,
			"cell": cell_index,
			"item_id": String(cell["item_id"]),
			"count": int(cell.get("count", 1)) if cell.get("count") else 1,
			"regrow_seconds": _positive(cell.get("regrow_seconds"), 120.0),
			"x": float(raw.get("x", 0.0)),
			"z": float(raw.get("z", 0.0)),
			"taken": false,
			"picked": false,
			"hidden": false,
			"regrow": 0.0,
			"radius": 0.0,
			"dirty": false,
		})
	return entities

static func _player_actor(manifest: Dictionary) -> Dictionary:
	var actors: Dictionary = manifest.get("actors", {})
	for id: String in actors.keys():
		var actor: Dictionary = actors[id]
		if String(actor.get("role", "")) == "player":
			return {"id": id, "actor": actor}
	return {}

static func _create_season(manifest: Dictionary, force: String) -> Dictionary:
	var block: Dictionary = manifest.get("seasons", {}) if manifest.get("seasons") is Dictionary else {}
	var calendar: Variant = block.get("calendar")
	var specs: Dictionary = {}
	for spec: Dictionary in block.get("seasons", []):
		specs[String(spec.get("season_id", ""))] = spec
	return {
		"calendar": calendar,
		"specs": specs,
		"force": force if force != "" else "auto",
		"id": "",
		"index": 0,
		"day_in_season": 1,
		"spec": Helpers.NO_SEASON,
		"turns": 0,
	}

static func _create_weather(manifest: Dictionary, mode: String) -> Dictionary:
	var block: Dictionary = manifest.get("weather", {}) if manifest.get("weather") is Dictionary else {}
	# "" where the viewer has null: this run has no rain condition at all.
	var condition := "rain" if block.get("rain") is Dictionary else ""
	# Deviation from the viewer, whose first spell was wet: `spell_ends_at` 0
	# fell due on the first step and flipped `wet_spell` to true, so every new
	# world opened under rain. Here the first spell is dry and lasts the
	# authored minimum, undrawn, so the PRNG sequence is the viewer's from the
	# first draw on and a new world opens under a clear sky.
	var first_dry := 0.0
	if condition != "":
		var span: Variant = (block["rain"] as Dictionary).get("dry_spell_seconds")
		if span is Array and not (span as Array).is_empty():
			first_dry = float((span as Array)[0])
	return {
		"mode": mode if mode != "" else "auto",
		"condition": condition,
		"rain": 0.0,
		"target": 0.0,
		"wet": 0.0,
		"hold": 0.0,
		"snow": 0.0,
		"snow_target": 0.0,
		"hold_snow": 0.0,
		"wet_spell": false,
		"peak": 0.0,
		"spell_ends_at": first_dry,
		"next_strike_at": INF,
		"flash_at": -99.0,
		"strikes": 0,
		"last_strike": null,
		"pending": [],
	}

## `invAdd` for the authored starting kit only, so world creation does not
## depend on the inventory module. The pack is empty here, so the two passes of
## the real helper collapse into one fill.
func _add_start_item(item_id: String, count: int) -> void:
	var items: Dictionary = manifest.get("items", {})
	var spec: Dictionary = items.get(item_id, {}) if items.get(item_id) is Dictionary else {}
	var stack_max := int(spec.get("stack_max", 1)) if spec.get("stack_max") else 1
	var tool: Variant = spec.get("tool")
	var uses: Variant = null
	if tool is Dictionary:
		uses = (tool as Dictionary).get("uses")
	var left := count
	while slots.size() < _start_capacity():
		slots.append(null)
	var index := 0
	while index < slots.size() and left > 0:
		if slots[index] == null:
			var take := mini(stack_max, left)
			slots[index] = {"item": item_id, "count": take, "uses": uses}
			left -= take
			while slots.size() < _start_capacity():
				slots.append(null)
		index += 1
	if left > 0:
		push_warning("crafting.start: %d %s did not fit the pack" % [left, item_id])

func _start_capacity() -> int:
	# Nothing in the kit is worn, so a pack in it carries nothing yet.
	return base_slots


static func _positive(value: Variant, fallback: float) -> float:
	if (value is float or value is int) and float(value) != 0.0:
		return float(value)
	return fallback
