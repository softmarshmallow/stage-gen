extends RefCounted

## The pointer's three inputs, as the sim reads them: a clicked thing is the
## target at any distance (reach starts the action, beyond it a walk), a
## clicked spot is walked to until a key or arrival ends it, a clicked recipe
## row is the table's choice. None of these existed in the viewer.


func run(h: TestHarness) -> void:
	var w := TestFixtures.world()
	if w == null:
		h.fail("test_pointer: could not open %s" % TestHarness.RUN_DIR)
		return
	_one_shots_are_declared(h, w)
	_click_on_a_far_pine_commits_a_walk(h, w)
	_click_within_reach_starts_the_action(h, w)
	_click_on_nothing_to_do_says_so(h, w)
	_click_on_the_ground_walks_there(h, w)
	_a_key_takes_the_walk_back(h, w)
	_a_click_on_a_thing_ends_the_walk(h, w)
	_the_dead_do_not_walk(h, w)
	_a_held_button_keeps_the_walk_on_the_pointer(h, w)
	_menu_select_chooses_a_row(h, w)


func _fresh(w: SurvivalWorld) -> void:
	TestFixtures.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.vx = 0.0
	w.player.vz = 0.0
	w.player.busy = null
	w.player.approach = null
	w.player.goto = null
	w.dead = false
	w.craft_open = false
	w.message = ""
	w.focus = null
	w.target = null


func _step(w: SurvivalWorld, seconds: float) -> void:
	var steps := int(round(seconds / TestFixtures.STEP))
	for i in steps:
		SurvivalSim.step(w, TestFixtures.STEP)


func _one_shots_are_declared(h: TestHarness, w: SurvivalWorld) -> void:
	for key in ["menu_select", "click_entity", "click_point"]:
		h.assert_true(SurvivalSim.ONE_SHOT_INPUT.has(key), "%s is a one-shot input" % key)
		h.assert_true(SurvivalWorld.fresh_input().has(key), "%s is in a fresh input bag" % key)
	_fresh(w)
	w.input["click_point"] = {"x": 1.0, "z": 1.0}
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_eq(w.input["click_point"], null, "a click lives for one step")


func _click_on_a_far_pine_commits_a_walk(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	# Chopping needs the axe; without it the click says so and starts nothing.
	SurvivalInventory.inv_add(w, "axe", 1)
	var pine := TestFixtures.prop(w, "p1", "pine", "grown", 6.0, 0.0)
	w.entities.append(pine)
	w.input["click_entity"] = pine
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.approach != null, "a clicked pine out of reach commits a walk")
	if w.player.approach != null:
		h.assert_true(is_same((w.player.approach as Dictionary)["entity"], pine), "toward that pine")
	h.assert_true(w.player.busy == null, "and nothing has started yet")
	_step(w, 3.0)
	h.assert_true(w.player.busy != null or int(pine.get("hits", 0)) > 0 or String(pine["state"]) != "grown",
		"the walk arrives and the chop begins (busy %s, hits %d, state %s)" % [
			str(w.player.busy != null), int(pine.get("hits", 0)), String(pine["state"])])


func _click_within_reach_starts_the_action(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	SurvivalInventory.inv_add(w, "axe", 1)
	var pine := TestFixtures.prop(w, "p2", "pine", "grown", 0.0, 0.5)
	w.entities.append(pine)
	w.input["click_entity"] = pine
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.busy != null, "a clicked pine within reach starts the swing at once")
	h.assert_true(w.player.approach == null, "with no walk")
	# Without the tool the click is refused in words, as the key is: the pine
	# is the focus (its label says what it needs) and not the target.
	_fresh(w)
	var bare_pine := TestFixtures.prop(w, "p4", "pine", "grown", 0.0, 0.5)
	w.entities.append(bare_pine)
	w.input["click_entity"] = bare_pine
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.busy == null, "no axe, no swing")
	h.assert_true(w.focus is Dictionary and is_same((w.focus as Dictionary)["entity"], bare_pine),
		"the pine is the focus")
	h.assert_true(w.target == null, "and not the target")
	h.assert_eq(w.message, "Needs a Flint axe.", "and the click says why")


func _click_on_nothing_to_do_says_so(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	var fire := TestFixtures.prop(w, "p3", "campfire", "lit", 0.0, 1.0)
	w.entities.append(fire)
	w.input["click_entity"] = fire
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_eq(w.message, "Nothing to be done with that.", "a lit fire clicked has nothing to offer")
	h.assert_true(w.player.busy == null and w.player.approach == null, "and nothing starts")


func _click_on_the_ground_walks_there(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	w.input["click_point"] = {"x": 3.0, "z": 0.0}
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto != null, "a clicked spot starts a pointer walk")
	h.assert_true(w.player.vx > 0.0, "toward +x")
	_step(w, 2.0)
	h.assert_true(w.player.goto == null, "the walk ends on arrival")
	h.assert_near(w.player.x, 3.0, 0.15, "standing on the spot")
	h.assert_near(w.player.z, 0.0, 0.05, "and not off to the side")
	# The last step lands on the spot: the player never overshoots it.
	_fresh(w)
	w.input["click_point"] = {"x": 0.5, "z": 0.0}
	_step(w, 1.0)
	h.assert_true(w.player.x <= 0.5 + 1e-6, "the walk does not overshoot (%.3f)" % w.player.x)


func _a_key_takes_the_walk_back(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	w.input["click_point"] = {"x": 5.0, "z": 0.0}
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto != null, "walking")
	w.input["z"] = 1.0
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto == null, "a movement key takes the pointer walk back")
	w.input["z"] = 0.0
	# Water in the way ends the walk rather than pinning the player to the shore.
	_fresh(w)
	w.masks = null
	w.player.goto = {"x": 0.0, "z": 0.0, "stall": 0.0}
	w.player.x = 0.0
	# Standing on the spot already: arrival on the first step.
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto == null, "a walk to where the player stands is over at once")


func _a_click_on_a_thing_ends_the_walk(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	w.input["click_point"] = {"x": 5.0, "z": 5.0}
	SurvivalSim.step(w, TestFixtures.STEP)
	var pine := TestFixtures.prop(w, "p1", "pine", "grown", 6.0, 0.0)
	w.entities.append(pine)
	# Without an axe the pine is refused: the pointer walk still ends, but no
	# approach is committed to a thing that could not be acted on.
	w.input["click_entity"] = pine
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto == null, "a refused thing clicked still ends the pointer walk")
	h.assert_true(w.player.approach == null, "but commits no approach to it")
	h.assert_true(w.target == null, "nor makes it the target")
	h.assert_eq(w.message, "Needs a Flint axe.", "and says what it needs")
	SurvivalInventory.inv_add(w, "axe", 1)
	w.input["click_point"] = {"x": 5.0, "z": 5.0}
	SurvivalSim.step(w, TestFixtures.STEP)
	w.input["click_entity"] = pine
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto == null, "a thing clicked ends the pointer walk")
	h.assert_true(w.player.approach != null, "and commits the approach instead")


func _the_dead_do_not_walk(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	w.dead = true
	w.input["click_point"] = {"x": 3.0, "z": 0.0}
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto == null, "a dead player takes no pointer walk")
	h.assert_near(w.player.x, 0.0, 1e-9, "and does not move")


func _menu_select_chooses_a_row(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	var recipes: Array = (w.manifest["crafting"] as Dictionary)["recipes"]
	h.assert_true(recipes.size() >= 3, "the run has a table to choose from")
	w.input["craft_toggle"] = true
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.craft_open, "the table opens")
	w.input["menu_select"] = 2
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_eq(w.craft_index, 2, "a clicked row is the table's choice")
	w.input["menu_select"] = 99
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_eq(w.craft_index, recipes.size() - 1, "a row past the end is the last row")
	w.input["menu_select"] = -4
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_eq(w.craft_index, 0, "a row before the start is the first")
	w.input["craft_toggle"] = true
	SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_false(w.craft_open, "and the table closes")


## The frame owner re-issues `click_point` every step while the button is
## held: the walk turns with the pointer, and the stall that ends a walk into
## the shore never accrues while the spot keeps being asked for.
func _a_held_button_keeps_the_walk_on_the_pointer(h: TestHarness, w: SurvivalWorld) -> void:
	_fresh(w)
	for i in 30:
		w.input["click_point"] = {"x": 5.0, "z": 0.0}
		SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto != null, "half a second of holding keeps the walk")
	h.assert_true(w.player.x > 1.0, "and the player has moved toward +x (%.2f)" % w.player.x)
	for i in 30:
		w.input["click_point"] = {"x": w.player.x, "z": 6.0}
		SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.vz > 0.0, "the walk turned with the pointer")
	h.assert_near(w.player.vx, 0.0, 1e-6, "straight along the new heading")
	# Against a wall the held walk pushes on rather than giving up: the
	# stall is reset by every re-issued point.
	_fresh(w)
	w.player.x = 0.0
	for i in 60:
		w.input["click_point"] = {"x": 0.0, "z": 0.0}
		w.player.x = 0.0
		w.player.z = 0.0
		SurvivalSim.step(w, TestFixtures.STEP)
	h.assert_true(w.player.goto == null, "a spot under the player is arrived at, held or not")
