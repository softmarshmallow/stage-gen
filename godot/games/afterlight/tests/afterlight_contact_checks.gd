extends "res://tests/afterlight_ensemble_checks.gd"

## Native proof of the required story contact, using real viewport mouse/touch
## events. The shared hit-test contract has its own renderer-free checks.
const CONTACT_BEAT := "a_touch_that_stays"
const CONTACT_OUTPUT := "res://tests/contact-afterlight"
var _contact_signals := 0
var _contact_captures: Array[Dictionary] = []


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Afterlight contact captures require a native renderer.")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(CONTACT_OUTPUT)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	for factor in [1, 2]:
		root.size = Vector2i(DESIGN_SIZE) * factor
		await _contact_at_size(factor)
	var sources := {}
	for path: String in ["res://addons/game_presentation/interaction/point_contact.gd", "res://root.gd", "res://story.gd", "res://story_beats.gd", "res://text/en.json", "res://text/ko.json"]:
		sources[path] = FileAccess.get_sha256(path)
	var portrait_path := "res://assets/characters/nami_contact.png"
	var output := FileAccess.open(CONTACT_OUTPUT.path_join("manifest.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"sources": sources, "art": {portrait_path: FileAccess.get_sha256(portrait_path)}, "captures": _contact_captures, "confirmation_signals": _contact_signals, "errors": _errors}, "\t"))
	await _dispose_app()
	for issue: String in _errors: printerr("FAIL Afterlight contact: " + issue)
	if _errors.is_empty(): print("PASS Afterlight contact: required reveal/point gate, native mouse/touch at 1x/2x, single confirmation, finite feedback, EN/KO/pause/Lab continuity before and after confirmation, explicit replay and restart cleanup")
	quit(0 if _errors.is_empty() else 1)


func _seek_contact() -> Control:
	_expect(_app.open_route("game:afterlight/new_game"), "A fresh Afterlight episode must open.")
	await _settle()
	var game := _active()
	game.set_language("ko")
	for iteration in game.beats.size():
		if str(game.current_beat()["id"]) == CONTACT_BEAT: return game
		game._process(6.0)
		if game._choice_pending():
			game._choose("help_first")
		else:
			game._next()
	_expect(false, "The new required touch must follow Nami's recovery scene.")
	return game


func _contact_at_size(factor: int) -> void:
	var game := await _seek_contact()
	_expect(_healthy_contact(game), "The contact story beat must initialize with prepared art.")
	if not _healthy_contact(game): return
	_expect(game.beats.size() == EPISODE_BEAT_COUNT and game.current_beat()["type"] == "contact", "The 57-beat story must reach its required contact beat.")
	var target: Dictionary = game.contact_target()
	_expect(bool(target["visible"]) and not bool(target["confirmed"]), "The contact image must appear without an automatic acknowledgement.")
	var count_before := _contact_signals
	if not bool(target["ready"]):
		_expect(not game._try_contact(target["center"]), "A target hit before readiness must not confirm contact.")
		await _contact_pointer(target["center"], factor == 2)
		_expect(str(game.current_beat()["id"]) == CONTACT_BEAT and bool(game.contact_target()["ready"]) and _contact_signals == count_before, "A native target pointer during reveal must finish text without confirming via a paired emulated event.")
	else:
		_expect(game.get_voice_state()["status"] == "ready" and game._reveal.sample()["phase"] == "holding", "A prepared voice must reveal the full contact line and make its target ready immediately.")
	await _contact_key(KEY_SPACE)
	game._continue_story()
	_expect(str(game.current_beat()["id"]) == CONTACT_BEAT and not game._contact.is_confirmed(), "Further Space or generic continuation must remain gated on the point hit.")
	target = game.contact_target()
	var center: Vector2 = target["center"]
	var radius := float(target["radius"])
	_expect(Rect2(Vector2.ZERO, DESIGN_SIZE).has_point(center) and radius > 0.0, "The authored target must have a visible logical-canvas position and positive radius.")
	var uv: Array = game._profile("nami")["contact_uv"]
	var portrait: Rect2 = game._portrait.get_rect()
	_expect(center.is_equal_approx(portrait.position + portrait.size * Vector2(float(uv[0]), float(uv[1]))), "The target must follow the supplied portrait's fingertip UV after camera projection.")
	await _contact_pointer(center + Vector2(radius + 18.0, 0.0), factor == 2)
	_expect(not game._contact.is_confirmed() and _contact_signals == count_before, "A native pointer outside the circular target must not confirm.")
	game._process(0.2)
	await _language_and_detour(game, CONTACT_BEAT)
	game = _active()
	_expect(_contact_signals == count_before and not game._contact.is_confirmed(), "An unconfirmed checkpoint must remain unconfirmed without synthetic input.")
	await _contact_frame("ready-" + str(factor), game)
	target = game.contact_target()
	await _contact_pointer(target["center"], factor == 2)
	_expect(game._contact.is_confirmed() and _contact_signals == count_before + 1 and str(game.current_beat()["id"]) == CONTACT_BEAT, "The native target hit must confirm exactly once and hold for feedback.")
	var confirmed_time: float = game._contact_time
	await _contact_pointer(target["center"], factor == 2)
	await _contact_key(KEY_SPACE)
	_expect(_contact_signals == count_before + 1 and is_equal_approx(game._contact_time, confirmed_time), "Repeated target/Space input must neither reconfirm nor retime feedback.")
	game._process(0.2)
	await _contact_frame("feedback-" + str(factor), game)
	await _language_and_detour(game, CONTACT_BEAT)
	game = _active()
	_expect(_contact_signals == count_before + 1 and game._contact.is_confirmed() and is_equal_approx(game._contact_time, confirmed_time), "Confirmed checkpoint replay must restore acknowledgement silently at the same time.")
	var remaining: float = float(game.content["contact"].get("feedback_seconds", 0.45)) - (game._elapsed - game._contact_time)
	game._process(maxf(0.0, remaining - 0.01))
	_expect(str(game.current_beat()["id"]) == CONTACT_BEAT, "Feedback must finish its authored delay before returning to the story.")
	game._process(0.02)
	_expect(str(game.current_beat()["id"]) == "only_a_second" and not bool(game.contact_target()["visible"]), "Completed feedback must advance once to Nami's relief line and remove the contact overlay.")
	await _contact_frame("returned-" + str(factor), game)
	game._process(0.5)
	_expect(str(game.current_beat()["id"]) == "only_a_second" and _contact_signals == count_before + 1, "The one-shot feedback must not schedule a second continuation.")
	# Restart while waiting for a new contact must clear the target and latch.
	game = await _seek_contact()
	game._next()
	_expect(bool(game.contact_target()["ready"]) and not game._contact.is_confirmed(), "A fresh episode must provide a fresh unconfirmed interaction.")
	game._restart()
	_expect(str(game.current_beat()["id"]) == "undeliverable" and not bool(game.contact_target()["visible"]) and not game._contact.is_confirmed(), "Restart must remove the contact target and acknowledgement.")


func _contact_frame(label: String, game: Control) -> void:
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	var path := CONTACT_OUTPUT.path_join(label + ".png")
	_expect(picture.get_size() == root.size and picture.save_png(path) == OK, "The contact capture must save at native resolution: " + label)
	var target: Dictionary = game.contact_target()
	var feedback_center: Vector2 = game._contact_ring.get_global_rect().get_center()
	if bool(target["visible"]):
		_expect(feedback_center.is_equal_approx(target["center"]), "The visible feedback must stay centered on the same logical target at both native scales.")
	_contact_captures.append({"file": path, "sha256": FileAccess.get_sha256(path), "window": [picture.get_width(), picture.get_height()], "beat": game.current_beat()["id"], "target": target, "native_target_center": root.get_final_transform() * target["center"], "native_feedback_center": root.get_final_transform() * feedback_center, "elapsed": game._elapsed, "contact_time": game._contact_time, "language": game.get_language()})
	print("Captured Afterlight contact: " + label)


func _contact_pointer(logical_point: Vector2, touch: bool) -> void:
	var native_point := root.get_final_transform() * logical_point
	for pressed in [true, false]:
		if touch:
			var event := InputEventScreenTouch.new()
			event.index = 0
			event.position = native_point
			event.pressed = pressed
			root.push_input(event, false)
		else:
			var event := InputEventMouseButton.new()
			event.button_index = MOUSE_BUTTON_LEFT
			event.position = native_point
			event.global_position = native_point
			event.pressed = pressed
			root.push_input(event, false)
	await _settle()


func _contact_key(key: Key) -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = key
		event.physical_keycode = key
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _freeze_route(node: Node) -> void:
	super._freeze_route(node)
	if node.has_method("contact_target") and node.get("_contact") != null:
		node._contact.confirmed.connect(_on_contact_confirmed)


func _on_contact_confirmed(_point: Vector2) -> void:
	_contact_signals += 1


func _healthy_contact(game: Control) -> bool:
	return game.current_beat()["id"] == CONTACT_BEAT and game._load_errors.is_empty()
