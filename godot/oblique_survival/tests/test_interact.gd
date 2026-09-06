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
	_barren_in_winter(h, w)
	_progress_looks(h, w)
	_take_a_forage_piece(h, w)


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
		"but the tool is required, so the target is disabled")
	w.message = ""
	for i in 30:
		w.input["interact"] = true
		Sim.step(w, SimFixture.STEP)
	h.assert_eq(w.message, "Needs a Flint axe.", "the refusal is said, sentence-cased")
	h.assert_eq(str(pine["state"]), "grown", "and the pine is untouched")
	h.assert_eq(SimFixture.events_of(w, "hit").size(), 0, "no blow landed")
	h.assert_true(w.player.busy == null, "and no swing was started")


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
	w.message = ""
	Targeting.start_interaction(w, target as Dictionary)
	h.assert_eq(w.message, "Bare in winter.", "and the prompt says so, sentence-cased")
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
