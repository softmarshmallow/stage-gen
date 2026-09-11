extends Control

## Afterlight's concrete standing-cast renderer. The story owns cues and time;
## this adapter composes existing actor controllers with the game's geometry.
## All rectangles are in the 1280 x 900 world. present() accepts the host's
## positive axis-aligned camera scale/translation; it never advances a clock.
## set_cast() cancels active motion. Resume is authored cue replay plus advance,
## not serialization of renderer nodes. The host can hide this entire layer.
const FOCUS = preload("res://addons/game_presentation/actors/actor_focus.gd")
const MANPU = preload("res://addons/game_presentation/actors/manpu_animation.gd")
const EXIT = preload("res://addons/game_presentation/actors/character_exit.gd")
const CAST = preload("res://addons/game_presentation/actors/cast_transition.gd")
const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const MOTION_CURVE = preload("res://addons/game_presentation/motion/motion_curve.gd")
const MOVE_DEFAULTS := {"duration_seconds": 0.32, "curve": "ease_in_out", "frequency": 1.5, "damping_ratio": 0.8}
const FOCUS_CATALOG := "res://addons/game_presentation/actors/presets/focus.json"
const MANPU_CATALOG := "res://addons/game_presentation/actors/presets/manpu.json"
const EXIT_CATALOG := "res://addons/game_presentation/actors/presets/exit.json"
const CAST_SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
const CONTENT_ADAPTER = preload("res://content_adapter.gd")
const HOLOGRAM = preload("res://addons/game_presentation/effects/shaders/character_hologram.gdshader")
const HEIGHT := 960.0
const TOP := 140.0
const MARK_HEIGHT_RATIO := 0.115

var _profiles: Dictionary = {}
var _sprites: Dictionary = {}
var _materials: Dictionary = {}
var _projection: Dictionary = {}
var _positions: Dictionary = {}
var _staged: Array[String] = []
var _marks: Array = []
var _mark_textures: Dictionary = {}
var _mark_nodes: Dictionary = {}
var _one_shot_nodes: Dictionary = {}
var _focus = FOCUS.new()
var _manpu = MANPU.new()
var _exit = EXIT.new()
var _cast = CAST.new()
var _handoff_ids: Array[String] = []
var _slots: Dictionary = {}
var _elapsed := 0.0
var _camera := Transform2D.IDENTITY
var _movement: Dictionary = {}


## Actor and optional manpu textures are supplied resources. The default art
## adapter preserves direct callers; initialization validates before replacing.
func initialize(profiles: Array, textures: Dictionary, manpu_textures: Dictionary = {}) -> Array[String]:
	var errors: Array[String] = []
	var ids: Array[String] = []
	for value: Variant in profiles:
		if not (value is Dictionary) or not ANIMATION.valid_id(value.get("id")):
			errors.append("Afterlight cast requires profiles with valid ids.")
			continue
		var id := String(value["id"])
		if ids.has(id) or not (textures.get(id) is Texture2D):
			errors.append("Afterlight cast requires one prepared texture per unique actor: " + id)
		ids.append(id)
	if ids.is_empty():
		errors.append("Afterlight cast requires at least one actor.")
	if not errors.is_empty():
		return errors
	var next_focus = FOCUS.new()
	var next_exit = EXIT.new()
	var next_manpu = MANPU.new()
	errors.append_array(next_focus.initialize(ids, FOCUS_CATALOG))
	errors.append_array(next_exit.initialize(ids, EXIT_CATALOG))
	errors.append_array(next_manpu.initialize(MANPU_CATALOG))
	errors.append_array(next_focus.configure("bounce"))
	errors.append_array(next_exit.configure("silhouette_fade"))
	errors.append_array(next_manpu.configure("shake"))
	var specification: Variant = JSON.parse_string(FileAccess.get_file_as_string(CAST_SPEC))
	if not (specification is Dictionary) or not (specification.get("slots") is Dictionary):
		errors.append("Afterlight cast requires the prepared Cast Transition slots.")
	var next_marks := manpu_textures.duplicate()
	if next_marks.is_empty():
		var loaded := CONTENT_ADAPTER.load_manpu()
		errors.append_array(loaded.errors)
		next_marks = loaded.textures
	for mark_id: Variant in next_marks:
		if not mark_id is String or not next_marks[mark_id] is Texture2D:
			errors.append("Afterlight manpu bindings require string ids and Texture2D resources.")
	if not errors.is_empty():
		return errors
	for child: Node in get_children():
		remove_child(child)
		child.queue_free()
	_profiles.clear()
	_sprites.clear()
	_materials.clear()
	_projection.clear()
	_mark_nodes.clear()
	_one_shot_nodes.clear()
	_slots = specification["slots"].duplicate()
	_mark_textures = next_marks
	_focus = next_focus
	_exit = next_exit
	_manpu = next_manpu
	_elapsed = 0.0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	for profile: Dictionary in profiles:
		var id := String(profile["id"])
		_profiles[id] = profile.duplicate(true)
		var sprite := _texture_node(id + "Sprite", textures[id])
		_sprites[id] = sprite
		var material := ShaderMaterial.new()
		material.shader = HOLOGRAM
		material.set_shader_parameter("strength", 0.9)
		_materials[id] = material
		_projection[id] = false
	set_cast([])
	return errors


## Immediate scene placement. Two-person composition shares the handoff spec's
## slots; a four-person final tableau is supported without a transition graph.
func set_cast(ids: Array) -> Array[String]:
	var errors := _validate_ids(ids)
	if ids.size() > 4:
		errors.append("Afterlight's standing composition supports up to four actors.")
	if not errors.is_empty():
		return errors
	_staged.assign(ids)
	_handoff_ids.clear()
	_movement.clear()
	_cast = CAST.new()
	_positions.clear()
	_exit.clear()
	_focus.clear()
	_manpu.clear()
	set_marks([])
	for index in ids.size():
		var center := 640.0
		if ids.size() == 2:
			center = float(_slots["left" if index == 0 else "right"])
		elif ids.size() > 2:
			center = lerpf(250.0, 1030.0, float(index) / float(ids.size() - 1))
		_positions[ids[index]] = center
	present(_camera)
	return []


func focus(actor_id: String, preset_id: String = "bounce", replay: bool = false) -> Array[String]:
	if not actor_id.is_empty() and not _profiles.has(actor_id):
		return ["Unknown Afterlight focus actor: " + actor_id]
	var errors: Array[String] = _focus.configure(preset_id)
	if not errors.is_empty(): return errors
	errors.append_array(_focus.set_focus(actor_id))
	if errors.is_empty() and replay: _focus.replay()
	return errors


func set_marks(cues: Array) -> Array[String]:
	for cue: Variant in cues:
		if not (cue is Dictionary) or not _profiles.has(cue.get("actor")) or not _mark_textures.has(cue.get("id")):
			return ["Afterlight manpu cues require a registered actor and raster mark."]
		# Resolve all requested art before sync can replace any active clocks.
		if cue.get("frames", []) is Array:
			for frame_id: Variant in cue.get("frames", []):
				if not _mark_textures.has(frame_id):
					return ["Afterlight manpu frames require prepared raster marks."]
	var errors: Array[String] = _manpu.sync(cues)
	if not errors.is_empty():
		return errors
	_marks = cues.duplicate(true)
	for cue: Dictionary in _marks:
		var key := String(cue["actor"]) + ":" + String(cue["id"])
		if not _mark_nodes.has(key):
			_mark_nodes[key] = _texture_node(key.replace(":", "_"), _mark_textures[cue["id"]])
	return []


func mark(actor_id: String, mark_id: String, preset_id: String = "", frames: Array = []) -> Array[String]:
	var cue := {"actor": actor_id, "id": mark_id}
	if not preset_id.is_empty(): cue["preset"] = preset_id
	if not frames.is_empty(): cue["frames"] = frames.duplicate()
	return set_marks([cue])


## Events have independent lifetimes; persistent dialogue cues never recreate them.
func emit_manpu(actor_id: String, mark_id: String, preset_id: String = "sigh_puff") -> Dictionary:
	if not _profiles.has(actor_id) or not _mark_textures.has(mark_id) or not visible_ids().has(actor_id):
		return {"errors": ["Afterlight one-shot manpu requires a visible actor and prepared raster mark."], "instance_id": -1}
	var result: Dictionary = _manpu.emit_one_shot(actor_id, mark_id, preset_id)
	if result["errors"].is_empty(): present(_camera)
	return result


func cancel_manpu(actor_id: String = "") -> void:
	_manpu.cancel_one_shots(actor_id)
	present(_camera)


## The existing bounded handoff exits the left actor, moves the right actor,
## then introduces the new right actor. Reject an incompatible pair unchanged.
func handoff(outgoing: String, survivor: String, incoming: String, settings: Dictionary = {}) -> Array[String]:
	var ids: Array[String] = [outgoing, survivor, incoming]
	var errors := _validate_ids(ids)
	if is_busy() or visible_ids() != [outgoing, survivor]:
		errors.append("Afterlight handoff requires an idle outgoing/survivor pair in left/right order.")
	if not errors.is_empty():
		return errors
	if not is_equal_approx(float(_positions[outgoing]), float(_slots["left"])) or not is_equal_approx(float(_positions[survivor]), float(_slots["right"])):
		return ["Afterlight handoff requires the authored two-person slot positions."]
	var next_cast = CAST.new()
	errors.append_array(next_cast.initialize(ids, EXIT_CATALOG, CAST_SPEC))
	errors.append_array(next_cast.configure(settings))
	if not errors.is_empty():
		return errors
	errors.append_array(next_cast.start())
	if errors.is_empty():
		_cast = next_cast
		_handoff_ids.assign(ids)
		_staged.assign(ids)
		_exit.show_actor(incoming)
	return errors


func dismiss(actor_id: String, preset_id: String = "silhouette_fade") -> Array[String]:
	if not _staged.has(actor_id) or not _handoff_ids.is_empty():
		return ["Afterlight dismissal requires a staged actor outside a cast handoff."]
	var errors: Array[String] = _exit.configure(preset_id)
	if not errors.is_empty(): return errors
	errors.append_array(_exit.exit_actor(actor_id))
	if errors.is_empty() and _movement.get("actor") == actor_id:
		_movement.clear()
	return errors


## Authored blocking in world-center units, using the existing motion curve.
## One mover at a time; retargeting that actor preserves its current position.
func move_actor(actor_id: String, center_x: float, settings: Dictionary = {}) -> Array[String]:
	var errors: Array[String] = []
	if not visible_ids().has(actor_id) or _exit.is_exiting(actor_id) or not _handoff_ids.is_empty():
		errors.append("Afterlight movement requires a visible actor outside an exit or cast handoff.")
	if bool(_movement.get("active", false)) and _movement.get("actor") != actor_id:
		errors.append("Afterlight blocking supports one active moving actor.")
	if not is_finite(center_x) or center_x < 0.0 or center_x > 1280.0:
		errors.append("Afterlight movement center_x must be finite and between 0 and 1280.")
	for key: Variant in settings:
		if not MOVE_DEFAULTS.has(key):
			errors.append("Unknown Afterlight movement setting: " + str(key))
	var configured := MOVE_DEFAULTS.duplicate()
	configured.merge(settings, true)
	if not ANIMATION.finite_number(configured["duration_seconds"]) or float(configured["duration_seconds"]) < 0.0 or float(configured["duration_seconds"]) > 5.0:
		errors.append("Afterlight movement duration_seconds must be finite and between 0 and 5.")
	errors.append_array(MOTION_CURVE.validate(configured))
	if not errors.is_empty():
		return errors
	var from_x := float(_positions[actor_id])
	var duration := float(configured["duration_seconds"])
	var active := duration > 0.0 and from_x != center_x
	_movement = {"actor": actor_id, "from_x": from_x, "target_x": center_x,
		"elapsed": 0.0 if active else duration, "duration_seconds": duration,
		"settings": configured, "active": active}
	if not active:
		_positions[actor_id] = center_x
	return []


## Capture one destination toward a stationary actor; this is not tracking.
func approach_actor(actor_id: String, target_id: String, settings: Dictionary = {}) -> Array[String]:
	if actor_id == target_id or not visible_ids().has(actor_id) or not visible_ids().has(target_id) or _exit.is_exiting(target_id):
		return ["Afterlight approach requires distinct visible actors and a stationary target outside an exit."]
	var gap: Variant = settings.get("stop_distance", 280.0)
	var from_x := float(_appearance(actor_id)["center_x"])
	var target_x := float(_appearance(target_id)["center_x"])
	if not ANIMATION.finite_number(gap) or float(gap) <= 0.0 or float(gap) >= absf(target_x - from_x):
		return ["Afterlight approach stop_distance must be finite, positive, and smaller than the current separation."]
	var motion_settings := settings.duplicate()
	motion_settings.erase("stop_distance")
	return move_actor(actor_id, target_x - signf(target_x - from_x) * float(gap), motion_settings)


func movement_state() -> Dictionary:
	var state := _movement.duplicate(true)
	if not state.is_empty():
		state["center_x"] = float(_positions[state["actor"]])
	return state


func set_projection(actor_id: String, enabled: bool) -> Array[String]:
	if not _profiles.has(actor_id):
		return ["Unknown Afterlight projection actor: " + actor_id]
	_projection[actor_id] = enabled
	return []


func advance(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0:
		return
	_elapsed += delta
	_focus.advance(delta)
	_manpu.advance(delta)
	_exit.advance(delta)
	_cast.advance(delta)
	if bool(_movement.get("active", false)):
		var duration := float(_movement["duration_seconds"])
		_movement["elapsed"] = minf(duration, float(_movement["elapsed"]) + delta)
		var progress := float(_movement["elapsed"]) / duration
		var weight: float = MOTION_CURVE.sample(progress, _movement["settings"])
		_positions[_movement["actor"]] = clampf(lerpf(float(_movement["from_x"]), float(_movement["target_x"]), weight), 0.0, 1280.0)
		_movement["active"] = progress < 1.0
		if not _movement["active"]:
			_positions[_movement["actor"]] = float(_movement["target_x"])
	if not _handoff_ids.is_empty() and not _cast.is_busy():
		var settled: Array[String] = []
		for actor_id: String in _handoff_ids:
			var appearance: Dictionary = _cast.sample(actor_id)
			if appearance["visible"]:
				settled.append(actor_id)
				_positions[actor_id] = float(appearance["center_x"])
		_staged = settled
		_handoff_ids.clear()
	for event: Dictionary in _manpu.one_shots():
		if not bool(_appearance(str(event["actor"]))["visible"]):
			_manpu.cancel_one_shots(str(event["actor"]))


func visible_ids() -> Array[String]:
	var result: Array[String] = []
	for id: String in _staged:
		if bool(_appearance(id)["visible"]):
			result.append(id)
	return result


func is_busy() -> bool:
	if _cast.is_busy() or bool(_movement.get("active", false)):
		return true
	for id: String in _staged:
		if _exit.is_exiting(id):
			return true
	return false


## Base world rectangle excludes the transient focus bounce, so a directed
## close-up does not chase speaker animation. Mark placement uses posed geometry.
func get_actor_rect(actor_id: String) -> Rect2:
	if not _sprites.has(actor_id):
		return Rect2()
	var texture: Texture2D = _sprites[actor_id].texture
	var dimensions := Vector2(HEIGHT * texture.get_width() / texture.get_height(), HEIGHT)
	var center := float(_appearance(actor_id)["center_x"])
	return Rect2(Vector2(center - dimensions.x * 0.5, TOP), dimensions)


## Full texture geometry after focus and camera, for attached alpha-mask VFX.
func get_presented_actor_rect(actor_id: String) -> Rect2:
	return _camera * _posed_rect(actor_id) if _sprites.has(actor_id) else Rect2()


func present(camera: Transform2D) -> void:
	_camera = camera
	for id: String in _sprites:
		var sprite: TextureRect = _sprites[id]
		var appearance := _appearance(id)
		sprite.visible = bool(appearance["visible"])
		if not sprite.visible:
			continue
		var rect: Rect2 = camera * _posed_rect(id)
		sprite.position = rect.position
		sprite.size = rect.size
		var focus_sample: Dictionary = _focus.sample(id)
		var brightness := float(focus_sample["brightness"]) * float(appearance["brightness"])
		var opacity := float(focus_sample["opacity"]) * float(appearance["opacity"])
		# Color goes black while source-alpha coverage stays intact, then only
		# that silhouette fades. A single PNG avoids doubled translucent edges.
		sprite.modulate = Color(brightness, brightness, brightness, opacity)
		var material: ShaderMaterial = _materials[id]
		material.set_shader_parameter("effect_time", _elapsed)
		sprite.material = material if bool(_projection[id]) else null
	for node: TextureRect in _mark_nodes.values():
		node.hide()
	for cue: Dictionary in _marks:
		var actor_id := String(cue["actor"])
		var mark_id := String(cue["id"])
		var node: TextureRect = _mark_nodes[actor_id + ":" + mark_id]
		_present_mark(node, actor_id, mark_id, _manpu.sample(actor_id, mark_id), camera)
	var active := {}
	for event: Dictionary in _manpu.one_shots():
		var handle := int(event["instance_id"])
		active[handle] = true
		if not _one_shot_nodes.has(handle):
			_one_shot_nodes[handle] = _texture_node("ManpuEvent%d" % handle, _mark_textures[event["id"]])
		_present_mark(_one_shot_nodes[handle], str(event["actor"]), str(event["id"]), event["sample"], camera)
	for handle: int in _one_shot_nodes.keys():
		if not active.has(handle):
			var node: TextureRect = _one_shot_nodes[handle]
			remove_child(node)
			node.queue_free()
			_one_shot_nodes.erase(handle)


func _present_mark(node: TextureRect, actor_id: String, mark_id: String, sample: Dictionary, camera: Transform2D) -> void:
	var appearance := _appearance(actor_id)
	node.visible = bool(appearance["visible"])
	if not node.visible: return
	var owner := _posed_rect(actor_id)
	var eye: Array = _profiles[actor_id].get("eye_uv", [0.5, 0.14])
	var anchor := Vector2(clampf(float(eye[0]) + 0.23, 0.1, 0.85), maxf(0.035, float(eye[1]) - 0.05))
	if mark_id in ["sigh", "sigh_puff"]:
		anchor.y = float(eye[1]) + 0.055
	var center := owner.position + owner.size * anchor
	var height := owner.size.y * MARK_HEIGHT_RATIO
	var dimensions := Vector2.ONE * height * float(sample["scale"])
	var origin := center - dimensions * 0.5
	origin += height * Vector2(float(sample["offset_x_ratio"]), float(sample["offset_y_ratio"]))
	var rect: Rect2 = camera * Rect2(origin, dimensions)
	node.texture = _mark_textures[str(sample.get("sprite_id", mark_id))]
	node.position = rect.position
	node.size = rect.size
	node.pivot_offset = rect.size * 0.5
	node.rotation_degrees = float(sample.get("rotation_degrees", 0.0))
	var brightness := float(sample["brightness"])
	node.modulate = Color(brightness, brightness, brightness, float(sample["opacity"]) * float(appearance["opacity"]))


func _appearance(actor_id: String) -> Dictionary:
	if _handoff_ids.has(actor_id):
		return _cast.sample(actor_id)
	var result: Dictionary = _exit.sample(actor_id)
	result["visible"] = _staged.has(actor_id) and _exit.is_visible(actor_id)
	result["center_x"] = float(_positions.get(actor_id, 640.0))
	return result


func _posed_rect(actor_id: String) -> Rect2:
	var base := get_actor_rect(actor_id)
	var sample: Dictionary = _focus.sample(actor_id)
	var dimensions := base.size * float(sample["scale"])
	var origin := base.position + Vector2((base.size.x - dimensions.x) * 0.5, base.size.y - dimensions.y)
	var departure := _appearance(actor_id)
	# All local motion uses the original target height, before camera scaling.
	# Exit and speaker cues compose once; neither feeds back into the base pose.
	origin.x += base.size.y * (float(sample.get("offset_x_ratio", 0.0)) + float(departure.get("offset_x_ratio", 0.0)))
	origin.y += base.size.y * (float(sample["offset_y_ratio"]) + float(departure.get("offset_y_ratio", 0.0)))
	return Rect2(origin, dimensions)


func _texture_node(node_name: String, texture: Texture2D) -> TextureRect:
	var node := TextureRect.new()
	node.name = node_name
	node.texture = texture
	node.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	node.stretch_mode = TextureRect.STRETCH_SCALE
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	node.hide()
	add_child(node)
	return node


func _validate_ids(ids: Array) -> Array[String]:
	var seen := {}
	var errors: Array[String] = []
	for id: Variant in ids:
		if not (id is String) or not _profiles.has(id) or seen.has(id):
			errors.append("Unknown or duplicate Afterlight cast actor: " + str(id))
		seen[id] = true
	return errors
