extends SceneTree

const MANPU = preload("res://addons/game_presentation/actors/manpu_animation.gd")
const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const LEGACY = preload("res://qa/manpu_animation_checks.gd")
const LEGACY_FOCUS = preload("res://qa/actor_focus_checks.gd")
const LEGACY_EXIT = preload("res://qa/character_exit_checks.gd")
const CATALOG := "res://addons/game_presentation/actors/presets/manpu.json"
const STEP := {"actor": "actor_a", "id": "sigh", "preset": "step_loop"}
const FRAMES := {"actor": "actor_b", "id": "sigh", "preset": "frame_loop", "frames": ["sigh", "sparkle", "heart"]}
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var script: Script = MANPU
	if not script.can_instantiate():
		printerr("FAIL Manpu Loops: controller must compile.")
		quit(1)
		return
	_stepped_motion_and_frames()
	_clocks_and_reconciliation()
	_custom_sampling_and_validation()
	var legacy = LEGACY.new()
	legacy._check_controller()
	_errors.append_array(legacy._errors)
	var focus = LEGACY_FOCUS.new()
	focus._check_engine()
	_errors.append_array(focus._errors)
	var exits = LEGACY_EXIT.new()
	exits._check_controller()
	_errors.append_array(exits._errors)
	for issue: String in _errors:
		printerr("FAIL Manpu Loops: " + issue)
	if _errors.is_empty():
		print("PASS Manpu Loops: held transform steps, two/three frame loops, independent phases, replay/removal, custom sampling, atomic rejection, and legacy introduction/focus/exit contracts.")
	quit(0 if _errors.is_empty() else 1)


func _make():
	var controller = MANPU.new()
	_expect(controller.initialize(CATALOG).is_empty(), "The extended catalog must initialize.")
	return controller


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _stepped_motion_and_frames() -> void:
	var controller = _make()
	controller.sync([STEP, FRAMES])
	var first: Dictionary = controller.sample("actor_a", "sigh")
	controller.advance(0.2)
	_expect(controller.sample("actor_a", "sigh") == first, "A stepped transform must hold its sample without interpolation.")
	_expect(controller.sample("actor_b", "sigh")["sprite_id"] == "sparkle", "Three frames must advance at one-third of the loop.")
	controller.advance(0.2)
	var second: Dictionary = controller.sample("actor_a", "sigh")
	_expect(second["rotation_degrees"] == 30.0 and second["scale"] == 0.8, "The midpoint must switch exactly to the alternate rotation/scale.")
	_expect(controller.sample("actor_b", "sigh")["sprite_id"] == "heart", "Three frames must reach the third image.")
	controller.advance(0.399)
	_expect(controller.sample("actor_a", "sigh") == second, "The alternate pose must remain held before wrap.")
	controller.advance(0.001)
	_expect(controller.sample("actor_a", "sigh") == first, "The duration boundary must wrap to the initial pose.")
	var pair: Dictionary = FRAMES.duplicate(true)
	pair["frames"] = ["sigh", "heart"]
	controller.sync([pair])
	controller.advance(0.3)
	_expect(controller.sample("actor_b", "sigh")["sprite_id"] == "heart", "Two-frame animation must use half-period holds.")
	controller.advance(0.3)
	_expect(controller.sample("actor_b", "sigh")["sprite_id"] == "sigh", "Two frames must wrap exactly.")
	controller.configure("frame_loop")
	controller.sync([{"actor": "actor_a", "id": "sigh"}])
	controller.advance(0.4)
	_expect(controller.sample("actor_a", "sigh")["sprite_id"] == "sigh", "A frame preset without supplied art must retain its base sprite.")
	var tracks := {"rotation_degrees": [[0, 0], [1, 30]]}
	var rejected: Array[String] = []
	ANIMATION.validate_tracks(tracks, "consumer", rejected)
	_expect(not rejected.is_empty(), "Rotation must require an explicitly opted-in renderer.")
	var accepted: Array[String] = []
	ANIMATION.validate_tracks(tracks, "manpu", accepted, true)
	_expect(accepted.is_empty(), "Manpu must explicitly admit the rotation channel.")
	_expect(ANIMATION.sample({}, 0.0, 1.0).size() == 6, "The shared sample must contain six numeric channels only.")
	var numeric := ANIMATION.sample({}, 0.0, 1.0, {"sprite_id": "metadata"})
	_expect(numeric.size() == 6 and not numeric.has("sprite_id"), "Retarget metadata must never leak into shared numeric samples.")


func _clocks_and_reconciliation() -> void:
	var whole = _make()
	var split = _make()
	whole.sync([STEP, FRAMES])
	split.sync([STEP, FRAMES])
	whole.advance(8.4)
	for index in 84:
		split.advance(0.1)
	_expect(whole.sample("actor_a", "sigh") == split.sample("actor_a", "sigh") and whole.sample("actor_b", "sigh") == split.sample("actor_b", "sigh"), "Large and partitioned elapsed time must select identical poses and frames.")
	var held: Dictionary = whole.get_state()
	whole.sync([FRAMES, STEP], false)
	whole.configure("fade_in")
	_expect(whole.get_state()["states"] == held["states"], "Pinned cues must preserve phases across reordering and default changes.")
	whole.replay("actor_a", "sigh")
	_expect(whole.get_state()["states"]["actor_b:sigh"] == held["states"]["actor_b:sigh"], "Targeted replay must preserve the other mark's phase.")
	_expect(whole.sample("actor_a", "sigh")["rotation_degrees"] == 0.0, "Replay must reset the chosen phase.")
	whole.sync([FRAMES])
	whole.sync([STEP, FRAMES], false)
	_expect(whole.get_state()["states"]["actor_a:sigh"]["elapsed"] == 0.0, "Reintroduced loops start at zero even during settled sync.")
	var changed: Dictionary = STEP.duplicate()
	changed["preset"] = "shake"
	whole.sync([changed, FRAMES])
	_expect(whole.get_state()["states"]["actor_a:sigh"]["elapsed"] == 0.0, "Changing a pair's explicit preset must restart only that pair.")
	whole.sync([])
	_expect(whole.get_state()["states"].is_empty(), "Removing cues must remove loops without transient events.")
	_expect(not split.get_state()["states"].is_empty(), "Controller instances must remain independent.")


func _custom_sampling_and_validation() -> void:
	var controller = _make()
	controller.sync([FRAMES])
	controller.advance(0.2)
	var state: Dictionary = controller.get_state()
	var builtin: Dictionary = controller.sample("actor_b", "sigh")
	var customized: Dictionary = controller.sample_with("actor_b", "sigh", func(context: Dictionary) -> Dictionary:
		context["frames"].clear()
		context["sample"]["scale"] = 99.0
		return {"scale": 0.7, "rotation_degrees": 15.0, "sprite_id": "heart"})
	_expect(customized["errors"].is_empty() and customized["sample"]["scale"] == 0.7 and customized["sample"]["sprite_id"] == "heart", "A custom sampler may replace valid channels and select supplied art.")
	_expect(controller.get_state() == state and controller.sample("actor_b", "sigh") == builtin, "Callback context must not alias internal state or built-in samples.")
	for invalid: Variant in [{"scale": 0}, {"rotation_degrees": NAN}, {"opacity": 2}, {"sprite_id": "missing"}, {"other": 1}, 42]:
		var result: Dictionary = controller.sample_with("actor_b", "sigh", func(_context: Dictionary): return invalid)
		_expect(not result["errors"].is_empty() and result["sample"] == builtin and controller.get_state() == state, "Invalid custom output must return the unchanged built-in fallback and diagnostics.")
	for frames: Variant in [[], ["sigh"], ["sigh", "bad id"], "sigh"]:
		_expect(not controller.sync([{"actor": "actor_b", "id": "sigh", "preset": "frame_loop", "frames": frames}]).is_empty() and controller.get_state() == state, "Malformed frame sequences must reject atomically.")
	_expect(not controller.sync([{"actor": "actor_b", "id": "sigh", "preset": "shake", "frames": ["sigh", "heart"]}]).is_empty(), "Frame animation must require looping playback.")
	_expect(not controller.emit_one_shot("actor_b", "sigh", "step_loop")["errors"].is_empty() and controller.get_state() == state, "Looping presets must never enter the finite one-shot pool.")
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
	for replacement: Dictionary in [{"playback": "forever"}, {"interpolation": "linear"}, {"playback": "loop", "duration_seconds": 0.0}]:
		var malformed := catalog.duplicate(true)
		malformed["presets"][0].merge(replacement, true)
		_expect(not controller._validate_catalog(malformed)["errors"].is_empty() and controller.get_state() == state, "Malformed loop policy must reject without replacing active state.")
	controller.advance(NAN)
	controller.advance(-1.0)
	_expect(controller.get_state() == state, "Invalid delta must leave phases untouched.")
	controller.clear()
	_expect(controller.get_state()["states"].is_empty() and controller.one_shots().is_empty(), "Clear must remove both lifecycles.")
