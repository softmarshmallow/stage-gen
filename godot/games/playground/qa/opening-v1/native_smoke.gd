extends SceneTree

## Historical P32-P35 checks, superseded by qa/opening-loop/native_smoke.gd.
## These assert the former auto-continue behavior. Invoke once per variant, then
## once with --route game to verify the explicit bypass on a fresh launch.
const FOLDER := "res://qa/opening-v1"
const MAX_PLAYBACK_SECONDS := 35.0
var app: Control
var errors: Array[String] = []
var observations: Dictionary = {}
var finished_count := 0
var variant := "a"


func _initialize() -> void:
	_run.call_deferred()


func _expect(ok: bool, detail: String) -> void:
	if not ok:
		errors.append(detail)


func _settle() -> void:
	for index in 3:
		await process_frame


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Opening media checks require the native renderer; use --check-only for parsing.")
		quit(2)
		return
	if DirAccess.make_dir_recursive_absolute(FOLDER) != OK:
		printerr("Could not create opening evidence directory.")
		quit(2)
		return
	root.size = Vector2i(1280, 900)
	app = load("res://main.tscn").instantiate()
	root.add_child(app)
	app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	variant = str(app.options.get("opening-variant", "a"))
	observations = {"variant": variant, "renderer": DisplayServer.get_name(), "captures": [], "skips": []}
	await _settle()
	if app.options.get("route", "opening") == "game":
		_expect_first_beat("Explicit --route game")
		_expect(app.active_scene.get("_player") == null, "Direct game must have no opening player.")
		observations["direct_game_bypass"] = true
		_write_result("direct-game")
		return
	_expect(app.current_route == "opening", "Fresh launch must begin with the selected opening.")
	if app.current_route != "opening":
		_write_result(variant)
		return
	var opening: Control = app.active_scene
	var player: VideoStreamPlayer = opening.get("_player")
	if player == null:
		_expect(false, "Selected final video must exist and create a native player.")
		_write_result(variant)
		return
	var expected_path := "res://assets/opening/title%s.ogv" % ("_b" if variant == "b" else "")
	_expect(opening.video_path == expected_path, "Variant must select its own file.")
	_expect(player.volume_db <= -80.0, "Opening must preserve muted playback.")
	observations["video_path"] = expected_path
	observations["video_sha256"] = FileAccess.get_sha256(expected_path)
	player.finished.connect(func() -> void: finished_count += 1)
	var began := Time.get_ticks_msec()
	var sampled_start := false
	var sampled_title := false
	var max_position := 0.0
	while app.current_route == "opening" and float(Time.get_ticks_msec() - began) / 1000.0 < MAX_PLAYBACK_SECONDS:
		max_position = maxf(max_position, player.stream_position)
		if not sampled_start and player.stream_position >= 1.1:
			sampled_start = true
			var frame := player.get_video_texture()
			_expect(frame != null and frame.get_width() == 1920 and frame.get_height() == 1080, "Native player must decode a 1920x1080 frame.")
			_expect(player.size.is_equal_approx(Vector2(1280, 720)) and player.position.is_equal_approx(Vector2(0, 90)), "Video must fit the fixed canvas without stretching or cropping.")
			var buttons: Array[Button] = []
			for child in opening.get_children():
				if child is Button:
					buttons.append(child)
			_expect(buttons.size() == 1, "Opening must expose exactly one button.")
			if buttons.size() == 1:
				_expect(buttons[0].get_rect().position.y >= 810.0 and buttons[0].get_rect().end.y <= 900.0, "Begin Briefing must stay entirely in the lower letterbox.")
			observations["decoded_dimensions"] = [frame.get_width(), frame.get_height()] if frame != null else []
			observations["first_sample_seconds"] = player.stream_position
			await _capture(variant + "-playback")
		if not sampled_title and is_instance_valid(player) and player.stream_position >= 20.5:
			sampled_title = true
			observations["title_sample_seconds"] = player.stream_position
			await _capture(variant + "-title")
		await create_timer(0.1).timeout
	await _settle()
	var elapsed := float(Time.get_ticks_msec() - began) / 1000.0
	observations["playback_elapsed_seconds"] = elapsed
	observations["max_stream_position"] = max_position
	observations["finished_signal_count"] = finished_count
	_expect(sampled_start and max_position >= 15.0, "Final clip must decode and progress for at least fifteen seconds.")
	_expect(finished_count == 1, "Natural playback must emit exactly one real finished signal.")
	_expect(elapsed < MAX_PLAYBACK_SECONDS, "Natural playback must complete within its bounded timeout.")
	_expect_first_beat("Natural completion")
	if app.current_route != "game":
		_write_result(variant)
		return
	for key in [KEY_ENTER, KEY_SPACE, KEY_ESCAPE]:
		await _restart_opening()
		_key(key, true, true)
		_key(key, false)
		await _settle()
		_expect(app.current_route == "opening", "Repeated key must not skip the opening.")
		_key(key, true)
		_key(key, false)
		await _settle()
		_expect_first_beat("Keyboard skip %s" % key)
		observations["skips"].append({"kind": "key", "keycode": key, "route": app.current_route})
	for point in [Vector2(1126, 855), Vector2(900, 300)]:
		await _restart_opening()
		for pressed: bool in [true, false]:
			var click := InputEventMouseButton.new()
			click.button_index = MOUSE_BUTTON_LEFT
			click.position = point
			click.global_position = point
			click.pressed = pressed
			root.push_input(click, true)
		await _settle()
		_expect_first_beat("Pointer skip")
		observations["skips"].append({"kind": "pointer", "point": [point.x, point.y], "route": app.current_route})
	await _restart_opening()
	for pressed: bool in [true, false]:
		var touch := InputEventScreenTouch.new()
		touch.position = Vector2(800, 350)
		touch.pressed = pressed
		root.push_input(touch, true)
	await _settle()
	_expect_first_beat("Touch skip")
	observations["skips"].append({"kind": "touch", "route": app.current_route})
	_write_result(variant)


func _restart_opening() -> void:
	app.game_state.clear()
	# Leaving a game captures its state; the preceding checks ensure that state
	# is still the first beat, so any leaked skip input remains observable.
	app.open_route("opening")
	await _settle()
	_expect(app.current_route == "opening", "Selected variant must reopen for input checks.")


func _key(code: int, pressed: bool, repeated: bool = false) -> void:
	var event := InputEventKey.new()
	event.keycode = code
	event.pressed = pressed
	event.echo = repeated
	root.push_input(event, true)


func _expect_first_beat(context: String) -> void:
	_expect(app.current_route == "game", context + " must enter the game.")
	if app.current_route == "game":
		_expect(app.active_scene.get("_story_id") == "arrival", context + " must preserve the first story beat.")


func _capture(name: String) -> void:
	# Background native windows may defer frame_post_draw until foregrounded.
	# Force the evidence frame synchronously so the player cannot finish while
	# this test is suspended waiting for a window redraw.
	RenderingServer.force_draw()
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == Vector2i(1280, 900), "Native capture must use the fixed logical viewport.")
	var path := FOLDER.path_join(name + ".png")
	_expect(picture.save_png(path) == OK, "Could not save native capture " + name)
	observations["captures"].append(path)


func _write_result(name: String) -> void:
	observations["errors"] = errors
	var file := FileAccess.open(FOLDER.path_join(name + ".json"), FileAccess.WRITE)
	if file == null:
		printerr("Could not write opening smoke results.")
		quit(2)
		return
	file.store_string(JSON.stringify(observations, "\t"))
	for issue in errors:
		printerr("FAIL opening " + name + ": " + issue)
	if errors.is_empty():
		print("PASS opening " + name + ": native media playback or explicit bypass, original story entry, and requested input checks.")
	quit(0 if errors.is_empty() else 1)
