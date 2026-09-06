extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T20.
##
## Every one of the eleven recipes made, the two stations refused when they are
## out of reach or in the wrong state, the eight headings a built prop is tried
## at, and the rule that a refused build spends nothing.

const STEP := 1.0 / 60.0
## The headings `placeProp` tries around the player's facing (index.html:751).
const HEADINGS := [0.0, 0.7, -0.7, 1.4, -1.4, 2.1, -2.1, PI]


func run(h: TestHarness) -> void:
	var world := SimFixture.world()
	if world == null:
		h.fail("could not open %s" % TestHarness.RUN_DIR)
		return
	_every_recipe(h, world)
	_station_reach(h, world)
	_station_state(h, world)
	_headings(h, world)
	_a_refused_build_spends_nothing(h, world)
	_the_menu(h, world)


## A bare stage at the camp, on land, facing the camera, with nothing carried.
func _stage(world: World) -> void:
	SimFixture.bare(world)
	world.camera_yaw = 0.0
	world.player.x = 0.0
	world.player.z = 0.0
	world.player.facing = "front"
	world.player.busy = null
	world.player.approach = null
	world.dead = false
	world.built = 0
	world.craft_open = false
	world.craft_index = 0
	world.message = ""
	SimFixture.force_season(world, "summer")


## The station a recipe names, standing in reach in the state it wants.
func _put_station(world: World, station: String) -> void:
	if station == "hand":
		return
	var stations: Dictionary = (world.manifest["crafting"] as Dictionary)["stations"]
	var spec: Dictionary = stations[station]
	var prop := SimFixture.prop(world, "st1", str(spec["prop_id"]), "", 0.0, -2.0)
	var wanted: Variant = spec.get("state")
	var props: Dictionary = world.manifest["props"]
	var template: Dictionary = props[str(spec["prop_id"])]
	prop["state"] = str(wanted) if wanted != null and str(wanted) != "" else str(template["baseline_state"])
	prop["baseline"] = prop["state"]
	world.entities.append(prop)


# ---------------------------------------------------------------------------
# Every recipe.
# ---------------------------------------------------------------------------

## All eleven: hand the player exactly what each one costs, stand the station
## it names behind them, and assert the product arrived and the cost was paid.
func _every_recipe(h: TestHarness, world: World) -> void:
	var recipes: Array = (world.manifest["crafting"] as Dictionary)["recipes"]
	h.assert_eq(recipes.size(), 11, "the run authors eleven recipes")
	var made := PackedStringArray()
	var failed := PackedStringArray()
	var unpaid := PackedStringArray()
	for recipe: Dictionary in recipes:
		_stage(world)
		_put_station(world, str(recipe.get("station", "hand")))
		var ingredients: Dictionary = recipe["ingredients"]
		for item_id: String in ingredients.keys():
			Inventory.inv_add(world, item_id, int(ingredients[item_id]))
		var status := SysCraft.recipe_status(world, recipe)
		if not bool(status["ok"]):
			failed.append("%s (status)" % str(recipe["recipe_id"]))
			continue
		if not SysCraft.craft_recipe(world, recipe):
			failed.append("%s (%s)" % [str(recipe["recipe_id"]), world.message])
			continue
		# The cost is gone.
		for item_id: String in ingredients.keys():
			if Inventory.count(world, item_id) != 0:
				unpaid.append(str(recipe["recipe_id"]))
				break
		var product: Dictionary = recipe["product"]
		var prop_id: Variant = product.get("prop_id")
		if prop_id != null and str(prop_id) != "":
			var built := _built_prop(world, str(prop_id))
			if built.is_empty():
				failed.append("%s (nothing built)" % str(recipe["recipe_id"]))
				continue
		elif Inventory.count(world, str(product["item_id"])) != int(product.get("count", 1)):
			failed.append("%s (no product)" % str(recipe["recipe_id"]))
			continue
		made.append(str(recipe["recipe_id"]))
	h.assert_eq(failed.size(), 0, "these recipes did not make their product: %s" % str(failed))
	h.assert_eq(unpaid.size(), 0, "these recipes did not spend their ingredients: %s" % str(unpaid))
	h.assert_eq(made.size(), 11, "only %d of the eleven recipes were made" % made.size())

	# A recipe whose ingredients are short says what is missing and makes
	# nothing.
	_stage(world)
	var axe_recipe: Dictionary = _recipe(world, "axe")
	Inventory.inv_add(world, "twig", 1)
	h.assert_false(SysCraft.craft_recipe(world, axe_recipe), "an axe was made out of one twig")
	h.assert_eq(world.message, "Need 1 Flint.", "the shortfall is named")
	h.assert_eq(Inventory.count(world, "twig"), 1, "and the twig was not spent")

	# A product that does not fit falls at the player's feet rather than being
	# lost. Every slot is filled with a stack deep enough that paying for the
	# poultice does not empty one of them.
	_stage(world)
	Inventory.inv_add(world, "grass_tuft", 10)
	Inventory.inv_add(world, "moss", 10)
	Inventory.inv_add(world, "log", 100)
	h.assert_eq(Inventory.slot_capacity(world), 12, "the pack is twelve slots")
	var empty := 0
	for slot: Variant in world.slots:
		if slot == null:
			empty += 1
	h.assert_eq(empty, 0, "the pack was not full before the overflow test")
	h.assert_true(SysCraft.craft_recipe(world, _recipe(world, "poultice")), "the poultice was not made")
	h.assert_eq(Inventory.count(world, "poultice"), 0, "the poultice went into a full pack")
	var dropped := 0
	for entity: Dictionary in world.entities:
		if str(entity.get("kind", "")) == "item" and str(entity.get("item_id", "")) == "poultice":
			dropped += 1
	h.assert_eq(dropped, 1, "the poultice did not fall at the player's feet")
	h.assert_true(world.message.contains("the pack is full"), "and nothing was said about it")


# ---------------------------------------------------------------------------
# Stations.
# ---------------------------------------------------------------------------

## `cooked_berry` and `warm_stone` want a lit campfire within an edge distance
## of 3 m; `pickaxe`, `backpack` and `grass_cloak` want a workbench.
func _station_reach(h: TestHarness, world: World) -> void:
	var cooked: Dictionary = _recipe(world, "cooked_berry")
	h.assert_eq(str(cooked["station"]), "campfire", "stewed berries are cooked on a fire")
	var reach := float((((world.manifest["crafting"] as Dictionary)["stations"] as Dictionary)["campfire"] as Dictionary)["reach_meters"])
	h.assert_near(reach, 3.0, 1e-9, "the campfire's reach")

	# No fire at all.
	_stage(world)
	Inventory.inv_add(world, "berry", 2)
	h.assert_false(SysCraft.craft_recipe(world, cooked), "berries were stewed with no fire")
	h.assert_eq(world.message, "Needs a campfire within reach.", "and the refusal names the station")
	h.assert_eq(Inventory.count(world, "berry"), 2, "the berries were not spent")

	# A lit fire whose edge is inside 3 m: 3.3 m of centre less the 0.374 m
	# footprint is 2.926 m, and the recipe goes.
	_stage(world)
	Inventory.inv_add(world, "berry", 2)
	_fire(world, 3.3, "lit")
	h.assert_true(SysCraft.craft_recipe(world, cooked), "a fire 2.926 m away was refused")
	h.assert_eq(Inventory.count(world, "cooked_berry"), 1, "the stew was not made")

	# One step further out and the edge is past the reach.
	_stage(world)
	Inventory.inv_add(world, "berry", 2)
	_fire(world, 3.5, "lit")
	h.assert_false(SysCraft.craft_recipe(world, cooked), "a fire 3.126 m away was accepted")
	h.assert_eq(Inventory.count(world, "berry"), 2, "and nothing was spent")

	# The pick wants a workbench, and says so.
	_stage(world)
	Inventory.inv_add(world, "flint", 2)
	Inventory.inv_add(world, "twig", 2)
	var pickaxe: Dictionary = _recipe(world, "pickaxe")
	h.assert_false(SysCraft.craft_recipe(world, pickaxe), "a pick was made with no workbench")
	h.assert_eq(world.message, "Needs a workbench within reach.", "the refusal names the workbench")
	h.assert_eq(Inventory.count(world, "flint"), 2, "the flint was not spent")
	_put_station(world, "workbench")
	h.assert_true(SysCraft.craft_recipe(world, pickaxe), "with a workbench the pick is made")
	h.assert_eq(Inventory.count(world, "pickaxe"), 1, "and it is in the pack")


## The campfire station wants the `lit` state; the workbench authors none, so
## any state serves.
func _station_state(h: TestHarness, world: World) -> void:
	var cooked: Dictionary = _recipe(world, "cooked_berry")
	_stage(world)
	Inventory.inv_add(world, "berry", 2)
	var fire := _fire(world, 2.0, "unlit")
	h.assert_false(SysCraft.craft_recipe(world, cooked), "berries were stewed on a cold fire")
	h.assert_eq(Inventory.count(world, "berry"), 2, "and nothing was spent")
	fire["state"] = "lit"
	h.assert_true(SysCraft.craft_recipe(world, cooked), "lighting the same fire did not help")

	var stations: Dictionary = (world.manifest["crafting"] as Dictionary)["stations"]
	h.assert_eq((stations["workbench"] as Dictionary).get("state"), null,
		"the workbench authors no required state")
	h.assert_eq(str((stations["campfire"] as Dictionary).get("state")), "lit",
		"the campfire's required state")


# ---------------------------------------------------------------------------
# Placing a built prop.
# ---------------------------------------------------------------------------

## The eight headings, tried in order around the player's facing, at
## `radius + player.radius + 0.45`.
func _headings(h: TestHarness, world: World) -> void:
	h.assert_eq(SysCraft.PLACE_OFFSETS, HEADINGS, "the eight headings, in order")

	var radius := float(((world.manifest["props"] as Dictionary)["campfire"] as Dictionary)["footprint_radius_meters"])
	h.assert_near(radius, 0.374, 1e-9, "the campfire's footprint")
	var stand_off := radius + world.player.radius + 0.45
	h.assert_near(stand_off, 0.374 + 0.34 + 0.45, 1e-9, "the stand-off distance")

	# Facing `front` at yaw 0 is world +z, so the first heading puts the fire
	# straight in front of the player.
	_stage(world)
	var built: Variant = SysCraft.place_prop(world, "campfire")
	if not h.assert_true(built != null, "nothing could be built in an empty clearing"):
		return
	var first := built as Dictionary
	h.assert_near(float(first["x"]), 0.0, 1e-6, "the first heading is straight ahead")
	h.assert_near(float(first["z"]), stand_off, 1e-6, "at the stand-off distance")
	h.assert_eq(str(first["id"]), "c1", "the first built prop is c1")
	h.assert_eq(str(first["state"]), "unlit", "it is built in its baseline look")
	h.assert_eq(str(first["baseline"]), "unlit", "which is also its baseline")
	h.assert_near(float(first["radius"]), radius, 1e-9, "with the prop's own footprint")

	# Block the first heading only, and the second is taken. A cut-grass tuft
	# is small enough that the 0.7 rad neighbour stays clear.
	_stage(world)
	var blocker := SimFixture.prop(world, "g1", "grass_tuft", "standing", 0.0, stand_off)
	world.entities.append(blocker)
	var second: Variant = SysCraft.place_prop(world, "campfire")
	if not h.assert_true(second != null, "the second heading was not tried"):
		return
	var base := PI * 0.5
	h.assert_near(float((second as Dictionary)["x"]), cos(base + 0.7) * stand_off, 1e-6,
		"the fire did not fall back to the 0.7 rad heading")
	h.assert_near(float((second as Dictionary)["z"]), sin(base + 0.7) * stand_off, 1e-6,
		"on both axes")

	# Placing draws exactly one value, for the card's seed.
	_stage(world)
	world.rng = Mulberry32.new(99)
	world.rand = Callable(world.rng, "next")
	var reference := Mulberry32.new(99)
	var expected_seed := int(reference.next() * 1e5)
	var seeded: Variant = SysCraft.place_prop(world, "campfire")
	h.assert_eq(int((seeded as Dictionary)["seed"]), expected_seed, "the built prop's seed")
	h.assert_near(float(world.rand.call()), reference.next(), 1e-12, "placing drew more than one value")


## Every heading blocked: the build is refused and the ingredients stay.
func _a_refused_build_spends_nothing(h: TestHarness, world: World) -> void:
	_stage(world)
	# A tent on top of the player: its 1.054 m footprint plus the fire's 0.374
	# plus the 0.2 clearance is 1.628 m, which swallows every 1.164 m heading.
	world.entities.append(SimFixture.prop(world, "t1", "canvas_tent", "pitched", 0.0, 0.0))
	h.assert_true(SysCraft.place_prop(world, "campfire") == null, "a blocked clearing still built")
	h.assert_eq(world.built, 0, "and it counted a build")

	Inventory.inv_add(world, "grass_tuft", 3)
	Inventory.inv_add(world, "log", 2)
	var campfire: Dictionary = _recipe(world, "campfire")
	world.message = ""
	h.assert_false(SysCraft.craft_recipe(world, campfire), "the fire was built with nowhere to put it")
	h.assert_eq(world.message, "No room to build here.", "and the refusal says why")
	h.assert_eq(Inventory.count(world, "grass_tuft"), 3, "the grass was not spent")
	h.assert_eq(Inventory.count(world, "log"), 2, "nor the logs")

	# The water is not ground either: standing on the shore facing the sea, a
	# heading that lands off the land is skipped.
	_stage(world)
	world.player.x = 0.0
	world.player.z = 0.0
	h.assert_true(world.is_land(0.0, 0.0), "the camp is land")
	h.assert_false(world.is_land(-125.0, -125.0), "and the far corner is not")


# ---------------------------------------------------------------------------
# The menu the crafting system drives.
# ---------------------------------------------------------------------------

func _the_menu(h: TestHarness, world: World) -> void:
	var recipes: Array = (world.manifest["crafting"] as Dictionary)["recipes"]
	_stage(world)
	world.input["craft_toggle"] = true
	SysCraft.update(world, STEP)
	h.assert_eq(world.craft_open, true, "C did not open the table")
	h.assert_eq(world.craft_index, 0, "it opens on the first recipe")
	Sim.clear_one_shots(world)

	world.input["menu_move"] = 1
	SysCraft.update(world, STEP)
	h.assert_eq(world.craft_index, 1, "S did not step down the list")
	Sim.clear_one_shots(world)

	world.input["menu_move"] = -1
	SysCraft.update(world, STEP)
	world.input["menu_move"] = -1
	SysCraft.update(world, STEP)
	h.assert_eq(world.craft_index, recipes.size() - 1, "the list did not wrap at the top")
	Sim.clear_one_shots(world)

	world.input["craft_toggle"] = true
	SysCraft.update(world, STEP)
	h.assert_eq(world.craft_open, false, "C did not close the table")


func _recipe(world: World, id: String) -> Dictionary:
	for recipe: Dictionary in ((world.manifest["crafting"] as Dictionary)["recipes"] as Array):
		if str(recipe["recipe_id"]) == id:
			return recipe
	return {}


func _fire(world: World, distance: float, state: String) -> Dictionary:
	var fire := SimFixture.prop(world, "f1", "campfire", "unlit", 0.0, distance)
	fire["state"] = state
	world.entities.append(fire)
	return fire


func _built_prop(world: World, prop_id: String) -> Dictionary:
	for entity: Dictionary in world.entities:
		if str(entity.get("kind", "")) == "prop" and str(entity.get("prop_id", "")) == prop_id \
				and str(entity.get("id", "")).begins_with("c"):
			return entity
	return {}
