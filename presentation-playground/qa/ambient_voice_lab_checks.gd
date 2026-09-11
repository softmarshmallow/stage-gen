extends SceneTree

## Focused host integration and optional native captures; no provider calls.
const OUTPUT := "res://qa/ambient-voice-lab"
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false
var _evidence := {"schema_version": 1, "captures": [], "checks": [], "source_sha256": {}}


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Ambient/audio Lab captures require a native renderer.")
		quit(2)
		return
	node_added.connect(_freeze)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	_expect(_app.selected_game_id == "presentation_lab", "Run the check with --game presentation_lab.")
	if _app.selected_game_id != "presentation_lab":
		quit(2)
		return
	var baseline_buses := AudioServer.bus_count
	for scale in [1, 2]:
		root.size = Vector2i(1280, 900) * scale
		await _particles(scale)
		await _voice(scale, baseline_buses)
		_expect(_app.open_route("effects_menu"), "Both studies must return to the Afterlight effects collection.")
		await _settle()
		_app.active_scene.set_language("en" if scale == 1 else "ko")
		await _capture("effects-menu-" + str(scale))
	_app.queue_free()
	_app = null
	for frame in 3: await process_frame
	_expect(AudioServer.bus_count == baseline_buses, "Exiting both studies must leave no private audio bus behind.")
	for path: String in ["res://games/presentation_lab/afterlight/ambient_particles_study.gd", "res://games/presentation_lab/afterlight/transmission_voice_study.gd", "res://games/presentation_lab/afterlight/effects_menu.gd", "res://games/presentation_lab/root.gd", "res://games/bishoujo_afterlight/atmosphere_profile.gd", "res://addons/game_presentation/effects/particles/ambient_particles.gd", "res://addons/game_presentation/audio/voice_effects.gd", "res://addons/game_presentation/audio/text_reveal_audio.gd"]:
		_evidence["source_sha256"][path] = FileAccess.get_sha256(path)
	_evidence["errors"] = _errors
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	var file := FileAccess.open(OUTPUT.path_join("validation.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(_evidence, "  ", true) + "\n")
	file.close()
	for issue: String in _errors: printerr("FAIL ambient/audio Lab: " + issue)
	if _errors.is_empty(): print("PASS ambient/audio Lab: two native sizes, real control input, seeded particle replay/density/pause/drain/world camera, same-source dry/wet switching, voice pause/language/replay/cleanup, separate routes and bilingual controls")
	quit(0 if _errors.is_empty() else 1)


func _particles(scale: int) -> void:
	_expect(_app.open_route("ambient_particles_study"), "Ambient Particles must be a Lab-owned route.")
	await _settle()
	var study: Control = _app.active_scene
	_expect(study._load_errors.is_empty(), "Ambient fixture must initialize: " + str(study._load_errors))
	if not study._load_errors.is_empty(): return
	study.set_language("en" if scale == 1 else "ko")
	var initial: Dictionary = study.particles_study_state()
	_expect(initial["emitters"].size() == 1 and initial["emitters"][0]["particle_count"] > 0, "Quiet dust must be visible from its deterministic warmup.")
	study._process(1.0)
	await _capture("quiet-" + str(scale))
	await _click(study.get_node("AmbientParticlesStudyInterface/InfernalHall"))
	study._density_slider.value = 2.0
	study._process(0.3)
	_expect(study._load_errors.is_empty() and study._emitters.size() == 3, "Dense infernal fixture must compose separate smoke, ember and spark emitters within capacity.")
	await _click(study.get_node("AmbientParticlesStudyInterface/PauseParticles"))
	var paused: Dictionary = study.particles_study_state()
	study._process(10.0)
	_expect(study.particles_study_state() == paused, "Pause must freeze all emitter and camera clocks.")
	await _click(study._language_button)
	_expect(study.particles_study_state() == paused, "Language replacement must preserve seeded particles and paused state.")
	await _click(study.get_node("AmbientParticlesStudyInterface/PauseParticles"))
	await _click(study.get_node("AmbientParticlesStudyInterface/ShakeAmbientCamera"))
	study._process(0.3)
	_expect(not study._world.is_equal_approx(Transform2D.IDENTITY), "Camera shake must produce a world transform.")
	for emitter: Control in study._emitters:
		_expect(emitter._camera.is_equal_approx(study._world), "Every particle emitter must share the background's final camera.")
	await _capture("infernal-" + str(scale))
	await _click(study.get_node("AmbientParticlesStudyInterface/DrainParticles"))
	study._process(20.0)
	for emitter: Control in study._emitters:
		_expect(emitter.get_state()["particle_count"] == 0 and not emitter.get_state()["emitting"], "Stopping emission must drain existing particles without new births.")
	await _click(study.get_node("AmbientParticlesStudyInterface/RestartParticles"))
	var replayed: Dictionary = study.particles_study_state()
	_expect(replayed["elapsed"] == 0.0 and not replayed["draining"], "Restart must restore emission from the seeded origin.")
	study._process(1.0)
	study._restart_particles()
	_expect(study.particles_study_state() == replayed, "Identical restart settings must reproduce the same particle and camera state.")
	_evidence["checks"].append("Particle Lab " + str(scale) + "x: quiet/infernal, density2, warmup, pause, language, world camera, finite drain and deterministic restart")


func _voice(scale: int, baseline_buses: int) -> void:
	_expect(_app.open_route("transmission_voice_study"), "Transmission Voice Processing must be a Lab-owned route.")
	await _settle()
	var study: Control = _app.active_scene
	_expect(study._load_errors.is_empty(), "Voice fixture must initialize: " + str(study._load_errors))
	if not study._load_errors.is_empty(): return
	study.set_language("en" if scale == 1 else "ko")
	var output_bus: StringName = study._processor.get_output_bus()
	_expect(AudioServer.bus_count == baseline_buses + 1 and not output_bus.is_empty(), "The voice study must own exactly one private bus.")
	await _click(study.get_node("TransmissionVoiceStudyInterface/PlayVoice"))
	await create_timer(0.15).timeout
	var stream: AudioStream = study._audio._voice_player.stream
	var before: float = study._audio.get_state()["voice_position_seconds"]
	_expect(stream != null and before > 0.0, "A prepared localized Eira recording must actually begin playback.")
	await _click(study.get_node("TransmissionVoiceStudyInterface/ProcessedVoice"))
	study._strength_slider.value = 0.85
	_expect(study._audio._voice_player.stream == stream and study._audio.get_state()["voice_position_seconds"] >= before, "Live processing changes must retain the same stream and playback position.")
	_expect(study._processor.get_state()["processing"] and study._audio.get_state()["voice_bus"] == output_bus and study._audio.get_state()["bus"] == "Master", "Only the voice must use the processing bus.")
	await _capture("transmission-" + str(scale))
	await _click(study.get_node("TransmissionVoiceStudyInterface/PauseVoice"))
	var paused: float = study._audio.get_state()["voice_position_seconds"]
	await create_timer(0.15).timeout
	_expect(absf(float(study._audio.get_state()["voice_position_seconds"]) - paused) < 0.015, "Pause must retain the nonzero voice cursor.")
	await _click(study._language_button)
	_expect(study._paused and study._audio._voice_player.stream != stream and study._audio.get_state()["voice_position_seconds"] < 0.03, "Language changes must stop the old clip and prepare the new language at zero while retaining pause.")
	await _click(study.get_node("TransmissionVoiceStudyInterface/StopVoice"))
	_expect(not study._has_started and not study._audio.get_state()["voice_playing"], "Stop must leave playback idle.")
	await _click(study.get_node("TransmissionVoiceStudyInterface/PlayVoice"))
	_expect(study._has_started and not study._paused, "Replay must start from the beginning and resume sound.")
	var old_player: WeakRef = weakref(study._audio)
	_expect(_app.open_route("effects_menu"), "The voice study must return to its effect collection.")
	await _settle()
	_expect(old_player.get_ref() == null and AudioServer.get_bus_index(output_bus) == -1 and AudioServer.bus_count == baseline_buses, "Leaving the voice study must stop/free its player and remove only its private bus.")
	_evidence["checks"].append("Voice Lab " + str(scale) + "x: actual Eira clip, dry/wet and strength keep source position, pause, locale, replay and bus cleanup; no listening verdict")


func _freeze(node: Node) -> void:
	if node.has_method("particles_study_state") or node.has_method("voice_study_state"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _click(button: Button) -> void:
	var point := root.get_final_transform() * button.get_global_rect().get_center()
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.global_position = point
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _settle() -> void:
	for frame in 3: await process_frame


func _capture(name: String) -> void:
	if not _capture_enabled: return
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	var path := OUTPUT.path_join(name + ".png")
	DirAccess.make_dir_recursive_absolute(OUTPUT)
	_expect(picture.get_size() == root.size and picture.save_png(path) == OK, "Lab capture must preserve native dimensions: " + name)
	_evidence["captures"].append({"path": path, "sha256": FileAccess.get_sha256(path), "size": [picture.get_width(), picture.get_height()]})


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
