extends Control

## Afterlight's episode director and complete game-owned interface.
## Cue data is authored Godot content, not a shared scenario language. Effects
## retain their own APIs; this host owns their ordering, clocks, and composition.
signal navigate(route_id: String)
signal language_changed(language: String)
const WALKING = preload("res://addons/game_presentation/camera/walking_approach.gd")
const CAMERA = preload("res://addons/game_presentation/camera/dialogue_camera.gd")
const ESTABLISH = preload("res://addons/game_presentation/camera/establishing_shot.gd")
const DRIFT = preload("res://addons/game_presentation/camera/camera_drift.gd")
const EYE = preload("res://addons/game_presentation/transitions/eye_transition.gd")
const BACKGROUND_BLACKOUT = preload("res://addons/game_presentation/transitions/background_blackout.gd")
const LAYER_PAN = preload("res://addons/game_presentation/motion/layer_pan.gd")
const REVEAL = preload("res://addons/game_presentation/text/intertitle.gd")
const VOICE_EFFECTS = preload("res://addons/game_presentation/audio/voice_effects.gd")
const AMBIENT_PARTICLES = preload("res://addons/game_presentation/effects/particles/ambient_particles.gd")
const ATMOSPHERE = preload("res://games/bishoujo_afterlight/atmosphere_profile.gd")
const TEXT_AUDIO = preload("res://addons/game_presentation/audio/text_reveal_audio.gd")
const POINT_CONTACT = preload("res://addons/game_presentation/interaction/point_contact.gd")
const REFRACTION = preload("res://addons/game_presentation/effects/refraction_field.gd")
const CORRUPTION = preload("res://addons/game_presentation/effects/ominous_corruption.gd")
const SPRITE_BURST = preload("res://addons/game_presentation/effects/particles/sprite_burst.gd")
const SHAKE = preload("res://addons/game_presentation/camera/impact_shake.gd")
const HALO = preload("res://addons/game_presentation/effects/actor_halo.gd")
const CAST = preload("res://games/bishoujo_afterlight/cast_stage.gd")
const CONTENT_ADAPTER = preload("res://games/bishoujo_afterlight/content_adapter.gd")
const TRANSMISSION_DISPLAY = preload("res://games/bishoujo_afterlight/transmission_display.gd")
const DESIGN_SIZE := Vector2(1280, 900)
const INK := Color("f4eee6")
const ACCENT := Color("e4bbac")
const CINEMATICS := ["walk", "eye", "establish", "handoff", "exit", "rift"]
var content: Dictionary = {}
var beats: Array = []
var saved_state: Dictionary = {}
var text_set: RefCounted
var voice_policy: RefCounted
var content_factory: Callable
var _voice_state: Dictionary = {}
var _voice_waiting := false
var _load_errors: Array[String] = []
var _backgrounds: Array[Texture2D] = []
var _textures: Dictionary = {}
var _portraits: Dictionary = {}
var _details: Dictionary = {}
var _contact_textures: Dictionary = {}
var _burst_textures: Dictionary = {}
var _burst_emitted := false
var _blackout_started := false
var _approach_started := false
var _cast_pan_started := false
var _background_index := 0
var _base_background := Rect2()
var _beat_index := 0
var _elapsed := 0.0
var _effect_time := 0.0
var _history: Array[float] = []
var _choices: Dictionary = {}
var _manpu_history: Array[float] = []
var _manpu_event_time := -1.0
var _contact_history: Array[float] = []
var _contact_time := -1.0
var _replaying_checkpoint := false
var _paused := false
var _autoplay_enabled := false
var _autoplay_elapsed := 0.0
var _walking = WALKING.new()
var _camera = CAMERA.new()
var _establish = ESTABLISH.new()
var _drift = DRIFT.new()
var _eye = EYE.new()
var _reveal = REVEAL.new()
var _text_audio = TEXT_AUDIO.new()
var _voice_effects = VOICE_EFFECTS.new()
var _atmosphere_layer := Control.new()
var _ambient_emitters: Array[Control] = []
var _atmosphere_id := ""
var _atmosphere_background := -1
var _contact = POINT_CONTACT.new()
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
var _ui: Control
var _header: Control
var _dialogue: Control
var _speaker: Label
var _line: Label
var _location: Label
var _ready_dot: Control
var _contact_ring: Panel
var _contact_dot: Panel
var _choice_buttons: Array[Button] = []
var _language_button: Button
var _autoplay_button: Button
var _black: Control
var _monologue: Label
var _monologue_dot: Control
var _pause_menu: Control
var _ui_bindings: Array[Dictionary] = []


func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	mouse_filter = Control.MOUSE_FILTER_STOP
	_text_audio.name = "TextRevealAudio"
	# Children exit in reverse order: stop voice before its bus is removed.
	add_child(_voice_effects)
	add_child(_text_audio)
	_load_errors.append_array(_voice_effects.configure(content.get("transmission_voice", {})))
	for item: Dictionary in content.get("backgrounds", []):
		_backgrounds.append(_load_texture(item["path"]))
	for profile: Dictionary in _cast_profiles():
		var actor_id := str(profile["id"])
		_textures[actor_id] = _load_texture(profile["path"])
		if profile.has("eye_close_path"): _portraits[actor_id] = _load_texture(profile["eye_close_path"])
		if profile.has("detail_path"): _details[actor_id] = _load_texture(profile["detail_path"])
		if profile.has("contact_path"): _contact_textures[actor_id] = _load_texture(profile["contact_path"])
	for sprite_id: String in content.get("sprite_burst", {}).get("sprites", {}):
		_burst_textures[sprite_id] = _load_texture(content["sprite_burst"]["sprites"][sprite_id])
	# Background treatments sit below actors; local aura and the barrier sit
	# above them. Every screen-reading pass owns its own preceding copy.
	add_child(_heat_haze)
	add_child(_world_corruption)
	_atmosphere_layer.name = "AfterlightWorldAtmosphere"
	_atmosphere_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_atmosphere_layer)
	_load_errors.append_array(_heat_haze.configure(content.get("heat_haze", {})))
	_load_errors.append_array(_world_corruption.configure(content.get("world_corruption", {})))
	_load_errors.append_array(_local_corruption.configure(content.get("local_corruption", {})))
	_load_errors.append_array(_barrier.configure(content.get("barrier", {})))
	# Black out the environment only; actors, manpu and interface draw above it.
	_background_blackout.name = "AfterlightBackgroundBlackout"
	add_child(_background_blackout)
	# The root chooses rear placement; emitted world positions detach from the
	# actor while their rendering continues to follow the final camera.
	_sprite_burst.name = "AfterlightSpriteBurst"
	add_child(_sprite_burst)
	_cast = CAST.new()
	_cast.name = "AfterlightCast"
	add_child(_cast)
	_load_errors.append_array(_cast.initialize(_cast_profiles(), _textures, content.get("manpu_textures", {})))
	_transmission_display = TRANSMISSION_DISPLAY.new()
	_transmission_display.name = "AfterlightTransmissionDisplay"
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
	_eye_layer.material.set_shader_parameter("viewport_size", DESIGN_SIZE)
	_eye_layer.material.set_shader_parameter("edge_softness", float(content.get("eye_mask", {}).get("edge_softness", 28.0)))
	_load_errors.append_array(_walking.configure(content.get("approach", {})))
	_load_errors.append_array(_eye.configure(content.get("eye_transition", {})))
	_validate_autoplay()
	if content.get("autoplay", {}) is Dictionary:
		_autoplay_enabled = bool(content.get("autoplay", {}).get("enabled", false))
	_build_ui()
	if beats.is_empty() or _backgrounds.is_empty(): _load_errors.append("Afterlight requires an authored episode and prepared backgrounds.")
	if _load_errors.is_empty():
		if saved_state.is_empty(): _restart()
		else: _restore_game()
	_render()


func _load_texture(path: String) -> Texture2D:
	var loaded := CONTENT_ADAPTER.load_texture(content.get("content_loader", CONTENT_ADAPTER.LOCAL_CONTENT.new()), path)
	_load_errors.append_array(loaded.errors)
	return loaded.resource


func current_beat() -> Dictionary:
	return beats[_beat_index] if _beat_index < beats.size() else {}


func _cast_profiles() -> Array:
	return content.get("guests", []) + content.get("supporting_cast", [])


func _profile(actor_id: String) -> Dictionary:
	for profile: Dictionary in _cast_profiles():
		if profile["id"] == actor_id: return profile
	return {}


func _bind_background(index: int) -> void:
	_background_index = index
	var dimensions := _backgrounds[index].get_size()
	var factor := maxf(DESIGN_SIZE.x / dimensions.x, DESIGN_SIZE.y / dimensions.y)
	_base_background = Rect2((DESIGN_SIZE - dimensions * factor) * 0.5, dimensions * factor)
	_load_errors.append_array(_walking.initialize(DESIGN_SIZE, _base_background))
	_load_errors.append_array(_camera.initialize(DESIGN_SIZE, _base_background))
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
	for layer: Dictionary in ATMOSPHERE.profile(profile_id):
		var emitter = AMBIENT_PARTICLES.new()
		emitter.name = str(layer["id"])
		_atmosphere_layer.add_child(emitter)
		_load_errors.append_array(emitter.start(layer["region"], layer["textures"], layer["options"]))
		_ambient_emitters.append(emitter)


func get_atmosphere_state() -> Dictionary:
	var layers := {}
	for emitter: Control in _ambient_emitters: layers[str(emitter.name)] = emitter.get_state()
	return {"profile": _atmosphere_id, "background": _atmosphere_background, "layers": layers}


func _restart(restored_choices: Dictionary = {}) -> void:
	_paused = false
	_clear_atmosphere()
	_background_blackout.clear()
	_cast_pan.clear()
	_history.clear()
	_manpu_history.clear()
	_contact_history.clear()
	_contact.reset()
	_choices = restored_choices.duplicate(true)
	_beat_index = 0
	_elapsed = 0.0
	_effect_time = 0.0
	_cast.set_cast([])
	for actor_id: String in _textures: _cast.set_projection(actor_id, false)
	_bind_background(0)
	_enter_beat()
	_render()


func _enter_beat() -> void:
	_autoplay_elapsed = 0.0
	_text_audio.stop()
	_voice_effects.set_bypassed(true)
	_voice_effects.reset()
	_sprite_burst.clear()
	_burst_emitted = false
	_blackout_started = false
	_approach_started = false
	_cast_pan_started = false
	_load_errors.append_array(_background_blackout.fade_to(0.0, float(content.get("background_blackout", {}).get("restore_seconds", 0.4))))
	_elapsed = 0.0
	_manpu_event_time = -1.0
	_contact_time = -1.0
	_contact.reset()
	var beat := current_beat()
	var kind := str(beat["type"])
	var actor_id := str(beat.get("speaker", ""))
	# New scene/cast direction resets this host's cast-layer framing. Ordinary
	# dialogue holds it until another pan, including through local actor motion.
	if beat.has("cast") or beat.has("background"):
		_cast_pan.clear()
	_eye.clear()
	_drift.clear()
	_establish.clear()
	_walking.clear()
	_shake.clear()
	if beat.has("shake"): _load_errors.append_array(_shake.start(beat["shake"]))
	if beat.has("background"): _bind_background(int(beat["background"]))
	if beat.has("cast") and kind != "handoff":
		var ids: Array[String] = []
		ids.assign(beat["cast"])
		_load_errors.append_array(_cast.set_cast(ids))
	_cast.set_marks([])
	if kind in ["monologue", "walk", "eye", "detail", "contact", "establish", "rift"]:
		_cast.cancel_manpu()
	_load_errors.append_array(_cast.focus(actor_id, str(beat.get("focus", "bounce")), bool(beat.get("focus_replay", false))))
	if beat.has("mark"):
		_load_errors.append_array(_cast.mark(actor_id, str(beat["mark"]), str(beat.get("mark_preset", ""))))
	if beat.get("manpu_timing", "on_enter") != "after_reveal" and not _replaying_checkpoint:
		_emit_beat_manpu()
	if str(beat.get("camera", "")) == "wide": _load_errors.append_array(_camera.wide(0.65))
	elif str(beat.get("camera", "")) == "close":
		var profile := _profile(actor_id)
		if profile.has("transmission_display"):
			var settings: Dictionary = profile["transmission_display"]
			var frame: Rect2 = settings.get("frame_rect", TRANSMISSION_DISPLAY.DEFAULT_FRAME)
			_load_errors.append_array(_camera.focus(actor_id, _cast_pan.sample_transform() * frame.get_center(), frame.get_center(), float(settings.get("camera_zoom", 1.06)), 0.8))
		else:
			var rect: Rect2 = _cast.get_actor_rect(actor_id)
			var eye_uv: Array = profile["eye_uv"]
			var point: Vector2 = _cast_pan.sample_transform() * (rect.position + rect.size * Vector2(float(eye_uv[0]), float(eye_uv[1])))
			_load_errors.append_array(_camera.focus(actor_id, point, Vector2(640, 280), 2.35, 0.8))
	match kind:
		"walk":
			_camera.clear()
			_load_errors.append_array(_walking.start())
		"eye":
			_load_errors.append_array(_eye.start(str(beat.get("eye_mode", "eye_opening")), beat.get("eye_settings", {})))
		"detail":
			_load_errors.append_array(_drift.start(content.get("drift", {})))
		"contact":
			if not _contact_textures.has(actor_id):
				_load_errors.append("Afterlight contact requires its actor's prepared contact portrait.")
		"establish":
			_camera.clear()
			_load_errors.append_array(_establish.start(str(content["backgrounds"][_background_index]["id"]), {"duration_seconds": 3.4, "pan_amount": 48.0, "zoom_amount": 0.1, "flare_enabled": true, "flare_strength": 0.28, "flare_source_uv": [0.74, 0.2]}))
		"handoff":
			_camera.clear()
			var ids: Array = beat["cast"]
			_load_errors.append_array(_cast.handoff(str(ids[0]), str(ids[1]), str(ids[2]), {"curve": "spring", "damping_ratio": 0.8, "exit_preset": str(beat.get("exit_preset", "silhouette_fade"))}))
		"projection": _load_errors.append_array(_cast.set_projection(actor_id, true))
		"exit": _load_errors.append_array(_cast.dismiss(actor_id, str(beat.get("exit_preset", "silhouette_fade"))))
	# A physical entrance explicitly clears a prior transmission treatment.
	if beat.has("physical"):
		for id: String in beat["physical"]: _cast.set_projection(id, false)
	_reveal.clear()
	var key := _resolved_text_key(beat)
	if not key.is_empty():
		_load_errors.append_array(_reveal.start(_text(key), {"chars_per_second": 32.0 if kind == "monologue" else 48.0}))
	_begin_text_audio()


func _process(delta: float) -> void:
	if _paused or not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0: return
	# A frame that finishes text, a cinematic or speech cannot also spend its
	# earlier time on reading. Only time starting with an open gate counts.
	var autoplay_ready := str(get_autoplay_state()["blocked_reason"]).is_empty()
	var step := delta
	if current_beat().get("type") == "contact" and _contact.is_confirmed():
		step = minf(delta, maxf(0.0, _contact_feedback_seconds() - (_elapsed - _contact_time)))
	_advance_clocks(step)
	_start_waiting_voice()
	_text_audio.update_reveal(int(_reveal.sample()["visible_characters"]), step)
	if _contact_complete(): _continue_story()
	else: _update_autoplay(step if autoplay_ready else 0.0)
	_render()


func _advance_clocks(delta: float) -> void:
	# Split at the reveal boundary so event age is independent of frame size.
	# Checkpoint replay uses the recorded actual event time, including fast taps.
	if not _replaying_checkpoint and _pending_reveal_manpu():
		var words: Dictionary = _reveal.get_state()
		var remaining := maxf(0.0, float(str(words["text"]).length()) / float(words["chars_per_second"]) - float(words["elapsed"]))
		if remaining <= delta:
			_advance_segment(remaining)
			_emit_beat_manpu()
			_advance_segment(delta - remaining)
			return
	_advance_segment(delta)


func _advance_segment(delta: float) -> void:
	# This authored burst has a fixed cue time, so checkpoint replay can rebuild
	# it from elapsed beat time without storing texture or particle snapshots.
	var cue: Dictionary = current_beat().get("sprite_burst", {})
	if not _burst_emitted and not cue.is_empty():
		var wait := maxf(0.0, float(cue.get("delay_seconds", 0.0)) - _elapsed)
		if wait <= delta:
			_advance_pan_segment(wait)
			_emit_beat_burst(cue)
			_advance_pan_segment(delta - wait)
			return
	_advance_pan_segment(delta)


func _advance_pan_segment(delta: float) -> void:
	var cue: Dictionary = current_beat().get("cast_pan", {})
	if not _cast_pan_started and not cue.is_empty():
		var wait := maxf(0.0, float(cue.get("delay_seconds", 0.0)) - _elapsed)
		if wait <= delta:
			_advance_world_segment(wait)
			_start_cast_pan(cue)
			_advance_world_segment(delta - wait)
			return
	_advance_world_segment(delta)


func _start_cast_pan(cue: Dictionary) -> void:
	_cast_pan_started = true
	var settings: Dictionary = content.get("cast_pan", {}).duplicate(true)
	settings.merge(cue.get("settings", {}), true)
	var offset := Vector2.ZERO
	if cue.has("actor") and not cue.has("offset"):
		var actor_id := str(cue["actor"])
		if not _cast.visible_ids().has(actor_id):
			_load_errors.append("Cast Pan requires a visible target actor.")
			return
		var anchor: Variant = cue.get("anchor_x", DESIGN_SIZE.x * 0.5)
		if not (anchor is float or anchor is int) or not is_finite(float(anchor)) or float(anchor) < 0.0 or float(anchor) > DESIGN_SIZE.x:
			_load_errors.append("Cast Pan anchor_x must be finite and inside the design viewport.")
			return
		var center: Vector2 = _cast.get_actor_rect(actor_id).get_center()
		var profile := _profile(actor_id)
		if profile.has("transmission_display"):
			center = profile["transmission_display"].get("frame_rect", TRANSMISSION_DISPLAY.DEFAULT_FRAME).get_center()
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


func _advance_world_segment(delta: float) -> void:
	var previous_elapsed := _elapsed
	_elapsed += delta
	_reveal.advance(delta)
	# Black monologues suspend the world; they do not finish a camera cue.
	if current_beat().get("type") == "monologue": return
	_effect_time += delta
	for emitter: Control in _ambient_emitters: emitter.advance(delta)
	_cast_pan.advance(delta)
	_shake.advance(delta)
	_walking.advance(delta)
	_camera.advance(delta)
	_establish.advance(delta)
	_drift.advance(delta)
	_eye.advance(delta)
	_advance_actor_blocking(delta, previous_elapsed)
	_sprite_burst.advance(delta)
	_advance_background_blackout(delta, previous_elapsed)


func _advance_actor_blocking(delta: float, previous_elapsed: float) -> void:
	var cue: Dictionary = current_beat().get("quick_approach", {})
	var delay := float(cue.get("delay_seconds", 0.0))
	if not cue.is_empty() and not _approach_started and _elapsed >= delay:
		var before := maxf(0.0, delay - previous_elapsed)
		_cast.advance(before)
		var settings: Dictionary = content.get("quick_approach", {}).duplicate(true)
		settings.merge(cue.get("settings", {}), true)
		_load_errors.append_array(_cast.approach_actor(str(cue["actor"]), str(cue["target"]), settings))
		_approach_started = true
		_cast.advance(maxf(0.0, delta - before))
	else:
		_cast.advance(delta)


func _advance_background_blackout(delta: float, previous_elapsed: float) -> void:
	var cue: Dictionary = current_beat().get("background_blackout", {})
	var delay := float(cue.get("delay_seconds", 0.0))
	if not cue.is_empty() and not _blackout_started and _elapsed >= delay:
		# Use only the part of this frame after the authored cue boundary. This
		# keeps large-step checkpoint replay identical to ordinary playback.
		var before := maxf(0.0, delay - previous_elapsed)
		_background_blackout.advance(before)
		var duration := float(cue.get("fade_seconds", content.get("background_blackout", {}).get("fade_seconds", 0.45)))
		_load_errors.append_array(_background_blackout.fade_to(1.0, duration))
		_blackout_started = true
		_background_blackout.advance(maxf(0.0, delta - before))
	else:
		_background_blackout.advance(delta)


func _emit_beat_burst(cue: Dictionary) -> void:
	_burst_emitted = true
	var actor_id := str(cue.get("actor", ""))
	if not _cast.visible_ids().has(actor_id):
		_load_errors.append("Afterlight sprite burst requires a visible actor.")
		return
	var textures: Array[Texture2D] = []
	for sprite_id: String in cue.get("sprites", []):
		textures.append(_burst_textures.get(sprite_id))
	var rect: Rect2 = _cast.get_actor_rect(actor_id)
	var origin: Vector2 = rect.position + rect.size * cue.get("origin_uv", Vector2(0.5, 0.25))
	var options: Dictionary = content.get("sprite_burst", {}).get("options", {}).duplicate(true)
	options.merge(cue.get("options", {}), true)
	var result: Dictionary = _sprite_burst.emit_burst(origin, textures, options)
	_load_errors.append_array(result["errors"])


func _pending_reveal_manpu() -> bool:
	return _manpu_event_time < 0.0 and current_beat().get("manpu_timing") == "after_reveal" and not current_beat().get("manpu_events", []).is_empty()


func _emit_beat_manpu() -> void:
	if _manpu_event_time >= 0.0 or current_beat().get("manpu_events", []).is_empty(): return
	_manpu_event_time = _elapsed
	for event: Dictionary in current_beat()["manpu_events"]:
		var result: Dictionary = _cast.emit_manpu(str(event["actor"]), str(event["id"]), str(event["preset"]))
		_load_errors.append_array(result["errors"])


func _emit_revealed_manpu() -> void:
	if not _replaying_checkpoint and _pending_reveal_manpu() and _reveal.sample()["phase"] == "holding":
		_emit_beat_manpu()


func _cinematic() -> bool:
	return current_beat().get("type") in CINEMATICS


func _cinematic_complete() -> bool:
	match current_beat().get("type"):
		"walk": return not _walking.is_active()
		"eye": return not _eye.is_active()
		"establish": return not _establish.is_active()
		"handoff", "exit": return not _cast.is_busy()
		"rift": return _elapsed >= float(current_beat().get("duration_seconds", 1.6))
	return false


func _next() -> void:
	if _paused or not _load_errors.is_empty(): return
	_autoplay_elapsed = 0.0
	if current_beat().get("type") == "contact":
		# Revealing words is allowed; contact itself always needs a target hit.
		if _reveal.sample()["phase"] == "revealing":
			_reveal.request_advance()
			_text_audio.sync_reveal(int(_reveal.sample()["visible_characters"]))
		_render()
		return
	if _cinematic() and not _cinematic_complete():
		# Complete the current motion; one input never skips the following beat.
		_advance_clocks(30.0)
		_start_waiting_voice()
	elif _reveal.sample()["phase"] == "revealing":
		_reveal.request_advance()
		_text_audio.sync_reveal(int(_reveal.sample()["visible_characters"]))
		_emit_revealed_manpu()
	elif _choice_pending():
		pass
	elif _beat_index == beats.size() - 1:
		_toggle_pause()
	else:
		_continue_story()
	_render()


func _continue_story() -> void:
	if _choice_pending() or _beat_index + 1 >= beats.size(): return
	if current_beat().get("type") == "contact" and not _contact_complete(): return
	_history.append(_elapsed)
	_manpu_history.append(_manpu_event_time)
	_contact_history.append(_contact_time)
	_beat_index += 1
	_enter_beat()


func _choice_pending() -> bool:
	return current_beat().get("type") == "choice" and not _choices.has(current_beat()["id"])


## Autoplay is host direction. The audio/reveal components never advance a beat.
func set_autoplay_enabled(enabled: bool) -> void:
	_autoplay_enabled = enabled
	_autoplay_elapsed = 0.0
	_render()


func _autoplay_settings() -> Dictionary:
	var settings: Dictionary = content.get("autoplay", {}).duplicate()
	settings.merge(current_beat().get("autoplay", {}), true)
	return settings


func get_autoplay_state() -> Dictionary:
	var settings := _autoplay_settings()
	var delay := float(settings.get("choice_delay_seconds", 5.0) if _choice_pending() else settings.get("delay_seconds", 3.0))
	var default_choice := str(settings.get("default_choice", ""))
	var reason := ""
	var audio: Dictionary = _text_audio.get_state()
	if not _load_errors.is_empty(): reason = "load_error"
	elif _paused: reason = "paused"
	elif not _autoplay_enabled: reason = "disabled"
	elif _cinematic() and not _cinematic_complete(): reason = "cinematic"
	elif _reveal.sample()["phase"] != "holding": reason = "text"
	elif _voice_waiting or (audio["active_mode"] == "voice" and not audio["voice_finished"]): reason = "voice"
	elif current_beat().get("type") == "contact" or bool(settings.get("require_input", false)): reason = "required_input"
	elif _choice_pending() and default_choice.is_empty(): reason = "choice"
	elif not _choice_pending() and _beat_index + 1 >= beats.size(): reason = "ended"
	return {"enabled": _autoplay_enabled, "elapsed_seconds": _autoplay_elapsed,
		"delay_seconds": delay, "remaining_seconds": maxf(0.0, delay - _autoplay_elapsed),
		"blocked_reason": reason, "default_choice": default_choice}


func _update_autoplay(delta: float) -> void:
	if _replaying_checkpoint or not is_finite(delta) or delta < 0.0: return
	var state := get_autoplay_state()
	var reason := str(state["blocked_reason"])
	if reason == "paused": return
	if not reason.is_empty():
		_autoplay_elapsed = 0.0
		if reason == "ended": _autoplay_enabled = false
		return
	_autoplay_elapsed += delta
	if _autoplay_elapsed < float(state["delay_seconds"]): return
	# At most one authored action per update, regardless of frame size.
	if _choice_pending(): _choose(str(state["default_choice"]))
	else: _continue_story()


func _validate_autoplay() -> void:
	var configured: Variant = content.get("autoplay", {})
	if not configured is Dictionary:
		_load_errors.append("Afterlight autoplay settings must be a dictionary.")
		return
	var inputs: Array = [{"settings": configured, "beat": {}}]
	for beat: Dictionary in beats:
		inputs.append({"settings": beat.get("autoplay", {}), "beat": beat})
	for input: Dictionary in inputs:
		var settings: Variant = input["settings"]
		if not settings is Dictionary:
			_load_errors.append("Afterlight beat autoplay settings must be a dictionary.")
			continue
		for key: Variant in settings:
			var value: Variant = settings[key]
			if key in ["delay_seconds", "choice_delay_seconds"]:
				if not _valid_time(value) or float(value) <= 0.0 or float(value) > 120.0:
					_load_errors.append("Afterlight autoplay delays must be positive and at most 120 seconds.")
			elif key in ["enabled", "require_input"]:
				if not value is bool: _load_errors.append("Afterlight autoplay flags must be boolean.")
				if key == "enabled" and not input["beat"].is_empty():
					_load_errors.append("Afterlight autoplay enabled is a host default; use require_input for a beat gate.")
			elif key == "default_choice":
				var valid := false
				for option: Dictionary in input["beat"].get("choices", []):
					if value is String and option["id"] == value: valid = true
				if not valid: _load_errors.append("Afterlight autoplay default_choice must name this beat's authored option.")
			else:
				_load_errors.append("Unknown Afterlight autoplay setting: " + str(key))


func _choose(option_id: String) -> void:
	if _paused or not _load_errors.is_empty() or not _choice_pending() or _reveal.sample()["phase"] != "holding": return
	for option: Dictionary in current_beat().get("choices", []):
		if option["id"] == option_id:
			_choices[current_beat()["id"]] = option_id
			_continue_story()
			_render()
			return


func _resolved_text_key(beat: Dictionary = {}) -> String:
	if beat.is_empty(): beat = current_beat()
	if beat.has("choice_from"):
		return str(beat.get("responses", {}).get(_choices.get(beat["choice_from"], ""), ""))
	return str(beat.get("text", ""))


func _world_transform() -> Transform2D:
	var pose: Dictionary = _walking.sample() if current_beat().get("type") == "walk" else _camera.sample()
	var zoom := float(pose["zoom"])
	var offset := Vector2(float(pose["offset_x"]), float(pose["offset_y"]))
	if current_beat().get("type") == "establish":
		var shot: Dictionary = _establish.sample()
		zoom = float(shot["zoom"])
		offset = DESIGN_SIZE * 0.5 * (1.0 - zoom) + Vector2(float(shot["pan_x"]), 0)
		offset = offset.clamp(DESIGN_SIZE - _base_background.end * zoom, -_base_background.position * zoom)
	if current_beat().get("type") == "detail":
		zoom = 1.24
		offset = DESIGN_SIZE * 0.5 * (1.0 - zoom) + _drift_offset()
	var base := Transform2D(Vector2(zoom, 0), Vector2(0, zoom), offset)
	return _shake.compose(base, _base_background, DESIGN_SIZE)


func _drift_offset() -> Vector2:
	var pose: Dictionary = _drift.sample()
	var base := Rect2(_base_background.position * 1.24 + DESIGN_SIZE * -0.12, _base_background.size * 1.24)
	return DRIFT.constrain_offset(base, DESIGN_SIZE, Vector2(float(pose["offset_x"]), float(pose["offset_y"])))


func _cast_transform() -> Transform2D:
	return _world_transform() * _cast_pan.sample_transform()


func presented_background_rect() -> Rect2:
	return _world_transform() * _base_background


func _portrait_rect(detail: bool) -> Rect2:
	var id := str(current_beat().get("speaker", "nami"))
	var profile := _profile(id)
	if current_beat().get("type") == "contact":
		_portrait.texture = _contact_textures[id]
		return _world_transform() * _contact_world_rect()
	if detail and _details.has(id):
		_portrait.texture = _details[id]
		var height := float(profile.get("detail_height", 1600.0))
		var width := height * _portrait.texture.get_width() / _portrait.texture.get_height()
		return Rect2(Vector2(640 - width * 0.5, float(profile.get("detail_y", -200))) + _drift_offset(), Vector2(width, height))
	_portrait.texture = _portraits.get(id, _textures[id])
	var height := float(profile.get("eye_close_height", 1050.0))
	var width := height * _portrait.texture.get_width() / _portrait.texture.get_height()
	var uv: Array = profile.get("eye_close_uv", profile["eye_uv"])
	return Rect2(640 - width * float(uv[0]), 280 - height * float(uv[1]), width, height)


func _contact_world_rect() -> Rect2:
	var actor_id := str(current_beat().get("speaker", ""))
	var texture: Texture2D = _contact_textures.get(actor_id)
	if texture == null: return Rect2()
	var profile := _profile(actor_id)
	var height := float(profile.get("contact_height", 960.0))
	var width := height * texture.get_width() / texture.get_height()
	return Rect2(640.0 - width * 0.5, float(profile.get("contact_y", -60.0)), width, height)


func _contact_feedback_seconds() -> float:
	return float(content.get("contact", {}).get("feedback_seconds", 0.45))


func _contact_complete() -> bool:
	return current_beat().get("type") == "contact" and _contact.is_confirmed() and _contact_time >= 0.0 and _elapsed - _contact_time + 0.000000001 >= _contact_feedback_seconds()


func contact_target() -> Dictionary:
	var result := {"center": Vector2.ZERO, "radius": 0.0, "visible": false,
		"ready": false, "confirmed": _contact.is_confirmed()}
	if current_beat().get("type") != "contact" or not _load_errors.is_empty(): return result
	var profile := _profile(str(current_beat().get("speaker", "")))
	var uv: Array = profile.get("contact_uv", [0.5, 0.52])
	var rect := _contact_world_rect()
	var camera := _world_transform()
	result["center"] = camera * (rect.position + rect.size * Vector2(float(uv[0]), float(uv[1])))
	result["radius"] = rect.size.y * float(profile.get("contact_radius_ratio", 0.035)) * minf(camera.x.length(), camera.y.length())
	result["visible"] = not _paused and rect.has_area()
	result["ready"] = result["visible"] and _reveal.sample()["phase"] == "holding" and not _contact.is_confirmed()
	return result


func _try_contact(point: Vector2) -> bool:
	var target := contact_target()
	if not bool(target["ready"]): return false
	if not _contact.confirm_at(point, target["center"], float(target["radius"])): return false
	_contact_time = _elapsed
	_render()
	return true


func _present_contact() -> void:
	var target := contact_target()
	_contact_ring.visible = bool(target["visible"]) and (_reveal.sample()["phase"] == "holding")
	if not _contact_ring.visible: return
	var progress := clampf((_elapsed - _contact_time) / _contact_feedback_seconds(), 0.0, 1.0) if _contact.is_confirmed() else 0.0
	var pulse := 1.0 if _contact.is_confirmed() else 0.88 + 0.12 * sin(_elapsed * 3.2)
	var diameter := float(target["radius"]) * (1.0 + progress * 1.7)
	_contact_ring.size = Vector2.ONE * diameter
	_contact_ring.position = (target["center"] as Vector2) - _contact_ring.size * 0.5
	_contact_ring.modulate.a = (1.0 - progress) * pulse
	_contact_dot.size = Vector2.ONE * maxf(4.0, float(target["radius"]) * 0.20)
	_contact_dot.position = (_contact_ring.size - _contact_dot.size) * 0.5


func _render() -> void:
	if _line == null: return
	if not _load_errors.is_empty():
		_black.hide()
		_dialogue.show()
		_line.text = _text("error.scene_load") + "\n" + "\n".join(_load_errors)
		_line.visible_characters = -1
		_line.add_theme_font_size_override("font_size", 17)
		_ready_dot.hide()
		_contact_ring.hide()
		for button: Button in _choice_buttons: button.hide()
		return
	var beat := current_beat()
	var kind := str(beat["type"])
	var portrait_shot := kind in ["detail", "contact"] or (kind == "eye" and bool(beat.get("eye_portrait", true)))
	_cast.visible = kind not in ["walk", "establish", "monologue"] and not portrait_shot
	_cast.present(_cast_transform())
	for emitter: Control in _ambient_emitters: emitter.present(_world_transform())
	_sprite_burst.present(_cast_transform())
	_present_transmission_display()
	_portrait.visible = portrait_shot
	_halo.hide()
	if portrait_shot:
		var rect := _portrait_rect(kind == "detail")
		_portrait.position = rect.position
		_portrait.size = rect.size
		if kind == "detail":
			_halo.set_source(_portrait.texture)
			_halo.set_rect(rect)
			_halo.set_strength(1.0)
	_eye_layer.visible = kind == "eye"
	_eye_layer.material.set_shader_parameter("openness", float(_eye.sample()["openness"]))
	_flare.visible = kind == "establish"
	if _flare.visible:
		var shot: Dictionary = _establish.sample()
		var uv: Array = shot["flare_source_uv"]
		var point := _world_transform() * (_base_background.position + _base_background.size * Vector2(float(uv[0]), float(uv[1])))
		_flare.material.set_shader_parameter("light_position", point / DESIGN_SIZE)
		_flare.material.set_shader_parameter("strength", float(shot["flare_strength"]))
	_ui.visible = kind != "monologue"
	_header.visible = kind not in ["eye", "detail", "contact"]
	_dialogue.visible = not _cinematic() or _cinematic_complete()
	var words: Dictionary = _reveal.sample()
	_line.text = str(words["text"])
	_line.visible_characters = int(words["visible_characters"])
	var speaker := str(beat.get("speaker", ""))
	_speaker.text = _text(str(beat["speaker_name"])) if beat.has("speaker_name") else (_text("guest." + speaker + ".name") if not speaker.is_empty() else _text("episode.ui.protagonist"))
	_location.text = _text(str(beat["place_name"])) if beat.has("place_name") else str(content["backgrounds"][_background_index]["name"])
	_location.modulate.a = 1.0 if kind in ["walk", "establish"] else clampf(1.0 - (_elapsed - 1.8) / 1.2, 0.0, 1.0)
	_black.visible = kind == "monologue"
	_monologue.text = str(words["text"])
	_monologue.visible_characters = int(words["visible_characters"])
	var held := str(words["phase"]) == "holding"
	var ready := held and kind != "contact" and not _choice_pending() and not _paused and (not _cinematic() or _cinematic_complete())
	_ready_dot.visible = ready and kind != "monologue"
	_monologue_dot.visible = ready and kind == "monologue"
	var pulse := 0.65 + 0.35 * sin(_elapsed * 3.2) * sin(_elapsed * 3.2)
	_ready_dot.modulate.a = pulse
	_monologue_dot.modulate.a = pulse
	var options: Array = beat.get("choices", [])
	var autoplay := get_autoplay_state()
	for index in _choice_buttons.size():
		var button := _choice_buttons[index]
		button.visible = _choice_pending() and held and not _paused and index < options.size()
		if button.visible:
			button.text = _text(str(options[index]["text"]))
			var is_default: bool = autoplay["enabled"] and str(options[index]["id"]) == str(autoplay["default_choice"])
			if is_default and str(autoplay["blocked_reason"]).is_empty():
				button.text += "  ·  " + _text("episode.ui.autoplay_choice").replace("{seconds}", str(ceili(float(autoplay["remaining_seconds"]))))
			button.add_theme_color_override("font_color", ACCENT if is_default else INK)
			button.set_meta("choice_id", str(options[index]["id"]))
	_pause_menu.visible = _paused
	_language_button.text = _text("ui.language_target")
	_autoplay_button.text = _text("episode.ui.autoplay_on" if _autoplay_enabled else "episode.ui.autoplay_off")
	_autoplay_button.set_pressed_no_signal(_autoplay_enabled)
	_autoplay_button.add_theme_color_override("font_color", ACCENT if _autoplay_enabled else INK)
	_present_ominous_effects()
	_present_contact()
	queue_redraw()


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
	var beat := current_beat()
	var envelope := 1.0
	if bool(beat.get("vfx_fade_out", false)):
		envelope = 1.0 - smoothstep(0.0, float(beat.get("duration_seconds", 1.6)), _elapsed)
	elif beat.get("type") == "rift":
		envelope = smoothstep(0.0, 0.25, _elapsed)
	for field: Control in [_heat_haze, _world_corruption, _local_corruption, _barrier]:
		field.set_time(_effect_time)
	_heat_haze.set_rect(Rect2(60, 80, 1160, 790))
	_heat_haze.set_strength(float(beat.get("heat", 0.0)) * envelope)
	_world_corruption.set_rect(Rect2(Vector2.ZERO, DESIGN_SIZE))
	_world_corruption.set_pattern_transform(_world_transform())
	_world_corruption.set_strength(float(beat.get("scene_corruption", 0.0)) * envelope)
	_barrier.set_rect(Rect2(240, 90, 800, 800))
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
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if not _load_errors.is_empty() or _backgrounds.is_empty(): return
	draw_texture_rect(_backgrounds[_background_index], presented_background_rect(), false)
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color(0.07, 0.045, 0.1, 0.08))


func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		set_language("ko" if get_language() == "en" else "en")
	elif event.keycode == KEY_ESCAPE: _toggle_pause()
	elif event.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		if _paused: return
		var owner := get_viewport().gui_get_focus_owner()
		if owner != null: return
		_next()
	else: return
	get_viewport().set_input_as_handled()


func _toggle_pause() -> void:
	_paused = not _paused
	_text_audio.set_paused(_paused)
	get_viewport().gui_release_focus()
	_render()


func save_game() -> Dictionary:
	# Replay authored elapsed history; preserve manual reveal and event times
	# separately because revealing a line never advances the world clock.
	var words: Dictionary = _reveal.get_state()
	return {"story_version": 4, "beat_id": current_beat()["id"], "history": _history.duplicate(), "elapsed": _elapsed,
		"choices": _choices.duplicate(true), "manpu_history": _manpu_history.duplicate(), "manpu_event_time": _manpu_event_time,
		"contact_history": _contact_history.duplicate(), "contact_time": _contact_time,
		"reveal_fraction": minf(1.0, float(words["elapsed"]) * float(words["chars_per_second"]) / maxf(1.0, str(words["text"]).length())),
		"voice_position_seconds": _voice_position(), "voice_source_revision": str(_voice_state.get("source_revision", "")), "language": get_language(),
		"autoplay": {"enabled": _autoplay_enabled, "elapsed_seconds": _autoplay_elapsed}}


func _restore_game() -> void:
	var autoplay: Variant = saved_state.get("autoplay", {"enabled": bool(content.get("autoplay", {}).get("enabled", false)), "elapsed_seconds": 0.0})
	if not autoplay is Dictionary or not autoplay.get("enabled") is bool or not _valid_time(autoplay.get("elapsed_seconds")):
		_load_errors.append("Afterlight autoplay checkpoint requires enabled and a finite nonnegative elapsed_seconds.")
		return
	var voice_position: Variant = saved_state.get("voice_position_seconds", 0.0)
	if not _valid_time(voice_position, true) or not saved_state.get("voice_source_revision", "") is String:
		_load_errors.append("Afterlight voice position must be finite and nonnegative, or -1 for a finished clip.")
		return
	var history: Variant = saved_state.get("history")
	var events: Variant = saved_state.get("manpu_history")
	var contacts: Variant = saved_state.get("contact_history")
	var choices: Variant = saved_state.get("choices")
	if saved_state.get("story_version") != 4 or not history is Array or history.size() >= beats.size() or not events is Array or events.size() != history.size() or not contacts is Array or contacts.size() != history.size() or not choices is Dictionary:
		_load_errors.append("Cannot resume an incompatible Afterlight episode checkpoint.")
		return
	var times: Array = history.duplicate()
	times.append(saved_state.get("elapsed"))
	var event_times: Array = events.duplicate()
	event_times.append(saved_state.get("manpu_event_time"))
	var contact_times: Array = contacts.duplicate()
	contact_times.append(saved_state.get("contact_time"))
	for index in times.size():
		var value: Variant = times[index]
		var event_time: Variant = event_times[index]
		var contact_time: Variant = contact_times[index]
		if not _valid_time(value) or not _valid_time(event_time, true) or float(event_time) > float(value) or not _valid_time(contact_time, true) or float(contact_time) > float(value):
			_load_errors.append("Afterlight checkpoint times must be finite and internally consistent.")
			return
		var has_events: bool = not beats[index].get("manpu_events", []).is_empty()
		if (not has_events and float(event_time) != -1.0) or (has_events and beats[index].get("manpu_timing", "on_enter") != "after_reveal" and float(event_time) != 0.0) or (has_events and index < history.size() and float(event_time) < 0.0):
			_load_errors.append("Afterlight checkpoint event history does not match its authored beat.")
			return
		var is_contact: bool = beats[index].get("type") == "contact"
		if (not is_contact and float(contact_time) != -1.0) or (is_contact and index < history.size() and (float(contact_time) < 0.0 or float(value) - float(contact_time) + 0.000000001 < _contact_feedback_seconds())):
			_load_errors.append("Afterlight checkpoint contact history does not match its authored beat.")
			return
	var fraction: Variant = saved_state.get("reveal_fraction")
	if not _valid_time(fraction) or float(fraction) > 1.0 or saved_state.get("beat_id") != beats[history.size()]["id"]:
		_load_errors.append("Afterlight checkpoint does not match its authored beat.")
		return
	var current: Dictionary = beats[history.size()]
	if current.get("type") == "contact" and float(contact_times.back()) >= 0.0 and float(fraction) < 1.0:
		_load_errors.append("Afterlight contact cannot be acknowledged before its line is revealed.")
		return
	if current.get("manpu_timing") == "after_reveal" and not current.get("manpu_events", []).is_empty() and float(fraction) >= 1.0 and float(event_times.back()) < 0.0:
		_load_errors.append("Afterlight checkpoint is missing its revealed line event.")
		return
	var known_choices: Dictionary = {}
	for index in beats.size():
		var beat: Dictionary = beats[index]
		if beat.get("type") != "choice": continue
		var id: String = beat["id"]
		known_choices[id] = true
		if not choices.has(id):
			if index < history.size():
				_load_errors.append("Afterlight checkpoint is missing an earlier choice.")
				return
			continue
		var valid_option := false
		for option: Dictionary in beat.get("choices", []):
			if choices[id] is String and option["id"] == choices[id]: valid_option = true
		if index >= history.size() or not valid_option:
			_load_errors.append("Afterlight checkpoint contains an invalid or future choice.")
			return
	for id: Variant in choices:
		if not id is String or not known_choices.has(id):
			_load_errors.append("Afterlight checkpoint contains an unknown choice.")
			return
	_replaying_checkpoint = true
	_restart(choices)
	for index in times.size():
		if index > 0: _continue_story()
		var event_time := float(event_times[index])
		if event_time >= 0.0:
			_advance_clocks(event_time)
			_emit_beat_manpu()
			_advance_clocks(float(times[index]) - event_time)
		else:
			_advance_clocks(float(times[index]))
		if float(contact_times[index]) >= 0.0:
			_contact_time = float(contact_times[index])
			_contact.reset(true)
	_replaying_checkpoint = false
	_set_reveal_fraction(float(fraction))
	_begin_text_audio(float(voice_position), str(saved_state.get("voice_source_revision", "")))
	_autoplay_enabled = bool(autoplay["enabled"])
	var same_source := str(saved_state.get("voice_source_revision", "")) == str(_voice_state.get("source_revision", ""))
	if same_source and saved_state.get("language") == get_language() and str(get_autoplay_state()["blocked_reason"]).is_empty():
		_autoplay_elapsed = minf(float(autoplay["elapsed_seconds"]), float(get_autoplay_state()["delay_seconds"]))


func _valid_time(value: Variant, allow_unemitted: bool = false) -> bool:
	if not (value is float or value is int) or not is_finite(float(value)): return false
	return float(value) >= 0.0 or (allow_unemitted and float(value) == -1.0)


func _text(key: String) -> String:
	return text_set.text(key) if text_set != null else "[" + key + "]"


func get_language() -> String:
	return text_set.get_language() if text_set != null else "en"


func set_language(language: String) -> Array[String]:
	var same_language := language == get_language()
	var voice_position := _voice_position() if same_language else 0.0
	var voice_revision := str(_voice_state.get("source_revision", "")) if same_language else ""
	var errors: Array[String] = text_set.set_language(language)
	if not errors.is_empty(): return errors
	if not same_language: _autoplay_elapsed = 0.0
	var words: Dictionary = _reveal.get_state()
	var fraction := minf(1.0, float(words["elapsed"]) * float(words["chars_per_second"]) / maxf(1.0, str(words["text"]).length()))
	content = content_factory.call(text_set)
	for binding: Dictionary in _ui_bindings: binding["node"].text = _text(binding["key"])
	_reveal.start(_text(_resolved_text_key()), {"chars_per_second": float(words["chars_per_second"])})
	_set_reveal_fraction(fraction)
	_begin_text_audio(voice_position, voice_revision)
	language_changed.emit(language)
	_render()
	return []


func _set_reveal_fraction(fraction: float) -> void:
	var state: Dictionary = _reveal.get_state()
	state["elapsed"] = float(str(state["text"]).length()) / float(state["chars_per_second"]) * fraction
	state["phase"] = "holding" if fraction >= 1.0 else "revealing"
	_load_errors.append_array(_reveal.restore(state))


func _begin_text_audio(voice_position: float = 0.0, resume_revision: String = "") -> void:
	# Replay rebuilds visual controllers only; start audio once at the final cue.
	if _replaying_checkpoint: return
	_voice_waiting = false
	var settings: Dictionary = content.get("text_audio", {}).duplicate()
	settings.merge(current_beat().get("text_audio", {}), true)
	var voices: Dictionary = content.get("voiceovers", {}).get(get_language(), {})
	var supplied: AudioStream = voices.get(_resolved_text_key())
	_voice_state = voice_policy.resolve(_resolved_text_key(), get_language(), supplied) if voice_policy != null else {"status": "none", "voice_policy": "none", "stream": null}
	var voice: AudioStream = _voice_state.get("stream") if _voice_state["status"] == "ready" else null
	# Speech begins when the cinematic's caption becomes visible. Its existing
	# first-input motion completion stays intact; no voice ends or skips a beat.
	if voice != null and settings.get("mode", "auto") == "auto":
		if _cinematic() and not _cinematic_complete():
			_voice_waiting = true
			settings["mode"] = "silent"
			voice = null
		else:
			_set_reveal_fraction(1.0)
			_emit_revealed_manpu()
	elif _cinematic():
		settings["mode"] = "silent"
	_text_audio.stop()
	_voice_effects.reset()
	# Visual and vocal coordination belongs to this host, keyed by the actual
	# voiced speaker. An offscreen voice or protagonist reply stays dry.
	var speaker_id := str(_voice_state.get("speaker_id", ""))
	var display: Dictionary = _profile(speaker_id).get("transmission_display", {})
	var transmitted: bool = voice != null and settings.get("mode", "auto") == "auto" and _cast.visible_ids().has(speaker_id) and bool(_cast._projection.get(speaker_id, false)) and display.get("voice_effect", "") == "transmission_voice"
	_voice_effects.set_bypassed(not transmitted)
	if transmitted: settings["voice_bus"] = _voice_effects.get_output_bus()
	var errors: Array[String] = _text_audio.configure(settings)
	_load_errors.append_array(errors)
	if not errors.is_empty(): return
	var words: Dictionary = _reveal.sample()
	var resume := voice_position if not resume_revision.is_empty() and resume_revision == str(_voice_state.get("source_revision", "")) else 0.0
	_text_audio.begin(str(words["text"]), voice, int(words["visible_characters"]), resume)
	_text_audio.set_paused(_paused)


func _start_waiting_voice() -> void:
	if _voice_waiting and not _replaying_checkpoint and _cinematic_complete():
		_begin_text_audio()


func get_voice_state() -> Dictionary:
	var result := _voice_state.duplicate(true)
	result.erase("stream")
	result["waiting_for_cinematic"] = _voice_waiting
	result["playback"] = _text_audio.get_state()
	result["processing"] = _voice_effects.get_state()
	return result


func _voice_position() -> float:
	var audio: Dictionary = _text_audio.get_state()
	return -1.0 if bool(audio["voice_finished"]) else float(audio["voice_position_seconds"])


func _exit_tree() -> void:
	_text_audio.stop()
	_voice_effects.cleanup()


func _shader_layer(path: String) -> ColorRect:
	var layer := ColorRect.new()
	layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var material := ShaderMaterial.new()
	material.shader = load(path)
	layer.material = material
	add_child(layer)
	layer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return layer


func _build_ui() -> void:
	gui_input.connect(_on_scene_input)
	_ui = _container(self)
	_header = _container(_ui)
	_edge_gradient(_header, "TopGradient", Rect2(0, 0, 1280, 190), true)
	var title := _label(_header, "episode.title", Rect2(40, 26, 720, 34), 22)
	title.add_theme_color_override("font_color", ACCENT)
	_location = _label(_header, "", Rect2(40, 72, 1000, 38), 22)
	_language_button = _button(_header, "ui.language_target", Rect2(930, 26, 150, 38), func() -> void: set_language("ko" if get_language() == "en" else "en"))
	var menu := _button(_header, "episode.ui.menu", Rect2(1096, 26, 146, 38), _toggle_pause)
	for button: Button in [_language_button, menu]:
		for state in ["normal", "hover", "pressed"]:
			button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.add_theme_color_override("font_hover_color", ACCENT)
	_dialogue = _container(_ui)
	_edge_gradient(_dialogue, "BottomGradient", Rect2(0, 620, 1280, 280), false)
	_speaker = _label(_dialogue, "", Rect2(58, 702, 1100, 34), 24)
	_speaker.add_theme_color_override("font_color", ACCENT)
	_line = _label(_dialogue, "", Rect2(58, 752, 1135, 108), 26)
	_ready_dot = _indicator(_dialogue, Vector2(1207, 853))
	_contact_ring = Panel.new()
	_contact_ring.name = "FingertipContactRing"
	_contact_ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ring_style := StyleBoxFlat.new()
	ring_style.bg_color = Color(ACCENT, 0.04)
	ring_style.border_color = Color(INK, 0.90)
	ring_style.set_border_width_all(2)
	ring_style.set_corner_radius_all(128)
	_contact_ring.add_theme_stylebox_override("panel", ring_style)
	_ui.add_child(_contact_ring)
	_contact_dot = _indicator(_contact_ring, Vector2.ZERO)
	for index in 2:
		var button := _button(_ui, "", Rect2(360, 482 + index * 68, 560, 58))
		button.name = "StoryChoice" + str(index + 1)
		button.add_theme_font_size_override("font_size", 21)
		button.pressed.connect(func() -> void: _choose(str(button.get_meta("choice_id", ""))))
		_choice_buttons.append(button)
		for state in ["normal", "hover", "pressed", "focus"]:
			var style := StyleBoxFlat.new()
			style.bg_color = Color(0.25, 0.18, 0.24, 0.96) if state in ["hover", "pressed"] else Color(0.085, 0.065, 0.11, 0.92)
			style.border_color = ACCENT if state in ["focus", "hover"] else Color(0.89, 0.73, 0.67, 0.42)
			style.set_border_width_all(1)
			style.set_corner_radius_all(3)
			button.add_theme_stylebox_override(state, style)
	_black = _container(self)
	var backdrop := ColorRect.new()
	backdrop.color = Color.BLACK
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_black.add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_monologue = _label(_black, "", Rect2(170, 280, 940, 340), 30)
	_monologue.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_monologue.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_monologue_dot = _indicator(_black, Vector2(636, 748))
	# Keep the user's transport control reachable even when cinematic direction
	# hides the normal header or a monologue covers the world with black.
	_autoplay_button = _button(self, "", Rect2(730, 26, 190, 38), func() -> void: set_autoplay_enabled(not _autoplay_enabled))
	_autoplay_button.name = "AutoplayToggle"
	_autoplay_button.toggle_mode = true
	for state in ["normal", "hover", "pressed"]:
		_autoplay_button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	_autoplay_button.add_theme_color_override("font_hover_color", ACCENT)

	_pause_menu = _container(self)
	_pause_menu.mouse_filter = Control.MOUSE_FILTER_STOP
	var veil := ColorRect.new()
	veil.color = Color(0.03, 0.025, 0.05, 0.85)
	veil.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_pause_menu.add_child(veil)
	veil.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(_pause_menu, Rect2(390, 200, 500, 510))
	var pause_title := _label(_pause_menu, "episode.title", Rect2(420, 233, 440, 64), 25)
	pause_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_button(_pause_menu, "episode.ui.resume", Rect2(435, 318, 410, 54), _toggle_pause)
	_button(_pause_menu, "episode.ui.restart", Rect2(435, 388, 410, 54), _restart)
	_button(_pause_menu, "episode.ui.lab", Rect2(435, 458, 410, 54), func() -> void: navigate.emit("game:presentation_lab"))
	_button(_pause_menu, "episode.ui.command_link", Rect2(435, 528, 410, 54), func() -> void: navigate.emit("game:command_link"))
	_button(_pause_menu, "ui.language_target", Rect2(435, 610, 410, 46), func() -> void: set_language("ko" if get_language() == "en" else "en"))


func _on_scene_input(event: InputEvent) -> void:
	var clicked: bool = event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed
	var touched: bool = event is InputEventScreenTouch and event.pressed
	if clicked or touched:
		accept_event()
		if current_beat().get("type") == "contact" and _reveal.sample()["phase"] == "holding":
			_try_contact(event.position)
		else:
			_next()


func _edge_gradient(parent: Node, node_name: String, rect: Rect2, top: bool) -> void:
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.5, 1.0])
	var clear := Color(0.045, 0.03, 0.065, 0.0)
	var middle := Color(0.045, 0.03, 0.065, 0.67)
	var edge := Color(0.045, 0.03, 0.065, 0.97)
	gradient.colors = PackedColorArray([edge, middle, clear] if top else [clear, middle, edge])
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.width = 2
	texture.height = 512
	texture.fill_from = Vector2(0, 0)
	texture.fill_to = Vector2(0, 1)
	var node := TextureRect.new()
	node.name = node_name
	node.texture = texture
	node.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	node.position = rect.position
	node.size = rect.size
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(node)


func _indicator(parent: Node, point: Vector2) -> Control:
	var node := Panel.new()
	node.position = point
	node.size = Vector2(8, 8)
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = ACCENT
	style.set_corner_radius_all(4)
	node.add_theme_stylebox_override("panel", style)
	parent.add_child(node)
	return node


func _container(parent: Node) -> Control:
	var node := Control.new()
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(node)
	node.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return node


func _panel(parent: Node, rect: Rect2, fill: Color = Color(0.075, 0.065, 0.10, 0.95)) -> void:
	var node := Panel.new()
	node.position = rect.position
	node.size = rect.size
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = Color("76616b")
	style.set_border_width_all(1)
	style.set_corner_radius_all(5)
	node.add_theme_stylebox_override("panel", style)
	parent.add_child(node)


func _label(parent: Node, key: String, rect: Rect2, font_size: int) -> Label:
	var node := Label.new()
	node.position = rect.position
	node.size = rect.size
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	node.add_theme_font_size_override("font_size", font_size)
	node.add_theme_color_override("font_color", INK)
	if not key.is_empty():
		node.text = _text(key)
		_ui_bindings.append({"node": node, "key": key})
	parent.add_child(node)
	return node


func _button(parent: Node, key: String, rect: Rect2, action: Callable = Callable()) -> Button:
	var node := Button.new()
	node.text = _text(key) if not key.is_empty() else ""
	node.position = rect.position
	node.size = rect.size
	node.add_theme_font_size_override("font_size", 17)
	node.add_theme_color_override("font_color", INK)
	node.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	for state in ["normal", "hover", "pressed", "focus"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("52404d") if state in ["hover", "pressed"] else Color("302a38")
		style.border_color = ACCENT if state in ["focus", "hover"] else Color("76616b")
		style.set_border_width_all(1)
		style.set_corner_radius_all(5)
		node.add_theme_stylebox_override(state, style)
	node.pressed.connect(func() -> void:
		get_viewport().gui_release_focus()
		if action.is_valid(): action.call())
	if not key.is_empty(): _ui_bindings.append({"node": node, "key": key})
	parent.add_child(node)
	return node
