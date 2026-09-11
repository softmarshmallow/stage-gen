extends "res://qa/text_reveal_audio_checks.gd"

## Offline policy and real host playback proof. Synthesized streams are fixtures,
## never evidence that a generated performance sounds correct.
const POLICY = preload("res://games/bishoujo_afterlight/voice/voice_policy.gd")
const EPISODE = preload("res://games/bishoujo_afterlight/story_beats.gd")
const DIRECTORY := "res://games/bishoujo_afterlight/voice/"
const EXPECTED_SPEAKERS := {"nami": 14, "yuzu": 9, "sena": 5, "riko": 6, "eira": 4, "keeper": 2}
const NONE_BEATS := ["undeliverable", "across_the_threshold", "one_more_minute", "reading_room", "hold_the_message", "a_voice_in_the_glass", "one_private_question", "relay_return", "scarlet_pressure", "between_addresses", "the_unlit_house", "a_name_is_not_consent", "the_room_refuses", "follow_the_warmth", "the_return", "a_hand_to_hold", "back_to_the_house", "the_next_arrival"]
var _policy_data: Dictionary
var _casting: Dictionary
var _sets: Dictionary
var _inventory: Array
var _fixture_manifest: Dictionary
var _fixture_voices := {"en": {}, "ko": {}}
var _fixtures_enabled := false
var _evidence := {"schema_version": 1, "listening_verdict": "not_performed", "generated_streams": [], "checks": [], "source_sha256": {}}


func _run() -> void:
	_policy_checks()
	_removed_line_checks()
	await _component_checks()
	if "--policy-only" not in OS.get_cmdline_user_args():
		await _host_checks()
		_recording_checks()
		if "--capture" in OS.get_cmdline_user_args() and _evidence["generated_streams"].size() == 80:
			await _actual_playback_checks()
	await create_timer(0.2).timeout
	_evidence["errors"] = _errors
	for path: String in [DIRECTORY + "voice_policy.gd", DIRECTORY + "voices.json", DIRECTORY + "cast.json", DIRECTORY + "manifest.json", "res://games/bishoujo_afterlight/story.gd", "res://games/bishoujo_afterlight/root.gd", "res://games/bishoujo_afterlight/story_beats.gd", "res://games/bishoujo_afterlight/text/en.json", "res://games/bishoujo_afterlight/text/ko.json", "res://addons/game_presentation/audio/text_reveal_audio.gd"]:
		if FileAccess.file_exists(path): _evidence["source_sha256"][path] = FileAccess.get_sha256(path)
	DirAccess.make_dir_recursive_absolute("res://qa/voiceovers")
	var file := FileAccess.open("res://qa/voiceovers/validation.json", FileAccess.WRITE)
	if file != null: file.store_string(JSON.stringify(_evidence, "  ", true) + "\n")
	for issue: String in _errors: printerr("FAIL Afterlight Voiceovers: " + issue)
	if _errors.is_empty(): print("PASS Afterlight Voiceovers: independent text classification, casting revisions, explicit silence and recording states, playback policy and host lifecycle; listening not performed")
	quit(0 if _errors.is_empty() else 1)


func _json(path: String) -> Dictionary:
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	_expect(value is Dictionary, "Expected dictionary document: " + path)
	return value if value is Dictionary else {}


func _policy_checks() -> void:
	_policy_data = _json(DIRECTORY + "voices.json")
	_casting = _json(DIRECTORY + "cast.json")
	_sets = {"en": _json("res://games/bishoujo_afterlight/text/en.json"), "ko": _json("res://games/bishoujo_afterlight/text/ko.json")}
	var policy := POLICY.new()
	_expect(policy.configure(_policy_data, _casting, {}, EPISODE.BEATS, _sets).is_empty(), "The authored voice inventory must configure offline.")
	_inventory = policy.get_inventory()["lines"]
	_expect(EPISODE.BEATS.size() == 57 and _inventory.size() == 116, "The 57-beat story plus alternate reply must produce 58 policy records per language.")
	var initial_status: Dictionary = policy.get_status_report()
	_expect(initial_status["lines"].size() == 116 and initial_status["counts"]["none"] == 36 and initial_status["counts"]["pending"] == 80 and initial_status["counts"]["ready"] == 0, "The exported status report must distinguish 36 intentional exclusions from 80 pending recordings.")
	for language: String in ["en", "ko"]:
		var counts := {}
		var none_beats := {}
		var choices := 0
		var total := 0
		for item: Dictionary in _inventory:
			if item["language"] != language: continue
			total += 1
			_expect(str(item["line_id"]).begins_with("episode."), "Menus, demos and UI keys must be absent from the voice inventory.")
			_expect(item["display_text"] == _sets[language][item["line_id"]], "Voice inventory must preserve the actual localized display text.")
			if item["voice_policy"] == "generated":
				counts[item["speaker_id"]] = int(counts.get(item["speaker_id"], 0)) + 1
				_expect(item["beat_id"] not in NONE_BEATS and item["kind"] != "choice_option", "Protagonist, narration and choice labels must never be generated: " + item["line_id"])
				_expect(policy.resolve(item["line_id"], language)["status"] == "pending", "Absent recording must remain pending rather than intentional none.")
			else:
				_expect(item["speaker_id"] == "protagonist", "Every excluded line must be explicitly owned by the protagonist voice policy.")
				if item["kind"] == "choice_option": choices += 1
				else: none_beats[item["beat_id"]] = true
				_expect(policy.resolve(item["line_id"], language, _tone(0.05))["status"] == "none", "Intentional none must win over any supplied stream.")
		_expect(total == 58 and counts == EXPECTED_SPEAKERS and choices == 0 and none_beats.size() == 18, "Independent localized line counts must match the reviewed six-speaker audit, excluding choice labels: " + language)
		for beat: String in NONE_BEATS: _expect(none_beats.has(beat), "Explicit none is missing for " + language + "/" + beat)
		_expect(policy.resolve("episode.a_hand_to_hold", language)["voice_policy"] == "none", "Nami's displayed portrait must not turn the courier's narration into her speech.")
		_expect(policy.resolve("episode.nami_beyond_the_wall", language)["speaker_id"] == "nami", "Nami's offscreen rescue line must use her voice despite no visible actor.")
	_expect(policy.resolve("ui.next", "en")["status"] == "failed", "An unknown UI key must not resolve to a recording.")
	var key := "episode.no_ordinary_post"
	var revision: String = policy.resolve(key, "en")["source_revision"]
	var recording := {"status": "ready", "source_revision": revision, "path": "res://qa/voiceovers/not-a-recording.mp3"}
	var manifest := {"schema_version": 1, "lines": {"en": {key: recording}}}
	_expect(policy.configure(_policy_data, _casting, manifest, EPISODE.BEATS, _sets).is_empty(), "An offline ready fixture must configure.")
	var tone := _tone(0.2)
	_expect(policy.resolve(key, "en", tone)["status"] == "ready" and policy.resolve(key, "en", tone)["stream"] == tone, "A current ready recording can be supplied as a prepared AudioStream.")
	_expect(policy.resolve(key, "en")["status"] == "missing", "A missing ready file must fail to missing without pretending intentional silence.")
	for status: String in ["pending", "failed", "missing", "stale"]:
		recording["status"] = status
		policy.configure(_policy_data, _casting, manifest, EPISODE.BEATS, _sets)
		_expect(policy.resolve(key, "en", tone)["status"] == status and policy.resolve(key, "en", tone)["stream"] == null, "Supplied streams must not bypass recording status: " + status)
	recording["status"] = "ready"
	recording["source_revision"] = "old_revision"
	policy.configure(_policy_data, _casting, manifest, EPISODE.BEATS, _sets)
	_expect(policy.resolve(key, "en", tone)["status"] == "stale", "Old text/casting lineage must not activate a supplied recording.")
	recording["source_revision"] = revision
	var changed_sets := _sets.duplicate(true)
	changed_sets["en"][key] += " Changed words."
	policy.configure(_policy_data, _casting, manifest, EPISODE.BEATS, changed_sets)
	_expect(policy.resolve(key, "en", tone)["status"] == "stale", "Display text edits must invalidate recordings.")
	var changed_cast := _casting.duplicate(true)
	changed_cast["voices"]["nami"]["en"]["provider_voice"] = "different_fixture_voice"
	policy.configure(_policy_data, changed_cast, manifest, EPISODE.BEATS, _sets)
	_expect(policy.resolve(key, "en", tone)["status"] == "stale", "Casting edits must invalidate recordings.")
	var changed_policy := _policy_data.duplicate(true)
	changed_policy["speech_scripts"] = {"en": {key: "A separately authored performance script."}}
	policy.configure(changed_policy, _casting, manifest, EPISODE.BEATS, _sets)
	_expect(policy.resolve(key, "en", tone)["status"] == "stale" and policy.resolve(key, "en")["display_text"] == _sets["en"][key], "Speech scripts change recording lineage without changing display text.")
	var broken := _policy_data.duplicate(true)
	broken["speakers"]["protagonist"]["voice_policy"] = "generated"
	var before := policy.get_inventory()
	_expect(not policy.configure(broken, _casting, {}, EPISODE.BEATS, _sets).is_empty() and before == policy.get_inventory(), "A rejected protagonist policy must leave the prior valid inventory intact.")
	_evidence["checks"].append("116 localized policy records; 80 generated clips; 18 excluded beats per language; choice labels omitted; six-speaker counts and text exceptions verified independently")
	_evidence["checks"].append("ready/pending/missing/failed/stale/none are distinct; supplied streams obey policy and lineage; display, speech-script and casting changes invalidate old recordings")


func _host_checks() -> void:
	_fixture_manifest = {"schema_version": 1, "lines": {"en": {}, "ko": {}}}
	for item: Dictionary in _inventory:
		if item["voice_policy"] != "generated": continue
		var language: String = item["language"]
		var key: String = item["line_id"]
		_fixture_manifest["lines"][language][key] = {"status": "ready", "source_revision": item["source_revision"]}
		_fixture_voices[language][key] = _tone(3.0 if language == "en" else 4.0)
	_fixtures_enabled = true
	root.size = Vector2i(1280, 900)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	var game: Control = _app.active_scene
	_expect(_app.selected_game_id == "bishoujo_afterlight" and game._load_errors.is_empty(), "The real Afterlight host must initialize with prepared voice fixtures.")
	if _app.selected_game_id != "bishoujo_afterlight" or not game._load_errors.is_empty(): return
	_expect(game.get_voice_state()["status"] == "none" and game._reveal.sample()["phase"] == "revealing", "Protagonist monologue must retain typewriter reveal and explicit none policy.")
	game._process(0.12)
	_expect(_plays(game._text_audio) > 0 and not game._text_audio.get_state()["voice_playing"], "The none policy must use the host's configured typing fallback without a voice.")
	_reach(game, "eyes_on_nami")
	_expect(game.get_voice_state()["waiting_for_cinematic"] and not game._text_audio.get_state()["voice_playing"], "Eye-opening motion must retain a pending ready voice until its caption is visible.")
	game._process(0.01)
	_expect(not game._dialogue.visible and not game._text_audio.get_state()["voice_playing"], "An unrevealed cinematic caption must not speak ahead of the picture.")
	game._next()
	_expect(game.current_beat()["id"] == "eyes_on_nami" and game._dialogue.visible and game._reveal.sample()["phase"] == "holding" and game._text_audio.get_state()["voice_playing"], "Completing cinematic motion must show the entire voiced caption and begin one voice without advancing the beat.")
	_reach(game, "no_ordinary_post")
	_expect(game._reveal.sample()["phase"] == "holding" and _plays(game._text_audio) == 0 and game._text_audio.get_state()["active_mode"] == "voice", "A ready ordinary line must show all text at entry, with no typing audio.")
	var key: String = game._resolved_text_key()
	_expect(game._text_audio._voice_player.stream == _fixture_voices[game.get_language()][key], "The actual player must hold the stream selected for the resolved line and language.")
	await create_timer(0.18).timeout
	var position: float = game._voice_position()
	_expect(position > 0.05, "Actual playback must advance independently of the frozen story QA clock.")
	game._toggle_pause()
	var paused_position: float = game._voice_position()
	_evidence["pause_playback"] = {"before": position, "after": paused_position, "raw_position": game._text_audio._voice_player.get_playback_position(), "raw_playing": game._text_audio._voice_player.playing, "raw_paused": game._text_audio._voice_player.stream_paused}
	_expect(absf(paused_position - position) < 0.06, "Pausing must retain a nonzero playback position: " + str(_evidence["pause_playback"]))
	await create_timer(0.2).timeout
	_expect(absf(game._voice_position() - paused_position) < 0.06 and game._text_audio.get_state()["paused"], "The pause menu must freeze actual voice playback.")
	var before_elapsed: float = game._elapsed
	game._process(5.0)
	_expect(is_equal_approx(game._elapsed, before_elapsed), "Paused story clocks must remain frozen with voice.")
	game._toggle_pause()
	var same_language: String = game.get_language()
	var before_same: float = game._voice_position()
	game.set_language(same_language)
	_expect(game._voice_position() >= before_same - 0.06, "Selecting the current language must retain the recording position.")
	game.set_language("ko" if same_language == "en" else "en")
	_expect(game._voice_position() < 0.08 and game._text_audio._voice_player.stream == _fixture_voices[game.get_language()][key] and game._reveal.sample()["phase"] == "holding", "A real language change must show full translated text and start that language's recording at zero.")
	await create_timer(0.16).timeout
	var before_checkpoint_pause: float = game._voice_position()
	_expect(before_checkpoint_pause > 0.05, "The checkpoint must be taken from a recording that has actually advanced.")
	game._toggle_pause()
	var saved: Dictionary = game.save_game()
	_expect(float(saved["voice_position_seconds"]) > 0.05, "Pausing before a Lab detour must retain the actual nonzero recording position.")
	var old_audio: WeakRef = weakref(game._text_audio)
	_expect(_app.open_route("game:presentation_lab"), "A voiced line must permit a real Lab detour.")
	await _settle()
	_expect(old_audio.get_ref() == null, "Leaving the story must free and stop its audio players.")
	_expect(_app.open_route("game:bishoujo_afterlight"), "The story must resume its voiced checkpoint after Lab.")
	await _settle()
	game = _app.active_scene
	_expect(game._load_errors.is_empty() and game.current_beat()["id"] == "no_ordinary_post" and not game._paused, "Returning from Lab must resume the same voiced line under the host's existing resume-on-return policy.")
	_evidence["checkpoint_playback"] = {"saved": saved["voice_position_seconds"], "initial_seek": game._text_audio._voice_position_seconds, "resumed": game._voice_position(), "typing_play_count": _plays(game._text_audio)}
	_expect(is_equal_approx(game._text_audio._voice_position_seconds, float(saved["voice_position_seconds"])) and game._voice_position() >= float(saved["voice_position_seconds"]) - 0.03 and _plays(game._text_audio) == 0, "Checkpoint history replay must be silent and seek exactly to the saved recording position before resuming: " + str(_evidence["checkpoint_playback"]))
	game.saved_state = game.save_game()
	game.saved_state["voice_source_revision"] = "an_older_recording_revision"
	game._restore_game()
	_expect(is_zero_approx(game._text_audio._voice_position_seconds) and game._text_audio.get_state()["voice_playing"], "A restored checkpoint from a different recording revision must start current audio at zero, never seek into unrelated speech.")
	var prior_stream: AudioStream = game._text_audio._voice_player.stream
	game._next()
	_expect(game.current_beat()["id"] == "a_glass_record" and game._text_audio._voice_player.stream != prior_stream and game._text_audio._typing_player.playing == false, "Explicit advance must replace the sole voice player without overlap or typing.")
	_reach(game, "no_forwarding_address")
	_expect(game._manpu_event_time == 0.0 and not game._cast._manpu.one_shots().is_empty(), "After-reveal Manpu must fire at full-text entry for a voiced line.")
	_reach(game, "courier_offer")
	_expect(game._choice_pending() and game._reveal.sample()["phase"] == "holding", "A voiced choice prompt must reveal its original choices immediately.")
	game._choose("tea_first")
	_expect(game._resolved_text_key() == "episode.courier_reply.tea_first" and game._text_audio._voice_player.stream == _fixture_voices[game.get_language()][game._resolved_text_key()], "The selected alternate reply must bind its own recorded text ID.")
	# A short actual fixture ends while the story stays on the same line.
	_fixture_voices[game.get_language()][game._resolved_text_key()] = _tone(0.12)
	game.content["voiceovers"] = _fixture_voices
	game._begin_text_audio()
	await create_timer(0.35).timeout
	game._process(0.1)
	_expect(game.current_beat()["id"] == "courier_reply" and game._voice_position() == -1.0 and _plays(game._text_audio) == 0, "Finishing a recording must neither advance the story nor fall back to typing.")
	_expect(_app.open_route("game:presentation_lab"), "A completed recording must also checkpoint through Lab.")
	await _settle()
	_expect(_app.open_route("game:bishoujo_afterlight"), "A completed recording must restore from Lab.")
	await _settle()
	game = _app.active_scene
	_expect(game._voice_position() == -1.0 and not game._text_audio.get_state()["voice_playing"], "Finished recording checkpoints must never restart their voice.")
	# A missing generated recording must retain the old text/fallback behavior.
	key = game._resolved_text_key()
	_fixture_manifest["lines"][game.get_language()][key]["status"] = "missing"
	game.voice_policy.configure(_policy_data, _casting, _fixture_manifest, EPISODE.BEATS, _sets)
	game._set_reveal_fraction(0.0)
	game._begin_text_audio()
	game._process(0.12)
	_expect(game.get_voice_state()["status"] == "missing" and game._reveal.sample()["phase"] == "revealing" and _plays(game._text_audio) > 0, "Unavailable generated audio must visibly remain missing and use the configured fallback.")
	# Explicit host silence remains authoritative over a prepared recording.
	_fixture_manifest["lines"][game.get_language()][key]["status"] = "ready"
	game.voice_policy.configure(_policy_data, _casting, _fixture_manifest, EPISODE.BEATS, _sets)
	game.current_beat()["text_audio"] = {"mode": "silent"}
	game._begin_text_audio()
	_expect(game._text_audio.get_state()["active_mode"] == "silent" and not game._text_audio.get_state()["voice_playing"], "A host per-beat silent override must suppress a ready recording.")
	game.current_beat().erase("text_audio")
	_reach(game, "a_hand_to_hold")
	_expect(game.get_voice_state()["status"] == "none" and not game._text_audio.get_state()["voice_playing"], "The close Nami portrait must leave the courier's narration unvoiced in actual play.")
	_reach(game, "a_touch_that_stays")
	_expect(game.contact_target()["ready"] and game._reveal.sample()["phase"] == "holding" and game._text_audio.get_state()["voice_playing"], "A voiced contact line must show full text and make its point gate ready at entry.")
	game._next()
	_expect(game.current_beat()["id"] == "a_touch_that_stays" and not game._contact.is_confirmed(), "Voice readiness must never bypass the required contact with Space/Next.")
	_expect(game._try_contact(game.contact_target()["center"]), "The recorded contact line must still accept the explicit fingertip interaction.")
	game._process(1.0)
	_expect(game.current_beat()["id"] == "only_a_second" and game._text_audio._voice_player.stream == _fixture_voices[game.get_language()][game._resolved_text_key()], "Completed contact feedback must stop the prior recording and start the next line exactly once.")
	game._restart()
	_expect(game.current_beat()["id"] == "undeliverable" and not game._text_audio.get_state()["voice_playing"], "Restart must stop the current recording and return to unvoiced narration.")
	_expect(game._load_errors.is_empty(), "Voice fixtures must not introduce runtime validation errors.")
	_app.queue_free()
	await _settle_disposed()
	_fixtures_enabled = false
	_evidence["checks"].append("Actual synthesized playback: ready full text, cinematic caption timing, no typing overlap, pause, locale restart, checkpoint resume/finished sentinel, alternate reply, no auto advance, explicit silence, missing fallback, required contact and restart")


func _removed_line_checks() -> void:
	var policy := POLICY.new()
	var records := {"schema_version": 1, "lines": {"en": {}, "ko": {}}}
	for item: Dictionary in _inventory:
		if item["line_id"] == "episode.no_forwarding_address":
			records["lines"][item["language"]][item["line_id"]] = {"status": "ready", "source_revision": item["source_revision"], "path": "res://qa/voiceovers/removed-recording.mp3"}
	var reduced: Array = []
	for beat: Dictionary in EPISODE.BEATS:
		if beat["id"] not in ["no_forwarding_address", "a_hand_to_hold"]: reduced.append(beat)
	_expect(policy.configure(_policy_data, _casting, records, reduced, _sets).is_empty(), "Removing a beat must not make its retained well-formed speech annotations or recordings fatal.")
	var inventory: Array = policy.get_inventory()["lines"]
	_expect(inventory.size() == 112, "Removing two beats must remove four localized policy entries.")
	for item: Dictionary in inventory:
		_expect(item["beat_id"] not in ["no_forwarding_address", "a_hand_to_hold"], "Removed lines must never enter the current generation inventory.")
	var status: Dictionary = policy.get_status_report()
	_expect(status.get("unused_configuration", []).size() == 3 and status.get("unused_recordings", []).size() == 2, "The offline report must expose two unused localized scripts, one unused override and two unused recordings.")
	var bindings: Dictionary = policy.bind_voiceovers()
	for language: String in ["en", "ko"]:
		_expect(not bindings[language].has("episode.no_forwarding_address") and policy.resolve("episode.no_forwarding_address", language, _tone(0.1)).get("reason") == "unknown_line", "A retained recording for a removed beat must never activate in current gameplay.")
	_evidence["checks"].append("Removed beats leave well-formed annotations/media inactive and offline-reportable, without blocking the host or entering current generation/bindings")


func _freeze_route(node: Node) -> void:
	super._freeze_route(node)
	if _fixtures_enabled and node.has_method("get_voice_state"):
		_expect(node.voice_policy.configure(_policy_data, _casting, _fixture_manifest, EPISODE.BEATS, _sets).is_empty(), "Fixture casting must configure before the scene enters its first beat.")
		node.content["voiceovers"] = _fixture_voices
		var factory: Callable = node.content_factory
		node.content_factory = func(words: RefCounted) -> Dictionary:
			var content: Dictionary = factory.call(words)
			content["voiceovers"] = _fixture_voices
			return content


func _settle_disposed() -> void:
	_app = null
	for frame in 3: await process_frame


func _recording_checks() -> void:
	if not FileAccess.file_exists(DIRECTORY + "manifest.json"):
		_expect("--require-recordings" not in OS.get_cmdline_user_args(), "The complete pass requires an installed recording manifest.")
		return
	var policy := POLICY.new()
	_expect(policy.load_project(EPISODE.BEATS, _sets).is_empty(), "Current recording manifest must load.")
	var ready := 0
	for item: Dictionary in policy.get_inventory()["lines"]:
		if item["voice_policy"] != "generated": continue
		var resolved := policy.resolve(item["line_id"], item["language"])
		if resolved["status"] != "ready": continue
		ready += 1
		var stream: AudioStream = resolved["stream"]
		_expect(stream != null and stream.get_length() > 0.05, "Actual ready recordings must decode to positive-duration Godot AudioStreams.")
		_evidence["generated_streams"].append({"line_id": item["line_id"], "language": item["language"], "speaker_id": item["speaker_id"], "path": resolved["path"], "source_revision": item["source_revision"], "duration_seconds": stream.get_length(), "audio_sha256": FileAccess.get_sha256(resolved["path"])})
	if "--require-recordings" in OS.get_cmdline_user_args(): _expect(ready == 80, "The complete pass requires all 80 current localized recordings, got " + str(ready))
	var bindings: Dictionary = policy.bind_voiceovers()
	for language: String in ["en", "ko"]:
		if ready == 80: _expect(bindings[language].size() == 40, "Each locale must bind exactly its 40 distinct voiced text keys.")
		for item: Dictionary in _inventory:
			if item["language"] == language and item["voice_policy"] == "none":
				_expect(not bindings[language].has(item["line_id"]), "No protagonist or narration recording may enter the actual binding table.")


func _actual_playback_checks() -> void:
	var bus_index := AudioServer.bus_count
	AudioServer.add_bus(bus_index)
	AudioServer.set_bus_name(bus_index, "VoiceoverProof")
	var capture := AudioEffectCapture.new()
	capture.buffer_length = 4.0
	AudioServer.add_bus_effect(bus_index, capture)
	_evidence["actual_mixer"] = []
	_evidence["captures"] = []
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	var game: Control = _app.active_scene
	_expect(game._load_errors.is_empty(), "The installed voice pack must initialize in the actual root.")
	_reach(game, "no_ordinary_post")
	for language: String in ["en", "ko"]:
		root.size = Vector2i(1280, 900) if language == "en" else Vector2i(2560, 1800)
		game.set_language(language)
		game.current_beat()["text_audio"] = {"bus": "VoiceoverProof"}
		capture.clear_buffer()
		game._begin_text_audio()
		game._process(0.1)
		var state: Dictionary = game.get_voice_state()
		_expect(state["status"] == "ready" and state["playback"]["active_mode"] == "voice" and game._reveal.sample()["phase"] == "holding" and _plays(game._text_audio) == 0, "Installed " + language + " recording must play with full text and no typing.")
		await _voice_frame("full-text-" + language, game)
		await create_timer(1.4).timeout
		var samples := capture.get_buffer(capture.get_frames_available())
		var peak := 0.0
		var energy := 0.0
		for sample: Vector2 in samples:
			peak = maxf(peak, maxf(absf(sample.x), absf(sample.y)))
			energy += (sample.x * sample.x + sample.y * sample.y) * 0.5
		_expect(samples.size() > 10000 and peak > 0.0001, "The installed " + language + " MP3 must produce nonzero PCM through Godot's actual mixer.")
		_evidence["actual_mixer"].append({"language": language, "line_id": game._resolved_text_key(), "frames": samples.size(), "peak": peak, "rms": sqrt(energy / maxf(1.0, samples.size())), "voice_position_seconds": game._voice_position()})
		game._toggle_pause()
		var position: float = game._voice_position()
		await create_timer(0.2).timeout
		_expect(absf(game._voice_position() - position) < 0.04, "Pausing must stop the installed " + language + " recording at its current position.")
		await _voice_frame("paused-" + language, game)
		game._toggle_pause()
	game.current_beat().erase("text_audio")
	_app.queue_free()
	await _settle_disposed()
	await create_timer(0.1).timeout
	AudioServer.remove_bus(bus_index)
	_evidence["checks"].append("All 80 installed MP3s decoded by Godot with positive durations and source/hash checks; actual English/Korean mixer samples nonzero; native full-text and pause captures at 1x/2x; listening not performed")


func _voice_frame(label: String, game: Control) -> void:
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	var path := "res://qa/voiceovers/" + label + ".png"
	_expect(picture.get_size() == root.size and picture.save_png(path) == OK, "Native voice/full-text capture must save at the actual window size: " + label)
	_evidence["captures"].append({"file": path, "sha256": FileAccess.get_sha256(path), "size": [picture.get_width(), picture.get_height()], "language": game.get_language(), "beat_id": game.current_beat()["id"], "visible_characters": game._reveal.sample()["visible_characters"], "text": game._reveal.sample()["text"], "voice_state": game.get_voice_state()})
