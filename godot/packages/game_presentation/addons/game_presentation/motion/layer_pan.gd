extends RefCounted

## Translation of a host-selected layer. The host owns members, placement,
## camera composition and clock; the sampler owns only the current offset.
const MOTION_CURVE = preload("res://addons/game_presentation/motion/motion_curve.gd")
const DEFAULT_SETTINGS := {"duration_seconds": 0.45, "curve": "ease_in_out", "frequency": 1.5, "damping_ratio": 0.8}

var _from := Vector2.ZERO
var _target := Vector2.ZERO
var _elapsed := 0.0
var _settings: Dictionary = DEFAULT_SETTINGS.duplicate()


func _init() -> void:
	clear()


## Retarget continuously from the currently sampled offset. No content bounds
## are imposed: the host decides which offsets suit its selected layer.
func pan_to(offset: Vector2, settings: Dictionary = {}) -> Array[String]:
	var errors: Array[String] = []
	if not offset.is_finite():
		errors.append("Layer Pan offset must be finite.")
	for key: Variant in settings:
		if not DEFAULT_SETTINGS.has(key):
			errors.append("Unknown Layer Pan setting: " + str(key))
	var configured := DEFAULT_SETTINGS.duplicate()
	configured.merge(settings, true)
	var duration: Variant = configured["duration_seconds"]
	if not (duration is float or duration is int) or not is_finite(float(duration)) or float(duration) < 0.0 or float(duration) > 5.0:
		errors.append("Layer Pan duration_seconds must be finite and between 0 and 5.")
	errors.append_array(MOTION_CURVE.validate(configured))
	if not errors.is_empty():
		return errors
	_from = sample_transform().origin
	_target = offset
	_settings = configured
	_elapsed = float(duration) if _from == _target else 0.0
	return []


## Pause by withholding time. Invalid or nonpositive delta is ignored.
func advance(delta: float) -> void:
	if not is_moving() or not is_finite(delta) or delta <= 0.0:
		return
	_elapsed = minf(float(_settings["duration_seconds"]), _elapsed + delta)


func sample_transform() -> Transform2D:
	if not is_moving():
		return Transform2D(0.0, _target)
	var weight: float = MOTION_CURVE.sample(_elapsed / float(_settings["duration_seconds"]), _settings)
	return Transform2D(0.0, _from.lerp(_target, weight))


func get_state() -> Dictionary:
	return {"from": _from, "target": _target, "offset": sample_transform().origin,
		"elapsed": _elapsed, "settings": _settings.duplicate(true), "moving": is_moving()}


func is_moving() -> bool:
	return _elapsed < float(_settings["duration_seconds"])


func clear() -> void:
	_from = Vector2.ZERO
	_target = Vector2.ZERO
	_elapsed = 0.0
	_settings = DEFAULT_SETTINGS.duplicate()
	_settings["duration_seconds"] = 0.0
