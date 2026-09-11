extends RefCounted

## Persistent (actor, id) marks own introduction or loop clocks. Explicit one-shot
## events own separate instance clocks and expire without changing that cue set.
## Hosts own actor/art validation, attachment, rendering, and the clock source.
const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const CHANNEL_DEFAULTS := ANIMATION.CHANNEL_DEFAULTS

var initialized := false
var preset_id := ""
var _presets: Dictionary = {}
var _preset_order: Array[String] = []
var _states: Dictionary = {}
var _one_shot_states: Dictionary = {}
var _next_instance_id := 1


func initialize(catalog_path: String) -> Array[String]:
	var errors: Array[String] = []
	var file := FileAccess.open(catalog_path, FileAccess.READ)
	if file == null:
		return ["Cannot open the Manpu animation preset catalog."]
	var parser := JSON.new()
	if parser.parse(file.get_as_text()) != OK:
		return ["Cannot parse the Manpu animation preset catalog: " + parser.get_error_message()]
	var checked := _validate_catalog(parser.data)
	errors.append_array(checked["errors"])
	if not errors.is_empty():
		return errors
	_presets = checked["presets"]
	_preset_order.assign(checked["order"])
	preset_id = _preset_order[0]
	initialized = true
	clear()
	return errors


## Defaults affect unpinned cues only. Smooth introductions retarget continuously;
## loops restart at phase zero, and stepped samples deliberately switch directly.
## Re-selecting a default is a no-op; replay starts the selected cue afresh.
func configure(selected_preset_id: String) -> Array[String]:
	if not initialized:
		return ["Manpu animation is not initialized."]
	if not _presets.has(selected_preset_id):
		return ["Unknown Manpu animation preset: " + selected_preset_id]
	if preset_id == selected_preset_id:
		return []
	var next_cues: Array = []
	for state: Dictionary in _states.values():
		var cue: Dictionary = state["cue"].duplicate(true)
		if not cue.has("preset"):
			cue["preset"] = selected_preset_id
		next_cues.append(cue)
	var errors := _validate_cues(next_cues)
	if not errors.is_empty():
		return errors
	var current := {}
	for key: String in _states:
		var state: Dictionary = _states[key]
		if not state["cue"].has("preset"):
			current[key] = sample(String(state["actor"]), String(state["id"]))
	preset_id = selected_preset_id
	for key: String in current:
		var previous: Dictionary = _states[key]
		_states[key] = _new_state(previous["cue"], true, current[key])
	return []


## Validation precedes mutation. Existing pairs keep their own clocks even if
## their order or speaker changes. Changed preset/frame bindings restart only
## that pair. Removed pairs disappear; new loops always begin at phase zero.
## animate=false settles newly added once-played introductions.
func sync(cues: Array, animate: bool = true) -> Array[String]:
	if not initialized:
		return ["Manpu animation is not initialized."]
	var errors := _validate_cues(cues)
	if not errors.is_empty():
		return errors
	var next_states := {}
	for cue: Dictionary in cues:
		var actor := String(cue["actor"])
		var id := String(cue["id"])
		var key := _key(actor, id)
		next_states[key] = _states[key] if _states.has(key) and _states[key]["cue"] == cue else _new_state(cue, animate)
	_states = next_states
	return errors


func advance(delta: float) -> void:
	if not initialized or not is_finite(delta) or delta <= 0.0:
		return
	for key: String in _states:
		var state: Dictionary = _states[key]
		var duration := float(state["duration_seconds"])
		if state["playback"] == "loop":
			var phase := fposmod(float(state["elapsed"]) + fposmod(delta, duration), duration)
			state["elapsed"] = 0.0 if duration - phase < duration * 0.000000001 else phase
		else:
			state["elapsed"] = minf(duration, float(state["elapsed"]) + delta)
	var expired: Array[int] = []
	for instance_id: int in _one_shot_states:
		var state: Dictionary = _one_shot_states[instance_id]
		var duration := float(state["duration_seconds"])
		state["elapsed"] = minf(duration, float(state["elapsed"]) + delta)
		# Snap only a relative floating-point remainder at the authored boundary.
		if duration - float(state["elapsed"]) <= duration * 0.000000001:
			expired.append(instance_id)
	for instance_id: int in expired:
		_one_shot_states.erase(instance_id)


func sample(actor: String, id: String) -> Dictionary:
	var key := _key(actor, id)
	if not initialized or not _states.has(key):
		var identity := CHANNEL_DEFAULTS.duplicate()
		identity["sprite_id"] = id
		return identity
	var state: Dictionary = _states[key]
	var result := ANIMATION.sample(_presets[state["preset_id"]]["tracks"], float(state["elapsed"]),
		float(state["duration_seconds"]), state["from"], state["interpolation"])
	var frames: Array = state["cue"].get("frames", [])
	var frame := 0 if frames.is_empty() else mini(int(floor(float(state["elapsed"]) / float(state["duration_seconds"]) * frames.size() + 0.000000001)), frames.size() - 1)
	result["sprite_id"] = id if frames.is_empty() else frames[frame]
	return result


## Optional host-used sampler at the render boundary. It receives copied timing,
## frame IDs and the built-in sample; malformed output falls back with errors.
func sample_with(actor: String, id: String, sampler: Callable) -> Dictionary:
	var builtin := sample(actor, id)
	var key := _key(actor, id)
	if not sampler.is_valid() or not _states.has(key):
		return {"sample": builtin, "errors": ["Custom Manpu sampling requires an active pair and a valid callable."]}
	var state: Dictionary = _states[key]
	var duration := float(state["duration_seconds"])
	var context := {"actor": actor, "id": id, "elapsed": state["elapsed"], "duration_seconds": duration,
		"progress": float(state["elapsed"]) / duration if duration > 0.0 else 1.0,
		"playback": state["playback"], "frames": state["cue"].get("frames", []).duplicate(), "sample": builtin.duplicate()}
	var supplied: Variant = sampler.call(context)
	var errors: Array[String] = []
	if not (supplied is Dictionary):
		return {"sample": builtin, "errors": ["Custom Manpu sampler must return a partial sample dictionary."]}
	for field: Variant in supplied:
		if field == "sprite_id":
			if supplied[field] != id and supplied[field] not in state["cue"].get("frames", []):
				errors.append("Custom Manpu sprite_id must be the cue id or one of its supplied frames.")
		elif not CHANNEL_DEFAULTS.has(field) or not ANIMATION.finite_number(supplied[field]):
			errors.append("Custom Manpu sample contains an unknown or nonfinite channel: " + str(field))
		elif field in ["opacity", "brightness"] and (float(supplied[field]) < 0.0 or float(supplied[field]) > 1.0):
			errors.append("Custom Manpu opacity and brightness must stay between 0 and 1.")
		elif field == "scale" and float(supplied[field]) < ANIMATION.MIN_SCALE:
			errors.append("Custom Manpu scale must be at least 0.001.")
	if not errors.is_empty():
		return {"sample": builtin, "errors": errors}
	var result := builtin.duplicate()
	result.merge(supplied, true)
	return {"sample": result, "errors": errors}


## Only this event creates a transient instance. Repeated actor/id pairs are
## allowed; each owns a fresh handle and a snapshot of the selected tracks.
## Validation is atomic, including the handle counter. A failed event uses -1.
func emit_one_shot(actor: String, id: String, selected_preset: String) -> Dictionary:
	var errors: Array[String] = []
	if not initialized:
		errors.append("Manpu animation is not initialized.")
		return {"errors": errors, "instance_id": -1}
	if not ANIMATION.valid_id(actor) or not ANIMATION.valid_id(id):
		errors.append("One-shot Manpu actor and id must be nonempty lower_snake_case identifiers.")
	if not ANIMATION.valid_id(selected_preset) or not _presets.has(selected_preset):
		errors.append("Unknown one-shot Manpu preset: " + selected_preset)
	if not errors.is_empty():
		return {"errors": errors, "instance_id": -1}
	var selected: Dictionary = _presets[selected_preset]
	var duration := float(selected["duration_seconds"])
	if duration <= 0.0:
		errors.append("One-shot Manpu presets require a positive duration.")
	if selected["playback"] != "once":
		errors.append("One-shot Manpu presets cannot loop.")
	if float(ANIMATION.evaluate(selected["tracks"], 1.0)["opacity"]) != 0.0:
		errors.append("One-shot Manpu presets must end at zero opacity.")
	if not errors.is_empty():
		return {"errors": errors, "instance_id": -1}
	var instance_id := _next_instance_id
	_next_instance_id += 1
	_one_shot_states[instance_id] = {
		"actor": actor, "id": id, "preset_id": selected_preset,
		"duration_seconds": duration, "elapsed": 0.0,
		"tracks": selected["tracks"].duplicate(true),
		"interpolation": selected["interpolation"],
	}
	return {"errors": errors, "instance_id": instance_id}


## Independent renderer samples, in emission order. Sampling never expires,
## emits, or restarts an event. No art, position, camera, or Node is retained.
func one_shots() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for instance_id: int in _one_shot_states:
		var state: Dictionary = _one_shot_states[instance_id]
		result.append({"instance_id": instance_id, "actor": state["actor"], "id": state["id"],
			"sample": ANIMATION.sample(state["tracks"], float(state["elapsed"]), float(state["duration_seconds"]), {}, state["interpolation"])})
	return result


## Cancellation never changes persistent marks. Empty actor cancels all events;
## an unknown actor is a no-op. Instance handles are never reused by this object.
func cancel_one_shots(actor: String = "") -> void:
	if actor.is_empty():
		_one_shot_states.clear()
		return
	var cancelled: Array[int] = []
	for instance_id: int in _one_shot_states:
		if _one_shot_states[instance_id]["actor"] == actor:
			cancelled.append(instance_id)
	for instance_id: int in cancelled:
		_one_shot_states.erase(instance_id)


func clear() -> void:
	_states.clear()
	_one_shot_states.clear()


## Replay either all active marks or one exact pair. Partial/unknown pairs fail
## atomically and never create a cue that the conversation did not request.
func replay(actor: String = "", id: String = "") -> Array[String]:
	if not initialized:
		return ["Manpu animation is not initialized."]
	if actor.is_empty() and id.is_empty():
		for key: String in _states:
			var previous: Dictionary = _states[key]
			_states[key] = _new_state(previous["cue"], true)
		return []
	if actor.is_empty() or id.is_empty() or not _states.has(_key(actor, id)):
		return ["Replay must name one active Manpu actor/id pair, or omit both."]
	_states[_key(actor, id)] = _new_state(_states[_key(actor, id)]["cue"], true)
	return []


func get_presets() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for id: String in _preset_order:
		result.append({"id": id, "label": _presets[id]["label"], "duration_seconds": _presets[id]["duration_seconds"]})
	return result


func get_state() -> Dictionary:
	return {"initialized": initialized, "preset_id": preset_id, "states": _states.duplicate(true),
		"one_shots": _one_shot_states.duplicate(true), "next_instance_id": _next_instance_id}


func _new_state(cue: Dictionary, animate: bool, from_sample: Dictionary = {}) -> Dictionary:
	var selected_id := String(cue.get("preset", preset_id))
	var selected: Dictionary = _presets[selected_id]
	var duration := float(selected["duration_seconds"])
	var looping: bool = selected["playback"] == "loop"
	return {"actor": cue["actor"], "id": cue["id"], "cue": cue.duplicate(true), "preset_id": selected_id,
		"playback": selected["playback"], "interpolation": selected["interpolation"], "duration_seconds": duration,
		"elapsed": 0.0 if animate or looping else duration,
		"from": ANIMATION.evaluate(selected["tracks"], 0.0) if from_sample.is_empty() or looping else from_sample.duplicate()}


func _key(actor: String, id: String) -> String:
	# Valid identifiers contain no colon, so the pair encoding is unambiguous.
	return actor + ":" + id


func _validate_cues(cues: Array) -> Array[String]:
	var errors: Array[String] = []
	var seen := {}
	for cue: Variant in cues:
		if not (cue is Dictionary):
			errors.append("Each Manpu animation cue must name an actor and id.")
			continue
		for field: Variant in cue:
			if field not in ["actor", "id", "preset", "frames"]:
				errors.append("Unknown Manpu animation cue field: " + str(field))
		if not ANIMATION.valid_id(cue.get("actor")) or not ANIMATION.valid_id(cue.get("id")):
			errors.append("Manpu animation cue actor and id must be nonempty lower_snake_case identifiers.")
			continue
		var key := _key(String(cue["actor"]), String(cue["id"]))
		if seen.has(key):
			errors.append("Duplicate Manpu animation cue: " + key)
		seen[key] = true
		var selected_id: Variant = cue.get("preset", preset_id)
		if not ANIMATION.valid_id(selected_id) or not _presets.has(selected_id):
			errors.append("Unknown per-cue Manpu preset: " + str(selected_id))
			continue
		if cue.has("frames"):
			var frames: Variant = cue["frames"]
			if not (frames is Array) or frames.size() < 2 or frames.size() > 64:
				errors.append("Manpu frames must contain between 2 and 64 sprite IDs.")
			else:
				for frame: Variant in frames:
					if not ANIMATION.valid_id(frame):
						errors.append("Manpu frame IDs must be lower_snake_case identifiers.")
			if _presets[selected_id]["playback"] != "loop":
				errors.append("Manpu frame sequences require a looping preset.")
	return errors


func _validate_catalog(value: Variant) -> Dictionary:
	var groups: Array[String] = ["tracks"]
	var stripped: Variant = value.duplicate(true) if value is Dictionary else value
	if stripped is Dictionary and stripped.get("presets") is Array:
		for preset: Variant in stripped["presets"]:
			if preset is Dictionary:
				preset.erase("playback")
				preset.erase("interpolation")
	var checked := ANIMATION.validate_catalog(stripped, groups, "Manpu animation", true)
	if not checked["errors"].is_empty():
		return checked
	for preset: Dictionary in value["presets"]:
		var playback: Variant = preset.get("playback", "once")
		var interpolation: Variant = preset.get("interpolation", "smooth")
		if playback not in ["once", "loop"]:
			checked["errors"].append("Manpu playback must be once or loop.")
		if interpolation not in ["smooth", "step"]:
			checked["errors"].append("Manpu interpolation must be smooth or step.")
		if playback == "loop" and float(preset["duration_seconds"]) <= 0.0:
			checked["errors"].append("Looping Manpu presets require a positive duration.")
		checked["presets"][preset["id"]]["playback"] = playback
		checked["presets"][preset["id"]]["interpolation"] = interpolation
	return checked
