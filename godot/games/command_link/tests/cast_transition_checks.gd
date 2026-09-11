extends RefCounted

## Independent sequence, curve, route-input, and renderer checks.
const CAST = preload("res://addons/game_presentation/actors/cast_transition.gd")
const CURVE = preload("res://addons/game_presentation/motion/motion_curve.gd")
const ACTORS: Array[String] = ["mira", "lena", "sera"]
const EXIT_CATALOG := "res://addons/game_presentation/actors/presets/exit.json"
const SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
const DESIGN_SIZE := Vector2(1280, 900)
var _errors: Array[String] = []
var _capture_count := 0
var _slots: Dictionary = {}


func run(root: Control, options: Dictionary) -> void:
	var specification: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SPEC))
	_slots = specification["slots"]
	_check_sequence()
	_check_curves()
	await _check_runtime(root)
	if _errors.is_empty() and options.has("capture-cast-transition"):
		if DisplayServer.get_name() == "headless":
			_errors.append("Cast Transition captures require a real renderer.")
		else:
			await _capture_proof(root, String(options.get("capture-dir", "res://tests/cast-transition/captures")))
	for issue: String in _errors:
		printerr("FAIL Cast Transition: " + issue)
	if _errors.is_empty():
		print("PASS Cast Transition: initial two-actor cast, ordered phases, both patterns, role rotation, frame partitions, finite bounded appearance, configurable curves, frozen rendering, reset, route isolation and keyboard controls")
		if _capture_count > 0:
			print("Cast Transition captures complete: %d PNG and metadata pairs" % _capture_count)
	root.get_tree().quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _new() -> CAST:
	var controller: CAST = CAST.new()
	_expect(controller.initialize(ACTORS, EXIT_CATALOG, SPEC).is_empty(), "The cast and transition specification must initialize.")
	return controller


func _phase(controller: CAST) -> String:
	return String(controller.get_state().get("phase", ""))


func _duration(controller: CAST) -> float:
	return float(controller.get_settings()["motion_duration_seconds"])


func _samples(controller: CAST) -> Dictionary:
	var result := {}
	for actor: String in ACTORS:
		result[actor] = controller.sample(actor)
	return result


func _same_samples(left: Dictionary, right: Dictionary) -> bool:
	for actor: String in ACTORS:
		if left[actor]["visible"] != right[actor]["visible"]:
			return false
		for channel: String in ["center_x", "opacity", "brightness"]:
			if not is_equal_approx(float(left[actor][channel]), float(right[actor][channel])):
				return false
	return true


func _initial(controller: CAST, context: String) -> void:
	var mira: Dictionary = controller.sample("mira")
	var lena: Dictionary = controller.sample("lena")
	var sera: Dictionary = controller.sample("sera")
	_expect(not controller.is_busy() and bool(mira["visible"]) and bool(lena["visible"]) and not bool(sera["visible"]), context + " must contain exactly Mira and Lena.")
	_expect(is_equal_approx(float(mira["center_x"]), float(_slots["left"])) and is_equal_approx(float(lena["center_x"]), float(_slots["right"])), context + " must use the two authored positions.")


func _bounded(controller: CAST) -> void:
	for actor: String in ACTORS:
		var sample: Dictionary = controller.sample(actor)
		_expect(is_finite(float(sample["center_x"])), "Motion curves must always yield finite actor positions.")
		for channel: String in ["opacity", "brightness"]:
			var value: float = sample[channel]
			_expect(is_finite(value) and value >= 0.0 and value <= 1.0, "Spring overshoot must never escape appearance channel bounds.")


func _check_sequence() -> void:
	var controller: CAST = _new()
	if not controller.initialized:
		return
	_initial(controller, "Initial cast")
	controller.configure({"pattern": "shift_and_replace", "curve": "linear"})
	var duration: float = _duration(controller)
	controller.start()
	_expect(_phase(controller) == "exit", "A handoff must begin with the outgoing actor's exit.")
	controller.advance(0.495)
	var outgoing: Dictionary = controller.sample("mira")
	_expect(is_zero_approx(float(outgoing["brightness"])) and is_equal_approx(float(outgoing["opacity"]), 1.0), "The outgoing actor must reach an opaque black matte before replacement.")
	_expect(not bool(controller.sample("sera")["visible"]) and is_equal_approx(float(controller.sample("lena")["center_x"]), float(_slots["right"])), "The entrant must stay absent and the survivor still during exit.")
	var busy_before: Dictionary = controller.get_state()
	controller.start()
	_expect(controller.get_state() == busy_before, "Repeated start while busy must not restart the sequence.")
	_expect(not controller.configure({"curve": "spring"}).is_empty() and controller.get_state() == busy_before, "Motion settings must reject changes while a handoff is busy.")
	controller.advance(0.405)
	_expect(_phase(controller) == "move" and not bool(controller.sample("mira")["visible"]) and not bool(controller.sample("sera")["visible"]), "Movement must begin only after exit completion, before entry begins.")
	controller.advance(duration * 0.5)
	_expect(is_equal_approx(float(controller.sample("lena")["center_x"]), (float(_slots["left"]) + float(_slots["right"])) * 0.5), "Linear survivor movement must pass through the midpoint.")
	controller.advance(duration * 0.5)
	_expect(_phase(controller) == "enter" and is_equal_approx(float(controller.sample("lena")["center_x"]), float(_slots["left"])), "Entry must wait until the survivor reaches the left position.")
	_expect(is_zero_approx(float(controller.sample("sera")["opacity"])), "The incoming actor must begin entry with zero opacity.")
	controller.advance(duration)
	_expect(_phase(controller) == "idle" and not bool(controller.sample("mira")["visible"]) and bool(controller.sample("lena")["visible"]) and bool(controller.sample("sera")["visible"]), "A complete handoff must leave only the survivor and entrant visible.")
	_expect(is_equal_approx(float(controller.sample("lena")["center_x"]), float(_slots["left"])) and is_equal_approx(float(controller.sample("sera")["center_x"]), float(_slots["right"])), "The resulting two-actor cast must occupy exact authored endpoints.")
	controller.start()
	controller.advance(0.9 + duration * 2.0)
	_expect(not bool(controller.sample("lena")["visible"]) and is_equal_approx(float(controller.sample("sera")["center_x"]), float(_slots["left"])) and is_equal_approx(float(controller.sample("mira")["center_x"]), float(_slots["right"])), "A second handoff must rotate outgoing, surviving, and incoming actors.")
	controller.reset()
	controller.configure({"pattern": "replace_in_place"})
	controller.start()
	controller.advance(0.9)
	_expect(_phase(controller) == "enter", "Replace in place must skip the survivor move phase.")
	controller.advance(duration)
	_expect(is_equal_approx(float(controller.sample("lena")["center_x"]), float(_slots["right"])) and is_equal_approx(float(controller.sample("sera")["center_x"]), float(_slots["left"])), "Replace in place must preserve the survivor's position and fill the vacated slot.")
	for pattern: String in ["shift_and_replace", "replace_in_place"]:
		for elapsed: float in [0.495, 0.9, 0.9 + duration * 0.5, 0.9 + duration, 0.9 + duration * 1.5, 0.9 + duration * 2.0, 5.0]:
			var once: CAST = _new()
			var partitioned: CAST = _new()
			once.configure({"pattern": pattern})
			partitioned.configure({"pattern": pattern})
			once.start()
			partitioned.start()
			once.advance(elapsed)
			for index in 30:
				partitioned.advance(elapsed / 30.0)
			_expect(_phase(once) == _phase(partitioned) and _same_samples(_samples(once), _samples(partitioned)), "Handoff phases and poses must be independent of frame partition at %.4f seconds (%s)." % [elapsed, pattern])
			_bounded(once)
	controller.reset()
	controller.start()
	controller.advance(0.2)
	controller.reset()
	_initial(controller, "Mid-sequence reset")
	var stable: Dictionary = controller.get_state()
	controller.advance(-1.0)
	controller.advance(INF)
	controller.advance(NAN)
	for index in 10:
		_samples(controller)
	_expect(controller.get_state() == stable, "Sampling and invalid deltas must not mutate sequence state.")


func _check_curves() -> void:
	var controller: CAST = _new()
	var settings: Dictionary = controller.get_settings()
	var quarter_samples := {}
	for curve: String in ["linear", "ease_in_out", "spring"]:
		settings["curve"] = curve
		_expect(is_zero_approx(CURVE.sample(0.0, settings)) and is_equal_approx(CURVE.sample(1.0, settings), 1.0), "Every curve must have exact motion endpoints.")
		quarter_samples[curve] = CURVE.sample(0.25, settings)
		for index in 101:
			_expect(is_finite(CURVE.sample(index / 100.0, settings)), "Curve graphs must contain only finite samples.")
	_expect(is_equal_approx(float(quarter_samples["linear"]), 0.25) and not is_equal_approx(float(quarter_samples["linear"]), float(quarter_samples["ease_in_out"])), "Linear and eased movement must produce different intermediate positions.")
	settings["curve"] = "spring"
	settings["frequency"] = 1.0
	settings["damping_ratio"] = 0.2
	var first_shape: Array[float] = []
	for phase: float in [0.1, 0.25, 0.5, 0.75]:
		first_shape.append(CURVE.sample(phase, settings))
	settings["frequency"] = 3.0
	settings["damping_ratio"] = 1.0
	var different := false
	for index in first_shape.size():
		var phase: float = [0.1, 0.25, 0.5, 0.75][index]
		different = different or absf(first_shape[index] - CURVE.sample(phase, settings)) > 0.01
	_expect(different, "Frequency and damping controls must alter the actual spring curve.")
	controller.configure({"curve": "spring", "frequency": 3.0, "damping_ratio": 0.2})
	controller.start()
	for index in 100:
		controller.advance(0.035)
		_bounded(controller)
	var before: Dictionary = controller.get_state()
	for invalid: Dictionary in [{"frequency": 0.5}, {"damping_ratio": 0.1}, {"motion_duration_seconds": 0.1}, {"travel_distance": 200.0}, {"curve": "unknown"}]:
		_expect(not controller.configure(invalid).is_empty() and controller.get_state() == before, "Invalid curve/settings changes must fail atomically.")


func _controller(scene: Control) -> CAST:
	return scene.get("_cast_transition") as CAST


func _open(root: Control, route: String) -> Control:
	if route in ["game", "new_game", "menu"]:
		route = "game:command_link/" + route
	_expect(bool(root.call("open_route", route)), "Could not open " + route)
	var scene: Control = root.get("active_scene") as Control
	scene.set("_capture_frozen", true)
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	scene.set("_entry", 1.0)
	scene.call("_update_character_layers")
	_expect((scene.get("_load_errors") as Array).is_empty(), "Cast route assets and controllers must load.")
	return scene


func _tick(scene: Control, seconds: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", seconds)
	scene.set("_capture_frozen", true)


func _sprite(scene: Control, actor: String) -> TextureRect:
	var nodes: Dictionary = scene.get("_actor_nodes")
	return nodes[actor] as TextureRect


func _check_runtime(root: Control) -> void:
	var scene: Control = await _open(root, "demos/cast_transition")
	var controller: CAST = _controller(scene)
	_expect(_sprite(scene, "mira").visible and _sprite(scene, "lena").visible and not _sprite(scene, "sera").visible, "The route must draw exactly two actors initially, not a transparent third sprite.")
	var defaults: Dictionary = controller.get_settings()
	var frequency: HSlider = scene.get("_frequency_slider") as HSlider
	var damping: HSlider = scene.get("_damping_slider") as HSlider
	var duration: HSlider = scene.get("_duration_slider") as HSlider
	var travel: HSlider = scene.get("_travel_slider") as HSlider
	var graph: Control = scene.get("_curve_graph") as Control
	var before_curve: Array = graph.call("get_curve_samples", 21)
	_expect(frequency.editable and damping.editable and duration.editable and travel.editable, "All settings must be available while the Spring route is idle.")
	var slider_point: Vector2 = frequency.get_global_rect().position + Vector2(frequency.size.x * 0.85, frequency.size.y * 0.5)
	scene.call("_route_mouse", slider_point)
	_expect(not is_equal_approx(float(controller.get_settings()["frequency"]), float(defaults["frequency"])) and graph.call("get_curve_samples", 21) != before_curve, "A native slider click must change both the settings and actual curve graph.")
	var plotted: Array = graph.call("get_curve_samples", 21)
	for point: Vector2 in plotted:
		_expect(is_equal_approx(point.y, CURVE.sample(point.x, controller.get_settings())), "The visible graph must sample the same motion function as the actors.")
	scene.call("_route_key", KEY_C)
	_expect(String(controller.get_settings()["curve"]) == "linear" and not frequency.editable and not damping.editable and duration.editable and travel.editable, "Only Spring-specific settings should disable outside Spring.")
	root.get_viewport().gui_release_focus()
	scene.call("_route_key", KEY_SPACE)
	_expect(controller.is_busy() and not frequency.editable and not damping.editable and not duration.editable and not travel.editable, "Space must start the sequence and lock settings during motion.")
	var busy: Dictionary = controller.get_state()
	scene.call("_route_key", KEY_P)
	scene.call("_route_key", KEY_C)
	scene.call("_route_key", KEY_E)
	_expect(controller.get_state() == busy, "Busy controls must not retune or restart the sequence.")
	_tick(scene, 0.9 + _duration(controller) * 0.25)
	var pose: Dictionary = controller.sample("lena")
	_expect(not _sprite(scene, "mira").visible and not _sprite(scene, "sera").visible, "Only the survivor may be drawn during repositioning.")
	_expect(is_equal_approx(_sprite(scene, "lena").get_rect().get_center().x, float(pose["center_x"])), "The rendered survivor must follow the controller's exact translation.")
	var frozen: Dictionary = controller.get_state()
	for index in 10:
		scene.call("_layout_interface")
		scene.call("_update_character_layers")
		scene.call("_process", 0.25)
	_expect(controller.get_state() == frozen and not _sprite(scene, "sera").visible, "Frozen redraws must not advance phases or resurrect the hidden actor.")
	scene.call("_route_key", KEY_R)
	_initial(controller, "Route reset")
	_expect(controller.get_settings() == defaults, "Route reset must also restore its initial settings.")
	scene.call("_route_key", KEY_P)
	_expect(String(controller.get_settings()["pattern"]) == "replace_in_place", "P must select the comparison pattern.")
	scene.call("_route_key", KEY_E)
	_tick(scene, 0.9 + _duration(controller))
	_expect(_sprite(scene, "lena").visible and _sprite(scene, "sera").visible and not _sprite(scene, "mira").visible, "A completed replacement must leave the correct two rendered actors.")
	scene = await _open(root, "new_game")
	scene.call("skip_establishing")
	scene.set("_entry", 1.0)
	scene.call("_update_interface")
	scene.call("_route_mouse", (scene.get("_next_button") as Button).get_global_rect().get_center())
	var game_before: Dictionary = scene.call("save_game")
	var game_visibility := {}
	for actor: String in ACTORS:
		game_visibility[actor] = _sprite(scene, actor).visible
	await _open(root, "demos/cast_transition")
	scene = root.get("active_scene") as Control
	scene.call("_start_handoff")
	_tick(scene, 0.4)
	scene = await _open(root, "game")
	var game_after: Dictionary = scene.call("save_game")
	for field: String in ["story_id", "priority", "approach", "connected", "location", "dialogue_camera"]:
		_expect(game_after[field] == game_before[field], "Cast workbench navigation must preserve game " + field)
	for actor: String in ACTORS:
		_expect(_sprite(scene, actor).visible == bool(game_visibility[actor]), "Demo cast visibility must not change the mission's authored cast.")


func _prepare(scene: Control, settings: Dictionary = {}) -> void:
	scene.call("_reset_cast")
	_controller(scene).configure(settings)
	scene.call("_update_interface")


func _capture_proof(root: Control, folder: String) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "Cannot create cast capture directory.")
	var scene: Control = await _open(root, "demos/cast_transition")
	scene.call("_select_location", "forward_command", true)
	scene.set("_capturing", true)
	scene.set("_location_title_elapsed", 3.7)
	scene.set("_elapsed", 1.0)
	scene.call("_update_location_title")
	_prepare(scene)
	await _capture(root, scene, folder, "initial_two", 0.0)
	scene.call("_start_handoff")
	var previous := 0.0
	for frame: Array in [["exit_matte", 0.495], ["move_start", 0.9], ["move_middle", 1.3], ["enter_start", 1.7], ["enter_middle", 2.1], ["finished", 2.5]]:
		_tick(scene, float(frame[1]) - previous)
		previous = float(frame[1])
		await _capture(root, scene, folder, String(frame[0]), previous)
	scene.call("_start_handoff")
	_tick(scene, 2.5)
	await _capture(root, scene, folder, "repeat_finished", 2.5)
	_prepare(scene, {"pattern": "replace_in_place"})
	scene.call("_start_handoff")
	_tick(scene, 1.3)
	await _capture(root, scene, folder, "replace_entry", 1.3)
	_tick(scene, 0.4)
	await _capture(root, scene, folder, "replace_finished", 1.7)
	for curve: String in ["linear", "ease_in_out", "spring"]:
		_prepare(scene, {"curve": curve})
		scene.call("_start_handoff")
		_tick(scene, 1.1)
		await _capture(root, scene, folder, curve + "_move_quarter", 1.1)
	_prepare(scene, {"curve": "spring", "frequency": 2.8, "damping_ratio": 0.25, "motion_duration_seconds": 1.2, "travel_distance": 120.0})
	await _capture(root, scene, folder, "spring_tuned_graph", 0.0)
	_prepare(scene, {"curve": "spring", "frequency": 1.5, "damping_ratio": 0.2})
	scene.call("_start_handoff")
	var peak_progress: float = 1.0 / (2.0 * 1.5 * sqrt(1.0 - 0.2 * 0.2))
	var peak_time: float = 0.9 + _duration(_controller(scene)) * peak_progress
	_tick(scene, peak_time)
	await _capture(root, scene, folder, "extreme_spring_peak", peak_time)


func _rect_array(rect: Rect2) -> Array[float]:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _capture(root: Control, scene: Control, folder: String, name: String, sequence_time: float) -> void:
	root.get_viewport().gui_release_focus()
	if root.get_viewport().gui_get_hovered_control() != null:
		root.get_viewport().notify_mouse_exited()
	scene.call("_update_interface")
	await root.get_tree().process_frame
	scene.queue_redraw()
	for index in 4:
		RenderingServer.force_draw(false)
	var image: Image = root.get_viewport().get_texture().get_image()
	_expect(image.get_size() == Vector2i(1280, 900) and image.save_png(folder.path_join(name + ".png")) == OK, "Cannot save cast frame " + name)
	var graph: Control = scene.get("_curve_graph") as Control
	var graph_points: Array = graph.call("get_curve_samples", 121)
	var graph_data: Array = []
	for point: Vector2 in graph_points:
		graph_data.append([point.x, point.y])
	var transform: Transform2D = root.get_viewport().get_final_transform()
	var extent: Vector2 = transform.basis_xform(DESIGN_SIZE)
	var metadata := {"state": name, "route": "demos/cast_transition", "sequence_time_seconds": sequence_time,
		"cast_transition": _controller(scene).get_state(), "curve_points": graph_data, "actors": {},
		"capture_space": "logical_viewport", "viewport": [1280, 900], "window_size": [root.get_window().size.x, root.get_window().size.y],
		"output_rect": [transform.origin.x, transform.origin.y, extent.x, extent.y], "output_scale": [transform.x.x, transform.y.y]}
	for actor: String in ACTORS:
		var sprite: TextureRect = _sprite(scene, actor)
		metadata["actors"][actor] = {"visible": sprite.visible, "rect": _rect_array(sprite.get_rect()), "modulate": [sprite.modulate.r, sprite.modulate.g, sprite.modulate.b, sprite.modulate.a]}
	var record: FileAccess = FileAccess.open(folder.path_join(name + ".json"), FileAccess.WRITE)
	if record == null:
		_errors.append("Cannot write cast metadata " + name)
	else:
		record.store_string(JSON.stringify(metadata, "\t"))
	_capture_count += 1
	print("Cast Transition capture: " + ProjectSettings.globalize_path(folder.path_join(name + ".png")))
