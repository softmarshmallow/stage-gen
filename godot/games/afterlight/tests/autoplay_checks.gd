extends "res://tests/text_reveal_audio_checks.gd"

## The real application host owns autoplay; deterministic clocks and prepared
## PCM fixtures exercise progression without providers or generated recordings.
const OUTPUT := "res://tests/autoplay"
var _capture_enabled := false
var _evidence := {"schema_version": 1, "checks": [], "captures": [], "source_sha256": {}}


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-autoplay")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Autoplay captures require a native renderer.")
		quit(2)
		return
	_force_episode_fallback = true
	root.size = Vector2i(1280, 900)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	var game: Control = _app.active_scene
	_expect(_app.selected_game_id == "afterlight" and game._load_errors.is_empty(), "Run the initialized Afterlight host with --game afterlight.")
	if _errors.is_empty():
		_expect(game.has_method("get_autoplay_state") and game.has_method("set_autoplay_enabled"), "Afterlight must expose its host-owned autoplay state and toggle.")
	if _errors.is_empty():
		_basic_timing_checks(game)
		await _voice_checks(game)
		_choice_checks(game)
		_contact_and_ending_checks(game)
		_complete_episode_checks(game)
		await _checkpoint_checks(game)
		await _input_and_layout_checks()
	if _app != null:
		_app.queue_free()
		_app = null
	await create_timer(0.2).timeout
	_evidence["errors"] = _errors
	for path: String in ["res://story.gd", "res://root.gd", "res://story_beats.gd", "res://text/en.json", "res://text/ko.json", "res://addons/game_presentation/audio/text_reveal_audio.gd", "res://tests/autoplay_checks.gd"]:
		_evidence["source_sha256"][path] = FileAccess.get_sha256(path)
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	var file := FileAccess.open(OUTPUT.path_join("validation.json"), FileAccess.WRITE)
	if file != null: file.store_string(JSON.stringify(_evidence, "  ", true) + "\n")
	for issue: String in _errors: printerr("FAIL Afterlight Autoplay: " + issue)
	if _errors.is_empty(): print("PASS Afterlight Autoplay: opt-in timing, reveal/cinematic/voice gates, explicit choices/contact, pause/language/checkpoint continuity, ending hold and native UI input")
	quit(0 if _errors.is_empty() else 1)


func _basic_timing_checks(game: Control) -> void:
	var initial: Dictionary = game.get_autoplay_state()
	for field: String in ["enabled", "elapsed_seconds", "delay_seconds", "blocked_reason", "default_choice"]:
		_expect(initial.has(field), "Autoplay diagnostics must expose " + field)
	_expect(not bool(initial.get("enabled", true)), "A newly opened game must start with autoplay OFF.")
	game._process(20.0)
	_expect(game.current_beat()["id"] == "undeliverable", "Autoplay OFF must retain manual monologue continuation after natural reveal.")
	_seek(game, "undeliverable")
	game.set_autoplay_enabled(true)
	game._process(20.0)
	_expect(game.current_beat()["id"] == "undeliverable" and game._reveal.sample()["phase"] == "holding" and is_zero_approx(_timer(game)), "The frame completing a text reveal must not credit its earlier time to autoplay.")
	game._process(2.99)
	_expect(game.current_beat()["id"] == "undeliverable", "An unvoiced fully revealed line must retain the full three-second reading delay.")
	game._process(0.02)
	_expect(game.current_beat()["id"] == "across_the_threshold" and is_zero_approx(_timer(game)), "Autoplay must advance once after three readable seconds and reset at the next beat.")
	game._set_reveal_fraction(1.0)
	game._process(0.1)
	_expect(not game._cinematic_complete() and is_zero_approx(_timer(game)), "Fully revealed text must not bypass unfinished cinematic motion.")
	game._process(20.0)
	_expect(game.current_beat()["id"] == "across_the_threshold" and game._cinematic_complete() and is_zero_approx(_timer(game)), "The cinematic completion frame must not credit hidden-caption time to reading.")
	game._process(3.01)
	_expect(game.current_beat()["id"] == "eyes_on_nami", "A naturally completed cinematic must auto-advance only after its reading delay.")
	_seek(game, "no_ordinary_post")
	game._next()
	game.set_autoplay_enabled(true)
	game._process(1.2)
	var elapsed := _timer(game)
	game._toggle_pause()
	game._process(30.0)
	_expect(is_equal_approx(_timer(game), elapsed) and game.current_beat()["id"] == "no_ordinary_post", "Menu pause must freeze the reading countdown and current beat.")
	game._toggle_pause()
	game._process(0.2)
	_expect(is_equal_approx(_timer(game), elapsed + 0.2), "Resume must continue the same countdown without a pause-time jump.")
	var same_language: String = game.get_language()
	game.set_language(same_language)
	_expect(is_equal_approx(_timer(game), elapsed + 0.2), "Selecting the current language must retain the countdown.")
	game.set_language("ko" if same_language == "en" else "en")
	_expect(game.current_beat()["id"] == "no_ordinary_post" and bool(game.get_autoplay_state()["enabled"]) and is_zero_approx(_timer(game)), "Changing language must preserve autoplay and beat identity while restarting reading time.")
	game._process(1.0)
	game.set_autoplay_enabled(false)
	game._process(20.0)
	_expect(game.current_beat()["id"] == "no_ordinary_post" and is_zero_approx(_timer(game)), "Disabling autoplay must clear its countdown and keep the current line.")
	game.set_autoplay_enabled(true)
	game._process(1.0)
	game._next()
	_expect(game.current_beat()["id"] == "a_glass_record" and bool(game.get_autoplay_state()["enabled"]) and is_zero_approx(_timer(game)), "Manual continuation must keep autoplay enabled with a fresh next-beat timer.")
	game._process(-1.0)
	game._process(INF)
	game._process(NAN)
	_expect(is_zero_approx(_timer(game)), "Invalid deltas must never advance the autoplay clock.")
	_evidence["checks"].append("Default OFF; natural reveal and cinematic completion precede the full 3s delay; pause freezes; real language change resets; manual continuation and toggles reset without disabling future autoplay")


func _voice_checks(game: Control) -> void:
	_seek(game, "no_ordinary_post")
	game._set_reveal_fraction(1.0)
	_expect(game._text_audio.configure({"mode": "auto"}).is_empty(), "The prepared voice fixture must configure.")
	game._text_audio.begin(str(game._reveal.sample()["text"]), _tone(10.0), int(game._reveal.sample()["visible_characters"]))
	game.set_autoplay_enabled(true)
	game._process(20.0)
	_expect(game._text_audio.get_state()["voice_playing"] and game.current_beat()["id"] == "no_ordinary_post" and is_zero_approx(_timer(game)), "Active prepared voice must block autoplay even when all text is visible and story time advances.")
	game._text_audio.begin(str(game._reveal.sample()["text"]), _tone(0.12), int(game._reveal.sample()["visible_characters"]))
	await create_timer(0.35).timeout
	_expect(game._text_audio.get_state()["voice_finished"], "A short actual PCM fixture must finish on the audio playback clock.")
	game._process(2.99)
	_expect(game.current_beat()["id"] == "no_ordinary_post", "Voice completion must precede the entire reading delay.")
	game._process(0.02)
	_expect(game.current_beat()["id"] == "a_glass_record", "A finished voice must release autoplay after the reading delay.")
	_seek(game, "eyes_on_nami")
	game._voice_waiting = true
	game.set_autoplay_enabled(true)
	game._process(0.1)
	_expect(is_zero_approx(_timer(game)) and game.current_beat()["id"] == "eyes_on_nami", "A voice waiting for its cinematic caption must not start the reading timer.")
	game._voice_waiting = false
	_evidence["checks"].append("Real 10s PCM voice blocks accelerated story time; real 0.12s PCM completion releases the full 3s delay; pending cinematic voice remains blocked; no listening verdict")


func _choice_checks(game: Control) -> void:
	_seek(game, "courier_offer")
	game._next()
	game.set_autoplay_enabled(true)
	var state: Dictionary = game.get_autoplay_state()
	_expect(state["default_choice"] == "help_first" and is_equal_approx(float(state["delay_seconds"]), 5.0), "The authored offer must explicitly select help_first after five readable seconds.")
	game._process(4.99)
	_expect(game.current_beat()["id"] == "courier_offer" and game._choice_pending(), "Autoplay must retain the complete choice delay.")
	game._process(0.02)
	_expect(game.current_beat()["id"] == "courier_reply" and game._choices.get("courier_offer") == "help_first" and game._resolved_text_key() == "episode.courier_reply.help_first", "The timeout must use the authored choice and its matching reply exactly once.")
	_seek(game, "courier_offer")
	game._next()
	game.set_autoplay_enabled(true)
	game._process(4.0)
	game._choose("tea_first")
	game._process(0.5)
	_expect(game.current_beat()["id"] == "courier_reply" and game._choices.get("courier_offer") == "tea_first" and game._resolved_text_key() == "episode.courier_reply.tea_first", "A manual alternative before timeout must win and cancel the pending default choice.")
	for authored: Dictionary in [{}, {"default_choice": "help_first", "require_input": true}]:
		_seek(game, "courier_offer")
		var original: Dictionary = game.current_beat().get("autoplay", {}).duplicate(true)
		game.current_beat()["autoplay"] = authored.duplicate(true)
		game._next()
		game.set_autoplay_enabled(true)
		game._process(60.0)
		_expect(game.current_beat()["id"] == "courier_offer" and game._choice_pending() and is_zero_approx(_timer(game)), "Missing defaults and explicit required input must hold a choice: " + str(authored))
		game.current_beat()["autoplay"] = original
	_seek(game, "courier_offer")
	var original: Dictionary = game.current_beat().get("autoplay", {}).duplicate(true)
	game.current_beat()["autoplay"] = {"default_choice": "unknown_option"}
	game._validate_autoplay()
	_expect(not game._load_errors.is_empty(), "Invalid authored choice defaults must be rejected before playback.")
	game.current_beat()["autoplay"] = original
	game._load_errors.clear()
	_seek(game, "no_ordinary_post")
	game.current_beat()["autoplay"] = {"require_input": true}
	game._next()
	game.set_autoplay_enabled(true)
	game._process(60.0)
	_expect(game.current_beat()["id"] == "no_ordinary_post" and is_zero_approx(_timer(game)), "An authored required-input dialogue must hold even after reveal and the normal delay.")
	game.current_beat().erase("autoplay")
	_evidence["checks"].append("Explicit help_first uses the 5s choice delay and matching reply; manual tea_first cancels the default; missing defaults and required input hold; invalid defaults are rejected")


func _contact_and_ending_checks(game: Control) -> void:
	_seek(game, "a_touch_that_stays")
	game._next()
	game.set_autoplay_enabled(true)
	game._process(60.0)
	_expect(game.current_beat()["id"] == "a_touch_that_stays" and not game._contact.is_confirmed() and is_zero_approx(_timer(game)), "Autoplay must never synthesize a fingertip confirmation, regardless of wait duration.")
	_expect(game._try_contact(game.contact_target()["center"]), "The contact fixture must explicitly hit the authored target.")
	game._process(0.44)
	_expect(game.current_beat()["id"] == "a_touch_that_stays", "Confirmed contact must keep its existing feedback duration.")
	game._process(0.02)
	_expect(game.current_beat()["id"] == "only_a_second" and is_zero_approx(_timer(game)), "Confirmed contact must advance once through the existing 0.45s feedback path.")
	_seek(game, "the_next_arrival")
	game._next()
	game.set_autoplay_enabled(true)
	game._process(60.0)
	_expect(game.current_beat()["id"] == "the_next_arrival" and not game._paused, "Autoplay must hold the final beat without opening the menu or restarting the episode.")
	_evidence["checks"].append("Unconfirmed contact holds indefinitely; explicit target hit retains 0.45s feedback and a fresh next-line timer; the ending holds without automatic restart or menu")


func _checkpoint_checks(game: Control) -> void:
	_seek(game, "no_ordinary_post")
	game._next()
	game.set_autoplay_enabled(true)
	game._process(1.25)
	var before: Dictionary = game.get_autoplay_state()
	game._toggle_pause()
	_expect(_app.open_route("game:lab"), "Autoplay must support a real Presentation Lab detour.")
	await _settle()
	_expect(not _app.active_scene.has_method("get_autoplay_state"), "Presentation Lab must retain independent behavior without Afterlight's autoplay API.")
	_expect(_app.open_route("game:afterlight"), "The autoplay checkpoint must return to Afterlight.")
	await _settle()
	game = _app.active_scene
	_expect(game._load_errors.is_empty(), "Autoplay checkpoint restoration must be valid: " + str(game._load_errors))
	var after: Dictionary = game.get_autoplay_state()
	_expect(game.current_beat()["id"] == "no_ordinary_post" and not game._paused and bool(after["enabled"]) and is_equal_approx(float(after["elapsed_seconds"]), float(before["elapsed_seconds"])), "A Lab return must restore the same line, enabled setting and partial countdown with the existing resume policy.")
	game._process(1.74)
	_expect(game.current_beat()["id"] == "no_ordinary_post", "A restored countdown must retain its remaining reading time.")
	game._process(0.02)
	_expect(game.current_beat()["id"] == "a_glass_record", "A restored countdown must continue once at its original total delay.")
	game.saved_state = game.save_game()
	game.saved_state.erase("autoplay")
	game._restore_game()
	_expect(game._load_errors.is_empty() and game.current_beat()["id"] == "a_glass_record" and not bool(game.get_autoplay_state()["enabled"]) and is_zero_approx(_timer(game)), "A pre-autoplay version-four checkpoint must remain compatible and default to manual progression.")
	_evidence["checks"].append("Actual app-shell Lab round trip preserves enabled autoplay and 1.25s countdown, then advances after the remaining delay; Lab keeps independent behavior; older checkpoints default OFF")


func _complete_episode_checks(game: Control) -> void:
	_seek(game, "undeliverable")
	game.set_autoplay_enabled(true)
	var visited: Array[String] = []
	var confirmations := 0
	for step in game.beats.size() * 4:
		var id := str(game.current_beat()["id"])
		if visited.is_empty() or visited.back() != id: visited.append(id)
		if game.current_beat().get("type") == "contact" and bool(game.contact_target()["ready"]):
			_expect(game._try_contact(game.contact_target()["center"]), "Complete autoplay traversal requires the user's one explicit contact.")
			confirmations += 1
		game._process(30.0)
		if id == "the_next_arrival" and game._reveal.sample()["phase"] == "holding": break
	_expect(visited.size() == game.beats.size() and confirmations == 1 and game._load_errors.is_empty(), "Autoplay must traverse all 57 authored beats with only the required explicit contact and no dropped/duplicate beat.")
	_expect(game.current_beat()["id"] == "the_next_arrival" and game._choices.get("courier_offer") == "help_first" and not game._paused, "The complete autoplay run must reach the held ending through the authored default branch.")
	_evidence["checks"].append("Complete 57-beat fallback-audio episode traversed in autoplay with the authored help_first choice and one explicit contact; each beat visited and the ending held")


func _input_and_layout_checks() -> void:
	for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window_size
		var game: Control = _app.active_scene
		_seek(game, "no_ordinary_post")
		game._next()
		await _settle()
		var toggle: Button = game.get("_autoplay_button")
		_expect(toggle != null, "Afterlight must expose its concrete autoplay button to focused UI QA.")
		if toggle == null: continue
		var button_rect := toggle.get_global_rect()
		_expect(toggle.is_visible_in_tree() and Rect2(0, 0, 1280, 900).encloses(button_rect), "The autoplay toggle must fit the logical canvas at each native window size.")
		_expect(not button_rect.intersects(game._language_button.get_global_rect()), "The autoplay and language controls must not overlap.")
		await _pointer(button_rect.get_center())
		_expect(bool(game.get_autoplay_state()["enabled"]) and game.current_beat()["id"] == "no_ordinary_post" and is_zero_approx(_timer(game)), "A native toggle click must enable autoplay without advancing the story.")
		game.set_language("en")
		if _capture_enabled: await _capture("on-en-" + str(window_size.x), game)
		game.set_language("ko")
		if _capture_enabled: await _capture("on-ko-" + str(window_size.x), game)
		await _pointer(button_rect.get_center())
		_expect(not bool(game.get_autoplay_state()["enabled"]) and game.current_beat()["id"] == "no_ordinary_post", "A native second toggle click must disable autoplay without advancing the story.")
		for enabled: bool in [true, false]:
			toggle.grab_focus()
			await _key(KEY_SPACE)
			_expect(bool(game.get_autoplay_state()["enabled"]) == enabled and game.current_beat()["id"] == "no_ordinary_post", "A keyboard activation of the focused autoplay toggle must not also continue the story.")
		if _capture_enabled: await _capture("off-ko-" + str(window_size.x), game)
		_seek(game, "courier_offer")
		game._next()
		game.set_autoplay_enabled(true)
		game._process(1.0)
		if _capture_enabled: await _capture("choice-ko-" + str(window_size.x), game)
		_seek(game, "undeliverable")
		var words: Dictionary = game._reveal.sample()
		_expect(toggle.is_visible_in_tree(), "The toggle must remain reachable over a black monologue.")
		await _pointer(button_rect.get_center())
		_expect(bool(game.get_autoplay_state()["enabled"]) and game.current_beat()["id"] == "undeliverable" and game._reveal.sample() == words, "A monologue toggle click must not reveal or advance the underlying story.")
		game._next()
		if _capture_enabled: await _capture("monologue-ko-" + str(window_size.x), game)
	_evidence["checks"].append("Actual mouse and focused Space activation toggle autoplay without advancing at 1280x900 and 2560x1800, including black monologues; top controls stay inside the canvas and separate from language UI")


func _seek(game: Control, beat_id: String) -> void:
	game.set_autoplay_enabled(false)
	game._restart()
	# Fallback text requires reveal plus continue at every line, so the full
	# 57-beat episode needs more than the audio suite's 100-action traversal.
	for step in game.beats.size() * 3:
		if game.current_beat()["id"] == beat_id: break
		if game.current_beat().get("type") == "contact":
			game._next()
			_expect(game._try_contact(game.contact_target()["center"]), "Autoplay traversal must explicitly fulfill the authored contact.")
			game._process(1.0)
		elif game._choice_pending():
			game._next()
			game._choose("help_first")
		else:
			game._next()
	_expect(game.current_beat()["id"] == beat_id and game._load_errors.is_empty(), "The deterministic host traversal must reach " + beat_id)


func _timer(game: Control) -> float:
	return float(game.get_autoplay_state()["elapsed_seconds"])


func _pointer(logical_point: Vector2) -> void:
	var native_point := root.get_final_transform() * logical_point
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = native_point
		event.global_position = native_point
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _key(key: Key) -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = key
		event.physical_keycode = key
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _capture(label: String, game: Control) -> void:
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	game._render()
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	var path := OUTPUT.path_join(label + ".png")
	_expect(picture.get_size() == root.size and picture.save_png(path) == OK, "Autoplay UI must capture at native resolution: " + label)
	_evidence["captures"].append({"file": path, "sha256": FileAccess.get_sha256(path), "window": [picture.get_width(), picture.get_height()], "beat_id": game.current_beat()["id"], "language": game.get_language(), "autoplay": game.get_autoplay_state()})
	print("Captured Afterlight autoplay: " + label)
