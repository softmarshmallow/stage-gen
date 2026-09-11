extends RefCounted

## Finite, host-clocked camera translation with smooth onset and settlement.
const DEFAULT_SETTINGS := {
	"amplitude_x": 28.0,
	"amplitude_y": 22.0,
	"frequency": 11.0,
	"duration": 1.35,
	"attack": 0.08,
	"seed": 0,
}
const LIMITS := {
	"amplitude_x": [0.0, 128.0],
	"amplitude_y": [0.0, 128.0],
	"frequency": [0.5, 40.0],
	"duration": [0.1, 30.0],
	"attack": [0.01, 5.0],
	"seed": [0.0, 65535.0],
}

var _settings: Dictionary = DEFAULT_SETTINGS.duplicate()
var _elapsed := 0.0
var _active := false


## A valid start replaces the previous cue; invalid settings leave it untouched.
func start(settings: Dictionary = {}) -> Array[String]:
	var candidate := DEFAULT_SETTINGS.duplicate()
	candidate.merge(settings, true)
	var errors := _settings_errors(candidate)
	if not errors.is_empty():
		return errors
	_settings = candidate
	_elapsed = 0.0
	_active = true
	return errors


func advance(delta: float) -> void:
	if not _active or not is_finite(delta) or delta <= 0.0:
		return
	_elapsed = minf(float(_settings.duration), _elapsed + minf(delta, float(_settings.duration)))
	_active = _elapsed < float(_settings.duration)


## Displacement and maximum displacement are logical screen pixels.
func sample() -> Dictionary:
	if not _active:
		return {"offset_x": 0.0, "offset_y": 0.0, "envelope": 0.0,
			"max_offset_x": 0.0, "max_offset_y": 0.0, "active": false}
	var attack := float(_settings.attack)
	var envelope := smoothstep(0.0, attack, _elapsed) * (1.0 - smoothstep(attack, float(_settings.duration), _elapsed))
	var phase := TAU * float(_settings.frequency) * _elapsed
	var seed_phase := fposmod(float(_settings.seed) * 2.39996323, TAU)
	var maximum := Vector2(float(_settings.amplitude_x), float(_settings.amplitude_y)) * envelope
	var x := (sin(phase + seed_phase) * 0.72 + sin(phase * 1.73 + seed_phase * 0.71) * 0.28) * maximum.x
	var y := (sin(phase * 0.87 + seed_phase + 1.1) * 0.72 + sin(phase * 1.41 - seed_phase * 0.53) * 0.28) * maximum.y
	return {"offset_x": x, "offset_y": y, "envelope": envelope,
		"max_offset_x": maximum.x, "max_offset_y": maximum.y, "active": true}


func is_active() -> bool:
	return _active


## Immediate cancellation; normal completion settles without a transform jump.
func clear() -> void:
	_settings = DEFAULT_SETTINGS.duplicate()
	_elapsed = 0.0
	_active = false


## Base must already cover. Do not feed the previous composed frame back in.
## Positive, axis-aligned transforms only; no rotation or skew is introduced.
func compose(base: Transform2D, background: Rect2, viewport: Vector2) -> Transform2D:
	if not can_compose(base, background, viewport):
		return base
	var pose := sample()
	if float(pose.envelope) == 0.0:
		return base
	var guard := 1.0 + maxf(2.0 * float(pose.max_offset_x) / viewport.x, 2.0 * float(pose.max_offset_y) / viewport.y)
	var center := viewport * 0.5
	var offset := Vector2(float(pose.offset_x), float(pose.offset_y))
	var result := Transform2D(base.x * guard, base.y * guard, center + (base.origin - center) * guard + offset)
	var transformed := Rect2(result * background.position, background.size * Vector2(result.x.x, result.y.y))
	var correction := Vector2(clampf(0.0, viewport.x - transformed.end.x, -transformed.position.x),
		clampf(0.0, viewport.y - transformed.end.y, -transformed.position.y))
	result.origin += correction
	return result


## False means the host must fix its base framing; composition cannot repair it.
static func can_compose(base: Transform2D, background: Rect2, viewport: Vector2) -> bool:
	if not base.is_finite() or base.x.x <= 0.0 or base.y.y <= 0.0 or base.x.y != 0.0 or base.y.x != 0.0:
		return false
	if not viewport.is_finite() or viewport.x <= 0.0 or viewport.y <= 0.0:
		return false
	if not background.position.is_finite() or not background.size.is_finite() or not background.end.is_finite() or background.size.x <= 0.0 or background.size.y <= 0.0:
		return false
	var transformed := Rect2(base * background.position, background.size * Vector2(base.x.x, base.y.y))
	return transformed.position.is_finite() and transformed.size.is_finite() and transformed.end.is_finite() and transformed.encloses(Rect2(Vector2.ZERO, viewport))


func get_state() -> Dictionary:
	return {"version": 1, "settings": _settings.duplicate(), "elapsed": _elapsed, "active": _active}


## Complete detached in-session snapshots; malformed input is rejected atomically.
func restore(saved: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in saved:
		if field not in ["version", "settings", "elapsed", "active"]:
			errors.append("Unknown impact-shake state field: " + str(field))
	if not _finite_number(saved.get("version")) or float(saved.version) != 1.0:
		errors.append("Impact-shake state must have version 1.")
	if not (saved.get("settings") is Dictionary):
		errors.append("Impact-shake settings must be an object.")
	else:
		errors.append_array(_settings_errors(saved.settings))
	if not _finite_number(saved.get("elapsed")) or float(saved.elapsed) < 0.0:
		errors.append("Impact-shake elapsed time must be finite and nonnegative.")
	if not (saved.get("active") is bool):
		errors.append("Impact-shake active state must be a boolean.")
	if not errors.is_empty():
		return errors
	var duration := float(saved.settings.duration)
	var elapsed := float(saved.elapsed)
	if elapsed > duration or (bool(saved.active) and elapsed >= duration) or (not bool(saved.active) and elapsed != 0.0 and elapsed != duration):
		return ["Impact-shake clock and active status are inconsistent."]
	_settings = saved.settings.duplicate()
	_elapsed = elapsed
	_active = bool(saved.active)
	return errors


static func _settings_errors(candidate: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in candidate:
		if not DEFAULT_SETTINGS.has(field):
			errors.append("Unknown impact-shake setting: " + str(field))
	for field: String in DEFAULT_SETTINGS:
		if not _finite_number(candidate.get(field)):
			errors.append("Impact-shake " + field + " must be a finite number.")
			continue
		var value := float(candidate[field])
		var limits: Array = LIMITS[field]
		if value < float(limits[0]) or value > float(limits[1]):
			errors.append("Impact-shake " + field + " is outside its supported range.")
	if errors.is_empty():
		if float(candidate.attack) >= float(candidate.duration):
			errors.append("Impact-shake attack must be shorter than duration.")
		if float(candidate.seed) != floorf(float(candidate.seed)):
			errors.append("Impact-shake seed must be an integer.")
	return errors


static func _finite_number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))
