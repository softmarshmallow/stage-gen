extends RefCounted

## Actor Focus samples presentation cues; the caller composes them with its
## actor rendering. Keyframes use normalized time and smoothstep interpolation.
## Retargeting preserves the current sample and removes its residual smoothly:
## track(t) + (from - track(0)) * (1 - smoothstep(t)).

const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const CHANNEL_DEFAULTS := ANIMATION.CHANNEL_DEFAULTS
const MIN_SCALE := ANIMATION.MIN_SCALE

var initialized := false
var focus_id := ""
var preset_id := ""
var elapsed := 0.0
var duration_seconds := 0.0
var _actor_ids: Array[String] = []
var _presets: Dictionary = {}
var _preset_order: Array[String] = []
var _from: Dictionary = {}


## Validation is atomic: a failed initialize leaves an existing instance intact.
func initialize(actor_ids: Array[String], catalog_path: String) -> Array[String]:
	var errors: Array[String] = []
	var actors_seen := {}
	if actor_ids.is_empty():
		errors.append("Actor Focus requires at least one actor id.")
	for actor_id: String in actor_ids:
		if not _valid_id(actor_id) or actors_seen.has(actor_id):
			errors.append("Actor Focus received an invalid or duplicate actor id: " + actor_id)
		actors_seen[actor_id] = true
	var file := FileAccess.open(catalog_path, FileAccess.READ)
	if file == null:
		errors.append("Cannot open the Actor Focus preset catalog.")
		return errors
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK:
		errors.append("Cannot parse the Actor Focus preset catalog: " + parser.get_error_message())
		return errors
	var checked := _validate_catalog(parser.data)
	errors.append_array(checked["errors"])
	if not errors.is_empty():
		return errors
	_actor_ids.assign(actor_ids)
	_presets = checked["presets"]
	_preset_order.assign(checked["order"])
	preset_id = _preset_order[0]
	initialized = true
	clear()
	return errors


## Changing a preset retargets the existing focus from its current samples.
## Re-selecting it is a no-op; replay() is the explicit retrigger operation.
func configure(selected_preset_id: String) -> Array[String]:
	if not initialized:
		return ["Actor Focus is not initialized."]
	if not _presets.has(selected_preset_id):
		return ["Unknown Actor Focus preset: " + selected_preset_id]
	if selected_preset_id == preset_id:
		return []
	var current := _current_samples()
	preset_id = selected_preset_id
	_begin_transition(focus_id, true, current)
	return []


func set_focus(actor_id: String, animate: bool = true) -> Array[String]:
	if not initialized:
		return ["Actor Focus is not initialized."]
	if not actor_id.is_empty() and not _actor_ids.has(actor_id):
		return ["Unknown Actor Focus actor: " + actor_id]
	if actor_id == focus_id:
		return []
	_begin_transition(actor_id, animate, _current_samples())
	return []


func replay() -> void:
	if initialized:
		_begin_transition(focus_id, true, _current_samples())


## Clear is immediate and neutral. The configured preset remains selected.
func clear() -> void:
	focus_id = ""
	elapsed = 0.0
	duration_seconds = 0.0
	_from.clear()
	for actor_id: String in _actor_ids:
		_from[actor_id] = CHANNEL_DEFAULTS.duplicate()


func advance(delta: float) -> void:
	if not initialized or not is_finite(delta) or delta <= 0.0:
		return
	elapsed = minf(duration_seconds, elapsed + delta)


## Every result is independent. Focus uses five channels; the shared rotation
## channel remains neutral because this controller does not accept rotation tracks.
## The empty focus represents a narrator: every actor returns to neutral.
func sample(actor_id: String) -> Dictionary:
	if not initialized or not _actor_ids.has(actor_id):
		return CHANNEL_DEFAULTS.duplicate()
	return ANIMATION.sample(_tracks_for(actor_id), elapsed, duration_seconds,
		_from.get(actor_id, CHANNEL_DEFAULTS))


func get_presets() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for id: String in _preset_order:
		result.append({"id": id, "label": _presets[id]["label"], "duration_seconds": _presets[id]["duration_seconds"]})
	return result


func _current_samples() -> Dictionary:
	var current := {}
	for actor_id: String in _actor_ids:
		current[actor_id] = sample(actor_id)
	return current


func _begin_transition(actor_id: String, animate: bool, from: Dictionary) -> void:
	_from = from
	focus_id = actor_id
	duration_seconds = float(_presets[preset_id]["duration_seconds"])
	elapsed = 0.0 if animate else duration_seconds


func _tracks_for(actor_id: String) -> Dictionary:
	if focus_id.is_empty():
		return {}
	return _presets[preset_id]["focused" if actor_id == focus_id else "listeners"]


func _valid_id(value: Variant) -> bool:
	return ANIMATION.valid_id(value)


func _validate_catalog(value: Variant) -> Dictionary:
	var groups: Array[String] = ["focused", "listeners"]
	return ANIMATION.validate_catalog(value, groups, "Actor Focus")
