extends SceneTree

## Provider-free controller proof. Render hosts separately prove that their
## original-height travel clears the camera before the final coverage drop.
const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const EXIT = preload("res://addons/game_presentation/actors/character_exit.gd")
const FOCUS = preload("res://addons/game_presentation/actors/actor_focus.gd")
const CAST = preload("res://addons/game_presentation/actors/cast_transition.gd")
const EXIT_CATALOG := "res://addons/game_presentation/actors/presets/exit.json"
const FOCUS_CATALOG := "res://addons/game_presentation/actors/presets/focus.json"
const CAST_SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
const ACTORS: Array[String] = ["first", "second", "third"]
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_check_sampler()
	_check_walks()
	_check_restless_bounce()
	_check_handoff()
	_check_existing_controllers()
	for issue: String in _errors: printerr("FAIL Walk-Away: " + issue)
	if _errors.is_empty(): print("PASS Walk-Away: signed height-relative travel, four rhythmic Y steps, late coverage removal, visible Y-only restlessness, cancellation, atomic per-handoff exits, no doubled X travel, phase/frame-partition invariance and existing focus/manpu/matte/cast baselines")
	quit(0 if _errors.is_empty() else 1)


func _check_sampler() -> void:
	var legacy := {"offset_y_ratio": 0.02, "scale": 1.0, "opacity": 1.0, "brightness": 1.0}
	var snapshot := legacy.duplicate()
	var sample: Dictionary = ANIMATION.sample({}, 0.0, 1.0, legacy)
	var expected := {"offset_x_ratio": 0.0, "offset_y_ratio": 0.02, "scale": 1.0, "opacity": 1.0, "brightness": 1.0, "rotation_degrees": 0.0}
	_expect(sample == expected and legacy == snapshot, "Partial retarget samples must gain neutral X and rotation while preserving Y and their source.")
	for direction: float in [-1.0, 1.0]:
		var tracks := {"offset_x_ratio": [[0.0, 0.0], [1.0, direction * 1.8]], "offset_y_ratio": [[0.0, 0.0], [1.0, 0.0]]}
		var errors: Array[String] = []
		ANIMATION.validate_tracks(tracks, "Walk test", errors)
		_expect(errors.is_empty(), "Signed finite horizontal offsets must be valid scalar tracks.")
		_expect(is_equal_approx(float(ANIMATION.sample(tracks, 0.5, 1.0)["offset_x_ratio"]), direction * 0.9), "The existing sampler must evaluate both horizontal directions.")
		tracks["offset_x_ratio"][1][1] = INF
		ANIMATION.validate_tracks(tracks, "Invalid walk test", errors)
		_expect(not errors.is_empty(), "Horizontal offsets must retain finite-number validation.")


func _new_exit(preset: String) -> EXIT:
	var controller: EXIT = EXIT.new()
	_expect(controller.initialize(ACTORS, EXIT_CATALOG).is_empty(), "Prepared Character Exit presets must initialize.")
	_expect(controller.configure(preset).is_empty(), "Walk-Away preset must be available: " + preset)
	return controller


func _check_walks() -> void:
	for preset: String in ["walk_away", "walk_away_right"]:
		var controller := _new_exit(preset)
		controller.exit_actor("first")
		var direction := -1.0 if preset == "walk_away" else 1.0
		var previous := 0.0
		var last_distance := 0.0
		for normalized: float in [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.99]:
			controller.advance((normalized - previous) * 1.8)
			previous = normalized
			var sample: Dictionary = controller.sample("first")
			var distance := float(sample["offset_x_ratio"]) * direction
			_expect(distance >= last_distance, "Walk-Away X travel must remain monotonic: " + preset)
			last_distance = distance
			_expect(controller.is_visible("first") and controller.is_exiting("first"), "Walking remains drawable until the offscreen end.")
			_expect(is_equal_approx(float(sample["opacity"]), 1.0) and is_equal_approx(float(sample["brightness"]), 1.0), "A visible walking actor must retain its color and source-alpha coverage through t=.99.")
			_expect(controller.sample("second") == ANIMATION.CHANNEL_DEFAULTS, "A walk must not alter another actor.")
			if normalized in [0.125, 0.375, 0.625, 0.875]:
				_expect(is_equal_approx(float(sample["offset_y_ratio"]), -0.016), "Each of the four walking steps must reach its authored Y peak.")
		controller.advance(0.1)
		_expect(not controller.is_visible("first") and not controller.is_exiting("first") and is_zero_approx(float(controller.sample("first")["opacity"])), "The completed walk must remove coverage and stay hidden.")
		_expect(is_equal_approx(float(controller.sample("first")["offset_x_ratio"]), direction * 1.8) and is_zero_approx(float(controller.sample("first")["offset_y_ratio"])), "Walk endpoints must preserve exact travel and settle Y.")
		controller.show_actor("first")
		_expect(controller.sample("first") == ANIMATION.CHANNEL_DEFAULTS, "Showing an actor must cancel and clear all walking offsets.")
		controller.exit_actor("first")
		controller.advance(0.3)
		var before: Dictionary = controller.get_state()["states"]["first"].duplicate(true)
		controller.configure("silhouette_fade")
		_expect(controller.get_state()["states"]["first"] == before, "Future-preset configuration must not retune an active walking actor.")
		controller.exit_actor("second")
		controller.advance(0.2)
		_expect(is_zero_approx(float(controller.sample("second")["offset_x_ratio"])) and float(controller.sample("second")["brightness"]) < 1.0, "A later actor must still use the unchanged matte baseline.")
		for time: float in [0.2, 0.67, 1.3, 1.8, 2.4]:
			var once := _new_exit(preset)
			var partitioned := _new_exit(preset)
			once.exit_actor("first")
			partitioned.exit_actor("first")
			once.advance(time)
			for frame in 30: partitioned.advance(time / 30.0)
			_expect(_same_sample(once.sample("first"), partitioned.sample("first")) and once.is_visible("first") == partitioned.is_visible("first"), "Walk samples and lifecycle must be independent of frame partitioning.")
	var controller := _new_exit("walk_away")
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(EXIT_CATALOG))
	catalog["presets"][2]["tracks"]["scale"] = [[0.0, 1.0], [1.0, 1.1]]
	_expect(not controller._validate_catalog(catalog)["errors"].is_empty(), "Character Exit must continue to reject scale tracks.")
	catalog["presets"][2]["tracks"].erase("scale")
	catalog["presets"][2]["tracks"]["opacity"] = [[0.0, 1.0], [1.0, 1.0]]
	_expect(not controller._validate_catalog(catalog)["errors"].is_empty(), "Every exit must retain the ending-zero-coverage contract.")


func _check_restless_bounce() -> void:
	var controller: FOCUS = FOCUS.new()
	_expect(controller.initialize(ACTORS, FOCUS_CATALOG).is_empty() and controller.configure("restless_bounce").is_empty(), "Restless Bounce must use the existing Actor Focus controller.")
	controller.set_focus("second")
	for step in 8:
		controller.advance(1.2 / 8.0)
		var sample: Dictionary = controller.sample("second")
		_expect(is_zero_approx(float(sample["offset_x_ratio"])) and is_equal_approx(float(sample["opacity"]), 1.0) and is_equal_approx(float(sample["brightness"]), 1.0) and is_equal_approx(float(sample["scale"]), 1.0), "Restlessness must affect only Y and keep the actor fully present.")
		_expect(is_equal_approx(float(sample["offset_y_ratio"]), -0.016 if step % 2 == 0 else 0.0), "Restlessness must reuse the four-step walking Y rhythm.")
		_expect(controller.sample("first") == ANIMATION.CHANNEL_DEFAULTS, "A restless speaker must leave listeners neutral.")
	_expect(controller.sample("second") == ANIMATION.CHANNEL_DEFAULTS, "Completed restlessness must settle without positional residue.")
	controller.replay()
	controller.advance(0.15)
	_expect(is_equal_approx(float(controller.sample("second")["offset_y_ratio"]), -0.016), "Explicit replay must reintroduce the same speaker's Y cue.")
	controller.clear()
	_expect(controller.sample("second") == ANIMATION.CHANNEL_DEFAULTS, "Clear must immediately cancel restlessness.")


func _new_cast() -> CAST:
	var controller: CAST = CAST.new()
	_expect(controller.initialize(ACTORS, EXIT_CATALOG, CAST_SPEC).is_empty(), "The existing Cast Transition spec must initialize without new fields.")
	return controller


func _check_handoff() -> void:
	var controller := _new_cast()
	_expect(controller.get_settings()["exit_preset"] == "silhouette_fade", "An omitted exit override must retain the specification's matte default.")
	var before := controller.get_state()
	for invalid: Dictionary in [{"exit_preset": "unknown"}, {"exit_preset": 4}, {"exit_preset": "walk_away", "curve": "invalid"}]:
		_expect(not controller.configure(invalid).is_empty() and controller.get_state() == before, "Invalid exit overrides must fail atomically.")
	controller.start()
	controller.advance(0.495)
	var baseline := controller.sample("first")
	_expect(is_zero_approx(float(baseline["brightness"])) and is_equal_approx(float(baseline["opacity"]), 1.0) and is_zero_approx(float(baseline["offset_x_ratio"])), "The default handoff must retain its opaque matte timing and zero extra X track.")
	for preset: String in ["walk_away", "walk_away_right"]:
		controller.reset()
		_expect(controller.configure({"exit_preset": preset}).is_empty(), "A future handoff must accept a directional walking preset.")
		controller.start()
		controller.advance(0.225)
		var sample := controller.sample("first")
		_expect(is_equal_approx(float(sample["center_x"]), 410.0) and not is_zero_approx(float(sample["offset_x_ratio"])), "Departure X must be supplied once by the walking track, without Cast's exit travel_distance.")
		_expect(is_equal_approx(float(sample["offset_y_ratio"]), -0.016), "The handoff must carry the Character Exit Y sample to its renderer.")
		before = controller.get_state()
		_expect(not controller.configure({"exit_preset": "silhouette_fade"}).is_empty() and controller.get_state() == before, "A busy handoff must refuse retuning its departure.")
		_expect(not bool(controller.sample("third")["visible"]) and is_equal_approx(float(controller.sample("second")["center_x"]), 890.0), "Departure must precede survivor movement and arrival.")
		controller.advance(1.575)
		_expect(controller.get_state()["phase"] == "move" and not bool(controller.sample("first")["visible"]), "Walking completion must hand off to survivor movement after1.8 seconds.")
		controller.advance(1.6)
		_expect(not controller.is_busy() and is_equal_approx(float(controller.sample("second")["center_x"]), 410.0) and is_equal_approx(float(controller.sample("third")["center_x"]), 890.0), "The unchanged move/arrival phases must settle into the normal pair.")
		for pattern: String in ["shift_and_replace", "replace_in_place"]:
			for time: float in [0.225, 1.782, 1.8, 2.2, 2.6, 3.0, 3.4, 6.0]:
				var once := _new_cast()
				var partitioned := _new_cast()
				for instance: CAST in [once, partitioned]:
					instance.configure({"exit_preset": preset, "pattern": pattern})
					instance.start()
				once.advance(time)
				for frame in 30: partitioned.advance(time / 30.0)
				for id: String in ACTORS:
					_expect(_same_sample(once.sample(id), partitioned.sample(id)), "Walking handoff phases must be independent of frame partitioning.")
	var specification: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CAST_SPEC))
	specification["defaults"]["exit_preset"] = "unknown"
	var temporary := "/tmp/walk_away_spec_%d.json" % OS.get_process_id()
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	file.store_string(JSON.stringify(specification))
	file.close()
	before = controller.get_state()
	_expect(not controller.initialize(ACTORS, EXIT_CATALOG, temporary).is_empty() and controller.get_state() == before, "Unknown default exit selection must refuse reinitialization atomically.")
	DirAccess.remove_absolute(temporary)


func _check_existing_controllers() -> void:
	var focus_checks = load("res://tests/actor_focus_checks.gd").new()
	focus_checks._check_engine()
	_errors.append_array(focus_checks._errors)
	var exit_checks = load("res://tests/character_exit_checks.gd").new()
	exit_checks._check_controller()
	_errors.append_array(exit_checks._errors)
	var cast_checks = load("res://tests/cast_transition_checks.gd").new()
	cast_checks._slots = JSON.parse_string(FileAccess.get_file_as_string(CAST_SPEC))["slots"]
	cast_checks._check_sequence()
	cast_checks._check_curves()
	_errors.append_array(cast_checks._errors)
	var manpu_checks = load("res://tests/manpu_animation_checks.gd").new()
	manpu_checks._check_controller()
	_errors.append_array(manpu_checks._errors)


func _same_sample(a: Dictionary, b: Dictionary) -> bool:
	if a.size() != b.size(): return false
	for key: String in a:
		if not b.has(key): return false
		if a[key] is bool:
			if a[key] != b[key]: return false
		elif not is_equal_approx(float(a[key]), float(b[key])): return false
	return true


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
