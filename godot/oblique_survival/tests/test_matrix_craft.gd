extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T20.
##
## Every one of the eleven recipes made, the two stations refused when they are
## out of reach or in the wrong state, a built thing placed with the pointer in
## the look its recipe names, the rule that a spot that refuses spends nothing,
## and a made thing worn when its place is free.

const STEP := 1.0 / 60.0


func run(h: TestHarness) -> void:
	var world := SimFixture.world()
	if world == null:
		h.fail("could not open %s" % TestHarness.RUN_DIR)
		return
	_every_recipe(h, world)
	_station_reach(h, world)
	_station_state(h, world)
	_build_and_place(h, world)
	_a_refused_build_spends_nothing(h, world)
	_a_made_thing_is_worn_when_its_place_is_free(h, world)
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
	world.placing = null
	world.equipment = {"hand": null, "body": null, "back": null}
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
		var product: Dictionary = recipe["product"]
		var prop_id: Variant = product.get("prop_id")
		if prop_id != null and str(prop_id) != "":
			# A built thing goes to the pointer first; set it down where it starts.
			if world.placing == null:
				failed.append("%s (nothing came to the pointer)" % str(recipe["recipe_id"]))
				continue
			world.input["place_click"] = true
			SysCraft.update(world, STEP)
			Sim.clear_one_shots(world)
		# The cost is gone.
		for item_id: String in ingredients.keys():
			if Inventory.count(world, item_id) != 0:
				unpaid.append(str(recipe["recipe_id"]))
				break
		if prop_id != null and str(prop_id) != "":
			var built := _built_prop(world, str(prop_id))
			if built.is_empty():
				failed.append("%s (nothing built)" % str(recipe["recipe_id"]))
				continue
			if str(built["state"]) != str(product["state"]):
				failed.append("%s (built %s, not %s)" % [str(recipe["recipe_id"]), str(built["state"]), str(product["state"])])
				continue
		elif Inventory.count(world, str(product["item_id"])) + _worn_count(world, str(product["item_id"])) != int(product.get("count", 1)):
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
	var hand: Variant = world.equipment["hand"]
	h.assert_true(hand is Dictionary and str((hand as Dictionary)["item"]) == "pickaxe",
		"and, the hand being empty, it is worn at once")
	h.assert_eq(Inventory.count(world, "pickaxe"), 0, "not left in the pack")


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

## Making a built thing closes the table and puts its silhouette in front of
## the player; the pointer moves it; a spot answers in words; a click where it
## can stand builds it in the recipe's look and spends the makings then.
func _build_and_place(h: TestHarness, world: World) -> void:
	var radius := float(((world.manifest["props"] as Dictionary)["campfire"] as Dictionary)["footprint_radius_meters"])
	h.assert_near(radius, 0.374, 1e-9, "the campfire's footprint")
	var stand_off := radius + world.player.radius + SysCraft.PLACE_STAND_OFF
	h.assert_near(stand_off, 0.374 + 0.34 + 0.45, 1e-9, "the stand-off distance")

	_stage(world)
	Inventory.inv_add(world, "grass_tuft", 3)
	Inventory.inv_add(world, "log", 2)
	world.craft_open = true
	var campfire: Dictionary = _recipe(world, "campfire")
	h.assert_eq(str((campfire["product"] as Dictionary)["state"]), "lit", "the recipe builds the fire lit")
	h.assert_true(SysCraft.craft_recipe(world, campfire), "the fire did not go to the pointer")
	h.assert_false(world.craft_open, "making a built thing closes the table")
	if not h.assert_true(world.placing != null, "nothing came to the pointer"):
		return
	var placing := world.placing as Dictionary
	h.assert_eq(str(placing["prop_id"]), "campfire", "the thing on the pointer")
	h.assert_eq(str(placing["state"]), "lit", "in the look its recipe names")
	# Facing `front` at yaw 0 is world +z, so the silhouette starts straight
	# in front of the player.
	h.assert_near(float(placing["x"]), 0.0, 1e-6, "the silhouette starts straight ahead")
	h.assert_near(float(placing["z"]), stand_off, 1e-6, "at the stand-off distance")
	h.assert_true(bool(placing["ok"]), "and the clearing takes it")
	h.assert_eq(Inventory.count(world, "log"), 2, "nothing is spent yet")
	h.assert_eq(world.message, "Click where the campfire goes; right-click to keep the makings.",
		"and the strip says what to do")

	# The pointer moves it, and the spot answers: too far, then taken.
	world.input["place_point"] = {"x": 0.0, "z": 9.0}
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	h.assert_false(bool(placing["ok"]), "nine metres off is red")
	h.assert_eq(str(placing["why"]), SysCraft.WHY_FAR, "because it is out of reach")
	world.input["place_click"] = true
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	h.assert_eq(world.message, "Too far to reach.", "a click there says why")
	h.assert_true(world.placing != null, "and the build stays on the pointer")
	h.assert_true(_built_prop(world, "campfire").is_empty(), "nothing was built")
	h.assert_eq(Inventory.count(world, "log"), 2, "and nothing was spent")
	world.entities.append(SimFixture.prop(world, "t1", "canvas_tent", "pitched", 2.0, 0.0))
	world.input["place_point"] = {"x": 2.0, "z": 0.0}
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	h.assert_eq(str(placing["why"]), SysCraft.WHY_ROOM, "a tent's footprint refuses the spot")
	world.input["place_point"] = {"x": 0.0, "z": 0.0}
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	h.assert_eq(str(placing["why"]), SysCraft.WHY_ROOM, "and so does the player's own")
	# Water is not ground either, judged at the spot (the far corner is sea).
	h.assert_eq(SysCraft.place_verdict(world, -250.0, -250.0, radius), SysCraft.WHY_FAR, "the sea is far from here")
	world.player.x = -249.5
	world.player.z = -249.5
	h.assert_eq(SysCraft.place_verdict(world, -250.0, -250.0, radius), SysCraft.WHY_WATER, "and water when it is near")
	world.player.x = 0.0
	world.player.z = 0.0

	# Back in front, the click builds it: lit, burning as if just lit, with
	# the makings spent at the set-down.
	world.input["place_point"] = {"x": 0.0, "z": stand_off}
	world.input["place_click"] = true
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	var built := _built_prop(world, "campfire")
	if not h.assert_false(built.is_empty(), "the click built nothing"):
		return
	h.assert_eq(str(built["id"]), "c1", "the first built prop is c1")
	h.assert_near(float(built["x"]), 0.0, 1e-6, "where the silhouette stood (x)")
	h.assert_near(float(built["z"]), stand_off, 1e-6, "where the silhouette stood (z)")
	h.assert_eq(str(built["state"]), "lit", "built in the recipe's look")
	h.assert_eq(str(built["baseline"]), "unlit", "with the prop's baseline as what it returns to")
	h.assert_near(float(built["radius"]), radius, 1e-9, "with the prop's own footprint")
	h.assert_near(float(built["burn"]), 90.0, 1e-9, "built lit, it burns as if it had just been lit")
	h.assert_true(world.placing == null, "the pointer is empty again")
	h.assert_eq(Inventory.count(world, "log"), 0, "the logs are spent at the set-down")
	h.assert_eq(Inventory.count(world, "grass_tuft"), 0, "and the grass")
	h.assert_eq(world.message, "Campfire built.", "and it is said")
	h.assert_eq(SimFixture.events_of(world, "craft").size(), 1, "one craft event, at the set-down")

	# Building draws exactly one value, for the card's seed; a look no `light`
	# interaction leads to does not burn.
	_stage(world)
	world.rng = Mulberry32.new(99)
	world.rand = Callable(world.rng, "next")
	var reference := Mulberry32.new(99)
	var expected_seed := int(reference.next() * 1e5)
	var seeded: Variant = SysCraft.place_prop(world, "campfire", "unlit", 0.0, 2.0)
	h.assert_eq(int((seeded as Dictionary)["seed"]), expected_seed, "the built prop's seed")
	h.assert_near(float(world.rand.call()), reference.next(), 1e-12, "building drew more than one value")
	h.assert_near(float((seeded as Dictionary)["burn"]), 0.0, 1e-9, "built unlit, it does not burn")


## A spot that refuses spends nothing, and letting the build go spends nothing.
func _a_refused_build_spends_nothing(h: TestHarness, world: World) -> void:
	_stage(world)
	# A tent on top of the player: its 1.054 m footprint plus the fire's 0.374
	# plus the 0.2 clearance is 1.628 m, which swallows the 1.164 m spot in
	# front where the silhouette starts.
	world.entities.append(SimFixture.prop(world, "t1", "canvas_tent", "pitched", 0.0, 0.0))
	Inventory.inv_add(world, "grass_tuft", 3)
	Inventory.inv_add(world, "log", 2)
	var campfire: Dictionary = _recipe(world, "campfire")
	world.message = ""
	h.assert_true(SysCraft.craft_recipe(world, campfire), "the build did not go to the pointer")
	if not h.assert_true(world.placing != null, "nothing came to the pointer"):
		return
	var placing := world.placing as Dictionary
	h.assert_false(bool(placing["ok"]), "the spot in front is taken, so the silhouette is red")
	h.assert_eq(str(placing["why"]), SysCraft.WHY_ROOM, "for want of room")
	world.input["place_click"] = true
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	h.assert_eq(world.message, "No room there.", "a click there says why")
	h.assert_eq(world.built, 0, "and nothing was built")
	h.assert_eq(Inventory.count(world, "grass_tuft"), 3, "the grass was not spent")
	h.assert_eq(Inventory.count(world, "log"), 2, "nor the logs")
	# Let go: the right button keeps the makings.
	world.input["place_cancel"] = true
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	h.assert_true(world.placing == null, "the build is let go")
	h.assert_eq(world.message, "The campfire is not built; the makings are kept.", "and it is said")
	h.assert_eq(Inventory.count(world, "grass_tuft"), 3, "the grass is still there")
	h.assert_eq(Inventory.count(world, "log"), 2, "and the logs")
	# Asking for the table again lets a build go too.
	h.assert_true(SysCraft.craft_recipe(world, campfire), "the build did not go to the pointer again")
	world.input["craft_toggle"] = true
	SysCraft.update(world, STEP)
	Sim.clear_one_shots(world)
	h.assert_true(world.placing == null, "C lets the build go")
	h.assert_true(world.craft_open, "and opens the table")
	h.assert_eq(Inventory.count(world, "log"), 2, "with the logs kept")

	# The water is not ground either: the camp is land and the far corner is not.
	_stage(world)
	h.assert_true(world.is_land(0.0, 0.0), "the camp is land")
	h.assert_false(world.is_land(-250.0, -250.0), "and the far corner is not")


## A made tool goes into an empty hand, a made pack onto an empty back; a
## place already taken leaves the new thing in the pack.
func _a_made_thing_is_worn_when_its_place_is_free(h: TestHarness, world: World) -> void:
	_stage(world)
	Inventory.inv_add(world, "twig", 1)
	Inventory.inv_add(world, "flint", 1)
	h.assert_true(SysCraft.craft_recipe(world, _recipe(world, "axe")), "the axe was not made")
	var hand: Variant = world.equipment["hand"]
	h.assert_true(hand is Dictionary and str((hand as Dictionary)["item"]) == "axe",
		"the made axe went straight into the empty hand")
	h.assert_eq(Inventory.count(world, "axe"), 0, "and not into the pack")
	h.assert_eq(world.message, "Made %s, now in hand." % Inventory.item_name(world, "axe"), "and it is said")
	# A second axe, the hand taken, stays in the pack.
	Inventory.inv_add(world, "twig", 1)
	Inventory.inv_add(world, "flint", 1)
	h.assert_true(SysCraft.craft_recipe(world, _recipe(world, "axe")), "the second axe was not made")
	h.assert_eq(Inventory.count(world, "axe"), 1, "the second axe stays in the pack")
	h.assert_eq(world.message, "Made %s." % Inventory.item_name(world, "axe"), "said plainly")
	# A pack goes on the back.
	_put_station(world, "workbench")
	Inventory.inv_add(world, "rope", 4)
	Inventory.inv_add(world, "grass_tuft", 4)
	h.assert_true(SysCraft.craft_recipe(world, _recipe(world, "backpack")), "the pack was not made")
	var back: Variant = world.equipment["back"]
	h.assert_true(back is Dictionary and str((back as Dictionary)["item"]) == "backpack", "the made pack went onto the back")
	h.assert_eq(world.message, "Made %s, now on the back." % Inventory.item_name(world, "backpack"), "and it is said")
	h.assert_true(world.slots.size() > world.base_slots, "and the hotbar grew on the spot")


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


## How many of an item are worn rather than carried.
func _worn_count(world: World, item_id: String) -> int:
	var n := 0
	for kind in world.equipment:
		var worn: Variant = world.equipment[kind]
		if worn is Dictionary and str((worn as Dictionary).get("item", "")) == item_id:
			n += int((worn as Dictionary).get("count", 1))
	return n


func _built_prop(world: World, prop_id: String) -> Dictionary:
	for entity: Dictionary in world.entities:
		if str(entity.get("kind", "")) == "prop" and str(entity.get("prop_id", "")) == prop_id \
				and str(entity.get("id", "")).begins_with("c"):
			return entity
	return {}
