extends SceneTree

# Native checks may run while the user works in another game. Only this test's
# tagged events enter the temporary test window; normal play has no such filter.
class TestInput extends Node:
	var ignored_presses := 0
	func _input(event: InputEvent) -> void:
		if event.device != 777:
			if event.is_pressed(): ignored_presses += 1
			get_viewport().set_input_as_handled()

var failures: Array[String] = []
var captures: Array[String] = []


func _init() -> void:
	_run.call_deferred()


func check(value: bool, message: String) -> void:
	if not value: failures.append(message)


func _run() -> void:
	if "--capture" in OS.get_cmdline_user_args() and DisplayServer.get_name() == "headless":
		push_error("Capture requires a native renderer.")
		quit(1)
		return
	root.size = Vector2i(2560, 1800) if "--scale-2" in OS.get_cmdline_user_args() else Vector2i(1280, 900)
	var input_filter := TestInput.new()
	root.add_child(input_filter)
	var scene := load("res://main.tscn") as PackedScene
	if scene == null:
		push_error("Starter scene could not be loaded.")
		quit(1)
		return
	var game = scene.instantiate()
	root.add_child(game)
	await process_frame
	game.set_process(false)
	check(game.errors.is_empty(), "Bootstrap configures without external media.")
	check(game.beat_index == 0 and game._reveal.sample()["phase"] == "revealing", "Starts with intertitle reveal.")
	game.advance_story()
	check(game.beat_index == 0 and game._reveal.sample()["phase"] == "holding", "First advance reveals only.")
	game.advance_story()
	check(game.beat_index == 1, "Second input continues to welcome.")
	game._process(0.3)
	var before: Dictionary = game._camera.sample()
	game.toggle_pause()
	game._process(10)
	check(game._camera.sample() == before, "Pause freezes camera and world clock.")
	game.toggle_pause()
	game._process(0.5)
	check(float(game._camera.sample()["zoom"]) > 1, "Welcome uses directed camera.")
	await capture("welcome")
	for option: String in ["light", "note"]:
		game.restart()
		for beat in 2:
			game.advance_story()
			game.advance_story()
		check(game.beat_index == 2, "Reached the choice.")
		game.choose(option)
		check(game.beat_index == 2, "Choice cannot bypass text reveal.")
		game.advance_story()
		game.advance_story()
		check(game.beat_index == 2 and game._choices[0].visible, "Choice waits for a real option.")
		if option == "light": await capture("choice")
		await click(game._choices[0 if option == "light" else 1].get_global_rect().get_center())
		check(game.choice_id == option and game.beat_index == 3, "Both authored replies are selectable.")
		check(game._reveal.sample()["text"] == game.WORDS["reply_" + option], "Reply matches the selected path.")
		game._process(0.41)
		check(float(game._manpu.sample("mara", "glint")["rotation_degrees"]) == 30, "Stepped Manpu loop is active.")
		check(game._mark.visible, "Manpu is presented by the host.")
		game.advance_story()
		game.advance_story()
		check(game.beat_index == 4, "Replies reconverge on contact.")
		var target: Dictionary = game.contact_target()
		check(not game.try_contact(target["center"]), "Contact is locked during reveal.")
		game.advance_story()
		game._process(0.7)
		game.advance_story()
		check(game.beat_index == 4, "Keyboard-style advance cannot confirm contact.")
		check(not game.try_contact(Vector2.ZERO), "Outside input cannot confirm contact.")
		if option == "light": await capture("contact")
		target = game.contact_target()
		game.toggle_pause()
		check(not game.try_contact(target["center"]), "Paused contact remains locked.")
		game.toggle_pause()
		await click(target["center"])
		check(game._contact.is_confirmed(), "Native pointer confirms the current transformed target.")
		check(not game.try_contact(target["center"]), "Duplicate contact cannot reset feedback.")
		check(game._burst.get_state().size() == 1, "Contact emits one sprite burst.")
		game._process(0.2)
		var contact_time: float = game._contact_seconds
		game.toggle_pause()
		game._process(3)
		check(game._contact_seconds == contact_time, "Pause holds contact feedback.")
		game.toggle_pause()
		game._process(0.46)
		check(game.beat_index == 5, "Acknowledged feedback continues exactly once.")
		game.advance_story()
		game.advance_story()
		game.advance_story()
		game.advance_story()
		check(game.beat_index == 6 and game._restart_button.visible, "Ending holds without automatic restart.")
	check(game.errors.is_empty(), "Full story has no runtime diagnostics.")
	var other = scene.instantiate()
	other.welcome_voice = game.TEXT_AUDIO.create_default_typing_stream()
	root.add_child(other)
	await process_frame
	other.set_process(false)
	other.advance_story()
	other.advance_story()
	check(other._audio.get_state()["active_mode"] == "voice", "Supplied voice wins over typing.")
	check(other._reveal.sample()["phase"] == "holding", "Ready voice displays complete subtitles.")
	other.advance_story()
	check(other._audio.get_state()["active_mode"] == "typing", "Advancing stops the old voice.")
	check(game.beat_index == 6, "A second host has independent state.")
	other.queue_free()
	game.queue_free()
	await process_frame
	# Let the audio server consume its deferred stop/free commands before exit.
	await create_timer(0.15).timeout
	var report := {"passed": failures.is_empty(), "errors": failures, "captures": captures,
		"ignored_external_presses": input_filter.ignored_presses}
	print(JSON.stringify(report))
	if failures.is_empty(): print("PASS starter: both replies, required contact, camera, Manpu, burst, pause, audio and instance isolation.")
	for message: String in failures: push_error(message)
	quit(0 if failures.is_empty() else 1)


func capture(label: String) -> void:
	if "--capture" not in OS.get_cmdline_user_args(): return
	await process_frame
	await RenderingServer.frame_post_draw
	var directory := "user://starter-checks"
	DirAccess.make_dir_recursive_absolute(directory)
	var suffix := "-2" if "--scale-2" in OS.get_cmdline_user_args() else "-1"
	var path := directory.path_join(label + suffix + ".png")
	var screenshot := root.get_texture().get_image()
	check(screenshot.save_png(path) == OK, "Capture writes successfully.")
	captures.append(ProjectSettings.globalize_path(path))


func click(logical_point: Vector2) -> void:
	var point := root.get_final_transform() * logical_point
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.device = 777
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.global_position = point
		event.pressed = pressed
		root.push_input(event, false)
	await process_frame
