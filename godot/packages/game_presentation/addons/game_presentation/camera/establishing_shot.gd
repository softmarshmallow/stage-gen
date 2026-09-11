extends RefCounted

## A deterministic location-only opening. The renderer owns cover geometry and
## maps the authored light source into screen space; this clock owns timing.
const DEFAULTS := {"duration_seconds": 4.0, "pan_amount": 60.0, "zoom_amount": 0.08,
	"flare_strength": 0.35, "flare_enabled": false, "flare_source_uv": [0.8, 0.2]}
const STATE_FIELDS := ["version", "location_id", "elapsed", "active", "settings", "active_settings"]
var _settings: Dictionary = DEFAULTS.duplicate(true)
var _active_settings: Dictionary = {}
var _location_id := ""
var _elapsed := 0.0
var _active := false


## Configuration changes the next shot; an active shot keeps its own settings.
func configure(settings: Dictionary) -> Array[String]:
	var candidate := _settings.duplicate(true)
	candidate.merge(settings, true)
	var errors := _validate_settings(candidate)
	if errors.is_empty():
		_settings = candidate
	return errors


func start(location_id: String, overrides: Dictionary = {}) -> Array[String]:
	var candidate := _settings.duplicate(true)
	candidate.merge(overrides, true)
	var errors := _validate_settings(candidate)
	if not _valid_location_id(location_id):
		errors.append("An establishing shot requires a lower_snake_case location id.")
	if not errors.is_empty():
		return errors
	_active_settings = candidate
	_location_id = location_id
	_elapsed = 0.0
	_active = true
	return errors


func advance(delta: float) -> void:
	if not _active or not is_finite(delta) or delta <= 0.0:
		return
	var duration := float(_active_settings["duration_seconds"])
	_elapsed = minf(duration, _elapsed + delta)
	if duration - _elapsed <= 0.000000001:
		_elapsed = duration
		_active = false


func skip() -> void:
	if _active:
		_elapsed = float(_active_settings["duration_seconds"])
		_active = false


func clear() -> void:
	_location_id = ""
	_elapsed = 0.0
	_active = false
	_active_settings.clear()


func is_active() -> bool:
	return _active


func get_settings() -> Dictionary:
	return _settings.duplicate(true)


func get_state() -> Dictionary:
	return {"version": 1, "location_id": _location_id, "elapsed": _elapsed,
		"active": _active, "settings": get_settings(), "active_settings": _active_settings.duplicate(true)}


func restore(saved: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in saved:
		if field not in STATE_FIELDS:
			errors.append("Unknown establishing-shot state field: " + str(field))
	if not _finite_number(saved.get("version")) or float(saved["version"]) != 1.0:
		errors.append("Establishing-shot state must have version 1.")
	if not (saved.get("active") is bool) or not _finite_number(saved.get("elapsed")):
		errors.append("Establishing-shot state needs a boolean active flag and finite elapsed time.")
	if not (saved.get("settings") is Dictionary) or not (saved.get("active_settings") is Dictionary):
		errors.append("Establishing-shot state needs settings and active_settings objects.")
		return errors
	errors.append_array(_validate_settings(saved["settings"]))
	var location: Variant = saved.get("location_id")
	if location == "":
		if saved.get("active") != false or saved.get("elapsed") != 0.0 or not saved["active_settings"].is_empty():
			errors.append("An empty establishing-shot state must be inactive with no active settings or elapsed time.")
	elif not _valid_location_id(location):
		errors.append("Invalid establishing-shot location id.")
	else:
		var active_errors := _validate_settings(saved["active_settings"])
		errors.append_array(active_errors)
		if active_errors.is_empty() and _finite_number(saved.get("elapsed")):
			var duration := float(saved["active_settings"]["duration_seconds"])
			var elapsed := float(saved["elapsed"])
			if elapsed < 0.0 or elapsed > duration or (saved.get("active") == true and elapsed >= duration) or (saved.get("active") == false and elapsed != duration):
				errors.append("Establishing-shot elapsed time does not match its active/completed state.")
	if not errors.is_empty():
		return errors
	_settings = saved["settings"].duplicate(true)
	_active_settings = saved["active_settings"].duplicate(true)
	_location_id = String(location)
	_elapsed = float(saved["elapsed"])
	_active = bool(saved["active"])
	return errors


func sample() -> Dictionary:
	var progress := 1.0
	if _active:
		progress = clampf(_elapsed / float(_active_settings["duration_seconds"]), 0.0, 1.0)
	var remaining := 1.0 - smoothstep(0.0, 1.0, progress)
	var settings := _active_settings if not _active_settings.is_empty() else _settings
	var flare_envelope := smoothstep(0.0, 0.12, progress) * (1.0 - smoothstep(0.72, 1.0, progress))
	return {"active": _active, "location_id": _location_id, "progress": progress,
		"zoom": 1.0 + float(settings["zoom_amount"]) * remaining,
		"pan_x": float(settings["pan_amount"]) * remaining,
		"flare_strength": float(settings["flare_strength"]) * flare_envelope if settings["flare_enabled"] else 0.0,
		"flare_source_uv": settings["flare_source_uv"].duplicate()}


func _validate_settings(settings: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in settings:
		if not DEFAULTS.has(field):
			errors.append("Unknown establishing-shot setting: " + str(field))
	for spec: Array in [["duration_seconds", 2.0, 8.0], ["pan_amount", -120.0, 120.0], ["zoom_amount", 0.0, 0.16], ["flare_strength", 0.0, 1.0]]:
		var value: Variant = settings.get(spec[0])
		if not _finite_number(value) or float(value) < float(spec[1]) or float(value) > float(spec[2]):
			errors.append("Establishing-shot " + String(spec[0]) + " must be finite and between " + str(spec[1]) + " and " + str(spec[2]) + ".")
	if not (settings.get("flare_enabled") is bool):
		errors.append("Establishing-shot flare_enabled must be a boolean.")
	var source: Variant = settings.get("flare_source_uv")
	if not (source is Array) or source.size() != 2:
		errors.append("Establishing-shot flare_source_uv must be a two-number array.")
	else:
		for coordinate: Variant in source:
			if not _finite_number(coordinate) or float(coordinate) < 0.0 or float(coordinate) > 1.0:
				errors.append("Establishing-shot flare_source_uv coordinates must lie between zero and one.")
	return errors


func _finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


func _valid_location_id(value: Variant) -> bool:
	return value is String and not value.is_empty() and value == value.to_lower() and value.is_valid_identifier()
