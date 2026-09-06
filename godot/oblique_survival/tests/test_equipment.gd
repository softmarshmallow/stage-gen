extends RefCounted

## What is worn, through the inputs the HUD and the keys write: X on a cloak
## puts it on, `equip` and `unequip` move things between the pack and the
## three worn places, the worn tool serves and wears first, and a new world
## opens under a clear sky rather than the viewer's first wet spell.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_equipment: could not open %s" % TestHarness.RUN_DIR)
		return
	_inputs_are_declared(h, w)
	_use_wears_a_cloak(h, w)
	_equip_and_unequip_inputs(h, w)
	_the_worn_tool_serves_first(h, w)
	_a_fresh_world_is_dry(h)


func _fresh(w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.player.approach = null
	w.player.goto = null
	w.dead = false
	w.craft_open = false
	w.message = ""
	w.target = null


func _inputs_are_declared(h: TestHarness, w: World) -> void:
	for key in ["equip", "unequip"]:
		h.assert_true(Sim.ONE_SHOT_INPUT.has(key), "%s is a one-shot input" % key)
		h.assert_true(World.fresh_input().has(key), "%s is in a fresh input bag" % key)
	h.assert_eq(w.equipment.keys(), ["hand", "body", "back"], "the three worn places")
	h.assert_eq(Inventory.EQUIPMENT_KINDS, ["hand", "body", "back"], "in the HUD's order")


func _use_wears_a_cloak(h: TestHarness, w: World) -> void:
	_fresh(w)
	Inventory.inv_add(w, "grass_cloak", 1)
	w.selected = 0
	w.input["use"] = true
	Sim.step(w, SimFixture.STEP)
	h.assert_true(w.equipment["body"] != null, "X on a cloak puts it on")
	h.assert_eq(w.slots[0], null, "and it left its slot")
	h.assert_eq(w.message, "body: Grass cloak.", "the message names the place")
	h.assert_near(Inventory.insulation(w), 0.5, 1e-9, "and the cold is halved")
	# The pack: worn on the back, and the slots grow.
	Inventory.inv_add(w, "backpack", 1)
	w.input["use"] = true
	Sim.step(w, SimFixture.STEP)
	h.assert_true(w.equipment["back"] != null, "X on a pack puts it on")
	h.assert_eq(Inventory.slot_capacity(w), 16, "and the pack is sixteen slots")
	h.assert_eq(w.slots.size(), 16, "grown on the spot")


func _equip_and_unequip_inputs(h: TestHarness, w: World) -> void:
	_fresh(w)
	Inventory.inv_add(w, "axe", 1)
	w.selected = 0
	w.input["equip"] = true
	Sim.step(w, SimFixture.STEP)
	h.assert_true(w.equipment["hand"] != null, "the equip input wears the chosen slot")
	h.assert_eq(int((w.equipment["hand"] as Dictionary)["uses"]), 25, "with its wear")
	w.input["unequip"] = "hand"
	Sim.step(w, SimFixture.STEP)
	h.assert_eq(w.equipment["hand"], null, "the unequip input takes it off")
	h.assert_eq(Inventory.count(w, "axe"), 1, "back into the pack")
	h.assert_eq(w.message, "Flint axe off.", "and says so")
	w.input["unequip"] = "nowhere"
	Sim.step(w, SimFixture.STEP)
	h.assert_eq(Inventory.count(w, "axe"), 1, "an unknown place is ignored")
	# A worn thing with no room to come off stays on.
	_fresh(w)
	Inventory.inv_add(w, "grass_cloak", 1)
	Inventory.equip(w, 0)
	Inventory.inv_add(w, "log", 120)
	w.input["unequip"] = "body"
	Sim.step(w, SimFixture.STEP)
	h.assert_true(w.equipment["body"] != null, "a full pack keeps the cloak on")
	h.assert_eq(w.message, "Hands full.", "and says so")


func _the_worn_tool_serves_first(h: TestHarness, w: World) -> void:
	_fresh(w)
	Inventory.inv_add(w, "axe", 1)
	Inventory.inv_add(w, "axe", 1)
	Inventory.equip(w, 1)
	var pine := SimFixture.prop(w, "p1", "pine", "grown", 0.0, 0.5)
	w.entities.append(pine)
	var target: Variant = Targeting.target_for(w, pine)
	h.assert_true(target != null, "a pine with an axe in hand is a target")
	h.assert_eq(int((target as Dictionary)["tool_slot"]), Inventory.HAND_SLOT, "served by the hand")
	var pine_tool: Dictionary = (((w.manifest["props"] as Dictionary)["pine"] as Dictionary)["interaction"] as Dictionary)["tool"]
	h.assert_eq(int((target as Dictionary)["hits"]), int(pine_tool["hits"]), "with the axe's authored hits")
	# Chop it down: the hand's axe wears, the pack's does not.
	w.input["click_entity"] = pine
	for i in 240:
		Sim.step(w, SimFixture.STEP)
		w.input["interact"] = true
	h.assert_eq(str(pine["state"]), "stump", "the pine came down (%s)" % str(pine["state"]))
	h.assert_eq(int((w.equipment["hand"] as Dictionary)["uses"]), 24, "the hand's axe wore once")
	h.assert_eq(int((w.slots[0] as Dictionary)["uses"]), 25, "the pack's axe did not")


func _a_fresh_world_is_dry(h: TestHarness) -> void:
	var world := World.create(SimFixture.package(), 7, {"masks": Masks.new()})
	world.entities = []
	var rain_spec: Dictionary = (world.manifest["weather"] as Dictionary)["rain"]
	var dry_low := float((rain_spec["dry_spell_seconds"] as Array)[0])
	h.assert_false(bool(world.weather["wet_spell"]), "a new world is in a dry spell")
	h.assert_near(float(world.weather["spell_ends_at"]), dry_low, 1e-9, "for the authored minimum, undrawn")
	Sim.advance(world, 30.0)
	h.assert_near(float(world.weather["rain"]), 0.0, 1e-9, "no rain in the first half minute")
	h.assert_false(bool(world.weather["wet_spell"]), "and no wet spell yet")
	Sim.advance(world, dry_low)
	h.assert_true(bool(world.weather["wet_spell"]), "the first wet spell follows the dry one")
