extends SceneTree

## Native evidence for a looping title that advances only on a click or tap.
const FOLDER := "res://tests/opening-loop"
const MAX_PLAYBACK_SECONDS := 35.0
var app: Control
var errors: Array[String] = []
var observations: Dictionary = {"captures": [], "input_checks": []}
var finished_count := 0
var missing_navigation_count := 0
var variant := "a"


func _initialize() -> void:
	_run.call_deferred()


func _expect(ok: bool, detail: String) -> void:
	if not ok:
		errors.append(detail)


func _settle() -> void:
	for index in 4:
		await process_frame


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Opening loop media checks require the native renderer.")
		quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(FOLDER) != OK:
		printerr("Could not create opening loop evidence directory.")
		quit(2)
		return
	root.size = Vector2i(1280, 900)
	app = load("res://main.tscn").instantiate()
	root.add_child(app)
	app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(app.current_route == "opening", "Fresh launch must begin with the opening.")
	if app.current_route != "opening":
		_write_result()
		return
	var opening: Control = app.active_scene
	var player: VideoStreamPlayer = opening.get("_player")
	if player == null:
		_expect(false, "Selected video must create a native player.")
		_write_result()
		return
	observations["renderer"] = DisplayServer.get_name()
	variant = str(app.options.get("opening-variant", "a"))
	observations["variant"] = variant
	observations["video_path"] = opening.video_path
	observations["video_sha256"] = FileAccess.get_sha256(opening.video_path)
	_expect(player.volume_db <= -80.0, "The visual opening must remain muted.")
	_expect(player.loop, "The player must enable native continuous looping.")
	var duration := float(opening.get("_duration_seconds"))
	observations["duration_seconds"] = duration
	var buttons := _buttons(opening)
	_expect(buttons.size() == 1, "Opening must expose exactly one Begin Briefing button.")
	if buttons.size() == 1:
		_expect(buttons[0].focus_mode == Control.FOCUS_NONE, "Begin Briefing must not receive keyboard focus.")
	for key in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE, KEY_ESCAPE]:
		_key(key, true)
		_key(key, false)
		await _settle()
		_expect(app.current_route == "opening", "Keyboard input must not advance the opening.")
		observations["input_checks"].append({"kind": "ignored_key", "keycode": key, "route": app.current_route})
	for pressed: bool in [true, false]:
		var right_click := InputEventMouseButton.new()
		right_click.button_index = MOUSE_BUTTON_RIGHT
		right_click.position = Vector2(900, 300)
		right_click.pressed = pressed
		root.push_input(right_click, true)
	await _settle()
	_expect(app.current_route == "opening", "Right-click must not advance the opening.")
	observations["input_checks"].append({"kind": "ignored_right_click", "route": app.current_route})
	if app.current_route != "opening":
		_write_result()
		return
	player.finished.connect(func() -> void: finished_count += 1)
	var began := Time.get_ticks_msec()
	var max_position := 0.0
	var minimum_end_alpha := 1.0
	var first_cycle_progress := false
	var saw_restart := false
	var saw_recovery := false
	var captured_end := false
	var previous_position := 0.0
	while app.current_route == "opening" and float(Time.get_ticks_msec() - began) / 1000.0 < MAX_PLAYBACK_SECONDS:
		var position := player.stream_position
		max_position = maxf(max_position, position)
		if position >= 1.0 and not first_cycle_progress:
			first_cycle_progress = true
			var frame := player.get_video_texture()
			_expect(frame != null and frame.get_width() == 1920 and frame.get_height() == 1080, "Native player must decode the selected 1080p clip.")
			_expect(player.size.is_equal_approx(Vector2(1280, 720)) and player.position.is_equal_approx(Vector2(0, 90)), "Video must preserve its fixed-canvas aspect fit.")
			await _capture("first-cycle")
		if position > duration - 1.0 and not saw_restart:
			minimum_end_alpha = minf(minimum_end_alpha, player.modulate.a)
			if player.modulate.a < 0.2 and not captured_end:
				captured_end = true
				observations["end_fade_sample"] = {"seconds": position, "alpha": player.modulate.a}
				await _capture("end-fade")
		if previous_position > duration - 1.0 and position < 1.0:
			saw_restart = true
		if saw_restart and position >= 1.0 and player.modulate.a > 0.95:
			saw_recovery = true
			observations["second_cycle_sample"] = {"seconds": position, "alpha": player.modulate.a}
			await _capture("second-cycle")
			break
		previous_position = position
		await create_timer(0.035).timeout
	observations["playback_elapsed_seconds"] = float(Time.get_ticks_msec() - began) / 1000.0
	observations["max_stream_position"] = max_position
	observations["minimum_end_alpha"] = minimum_end_alpha
	observations["finished_signal_count"] = finished_count
	observations["second_cycle_started"] = saw_restart
	observations["second_cycle_recovered"] = saw_recovery
	_expect(first_cycle_progress and max_position >= duration - 0.5, "The selected opening must play its whole first cycle.")
	_expect(minimum_end_alpha < 0.1, "The end of the first cycle must fade almost completely to black.")
	_expect(saw_restart and saw_recovery, "Natural completion must restart the clip and recover its opacity.")
	_expect(app.current_route == "opening" and not opening.get("_leaving"), "A completed loop must never enter the story automatically.")
	if app.current_route != "opening":
		_write_result()
		return
	for point in [Vector2(1126, 855), Vector2(900, 300)]:
		await _restart_opening()
		_pointer(point)
		await _settle()
		_expect_first_beat("Click")
		observations["input_checks"].append({"kind": "click", "point": [point.x, point.y], "route": app.current_route})
	await _restart_opening()
	for pressed: bool in [true, false]:
		var touch := InputEventScreenTouch.new()
		touch.position = Vector2(800, 350)
		touch.pressed = pressed
		root.push_input(touch, true)
	await _settle()
	_expect_first_beat("Tap")
	observations["input_checks"].append({"kind": "tap", "route": app.current_route})
	await _missing_media()
	_write_result()


func _restart_opening() -> void:
	app.game_state.clear()
	app.open_route("opening")
	await _settle()
	_expect(app.current_route == "opening", "Opening must reopen for input checks.")


func _missing_media() -> void:
	root.remove_child(app)
	app.queue_free()
	await _settle()
	var missing: Control = load("res://presentation/opening.gd").new()
	missing.video_path = "res://tests/opening-loop/intentionally-missing.ogv"
	missing.navigate.connect(func(_route_id: String) -> void: missing_navigation_count += 1)
	root.add_child(missing)
	missing.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await create_timer(2.3).timeout
	_expect(missing_navigation_count == 0 and not missing.get("_leaving"), "Missing media must remain on the title until an explicit click.")
	var buttons := _buttons(missing)
	_expect(buttons.size() == 1, "Missing media must retain the Begin Briefing button.")
	_key(KEY_ENTER, true)
	_key(KEY_ENTER, false)
	await _settle()
	_expect(missing_navigation_count == 0, "Missing media must also ignore keyboard entry.")
	await _capture("missing-media")
	_pointer(Vector2(1126, 855))
	await _settle()
	_expect(missing_navigation_count == 1, "An explicit click must leave the missing-media title exactly once.")
	observations["missing_media"] = {"button_count": buttons.size(), "navigation_count_after_click": missing_navigation_count}


func _buttons(parent: Node) -> Array[Button]:
	var found: Array[Button] = []
	for child in parent.get_children():
		if child is Button:
			found.append(child)
	return found


func _key(code: int, pressed: bool) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = pressed
	root.push_input(event, true)


func _pointer(point: Vector2) -> void:
	for pressed: bool in [true, false]:
		var click := InputEventMouseButton.new()
		click.button_index = MOUSE_BUTTON_LEFT
		click.position = point
		click.global_position = point
		click.pressed = pressed
		root.push_input(click, true)


func _expect_first_beat(context: String) -> void:
	_expect(app.current_route == "game", context + " must enter the game.")
	if app.current_route == "game":
		_expect(app.active_scene.get("_story_id") == "arrival", context + " must preserve the first story beat.")


func _capture(name: String) -> void:
	RenderingServer.force_draw()
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == Vector2i(1280, 900), "Native evidence must use the fixed logical viewport.")
	var path := FOLDER.path_join(variant + "-" + name + ".png")
	_expect(picture.save_png(path) == OK, "Could not save native capture " + name)
	observations["captures"].append(path)


func _write_result() -> void:
	observations["errors"] = errors
	var file := FileAccess.open(FOLDER.path_join(variant + ".json"), FileAccess.WRITE)
	if file == null:
		printerr("Could not write opening loop smoke results.")
		quit(2)
		return
	file.store_string(JSON.stringify(observations, "\t"))
	for issue in errors:
		printerr("FAIL opening loop: " + issue)
	if errors.is_empty():
		print("PASS opening loop: native fade and restart, click-only story entry, ignored keys, and missing-media fallback.")
	quit(0 if errors.is_empty() else 1)
