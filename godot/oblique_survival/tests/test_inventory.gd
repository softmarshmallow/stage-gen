extends RefCounted

## The pack: stack_max, tool wear, backpack capacity, insulation.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_inventory: could not open %s" % TestHarness.RUN_DIR)
		return
	_stacks(h, w)
	_capacity_overflow(h, w)
	_tool_wear(h, w)
	_backpack(h, w)
	_insulation(h, w)
	_remove_last_stack_first(h, w)


func _stacks(h: TestHarness, w: World) -> void:
	# Log stacks to ten; twenty-five fills two full slots and starts a third.
	SimFixture.bare(w)
	h.assert_eq(Inventory.inv_add(w, "log", 25), 0, "25 logs fit in an empty pack")
	h.assert_eq(Inventory.count(w, "log"), 25, "the pack holds 25 logs")
	h.assert_eq(int((w.slots[0] as Dictionary)["count"]), 10, "slot 0 is a full stack")
	h.assert_eq(int((w.slots[1] as Dictionary)["count"]), 10, "slot 1 is a full stack")
	h.assert_eq(int((w.slots[2] as Dictionary)["count"]), 5, "slot 2 holds the rest")
	h.assert_true(Inventory.has(w, "log", 25), "has() sees all 25")
	h.assert_true(not Inventory.has(w, "log", 26), "has() refuses 26")
	# Topping up walks the slots in order, so the part-full stack fills first.
	h.assert_eq(Inventory.inv_add(w, "log", 3), 0, "three more fit")
	h.assert_eq(int((w.slots[2] as Dictionary)["count"]), 8, "the part-full stack took them")


func _capacity_overflow(h: TestHarness, w: World) -> void:
	# Twelve slots of ten: 120 fit, the rest is the leftover the caller drops.
	SimFixture.bare(w)
	h.assert_eq(Inventory.slot_capacity(w), 12, "the base pack is twelve slots")
	h.assert_eq(Inventory.inv_add(w, "log", 130), 10, "ten logs do not fit")
	h.assert_eq(Inventory.count(w, "log"), 120, "the pack holds 120")


func _tool_wear(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	Inventory.inv_add(w, "axe", 1)
	h.assert_eq(int((w.slots[0] as Dictionary)["uses"]), 25, "a fresh axe carries its 25 uses")
	# A tool slot is never topped up: the second axe takes its own slot.
	Inventory.inv_add(w, "axe", 1)
	h.assert_true(w.slots[1] != null, "the second axe takes its own slot")
	h.assert_eq(Inventory.inv_find_tool(w, "chop"), 0, "the first carried axe serves chop")
	h.assert_eq(Inventory.inv_find_tool(w, "mine"), -1, "no pick is carried")
	for i in 24:
		Inventory.wear_tool(w, 0)
	h.assert_eq(int((w.slots[0] as Dictionary)["uses"]), 1, "24 finished things leave one use")
	w.message = ""
	Inventory.wear_tool(w, 0)
	h.assert_true(w.slots[0] == null, "the 25th use breaks the axe")
	h.assert_eq(w.message, "The Flint axe breaks.", "and it says so by the item's display name")
	h.assert_eq(Inventory.inv_find_tool(w, "chop"), 1, "the spare axe is found next")


func _backpack(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	h.assert_eq(Inventory.slot_capacity(w), 12, "twelve without a pack")
	Inventory.inv_add(w, "backpack", 1)
	h.assert_eq(Inventory.slot_capacity(w), 16, "a carried reed pack adds four slots")
	# The bonus slots are real: 15 * 10 = 150 now fits where 120 did.
	SimFixture.bare(w)
	Inventory.inv_add(w, "backpack", 1)
	h.assert_eq(Inventory.inv_add(w, "log", 150), 0, "150 logs fit in fifteen free slots")
	h.assert_eq(Inventory.inv_add(w, "log", 1), 1, "the 151st does not")


func _insulation(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	h.assert_near(Inventory.insulation(w), 0.0, 1e-9, "nothing worn insulates nothing")
	Inventory.inv_add(w, "grass_cloak", 1)
	h.assert_near(Inventory.insulation(w), 0.5, 1e-9, "a grass cloak halves the cold")
	Inventory.inv_add(w, "grass_cloak", 1)
	h.assert_near(Inventory.insulation(w), 0.9, 1e-9, "two cloaks are capped at 0.9")


func _remove_last_stack_first(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	Inventory.inv_add(w, "log", 15)
	h.assert_eq(Inventory.inv_remove(w, "log", 3), 3, "three logs came out")
	h.assert_eq(int((w.slots[0] as Dictionary)["count"]), 10, "the first stack is untouched")
	h.assert_eq(int((w.slots[1] as Dictionary)["count"]), 2, "the last stack paid")
	h.assert_eq(Inventory.inv_remove(w, "log", 99), 12, "only twelve were there to take")
	h.assert_true(w.slots[0] == null and w.slots[1] == null, "emptied slots go back to null")
