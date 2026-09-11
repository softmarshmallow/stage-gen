extends RefCounted

## Independent camera-shot lifecycle, presentation isolation, and renderer proof.
const SHOT = preload("res://addons/game_presentation/camera/establishing_shot.gd")
const DESIGN_SIZE := Vector2(1280, 900)
const LOCATIONS: Array[String] = ["forward_command", "perimeter_overlook", "coastal_staging"]
var _errors: Array[String] = []
var _capture_count := 0


func run(root: Control, options: Dictionary) -> void:
	_check_controller()
	await _check_runtime(root)
	if _errors.is_empty() and options.has("capture-establishing-shot"):
		if DisplayServer.get_name() == "headless":
			_errors.append("Establishing-shot captures require a real renderer.")
		else:
			await _capture_proof(root, String(options.get("capture-dir", "res://qa/establishing-shot/captures")))
	for issue: String in _errors:
		printerr("FAIL Establishing shot: " + issue)
	if _errors.is_empty():
		print("PASS Establishing shot: bounded camera motion, frame partitions, settings snapshots, skip/completion, atomic restore, cover geometry, actor/manpu isolation, frozen redraw, and resumed timeline")
		if _capture_count > 0:
			print("Establishing-shot captures complete: %d PNG and metadata pairs" % _capture_count)
	root.get_tree().quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _same_sample(left: Dictionary, right: Dictionary) -> bool:
	for field: String in ["active", "location_id", "flare_source_uv"]:
		if left[field] != right[field]:
			return false
	for field: String in ["progress", "zoom", "pan_x", "flare_strength"]:
		if not is_equal_approx(float(left[field]), float(right[field])):
			return false
	return true


func _bounded(sample: Dictionary) -> void:
	for field: String in ["progress", "zoom", "pan_x", "flare_strength"]:
		_expect(is_finite(float(sample[field])), "Camera samples must remain finite: " + field)
	_expect(float(sample["progress"]) >= 0.0 and float(sample["progress"]) <= 1.0, "Shot progress must remain normalized.")
	_expect(float(sample["zoom"]) >= 1.0 and float(sample["zoom"]) <= 1.16, "Authored zoom must remain inside its configured range.")
	_expect(absf(float(sample["pan_x"])) <= 120.0 and float(sample["flare_strength"]) >= 0.0 and float(sample["flare_strength"]) <= 1.0, "Pan and flare samples must remain bounded.")


func _neutral(sample: Dictionary, context: String) -> void:
	_expect(not bool(sample["active"]) and is_equal_approx(float(sample["zoom"]), 1.0) and is_zero_approx(float(sample["pan_x"])) and is_zero_approx(float(sample["flare_strength"])), context + " must restore the exact base camera and no flare.")


func _check_controller() -> void:
	var shot: SHOT = SHOT.new()
	_expect(not shot.is_active(), "A fresh controller must not introduce an unsolicited shot.")
	_expect(shot.start("forward_command", {"duration_seconds": 4.0, "flare_enabled": true}).is_empty(), "A valid establishing shot must start.")
	shot.advance(1.0)
	var held: Dictionary = shot.sample()
	var snapshot: Dictionary = shot.get_state()
	shot.configure({"duration_seconds": 6.0, "pan_amount": -80.0})
	_expect(_same_sample(held, shot.sample()) and shot.get_state()["active_settings"] == snapshot["active_settings"], "Changing settings must affect future shots without retuning active motion.")
	var restored: SHOT = SHOT.new()
	_expect(restored.restore(shot.get_state()).is_empty() and _same_sample(restored.sample(), shot.sample()), "Restore must reproduce an active camera sample exactly.")
	var saved: Dictionary = shot.get_state()
	for invalid: Dictionary in [{"duration_seconds": 1.0}, {"pan_amount": 121.0}, {"zoom_amount": 0.2}, {"flare_strength": -0.1}, {"flare_enabled": "yes"}, {"flare_source_uv": [-0.1, 0.5]}, {"unknown": 1}]:
		_expect(not shot.configure(invalid).is_empty() and shot.get_state() == saved, "Invalid shot settings must fail atomically.")
	var corrupted: Dictionary = saved.duplicate(true)
	corrupted["elapsed"] = -1.0
	_expect(not shot.restore(corrupted).is_empty() and shot.get_state() == saved, "An invalid saved timeline must not replace the active shot.")
	for bad_delta: float in [-1.0, INF, NAN]:
		shot.advance(bad_delta)
	shot.sample()
	_expect(shot.get_state() == saved, "Sampling and invalid deltas must leave the timeline unchanged.")
	shot.advance(3.0)
	_neutral(shot.sample(), "Natural completion")
	_expect(is_equal_approx(float(shot.get_state()["elapsed"]), 4.0), "An active shot must finish using its original duration snapshot.")
	shot.start("perimeter_overlook")
	_expect(is_equal_approx(float(shot.get_state()["active_settings"]["duration_seconds"]), 6.0), "The next shot must adopt changed settings.")
	shot.advance(0.5)
	shot.skip()
	_neutral(shot.sample(), "Skip")
	shot.start("coastal_staging")
	shot.clear()
	_neutral(shot.sample(), "Clear")
	for elapsed: float in [0.0, 0.2, 1.0, 2.0, 3.999, 4.0, 5.0]:
		var once: SHOT = SHOT.new()
		var parts: SHOT = SHOT.new()
		once.start("coastal_staging", {"flare_enabled": true, "zoom_amount": 0.16, "pan_amount": -120.0})
		parts.start("coastal_staging", {"flare_enabled": true, "zoom_amount": 0.16, "pan_amount": -120.0})
		once.advance(elapsed)
		for index in 40:
			parts.advance(elapsed / 40.0)
		_expect(_same_sample(once.sample(), parts.sample()), "Camera results must be independent of frame partition at %.3f seconds." % elapsed)
		_bounded(once.sample())
	shot.start("forward_command", {"flare_enabled": false})
	for index in 20:
		shot.advance(0.1)
		_expect(is_zero_approx(float(shot.sample()["flare_strength"])), "Disabling the flare must remove its contribution for the whole shot.")


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
	_expect((scene.get("_load_errors") as Array).is_empty(), "Establishing route assets must load.")
	return scene


func _tick(scene: Control, seconds: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", seconds)
	scene.set("_capture_frozen", true)


func _background_rect(scene: Control) -> Rect2:
	var textures: Dictionary = scene.get("_location_textures")
	var background: Texture2D = textures[String(scene.get("_location_id"))]
	return scene.call("_presented_background_rect", DESIGN_SIZE, background.get_size())


func _hidden_cast(scene: Control) -> void:
	var actors: Dictionary = scene.get("_actor_nodes")
	for actor: String in actors:
		_expect(not (actors[actor] as TextureRect).visible, "Establishing shots must hide actor " + actor)
	_expect((scene.call("_presented_manpu_cues") as Array).is_empty(), "Establishing shots must hide all owner-attached manpu.")
	for field: String in ["_line", "_speaker"]:
		_expect(not (scene.get(field) as Control).visible, "Establishing shots must hide ordinary dialogue " + field)


func _check_runtime(root: Control) -> void:
	var scene: Control = await _open(root, "demos/dialogue")
	scene.call("_select_location", "forward_command", true)
	var base_rect: Rect2 = _background_rect(scene)
	var actors: Dictionary = scene.get("_actor_nodes")
	var actor_rects := {}
	for actor: String in actors:
		actor_rects[actor] = (actors[actor] as TextureRect).get_rect()
	_expect((scene.call("start_establishing", "forward_command", {"duration_seconds": 4.0, "pan_amount": 120.0, "zoom_amount": 0.16, "flare_enabled": true}) as Array).is_empty(), "The stage must start a configured location shot.")
	_hidden_cast(scene)
	var sample_before: Dictionary = scene.call("establishing_sample")
	var saved: Dictionary = scene.call("save_establishing")
	for index in 8:
		scene.call("_layout_interface")
		scene.call("_update_character_layers")
		scene.call("_process", 0.25)
	_expect(scene.call("save_establishing") == saved and _same_sample(sample_before, scene.call("establishing_sample")), "Frozen redraw and layout must not advance the camera.")
	var samples_changed := false
	for index in 8:
		_tick(scene, 0.4)
		var rect: Rect2 = _background_rect(scene)
		_expect(rect.position.x <= 0.001 and rect.position.y <= 0.001 and rect.end.x >= DESIGN_SIZE.x - 0.001 and rect.end.y >= DESIGN_SIZE.y - 0.001, "Pan and zoom must keep the entire viewport covered by the background.")
		var sample: Dictionary = scene.call("establishing_sample")
		var flare: ColorRect = scene.get("_location_flare") as ColorRect
		_expect(flare.visible == (float(sample["flare_strength"]) > 0.0) and flare.mouse_filter == Control.MOUSE_FILTER_IGNORE, "The shot flare must follow its envelope without intercepting player input.")
		if flare.visible:
			var source: Array = sample["flare_source_uv"]
			var expected_source: Vector2 = (rect.position + rect.size * Vector2(float(source[0]), float(source[1]))) / DESIGN_SIZE
			var material: ShaderMaterial = flare.material as ShaderMaterial
			var actual_source: Vector2 = material.get_shader_parameter("light_position")
			_expect(actual_source.is_equal_approx(expected_source), "The flare's screen source must follow the same background pan and zoom.")
		samples_changed = samples_changed or not rect.is_equal_approx(base_rect)
		_hidden_cast(scene)
	_expect(samples_changed, "The runtime must apply shot motion to its actual background rectangle.")
	saved = scene.call("save_establishing")
	var paused_sample: Dictionary = scene.call("establishing_sample")
	scene.call("skip_establishing")
	_expect(_background_rect(scene).is_equal_approx(base_rect), "Skipping must restore the exact unanimated background framing.")
	for actor: String in actors:
		_expect((actors[actor] as TextureRect).visible and (actors[actor] as TextureRect).get_rect().is_equal_approx(actor_rects[actor]), "Finishing a shot must restore the existing actor geometry.")
	_expect((scene.call("restore_establishing", saved) as Array).is_empty() and _same_sample(paused_sample, scene.call("establishing_sample")), "The stage must restore the exact paused shot sample.")
	_hidden_cast(scene)
	_tick(scene, 1.0)
	_expect(not bool(scene.call("is_establishing")) and _background_rect(scene).is_equal_approx(base_rect), "Natural shot completion must restore the base presentation.")
	var unchanged: Dictionary = scene.call("save_establishing")
	_expect(not (scene.call("start_establishing", "missing_location") as Array).is_empty() and scene.call("save_establishing") == unchanged, "Unknown location requests must be rejected without losing the current state.")


func _capture_proof(root: Control, folder: String) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "Cannot create establishing capture directory.")
	var scene: Control = await _open(root, "demos/establishing_shot")
	scene.set("_capturing", true)
	scene.set("_natural_blink", false)
	scene.set("_pointer", Vector2(-1000, -1000))
	for location: String in LOCATIONS:
		_prepare_capture(scene, location, {"duration_seconds": 4.0, "pan_amount": 60.0, "zoom_amount": 0.08, "flare_enabled": location == "coastal_staging", "flare_strength": 0.35})
		await _capture(root, scene, folder, location + "_opening")
		_tick(scene, 2.0)
		await _capture(root, scene, folder, location + "_middle")
		_tick(scene, 2.0)
		await _capture(root, scene, folder, location + "_settled")
	_prepare_capture(scene, "coastal_staging", {"duration_seconds": 4.0, "pan_amount": -120.0, "zoom_amount": 0.16, "flare_enabled": true, "flare_strength": 1.0})
	_tick(scene, 2.0)
	await _capture(root, scene, folder, "coastal_extreme_motion_flare")
	_prepare_capture(scene, "coastal_staging", {"duration_seconds": 4.0, "pan_amount": -120.0, "zoom_amount": 0.16, "flare_enabled": false})
	_tick(scene, 2.0)
	await _capture(root, scene, folder, "coastal_extreme_no_flare")


func _prepare_capture(scene: Control, location: String, overrides: Dictionary) -> void:
	scene.call("_set_profile", location)
	var settings: Dictionary = (scene.get("_demo_settings") as Dictionary).duplicate(true)
	settings.merge(overrides, true)
	scene.set("_demo_settings", settings)
	scene.call("_select_location", location, true)
	scene.call("_replay_shot")


func _rect_array(rect: Rect2) -> Array[float]:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _capture(root: Control, scene: Control, folder: String, name: String) -> void:
	root.get_viewport().gui_release_focus()
	root.get_viewport().notify_mouse_exited()
	scene.call("_update_interface")
	await root.get_tree().process_frame
	scene.queue_redraw()
	for index in 4:
		RenderingServer.force_draw(false)
	var picture: Image = root.get_viewport().get_texture().get_image()
	_expect(picture.get_size() == Vector2i(1280, 900) and picture.save_png(folder.path_join(name + ".png")) == OK, "Cannot save establishing frame " + name)
	var transform: Transform2D = root.get_viewport().get_final_transform()
	var extent: Vector2 = transform.basis_xform(DESIGN_SIZE)
	var metadata := {"state": name, "route": "demos/establishing_shot", "establishing_shot": scene.call("save_establishing"), "sample": scene.call("establishing_sample"),
		"background_rect": _rect_array(_background_rect(scene)), "actors": {}, "manpu_cues": scene.call("_presented_manpu_cues"),
		"capture_space": "logical_viewport", "viewport": [1280, 900], "window_size": [root.get_window().size.x, root.get_window().size.y],
		"output_rect": [transform.origin.x, transform.origin.y, extent.x, extent.y], "output_scale": [transform.x.x, transform.y.y]}
	var actors: Dictionary = scene.get("_actor_nodes")
	for actor: String in actors:
		metadata["actors"][actor] = {"visible": (actors[actor] as TextureRect).visible, "rect": _rect_array((actors[actor] as TextureRect).get_rect())}
	var record: FileAccess = FileAccess.open(folder.path_join(name + ".json"), FileAccess.WRITE)
	if record == null:
		_errors.append("Cannot write establishing metadata " + name)
	else:
		record.store_string(JSON.stringify(metadata, "\t"))
	_capture_count += 1
	print("Establishing-shot capture: " + ProjectSettings.globalize_path(folder.path_join(name + ".png")))
