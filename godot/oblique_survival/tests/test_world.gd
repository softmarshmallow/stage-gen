extends RefCounted

## `createWorld` against full-v66: every placed thing becomes an entity, the
## player stands where the layout put them, and the pack is the authored one.

func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	var world := World.create(pkg, int(pkg.layout.get("seed", 1)), {"masks": Masks.new()})

	_entity_counts(h, pkg, world)
	_player(h, pkg, world)
	_pack(h, world)
	_clock_and_conditions(h, world)
	_start_kit(h, pkg)

func _entity_counts(h: TestHarness, pkg: RunPackage, world: World) -> void:
	var counts: Dictionary = pkg.layout.get("counts", {})
	var tallied: Dictionary = {}
	var forage := 0
	for entity: Dictionary in world.entities:
		match entity["kind"]:
			"prop":
				tallied[entity["prop_id"]] = int(tallied.get(entity["prop_id"], 0)) + 1
			"mob":
				tallied[entity["actor_id"]] = int(tallied.get(entity["actor_id"], 0)) + 1
			"forage":
				forage += 1
	for id: String in counts.keys():
		h.assert_eq(tallied.get(id, 0), counts[id], "entities placed for %s" % id)
	h.assert_eq(tallied.size(), counts.size(), "a prop or mob id was invented or lost")
	h.assert_eq(forage, pkg.layout.get("forage", []).size(), "forage entities")
	h.assert_eq(
		world.entities.size(),
		pkg.layout.get("entities", []).size() + pkg.layout.get("forage", []).size(),
		"total entities",
	)

	# The layout's footprint overrides the prop's: the tent is placed at 1.275,
	# not the prop's 1.054.
	var tent := _entity(world, "p0000")
	if h.assert_true(not tent.is_empty(), "the tent p0000 is missing"):
		h.assert_eq(tent["prop_id"], "canvas_tent", "p0000 is not the tent")
		h.assert_near(float(tent["radius"]), 1.275, 1e-6, "the layout footprint did not win")
		h.assert_eq(tent["state"], "pitched", "the tent's placed state")
		h.assert_eq(tent["baseline"], tent["state"], "baseline is the placed variant")
		h.assert_eq(int(tent["hits"]), 0, "a fresh prop has hits")
		h.assert_eq(tent["dirty"], false, "a fresh prop is dirty")

	# A mob anchors its wander orbit where it was placed.
	var mob := {}
	for entity: Dictionary in world.entities:
		if entity["kind"] == "mob":
			mob = entity
			break
	if h.assert_true(not mob.is_empty(), "no mob was placed"):
		h.assert_eq(mob["actor_id"], "grub_hound", "the mob's actor")
		h.assert_near(float(mob["home_x"]), float(mob["x"]), 1e-9, "home_x is not the spawn")
		h.assert_near(float(mob["home_z"]), float(mob["z"]), 1e-9, "home_z is not the spawn")
		h.assert_near(float(mob["radius"]), 0.476, 1e-6, "the mob's footprint")
		h.assert_eq(mob["state"], "idle", "a fresh mob's state")

	# Forage carries its cell's item, count and regrow time, and no footprint.
	var forage_entity := {}
	for entity: Dictionary in world.entities:
		if entity["kind"] == "forage":
			forage_entity = entity
			break
	if h.assert_true(not forage_entity.is_empty(), "no forage was placed"):
		var cells: Array = pkg.manifest["ground"]["forage"]["cells"]
		var cell: Dictionary = cells[int(forage_entity["cell"])]
		h.assert_eq(forage_entity["item_id"], cell["item_id"], "the forage's item")
		h.assert_eq(int(forage_entity["count"]), int(cell["count"]), "the forage's count")
		h.assert_near(
			float(forage_entity["regrow_seconds"]),
			float(cell["regrow_seconds"]),
			1e-6,
			"the forage's regrow time",
		)
		h.assert_near(float(forage_entity["radius"]), 0.0, 1e-9, "forage has a footprint")
		h.assert_eq(forage_entity["id"], "f%d" % int(forage_entity["index"]), "the forage id is its index")

func _player(h: TestHarness, pkg: RunPackage, world: World) -> void:
	var spawn: Dictionary = pkg.layout.get("player_spawn", {})
	h.assert_eq(world.player_id, "wren", "the player actor")
	h.assert_near(world.player.x, float(spawn["x"]), 1e-9, "player spawn x")
	h.assert_near(world.player.z, float(spawn["z"]), 1e-9, "player spawn z")
	h.assert_near(world.player.z, 2.4, 1e-9, "full-v66 spawns the player at z = 2.4")
	h.assert_near(world.player.radius, 0.34, 1e-6, "the player's footprint")
	h.assert_near(world.player.health, 100.0, 1e-9, "starting health")
	h.assert_near(world.player.hunger, 100.0, 1e-9, "starting hunger")
	h.assert_near(world.player.warmth, 100.0, 1e-9, "starting warmth")
	h.assert_eq(world.player.facing, "front", "starting facing")
	h.assert_eq(world.player.state, "idle", "starting state")
	h.assert_eq(world.player.busy, null, "a fresh player is busy")
	h.assert_eq(world.player.approach, null, "a fresh player is walking somewhere")
	# The player is not an entity.
	for entity: Dictionary in world.entities:
		if entity.get("actor_id") == "wren":
			h.fail("the player was placed as an entity")
			break

func _pack(h: TestHarness, world: World) -> void:
	h.assert_eq(world.base_slots, 12, "crafting.slots")
	h.assert_eq(world.selected, 0, "the selected slot")
	h.assert_eq(world.slots.size(), 0, "full-v66 authors no starting kit")
	h.assert_near(float(world.torch["remaining"]), 0.0, 1e-9, "a fresh world has a lit torch")
	h.assert_near(float(world.warm["remaining"]), 0.0, 1e-9, "a fresh world has a warm stone")

func _clock_and_conditions(h: TestHarness, world: World) -> void:
	h.assert_near(world.day_phase, 0.12, 1e-9, "the day starts at 0.12")
	h.assert_eq(world.day, 1, "the world starts on day 1")
	h.assert_near(world.time, 0.0, 1e-9, "the world starts at t = 0")
	h.assert_eq(world.season["id"], "", "the season before the first tick")
	h.assert_near(float((world.season["spec"] as Dictionary)["night_share"]), 0.38, 1e-9, "the tick-0 night share")
	h.assert_eq(world.look, "", "the world starts on the summer sprites")
	h.assert_eq(world.weather["condition"], "rain", "full-v66 has a rain condition")
	h.assert_eq(world.weather["mode"], "auto", "the weather starts on auto")
	h.assert_eq(world.light["on"], false, "a fresh world is lit")
	h.assert_eq(world.dead, false, "a fresh world is dead")
	h.assert_eq(world.events.size(), 0, "a fresh world has events")
	h.assert_eq(world.input, World.fresh_input(), "the input bag")

	# The start modes the host's `--time` and `--season` reach.
	var pkg := h.package()
	var night_world := World.create(pkg, 7, {"masks": Masks.new(), "time": "night", "season": "winter"})
	h.assert_near(night_world.day_phase, 0.72, 1e-9, "--time night day phase")
	h.assert_near(night_world.night, 1.0, 1e-9, "--time night is not night")
	h.assert_eq(night_world.season["force"], "winter", "--season winter was not forced")

## `crafting.start` is dead code in the viewer; the host applies it, so a run
## that authors a starting kit gets one.
func _start_kit(h: TestHarness, pkg: RunPackage) -> void:
	var kit := RunPackage.new()
	kit.run_dir = pkg.run_dir
	kit.manifest = pkg.manifest.duplicate()
	var crafting: Dictionary = (pkg.manifest["crafting"] as Dictionary).duplicate()
	crafting["start"] = {"axe": 1, "berry": 12}
	kit.manifest["crafting"] = crafting
	# An empty layout: this is about the pack, not the world.
	kit.layout = {"entities": [], "forage": [], "player_spawn": {"x": 0.0, "z": 0.0}}

	var world := World.create(kit, 7, {"masks": Masks.new()})
	h.assert_eq(world.entities.size(), 0, "the empty layout placed entities")
	if not h.assert_true(world.slots.size() >= 3, "the starting kit did not fill three slots"):
		return
	var axe: Dictionary = world.slots[0]
	h.assert_eq(axe["item"], "axe", "the first slot")
	h.assert_eq(int(axe["count"]), 1, "the axe's count")
	h.assert_eq(int(axe["uses"]), 25, "the axe carries its wear")
	var first: Dictionary = world.slots[1]
	var second: Dictionary = world.slots[2]
	h.assert_eq(first["item"], "berry", "the second slot")
	h.assert_eq(int(first["count"]), 10, "berries fill a stack to stack_max")
	h.assert_eq(int(second["count"]), 2, "the rest of the berries spill into the next slot")
	h.assert_eq(first["uses"], null, "a stack that is not a tool carries no wear")

func _entity(world: World, id: String) -> Dictionary:
	for entity: Dictionary in world.entities:
		if entity["id"] == id:
			return entity
	return {}
