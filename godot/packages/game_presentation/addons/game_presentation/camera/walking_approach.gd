extends RefCounted

## A background-only approach cue. The host owns its clock and applies the
## sampled transform to the authored background rectangle, never last frame's.
const DEFAULT_SETTINGS := {
	"duration_seconds": 5.5,
	"target_zoom": 1.24,
	"bob_amplitude": 12.0,
	"bob_cycles_per_second": 1.6,
}
const SETTING_LIMITS := {
	"duration_seconds": [1.0, 15.0],
	"target_zoom": [1.0, 1.8],
	"bob_amplitude": [0.0, 40.0],
	"bob_cycles_per_second": [0.5, 3.0],
}
const STATE_FIELDS := ["version", "initialized", "viewport_size", "background_rect", "settings", "shot_settings", "has_shot", "elapsed"]

var initialized := false
var _viewport_size := Vector2(1280.0, 900.0)
var _background_rect := Rect2(0.0, 0.0, 1280.0, 900.0)
var _settings: Dictionary = DEFAULT_SETTINGS.duplicate()
var _shot_settings: Dictionary = DEFAULT_SETTINGS.duplicate()
var _has_shot := false
var _elapsed := 0.0


## Successful initialization cancels the current shot, keeping configured defaults.
func initialize(viewport_size: Vector2, background_rect: Rect2) -> Array[String]:
	var errors := _bounds_errors(viewport_size, background_rect)
	if not errors.is_empty():
		return errors
	_viewport_size = viewport_size
	_background_rect = background_rect
	initialized = true
	clear()
	return errors


## Settings affect the next start. A running or held shot retains its snapshot.
func configure(partial_settings: Dictionary) -> Array[String]:
	var errors := _settings_errors(partial_settings, false)
	if not errors.is_empty():
		return errors
	for field: String in partial_settings:
		_settings[field] = float(partial_settings[field])
	return errors


## Overrides apply only to this shot. Every replay starts from authored wide.
func start(overrides: Dictionary = {}) -> Array[String]:
	var errors := _settings_errors(overrides, false)
	if not initialized:
		errors.append("Walking approach is not initialized.")
	if not errors.is_empty():
		return errors
	_shot_settings = _settings.duplicate()
	for field: String in overrides:
		_shot_settings[field] = float(overrides[field])
	_has_shot = true
	_elapsed = 0.0
	return errors


func advance(delta: float) -> void:
	if not is_active() or not is_finite(delta) or delta <= 0.0:
		return
	var duration := float(_shot_settings["duration_seconds"])
	_elapsed = minf(duration, _elapsed + minf(delta, duration))
	if duration - _elapsed <= 0.000000001:
		_elapsed = duration


func is_active() -> bool:
	return initialized and _has_shot and _elapsed < float(_shot_settings["duration_seconds"])


## Absolute affine transform in logical screen coordinates: world * zoom + offset.
## bob_y is the actual vertical contribution after reducing amplitude for coverage.
func sample() -> Dictionary:
	if not initialized or not _has_shot:
		return {"zoom": 1.0, "offset_x": 0.0, "offset_y": 0.0, "bob_y": 0.0, "progress": 0.0, "active": false}
	var progress := clampf(_elapsed / float(_shot_settings["duration_seconds"]), 0.0, 1.0)
	var zoom := lerpf(1.0, float(_shot_settings["target_zoom"]), smoothstep(0.0, 1.0, progress))
	var centered_offset := _viewport_size * 0.5 * (1.0 - zoom)
	var minimum := _viewport_size - _background_rect.end * zoom
	var maximum := -_background_rect.position * zoom
	var offset := Vector2(clampf(centered_offset.x, minimum.x, maximum.x), clampf(centered_offset.y, minimum.y, maximum.y))
	var bob := 0.0
	if progress > 0.0 and progress < 1.0:
		# This envelope has zero velocity at arrival and departure. Limiting its
		# amplitude before applying the sine avoids flattened, clipped footsteps.
		var envelope := pow(sin(PI * progress), 2.0)
		var margin := maxf(0.0, minf(offset.y - minimum.y, maximum.y - offset.y))
		var amplitude := minf(float(_shot_settings["bob_amplitude"]) * envelope, margin)
		bob = sin(TAU * float(_shot_settings["bob_cycles_per_second"]) * _elapsed) * amplitude
	# The final clamp handles floating-point rounding at background boundaries.
	var final_y := clampf(offset.y + bob, minimum.y, maximum.y)
	bob = final_y - offset.y
	return {"zoom": zoom, "offset_x": offset.x, "offset_y": final_y, "bob_y": bob, "progress": progress, "active": is_active()}


## Skip completes the current cue, holding its exact final zoom with no bob.
func skip() -> void:
	if initialized and _has_shot:
		_elapsed = float(_shot_settings["duration_seconds"])


## Cancel and return to authored wide. The host can start a fresh cue afterward.
func clear() -> void:
	_has_shot = false
	_elapsed = 0.0
	_shot_settings = _settings.duplicate()


func get_settings() -> Dictionary:
	return _settings.duplicate()


## An in-memory pause snapshot; it includes source geometry and next-shot defaults.
func get_state() -> Dictionary:
	return {"version": 1, "initialized": initialized,
		"viewport_size": [_viewport_size.x, _viewport_size.y],
		"background_rect": [_background_rect.position.x, _background_rect.position.y, _background_rect.size.x, _background_rect.size.y],
		"settings": _settings.duplicate(), "shot_settings": _shot_settings.duplicate(),
		"has_shot": _has_shot, "elapsed": _elapsed}


## Validate the complete snapshot before replacing any live fields.
func restore(saved: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in saved:
		if field not in STATE_FIELDS:
			errors.append("Unknown walking-approach state field: " + str(field))
	if not _finite_number(saved.get("version")) or float(saved["version"]) != 1.0:
		errors.append("Walking-approach state must have version 1.")
	if not (saved.get("initialized") is bool) or not (saved.get("has_shot") is bool):
		errors.append("Walking-approach initialized and has_shot state must be booleans.")
	if not _finite_number(saved.get("elapsed")) or float(saved["elapsed"]) < 0.0:
		errors.append("Walking-approach elapsed time must be finite and nonnegative.")
	for field: String in ["settings", "shot_settings"]:
		if not (saved.get(field) is Dictionary):
			errors.append("Walking-approach " + field + " must be an object.")
		else:
			errors.append_array(_settings_errors(saved[field], true))
	if not _number_array(saved.get("viewport_size"), 2) or not _number_array(saved.get("background_rect"), 4):
		errors.append("Walking-approach saved bounds must contain finite coordinate arrays.")
		return errors
	var view := Vector2(float(saved["viewport_size"][0]), float(saved["viewport_size"][1]))
	var background := Rect2(float(saved["background_rect"][0]), float(saved["background_rect"][1]), float(saved["background_rect"][2]), float(saved["background_rect"][3]))
	errors.append_array(_bounds_errors(view, background))
	if not errors.is_empty():
		return errors
	if not bool(saved["initialized"]) and bool(saved["has_shot"]):
		return ["An uninitialized walking approach cannot have a shot."]
	if not bool(saved["has_shot"]) and float(saved["elapsed"]) != 0.0:
		return ["Walking-approach elapsed time must be zero when no shot exists."]
	if float(saved["elapsed"]) > float(saved["shot_settings"]["duration_seconds"]):
		return ["Walking-approach elapsed time cannot exceed its shot duration."]
	initialized = bool(saved["initialized"])
	_viewport_size = view
	_background_rect = background
	_settings = saved["settings"].duplicate()
	_shot_settings = saved["shot_settings"].duplicate()
	_has_shot = bool(saved["has_shot"])
	_elapsed = float(saved["elapsed"])
	return errors


func _settings_errors(candidate: Dictionary, require_complete: bool) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in candidate:
		if not DEFAULT_SETTINGS.has(field):
			errors.append("Unknown walking-approach setting: " + str(field))
	for field: String in DEFAULT_SETTINGS:
		if not candidate.has(field) and not require_complete:
			continue
		if not _finite_number(candidate.get(field)):
			errors.append("Walking-approach " + field + " must be a finite number.")
			continue
		var limits: Array = SETTING_LIMITS[field]
		var value := float(candidate[field])
		if value < float(limits[0]) or value > float(limits[1]):
			errors.append("Walking-approach " + field + " must lie between " + str(limits[0]) + " and " + str(limits[1]) + ".")
	return errors


func _bounds_errors(viewport_size: Vector2, background_rect: Rect2) -> Array[String]:
	if not viewport_size.is_finite() or not background_rect.position.is_finite() or not background_rect.size.is_finite() or not background_rect.end.is_finite() or viewport_size.x <= 0.0 or viewport_size.y <= 0.0 or background_rect.size.x <= 0.0 or background_rect.size.y <= 0.0:
		return ["Walking-approach bounds must be finite and have positive dimensions."]
	if not (background_rect.position * 1.8).is_finite() or not (background_rect.size * 1.8).is_finite() or not (background_rect.end * 1.8).is_finite():
		return ["Walking-approach bounds must remain finite at maximum zoom."]
	if not background_rect.encloses(Rect2(Vector2.ZERO, viewport_size)):
		return ["Walking-approach background must cover the design viewport at authored wide."]
	return []


func _finite_number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))


func _number_array(value: Variant, count: int) -> bool:
	if not (value is Array) or value.size() != count:
		return false
	for number: Variant in value:
		if not _finite_number(number):
			return false
	return true
