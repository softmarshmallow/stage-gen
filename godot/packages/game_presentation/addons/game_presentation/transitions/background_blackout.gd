extends ColorRect

## Background-only coverage. The host places this layer above its environment
## and below its actors, advances its clock, and chooses when to restore it.
const PresentationAnimation := preload("res://addons/game_presentation/motion/presentation_animation.gd")

var _strength := 0.0
var _from := 0.0
var _target := 0.0
var _elapsed := 0.0
var _duration_seconds := 0.0
var _active := false
var _tracks: Dictionary = {"opacity": [[0.0, 0.0], [1.0, 0.0]]}


func _init() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_sync_coverage()


## Retarget from the currently presented opacity, including during a fade.
## A completed fade holds its target until another request or clear().
func fade_to(strength: float, duration_seconds: float = 0.4) -> Array[String]:
	var errors: Array[String] = []
	if not is_finite(strength) or strength < 0.0 or strength > 1.0:
		errors.append("Background Blackout strength must be finite and between 0 and 1.")
	if not is_finite(duration_seconds) or duration_seconds < 0.0 or duration_seconds > 30.0:
		errors.append("Background Blackout duration_seconds must be finite and between 0 and 30.")
	if not errors.is_empty():
		return errors
	_from = _strength
	_target = strength
	_duration_seconds = duration_seconds
	_active = duration_seconds > 0.0 and _from != _target
	_elapsed = 0.0 if _active else duration_seconds
	_tracks = {"opacity": [[0.0, _from], [1.0, _target]]}
	if not _active:
		_strength = _target
	_sync_coverage()
	return errors


## No autonomous process or Tween runs. Invalid input leaves state untouched.
func advance(delta: float) -> Array[String]:
	if not is_finite(delta) or delta < 0.0:
		return ["Background Blackout delta must be finite and nonnegative."]
	if not _active or delta == 0.0:
		return []
	_elapsed = minf(_duration_seconds, _elapsed + delta)
	_strength = float(PresentationAnimation.sample(_tracks, _elapsed, _duration_seconds)["opacity"])
	_active = _elapsed < _duration_seconds
	if not _active:
		_strength = _target
	_sync_coverage()
	return []


func clear() -> void:
	_strength = 0.0
	_from = 0.0
	_target = 0.0
	_elapsed = 0.0
	_duration_seconds = 0.0
	_active = false
	_tracks = {"opacity": [[0.0, 0.0], [1.0, 0.0]]}
	_sync_coverage()


func get_state() -> Dictionary:
	return {
		"strength": _strength,
		"from": _from,
		"target": _target,
		"elapsed": _elapsed,
		"duration_seconds": _duration_seconds,
		"active": _active,
	}


func is_active() -> bool:
	return _active


func _sync_coverage() -> void:
	color = Color(0.0, 0.0, 0.0, _strength)
	visible = _strength > 0.0
