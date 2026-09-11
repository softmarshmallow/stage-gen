extends "res://qa/autoplay_checks.gd"

## Real host integration; PCM/art outputs remain local and unapproved listening.
const PASS_OUTPUT := "res://qa/ambient-transmission"
var _pass_evidence := {"checks": [], "captures": [], "source_sha256": {}}
var _initial_bus_count := 0


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-atmosphere")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Atmosphere captures require a native renderer.")
		quit(2)
		return
	_initial_bus_count = AudioServer.bus_count
	root.size = Vector2i(1280, 900)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	var game: Control = _app.active_scene
	_expect(_app.selected_game_id == "bishoujo_afterlight" and game._load_errors.is_empty(), "Load the actual Afterlight host with --game bishoujo_afterlight.")
	if _errors.is_empty():
		_expect(game._voice_effects.get_index() < game._text_audio.get_index(), "Reverse child exit must stop audio before removing the voice processor bus.")
		await _atmosphere_checks(game)
		game = _app.active_scene
		await _transmission_checks(game)
		game = _app.active_scene
		await _composed_captures(game)
		_expect(game._load_errors.is_empty(), "No host errors after scene, audio, and language transitions: " + str(game._load_errors))
	if _app != null:
		_app.queue_free()
		_app = null
	await create_timer(0.3).timeout
	_expect(AudioServer.bus_count == _initial_bus_count, "Leaving the host must remove every private voice bus.")
	_pass_evidence["checks"].append("Private audio buses released after host destruction")
	_expect(_pass_evidence["checks"].size() == 3, "Every integration check group must complete.")
	if _capture_enabled: _expect(_pass_evidence["captures"].size() == 8, "Both-scale native capture groups must complete.")
	_pass_evidence["errors"] = _errors
	_pass_evidence["provider_operations"] = 0
	_pass_evidence["listening_verdict"] = "not_performed"
	for path: String in ["res://games/bishoujo_afterlight/story.gd", "res://games/bishoujo_afterlight/root.gd", "res://games/bishoujo_afterlight/atmosphere_profile.gd", "res://addons/game_presentation/effects/particles/ambient_particles.gd", "res://addons/game_presentation/audio/voice_effects.gd", "res://addons/game_presentation/audio/text_reveal_audio.gd", "res://qa/ambient_transmission_integration_checks.gd"]:
		_pass_evidence["source_sha256"][path] = FileAccess.get_sha256(path)
	DirAccess.make_dir_recursive_absolute(PASS_OUTPUT)
	var file := FileAccess.open(PASS_OUTPUT.path_join("validation.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_pass_evidence, "  ", true) + "\n")
	for issue: String in _errors: printerr("FAIL Ambient / Transmission Integration: " + issue)
	if _errors.is_empty(): print("PASS Ambient / Transmission Integration: world framing, scene/pause/replay/Lab continuity, localized projection-only DSP, voice/fallback isolation and cleanup")
	quit(0 if _errors.is_empty() else 1)


func _atmosphere_checks(game: Control) -> void:
	_seek(game, "across_the_threshold")
	game._process(0.6)
	var before: Dictionary = game.get_atmosphere_state()
	_expect(before["profile"] == "quiet_interior" and before["layers"]["dust"]["particle_count"] > 0, "The quiet entrance must have sustained ambient dust.")
	var emitter: Control = game._ambient_emitters[0]
	_expect(emitter._camera == game._world_transform() and emitter._camera != Transform2D.IDENTITY, "Walking camera must transform ambient positions and sizes.")
	_expect(game._atmosphere_layer.get_index() < game._background_blackout.get_index() and game._atmosphere_layer.get_index() < game._cast.get_index(), "Ambient layers must be behind actors and the environment blackout.")
	game._toggle_pause()
	game._process(8.0)
	_expect(game.get_atmosphere_state() == before, "Menu pause must freeze atmosphere samples and birth clocks.")
	game._toggle_pause()
	game._process(0.3)
	_expect(game.get_atmosphere_state() != before, "Resume must continue emission from the held clock.")
	before = game.get_atmosphere_state()
	game.set_language("en" if game.get_language() == "ko" else "ko")
	_expect(game.get_atmosphere_state() == before, "Locale changes must not restart the particle field.")
	game._next()
	var clock: float = game._ambient_emitters[0].get_state()["elapsed"]
	game._next()
	_expect(float(game._ambient_emitters[0].get_state()["elapsed"]) >= clock, "Ordinary dialogue transitions must preserve continuous atmosphere.")
	_seek(game, "the_keeper")
	game._process(0.24)
	before = game.get_atmosphere_state()
	_expect(before["profile"] == "infernal_hall" and before["layers"].keys() == ["smoke", "embers", "sparks"], "Keeper scene must compose independent smoke, ember and spark emitters.")
	for layer: Control in game._ambient_emitters:
		_expect(layer._camera == game._world_transform(), "Every infernal layer must receive the final shaken camera.")
		_expect(int(layer.get_state()["particle_count"]) > 0, "Warm infernal layers must immediately contain live sprites.")
	_expect(game._shake.is_active() and float(game._shake.sample()["envelope"]) > 0.0, "The Keeper fixture must contain active impact camera motion.")
	game.saved_state = game.save_game()
	game._restore_game()
	_expect(_same_atmosphere(before, game.get_atmosphere_state()), "Reconstruction must preserve each live particle without storing sprite snapshots.")
	_expect(_app.open_route("game:presentation_lab"), "A real Lab detour must open.")
	await _settle()
	_expect(_app.open_route("game:bishoujo_afterlight"), "Return from Lab must restore the story host.")
	await _settle()
	game = _app.active_scene
	_expect(game.current_beat()["id"] == "the_keeper" and _same_atmosphere(before, game.get_atmosphere_state()), "Lab detour must restore the active infernal field and story time.")
	_seek(game, "a_hand_to_hold")
	_expect(game.get_atmosphere_state()["profile"] == "quiet_interior" and game._ambient_emitters.size() == 1, "The waking return must clear smoke, embers and sparks and restore quiet dust.")
	_pass_evidence["checks"].append("Quiet/relay/infernal profiles; world camera scale and shake; rear layering; uninterrupted dialogue; pause and locale stability; exact seeded replay and Lab restoration; clean waking return")


func _transmission_checks(game: Control) -> void:
	for language: String in ["en", "ko"]:
		game.set_language(language)
		_seek(game, "eira_on_the_relay")
		var state: Dictionary = game.get_voice_state()
		_expect(state["speaker_id"] == "eira" and state["status"] == "ready" and state["processing"]["processing"], "Existing Eira recording must use transmission DSP in " + language)
		_expect(game.get_atmosphere_state()["profile"] == "relay_alcove", "The relay must own a restrained cool atmosphere.")
		_expect(game._text_audio._voice_player.bus == game._voice_effects.get_output_bus() and game._text_audio._typing_player.bus == &"Master", "Only voice must route through the private processor.")
		_expect(game._reveal.sample()["phase"] == "holding" and game._text_audio.get_state()["active_mode"] == "voice", "Transmission retains full subtitles and exclusive voice playback.")
		var before_count: int = game._text_audio.get_state()["typing_play_count"]
		game._process(0.2)
		_expect(game._text_audio.get_state()["typing_play_count"] == before_count, "Transmission voice must not introduce typing ticks.")
		game._toggle_pause()
		await create_timer(0.15).timeout
		_expect(game._text_audio.get_state()["paused"] and game.get_voice_state()["processing"]["processing"], "Menu pause retains the same voice processing route.")
		game._toggle_pause()
		var source: String = state["source_revision"]
		game._begin_text_audio()
		_expect(game.get_voice_state()["source_revision"] == source and game.get_voice_state()["processing"]["processing"], "Replay must reuse the same recording revision and reapply transmission DSP.")
		game._next()
		state = game.get_voice_state()
		_expect(state["voice_policy"] == "none" and not state["processing"]["processing"] and state["playback"]["active_mode"] == "typing", "Protagonist reply while Eira remains visible must be explicitly unvoiced and dry.")
		_seek(game, "eira_on_the_relay")
		game.set_language("ko" if language == "en" else "en")
		_expect(game.get_voice_state()["processing"]["processing"], "Language change must bind the new recording through the same processor.")
	_seek(game, "the_return_channel")
	game._process(0.5)
	var source: String = game.get_voice_state()["source_revision"]
	_expect(_app.open_route("game:presentation_lab"), "Voice Lab detour must open.")
	await _settle()
	_expect(_app.open_route("game:bishoujo_afterlight"), "Voice Lab detour must restore.")
	await _settle()
	game = _app.active_scene
	_expect(game.current_beat()["id"] == "the_return_channel" and game.get_voice_state()["source_revision"] == source and game.get_voice_state()["processing"]["processing"], "Transmission processing must resume on a new isolated bus after a Lab detour.")
	_seek(game, "riko_on_the_glass")
	var emitter: Control = game._ambient_emitters[0]
	game._process(1.0)
	_expect(emitter._camera == game._world_transform() and emitter._camera != game._cast_transform(), "Cast Pan must move the cast without dragging environmental particles.")
	_seek(game, "relay_return")
	_expect(not game.get_voice_state()["processing"]["processing"] and not game._text_audio.get_state()["voice_playing"], "Ending the relay call clears processing and previous speech.")
	_seek(game, "the_keeper")
	_expect(game.get_voice_state()["speaker_id"] == "keeper" and not game.get_voice_state()["processing"]["processing"], "Physical speakers must stay dry after the call.")
	_pass_evidence["checks"].append("Existing Eira EN/KO voice-only private bus; full subtitle reveal; no typing overlap; dry protagonist and physical voices; pause, replay, language and Lab lifecycle; Cast Pan independent of atmosphere; no recording/generation edits")


func _same_atmosphere(a: Dictionary, b: Dictionary) -> bool:
	if a["profile"] != b["profile"] or a["layers"].keys() != b["layers"].keys(): return false
	for key: String in a["layers"]:
		var left: Dictionary = a["layers"][key]
		var right: Dictionary = b["layers"][key]
		if not is_equal_approx(float(left["elapsed"]), float(right["elapsed"])) or left["particle_count"] != right["particle_count"]: return false
		for index in left["particles"].size():
			if not left["particles"][index]["position"].is_equal_approx(right["particles"][index]["position"]): return false
	return true


func _composed_captures(game: Control) -> void:
	if not _capture_enabled: return
	for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window_size
		for cue: Dictionary in [{"id": "no_ordinary_post", "time": 1.2}, {"id": "the_keeper", "time": 0.24}, {"id": "the_return_channel", "time": 0.8}, {"id": "a_hand_to_hold", "time": 4.0}]:
			_seek(game, cue["id"])
			game._process(cue["time"])
			game._render()
			await _settle()
			await RenderingServer.frame_post_draw
			var path := PASS_OUTPUT.path_join(str(cue["id"]) + "-" + str(window_size.x) + ".png")
			DirAccess.make_dir_recursive_absolute(PASS_OUTPUT)
			var frame := root.get_texture().get_image()
			_expect(frame.save_png(path) == OK, "Native composition capture must persist.")
			_pass_evidence["captures"].append({"path": path, "sha256": FileAccess.get_sha256(path), "size": [frame.get_width(), frame.get_height()]})
