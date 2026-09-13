extends Control

## Optional front-facing presentation binding. The embedding game supplies
## resources, geometry and grants; admitted primitive cues select behavior.
## This adapter samples only presentation clocks and owns no narrative graph.
const WALKING = preload("res://addons/game_presentation/camera/walking_approach.gd")
const CAMERA = preload("res://addons/game_presentation/camera/dialogue_camera.gd")
const ESTABLISH = preload("res://addons/game_presentation/camera/establishing_shot.gd")
const DRIFT = preload("res://addons/game_presentation/camera/camera_drift.gd")
const EYE = preload("res://addons/game_presentation/transitions/eye_transition.gd")
const BACKGROUND_BLACKOUT = preload("res://addons/game_presentation/transitions/background_blackout.gd")
const LAYER_PAN = preload("res://addons/game_presentation/motion/layer_pan.gd")
const AMBIENT_PARTICLES = preload("res://addons/game_presentation/effects/particles/ambient_particles.gd")
const REFRACTION = preload("res://addons/game_presentation/effects/refraction_field.gd")
const CORRUPTION = preload("res://addons/game_presentation/effects/ominous_corruption.gd")
const SPRITE_BURST = preload("res://addons/game_presentation/effects/particles/sprite_burst.gd")
const SHAKE = preload("res://addons/game_presentation/camera/impact_shake.gd")
const HALO = preload("res://addons/game_presentation/effects/actor_halo.gd")
const CAST = preload("front_cast.gd")
const TRANSMISSION_DISPLAY = preload("portrait_feed.gd")
var content: Dictionary = {}
var design_size := Vector2.ZERO
var _view: Dictionary = {}
var _load_errors: Array[String] = []
var _backgrounds: Array[Texture2D] = []
var _textures: Dictionary = {}
var _portraits: Dictionary = {}
var _details: Dictionary = {}
var _contact_textures: Dictionary = {}
var _burst_textures: Dictionary = {}
var _background_index := 0
var _base_background := Rect2()
var _elapsed := 0.0
var _effect_time := 0.0
var _walking = WALKING.new()
var _camera = CAMERA.new()
var _establish = ESTABLISH.new()
var _drift = DRIFT.new()
var _eye = EYE.new()
var _atmosphere_layer := Control.new()
var _ambient_emitters: Array[Control] = []
var _atmosphere_id := ""
var _atmosphere_background := -1
var _shake = SHAKE.new()
var _heat_haze = REFRACTION.new()
var _world_corruption = CORRUPTION.new()
var _local_corruption = CORRUPTION.new()
var _barrier = REFRACTION.new()
var _sprite_burst = SPRITE_BURST.new()
var _background_blackout = BACKGROUND_BLACKOUT.new()
var _cast_pan = LAYER_PAN.new()
var _cast: Control
var _transmission_display: Control
var _portrait: TextureRect
var _halo: TextureRect
var _eye_layer: ColorRect
var _flare: ColorRect


func configure(settings: Dictionary, resources: Dictionary, feed: Control = null) -> Array[String]:
	var size_value: Variant = settings.get("design_size")
	if not size_value is Array or size_value.size() != 2:
		return ["Front stage requires a positive logical design_size."]
	if not (size_value[0] is float or size_value[0] is int) or not (size_value[1] is float or size_value[1] is int) or not is_finite(float(size_value[0])) or not is_finite(float(size_value[1])) or float(size_value[0]) <= 0.0 or float(size_value[1]) <= 0.0:
		return ["Front stage requires a positive logical design_size."]
	if not settings.get("actors") is Array or not settings.get("cast_geometry") is Dictionary or not settings.get("geometry") is Dictionary:
		return ["Front stage requires actor profiles, cast geometry and camera geometry."]
	for field: String in ["eye_anchor_y", "detail_zoom"]:
		var value: Variant = settings["geometry"].get(field)
		if not (value is float or value is int) or not is_finite(float(value)):
			return ["Front stage requires finite camera geometry."]
	for field: String in ["heat_rect", "barrier_rect"]:
		if not settings["geometry"].get(field) is Rect2 or not (settings["geometry"][field] as Rect2).has_area():
			return ["Front stage requires positive effect regions."]
	if not resources.get("backgrounds") is Array or resources["backgrounds"].is_empty() or not settings.get("backgrounds") is Array or settings["backgrounds"].size() != resources["backgrounds"].size():
		return ["Front stage requires matching background identities and textures."]
	for texture: Variant in resources["backgrounds"]:
		if not texture is Texture2D: return ["Front stage background resources must be textures."]
	for field: String in ["actors", "portraits", "details", "contacts", "burst", "manpu"]:
		if not resources.get(field, {}) is Dictionary: return ["Front stage texture bindings must be dictionaries."]
		for texture: Variant in resources.get(field, {}).values():
			if not texture is Texture2D: return ["Front stage actor/effect resources must be textures."]
	content = settings.duplicate(true)
	design_size = Vector2(float(size_value[0]), float(size_value[1]))
	_backgrounds.assign(resources.get("backgrounds", []))
	_textures = resources.get("actors", {}).duplicate()
	_portraits = resources.get("portraits", {}).duplicate()
	_details = resources.get("details", {}).duplicate()
	_contact_textures = resources.get("contacts", {}).duplicate()
	_burst_textures = resources.get("burst", {}).duplicate()
	content["manpu_textures"] = resources.get("manpu", {}).duplicate()
	_transmission_display = feed if feed != null else TRANSMISSION_DISPLAY.new()
	return []


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	# Background treatments sit below actors; local aura and the barrier sit
	# above them. Every screen-reading pass owns its own preceding copy.
	add_child(_heat_haze)
	add_child(_world_corruption)
	_atmosphere_layer.name = "FrontStageWorldAtmosphere"
	_atmosphere_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_atmosphere_layer)
	_load_errors.append_array(_heat_haze.configure(content.get("heat_haze", {})))
	_load_errors.append_array(_world_corruption.configure(content.get("world_corruption", {})))
	_load_errors.append_array(_local_corruption.configure(content.get("local_corruption", {})))
	_load_errors.append_array(_barrier.configure(content.get("barrier", {})))
	# Black out the environment only; actors, manpu and interface draw above it.
	_background_blackout.name = "FrontStageBackgroundBlackout"
	add_child(_background_blackout)
	# The root chooses rear placement; emitted world positions detach from the
	# actor while their rendering continues to follow the final camera.
	_sprite_burst.name = "FrontStageSpriteBurst"
	add_child(_sprite_burst)
	_cast = CAST.new()
	_cast.name = "FrontStageCast"
	add_child(_cast)
	_load_errors.append_array(_cast.initialize(_cast_profiles(), _textures, content.get("manpu_textures", {}), content.get("cast_geometry", {})))
	_transmission_display.name = "FrontStageTransmissionDisplay"
	add_child(_transmission_display)
	_halo = HALO.new()
	add_child(_halo)
	_load_errors.append_array(_halo.configure(content.get("halo", {})))
	_portrait = TextureRect.new()
	_portrait.name = "DirectedPortrait"
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_portrait)
	add_child(_local_corruption)
	add_child(_barrier)
	_flare = _shader_layer("res://addons/game_presentation/effects/shaders/location_lens_flare.gdshader")
	_eye_layer = _shader_layer("res://addons/game_presentation/effects/shaders/eye_transition.gdshader")
	_eye_layer.material.set_shader_parameter("viewport_size", design_size)
	_eye_layer.material.set_shader_parameter("edge_softness", float(content.get("eye_mask", {}).get("edge_softness", 28.0)))
	_load_errors.append_array(_walking.configure(content.get("approach", {})))
	_load_errors.append_array(_eye.configure(content.get("eye_transition", {})))


func advance(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0: return
	_elapsed += delta
	_effect_time += delta
	for emitter: Control in _ambient_emitters: emitter.advance(delta)
	for controller in [_cast_pan, _shake, _walking, _camera, _establish, _drift, _eye, _cast, _sprite_burst, _background_blackout]:
		controller.advance(delta)


func reset() -> void:
	_clear_atmosphere()
	_background_blackout.clear()
	_cast_pan.clear()
	_elapsed = 0.0
	_effect_time = 0.0
	_cast.set_cast([])
	for actor_id: String in _textures: _cast.set_projection(actor_id, false)
	_bind_background(0)
	_view.clear()


func present() -> void:
	if not _load_errors.is_empty() or _view.is_empty(): return
	var portrait_mode := str(_view.get("portrait_mode", "none"))
	_cast.visible = bool(_view.get("cast_visible", true))
	_cast.present(_cast_transform())
	for emitter: Control in _ambient_emitters: emitter.present(_world_transform())
	_sprite_burst.present(_cast_transform())
	_present_transmission_display()
	_portrait.visible = portrait_mode != "none"
	_halo.hide()
	if _portrait.visible:
		var rect := _portrait_rect(portrait_mode == "detail")
		_portrait.position = rect.position
		_portrait.size = rect.size
		if bool(_view.get("halo", false)):
			_halo.set_source(_portrait.texture)
			_halo.set_rect(rect)
			_halo.set_strength(1.0)
	_eye_layer.visible = bool(_view.get("eye_mask", false))
	_eye_layer.material.set_shader_parameter("openness", float(_eye.sample()["openness"]))
	_flare.visible = bool(_view.get("flare", false))
	if _flare.visible:
		var shot: Dictionary = _establish.sample()
		var uv: Array = shot["flare_source_uv"]
		var point := _world_transform() * (_base_background.position + _base_background.size * Vector2(float(uv[0]), float(uv[1])))
		_flare.material.set_shader_parameter("light_position", point / design_size)
		_flare.material.set_shader_parameter("strength", float(shot["flare_strength"]))
	_present_ominous_effects()
	queue_redraw()


func execute(type: String, parameters: Dictionary) -> Array[String]:
	var errors := validate_operation(type, parameters)
	if not errors.is_empty(): return errors
	match type:
		"front_delay": pass
		"front_view":
			_view = parameters.duplicate(true)
			var area: Variant = _view.get("corruption", {}).get("area")
			if area is Array and area.size() == 4: _view["corruption"]["area"] = Rect2(area[0], area[1], area[2], area[3])
			_elapsed = 0.0
		"front_reset":
			for controller: String in parameters["controllers"]:
				match controller:
					"eye": _eye.clear()
					"drift": _drift.clear()
					"establish": _establish.clear()
					"walking": _walking.clear()
					"shake": _shake.clear()
					"burst": _sprite_burst.clear()
					"pan": _cast_pan.clear()
					"camera": _camera.clear()
					"marks": errors.append_array(_cast.set_marks([]))
					"reactions": _cast.cancel_manpu()
		"front_background": _bind_background(int(parameters["index"]))
		"front_cast": errors.append_array(_cast.set_cast(parameters["actors"]))
		"front_focus": errors.append_array(_cast.focus(str(parameters["actor"]), str(parameters["preset"]), bool(parameters["replay"])))
		"front_mark": errors.append_array(_cast.mark(str(parameters["actor"]), str(parameters["sprite"]), str(parameters["preset"])))
		"front_reaction":
			var response: Dictionary = _cast.emit_manpu(str(parameters["actor"]), str(parameters["sprite"]), str(parameters["preset"]))
			errors.append_array(response["errors"])
		"front_projection": errors.append_array(_cast.set_projection(str(parameters["actor"]), bool(parameters["enabled"])))
		"front_camera":
			if parameters["mode"] == "wide": errors.append_array(_camera.wide(float(parameters["duration_seconds"])))
			else:
				var actor_id := str(parameters["actor"])
				var profile := _profile(actor_id)
				if profile.has("transmission_display"):
					var settings: Dictionary = profile["transmission_display"]
					var frame: Rect2 = settings["frame_rect"]
					errors.append_array(_camera.focus(actor_id, _cast_pan.sample_transform() * frame.get_center(), frame.get_center(), float(settings["camera_zoom"]), float(parameters["duration_seconds"])))
				else:
					var rect: Rect2 = _cast.get_actor_rect(actor_id)
					var eye: Array = profile["eye_uv"]
					var point := _cast_pan.sample_transform() * (rect.position + rect.size * Vector2(float(eye[0]), float(eye[1])))
					errors.append_array(_camera.focus(actor_id, point, Vector2(design_size.x * 0.5, float(content["geometry"]["eye_anchor_y"])), float(parameters["zoom"]), float(parameters["duration_seconds"])))
		"front_walking": errors.append_array(_walking.start())
		"front_eye": errors.append_array(_eye.start(str(parameters["mode"]), parameters.get("settings", {})))
		"front_drift": errors.append_array(_drift.start(content.get("drift", {})))
		"front_establish": errors.append_array(_establish.start(str(content["backgrounds"][_background_index]["id"]), parameters))
		"front_handoff": errors.append_array(_cast.handoff(str(parameters["outgoing"]), str(parameters["survivor"]), str(parameters["incoming"]), parameters["settings"]))
		"front_exit": errors.append_array(_cast.dismiss(str(parameters["actor"]), str(parameters["preset"])))
		"front_shake": errors.append_array(_shake.start(parameters))
		"front_blackout": errors.append_array(_background_blackout.fade_to(float(parameters["strength"]), float(parameters["duration_seconds"])))
		"front_pan": _start_cast_pan(parameters)
		"front_approach":
			var settings: Dictionary = content.get("quick_approach", {}).duplicate(true)
			settings.merge(parameters.get("settings", {}), true)
			errors.append_array(_cast.approach_actor(str(parameters["actor"]), str(parameters["target"]), settings))
		"front_burst": _emit_burst(parameters)
		_: errors.append("Unsupported front presentation operation: " + type)
	_load_errors.append_array(errors)
	return errors


func validate_operation(type: String, parameters: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: String in ["origin_uv", "offset", "flare_source_uv"]:
		if parameters.has(key):
			var coordinates: Variant = parameters[key]
			if not coordinates is Array or coordinates.size() != 2:
				errors.append("Front-stage coordinates require two numbers: " + key)
			else:
				for coordinate: Variant in coordinates:
					if not (coordinate is float or coordinate is int) or not is_finite(float(coordinate)): errors.append("Front-stage coordinates must be finite.")
	var area: Variant = parameters.get("corruption", {}).get("area")
	if area != null:
		if not area is Array or area.size() != 4:
			errors.append("Front-stage corruption area requires four finite numbers.")
		else:
			for coordinate: Variant in area:
				if not (coordinate is float or coordinate is int) or not is_finite(float(coordinate)): errors.append("Front-stage corruption coordinates must be finite.")
	for key: String in ["actor", "speaker", "outgoing", "survivor", "incoming", "target"]:
		var actor_id := str(parameters.get(key, ""))
		if not actor_id.is_empty() and not _textures.has(actor_id): errors.append("Unknown bound front-stage actor: " + actor_id)
	if type == "front_background" and (int(parameters.get("index", -1)) < 0 or int(parameters.get("index", -1)) >= _backgrounds.size()):
		errors.append("Front-stage background index must name a bound resource.")
	if type == "front_cast":
		var ids: Array = parameters.get("actors", [])
		if ids.size() > int(content.get("cast_geometry", {}).get("max_actors", 0)): errors.append("Front-stage cast exceeds its bound layout capacity.")
		var seen := {}
		for actor_id: String in ids:
			if not _textures.has(actor_id) or seen.has(actor_id): errors.append("Front-stage cast requires unique bound actors.")
			seen[actor_id] = true
	if type == "front_view":
		var speaker := str(parameters.get("speaker", ""))
		var portrait := str(parameters.get("portrait_mode", "none"))
		if portrait != "none" and speaker.is_empty(): errors.append("A portrait view requires a bound speaker.")
		if portrait == "contact" and not _contact_textures.has(speaker): errors.append("Contact view requires a bound contact portrait.")
		if portrait == "detail" and not _details.has(speaker): errors.append("Detail view requires a bound detail portrait.")
	if type == "front_burst":
		for sprite: String in parameters.get("sprites", []):
			if not _burst_textures.has(sprite): errors.append("Unknown bound burst sprite: " + sprite)
	if type in ["front_mark", "front_reaction"] and not content.get("manpu_textures", {}).has(str(parameters.get("sprite", ""))):
		errors.append("Mark/reaction requires a bound sprite.")
	return errors


func cinematic_complete(controller: String) -> bool:
	match controller:
		"walking": return not _walking.is_active()
		"eye": return not _eye.is_active()
		"establish": return not _establish.is_active()
		"cast": return not _cast.is_busy()
	return true


func _cast_profiles() -> Array:
	return content.get("actors", [])




func _profile(actor_id: String) -> Dictionary:
	for profile: Dictionary in _cast_profiles():
		if profile["id"] == actor_id: return profile
	return {}




func _bind_background(index: int) -> void:
	_background_index = index
	var dimensions := _backgrounds[index].get_size()
	var factor := maxf(design_size.x / dimensions.x, design_size.y / dimensions.y)
	_base_background = Rect2((design_size - dimensions * factor) * 0.5, dimensions * factor)
	_load_errors.append_array(_walking.initialize(design_size, _base_background))
	_load_errors.append_array(_camera.initialize(design_size, _base_background))
	_bind_atmosphere(index)




func _clear_atmosphere() -> void:
	for emitter: Control in _ambient_emitters:
		emitter.clear()
		_atmosphere_layer.remove_child(emitter)
		emitter.queue_free()
	_ambient_emitters.clear()
	_atmosphere_id = ""
	_atmosphere_background = -1




func _bind_atmosphere(background: int) -> void:
	var background_id := str(content["backgrounds"][background]["id"])
	var profile_id := str(content.get("ambient_particles", {}).get(background_id, ""))
	if background == _atmosphere_background and profile_id == _atmosphere_id: return
	_clear_atmosphere()
	_atmosphere_id = profile_id
	_atmosphere_background = background
	for layer: Dictionary in content.get("atmosphere_profiles", {}).get(profile_id, []):
		var emitter = AMBIENT_PARTICLES.new()
		emitter.name = str(layer["id"])
		_atmosphere_layer.add_child(emitter)
		_load_errors.append_array(emitter.start(layer["region"], AMBIENT_PARTICLES.fallback_textures(str(layer["sprite_kind"])), layer["options"]))
		_ambient_emitters.append(emitter)




func get_atmosphere_state() -> Dictionary:
	var layers := {}
	for emitter: Control in _ambient_emitters: layers[str(emitter.name)] = emitter.get_state()
	return {"profile": _atmosphere_id, "background": _atmosphere_background, "layers": layers}




func _start_cast_pan(cue: Dictionary) -> void:
	var settings: Dictionary = content.get("cast_pan", {}).duplicate(true)
	settings.merge(cue.get("settings", {}), true)
	var offset := Vector2.ZERO
	if cue.has("actor") and not cue.has("offset"):
		var actor_id := str(cue["actor"])
		if not _cast.visible_ids().has(actor_id):
			_load_errors.append("Cast Pan requires a visible target actor.")
			return
		var anchor: Variant = cue.get("anchor_x", design_size.x * 0.5)
		if not (anchor is float or anchor is int) or not is_finite(float(anchor)) or float(anchor) < 0.0 or float(anchor) > design_size.x:
			_load_errors.append("Cast Pan anchor_x must be finite and inside the design viewport.")
			return
		var center: Vector2 = _cast.get_actor_rect(actor_id).get_center()
		var profile := _profile(actor_id)
		if profile.has("transmission_display"):
			center = profile["transmission_display"].get("frame_rect", Rect2()).get_center()
		# Resolve once from local blocking, never from an already panned sprite.
		var anchor_world: Vector2 = _world_transform().affine_inverse() * Vector2(float(anchor), 0.0)
		offset.x = anchor_world.x - center.x
	elif cue.has("offset") and not cue.has("actor"):
		var coordinates: Variant = cue["offset"]
		if not (coordinates is Array) or coordinates.size() != 2 or not (coordinates[0] is float or coordinates[0] is int) or not (coordinates[1] is float or coordinates[1] is int):
			_load_errors.append("Cast Pan offset must be an array of two finite numbers.")
			return
		offset = Vector2(float(coordinates[0]), float(coordinates[1]))
	else:
		_load_errors.append("Cast Pan requires exactly one actor target or offset.")
		return
	_load_errors.append_array(_cast_pan.pan_to(offset, settings))




func _emit_burst(cue: Dictionary) -> void:
	var actor_id := str(cue.get("actor", ""))
	if not _cast.visible_ids().has(actor_id):
		_load_errors.append("Front stage sprite burst requires a visible actor.")
		return
	var textures: Array[Texture2D] = []
	for sprite_id: String in cue.get("sprites", []):
		textures.append(_burst_textures.get(sprite_id))
	var rect: Rect2 = _cast.get_actor_rect(actor_id)
	var origin: Vector2 = rect.position + rect.size * Vector2(float(cue.get("origin_uv", [0.5, 0.25])[0]), float(cue.get("origin_uv", [0.5, 0.25])[1]))
	var options: Dictionary = content.get("sprite_burst", {}).get("options", {}).duplicate(true)
	options.merge(cue.get("options", {}), true)
	var result: Dictionary = _sprite_burst.emit_burst(origin, textures, options)
	_load_errors.append_array(result["errors"])




func _world_transform() -> Transform2D:
	var pose: Dictionary = _walking.sample() if _view.get("camera_mode") == "walking" else _camera.sample()
	var zoom := float(pose["zoom"])
	var offset := Vector2(float(pose["offset_x"]), float(pose["offset_y"]))
	if _view.get("camera_mode") == "establish":
		var shot: Dictionary = _establish.sample()
		zoom = float(shot["zoom"])
		offset = design_size * 0.5 * (1.0 - zoom) + Vector2(float(shot["pan_x"]), 0)
		offset = offset.clamp(design_size - _base_background.end * zoom, -_base_background.position * zoom)
	if _view.get("camera_mode") == "detail":
		zoom = float(content["geometry"]["detail_zoom"])
		offset = design_size * 0.5 * (1.0 - zoom) + _drift_offset()
	var base := Transform2D(Vector2(zoom, 0), Vector2(0, zoom), offset)
	return _shake.compose(base, _base_background, design_size)




func _drift_offset() -> Vector2:
	var pose: Dictionary = _drift.sample()
	var base := Rect2(_base_background.position * float(content["geometry"]["detail_zoom"]) + design_size * (1.0 - float(content["geometry"]["detail_zoom"])) * 0.5, _base_background.size * float(content["geometry"]["detail_zoom"]))
	return DRIFT.constrain_offset(base, design_size, Vector2(float(pose["offset_x"]), float(pose["offset_y"])))




func _cast_transform() -> Transform2D:
	return _world_transform() * _cast_pan.sample_transform()




func presented_background_rect() -> Rect2:
	return _world_transform() * _base_background




func _portrait_rect(detail: bool) -> Rect2:
	var id := str(_view.get("speaker", ""))
	var profile := _profile(id)
	if _view.get("portrait_mode") == "contact":
		_portrait.texture = _contact_textures[id]
		return _world_transform() * _contact_world_rect()
	if detail and _details.has(id):
		_portrait.texture = _details[id]
		var height := float(profile.get("detail_height", design_size.y))
		var width := height * _portrait.texture.get_width() / _portrait.texture.get_height()
		return Rect2(Vector2(design_size.x * 0.5 - width * 0.5, float(profile.get("detail_y", 0))) + _drift_offset(), Vector2(width, height))
	_portrait.texture = _portraits.get(id, _textures[id])
	var height := float(profile.get("eye_close_height", design_size.y))
	var width := height * _portrait.texture.get_width() / _portrait.texture.get_height()
	var uv: Array = profile.get("eye_close_uv", profile["eye_uv"])
	return Rect2(design_size.x * 0.5 - width * float(uv[0]), float(content["geometry"]["eye_anchor_y"]) - height * float(uv[1]), width, height)




func _contact_world_rect() -> Rect2:
	var actor_id := str(_view.get("speaker", ""))
	var texture: Texture2D = _contact_textures.get(actor_id)
	if texture == null: return Rect2()
	var profile := _profile(actor_id)
	var height := float(profile.get("contact_height", design_size.y))
	var width := height * texture.get_width() / texture.get_height()
	return Rect2(design_size.x * 0.5 - width * 0.5, float(profile.get("contact_y", 0.0)), width, height)




func _present_transmission_display() -> void:
	_transmission_display.clear()
	if not _cast.visible: return
	# A call belongs to the staged participant, including protagonist replies.
	# Cast semantics stay intact; this host swaps only the visible presentation.
	var staged: Array[String] = _cast.visible_ids()
	if staged.size() != 1: return
	var actor_id := staged[0]
	var profile := _profile(actor_id)
	if not profile.has("transmission_display") or not bool(_cast._projection.get(actor_id, false)): return
	var settings: Dictionary = profile["transmission_display"].duplicate(true)
	var eye_uv: Array = profile.get("eye_uv", [0.5, 0.25])
	settings["eye_uv"] = Vector2(float(eye_uv[0]), float(eye_uv[1]))
	_transmission_display.present(actor_id, _textures[actor_id], _cast_transform(), _effect_time, settings)
	_cast.hide()




func _present_ominous_effects() -> void:
	var beat := _view
	var envelope := 1.0
	if beat.get("field_envelope") == "fade_out":
		envelope = 1.0 - smoothstep(0.0, float(beat.get("duration_seconds", 1.6)), _elapsed)
	elif beat.get("field_envelope") == "fade_in":
		envelope = smoothstep(0.0, 0.25, _elapsed)
	for field: Control in [_heat_haze, _world_corruption, _local_corruption, _barrier]:
		field.set_time(_effect_time)
	_heat_haze.set_rect(content["geometry"]["heat_rect"])
	_heat_haze.set_strength(float(beat.get("heat", 0.0)) * envelope)
	_world_corruption.set_rect(Rect2(Vector2.ZERO, design_size))
	_world_corruption.set_pattern_transform(_world_transform())
	_world_corruption.set_strength(float(beat.get("scene_corruption", 0.0)) * envelope)
	_barrier.set_rect(content["geometry"]["barrier_rect"])
	_barrier.set_strength(float(beat.get("barrier", 0.0)) * envelope)
	var target: Dictionary = beat.get("corruption", {})
	_local_corruption.set_pattern_transform(_world_transform())
	var actor_id := str(target.get("actor", ""))
	var visible_target := false
	if not actor_id.is_empty() and _cast.visible_ids().has(actor_id):
		_local_corruption.set_pattern_transform(_cast_transform())
		_local_corruption.set_source(_textures[actor_id])
		_local_corruption.set_rect(_cast.get_presented_actor_rect(actor_id))
		visible_target = true
	elif target.has("area"):
		_local_corruption.set_source(null)
		_local_corruption.set_rect(_world_transform() * (target["area"] as Rect2))
		visible_target = true
	_local_corruption.set_strength(float(target.get("strength", 0.0)) * envelope if visible_target else 0.0)




func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, design_size), content.get("clear_color", Color.BLACK))
	if not _load_errors.is_empty() or _backgrounds.is_empty(): return
	draw_texture_rect(_backgrounds[_background_index], presented_background_rect(), false)
	draw_rect(Rect2(Vector2.ZERO, design_size), content.get("overlay_color", Color.TRANSPARENT))




func _shader_layer(path: String) -> ColorRect:
	var layer := ColorRect.new()
	layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var material := ShaderMaterial.new()
	material.shader = load(path)
	layer.material = material
	add_child(layer)
	layer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return layer
