extends RefCounted

## One explicit world-camera cue, held until another focus or wide cue arrives.
## Actors, attached marks, and scenery share the resulting affine transform.
## Linear interpolation of scale/offset with common smoothstep time preserves
## background coverage between two valid endpoints (the bounds are convex).
const IDENTITY := {"zoom": 1.0, "offset_x": 0.0, "offset_y": 0.0}
const MAX_ZOOM := 4.0
const STATE_FIELDS := ["version", "initialized", "focus_id", "elapsed", "duration_seconds", "viewport_size", "background_rect", "from", "to"]
var initialized := false
var focus_id := ""
var _viewport_size := Vector2(1280, 900)
var _background_rect := Rect2(0, 0, 1280, 900)
var _elapsed := 0.0
var _duration_seconds := 0.0
var _from: Dictionary = IDENTITY.duplicate()
var _to: Dictionary = IDENTITY.duplicate()


func initialize(viewport_size: Vector2, background_rect: Rect2) -> Array[String]:
	var errors := _bounds_errors(viewport_size, background_rect)
	if not errors.is_empty():
		return errors
	_viewport_size = viewport_size
	_background_rect = background_rect
	initialized = true
	clear()
	return errors


## The stage resolves a visible actor's current world eye point once. Holding
## this cue does not follow future speakers or accumulate actor animation.
func focus(actor_id: String, world_point: Vector2, screen_anchor: Vector2, zoom: float, duration_seconds: float = 0.7) -> Array[String]:
	var errors := _request_errors(duration_seconds)
	if actor_id.is_empty() or actor_id != actor_id.to_lower() or not actor_id.is_valid_identifier():
		errors.append("Dialogue camera focus requires a lower_snake_case actor id.")
	if not world_point.is_finite() or not screen_anchor.is_finite():
		errors.append("Dialogue camera focus points must be finite.")
	elif not Rect2(Vector2.ZERO, _viewport_size).has_point(screen_anchor):
		errors.append("Dialogue camera screen anchor must lie inside the design viewport.")
	if not is_finite(zoom):
		errors.append("Dialogue camera zoom must be finite.")
	if not errors.is_empty():
		return errors
	zoom = clampf(zoom, 1.0, MAX_ZOOM)
	var desired := screen_anchor - world_point * zoom
	var minimum := _viewport_size - _background_rect.end * zoom
	var maximum := -_background_rect.position * zoom
	var offset := Vector2(clampf(desired.x, minimum.x, maximum.x), clampf(desired.y, minimum.y, maximum.y))
	_begin(actor_id, {"zoom": zoom, "offset_x": offset.x, "offset_y": offset.y}, duration_seconds)
	return errors


func wide(duration_seconds: float = 0.7) -> Array[String]:
	var errors := _request_errors(duration_seconds)
	if errors.is_empty():
		_begin("", IDENTITY, duration_seconds)
	return errors


func clear() -> void:
	focus_id = ""
	_elapsed = 0.0
	_duration_seconds = 0.0
	_from = IDENTITY.duplicate()
	_to = IDENTITY.duplicate()


func advance(delta: float) -> void:
	if not is_moving() or not is_finite(delta) or delta <= 0.0:
		return
	_elapsed = minf(_duration_seconds, _elapsed + delta)
	if _duration_seconds - _elapsed <= 0.000000001:
		_elapsed = _duration_seconds


func is_moving() -> bool:
	return initialized and _elapsed < _duration_seconds


func sample() -> Dictionary:
	var progress := 1.0 if _duration_seconds <= 0.0 else clampf(_elapsed / _duration_seconds, 0.0, 1.0)
	var weight := smoothstep(0.0, 1.0, progress)
	var pose := {}
	for field: String in IDENTITY:
		pose[field] = lerpf(float(_from[field]), float(_to[field]), weight)
	return pose


func get_state() -> Dictionary:
	return {"version": 1, "initialized": initialized, "focus_id": focus_id,
		"elapsed": _elapsed, "duration_seconds": _duration_seconds,
		"viewport_size": [_viewport_size.x, _viewport_size.y],
		"background_rect": [_background_rect.position.x, _background_rect.position.y, _background_rect.size.x, _background_rect.size.y],
		"from": _from.duplicate(), "to": _to.duplicate()}


func restore(saved: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for field: Variant in saved:
		if field not in STATE_FIELDS:
			errors.append("Unknown dialogue-camera state field: " + str(field))
	if not _finite_number(saved.get("version")) or float(saved["version"]) != 1.0:
		errors.append("Dialogue-camera state must have version 1.")
	if not (saved.get("initialized") is bool):
		errors.append("Dialogue-camera initialized state must be a boolean.")
	var target: Variant = saved.get("focus_id")
	if not (target is String) or (not target.is_empty() and (target != target.to_lower() or not target.is_valid_identifier())):
		errors.append("Dialogue-camera focus_id must be empty or a lower_snake_case actor id.")
	if not _finite_number(saved.get("duration_seconds")) or float(saved["duration_seconds"]) < 0.0 or float(saved["duration_seconds"]) > 2.0:
		errors.append("Dialogue-camera duration_seconds must be finite and between 0 and 2.")
	if not _finite_number(saved.get("elapsed")) or float(saved["elapsed"]) < 0.0 or (errors.is_empty() and float(saved["elapsed"]) > float(saved["duration_seconds"])):
		errors.append("Dialogue-camera elapsed time must lie inside its duration.")
	if not _number_array(saved.get("viewport_size"), 2) or not _number_array(saved.get("background_rect"), 4):
		errors.append("Dialogue-camera saved bounds must contain finite coordinate arrays.")
		return errors
	var view := Vector2(float(saved["viewport_size"][0]), float(saved["viewport_size"][1]))
	var background := Rect2(float(saved["background_rect"][0]), float(saved["background_rect"][1]), float(saved["background_rect"][2]), float(saved["background_rect"][3]))
	errors.append_array(_bounds_errors(view, background))
	for field: String in ["from", "to"]:
		var pose_errors := _pose_errors(saved.get(field))
		errors.append_array(pose_errors)
		if pose_errors.is_empty() and not _covers(view, background, saved[field]):
			errors.append("Dialogue-camera saved " + field + " pose exposes a background edge.")
	if not errors.is_empty():
		return errors
	if not bool(saved["initialized"]) and (saved["from"] != IDENTITY or saved["to"] != IDENTITY or target != "" or float(saved["duration_seconds"]) != 0.0):
		return ["An uninitialized dialogue camera must have an identity pose."]
	initialized = bool(saved["initialized"])
	focus_id = String(target)
	_viewport_size = view
	_background_rect = background
	_elapsed = float(saved["elapsed"])
	_duration_seconds = float(saved["duration_seconds"])
	_from = saved["from"].duplicate()
	_to = saved["to"].duplicate()
	return errors


func _begin(actor_id: String, target: Dictionary, duration_seconds: float) -> void:
	_from = sample()
	_to = target.duplicate()
	focus_id = actor_id
	_elapsed = 0.0
	_duration_seconds = duration_seconds


func _request_errors(duration_seconds: float) -> Array[String]:
	var errors: Array[String] = []
	if not initialized:
		errors.append("Dialogue camera is not initialized.")
	if not is_finite(duration_seconds) or duration_seconds < 0.0 or duration_seconds > 2.0:
		errors.append("Dialogue camera duration_seconds must be finite and between 0 and 2.")
	return errors


func _bounds_errors(viewport_size: Vector2, background_rect: Rect2) -> Array[String]:
	if not viewport_size.is_finite() or not background_rect.position.is_finite() or not background_rect.size.is_finite() or viewport_size.x <= 0.0 or viewport_size.y <= 0.0 or background_rect.size.x <= 0.0 or background_rect.size.y <= 0.0:
		return ["Dialogue camera bounds must be finite and have positive dimensions."]
	if not background_rect.grow(0.0001).encloses(Rect2(Vector2.ZERO, viewport_size)):
		return ["Dialogue camera background must cover the design viewport at the wide pose."]
	return []


func _pose_errors(value: Variant) -> Array[String]:
	if not (value is Dictionary):
		return ["Dialogue-camera poses must be objects."]
	var errors: Array[String] = []
	for field: Variant in value:
		if not IDENTITY.has(field):
			errors.append("Unknown dialogue-camera pose field: " + str(field))
	for field: String in IDENTITY:
		if not _finite_number(value.get(field)):
			errors.append("Dialogue-camera pose " + field + " must be finite.")
	if errors.is_empty() and (float(value["zoom"]) < 1.0 or float(value["zoom"]) > MAX_ZOOM):
		errors.append("Dialogue-camera pose zoom must lie between 1 and 4.")
	return errors


func _covers(viewport_size: Vector2, background_rect: Rect2, pose: Dictionary) -> bool:
	var zoom := float(pose["zoom"])
	var offset := Vector2(float(pose["offset_x"]), float(pose["offset_y"]))
	return Rect2(background_rect.position * zoom + offset, background_rect.size * zoom).grow(0.0001).encloses(Rect2(Vector2.ZERO, viewport_size))


func _finite_number(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value))


func _number_array(value: Variant, count: int) -> bool:
	if not (value is Array) or value.size() != count:
		return false
	for number: Variant in value:
		if not _finite_number(number):
			return false
	return true
