extends RefCounted

## Fire as a thing the player carries: the `burn` verb.
##
## `light` and `burn` are the two ways a thing takes fire and they are not the
## same thing — a campfire IS the fire and goes to its lit look at the strike, a
## tree is fuel and keeps its own look until the flame dies. Both are on the
## fire key, and the key asks its own question of the thing in focus, because
## the offer the nearest rule makes on a pine with an axe in the pack is the
## chop.


func run(h: TestHarness) -> void:
	var w := TestFixtures.world()
	if w == null:
		h.fail("test_burn: could not open %s" % TestHarness.RUN_DIR)
		return
	_the_torch_is_what_it_wants(h, w)
	_it_stands_burning_in_its_own_look(h, w)
	_a_burning_thing_is_nobodys_target(h, w)
	_burning_is_a_light_and_a_warmth(h, w)
	_what_the_fire_leaves(h, w)
	_how_long_it_burns(h, w)
	_the_fire_key_asks_its_own_question(h, w)
	_the_fireplace_is_unchanged(h, w)


func _stand_at_the_pine(w: SurvivalWorld) -> Dictionary:
	TestFixtures.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.player.approach = null
	w.dead = false
	w.torch = {"remaining": 0.0, "radius": 0.0}
	var pine := TestFixtures.prop(w, "p1", "pine", "grown", 0.0, 0.9)
	w.entities.append(pine)
	return pine


func _the_torch_is_what_it_wants(h: TestHarness, w: SurvivalWorld) -> void:
	var pine := _stand_at_the_pine(w)
	var empty: Variant = SurvivalTargeting.fire_target(w, pine)
	h.assert_true(empty is Dictionary, "a pine answers the fire key at all")
	h.assert_eq(str((empty as Dictionary)["disabled"]), "needs a Torch",
		"and with nothing to light it with, it says what it needs")
	SurvivalInventory.inv_add(w, "torch", 1)
	var ready: Variant = SurvivalTargeting.fire_target(w, pine)
	h.assert_true((ready as Dictionary)["disabled"] == null, "a torch in the pack is the answer")
	h.assert_eq(str(((ready as Dictionary)["interaction"] as Dictionary)["verb"]), "burn",
		"the offer is the burn, not the chop the nearest rule would make")


func _it_stands_burning_in_its_own_look(h: TestHarness, w: SurvivalWorld) -> void:
	var pine := _stand_at_the_pine(w)
	SurvivalInventory.inv_add(w, "torch", 1)
	SurvivalTargeting.start_interaction(w, SurvivalTargeting.fire_target(w, pine) as Dictionary)
	h.assert_true(float(pine["burn"]) > 0.0, "the pine is alight")
	h.assert_eq(str(pine["state"]), "grown",
		"and it is still a pine: fire takes time, and the look it ends in is the fire's to give")
	h.assert_eq(str(w.message), "The tree catches.", "said by the word the label uses")
	h.assert_eq(SurvivalInventory.count(w, "torch"), 0, "the torch went into the striking")


func _a_burning_thing_is_nobodys_target(h: TestHarness, w: SurvivalWorld) -> void:
	var pine := _stand_at_the_pine(w)
	SurvivalInventory.inv_add(w, "torch", 1)
	SurvivalInventory.inv_add(w, "axe", 1)
	SurvivalTargeting.start_interaction(w, SurvivalTargeting.fire_target(w, pine) as Dictionary)
	h.assert_true(SurvivalTargeting.target_for(w, pine) == null,
		"an axe has nothing to say to a tree that is on fire")
	h.assert_true(SurvivalTargeting.fire_target(w, pine) == null, "nor has a second torch")


func _burning_is_a_light_and_a_warmth(h: TestHarness, w: SurvivalWorld) -> void:
	var pine := _stand_at_the_pine(w)
	SurvivalInventory.inv_add(w, "torch", 1)
	SurvivalTargeting.start_interaction(w, SurvivalTargeting.fire_target(w, pine) as Dictionary)
	SurvivalFirelightSystem.update(w, 1.0 / 60.0)
	h.assert_eq(w.light["on"], true, "the burning tree is the light in the frame")
	h.assert_near(float(w.light["x"]), 0.0, 1e-6, "standing where the tree stands")
	h.assert_near(float(w.light["z"]), 0.9, 1e-6, "standing where the tree stands")
	# The dark is a cold, and a fire within its light radius holds it off.
	w.night = 1.0
	w.player.warmth = 50.0
	SurvivalVitalsSystem.update(w, 1.0)
	h.assert_true(w.player.warmth > 50.0, "and it gives warmth back like any other fire")
	w.night = 0.0


func _what_the_fire_leaves(h: TestHarness, w: SurvivalWorld) -> void:
	var pine := _stand_at_the_pine(w)
	SurvivalInventory.inv_add(w, "torch", 1)
	SurvivalTargeting.start_interaction(w, SurvivalTargeting.fire_target(w, pine) as Dictionary)
	for i in 3000:
		SurvivalTimersSystem.update(w, 1.0 / 60.0)
		if float(pine["burn"]) <= 0.0:
			break
	h.assert_eq(str(pine["state"]), "stump", "what the fire leaves is the stump the axe leaves")
	h.assert_near(float(pine["burn"]), 0.0, 1e-9, "and the flame is out")

	# A bush is authored to come back, three times slower than a picked one.
	TestFixtures.bare(w)
	var bush := TestFixtures.prop(w, "b1", "thorn_bush", "full", 0.0, 0.6)
	w.entities.append(bush)
	SurvivalInventory.inv_add(w, "torch", 1)
	SurvivalTargeting.start_interaction(w, SurvivalTargeting.fire_target(w, bush) as Dictionary)
	for i in 3000:
		SurvivalTimersSystem.update(w, 1.0 / 60.0)
		if float(bush["burn"]) <= 0.0:
			break
	h.assert_eq(str(bush["state"]), "picked", "the bush burns back to the picked look")
	h.assert_near(float(bush["regrow"]), 150.0, 0.02, "and takes the burn's own regrow, not the hand's 45")


func _how_long_it_burns(h: TestHarness, w: SurvivalWorld) -> void:
	# Nobody authors the length: a thing burns for its own height, four seconds
	# to the metre, with a floor so the smallest still reads as having caught.
	var pine := _stand_at_the_pine(w)
	h.assert_near(SurvivalTargeting.burn_seconds_for(w, pine), 5.44 * 4.0, 0.05,
		"a grown pine is 5.44 m and burns for twenty-one seconds")
	TestFixtures.bare(w)
	var tuft := TestFixtures.prop(w, "g1", "grass_tuft", "standing", 0.0, 0.6)
	h.assert_near(SurvivalTargeting.burn_seconds_for(w, tuft), 3.0, 1e-6,
		"a tuft of grass is half a metre and takes the floor")


func _the_fire_key_asks_its_own_question(h: TestHarness, w: SurvivalWorld) -> void:
	var pine := _stand_at_the_pine(w)
	SurvivalInventory.inv_add(w, "axe", 1)
	SurvivalInventory.inv_add(w, "torch", 1)
	SurvivalInteractSystem.update(w, 1.0 / 60.0)
	h.assert_eq(str(((w.focus as Dictionary)["interaction"] as Dictionary)["verb"]), "chop",
		"the label still says what the nearest rule offers, which is the axe's word")
	w.input["light"] = true
	SurvivalInteractSystem.update(w, 1.0 / 60.0)
	w.input["light"] = false
	h.assert_true(float(pine["burn"]) > 0.0, "and the fire key burns it anyway")
	h.assert_eq(int(pine["hits"]), 0, "without the axe having touched it")


func _the_fireplace_is_unchanged(h: TestHarness, w: SurvivalWorld) -> void:
	TestFixtures.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	var fire := TestFixtures.prop(w, "c1", "campfire", "unlit", 0.0, 0.6)
	w.entities.append(fire)
	var offer: Variant = SurvivalTargeting.fire_target(w, fire)
	h.assert_eq(str(((offer as Dictionary)["interaction"] as Dictionary)["verb"]), "light",
		"a fireplace is lit, not burned")
	h.assert_true((offer as Dictionary)["disabled"] == null, "and it needs nothing to light it")
	SurvivalTargeting.start_interaction(w, offer as Dictionary)
	h.assert_eq(str(fire["state"]), "lit", "its lit look IS the fire, so it goes there at the strike")
	h.assert_true(float(fire["burn"]) > 0.0, "and it burns")
	for i in 8000:
		SurvivalTimersSystem.update(w, 1.0 / 60.0)
		if float(fire["burn"]) <= 0.0:
			break
	h.assert_eq(str(fire["state"]), "unlit", "and goes back to unlit when it has burnt down")
