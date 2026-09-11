extends RefCounted

## First-person eyelid coverage, independent of a character's blink animation.
## The host owns the clock, screen-space mask, scene changes, and input.
const DEFAULT_SETTINGS := {
	"opening_seconds": 2.2,
	"closing_seconds": 0.4,
	"closed_hold_seconds": 0.18,
	"peek_seconds": 0.22,
	"peek_openness": 0.42,
}
const SETTING_RANGES := {
	"opening_seconds": [0.1, 8.0],
	"closing_seconds": [0.1, 4.0],
	"closed_hold_seconds": [0.0, 2.0],
	"peek_seconds": [0.05, 2.0],
	"peek_openness": [0.05, 1.0],
}
const MODES := ["eye_opening", "eye_closing", "blink", "waking_opening"]
const LEGACY_SETTINGS := ["opening_seconds", "closing_seconds", "closed_hold_seconds"]
const STATE_FIELDS := ["version", "mode", "defaults", "active_settings", "elapsed"]

var _defaults: Dictionary = DEFAULT_SETTINGS.duplicate()
var _active_settings: Dictionary = DEFAULT_SETTINGS.duplicate()
var _mode := ""
var _elapsed := 0.0


## Configuration affects future starts, including explicit replay. It does not
## retime the current transition. Invalid settings leave all state unchanged.
func configure(partial_settings: Dictionary) -> Array[String]:
	var errors := _validate_settings(partial_settings, false)
	if errors.is_empty():
		_defaults.merge(partial_settings, true)
	return errors


## Every start begins at its own endpoint: opening and waking start closed;
## closing and blink start open. The host chooses what is revealed behind it.
func start(mode: String, overrides: Dictionary = {}) -> Array[String]:
	var errors := _validate_settings(overrides, false)
	if mode not in MODES:
		errors.append("Unknown Eye Transition mode: " + mode)
	if not errors.is_empty():
		return errors
	var settings := _defaults.duplicate()
	settings.merge(overrides, true)
	_mode = mode
	_active_settings = settings
	_elapsed = 0.0
	return errors


## Time is clamped at completion. sample().elapsed lets a host compute unused
## delta when it needs to advance another authored cue in the same frame.
func advance(delta: float) -> void:
	if not is_active() or not is_finite(delta) or delta <= 0.0:
		return
	_elapsed = minf(_elapsed + delta, _total_seconds(_mode, _active_settings))


func sample() -> Dictionary:
	var total := _total_seconds(_mode, _active_settings)
	var openness := 1.0
	var phase := "open"
	var reached_closed := false
	var active := is_active()
	match _mode:
		"eye_opening":
			openness = _ease(_elapsed / float(_active_settings["opening_seconds"]))
			phase = "opening" if active else "open"
			reached_closed = true
		"eye_closing":
			openness = 1.0 - _ease(_elapsed / float(_active_settings["closing_seconds"]))
			phase = "closing" if active else "closed"
			reached_closed = not active
		"blink":
			var closing := float(_active_settings["closing_seconds"])
			var opening_start := closing + float(_active_settings["closed_hold_seconds"])
			reached_closed = _elapsed >= closing
			if _elapsed < closing:
				openness = 1.0 - _ease(_elapsed / closing)
				phase = "closing"
			elif _elapsed < opening_start:
				openness = 0.0
				phase = "closed"
			else:
				openness = _ease((_elapsed - opening_start) / float(_active_settings["opening_seconds"]))
				phase = "opening" if active else "open"
		"waking_opening":
			var peek := float(_active_settings["peek_seconds"])
			var peak := float(_active_settings["peek_openness"])
			var closing := float(_active_settings["closing_seconds"])
			var closed_start := peek + closing
			var opening_start := closed_start + float(_active_settings["closed_hold_seconds"])
			reached_closed = true
			if _elapsed < peek:
				openness = peak * _ease(_elapsed / peek)
				phase = "peeking"
			elif _elapsed < closed_start:
				openness = peak * (1.0 - _ease((_elapsed - peek) / closing))
				phase = "closing"
			elif _elapsed < opening_start:
				openness = 0.0
				phase = "closed"
			else:
				openness = _ease((_elapsed - opening_start) / float(_active_settings["opening_seconds"]))
				phase = "opening" if active else "open"
	# Exact ending samples prevent accumulated time error from leaving a veil.
	if not active:
		openness = 0.0 if _mode == "eye_closing" else 1.0
	return {
		"openness": openness,
		"phase": phase,
		"active": active,
		"progress": _elapsed / total if total > 0.0 else 1.0,
		"elapsed": _elapsed,
		"total_seconds": total,
		"reached_closed": reached_closed,
	}


func is_active() -> bool:
	return not _mode.is_empty() and _elapsed < _total_seconds(_mode, _active_settings)


## Complete the selected transition; closing deliberately keeps the mask shut.
func skip() -> void:
	_elapsed = _total_seconds(_mode, _active_settings)


## Cancel any transition and return the fully open identity.
func clear() -> void:
	_mode = ""
	_elapsed = 0.0
	_active_settings = _defaults.duplicate()


func get_settings() -> Dictionary:
	return _defaults.duplicate()


func get_state() -> Dictionary:
	return {
		"version": 2,
		"mode": _mode,
		"defaults": _defaults.duplicate(),
		"active_settings": _active_settings.duplicate(),
		"elapsed": _elapsed,
	}


## Snapshots contain only portable scalar values and are validated atomically.
## Derived status cannot disagree with the saved mode, settings, and time.
func restore(state: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in state:
		if key not in STATE_FIELDS:
			errors.append("Unknown Eye Transition state field: " + str(key))
	for key: String in STATE_FIELDS:
		if not state.has(key):
			errors.append("Missing Eye Transition state field: " + key)
	if not errors.is_empty():
		return errors
	if not _is_number(state["version"]) or float(state["version"]) not in [1.0, 2.0]:
		errors.append("Eye Transition state version must be 1 or 2.")
	var legacy := _is_number(state["version"]) and float(state["version"]) == 1.0
	if not state["mode"] is String or (state["mode"] != "" and state["mode"] not in MODES):
		errors.append("Invalid Eye Transition state mode.")
	elif legacy and state["mode"] == "waking_opening":
		errors.append("Waking Opening requires an Eye Transition version 2 state.")
	for key: String in ["defaults", "active_settings"]:
		if not state[key] is Dictionary:
			errors.append("Eye Transition state " + key + " must be a dictionary.")
		else:
			errors.append_array(_validate_settings(state[key], true, legacy))
	if not _is_number(state["elapsed"]) or not is_finite(float(state["elapsed"])):
		errors.append("Eye Transition state elapsed must be a finite number.")
	if not errors.is_empty():
		return errors
	var elapsed := float(state["elapsed"])
	var restored_defaults := DEFAULT_SETTINGS.duplicate()
	restored_defaults.merge(state["defaults"], true)
	var restored_active := DEFAULT_SETTINGS.duplicate()
	restored_active.merge(state["active_settings"], true)
	var total := _total_seconds(state["mode"], restored_active)
	if elapsed < 0.0 or elapsed > total:
		return ["Eye Transition state elapsed is outside its transition duration."]
	_defaults = restored_defaults
	_active_settings = restored_active
	_mode = state["mode"]
	_elapsed = elapsed
	return errors


func _validate_settings(settings: Dictionary, require_all: bool, legacy: bool = false) -> Array[String]:
	var errors: Array[String] = []
	var fields: Array = LEGACY_SETTINGS if legacy else SETTING_RANGES.keys()
	for key: Variant in settings:
		if key not in fields:
			errors.append("Unknown Eye Transition setting: " + str(key))
			continue
		var value: Variant = settings[key]
		if not _is_number(value) or not is_finite(float(value)):
			errors.append("Eye Transition setting " + str(key) + " must be a finite number.")
			continue
		var limits: Array = SETTING_RANGES[key]
		if float(value) < float(limits[0]) or float(value) > float(limits[1]):
			errors.append("Eye Transition setting " + str(key) + " is outside its allowed range.")
	if require_all:
		for key: String in fields:
			if not settings.has(key):
				errors.append("Missing Eye Transition setting: " + key)
	return errors


func _is_number(value: Variant) -> bool:
	return value is int or value is float


func _total_seconds(mode: String, settings: Dictionary) -> float:
	match mode:
		"eye_opening":
			return float(settings["opening_seconds"])
		"eye_closing":
			return float(settings["closing_seconds"])
		"blink":
			return float(settings["closing_seconds"]) + float(settings["closed_hold_seconds"]) + float(settings["opening_seconds"])
		"waking_opening":
			return float(settings["peek_seconds"]) + float(settings["closing_seconds"]) + float(settings["closed_hold_seconds"]) + float(settings["opening_seconds"])
	return 0.0


func _ease(progress: float) -> float:
	var bounded := clampf(progress, 0.0, 1.0)
	return bounded * bounded * (3.0 - 2.0 * bounded)
