extends RefCounted

## The pack: stack_max, tool wear, the pack worn on the back, the cloak worn on
## the body, the tool in hand.


func run(h: TestHarness) -> void:
	var w := TestFixtures.world()
	if w == null:
		h.fail("test_inventory: could not open %s" % TestHarness.RUN_DIR)
		return
	_stacks(h, w)
	_capacity_overflow(h, w)
	_tool_wear(h, w)
	_backpack(h, w)
	_insulation(h, w)
	_remove_last_stack_first(h, w)
	h.done()


func _stacks(h: TestHarness, w: SurvivalWorld) -> void:
	# Log stacks to ten; twenty-five fills two full slots and starts a third.
	TestFixtures.bare(w)
	h.assert_eq(SurvivalInventory.inv_add(w, "log", 25), 0, "25 logs fit in an empty pack")
	h.assert_eq(SurvivalInventory.count(w, "log"), 25, "the pack holds 25 logs")
	h.assert_eq(int((w.slots[0] as Dictionary)["count"]), 10, "slot 0 is a full stack")
	h.assert_eq(int((w.slots[1] as Dictionary)["count"]), 10, "slot 1 is a full stack")
	h.assert_eq(int((w.slots[2] as Dictionary)["count"]), 5, "slot 2 holds the rest")
	h.assert_true(SurvivalInventory.has(w, "log", 25), "has() sees all 25")
	h.assert_true(not SurvivalInventory.has(w, "log", 26), "has() refuses 26")
	# Topping up walks the slots in order, so the part-full stack fills first.
	h.assert_eq(SurvivalInventory.inv_add(w, "log", 3), 0, "three more fit")
	h.assert_eq(int((w.slots[2] as Dictionary)["count"]), 8, "the part-full stack took them")


func _capacity_overflow(h: TestHarness, w: SurvivalWorld) -> void:
	# Twelve slots of ten: 120 fit, the rest is the leftover the caller drops.
	TestFixtures.bare(w)
	h.assert_eq(SurvivalInventory.slot_capacity(w), 12, "the base pack is twelve slots")
	h.assert_eq(SurvivalInventory.inv_add(w, "log", 130), 10, "ten logs do not fit")
	h.assert_eq(SurvivalInventory.count(w, "log"), 120, "the pack holds 120")


func _tool_wear(h: TestHarness, w: SurvivalWorld) -> void:
	TestFixtures.bare(w)
	SurvivalInventory.inv_add(w, "axe", 1)
	h.assert_eq(int((w.slots[0] as Dictionary)["uses"]), 25, "a fresh axe carries its 25 uses")
	# A tool slot is never topped up: the second axe takes its own slot.
	SurvivalInventory.inv_add(w, "axe", 1)
	h.assert_true(w.slots[1] != null, "the second axe takes its own slot")
	h.assert_eq(SurvivalInventory.inv_find_tool(w, "chop"), 0, "the first carried axe serves chop")
	h.assert_eq(SurvivalInventory.inv_find_tool(w, "mine"), -1, "no pick is carried")
	for i in 24:
		SurvivalInventory.wear_tool(w, 0)
	h.assert_eq(int((w.slots[0] as Dictionary)["uses"]), 1, "24 finished things leave one use")
	w.message = ""
	SurvivalInventory.wear_tool(w, 0)
	h.assert_true(w.slots[0] == null, "the 25th use breaks the axe")
	h.assert_eq(w.message, "The Flint axe breaks.", "and it says so by the item's display name")
	h.assert_eq(SurvivalInventory.inv_find_tool(w, "chop"), 1, "the spare axe is found next")
	# A tool in hand serves before any in the pack, and wears there.
	SurvivalInventory.inv_add(w, "axe", 1)
	h.assert_true(SurvivalInventory.equip(w, 0), "the axe goes into the hand")
	h.assert_eq(SurvivalInventory.inv_find_tool(w, "chop"), SurvivalInventory.HAND_SLOT, "the hand's axe serves first")
	SurvivalInventory.wear_tool(w, SurvivalInventory.HAND_SLOT)
	h.assert_eq(int((w.equipment["hand"] as Dictionary)["uses"]), 24, "the hand's axe wore")
	h.assert_true(SurvivalInventory.unequip(w, "hand"), "and comes off again")
	h.assert_eq(w.equipment["hand"], null, "leaving the hand empty")


func _backpack(h: TestHarness, w: SurvivalWorld) -> void:
	TestFixtures.bare(w)
	h.assert_eq(SurvivalInventory.slot_capacity(w), 12, "twelve without a pack")
	SurvivalInventory.inv_add(w, "backpack", 1)
	h.assert_eq(SurvivalInventory.slot_capacity(w), 12, "a reed pack in a slot carries nothing")
	h.assert_eq(SurvivalInventory.equip_kind(w, "backpack"), "back", "a pack is worn on the back")
	h.assert_true(SurvivalInventory.equip(w, 0), "the pack goes on")
	h.assert_eq(w.slots[0], null, "and leaves its slot")
	h.assert_eq(SurvivalInventory.slot_capacity(w), 16, "a worn reed pack adds four slots")
	# The bonus slots are real: 16 * 10 = 160 fits where 120 did.
	h.assert_eq(SurvivalInventory.inv_add(w, "log", 160), 0, "160 logs fit in sixteen free slots")
	h.assert_eq(SurvivalInventory.inv_add(w, "log", 1), 1, "the 161st does not")
	# The pack comes off only once its own slots are empty.
	h.assert_false(SurvivalInventory.unequip(w, "back"), "a full pack does not come off")
	h.assert_eq(w.message, "Empty the pack's own slots first.", "and says why")
	SurvivalInventory.inv_remove(w, "log", 50)
	h.assert_true(SurvivalInventory.unequip(w, "back"), "emptied, it comes off")
	h.assert_eq(SurvivalInventory.slot_capacity(w), 12, "and the slots are twelve again")
	h.assert_eq(w.slots.size(), 12, "the bonus slots are gone")
	h.assert_eq(SurvivalInventory.count(w, "backpack"), 1, "the pack is back in the pack")


func _insulation(h: TestHarness, w: SurvivalWorld) -> void:
	TestFixtures.bare(w)
	h.assert_near(SurvivalInventory.insulation(w), 0.0, 1e-9, "nothing worn insulates nothing")
	SurvivalInventory.inv_add(w, "grass_cloak", 1)
	h.assert_near(SurvivalInventory.insulation(w), 0.0, 1e-9, "a cloak in the pack warms nothing")
	h.assert_true(SurvivalInventory.equip(w, 0), "the cloak goes on")
	h.assert_near(SurvivalInventory.insulation(w), 0.5, 1e-9, "a worn grass cloak halves the cold")
	# A second cloak swaps with the first rather than stacking on it.
	SurvivalInventory.inv_add(w, "grass_cloak", 1)
	var second := SurvivalInventory.count(w, "grass_cloak")
	h.assert_eq(second, 1, "one cloak in the pack, one on")
	h.assert_true(SurvivalInventory.equip(w, 0), "the second goes on")
	h.assert_eq(SurvivalInventory.count(w, "grass_cloak"), 1, "and the first came off into the pack")
	h.assert_near(SurvivalInventory.insulation(w), 0.5, 1e-9, "one cloak's worth, not two")
	# A material has nowhere to be worn.
	SurvivalInventory.inv_add(w, "log", 1)
	h.assert_eq(SurvivalInventory.equip_kind(w, "log"), "", "a log is not worn")
	h.assert_false(SurvivalInventory.equip(w, 1), "and is refused")


func _remove_last_stack_first(h: TestHarness, w: SurvivalWorld) -> void:
	TestFixtures.bare(w)
	SurvivalInventory.inv_add(w, "log", 15)
	h.assert_eq(SurvivalInventory.inv_remove(w, "log", 3), 3, "three logs came out")
	h.assert_eq(int((w.slots[0] as Dictionary)["count"]), 10, "the first stack is untouched")
	h.assert_eq(int((w.slots[1] as Dictionary)["count"]), 2, "the last stack paid")
	h.assert_eq(SurvivalInventory.inv_remove(w, "log", 99), 12, "only twelve were there to take")
	h.assert_true(w.slots[0] == null and w.slots[1] == null, "emptied slots go back to null")
