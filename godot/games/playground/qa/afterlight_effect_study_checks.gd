extends SceneTree

## Host-owned study integration and optional native 1x/2x visual evidence.
## Godot --headless --path godot/games/playground --script res://qa/afterlight_effect_study_checks.gd
## Omit --headless and add -- --capture-effect-studies for native PNG evidence.
const DESIGN_SIZE := Vector2i(1280, 900)
const PREVIEW := Rect2(32, 148, 1216, 468)
const CAPTURES := "res://qa/afterlight-effects"
var _failures: Array[String] = []
var _capture_enabled := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-effect-studies")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Afterlight effect study captures require a native renderer.")
		quit(2)
		return
	var composition = load("res://games/bishoujo_afterlight/root.gd").new()
	root.content_scale_size = DESIGN_SIZE
	root.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	for window_size: Vector2i in [DESIGN_SIZE, DESIGN_SIZE * 2]:
		root.size = window_size
		for route: String in ["effects_menu", "intertitle_study", "drift_study", "halo_study"]:
			var scene = _make_scene(route, composition.CONTENT)
			if scene == null:
				continue
			await _settle()
			_expect(scene.size.is_equal_approx(Vector2(DESIGN_SIZE)), "Studies keep their fixed logical canvas at " + str(window_size))
			if route == "intertitle_study":
				await _intertitle_controls(scene)
			elif route in ["drift_study", "halo_study"]:
				await _portrait_controls(scene, route)
			await _capture(route + "-" + str(window_size.x))
			scene.free()
	await _dedicated_profile_binding(composition.CONTENT)
	for failure: String in _failures:
		printerr("FAIL Afterlight effect studies: " + failure)
	if _failures.is_empty():
		print("PASS Afterlight effect studies: fixed 1x/2x canvas, native-scaled controls, intertitle actions/duration, guest/detail bindings, coverage, shared drift, halo geometry and toggle")
	quit(0 if _failures.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_failures.append(message)


func _make_scene(route: String, content: Dictionary) -> Control:
	var packed = load("res://games/presentation_lab/afterlight/" + route + ".tscn")
	if packed == null or not packed.can_instantiate():
		_failures.append("Cannot instantiate " + route)
		return null
	var scene = packed.instantiate()
	var composition = load("res://games/bishoujo_afterlight/root.gd").new()
	composition.prepare_scene(scene, route, {}, {})
	scene.content = composition.localize_content(scene.text_set, content)
	root.add_child(scene)
	scene.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	scene.set_process(false)
	_expect((scene.get("_load_errors") as Array).is_empty(), route + " must load: " + str(scene.get("_load_errors")))
	return scene


func _intertitle_controls(scene: Control) -> void:
	var draft: TextEdit = scene.get("_draft_text")
	var duration: HSlider = scene.get("_duration_slider")
	var initial_text := draft.text
	for text: String in ["I", "A".repeat(512)]:
		draft.text = text
		scene.call("_draft_changed")
		for seconds: float in [duration.min_value, duration.max_value]:
			duration.value = seconds
			scene.call("_replay_effect")
			_expect(scene.get("_intertitle").sample()["text"] == text, "Duration limits accept short and long editable monologue text.")
	draft.text = initial_text
	scene.call("_draft_changed")
	duration.value = float(initial_text.length()) / 32.0
	await _click(scene.get("_replay_button"))
	await _click(scene.get("_action_button"))
	_expect(scene.get("_intertitle").sample()["phase"] == "holding", "The first action reveals the text without continuing.")
	await _click(scene.get("_action_button"))
	_expect(scene.get("_intertitle").sample()["phase"] == "finished", "The next explicit action continues.")
	await _click(scene.get("_replay_button"))
	await _click(scene.get("_action_button"))
	var title: Label = scene.get("_title_text")
	_expect(title.get_parent().get_rect() == PREVIEW and title.horizontal_alignment == HORIZONTAL_ALIGNMENT_CENTER and title.vertical_alignment == VERTICAL_ALIGNMENT_CENTER, "Monologue text is centered inside its separate black preview.")


func _portrait_controls(scene: Control, route: String) -> void:
	var fixed_ui: Vector2 = scene.get("_return_button").position
	for guest: Dictionary in scene.content["guests"]:
		await _click(scene.get("_guest_buttons")[str(guest["id"])])
		scene.call("_process", 2.125)
		var rect: Rect2 = scene.call("presented_background_rect")
		_expect(rect.grow(0.01).encloses(Rect2(Vector2.ZERO, PREVIEW.size)), route + " keeps the background covered.")
		_expect(scene.get("_return_button").position == fixed_ui, route + " keeps host UI fixed.")
		var actor: TextureRect = scene.get("_actor")
		var halo = scene.get("_halo")
		_expect(halo.get_source_rect().is_equal_approx(Rect2(actor.position, actor.size)), route + " halo uses the full displayed sprite rectangle.")
		var base: Rect2 = scene.get("_base_portrait")
		var background_base: Rect2 = scene.get("_base_background")
		_expect((actor.position - base.position).distance_to(rect.position - background_base.position) < 0.001, "Portrait and background receive the same drift offset once.")
		if route == "drift_study":
			_expect(not halo.visible, "The isolated drift study does not also enable halo.")
	if route == "drift_study":
		await _click(scene.get("_pause_button"))
		var before: Vector2 = scene.get("_actor").position
		scene.call("_process", 1.0)
		_expect(scene.get("_actor").position == before, "Drift pause holds the visible frame.")
		scene.call("_clear_drift")
		_expect(scene.get("_world_offset") == Vector2.ZERO, "Clear removes drift.")
	else:
		await _click(scene.get("_halo_toggle"))
		_expect(not scene.get("_halo").visible and scene.get("_actor").visible, "Halo toggle disables glow while preserving the sprite.")
		await _click(scene.get("_halo_toggle"))
	# Captures use the same approved default guest, with the effects at rest or held.
	await _click(scene.get("_guest_buttons")[str(scene.content["default_guest_id"])])
	if route == "drift_study":
		scene.call("_process", 2.125)
		await _click(scene.get("_pause_button"))


func _dedicated_profile_binding(content: Dictionary) -> void:
	# Exercise the optional binding with an already approved texture. This local
	# test profile does not activate the pending dedicated asset in the game root.
	var fixture := content.duplicate(true)
	var profile: Dictionary = fixture["guests"][0]
	profile["detail_path"] = profile["path"]
	profile["detail_height"] = 980.0
	profile["detail_y"] = -135.0
	fixture["default_guest_id"] = profile["id"]
	for override_y: bool in [false, true]:
		if override_y:
			profile["study_detail_y"] = -175.0
		var scene = _make_scene("halo_study", fixture)
		if scene == null:
			continue
		var rect: Rect2 = scene.get("_base_portrait")
		_expect(is_equal_approx(rect.size.y, 980.0), "Dedicated profile supplies its logical height.")
		_expect(is_equal_approx(rect.get_center().x, PREVIEW.size.x * 0.5), "Dedicated profile centers the full texture in the preview.")
		_expect(is_equal_approx(rect.position.y, -175.0 if override_y else -135.0), "study_detail_y overrides detail_y only inside the study.")
		_expect(scene.get("_actor").texture == scene.get("_guest_detail_textures")[str(profile["id"])], "Dedicated source takes priority over fallback eye and standing textures.")
		scene.free()


func _click(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The requested review control is visible and enabled.")
	if button == null:
		return
	var point: Vector2 = root.get_final_transform() * button.get_global_rect().get_center()
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.global_position = point
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _settle() -> void:
	for index in 3:
		await process_frame


func _capture(name: String) -> void:
	if not _capture_enabled:
		return
	await RenderingServer.frame_post_draw
	_expect(DirAccess.make_dir_recursive_absolute(CAPTURES) == OK, "Capture directory must be writable.")
	var image := root.get_texture().get_image()
	_expect(image.get_size() == root.size, "Evidence must render at the actual native window resolution.")
	_expect(image.save_png(CAPTURES.path_join(name + ".png")) == OK, "Native study capture must save: " + name)
