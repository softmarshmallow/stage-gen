extends RefCounted

## Interacting: felling a tree, the tool refusal, the barren season, and the
## multi-hit progress looks.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_interact: could not open %s" % TestHarness.RUN_DIR)
		return
	_fell_a_pine(h, w)
	_refused_without_an_axe(h, w)
	_the_snag_offers_what_the_pack_allows(h, w)
	_barren_in_winter(h, w)
	_progress_looks(h, w)
	_take_a_forage_piece(h, w)
	_gathered_by_hand(h, w)
	_a_full_pack_lets_the_rest_fall(h, w)
	_the_key_waits_for_the_yield(h, w)


func _stand_at_the_pine(w: World) -> Dictionary:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.player.approach = null
	w.dead = false
	var pine := SimFixture.prop(w, "p1", "pine", "grown", 0.0, 0.9)
	w.entities.append(pine)
	return pine


func _fell_a_pine(h: TestHarness, w: World) -> void:
	var pine := _stand_at_the_pine(w)
	Inventory.inv_add(w, "axe", 1)
	var before: Variant = Targeting.target_for(w, pine)
	h.assert_eq(int((before as Dictionary)["hits"]), 2,
		"a carried axe takes the pine in two blows, not the bare hand's three")
	h.assert_true((before as Dictionary)["disabled"] == null, "with the axe nothing is refused")
	var swung := 0
	w.input["interact"] = true
	for i in 400:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		swung += 1
		if str(pine["state"]) == "stump":
			break
	h.assert_eq(str(pine["state"]), "stump", "the pine is felled")
	h.assert_eq(SimFixture.events_of(w, "hit").size(), 2, "two blows were struck")
	var fell := SimFixture.events_of(w, "fell")
	h.assert_eq(fell.size(), 1, "and one trunk fell")
	h.assert_near(float((fell[0] as Dictionary)["height"]), 5.44, 1e-4,
		"the fall carries the prop's authored height")
	h.assert_eq(int((w.slots[0] as Dictionary)["uses"]), 24,
		"the axe wore once for the thing it finished, not once per blow")
	h.assert_eq(w.drops.size(), 1, "the yield is queued behind the falling trunk")
	var queued: Dictionary = w.drops[0]
	# At yaw 0 the trunk topples along world +x; the crown lands at
	# height * 0.45 from the stump.
	h.assert_near(float(queued["x"]), 5.44 * 0.45, 1e-4, "the yield waits where the crown lands")
	h.assert_near(float(queued["z"]), 0.9, 1e-4, "and on the trunk's line")
	# Let go, and let the crown land.
	w.input["interact"] = false
	for i in 120:
		Sim.step(w, SimFixture.STEP)
	var logs: Array = []
	for entity in w.entities:
		if str((entity as Dictionary).get("kind", "")) == "item" \
				and str((entity as Dictionary).get("item_id", "")) == "log":
			logs.append(entity)
	h.assert_eq(logs.size(), 2, "two logs are on the ground")
	h.assert_eq(w.drops.size(), 0, "and nothing is still queued")
	h.assert_true(float((logs[0] as Dictionary)["x"]) > 1.0,
		"they landed out at the crown, not at the stump")
	h.assert_true(Targeting.target_for(w, pine) == null, "a stump offers no second chop")


func _refused_without_an_axe(h: TestHarness, w: World) -> void:
	var pine := _stand_at_the_pine(w)
	var target: Variant = Targeting.target_for(w, pine)
	h.assert_eq(int((target as Dictionary)["hits"]), 3, "the bare hand would take three blows")
	h.assert_eq(str((target as Dictionary)["disabled"]), "needs a Flint axe",
		"but the tool is required, so the offer is refused")
	# Within reach, the key held: the pine is the focus (lit, named with what
	# it needs) and not the target, so the key does nothing and says nothing —
	# the label already says what is needed.
	w.message = ""
	for i in 30:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
	h.assert_true(w.focus != null and is_same((w.focus as Dictionary)["entity"], pine),
		"the pine is the focus, by the one nearest rule")
	h.assert_true(w.target == null, "and not the target")
	h.assert_eq(w.message, "", "the key is ignored in silence")
	h.assert_eq(str(pine["state"]), "grown", "and the pine is untouched")
	h.assert_eq(SimFixture.events_of(w, "hit").size(), 0, "no blow landed")
	h.assert_true(w.player.busy == null, "and no swing was started")
	# Three metres off, the held key does not walk to a thing it could not act
	# on: the pine stays the lit, named focus and the player stands where they
	# were.
	pine["z"] = 3.5
	w.player.approach = null
	w.message = ""
	for i in 60:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
	h.assert_true(w.player.approach == null, "no walk is committed to a refused thing")
	h.assert_near(w.player.x, 0.0, 1e-6, "the player has not moved (x)")
	h.assert_near(w.player.z, 0.0, 1e-6, "the player has not moved (z)")
	h.assert_true(w.focus != null and is_same((w.focus as Dictionary)["entity"], pine),
		"but the pine is still the focus, lit and named with what it needs")
	h.assert_true(w.target == null, "with no target in it")
	h.assert_eq(w.message, "", "and nothing is said")
	# Nor does a click on it: passed over, the focus stays with the nearest rule.
	w.input["interact"] = false
	w.message = ""
	w.input["click_entity"] = pine
	Sim.step(w, SimFixture.STEP)
	h.assert_true(w.player.approach == null, "a click on a refused thing commits no walk either")
	h.assert_true(w.target == null, "nor makes it the target")
	h.assert_eq(w.message, "", "and is ignored in silence")
	w.input["click_entity"] = null
	# With the axe in the pack the same key walks there and fells it.
	Inventory.inv_add(w, "axe", 1)
	for i in 240:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		if str(pine["state"]) == "stump":
			break
	h.assert_eq(str(pine["state"]), "stump", "with the axe the key walks up and fells it")
	w.input["interact"] = false


## Two interactions on one prop, resolved by state and by what is carried:
## the dead snag is chopped with an axe (listed first) and snapped for twigs
## by hand without one; a broken snag waits for the axe.
func _the_snag_offers_what_the_pack_allows(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.player.approach = null
	w.dead = false
	var snag := SimFixture.prop(w, "s2", "dead_snag", "standing", 0.0, 0.8)
	w.entities.append(snag)
	var bare: Variant = Targeting.target_for(w, snag)
	h.assert_eq(str(((bare as Dictionary)["interaction"] as Dictionary)["verb"]), "gather",
		"without an axe the snag offers the hand's snap")
	h.assert_true((bare as Dictionary)["disabled"] == null, "which nothing refuses")
	Inventory.inv_add(w, "axe", 1)
	var armed: Variant = Targeting.target_for(w, snag)
	h.assert_eq(str(((armed as Dictionary)["interaction"] as Dictionary)["verb"]), "chop",
		"with an axe the snag offers the chop, listed first")
	h.assert_eq(int((armed as Dictionary)["hits"]), 2, "at the axe's two blows")
	# Drop the axe and snap the top off by hand.
	w.slots[0] = null
	for i in 120:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		if str(snag["state"]) == "broken":
			break
	w.input["interact"] = false
	h.assert_eq(str(snag["state"]), "broken", "the snap leaves the broken look")
	h.assert_eq(UiKit.inv_count(w.slots, "twig"), 2, "and two twigs went into the pack")
	var broken: Variant = Targeting.target_for(w, snag)
	h.assert_true(broken != null, "a broken snag is still a target")
	h.assert_eq(str(((broken as Dictionary)["interaction"] as Dictionary)["verb"]), "chop",
		"but only the chop applies from `broken`")
	h.assert_eq(str((broken as Dictionary)["disabled"]), "needs a Flint axe", "which the bare hand is refused")
	Inventory.inv_add(w, "axe", 1)
	for i in 240:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		if str(snag["state"]) == "stump":
			break
	w.input["interact"] = false
	h.assert_eq(str(snag["state"]), "stump", "the axe finishes the broken snag")
	h.assert_true(Targeting.target_for(w, snag) == null, "and a stump offers nothing")


func _barren_in_winter(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.dead = false
	SimFixture.force_season(w, "winter")
	var bush := SimFixture.prop(w, "b1", "thorn_bush", "full", 0.0, 0.7)
	w.entities.append(bush)
	var target: Variant = Targeting.target_for(w, bush)
	h.assert_true(target != null, "the bush is still a target in winter")
	h.assert_eq(str((target as Dictionary)["disabled"]), "bare in winter",
		"the season's barren list disables it")
	# The held key: the bush is the focus, labelled `bare in winter`, and not
	# the target, so nothing is said and nothing starts.
	w.message = ""
	for i in 10:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
	w.input["interact"] = false
	h.assert_true(w.focus != null and is_same((w.focus as Dictionary)["entity"], bush), "the bush is the focus")
	h.assert_true(w.target == null, "and not the target")
	h.assert_eq(w.message, "", "the key is passed over in silence")
	h.assert_eq(str(bush["state"]), "full", "nothing was spent")
	h.assert_true(w.player.busy == null, "and no swing was started")
	SimFixture.force_season(w, "summer")
	h.assert_true((Targeting.target_for(w, bush) as Dictionary)["disabled"] == null,
		"in summer the same bush is gatherable")


func _progress_looks(h: TestHarness, w: World) -> void:
	# A boulder takes three blows with the pick and wears a cracked then a
	# split look on the way.
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.dead = false
	var boulder := SimFixture.prop(w, "r1", "moss_boulder", "whole", 0.0, 0.85)
	w.entities.append(boulder)
	Inventory.inv_add(w, "pickaxe", 1)
	var seen: Array = []
	for i in 200:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		var look := str(boulder["state"])
		if seen.is_empty() or str(seen[seen.size() - 1]) != look:
			seen.append(look)
		if look == "rubble":
			break
	h.assert_eq(seen, ["whole", "cracked", "split", "rubble"],
		"the boulder wears each authored progress look in turn")
	h.assert_eq(SimFixture.events_of(w, "hit").size(), 3, "three blows with the pick")
	# `timers` runs after `interact` in the same step, so the clock has already
	# ticked once by the time the test looks at it.
	h.assert_near(float(boulder["regrow"]), 120.0, SimFixture.STEP + 1e-6,
		"and it will come back in 120 s")


## The authored contract, `interaction.yield_to`: what the hand gathers goes
## straight into the pack at the blow, seen as a pickup from the bush.
func _gathered_by_hand(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.dead = false
	SimFixture.force_season(w, "summer")
	h.assert_eq(str((((w.manifest["props"] as Dictionary)["twig_bush"]["interactions"] as Array)[0] as Dictionary)["yield_to"]), "hand",
		"the twig bush yields to the hand")
	h.assert_eq(str((((w.manifest["props"] as Dictionary)["pine"]["interactions"] as Array)[0] as Dictionary)["yield_to"]), "ground",
		"and the pine to the ground")
	var bush := SimFixture.prop(w, "t1", "twig_bush", "full", 0.0, 0.5)
	w.entities.append(bush)
	for i in 60:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		if str(bush["state"]) == "cut":
			break
	h.assert_eq(str(bush["state"]), "cut", "the bush was gathered")
	h.assert_eq(Inventory.count(w, "twig"), 2, "both twigs are in the pack already")
	var on_ground := 0
	for entity in w.entities:
		if str((entity as Dictionary).get("kind", "")) == "item":
			on_ground += 1
	h.assert_eq(on_ground, 0, "and nothing fell to be picked up after")
	var pickups := SimFixture.events_of(w, "pickup")
	h.assert_eq(pickups.size(), 2, "two pickups were heard, one per twig")
	h.assert_near(float((pickups[0] as Dictionary)["z"]), 0.5, 1e-9, "from where the bush stands, not the player")


func _a_full_pack_lets_the_rest_fall(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.dead = false
	SimFixture.force_season(w, "summer")
	# Every slot full of something else: the twigs have nowhere to go.
	for i in 400:
		if Inventory.inv_add(w, "log", 1) > 0:
			break
	h.assert_true(Inventory.inv_add(w, "log", 1) == 1, "the pack is full of logs")
	var bush := SimFixture.prop(w, "t2", "twig_bush", "full", 0.0, 0.5)
	w.entities.append(bush)
	w.message = ""
	for i in 60:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		if str(bush["state"]) == "cut":
			break
	h.assert_eq(str(bush["state"]), "cut", "the bush was still gathered")
	h.assert_eq(Inventory.count(w, "twig"), 0, "no twig fit")
	var fallen := 0
	for entity in w.entities:
		if str((entity as Dictionary).get("kind", "")) == "item" and str((entity as Dictionary)["item_id"]) == "twig":
			fallen += 1
	h.assert_eq(fallen, 2, "so both fell at the bush")
	h.assert_eq(w.message, "Hands full.", "and it was said")


## A drop on its way down is the target from the moment it flies, and the held
## key waits for it rather than turning to the next thing: the rock just mined
## is not lost to the bush behind the player.
func _the_key_waits_for_the_yield(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.player.approach = null
	w.dead = false
	SimFixture.force_season(w, "summer")
	Inventory.inv_add(w, "pickaxe", 1)
	var boulder := SimFixture.prop(w, "r2", "moss_boulder", "whole", 0.0, 0.85)
	w.entities.append(boulder)
	# A bush a step behind the player: the next nearest thing once the rock
	# is spent, and what the key used to turn to while the stones bounced.
	var bush := SimFixture.prop(w, "t3", "twig_bush", "full", 0.0, -1.0)
	w.entities.append(bush)
	var stones_flew := false
	var bush_touched := false
	for i in 600:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		if str(bush["state"]) != "full":
			bush_touched = true
		var target: Variant = w.target
		for entity in w.entities:
			if str((entity as Dictionary).get("kind", "")) == "item" and not bool((entity as Dictionary)["settled"]):
				stones_flew = true
				h.assert_true(target is Dictionary and bool((target as Dictionary).get("item", false)),
					"while a stone is in the air it is the target, not the bush")
				break
		if Inventory.count(w, "stone") == 2:
			break
	h.assert_true(stones_flew, "the stones were seen in the air")
	h.assert_eq(Inventory.count(w, "stone"), 2, "both stones were taken")
	h.assert_false(bush_touched, "and the bush behind was left alone the whole time")
	# A trunk's logs on their way down are waited for too: nothing is targeted
	# while a yield is queued beside the player.
	SimFixture.bare(w)
	w.player.busy = null
	w.player.approach = null
	w.entities.append(bush)
	w.drops.append({"at": w.time + 1.0, "yields": [{"item_id": "log", "count": 1}], "x": 1.0, "z": 0.0,
		"dir_x": 1.0, "dir_z": 0.0, "spread": 1.0})
	w.input["interact"] = true
	Sim.step(w, SimFixture.STEP)
	h.assert_true(w.target == null, "the held key waits for the crown to land")
	h.assert_true(w.player.busy == null, "and starts nothing")


func _take_a_forage_piece(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.busy = null
	w.dead = false
	SimFixture.force_season(w, "summer")
	var moss := SimFixture.forage(w, "f1", 11, 0.0, 0.4)
	w.entities.append(moss)
	for i in 60:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
		if bool(moss["picked"]):
			break
	h.assert_true(bool(moss["picked"]), "the piece was lifted")
	h.assert_eq(Inventory.count(w, "moss"), 1, "and counted into the pack")
	h.assert_near(float(moss["regrow"]), 200.0, SimFixture.STEP + 1e-6,
		"its regrow clock is the cell's")
	h.assert_eq(SimFixture.events_of(w, "pickup").size(), 1, "one pickup was heard")
