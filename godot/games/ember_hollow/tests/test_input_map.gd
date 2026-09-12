extends RefCounted

## The key map: held keys are re-read every substep, presses live for one step.
##
## Ported behaviour under test — viewer index.html:5228-5294 (the handler) and
## :5496-5515 (the sampling). `SurvivalInput` is the class in
## `runtime/input_map.gd`; the plan's name `InputMap` is a native Godot class
## and cannot be declared.

func run(h: TestHarness) -> void:
	var pkg: Variant = h.package()
	if pkg == null:
		h.fail("the run package did not open")
		return
	var world: SurvivalWorld = SurvivalWorldFactory.create(pkg, 7)
	if world == null:
		h.fail("the world did not build")
		return
	_held_keys(h, world)
	_one_shots(h, world)
	_panel_buttons(h, world)
	_actions(h)
	_owner_lifetime(h)
	h.done()


func _held_keys(h: TestHarness, world: SurvivalWorld) -> void:
	var input := SurvivalInput.new()
	input.bind(world)
	input.press("w")
	input.sample(world)
	h.assert_eq(world.input["z"], -1.0, "a held W walks forward")
	h.assert_eq(world.input["x"], 0.0, "and does not stray sideways")
	# Held means held: the next substep reads the key again, with no new event.
	SurvivalSim.clear_one_shots(world)
	input.sample(world)
	h.assert_eq(world.input["z"], -1.0, "a held W is still forward on the next substep")
	input.press("d")
	input.sample(world)
	h.assert_eq(world.input["x"], 1.0, "D walks right")
	input.release("w")
	input.sample(world)
	h.assert_eq(world.input["z"], 0.0, "releasing W stops the walk")
	input.release("d")

	input.press("space")
	input.sample(world)
	h.assert_true(bool(world.input["interact"]), "Space is held, not a press")
	SurvivalSim.clear_one_shots(world)
	input.sample(world)
	h.assert_true(bool(world.input["interact"]), "so it survives the step that cleared the presses")
	input.release("space")
	input.sample(world)
	h.assert_false(bool(world.input["interact"]), "and stops the moment it is let go")

	# The craft panel and verdict mode hold the player still (:5503-5505).
	input.press("w")
	world.craft_open = true
	input.sample(world)
	h.assert_eq(world.input["z"], 0.0, "the open craft panel zeroes movement")
	world.craft_open = false
	input.set_mode("verdict")
	input.sample(world)
	h.assert_eq(world.input["z"], 0.0, "verdict mode zeroes movement")
	input.set_mode("play")
	input.release("w")
	input.sample(world)
	input.free()


func _owner_lifetime(h: TestHarness) -> void:
	var host: Node3D = load("res://main.gd").new()
	var input := SurvivalInput.new()
	host.set("_input_sampler", input)
	h.assert_true(input.polling(), "the frame owner keeps its sampler outside the tree for polling")
	var sampler_ref: WeakRef = weakref(input)
	host.free()
	h.assert_eq(sampler_ref.get_ref(), null, "destroying the frame owner frees its detached input sampler")


func _one_shots(h: TestHarness, world: SurvivalWorld) -> void:
	var input := SurvivalInput.new()
	input.bind(world)
	# X is a press: it reaches exactly one step.
	input.press("x")
	input.sample(world)
	h.assert_true(bool(world.input["use"]), "X asks to use the selected slot")
	SurvivalSim.clear_one_shots(world)
	h.assert_false(bool(world.input["use"]), "the step consumed it")
	input.sample(world)
	h.assert_false(bool(world.input["use"]), "and it is not repeated on the next substep")

	# Space is a menu key while the craft panel is open, and that is a press.
	world.craft_open = true
	input.press("space")
	input.sample(world)
	h.assert_true(bool(world.input["menu_confirm"]), "Space confirms in the craft panel")
	h.assert_false(bool(world.input["interact"]), "and does not also swing")
	SurvivalSim.clear_one_shots(world)
	input.sample(world)
	h.assert_false(bool(world.input["menu_confirm"]), "the confirm lived for one step")
	input.release("space")

	input.press("w")
	input.sample(world)
	h.assert_eq(world.input["menu_move"], -1, "W chooses upward in the panel")
	SurvivalSim.clear_one_shots(world)
	input.release("w")
	world.craft_open = false

	# The digits pick a slot, but only while the debug panel is down (:5252-5256).
	input.press("3")
	input.sample(world)
	h.assert_eq(world.input["select"], 2, "3 selects the third slot")
	SurvivalSim.clear_one_shots(world)
	input.release("3")
	input.press("0")
	input.sample(world)
	h.assert_eq(world.input["select"], 9, "0 selects the tenth")
	SurvivalSim.clear_one_shots(world)
	input.release("0")
	input.debug_on = true
	input.press("3")
	input.sample(world)
	h.assert_eq(world.input["select"], null, "with the debug panel up the digits are ground modes")
	input.debug_on = false
	input.release("3")
	# An auto-repeat is not a second press.
	input.press("z")
	input.sample(world)
	h.assert_true(bool(world.input["drop"]), "Z drops")
	SurvivalSim.clear_one_shots(world)
	input.press("z", true)
	input.sample(world)
	h.assert_false(bool(world.input["drop"]), "a key repeat does not drop again")
	input.free()


## A panel button is a one-shot, and nothing else. `main.gd` keeps this node
## out of the scene tree and polls the keyboard for the held keys, so a latch
## that claimed somebody was feeding the key set left WASD dead for the rest of
## the run: the craft button was clicked once and the player never walked again.
func _panel_buttons(h: TestHarness, world: SurvivalWorld) -> void:
	var input := SurvivalInput.new()
	input.bind(world)
	h.assert_true(input.polling(), "a sampler outside the tree polls the keyboard for held keys")
	world.craft_open = true
	input.latch("menu_confirm", true)
	h.assert_true(input.polling(), "and still does after the Craft button is clicked")
	input.latch("craft_toggle", true)
	input.sample(world)
	h.assert_true(bool(world.input["craft_toggle"]), "the close button reaches the sim as a one-shot")
	SurvivalSim.clear_one_shots(world)
	world.craft_open = false
	h.assert_true(input.polling(), "closing the panel leaves the keyboard polled")
	input.press("w")
	h.assert_false(input.polling(), "a fed held key is what stops the polling")
	input.release("w")
	input.free()


func _actions(h: TestHarness) -> void:
	var input := SurvivalInput.new()
	var seen: Array = []
	input.action.connect(func(name: String) -> void: seen.append(name))
	var first := [0]
	input.first_input.connect(func() -> void: first[0] += 1)
	input.press("q")
	input.press("e")
	input.press("m")
	input.press("`")
	h.assert_eq(seen, ["yaw_left", "yaw_right", "map", "debug"], "the mode keys are actions")
	h.assert_eq(first[0], 1, "audio starts on the first key only")
	h.assert_true(input.debug_on, "the backtick opened the debug panel")
	seen.clear()
	# The backtick returns immediately, so it never reaches the keys below it.
	input.press("k")
	h.assert_eq(seen, ["wireframe"], "K is the wireframe key while debug is up, not the season")
	seen.clear()
	input.press("`")
	input.press("k")
	h.assert_eq(seen, ["debug", "season"], "and the season again once it is down")
	seen.clear()
	input.set_mode("verdict")
	input.press("q")
	h.assert_eq(seen, [], "verdict mode refuses the turn keys")
	input.set_mode("play")
	input.yaw_allowed = false
	input.press("q")
	h.assert_eq(seen, [], "and so does a run whose camera forbids rotation")
	input.free()
