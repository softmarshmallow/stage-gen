extends RefCounted

## Host-clocked translation around an authored frame. No scene or asset ownership.
const DEFAULT_SETTINGS := {
	"amplitude_x": 8.0,
	"amplitude_y": 5.0,
	"period_x": 7.0,
	"period_y": 9.0,
	"phase_y": 0.7,
}
const SETTING_LIMITS := {
	"amplitude_x": [0.0, 64.0],
	"amplitude_y": [0.0, 64.0],
	"period_x": [0.5, 120.0],
	"period_y": [0.5, 120.0],
	"phase_y": [-TAU, TAU],
}
const STATE_FIELDS := ["version", "active", "settings", "time_x", "time_y", "onset_elapsed"]

var _active := false
var _settings: Dictionary = DEFAULT_SETTINGS.duplicate()
var _time_x := 0.0
var _time_y := 0.0
var _onset_elapsed := 0.0


## Start or replace a cue at zero translation. Unspecified settings use defaults.
func start(settings: Dictionary = {}) -> Array[String]:
	var errors := _settings_errors(settings, false)
	if not errors.is_empty():
		return errors
	_settings = DEFAULT_SETTINGS.duplicate()
	for field: String in settings:
		_settings[field] = float(settings[field])
	_active = true
	_time_x = 0.0
	_time_y = 0.0
	_onset_elapsed = 0.0
	return errors


## Pausing means withholding time. Wrapped clocks avoid growing phase values.
func advance(delta: float) -> void:
	if not _active or not is_finite(delta) or delta <= 0.0:
		return
	var period_x := float(_settings["period_x"])
	var period_y := float(_settings["period_y"])
	_time_x = fposmod(_time_x + fposmod(delta, period_x), period_x)
	_time_y = fposmod(_time_y + fposmod(delta, period_y), period_y)
	var onset_duration := _onset_duration(_settings)
	_onset_elapsed = minf(onset_duration, _onset_elapsed + minf(delta, onset_duration))


## Translation in logical screen pixels; add once to each authored world layer.
func sample() -> Dictionary:
	if not _active:
		return {"offset_x": 0.0, "offset_y": 0.0, "active": false}
	var envelope := smoothstep(0.0, _onset_duration(_settings), _onset_elapsed)
	var x := float(_settings["amplitude_x"]) * sin(TAU * _time_x / float(_settings["period_x"])) * envelope
	var y := float(_settings["amplitude_y"]) * sin(TAU * _time_y / float(_settings["period_y"]) + float(_settings["phase_y"])) * envelope
	return {"offset_x": x, "offset_y": y, "active": true}


func is_active() -> bool:
	return _active


## Cancel immediately. The host owns any transition back to its authored frame.
func clear() -> void:
	_active = false
	_settings = DEFAULT_SETTINGS.duplicate()
	_time_x = 0.0
	_time_y = 0.0
	_onset_elapsed = 0.0


func get_state() -> Dictionary:
	return {"version": 1, "active": _active, "settings": _settings.duplicate(),
		"time_x": _time_x, "time_y": _time_y, "onset_elapsed": _onset_elapsed}


## Validate a complete snapshot before replacing any state. No disk-save schema.
func restore(saved: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in saved:
		if field not in STATE_FIELDS:
			errors.append("Unknown camera-drift state field: " + str(field))
	if not _finite_number(saved.get("version")) or float(saved["version"]) != 1.0:
		errors.append("Camera-drift state must have version 1.")
	if not (saved.get("active") is bool):
		errors.append("Camera-drift active state must be a boolean.")
	if not (saved.get("settings") is Dictionary):
		errors.append("Camera-drift settings must be an object.")
	else:
		errors.append_array(_settings_errors(saved["settings"], true))
	for field: String in ["time_x", "time_y", "onset_elapsed"]:
		if not _finite_number(saved.get(field)) or float(saved[field]) < 0.0:
			errors.append("Camera-drift " + field + " must be finite and nonnegative.")
	if not errors.is_empty():
		return errors
	var settings: Dictionary = saved["settings"]
	if float(saved["time_x"]) >= float(settings["period_x"]) or float(saved["time_y"]) >= float(settings["period_y"]):
		return ["Camera-drift axis times must be less than their periods."]
	if float(saved["onset_elapsed"]) > _onset_duration(settings):
		return ["Camera-drift onset time must not exceed its duration."]
	if not bool(saved["active"]) and (float(saved["time_x"]) != 0.0 or float(saved["time_y"]) != 0.0 or float(saved["onset_elapsed"]) != 0.0):
		return ["An inactive camera drift must have zero clock values."]
	_active = bool(saved["active"])
	_settings = settings.duplicate()
	_time_x = float(saved["time_x"])
	_time_y = float(saved["time_y"])
	_onset_elapsed = float(saved["onset_elapsed"])
	return errors


## Host must refuse drift if the unshifted final background does not cover.
static func can_cover(base_background: Rect2, viewport_size: Vector2) -> bool:
	if not viewport_size.is_finite() or viewport_size.x <= 0.0 or viewport_size.y <= 0.0:
		return false
	if not base_background.position.is_finite() or not base_background.size.is_finite() or not base_background.end.is_finite():
		return false
	if base_background.size.x <= 0.0 or base_background.size.y <= 0.0:
		return false
	return base_background.encloses(Rect2(Vector2.ZERO, viewport_size))


## Geometry is after authored zoom/crop, before drift. Apply returned offset to
## both background and portraits. Zero is only a no-op fallback for bad geometry.
static func constrain_offset(base_background: Rect2, viewport_size: Vector2, offset: Vector2) -> Vector2:
	if not can_cover(base_background, viewport_size) or not offset.is_finite():
		return Vector2.ZERO
	var minimum := viewport_size - base_background.end
	var maximum := -base_background.position
	return Vector2(clampf(offset.x, minimum.x, maximum.x), clampf(offset.y, minimum.y, maximum.y))


static func _onset_duration(settings: Dictionary) -> float:
	return minf(1.0, minf(float(settings["period_x"]), float(settings["period_y"])) * 0.25)


static func _settings_errors(candidate: Dictionary, require_complete: bool) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in candidate:
		if not DEFAULT_SETTINGS.has(field):
			errors.append("Unknown camera-drift setting: " + str(field))
	for field: String in DEFAULT_SETTINGS:
		if not candidate.has(field) and not require_complete:
			continue
		if not _finite_number(candidate.get(field)):
			errors.append("Camera-drift " + field + " must be a finite number.")
			continue
		var limits: Array = SETTING_LIMITS[field]
		var value := float(candidate[field])
		if value < float(limits[0]) or value > float(limits[1]):
			errors.append("Camera-drift " + field + " must lie between " + str(limits[0]) + " and " + str(limits[1]) + ".")
	return errors


static func _finite_number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))
