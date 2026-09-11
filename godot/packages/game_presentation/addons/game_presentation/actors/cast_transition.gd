extends RefCounted

## A bounded, sequential two-slot handoff for three registered actors.
## Character Exit owns departure color/coverage and optional height-relative
## motion. An authored departure X track replaces this controller's exit travel
## so the renderer applies translation once. Presentation Animation owns
## entrance opacity; Motion Curve owns translation and the matching graph.
const CHARACTER_EXIT = preload("res://addons/game_presentation/actors/character_exit.gd")
const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const MOTION_CURVE = preload("res://addons/game_presentation/motion/motion_curve.gd")
const SETTING_FIELDS := ["pattern", "curve", "frequency", "damping_ratio", "motion_duration_seconds", "travel_distance", "exit_preset"]
const SPEC_FIELDS := ["version", "slots", "exit_preset", "entrance_tracks", "defaults"]

var initialized := false
var _actor_ids: Array[String] = []
var _settings: Dictionary = {}
var _active_settings: Dictionary = {}
var _slots: Dictionary = {}
var _entrance_tracks: Dictionary = {}
var _exit = CHARACTER_EXIT.new()
var _occupancy: Dictionary = {}
var _positions: Dictionary = {}
var _visible: Dictionary = {}
var _phase := "idle"
var _phase_elapsed := 0.0
var _phase_duration := 0.0
var _phase_actor := ""
var _motion_from := 0.0
var _motion_to := 0.0
var _outgoing := ""
var _survivor := ""
var _incoming := ""
var _completed_handoffs := 0


## The first two actor ids occupy left/right initially; the third is hidden.
## Validate everything in temporary state before replacing a live controller.
func initialize(actor_ids: Array[String], exit_catalog_path: String, spec_path: String) -> Array[String]:
	var errors: Array[String] = []
	if actor_ids.size() != 3:
		errors.append("Cast Transition requires exactly three actor ids.")
	var next_exit = CHARACTER_EXIT.new()
	errors.append_array(next_exit.initialize(actor_ids, exit_catalog_path))
	var file := FileAccess.open(spec_path, FileAccess.READ)
	if file == null:
		errors.append("Cannot open the Cast Transition specification.")
		return errors
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK:
		errors.append("Cannot parse the Cast Transition specification: " + parser.get_error_message())
		return errors
	errors.append_array(_validate_spec(parser.data))
	if not errors.is_empty():
		return errors
	var spec: Dictionary = parser.data
	var selected_exit := String(spec["defaults"].get("exit_preset", spec["exit_preset"]))
	errors.append_array(next_exit.configure(selected_exit))
	if not errors.is_empty():
		return errors
	_actor_ids.assign(actor_ids)
	_settings = spec["defaults"].duplicate(true)
	_settings["exit_preset"] = selected_exit
	_slots = spec["slots"].duplicate(true)
	_entrance_tracks = spec["entrance_tracks"].duplicate(true)
	_exit = next_exit
	initialized = true
	reset()
	return errors


## Partial settings are merged atomically. An active handoff cannot be retuned;
## reset() is the explicit cancellation before configuring the next handoff.
func configure(settings: Dictionary) -> Array[String]:
	if not initialized:
		return ["Cast Transition is not initialized."]
	if is_busy():
		return ["Finish or reset the active cast handoff before changing its settings."]
	var candidate := _settings.duplicate(true)
	candidate.merge(settings, true)
	var errors := _validate_settings(candidate)
	if not errors.is_empty():
		return errors
	var known_exit := false
	for preset: Dictionary in _exit.get_presets():
		if preset["id"] == candidate.get("exit_preset"):
			known_exit = true
	if not known_exit:
		errors.append("Unknown Cast Transition exit preset: " + str(candidate.get("exit_preset")))
	if errors.is_empty():
		_settings = candidate
	return errors


func start() -> Array[String]:
	if not initialized:
		return ["Cast Transition is not initialized."]
	if is_busy():
		return []
	var errors: Array[String] = _exit.configure(String(_settings["exit_preset"]))
	if not errors.is_empty():
		return errors
	_active_settings = _settings.duplicate(true)
	_outgoing = String(_occupancy["left"])
	_survivor = String(_occupancy["right"])
	for actor_id: String in _actor_ids:
		if actor_id != _outgoing and actor_id != _survivor:
			_incoming = actor_id
			break
	_exit.show_actor(_outgoing)
	_exit.exit_actor(_outgoing)
	var departure: Dictionary = _exit.get_state()["states"][_outgoing]
	var travel := 0.0 if departure["tracks"].has("offset_x_ratio") else float(_active_settings["travel_distance"])
	_begin_phase("exit", float(departure["duration_seconds"]), _outgoing,
		float(_positions[_outgoing]), float(_positions[_outgoing]) - travel)
	if _phase_duration <= 0.0:
		_complete_phase()
	return []


## Reset cancels every phase and restores the initial pair. Settings persist.
func reset() -> void:
	_phase = "idle"
	_phase_elapsed = 0.0
	_phase_duration = 0.0
	_phase_actor = ""
	_outgoing = ""
	_survivor = ""
	_incoming = ""
	_active_settings.clear()
	_completed_handoffs = 0
	_occupancy.clear()
	_positions.clear()
	_visible.clear()
	_exit.clear()
	if not initialized:
		return
	_occupancy = {"left": _actor_ids[0], "right": _actor_ids[1]}
	for index in _actor_ids.size():
		var actor_id := _actor_ids[index]
		_positions[actor_id] = float(_slots["left" if index == 0 else "right"])
		_visible[actor_id] = index < 2


## Consume elapsed time through phase boundaries, including large frame deltas.
## A completed handoff stays idle; excess time never starts another handoff.
func advance(delta: float) -> void:
	if not initialized or not is_finite(delta) or delta <= 0.0:
		return
	var remaining := delta
	while is_busy() and remaining > 0.0:
		var phase_remaining := maxf(0.0, _phase_duration - _phase_elapsed)
		var step := minf(remaining, phase_remaining)
		# Decimal authored durations can straddle a boundary by a few machine
		# rounding bits after subtraction. Snap only that negligible remainder.
		var finishes_phase := phase_remaining - step <= 0.000000001
		if finishes_phase:
			step = phase_remaining
		if _phase == "exit":
			_exit.advance(step)
		_phase_elapsed = _phase_duration if finishes_phase else _phase_elapsed + step
		remaining = maxf(0.0, remaining - step)
		if finishes_phase:
			_complete_phase()
		else:
			break


func sample(actor_id: String) -> Dictionary:
	if not initialized or not _positions.has(actor_id):
		return {"visible": false, "center_x": 0.0, "opacity": 0.0, "brightness": 1.0, "offset_x_ratio": 0.0, "offset_y_ratio": 0.0}
	var appearance := {"visible": bool(_visible[actor_id]), "center_x": float(_positions[actor_id]), "opacity": 1.0, "brightness": 1.0, "offset_x_ratio": 0.0, "offset_y_ratio": 0.0}
	if not bool(appearance["visible"]):
		appearance["opacity"] = 0.0
		appearance["brightness"] = float(_exit.sample(actor_id)["brightness"])
		return appearance
	if is_busy() and actor_id == _phase_actor:
		var progress := 1.0 if _phase_duration <= 0.0 else _phase_elapsed / _phase_duration
		appearance["center_x"] = lerpf(_motion_from, _motion_to, MOTION_CURVE.sample(progress, _active_settings))
		if _phase == "exit":
			var departure: Dictionary = _exit.sample(actor_id)
			appearance["opacity"] = float(departure["opacity"])
			appearance["brightness"] = float(departure["brightness"])
			appearance["offset_x_ratio"] = float(departure["offset_x_ratio"])
			appearance["offset_y_ratio"] = float(departure["offset_y_ratio"])
		elif _phase == "enter":
			appearance["opacity"] = float(ANIMATION.sample(_entrance_tracks, _phase_elapsed, _phase_duration)["opacity"])
	return appearance


func is_busy() -> bool:
	return initialized and _phase != "idle"


func get_settings() -> Dictionary:
	return _settings.duplicate(true)


func get_state() -> Dictionary:
	var actors := {}
	for actor_id: String in _actor_ids:
		actors[actor_id] = sample(actor_id)
	return {"initialized": initialized, "phase": _phase, "phase_elapsed": _phase_elapsed,
		"phase_duration": _phase_duration, "occupancy": _occupancy.duplicate(true),
		"settings": get_settings(), "active_settings": _active_settings.duplicate(true),
		"outgoing": _outgoing, "survivor": _survivor, "incoming": _incoming,
		"actors": actors, "completed_handoffs": _completed_handoffs}


func _begin_phase(phase: String, duration: float, actor_id: String, from_x: float, to_x: float) -> void:
	_phase = phase
	_phase_elapsed = 0.0
	_phase_duration = duration
	_phase_actor = actor_id
	_motion_from = from_x
	_motion_to = to_x


func _complete_phase() -> void:
	_positions[_phase_actor] = _motion_to
	match _phase:
		"exit":
			_visible[_outgoing] = false
			_occupancy["left"] = ""
			if _active_settings["pattern"] == "shift_and_replace":
				_begin_phase("move", float(_active_settings["motion_duration_seconds"]), _survivor,
					float(_positions[_survivor]), float(_slots["left"]))
			else:
				_begin_entrance("left")
		"move":
			_occupancy["left"] = _survivor
			_occupancy["right"] = ""
			_begin_entrance("right")
		"enter":
			_completed_handoffs += 1
			_phase = "idle"
			_phase_elapsed = 0.0
			_phase_duration = 0.0
			_phase_actor = ""
			_active_settings.clear()
			_outgoing = ""
			_survivor = ""
			_incoming = ""


func _begin_entrance(slot: String) -> void:
	var target := float(_slots[slot])
	var direction := -1.0 if slot == "left" else 1.0
	var origin := target + direction * float(_active_settings["travel_distance"])
	_exit.show_actor(_incoming)
	_positions[_incoming] = origin
	_visible[_incoming] = true
	_occupancy[slot] = _incoming
	_begin_phase("enter", float(_active_settings["motion_duration_seconds"]), _incoming, origin, target)


func _validate_settings(settings: Dictionary) -> Array[String]:
	var errors := MOTION_CURVE.validate(settings)
	for field: Variant in settings:
		if field not in SETTING_FIELDS:
			errors.append("Unknown Cast Transition setting: " + str(field))
	if settings.get("pattern") not in ["replace_in_place", "shift_and_replace"]:
		errors.append("Cast Transition pattern must be replace_in_place or shift_and_replace.")
	if settings.has("exit_preset") and not ANIMATION.valid_id(settings["exit_preset"]):
		errors.append("Cast Transition exit_preset must name a Character Exit preset.")
	if not ANIMATION.finite_number(settings.get("motion_duration_seconds")) or float(settings["motion_duration_seconds"]) < 0.4 or float(settings["motion_duration_seconds"]) > 1.4:
		errors.append("Cast Transition motion_duration_seconds must be finite and between 0.4 and 1.4.")
	if not ANIMATION.finite_number(settings.get("travel_distance")) or float(settings["travel_distance"]) < 40.0 or float(settings["travel_distance"]) > 120.0:
		errors.append("Cast Transition travel_distance must be finite and between 40 and 120 logical pixels.")
	return errors


func _validate_spec(value: Variant) -> Array[String]:
	var errors: Array[String] = []
	if not (value is Dictionary):
		return ["Cast Transition specification must be an object."]
	for field: Variant in value:
		if field not in SPEC_FIELDS:
			errors.append("Unknown Cast Transition specification field: " + str(field))
	if not ANIMATION.finite_number(value.get("version")) or float(value["version"]) != 1.0:
		errors.append("Cast Transition specification must have version 1.")
	if not ANIMATION.valid_id(value.get("exit_preset")):
		errors.append("Cast Transition exit_preset must name a Character Exit preset.")
	var defaults: Variant = value.get("defaults")
	if defaults is Dictionary:
		errors.append_array(_validate_settings(defaults))
	else:
		errors.append("Cast Transition defaults must be a settings object.")
	var slots: Variant = value.get("slots")
	if not (slots is Dictionary):
		errors.append("Cast Transition slots must name left and right centers.")
	else:
		for field: Variant in slots:
			if field not in ["left", "right"]:
				errors.append("Unknown Cast Transition slot: " + str(field))
		if not ANIMATION.finite_number(slots.get("left")) or not ANIMATION.finite_number(slots.get("right")):
			errors.append("Cast Transition slot centers must be finite numbers.")
		elif float(slots["left"]) < 0.0 or float(slots["right"]) > 1280.0 or float(slots["left"]) >= float(slots["right"]):
			errors.append("Cast Transition slot centers must be ordered inside the 1280-pixel canvas.")
	var tracks: Variant = value.get("entrance_tracks")
	var track_errors: Array[String] = []
	ANIMATION.validate_tracks(tracks, "Cast Transition entrance_tracks", track_errors)
	errors.append_array(track_errors)
	if track_errors.is_empty():
		for channel: String in tracks:
			if channel != "opacity":
				errors.append("Cast Transition entrance_tracks supports only opacity.")
		if float(ANIMATION.evaluate(tracks, 0.0)["opacity"]) != 0.0 or float(ANIMATION.evaluate(tracks, 1.0)["opacity"]) != 1.0:
			errors.append("Cast Transition entrance opacity must start at zero and end at one.")
	return errors
