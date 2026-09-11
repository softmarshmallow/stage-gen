extends SceneTree

## Focused P84 story/laboratory evidence, without replaying the complete episode.
## Godot --path godot/games/playground --script res://qa/waking_eye_integration_checks.gd -- --game bishoujo_afterlight
## Add --capture-waking on a native renderer for 1x/2x story and laboratory frames.
const DESIGN_SIZE := Vector2(1280, 900)
const CAPTURE_DIRECTORY := "res://qa/waking-eye"
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-waking")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Waking Eye captures require a native renderer.")
		quit(2)
		return
	root.size = Vector2i(DESIGN_SIZE)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "bishoujo_afterlight", "Run this fixture with --game bishoujo_afterlight.")
	_expect(_active()._load_errors.is_empty(), "The authored episode must initialize: " + str(_active()._load_errors))
	if _errors.is_empty():
		await _story_pause_and_checkpoint()
		for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
			root.size = window_size
			await _story_frames(window_size)
			await _laboratory(window_size)
	_app.queue_free()
	_app = null
	for frame in 3: await process_frame
	for issue: String in _errors: printerr("FAIL Waking Eye Integration: " + issue)
	if _errors.is_empty():
		print("PASS Waking Eye Integration: authored waking beat, partial peek/reclosure/final opening, paused and bilingual checkpoints in each active phase, isolated lab timing/reset, all four modes and physical controls, native 1x/2x frames when enabled")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)


func _active() -> Control:
	return _app.active_scene


func _freeze_route(node: Node) -> void:
	if _app != null and node == _app.get("active_scene"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _active() != null: _active().set_process(false)


func _key(code: Key) -> void:
	for pressed: bool in [true, false]:
		var event := InputEventKey.new()
		event.keycode = code
		event.pressed = pressed
		root.push_input(event)
	await _settle()


func _click(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The intended route action must be visible and enabled.")
	if button == null or not button.is_visible_in_tree() or button.disabled: return
	var physical := root.get_final_transform() * button.get_global_rect().get_center()
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = physical
		event.global_position = physical
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _bound_button(scene: Control, key: String, field: String, parent: Node = null) -> Button:
	for binding: Dictionary in scene.get(field):
		if binding["key"] == key and binding["node"] is Button:
			var button: Button = binding["node"]
			if parent == null or parent.is_ancestor_of(button): return button
	_expect(false, "A bound action must exist: " + key)
	return null


func _eye_pose(scene: Control) -> Dictionary:
	return scene.get("_eye").sample()


func _same_pose(first: Dictionary, second: Dictionary) -> bool:
	for field: String in ["openness", "elapsed", "progress", "total_seconds"]:
		if absf(float(first[field]) - float(second[field])) > 0.00001: return false
	return first["phase"] == second["phase"] and first["active"] == second["active"] and first["reached_closed"] == second["reached_closed"]


func _reach_opening() -> Control:
	_expect(_app.open_route("game:bishoujo_afterlight/new_game"), "A new Afterlight episode must open.")
	await _settle()
	for action in 8:
		if _active().current_beat()["id"] == "eyes_on_nami": break
		await _key(KEY_SPACE)
	var game := _active()
	_expect(game.current_beat()["id"] == "eyes_on_nami", "Ordinary reveal and continue inputs must reach the first portrait opening.")
	_expect(game.current_beat().get("eye_mode") == "waking_opening" and game._eye.get_state()["mode"] == "waking_opening", "The first Nami portrait must explicitly select the new waking mode.")
	_expect(is_equal_approx(float(_eye_pose(game)["total_seconds"]), 2.64), "The authored waking beat must retain its full 2.2-second final opening after the brief preliminary blink.")
	_expect(game._portrait.visible and not game._cast.visible and is_zero_approx(float(_eye_pose(game)["openness"])), "The close portrait must be prepared beneath the initially closed mask.")
	return game


func _story_pause_and_checkpoint() -> void:
	for checkpoint: Dictionary in [{"time": 0.11, "phase": "peeking"}, {"time": 0.29, "phase": "closing"}, {"time": 0.40, "phase": "closed"}, {"time": 1.1, "phase": "opening"}]:
		var game: Control = await _reach_opening()
		game._process(float(checkpoint["time"]))
		_expect(_eye_pose(game)["phase"] == checkpoint["phase"], "Story timing must reach the expected waking phase: " + str(checkpoint["phase"]))
		var before := _eye_pose(game)
		var portrait: Rect2 = game._portrait.get_rect()
		var background: Rect2 = game.presented_background_rect()
		await _key(KEY_ESCAPE)
		_expect(game._paused and game._pause_menu.visible, "Escape must expose the host menu during every waking phase.")
		game._process(3.0)
		_expect(_same_pose(before, _eye_pose(game)), "Pause must stop the waking clock without settling the mask.")
		await _click(_bound_button(game, "ui.language_target", "_ui_bindings", game._pause_menu))
		_expect(game.get_language() == "ko" and _same_pose(before, _eye_pose(game)), "The menu language action must preserve the exact paused eye frame.")
		var saved: Dictionary = game.save_game()
		await _click(_bound_button(game, "episode.ui.lab", "_ui_bindings", game._pause_menu))
		_expect(_app.selected_game_id == "presentation_lab", "The pause menu must reach the independently owned laboratory.")
		_expect(_app._game_states["bishoujo_afterlight"] == saved, "The menu detour must preserve the current narrative checkpoint.")
		await _click(_active()._story_buttons["bishoujo_afterlight"])
		game = _active()
		_expect(game._load_errors.is_empty() and game.current_beat()["id"] == "eyes_on_nami" and not game._paused, "Returning must resume the same playable waking beat.")
		_expect(game.get_language() == "ko" and _same_pose(before, _eye_pose(game)), "Checkpoint reconstruction must preserve Korean text and the exact preliminary/final opening phase.")
		_expect(game._portrait.get_rect().is_equal_approx(portrait) and game.presented_background_rect().is_equal_approx(background), "Checkpoint restoration must preserve the portrait and background framing.")
		game._process(0.03125)
		_expect(float(_eye_pose(game)["elapsed"]) > float(before["elapsed"]), "The reconstructed eye transition must resume advancing normally.")
		_expect(game.set_language("en").is_empty(), "Restore English for the next independent checkpoint fixture.")


func _story_frames(window_size: Vector2i) -> void:
	var game: Control = await _reach_opening()
	_expect(game.size.is_equal_approx(DESIGN_SIZE) and root.content_scale_mode == Window.CONTENT_SCALE_MODE_CANVAS_ITEMS, "Waking shots must retain logical framing with native-resolution rendering.")
	var sample_time := 0.0
	for shot: Dictionary in [{"time": 0.20, "label": "peek", "phase": "peeking"}, {"time": 0.40, "label": "closed", "phase": "closed"}, {"time": 1.20, "label": "reopening", "phase": "opening"}, {"time": 2.64, "label": "open", "phase": "open"}]:
		game._process(float(shot["time"]) - sample_time)
		sample_time = float(shot["time"])
		_expect(_eye_pose(game)["phase"] == shot["phase"], "The authored portrait capture must represent " + str(shot["phase"]) + ".")
		_expect(game.current_beat()["id"] == "eyes_on_nami", "Completing eye animation must hold the current beat for explicit continuation.")
		await _capture("story-" + str(shot["label"]) + "-" + str(window_size.x), shot["phase"] == "closed")
	_expect(game._dialogue.visible and game._cinematic_complete(), "Dialogue must become visible only after the full waking sequence completes.")
	await _key(KEY_SPACE)
	_expect(game.current_beat()["id"] == "no_ordinary_post", "A subsequent explicit input must continue to the next authored beat.")
	game = await _reach_opening()
	game._process(0.10)
	await _key(KEY_SPACE)
	_expect(game.current_beat()["id"] == "eyes_on_nami" and game._cinematic_complete() and is_equal_approx(float(_eye_pose(game)["openness"]), 1.0), "One cinematic skip must finish the waking mask without skipping its dialogue beat.")


func _laboratory(window_size: Vector2i) -> void:
	var story := _active()
	var saved: Dictionary = story.save_game()
	_expect(_app.open_route("game:presentation_lab/eye_study"), "The independent eye laboratory must be reachable.")
	await _settle()
	var study := _active()
	_expect(study._load_errors.is_empty(), "The eye laboratory must load its prepared portrait and controls: " + str(study._load_errors))
	if not study._load_errors.is_empty(): return
	_expect(study._selected_mode == "waking_opening" and study._mode_buttons.size() == 4, "The study must start with Waking Eye-Opening and retain all original modes.")
	var sliders: Dictionary = study._eye_sliders
	_expect(sliders.size() == 5 and sliders.has("peek_seconds") and sliders.has("peek_openness"), "The study must expose independently authored peek timing and depth.")
	for field: String in sliders:
		_expect(is_equal_approx(sliders[field].value, float(study.content["eye_transition"][field])), "A study timing control must match root configuration before any replay: " + field)
	var before: Dictionary = study._eye.get_state()
	sliders["peek_seconds"].value = 0.6
	sliders["peek_openness"].value = 0.7
	_expect(study._eye.get_state()["active_settings"] == before["active_settings"] and is_equal_approx(float(study._eye.get_state()["elapsed"]), float(before["elapsed"])), "Changing peek controls must leave the active cue's timing and depth unchanged.")
	await _click(study._replay_button)
	study._process(float(study._eye.get_settings()["peek_seconds"]))
	_expect(is_equal_approx(float(_eye_pose(study)["openness"]), 0.7) and _eye_pose(study)["phase"] == "closing", "Replay must apply the separately configured peek duration and depth.")
	var tuning_state: Dictionary = study._eye.get_state()
	study._softness_slider.value = 50.0
	_expect(study._eye.get_state() == tuning_state, "Live feather tuning must not retime or restart waking motion.")
	await _click(_bound_button(study, "ui.reset", "_text_bindings"))
	for field: String in sliders:
		_expect(is_equal_approx(sliders[field].value, float(study.content["eye_transition"][field])), "Reset must restore every authored waking field: " + field)
	_expect(is_equal_approx(float(study._eye_material.get_shader_parameter("edge_softness")), 28.0), "Reset must preserve the authored soft eyelid edge.")
	_expect(_app._game_states["bishoujo_afterlight"] == saved, "Lab tuning must not mutate the suspended story checkpoint.")
	for mode: String in ["eye_opening", "eye_closing", "blink", "waking_opening"]:
		await _click(study._mode_buttons[mode])
		_expect(study._selected_mode == mode and study._eye.is_active(), "A physical study button must start its selected mode at " + str(window_size) + ": " + mode)
		await _click(study._skip_button)
		_expect(not study._eye.is_active() and is_equal_approx(float(_eye_pose(study)["openness"]), 0.0 if mode == "eye_closing" else 1.0), "Skip must preserve the correct original/new mode endpoint: " + mode)
		await _click(study._replay_button)
		_expect(is_zero_approx(float(_eye_pose(study)["elapsed"])), "Physical replay must restart the selected eye mode.")
	study._process(0.2)
	await _capture("lab-peek-" + str(window_size.x))
	study._process(0.2)
	await _capture("lab-closed-" + str(window_size.x))
	study._process(0.8)
	await _capture("lab-reopening-" + str(window_size.x))
	await _click(study._skip_button)
	await _capture("lab-open-" + str(window_size.x))
	await _click(study._return_button)
	_expect(_app.selected_game_id == "bishoujo_afterlight" and _active().save_game() == saved, "Returning from tuned study must restore the story checkpoint unchanged.")


func _capture(label: String, closed_story: bool = false) -> void:
	if not _capture_enabled: return
	_expect(DirAccess.make_dir_recursive_absolute(CAPTURE_DIRECTORY) == OK, "The focused waking capture directory must be writable.")
	await _settle()
	RenderingServer.force_draw(false)
	await process_frame
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Waking evidence must render at the actual native window size.")
	if closed_story:
		var center := picture.get_pixel(picture.get_width() / 2, picture.get_height() / 2)
		_expect(maxf(center.r, maxf(center.g, center.b)) < 0.01, "The waking reclosure must fully mask the central portrait before its final opening.")
	_expect(picture.save_png(CAPTURE_DIRECTORY.path_join(label + ".png")) == OK, "Native waking capture must save: " + label)
