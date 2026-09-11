extends RefCounted

## Each actor owns a visible -> exiting -> hidden lifecycle. This controller
## samples scalar tracks only; the stage owns rendering and actor composition.
## The renderer composes color/coverage and height-relative X/Y motion samples.
## Scale remains neutral. Walking presets rely on host-proven offscreen travel
## before their final coverage drop; this controller has no camera geometry.
const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const CHANNEL_DEFAULTS := ANIMATION.CHANNEL_DEFAULTS

var initialized := false
var preset_id := ""
var _actor_ids: Array[String] = []
var _presets: Dictionary = {}
var _preset_order: Array[String] = []
var _states: Dictionary = {}


## A failed initialize leaves any existing catalog and actor state intact.
func initialize(actor_ids: Array[String], catalog_path: String) -> Array[String]:
	var errors: Array[String] = []
	var seen := {}
	if actor_ids.is_empty():
		errors.append("Character Exit requires at least one actor id.")
	for actor_id: String in actor_ids:
		if not ANIMATION.valid_id(actor_id) or seen.has(actor_id):
			errors.append("Character Exit received an invalid or duplicate actor id: " + actor_id)
		seen[actor_id] = true
	var file := FileAccess.open(catalog_path, FileAccess.READ)
	if file == null:
		errors.append("Cannot open the Character Exit preset catalog.")
		return errors
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK:
		errors.append("Cannot parse the Character Exit preset catalog: " + parser.get_error_message())
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


## Selection affects future exits. Existing exits retain their preset snapshot;
## neither active nor hidden actors are restarted or restored by configuration.
func configure(selected_preset_id: String) -> Array[String]:
	if not initialized:
		return ["Character Exit is not initialized."]
	if not _presets.has(selected_preset_id):
		return ["Unknown Character Exit preset: " + selected_preset_id]
	preset_id = selected_preset_id
	return []


func exit_actor(actor_id: String) -> Array[String]:
	var errors := _actor_errors(actor_id)
	if not errors.is_empty():
		return errors
	if _states[actor_id]["status"] != "visible":
		return []
	var selected: Dictionary = _presets[preset_id]
	var duration := float(selected["duration_seconds"])
	_states[actor_id] = {
		"status": "hidden" if duration <= 0.0 else "exiting",
		"preset_id": preset_id,
		"elapsed": 0.0,
		"duration_seconds": duration,
		"tracks": selected["tracks"].duplicate(true),
	}
	return []


## Showing an actor is immediate: cancel any exit and restore the identity.
## Entrance animation is intentionally outside this exit lifecycle.
func show_actor(actor_id: String) -> Array[String]:
	var errors := _actor_errors(actor_id)
	if not errors.is_empty():
		return errors
	_states[actor_id] = _visible_state()
	return []


## Restore every registered actor while preserving the selected exit preset.
func clear() -> void:
	_states.clear()
	for actor_id: String in _actor_ids:
		_states[actor_id] = _visible_state()


func advance(delta: float) -> void:
	if not initialized or not is_finite(delta) or delta <= 0.0:
		return
	for actor_id: String in _states:
		var state: Dictionary = _states[actor_id]
		if state["status"] != "exiting":
			continue
		var duration := float(state["duration_seconds"])
		state["elapsed"] = minf(duration, float(state["elapsed"]) + delta)
		if float(state["elapsed"]) >= duration:
			state["status"] = "hidden"


## Unknown actors are identity safe. Hidden actors hold the authored ending
## (opacity zero), including its brightness, rather than resetting their tracks.
func sample(actor_id: String) -> Dictionary:
	if not initialized or not _states.has(actor_id):
		return CHANNEL_DEFAULTS.duplicate()
	var state: Dictionary = _states[actor_id]
	if state["status"] == "visible":
		return CHANNEL_DEFAULTS.duplicate()
	return ANIMATION.sample(state["tracks"], float(state["elapsed"]),
		float(state["duration_seconds"]), CHANNEL_DEFAULTS)


## Exiting actors must remain drawable until their last sample is reached.
func is_visible(actor_id: String) -> bool:
	return initialized and _states.has(actor_id) and _states[actor_id]["status"] != "hidden"


func is_exiting(actor_id: String) -> bool:
	return initialized and _states.has(actor_id) and _states[actor_id]["status"] == "exiting"


func get_presets() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for id: String in _preset_order:
		result.append({"id": id, "label": _presets[id]["label"], "duration_seconds": _presets[id]["duration_seconds"]})
	return result


func get_state() -> Dictionary:
	return {"initialized": initialized, "preset_id": preset_id, "states": _states.duplicate(true)}


func _visible_state() -> Dictionary:
	return {"status": "visible", "preset_id": "", "elapsed": 0.0,
		"duration_seconds": 0.0, "tracks": {}}


func _actor_errors(actor_id: String) -> Array[String]:
	if not initialized:
		return ["Character Exit is not initialized."]
	if not _states.has(actor_id):
		return ["Unknown Character Exit actor: " + actor_id]
	return []


func _validate_catalog(value: Variant) -> Dictionary:
	var groups: Array[String] = ["tracks"]
	var checked := ANIMATION.validate_catalog(value, groups, "Character Exit")
	if not checked["errors"].is_empty():
		return checked
	for id: String in checked["order"]:
		var tracks: Dictionary = checked["presets"][id]["tracks"]
		for channel: String in tracks:
			if channel not in ["brightness", "opacity", "offset_x_ratio", "offset_y_ratio"]:
				checked["errors"].append("Character Exit preset " + id + " does not support " + channel + "; only brightness, opacity, and X/Y offset tracks are supported.")
		var ending := ANIMATION.evaluate(tracks, 1.0)
		if float(ending["opacity"]) != 0.0:
			checked["errors"].append("Character Exit preset " + id + " must end at opacity zero.")
	return checked
