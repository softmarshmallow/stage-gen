extends "res://qa/afterlight_ensemble_checks.gd"

## Focused Keeper intensity comparison; inherits existing world/restore checks.
const SAMPLES := ["scarlet_pressure", "the_unlit_house", "the_keeper", "the_price_of_return", "the_room_refuses", "the_return", "only_a_second"]
const WAKING_BEATS := ["the_unlit_house", "a_hand_to_hold"]
var _phase := "after"
var _intensity_captures: Array[Dictionary] = []
var _sources := {}


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Keeper intensity captures require a native renderer.")
		quit(2)
		return
	var args := OS.get_cmdline_user_args()
	for index in args.size() - 1:
		if args[index] == "--phase": _phase = args[index + 1]
	if _phase not in ["before", "after"]:
		printerr("Keeper comparison phase must be before or after.")
		quit(2)
		return
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "bishoujo_afterlight", "Use --game bishoujo_afterlight.")
	_sources["root_source_sha256"] = _app.game_root.get_script().source_code.sha256_text()
	_sources["story_source_sha256"] = _active().get_script().source_code.sha256_text()
	_sources["beats_source_sha256"] = load("res://games/bishoujo_afterlight/story_beats.gd").source_code.sha256_text()
	for path: String in ["res://addons/game_presentation/effects/shaders/ominous_corruption.gdshader", "res://addons/game_presentation/effects/shaders/refraction_field.gdshader"]:
		_sources[path.get_file()] = FileAccess.get_sha256(path)
	print("Keeper " + _phase + " comparison loaded source hashes: " + JSON.stringify(_sources))
	for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window_size
		await _keeper_samples(window_size)
	await _dispose_app()
	var folder := "res://qa/keeper-intensity/" + _phase
	var output := FileAccess.open(folder.path_join("manifest.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"phase": _phase, "sources": _sources, "captures": _intensity_captures, "errors": _errors}, "\t"))
	for issue: String in _errors: printerr("FAIL Keeper intensity: " + issue)
	if _errors.is_empty(): print("PASS Keeper intensity " + _phase + ": seven fixed encounter samples and both realm waking sequences at 1x/2x, world-bound patterns, active-shake background coverage, live VFX/eyelid EN/KO/pause/Lab restore, unchanged UI geometry/materials, and complete return cleanup")
	quit(0 if _errors.is_empty() else 1)


func _keeper_samples(window_size: Vector2i) -> void:
	_expect(_app.open_route("new_game"), "The focused encounter must start with an isolated game.")
	await _settle()
	var game := _active()
	_expect(game.set_language("ko").is_empty(), "Korean must be available.")
	var initial_ui := _ui_geometry(game)
	var captured := 0
	var effects_seen := {}
	for iteration in game.beats.size():
		game = _active()
		var beat: Dictionary = game.current_beat()
		var id := str(beat["id"])
		if WAKING_BEATS.has(id):
			await _check_waking_scene(game, id, window_size)
			game = _active()
		if SAMPLES.has(id):
			if beat.has("shake") and beat["type"] != "rift":
				game._process(0.1)
				_expect(game._shake.is_active(), "A character-entry shake must be active near the beginning of its line: " + id)
				for frame in 16:
					game._process(0.0125)
					_check_coverage(game, id + " entry shake frame " + str(frame))
					_check_pattern_binding(game, id)
			game._process((0.35 if beat["type"] == "rift" else 1.2) - game._elapsed)
			if id == "only_a_second":
				var reveal: Dictionary = game._reveal.get_state()
				var remaining := maxf(0.0, float(str(reveal["text"]).length()) / float(reveal["chars_per_second"]) - float(reveal["elapsed"]))
				game._process(remaining + 0.1)
			else:
				game._reveal.request_advance()
				game._render()
			_expect(game._load_errors.is_empty(), "The sampled encounter must initialize: " + id + " " + str(game._load_errors))
			_check_coverage(game, id)
			_check_ominous_effects(game, id, effects_seen)
			_check_pattern_binding(game, id)
			_expect(_same(initial_ui, _ui_geometry(game)), "Stronger VFX must not change UI geometry or materials: " + id)
			await _capture_intensity(game, id, window_size)
			captured += 1
			if id in ["scarlet_pressure", "the_price_of_return", "the_room_refuses"]:
				await _language_and_detour(game, id)
				game = _active()
				_expect(_same(initial_ui, _ui_geometry(game)), "Restoring active VFX must preserve host UI: " + id)
				_check_pattern_binding(game, id)
			if beat["type"] == "rift" and beat.has("shake"):
				_expect(game._shake.is_active(), "Coverage samples must run during the authored shake: " + id)
				for frame in 32:
					game._process(0.018)
					var pose: Dictionary = game._camera.sample()
					var zoom := float(pose["zoom"])
					var base := Transform2D(Vector2(zoom, 0), Vector2(0, zoom), Vector2(float(pose["offset_x"]), float(pose["offset_y"])))
					_expect(IMPACT_SHAKE.can_compose(base, game._base_background, DESIGN_SIZE), "The camera must retain overscan for stronger shake: " + id)
					_check_coverage(game, id + " shake frame " + str(frame))
					_check_pattern_binding(game, id)
			if id == "the_unlit_house":
				game._process(3.0 - game._elapsed)
				_expect(not game._eye.is_active() and float(game._eye.sample()["openness"]) == 1.0, "The hall's waking sequence must finish fully open.")
				await _capture_intensity(game, id, window_size, "open")
			if id == "the_return":
				game._process(6.0 - game._elapsed)
				_check_clean_return(game, id)
			if id == "only_a_second":
				_check_clean_return(game, id)
				_expect(game._background_index == 1 and game._cast.visible_ids() == HEROINE_IDS, "The clean return must restore the familiar physical ensemble.")
				break
		elif id == "a_hand_to_hold":
			game._process(3.0 - game._elapsed)
			_expect(not game._eye.is_active() and float(game._eye.sample()["openness"]) == 1.0, "Nami's recovery sequence must finish fully open.")
			_check_clean_return(game, id)
			await _capture_intensity(game, id, window_size, "open")
		# Replay the authored prefix with fixed six-second beat histories, without
		# rerunning the full episode/input matrix before each selected sample.
		game._process(maxf(0.0, 6.0 - game._elapsed))
		if _fulfill_contact_gate(game): continue
		if beat["type"] == "choice": game._choices[id] = "help_first"
		game._continue_story()
	_expect(captured == SAMPLES.size(), "All seven fixed encounter samples must be captured.")


func _check_waking_scene(game: Control, id: String, window_size: Vector2i) -> void:
	game._render()
	_expect(game.current_beat()["type"] == "eye" and game._eye.get_state()["mode"] == "waking_opening", "Both realm changes must select Waking Opening: " + id)
	_expect(game._eye_layer.visible and float(game._eye.sample()["openness"]) == 0.0, "A waking scene must start behind closed eyes: " + id)
	if id == "the_unlit_house":
		_expect(not game._portrait.visible and game._cast.visible_ids().is_empty() and game._background_index == 2, "The infernal waking shot must reveal only the dedicated background.")
	else:
		_expect(game._portrait.visible and game._cast.visible_ids() == ["nami"] and game._background_index == 1, "Recovery must reveal Nami's close portrait in the warm room.")
		_check_clean_return(game, id)
	var settings: Dictionary = game._eye.get_state()["active_settings"]
	var peek := float(settings["peek_seconds"])
	var closed_start := peek + float(settings["closing_seconds"])
	var opening_start := closed_start + float(settings["closed_hold_seconds"])
	game._process(peek * 0.5)
	_expect(game._eye.sample()["phase"] == "peeking" and float(game._eye.sample()["openness"]) > 0.0, "Waking must visibly peek before closing: " + id)
	await _capture_intensity(game, id, window_size, "peek")
	game._process(closed_start + float(settings["closed_hold_seconds"]) * 0.5 - game._elapsed)
	_expect(game._eye.sample()["phase"] == "closed" and float(game._eye.sample()["openness"]) == 0.0, "The brief waking blink must completely close: " + id)
	var closed_image := await _capture_intensity(game, id, window_size, "closed")
	for y in range(0, window_size.y, 29):
		for x in range(0, window_size.x, 29):
			var color := closed_image.get_pixel(x, y)
			_expect(color.r + color.g + color.b < 0.004, "Closed eyes must cover world effects and scene UI: " + id)
	await _language_and_detour(game, id)
	game = _active()
	game._process(opening_start + minf(0.25, float(settings["opening_seconds"]) * 0.2) - game._elapsed)
	_expect(game._eye.sample()["phase"] == "opening" and float(game._eye.sample()["openness"]) > 0.0, "The waking blink must reopen into its held scene: " + id)
	_check_pattern_binding(game, id)
	await _capture_intensity(game, id, window_size, "reopening")


func _check_pattern_binding(game: Control, id: String) -> void:
	for field: Control in [game._world_corruption, game._local_corruption]:
		_expect(field.get_pattern_transform().is_equal_approx(game._world_transform()), "Mist and embers must use the final world camera including shake and zoom: " + id)


func _check_clean_return(game: Control, id: String) -> void:
	for field: Control in [game._heat_haze, game._world_corruption, game._local_corruption, game._barrier]:
		_expect(not field.visible and field.get_strength() == 0.0, "Returning must clear every ominous field: " + id)
	_expect(not game._shake.is_active() and float(game._shake.sample()["envelope"]) == 0.0, "Returning must leave no shake displacement or active envelope: " + id)


func _ui_geometry(game: Control) -> Array:
	var controls := []
	for control: Control in [game._ui, game._header, game._dialogue, game._speaker, game._line, game._language_button]:
		_expect(control.material == null, "Scene VFX must never attach a shader to host UI.")
		controls.append({"rect": control.get_rect(), "material": control.material})
	for field: Control in [game._heat_haze, game._world_corruption, game._local_corruption, game._barrier]:
		_expect(field.get_index() < game._ui.get_index(), "World effects must render before the UI.")
	return controls


func _capture_intensity(game: Control, id: String, window_size: Vector2i, sample_name: String = "") -> Image:
	var folder := "res://qa/keeper-intensity/" + _phase
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "The comparison directory must be writable.")
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	var path := folder.path_join(id + ("-" + sample_name if not sample_name.is_empty() else "") + "-" + str(window_size.x) + ".png")
	_expect(picture.get_size() == window_size, "Keeper captures must use native window resolution.")
	_expect(picture.save_png(path) == OK, "Keeper capture must save: " + id)
	_intensity_captures.append({"beat": id, "sample": sample_name, "window": [window_size.x, window_size.y], "elapsed": game._elapsed,
		"effect_time": game._effect_time, "file": path, "sha256": FileAccess.get_sha256(path),
		"authored_beat": game.current_beat(), "profile": {"heat_haze": game.content["heat_haze"], "barrier": game.content["barrier"], "world_corruption": game.content["world_corruption"], "local_corruption": game.content["local_corruption"]},
		"world": _world_snapshot(game)})
	return picture
