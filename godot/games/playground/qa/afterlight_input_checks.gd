extends SceneTree

## Dispatch real viewport events through the episode-owned interface.
## --capture-input records dialogue, monologue and choice at native 1x/2x.
const DESIGN_SIZE := Vector2(1280, 900)
const DIRECTORY := "res://qa/afterlight-ensemble"
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false
var _capture_count := 0
var _replies := {}


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-input")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Afterlight input captures require a native renderer.")
		quit(2)
		return
	root.size = Vector2i(DESIGN_SIZE)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "bishoujo_afterlight", "Run with --game bishoujo_afterlight.")
	if _app.selected_game_id == "bishoujo_afterlight":
		await _input_at_size(Vector2i(1280, 900), "help_first")
		await _input_at_size(Vector2i(2560, 1800), "tea_first")
	_expect(_replies.size() == 2 and _replies.get("help_first") != _replies.get("tea_first"), "The two authored responses must differ before merging into the same episode.")
	for issue: String in _errors: printerr("FAIL Afterlight input: " + issue)
	if _errors.is_empty():
		print("PASS Afterlight input: background mouse/touch and keyboard gates, ready indicators, no Next or hint controls, explicit convergent choices, unresolved/resolved Lab checkpoints, Korean/English continuity and native 1x/2x layout")
		if _capture_count > 0: print("Afterlight input captures: " + str(_capture_count))
	quit(0 if _errors.is_empty() else 1)


func _input_at_size(window_size: Vector2i, option_id: String) -> void:
	root.size = window_size
	_app.open_route("new_game")
	await _settle()
	var game: Control = _app.active_scene
	_expect(game._load_errors.is_empty(), "The host must initialize for physical input.")
	if not game._load_errors.is_empty(): return
	game.set_language("ko")
	_expect(game.get("_next_button") == null and game.get("_monologue_hint") == null, "The story must remove its former Next button and monologue instruction.")
	_check_no_advance_labels(game)
	game._process(0.21)
	_expect(not game._monologue_dot.visible, "The monologue readiness dot must stay hidden during typing.")
	var fraction: float = game.save_game()["reveal_fraction"]
	var elapsed: float = game._elapsed
	await _key(KEY_F6)
	_expect(game.get_language() == "en" and is_equal_approx(float(game.save_game()["reveal_fraction"]), fraction), "F6 must preserve normalized reveal progress.")
	_expect(is_equal_approx(game._elapsed, elapsed), "Language changes must preserve world time.")
	await _key(KEY_F6)
	await _background_click()
	_expect(_id(game) == "undeliverable" and game._reveal.sample()["phase"] == "holding" and game._monologue_dot.visible, "One fullblack click must reveal text and show readiness without continuing.")
	await _capture("input-monologue-" + str(window_size.x))
	await _touch(Vector2(900, 300))
	_expect(_id(game) == "across_the_threshold", "One touch must continue the held monologue exactly once.")
	_expect(not game._ready_dot.visible and not game._dialogue.visible, "Readiness must stay hidden during the walking camera motion.")
	await _key(KEY_ESCAPE)
	_expect(game._paused and game._pause_menu.visible, "Escape must open the game menu.")
	elapsed = game._elapsed
	game._process(5.0)
	_expect(is_equal_approx(game._elapsed, elapsed), "The menu must freeze camera motion.")
	await _background_click()
	_expect(_id(game) == "across_the_threshold" and game._paused, "A menu-background click must not advance the episode.")
	await _key(KEY_ESCAPE)
	await _key(KEY_SPACE)
	_expect(_id(game) == "across_the_threshold" and game._cinematic_complete() and game._dialogue.visible and game._ready_dot.visible, "Space must finish walking and show its held text before continuing.")
	await _key(KEY_ENTER)
	_expect(_id(game) == "eyes_on_nami", "Enter must continue settled motion once.")
	await _touch(Vector2(900, 300))
	_expect(_id(game) == "eyes_on_nami" and game._cinematic_complete(), "Touch must settle the eye-opening mask before advancing.")
	await _key(KEY_SPACE)
	_expect(_id(game) == "no_ordinary_post" and not game._ready_dot.visible, "A new dialogue beat must begin with its readiness dot hidden.")
	await _background_click()
	_expect(_id(game) == "no_ordinary_post" and game._reveal.sample()["phase"] == "holding" and game._ready_dot.visible, "A background click must reveal dialogue without click-through.")
	game._process(0.8)
	await _capture("input-dialogue-" + str(window_size.x))
	await _key(KEY_ESCAPE)
	_expect(not game._ready_dot.visible, "Paused dialogue must hide its readiness dot.")
	await _key(KEY_ESCAPE)
	await _touch(Vector2(300, 780))
	_expect(_id(game) == "a_glass_record", "Touching the dialogue sheet must continue exactly one beat.")
	await _key(KEY_SPACE)
	_expect(_id(game) == "a_glass_record" and game._reveal.sample()["phase"] == "holding", "Space must reveal dialogue without activating the background twice.")
	await _key(KEY_ENTER)
	_expect(_id(game) == "no_forwarding_address", "Enter must continue the held dialogue exactly once.")
	await _background_click()
	await _background_click()
	_expect(_id(game) == "courier_offer" and game._choice_pending(), "The story must reach its authored choice without selecting an answer.")
	_expect(_visible_choices(game).is_empty() and not game._ready_dot.visible, "Choices must wait until their prompt finishes revealing.")
	game._choose("missing_option")
	_expect(game._choices.is_empty() and _id(game) == "courier_offer", "Unknown choice identities must not change the episode.")
	await _background_click()
	_expect(_id(game) == "courier_offer" and _visible_choices(game).size() == 2, "Revealing the choice prompt must expose exactly two explicit answers.")
	_expect(not game._ready_dot.visible and not game._monologue_dot.visible, "Pending choices must hide generic continuation indicators.")
	_check_choice_layout(game)
	await _capture("input-choice-" + str(window_size.x))
	await _background_click()
	await _touch(Vector2(80, 350))
	await _key(KEY_SPACE)
	await _key(KEY_ENTER)
	_expect(_id(game) == "courier_offer" and game._choice_pending() and game._choices.is_empty(), "Background, touch, Space and unfocused Enter must never select or skip a pending choice.")
	if window_size.x == 1280:
		game = await _choice_detour(game, "courier_offer", "")
	var button: Button = _choice_button(game, option_id)
	if button == null: return
	if option_id == "tea_first":
		button.grab_focus()
		await _key(KEY_ENTER)
	else:
		await _click_control(button)
	_expect(_id(game) == "courier_reply" and game._choices.get("courier_offer") == option_id, "Explicit selection must record its stable identity and enter only the response beat.")
	_expect(not game._choice_pending() and _visible_choices(game).is_empty(), "Response text must clear the prior answer controls.")
	_replies[option_id] = game._text(game._resolved_text_key())
	game._process(0.12)
	if window_size.x == 1280:
		game = await _choice_detour(game, "courier_reply", option_id)
	await _background_click()
	_expect(_id(game) == "courier_reply" and game._ready_dot.visible, "A response click must finish revealing before continuation.")
	game._process(0.2)
	_expect(game._cast._manpu.one_shots().size() >= 1 and game._manpu_event_time >= 0.0 and game._elapsed - game._manpu_event_time < 0.65, "The main-story response must display its newly emitted Sigh Puff after text reveal.")
	if window_size.x == 1280: await _capture("input-courier-puff-1280")
	await _background_click()
	_expect(_id(game) == "one_more_minute", "Both answers must merge into the same protagonist monologue.")
	_expect(game._load_errors.is_empty(), "Physical input must not produce host validation errors.")


func _choice_detour(game: Control, beat_id: String, selected: String) -> Control:
	var before: Dictionary = game.save_game()
	await _key(KEY_F6)
	var switched: Dictionary = game.save_game()
	_expect(game.get_language() == "en" and is_equal_approx(float(before["reveal_fraction"]), float(switched["reveal_fraction"])), "Choice language switching must preserve reveal fraction.")
	_expect(before.get("choices", {}) == switched.get("choices", {}) and is_equal_approx(float(before["elapsed"]), float(switched["elapsed"])), "Choice language switching must preserve decisions and effect time.")
	_expect(_app.open_route("game:presentation_lab"), "A choice checkpoint must permit a real Lab detour.")
	await _settle()
	_expect(_app.open_route("game:bishoujo_afterlight"), "The story must resume after its choice detour.")
	await _settle()
	var restored: Control = _app.active_scene
	_expect(restored._load_errors.is_empty() and _id(restored) == beat_id and restored.get_language() == "en", "The choice checkpoint must restore the exact beat and language.")
	var resumed: Dictionary = restored.save_game()
	_expect(resumed.get("choices", {}) == switched.get("choices", {}) and resumed["history"] == switched["history"] and resumed.get("manpu_history", []) == switched.get("manpu_history", []), "The in-session checkpoint must retain pending/resolved decisions and effect history.")
	_expect(is_equal_approx(float(resumed["elapsed"]), float(switched["elapsed"])) and is_equal_approx(float(resumed["reveal_fraction"]), float(switched["reveal_fraction"])) and is_equal_approx(float(resumed.get("manpu_event_time", -1.0)), float(switched.get("manpu_event_time", -1.0))), "The restored choice must retain effect time, puff onset and text reveal fraction.")
	_expect(restored._choice_pending() == selected.is_empty(), "Choice restoration must retain whether an explicit answer is still required.")
	if selected.is_empty():
		_expect(_visible_choices(restored).size() == 2, "An unresolved restored prompt must still display both answers.")
	else:
		_expect(restored._choices.get("courier_offer") == selected, "The selected answer identity must survive a real detour.")
	await _key(KEY_F6)
	_expect(restored.get_language() == "ko", "The restored response must switch back to Korean.")
	return restored


func _visible_choices(game: Control) -> Array[Button]:
	var result: Array[Button] = []
	for button: Button in game._choice_buttons:
		if button.is_visible_in_tree(): result.append(button)
	return result


func _choice_button(game: Control, option_id: String) -> Button:
	for button: Button in game._choice_buttons:
		if str(button.get_meta("choice_id", "")) == option_id: return button
	_expect(false, "The expected stable answer identity must have a visible control: " + option_id)
	return null


func _check_choice_layout(game: Control) -> void:
	var previous := Rect2()
	for button: Button in _visible_choices(game):
		var rect := button.get_global_rect()
		_expect(is_equal_approx(rect.get_center().x, DESIGN_SIZE.x * 0.5) and rect.end.y < 620.0 and rect.size.x >= 400.0, "Choice answers must be centered above the dialogue sheet with readable width.")
		_expect(not previous.has_area() or not previous.intersects(rect), "The two answer controls must not overlap.")
		previous = rect


func _check_no_advance_labels(node: Node) -> void:
	if node is Button or node is Label:
		var text: String = node.text.to_lower()
		_expect(not text.begins_with("next") and not text.begins_with("skip") and not text.contains("space / enter") and not text.contains("click to continue"), "The story must not display navigation buttons or continuation instructions.")
	for child: Node in node.get_children(): _check_no_advance_labels(child)


func _capture(label: String) -> void:
	if not _capture_enabled: return
	_expect(DirAccess.make_dir_recursive_absolute(DIRECTORY) == OK, "The input capture directory must be writable.")
	await _settle()
	RenderingServer.force_draw()
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Input captures must use native resolution.")
	_expect(picture.save_png(DIRECTORY.path_join(label + ".png")) == OK, "The input capture must save: " + label)
	_capture_count += 1


func _background_click() -> void:
	await _mouse(Vector2(80, 350))


func _click_control(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The intended answer control must be visible and enabled.")
	if button != null and button.is_visible_in_tree() and not button.disabled:
		await _mouse(button.get_global_rect().get_center())


func _mouse(logical_position: Vector2) -> void:
	var point := root.get_final_transform() * logical_position
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.global_position = point
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _touch(logical_position: Vector2) -> void:
	for pressed: bool in [true, false]:
		var event := InputEventScreenTouch.new()
		event.index = 0
		event.position = root.get_final_transform() * logical_position
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _key(keycode: Key) -> void:
	for pressed: bool in [true, false]:
		var event := InputEventKey.new()
		event.keycode = keycode
		event.physical_keycode = keycode
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _id(game: Control) -> String:
	return str(game.current_beat()["id"])


func _freeze_route(node: Node) -> void:
	if node.has_method("current_beat"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _app.active_scene != null: _app.active_scene.set_process(false)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
