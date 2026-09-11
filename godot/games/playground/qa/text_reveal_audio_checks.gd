extends SceneTree

## Audio policy/lifecycle proof plus the real episode's reveal and route wiring.
## Synthesized fixtures exercise playback; this is not a listening verdict.
var _errors: Array[String] = []
var _app: Control
var _force_episode_fallback := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	await _component_checks()
	await _capture_typing_preview()
	await _episode_checks()
	# Let the audio mixer reclaim stopped playbacks after accelerated QA clocks.
	await create_timer(0.2).timeout
	for issue: String in _errors: printerr("FAIL Text Reveal Audio: " + issue)
	if _errors.is_empty():
		print("PASS Text Reveal Audio: natural Unicode reveal, bounded cadence, silent jumps, pause, voice precedence and completion, explicit host modes, custom PCM, monologue/dialogue, Sigh Puff, language and Lab checkpoint continuity")
	quit(0 if _errors.is_empty() else 1)


func _component_checks() -> void:
	var audio: Node = load("res://addons/game_presentation/audio/text_reveal_audio.gd").new()
	root.add_child(audio)
	_expect(audio.configure({"min_interval_seconds": 0.08}).is_empty(), "Default fallback settings must initialize.")
	audio.begin("A \n한B")
	audio.update_reveal(1, 0.1)
	_expect(_plays(audio) == 1 and audio.get_state()["active_mode"] == "typing", "Natural Latin text must use the built-in fallback when no voice exists.")
	audio.update_reveal(3, 0.1)
	_expect(_plays(audio) == 1, "Spaces and line breaks must not emit typing audio.")
	audio.update_reveal(4, 0.1)
	_expect(_plays(audio) == 2, "A revealed Korean syllable must emit the same fallback.")
	audio.update_reveal(5, 0.01)
	_expect(_plays(audio) == 2, "Closely spaced glyphs must obey the configured cadence limit.")
	audio.update_reveal(5, 2.0)
	_expect(_plays(audio) == 2, "Holding finished text must never flush a deferred sound queue.")
	var prepared := false
	for player: Node in audio.get_children():
		if player is AudioStreamPlayer and player.stream is AudioStreamWAV:
			prepared = prepared or _pcm_has_signal(player.stream)
	_expect(prepared, "The built-in fallback must contain nonzero PCM samples in an actual audio stream.")
	audio.begin("Natural reveal should never play every skipped character.")
	var before := _plays(audio)
	audio.update_reveal(45, 3.0)
	_expect(_plays(audio) - before <= 1, "One long frame must produce at most one tick, with no burst catch-up.")
	before = _plays(audio)
	audio.sync_reveal(55)
	audio.update_reveal(55, 1.0)
	_expect(_plays(audio) == before, "A manual reveal jump must synchronize without sound or a later burst.")
	audio.begin("Paused and intentionally inaudible reveal.")
	before = _plays(audio)
	audio.set_paused(true)
	audio.update_reveal(3, 1.0)
	_expect(_plays(audio) == before and audio.get_state()["paused"], "Paused reveal must not schedule sound.")
	audio.set_paused(false)
	audio.sync_reveal(3)
	audio.update_reveal(6, 0.1, false)
	_expect(_plays(audio) == before, "The host must be able to advance a hidden or replayed reveal silently.")
	audio.update_reveal(8, 0.1)
	_expect(_plays(audio) == before + 1, "Audio must resume only for newly visible text after a silent update.")
	var custom := _tone(0.04)
	_expect(audio.configure({"mode": "typing", "typing_stream": custom}).is_empty(), "Hosts must be able to substitute their own typing stream.")
	audio.begin("Custom", _tone(0.4))
	audio.update_reveal(1, 0.1)
	_expect(audio.get_state()["active_mode"] == "typing" and not audio.get_state()["voice_playing"], "Explicit typing mode must override supplied voice.")
	var uses_custom := false
	for player: Node in audio.get_children():
		if player is AudioStreamPlayer and player.stream == custom: uses_custom = true
	_expect(uses_custom, "The configured stream must be bound to the actual typing player.")
	_expect(audio.configure({"mode": "silent"}).is_empty(), "Hosts must be able to disable all text audio.")
	audio.begin("Silence", _tone(0.4))
	before = _plays(audio)
	audio.update_reveal(4, 1.0)
	_expect(audio.get_state()["active_mode"] == "silent" and _plays(audio) == before and not audio.get_state()["voice_playing"], "Silent mode must disable both voice and fallback.")
	_expect(audio.configure({"mode": "auto"}).is_empty(), "Automatic voice-first policy must be selectable.")
	audio.begin("Voice remains authoritative after its stream ends.", _tone(0.16))
	before = _plays(audio)
	audio.update_reveal(1, 0.1)
	_expect(audio.get_state()["active_mode"] == "voice" and audio.get_state()["voice_playing"] and _plays(audio) == before, "A supplied voice must take precedence without simultaneous typing.")
	audio.set_paused(true)
	await create_timer(0.22).timeout
	_expect(not audio.get_state()["voice_finished"], "Pausing the menu must pause actual voice playback.")
	audio.set_paused(false)
	await create_timer(0.35).timeout
	audio.update_reveal(10, 0.2)
	_expect(audio.get_state()["voice_finished"] and audio.get_state()["active_mode"] == "voice" and _plays(audio) == before, "Finished voice must remain authoritative for the rest of its line, without fallback tail.")
	audio.begin("Previously finished voice", _tone(0.16), 5, -1.0)
	_expect(audio.get_state()["voice_finished"] and not audio.get_state()["voice_playing"], "A completed voice checkpoint must not restart the clip.")
	audio.stop()
	_expect(not audio.get_state()["voice_playing"], "Stopping or replacing a line must stop its voice.")
	audio.queue_free()
	await process_frame


func _episode_checks() -> void:
	# This original regression deliberately exercises missing-recording fallback;
	# voiceover_checks.gd covers prepared recordings and full-text voice behavior.
	_force_episode_fallback = true
	root.size = Vector2i(1280, 900)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	_expect(_app.selected_game_id == "bishoujo_afterlight", "Run this check with --game bishoujo_afterlight.")
	if _app.selected_game_id != "bishoujo_afterlight": return
	var game: Control = _app.active_scene
	_expect(game._load_errors.is_empty(), "Afterlight must initialize with its text-audio fallback enabled.")
	if not game._load_errors.is_empty(): return
	var audio: Node = game._text_audio
	_expect(_plays(audio) == 0, "Entering a beat must not play sound before text appears.")
	game._process(0.12)
	_expect(_plays(audio) > 0, "A naturally revealing protagonist monologue must produce fallback audio.")
	var before := _plays(audio)
	game._toggle_pause()
	game._process(1.0)
	_expect(audio.get_state()["paused"] and _plays(audio) == before, "The real menu must pause reveal audio with its text clock.")
	game._toggle_pause()
	game._next()
	_expect(_plays(audio) == before and game._reveal.sample()["phase"] == "holding", "Manual monologue reveal must be silent and stay on the same beat.")
	game._next()
	before = _plays(audio)
	game._next()
	_expect(_plays(audio) == before, "Fast-forwarding a cinematic must not emit accumulated typing sounds.")
	_reach(game, "no_ordinary_post")
	audio = game._text_audio
	before = _plays(audio)
	game._process(0.12)
	_expect(_plays(audio) > before, "Ordinary cast dialogue must use the same fallback.")
	before = _plays(audio)
	var saved_fraction: float = game.save_game()["reveal_fraction"]
	game.set_language("en" if game.get_language() == "ko" else "ko")
	_expect(_plays(audio) == 0 and audio.get_state()["visible_characters"] == game._reveal.sample()["visible_characters"] and is_equal_approx(float(game.save_game()["reveal_fraction"]), saved_fraction), "Language changes must silently synchronize the translated reveal.")
	var old_audio: WeakRef = weakref(audio)
	var checkpoint: Dictionary = game.save_game()
	_expect(_app.open_route("game:presentation_lab"), "Text playback must permit a real Lab detour.")
	await _settle()
	_expect(old_audio.get_ref() == null, "Leaving the episode must free its audio players.")
	_expect(_app.open_route("game:bishoujo_afterlight"), "The episode must restore after the Lab detour.")
	await _settle()
	game = _app.active_scene
	audio = game._text_audio
	_expect(game._load_errors.is_empty() and game.save_game()["beat_id"] == checkpoint["beat_id"] and is_equal_approx(float(game.save_game()["reveal_fraction"]), float(checkpoint["reveal_fraction"])), "The resumed episode must retain its exact text position.")
	_expect(_plays(audio) == 0, "Checkpoint history replay and current-text restoration must not make typing sounds.")
	game._process(0.12)
	_expect(_plays(audio) > 0, "A restored unfinished line must sound only its newly revealed text.")
	_reach(game, "no_forwarding_address")
	game._process(0.12)
	before = _plays(audio)
	game._next()
	_expect(_plays(audio) == before and game._cast._manpu.one_shots().size() > 0, "Silent manual reveal must still emit its authored after-reveal Sigh Puff.")
	game._next()
	game._next()
	game._choose("tea_first")
	_expect(game.current_beat()["id"] == "courier_reply", "The choice response must be reached normally.")
	for frame in 150: game._process(0.02)
	_expect(game._reveal.sample()["phase"] == "holding" and game._manpu_event_time >= 0.0 and _plays(audio) > 0, "Natural response typing and its after-reveal event must coexist.")
	game.content["voiceovers"] = {game.get_language(): {game._resolved_text_key(): _tone(0.24)}}
	var ready_manifest := {"schema_version": 1, "lines": {game.get_language(): {game._resolved_text_key(): {"status": "ready", "source_revision": game.voice_policy.resolve(game._resolved_text_key(), game.get_language())["source_revision"]}}}}
	_configure_episode_voice_policy(game, ready_manifest)
	game._begin_text_audio()
	await create_timer(0.08).timeout
	game._process(0.1)
	_expect(audio.get_state()["active_mode"] == "voice" and _plays(audio) == 0 and float(game.save_game()["voice_position_seconds"]) > 0.0, "The host's localized resolved-text binding must prefer voice and checkpoint its playback position.")
	await create_timer(0.32).timeout
	_expect(float(game.save_game()["voice_position_seconds"]) == -1.0, "The host must preserve completed voice without replaying it on resume.")
	game.current_beat()["text_audio"] = {"mode": "silent"}
	game._begin_text_audio()
	_expect(audio.get_state()["active_mode"] == "silent" and not audio.get_state()["voice_playing"], "A host-authored per-beat silent override must suppress even an available voice.")
	_expect(game._load_errors.is_empty(), "Text audio must not introduce episode validation errors.")
	_app.queue_free()
	for frame in 3: await process_frame
	_force_episode_fallback = false


func _capture_typing_preview() -> void:
	var bus_index := AudioServer.bus_count
	AudioServer.add_bus(bus_index)
	AudioServer.set_bus_name(bus_index, "TextAudioProof")
	var capture := AudioEffectCapture.new()
	capture.buffer_length = 5.0
	AudioServer.add_bus_effect(bus_index, capture)
	var audio: Node = load("res://addons/game_presentation/audio/text_reveal_audio.gd").new()
	root.add_child(audio)
	audio.configure({"bus": "TextAudioProof", "typing_volume_db": -18.0})
	var text := "A letter arrived.\nWho sent it?"
	audio.begin(text)
	for index in text.length():
		audio.update_reveal(index + 1, 0.08)
		await create_timer(0.08).timeout
	await create_timer(0.1).timeout
	var frames := capture.get_buffer(capture.get_frames_available())
	var peak := 0.0
	var pcm := PackedByteArray()
	pcm.resize(frames.size() * 4)
	for index in frames.size():
		peak = maxf(peak, maxf(absf(frames[index].x), absf(frames[index].y)))
		pcm.encode_s16(index * 4, int(clampf(frames[index].x, -1.0, 1.0) * 32767.0))
		pcm.encode_s16(index * 4 + 2, int(clampf(frames[index].y, -1.0, 1.0) * 32767.0))
	_expect(frames.size() > 1000 and peak > 0.0001 and peak < 0.9, "The actual mixer must capture nonzero, unclipped default typing output.")
	var preview := AudioStreamWAV.new()
	preview.format = AudioStreamWAV.FORMAT_16_BITS
	preview.stereo = true
	preview.mix_rate = int(AudioServer.get_mix_rate())
	preview.data = pcm
	var directory := "res://qa/text-audio"
	_expect(DirAccess.make_dir_recursive_absolute(directory) == OK and preview.save_to_wav(directory.path_join("default-typing.wav")) == OK, "The actual typing mix must save as an auditionable preview.")
	print("Text Reveal Audio preview: ", ProjectSettings.globalize_path(directory.path_join("default-typing.wav")), "; peak=", peak)
	audio.queue_free()
	await create_timer(0.1).timeout
	AudioServer.remove_bus(bus_index)


func _tone(duration: float) -> AudioStreamWAV:
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = 22050
	var samples := int(duration * stream.mix_rate)
	var pcm := PackedByteArray()
	pcm.resize(samples * 2)
	for index in samples:
		pcm.encode_s16(index * 2, int(sin(TAU * 440.0 * index / stream.mix_rate) * 2000.0))
	stream.data = pcm
	return stream


func _pcm_has_signal(stream: AudioStreamWAV) -> bool:
	for value in stream.data:
		if value != 0: return true
	return false


func _plays(audio: Node) -> int:
	return int(audio.get_state()["typing_play_count"])


func _reach(game: Control, beat_id: String) -> void:
	for step in 100:
		if game.current_beat()["id"] == beat_id: return
		if game.current_beat().get("type") == "contact":
			game._next()
			_expect(game._try_contact(game.contact_target()["center"]), "Audio traversal must fulfill the required contact.")
			game._process(1.0)
		elif game._choice_pending():
			game._next()
			game._choose("help_first")
		else: game._next()
	_expect(false, "The episode could not reach " + beat_id)


func _freeze_route(node: Node) -> void:
	if node.has_method("current_beat"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)
		if _force_episode_fallback and node.has_method("get_voice_state"):
			_configure_episode_voice_policy(node, {})
			node.content["voiceovers"] = {}


func _configure_episode_voice_policy(game: Control, manifest: Dictionary) -> void:
	var directory := "res://games/bishoujo_afterlight/"
	var policy: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(directory + "voice/voices.json"))
	var casting: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(directory + "voice/cast.json"))
	var sets := {}
	for language: String in ["en", "ko"]:
		sets[language] = JSON.parse_string(FileAccess.get_file_as_string(directory + "text/" + language + ".json"))
	_expect(game.voice_policy.configure(policy, casting, manifest, game.beats, sets).is_empty(), "The focused audio fixture must configure the host's explicit recording policy.")


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _app.active_scene != null: _app.active_scene.set_process(false)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
