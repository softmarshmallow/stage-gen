extends Control

## Command Link's concrete presenter. The host chooses imported project content
## or an external directory without changing story, geometry or art bindings.

signal navigate(route_id: String)

@export var standalone_checks := false
@export var actor_focus_preset := "none"
@export var manpu_animation_preset := "none"
@export var character_exit_preset := "silhouette_fade"

const HOLOGRAM_SHADER = preload("res://addons/game_presentation/effects/shaders/character_hologram.gdshader")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const ACTOR_OVERLAY_SCRIPT = preload("res://presentation/actor_overlay.gd")
const ACTOR_FOCUS_SCRIPT = preload("res://addons/game_presentation/actors/actor_focus.gd")
const ACTOR_FOCUS_CATALOG := "res://addons/game_presentation/actors/presets/focus.json"
const MANPU_ANIMATION_SCRIPT = preload("res://addons/game_presentation/actors/manpu_animation.gd")
const MANPU_ANIMATION_CATALOG := "res://addons/game_presentation/actors/presets/manpu.json"
const CHARACTER_EXIT_SCRIPT = preload("res://addons/game_presentation/actors/character_exit.gd")
const CHARACTER_EXIT_CATALOG := "res://addons/game_presentation/actors/presets/exit.json"
const ESTABLISHING_SHOT_SCRIPT = preload("res://addons/game_presentation/camera/establishing_shot.gd")
const DIALOGUE_CAMERA_SCRIPT = preload("res://addons/game_presentation/camera/dialogue_camera.gd")
const POINT_CONTACT_SCRIPT = preload("res://addons/game_presentation/interaction/point_contact.gd")
const LOCATION_FLARE_SHADER = preload("res://addons/game_presentation/effects/shaders/location_lens_flare.gdshader")
const TACTICAL_THEME = preload("res://presentation/ui/tactical_theme.gd")
const PAPER = TACTICAL_THEME.TEXT
const MUTED = TACTICAL_THEME.MUTED
const WARM = TACTICAL_THEME.ACCENT
const STAGE = TACTICAL_THEME.BG
const DESIGN_SIZE := Vector2(1280, 900)
const WINDOW_TEST_SIZES := [Vector2i(1280, 900), Vector2i(640, 450), Vector2i(720, 900), Vector2i(1440, 900), Vector2i(1920, 1350)]
const MANPU_ACTOR_HEIGHT_RATIO := 0.10
const REACTION_SECONDS := 1.5
const LOCATION_TITLE_FADE_IN := 0.35
const LOCATION_TITLE_HOLD := 2.4
const LOCATION_TITLE_FADE_OUT := 0.7
const LOCATION_TITLE_SECONDS := LOCATION_TITLE_FADE_IN + LOCATION_TITLE_HOLD + LOCATION_TITLE_FADE_OUT
const LOCATION_HEADER_SETTLE_SECONDS := LOCATION_TITLE_SECONDS + 0.25
const MODES := ["full_body", "reach_out", "dialogue", "manpu_gallery"]
const STAGE_PROFILE_SCRIPT = preload("res://presentation/stage_profile.gd")
# Roots must supply this before add_child; the renderer never chooses a game.
var stage_profile: STAGE_PROFILE_SCRIPT

var _actor_nodes: Dictionary = {}
var _actor_focus = ACTOR_FOCUS_SCRIPT.new()
var _manpu_animation = MANPU_ANIMATION_SCRIPT.new()
var _character_exit = CHARACTER_EXIT_SCRIPT.new()
var _establishing = ESTABLISHING_SHOT_SCRIPT.new()
var _dialogue_camera = DIALOGUE_CAMERA_SCRIPT.new()
var _contact = POINT_CONTACT_SCRIPT.new()
var _establishing_hidden_labels: Dictionary = {}
var _location_flare: ColorRect
var _location_flare_material: ShaderMaterial
var _actor_materials: Dictionary = {}
var _character_effects: Dictionary = {}
var _effect_target := ""
var _actor_overlay: Control
var _effect_target_button: Button
var _effect_toggle_button: Button
var _effect_strength_slider: HSlider
var _effect_strength_label: Label
var _textures: Dictionary = {}
var _images: Dictionary = {}
var _manpu_catalog: Dictionary = {}
var _manpu_textures: Dictionary = {}
var _locations: Dictionary = {}
var _location_textures: Dictionary = {}
var _location_rng := RandomNumberGenerator.new()
var _location_id := ""
var _location_title_elapsed := 0.0
var _load_errors: Array[String] = []
var _touch_point := Vector2(0.5, 0.5)
var _touch_radius := 0.034
var _layout_loaded := false
var _mode := "full_body"
var _dialogue_index := 0
var _manual_closed := false
var _natural_blink := true
var _blink_remaining := 0.0
var _blink_wait := 3.8
var _blink_cycle := 0
var _elapsed := 0.0
var _entry := 0.0
var _reaction := 0.0
var _connected: bool:
	get:
		return _contact.is_confirmed()
	set(value):
		_contact.reset(value)
var _show_hotspot := false
var _capturing := false
var _capture_frozen := false
var _pointer := Vector2(-1000.0, -1000.0)
var _title: Label
var _subtitle: Label
var _location_title: Label
var _location_detail: Label
var _line: Label
var _speaker: Label
var _hint: Label
var _footer: Label
var _full_button: Button
var _reach_button: Button
var _dialogue_button: Button
var _manpu_button: Button
var _next_button: Button
var _blink_button: Button
var _auto_button: Button
var _restart_button: Button
var _scene_button: Button
var _options: Dictionary = {}


func _ready() -> void:
	if stage_profile == null:
		_load_errors.append("A game root must supply stage_profile before the stage enters the tree.")
		process_mode = Node.PROCESS_MODE_DISABLED
		return
	_load_errors.append_array(stage_profile.validation_errors())
	if not _load_errors.is_empty():
		process_mode = Node.PROCESS_MODE_DISABLED
		return
	_options = _arguments()
	theme = TACTICAL_THEME.build()
	get_window().min_size = Vector2i(320, 225)
	mouse_filter = Control.MOUSE_FILTER_STOP
	# The detailed standing sprites are drawn at a fraction of their source size.
	# Mipmaps keep thin hair and metallic edges from sparkling when downscaled.
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_load_assets()
	_load_manpu()
	_load_locations()
	var actor_ids: Array[String] = []
	for actor: Dictionary in stage_profile.actors:
		actor_ids.append(String(actor["id"]))
	if not actor_ids.is_empty():
		_load_errors.append_array(_actor_focus.initialize(actor_ids, ACTOR_FOCUS_CATALOG))
		_load_errors.append_array(_character_exit.initialize(actor_ids, CHARACTER_EXIT_CATALOG))
	if _character_exit.initialized:
		_load_errors.append_array(_character_exit.configure(character_exit_preset))
	if standalone_checks:
		actor_focus_preset = "listener_dim"
	if _actor_focus.initialized:
		_load_errors.append_array(_actor_focus.configure(actor_focus_preset))
	_load_errors.append_array(_manpu_animation.initialize(MANPU_ANIMATION_CATALOG))
	if _manpu_animation.initialized:
		_load_errors.append_array(_manpu_animation.configure(manpu_animation_preset))
	for beat: Dictionary in stage_profile.dialogue:
		_load_errors.append_array(_manpu_cue_errors(beat.get("manpu", [])))
	_build_establishing_layer()
	_build_character_layers()
	_reset_character_effects()
	_build_interface()
	_apply_interface_typography()
	_location_rng.randomize()
	var opening_location := String(_options.get("location", ""))
	_select_location(opening_location if _locations.has(opening_location) else _random_location_id(), true)
	var opening_mode := String(_options.get("mode", "full_body"))
	if MODES.has(opening_mode):
		_mode = opening_mode
	_configure_route()
	resized.connect(_layout_interface)
	_layout_interface()
	_update_interface()
	if standalone_checks and _options.has("validate"):
		call_deferred("_validate_and_quit")
	elif standalone_checks and (_options.has("capture-state") or _options.has("capture-all")):
		_capturing = true
		call_deferred("_capture_requested")


## Routes choose their opening state after all shared assets and UI exist.
func _configure_route() -> void:
	pass


func _current_beat() -> Dictionary:
	return stage_profile.dialogue[_dialogue_index] if not stage_profile.dialogue.is_empty() else {"speaker": "", "line": ""}


func _can_use_dialogue_camera() -> bool:
	return _mode == "dialogue" and not is_establishing()


func focus_dialogue_camera(actor_id: String, zoom: float = 2.0, duration_seconds: float = 0.7) -> Array[String]:
	if not _can_use_dialogue_camera():
		return ["Dialogue camera focus is unavailable during this scene presentation."]
	var index := _dialogue_actor_index(actor_id)
	if index < 0 or not _actor_is_present(actor_id):
		return ["Dialogue camera focus requires a present actor: " + actor_id]
	if not is_finite(zoom):
		return ["Dialogue camera zoom must be finite."]
	zoom = clampf(zoom, 1.0, DIALOGUE_CAMERA_SCRIPT.MAX_ZOOM)
	var rect := _posed_dialogue_rect(DESIGN_SIZE, index)
	var eyes: Vector2 = rect.position + rect.size * stage_profile.dialogue_eye_anchors[actor_id]
	var head_top := rect.position.y + rect.size.y * float(stage_profile.dialogue_head_top[actor_id])
	# Center the eyes horizontally. At strong close-ups, leave the authored
	# upper-hair boundary below the fixed header rather than cutting it away.
	var portrait_y := lerpf(260.0, 420.0, clampf((zoom - 1.0) / 3.0, 0.0, 1.0))
	var anchor := Vector2(DESIGN_SIZE.x * 0.5, maxf(portrait_y, 126.0 + (eyes.y - head_top) * zoom))
	var errors: Array[String] = _dialogue_camera.focus(actor_id, eyes, anchor, zoom, duration_seconds)
	if errors.is_empty():
		_update_character_layers()
		queue_redraw()
	return errors


func wide_dialogue_camera(duration_seconds: float = 0.7) -> Array[String]:
	var errors: Array[String] = _dialogue_camera.wide(duration_seconds)
	if errors.is_empty():
		_update_character_layers()
		queue_redraw()
	return errors


func clear_dialogue_camera() -> void:
	_dialogue_camera.clear()
	_update_character_layers()
	queue_redraw()


func dialogue_camera_sample() -> Dictionary:
	return _dialogue_camera.sample() if _can_use_dialogue_camera() else DIALOGUE_CAMERA_SCRIPT.IDENTITY.duplicate()


func is_dialogue_camera_moving() -> bool:
	return _can_use_dialogue_camera() and _dialogue_camera.is_moving()


func save_dialogue_camera() -> Dictionary:
	return _dialogue_camera.get_state()


func restore_dialogue_camera(saved: Dictionary) -> Array[String]:
	var candidate = DIALOGUE_CAMERA_SCRIPT.new()
	var errors: Array[String] = candidate.restore(saved)
	if not errors.is_empty():
		return errors
	if not _location_textures.has(_location_id):
		return ["Cannot restore a dialogue camera without a loaded location."]
	var background: Texture2D = _location_textures[_location_id]
	var bounds := _background_rect(DESIGN_SIZE, background.get_size())
	var stored: Array = saved["background_rect"]
	var saved_bounds := Rect2(float(stored[0]), float(stored[1]), float(stored[2]), float(stored[3]))
	if not bounds.is_equal_approx(saved_bounds) or not Vector2(float(saved["viewport_size"][0]), float(saved["viewport_size"][1])).is_equal_approx(DESIGN_SIZE):
		return ["Saved dialogue camera bounds do not match this location and design canvas."]
	if not candidate.focus_id.is_empty() and (_dialogue_actor_index(candidate.focus_id) < 0 or not _actor_is_present(candidate.focus_id)):
		return ["Saved dialogue camera names an unavailable actor."]
	if not _can_use_dialogue_camera() and (candidate.sample() != DIALOGUE_CAMERA_SCRIPT.IDENTITY or candidate.is_moving() or not candidate.focus_id.is_empty()):
		return ["A focused dialogue camera cannot overlap this scene presentation."]
	_dialogue_camera = candidate
	_update_character_layers()
	queue_redraw()
	return errors


func _dialogue_camera_rect(rect: Rect2) -> Rect2:
	var camera: Dictionary = dialogue_camera_sample()
	var zoom := float(camera["zoom"])
	return Rect2(rect.position * zoom + Vector2(float(camera["offset_x"]), float(camera["offset_y"])), rect.size * zoom)


func start_establishing(location_id: String, overrides: Dictionary = {}) -> Array[String]:
	if not _locations.has(location_id):
		return ["Unknown establishing-shot location: " + location_id]
	var profile: Variant = _locations[location_id].get("establishing_shot", {})
	if not (profile is Dictionary):
		return ["The location establishing_shot profile must be an object."]
	var settings: Dictionary = profile.duplicate(true)
	settings.merge(overrides, true)
	# Validate on a temporary instance before selecting scenery or hiding UI.
	var candidate = ESTABLISHING_SHOT_SCRIPT.new()
	var errors: Array[String] = candidate.configure(_establishing.get_settings())
	errors.append_array(candidate.start(location_id, settings))
	if not errors.is_empty():
		return errors
	clear_dialogue_camera()
	_select_location(location_id, true)
	_establishing = candidate
	_entry = 0.0
	_reaction = 0.0
	_actor_focus.clear()
	_manpu_animation.clear()
	_update_character_layers()
	queue_redraw()
	return errors


func is_establishing() -> bool:
	return _establishing.is_active()


func skip_establishing() -> void:
	if not is_establishing():
		return
	_establishing.skip()
	_finish_establishing()
	_update_interface()
	queue_redraw()


func save_establishing() -> Dictionary:
	return _establishing.get_state()


func establishing_sample() -> Dictionary:
	return _establishing.sample()


func restore_establishing(saved: Dictionary) -> Array[String]:
	var candidate = ESTABLISHING_SHOT_SCRIPT.new()
	var errors: Array[String] = candidate.restore(saved)
	if not errors.is_empty():
		return errors
	var location_id := String(saved["location_id"])
	if not location_id.is_empty() and not _locations.has(location_id):
		return ["Saved establishing shot names an unknown location: " + location_id]
	_restore_establishing_labels()
	if not location_id.is_empty():
		_select_location(location_id)
	_establishing = candidate
	_entry = 0.0 if is_establishing() else 1.0
	if is_establishing():
		_location_title_elapsed = minf(float(saved["elapsed"]), LOCATION_TITLE_FADE_IN + LOCATION_TITLE_HOLD)
		_actor_focus.clear()
		_manpu_animation.clear()
	_update_character_layers()
	_update_location_title()
	queue_redraw()
	return errors


func _finish_establishing() -> void:
	_entry = 0.0
	_restore_establishing_labels()


func _restore_establishing_labels() -> void:
	for label: Label in _establishing_hidden_labels:
		if is_instance_valid(label):
			label.visible = bool(_establishing_hidden_labels[label])
	_establishing_hidden_labels.clear()


func _update_establishing_visibility() -> void:
	if not is_establishing():
		return
	for label: Label in [_line, _speaker, _hint, _footer]:
		if label == null:
			continue
		if not _establishing_hidden_labels.has(label):
			_establishing_hidden_labels[label] = label.visible
		label.visible = false


func _build_establishing_layer() -> void:
	_location_flare = ColorRect.new()
	_location_flare.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_location_flare_material = ShaderMaterial.new()
	_location_flare_material.shader = LOCATION_FLARE_SHADER
	_location_flare.material = _location_flare_material
	_location_flare.visible = false
	add_child(_location_flare)


func _update_location_flare() -> void:
	if _location_flare == null:
		return
	var shot: Dictionary = establishing_sample()
	_location_flare.visible = is_establishing() and float(shot["flare_strength"]) > 0.0
	_location_flare.size = size
	if not _location_flare.visible or not _location_textures.has(_location_id):
		return
	var background: Texture2D = _location_textures[_location_id]
	var rect := _presented_background_rect(size, background.get_size())
	var source: Array = shot["flare_source_uv"]
	var source_position := rect.position + rect.size * Vector2(float(source[0]), float(source[1]))
	_location_flare_material.set_shader_parameter("light_position", source_position / size)
	_location_flare_material.set_shader_parameter("strength", float(shot["flare_strength"]))
	_location_flare_material.set_shader_parameter("aspect_ratio", size.x / size.y)


func set_actor_focus_preset(preset_id: String) -> Array[String]:
	var errors: Array[String] = _actor_focus.configure(preset_id)
	if errors.is_empty():
		actor_focus_preset = preset_id
		_update_character_layers()
	return errors


func _sync_actor_focus(animate: bool = true) -> void:
	if not _actor_focus.initialized:
		return
	if _mode != "dialogue" or is_establishing():
		_actor_focus.clear()
		return
	var focus_id := ""
	if _mode == "dialogue":
		var speaker_name := String(_current_beat().get("speaker", ""))
		for actor: Dictionary in stage_profile.actors:
			if actor["name"] == speaker_name:
				focus_id = actor["id"]
				break
	_actor_focus.set_focus(focus_id, animate)


func set_manpu_animation_preset(preset_id: String) -> Array[String]:
	var errors: Array[String] = _manpu_animation.configure(preset_id)
	if errors.is_empty():
		manpu_animation_preset = preset_id
		_update_character_layers()
	return errors


## This concrete presenter attaches events to visible dialogue actors. Other
## hosts can use the same event controller with their own world coordinates.
func emit_manpu(actor: String, id: String, preset: String = "sigh_puff") -> Dictionary:
	var errors := _manpu_cue_errors([{"actor": actor, "id": id}])
	if _mode != "dialogue" or not _actor_is_present(actor):
		errors.append("This presenter requires a visible dialogue actor for one-shot manpu.")
	if not errors.is_empty(): return {"errors": errors, "instance_id": -1}
	var result: Dictionary = _manpu_animation.emit_one_shot(actor, id, preset)
	_update_character_layers()
	return result


func _sync_manpu_animation(animate: bool = true) -> void:
	if not _manpu_animation.initialized:
		return
	if _mode != "dialogue" or is_establishing():
		_manpu_animation.clear()
		return
	var cues := _presented_manpu_cues()
	var errors := _manpu_cue_errors(cues)
	if errors.is_empty(): errors.append_array(_manpu_animation.sync(cues, animate))
	for issue: String in errors:
		if not _load_errors.has(issue): _load_errors.append(issue)
	if not errors.is_empty(): return
	for event: Dictionary in _manpu_animation.one_shots():
		if not _actor_is_present(str(event["actor"])):
			_manpu_animation.cancel_one_shots(str(event["actor"]))


func _replay_manpu_animation(actor: String = "", id: String = "") -> void:
	_manpu_animation.replay(actor, id)
	_update_character_layers()


func set_character_exit_preset(preset_id: String) -> Array[String]:
	var errors: Array[String] = _character_exit.configure(preset_id)
	if errors.is_empty():
		character_exit_preset = preset_id
	return errors


func exit_actor(actor_id: String) -> Array[String]:
	var errors: Array[String] = _character_exit.exit_actor(actor_id)
	if errors.is_empty() and actor_id == stage_profile.contact_actor_id and _mode == "reach_out":
		_connected = false
		_reaction = 0.0
	_update_character_layers()
	return errors


func show_actor(actor_id: String) -> Array[String]:
	var errors: Array[String] = _character_exit.show_actor(actor_id)
	_update_character_layers()
	return errors


func _actor_is_present(actor_id: String) -> bool:
	return not is_establishing() and _character_exit.is_visible(actor_id) and not _character_exit.is_exiting(actor_id)


## A dedicated choreography route can supply presence and color samples while
## keeping texture, focus, material, and overlay composition in this stage.
func _actor_is_visible(actor_id: String) -> bool:
	return _character_exit.is_visible(actor_id)


func _actor_visual_sample(actor_id: String) -> Dictionary:
	return _character_exit.sample(actor_id)


func _load_assets() -> void:
	for key: String in stage_profile.asset_paths:
		var path: String = stage_profile.asset_paths[key]
		var picture := _load_content_image(path, "Actor image " + key)
		if picture == null:
			continue
		_images[key] = picture
		picture.generate_mipmaps()
		_textures[key] = ImageTexture.create_from_image(picture)
	if stage_profile.contact_actor_id.is_empty():
		return
	var parsed: Variant = _read_content_json(stage_profile.contact_layout_path)
	if parsed is Dictionary:
		var point: Variant = parsed.get("touch_point")
		var radius: Variant = parsed.get("touch_radius")
		if point is Array and point.size() == 2 and (radius is float or radius is int):
			if (point[0] is float or point[0] is int) and (point[1] is float or point[1] is int):
				_touch_point = Vector2(float(point[0]), float(point[1]))
				_touch_radius = float(radius)
				_layout_loaded = _touch_point.is_finite() and is_finite(_touch_radius) and _touch_radius > 0.0
	if not _layout_loaded:
		_load_errors.append("Missing fingertip coordinates for contact actor: " + stage_profile.contact_actor_id)


func _content() -> RefCounted:
	if stage_profile.content_loader == null:
		stage_profile.content_loader = LOCAL_CONTENT.new()
	return stage_profile.content_loader


func _read_content_json(path: String) -> Variant:
	# Historical project bindings are interpreted by the example, not the SDK.
	var result: Dictionary = _content().read_json(path.trim_prefix("res://"))
	_load_errors.append_array(result.errors)
	return result.value


func _load_content_image(path: String, label: String) -> Image:
	var result: Dictionary = _content().load_texture(path.trim_prefix("res://"), true)
	for issue: String in result.errors:
		_load_errors.append(label + ": " + issue)
	var texture: Texture2D = result.resource
	return texture.get_image() if texture != null else null


func _load_manpu() -> void:
	if stage_profile.manpu_catalog_path.is_empty():
		return
	var parsed: Variant = _read_content_json(stage_profile.manpu_catalog_path)
	if not (parsed is Dictionary) or not (parsed.get("manpu") is Array):
		_load_errors.append("The manpu catalog must contain a manpu array.")
		return
	for entry: Variant in parsed["manpu"]:
		if not (entry is Dictionary):
			_load_errors.append("A manpu catalog entry is not a record.")
			continue
		var id := String(entry.get("id", ""))
		var path := String(entry.get("file", ""))
		if not stage_profile.manpu_ids.has(id) or _manpu_catalog.has(id):
			_load_errors.append("Unknown or duplicate manpu: " + id)
			continue
		var picture := _load_content_image(path, "Manpu " + id)
		if picture == null:
			continue
		if picture.get_width() != picture.get_height():
			_load_errors.append("The manpu image must have a square canvas: " + id)
			continue
		picture.generate_mipmaps()
		_manpu_catalog[id] = entry
		_manpu_textures[id] = ImageTexture.create_from_image(picture)
	for id: String in stage_profile.manpu_ids:
		if not _manpu_textures.has(id):
			_load_errors.append("The manpu catalog does not provide " + id)


func _load_locations() -> void:
	if stage_profile.location_catalog_path.is_empty():
		return
	var parsed: Variant = _read_content_json(stage_profile.location_catalog_path)
	if not (parsed is Dictionary) or not (parsed.get("locations") is Array):
		_load_errors.append("The location catalog must contain a locations array.")
		return
	for entry: Variant in parsed["locations"]:
		if not (entry is Dictionary):
			_load_errors.append("A location catalog entry is not a record.")
			continue
		var id := String(entry.get("id", ""))
		var path := String(entry.get("background", ""))
		if not stage_profile.location_ids.has(id) or _locations.has(id):
			_load_errors.append("Unknown or duplicate location: " + id)
			continue
		if String(entry.get("name", "")).is_empty() or String(entry.get("detail", "")).is_empty():
			_load_errors.append("A location needs its name and detail: " + id)
			continue
		var picture := _load_content_image(path, "Location " + id)
		if picture == null:
			continue
		if picture.detect_alpha() != Image.ALPHA_NONE:
			_load_errors.append("A location background must be opaque: " + id)
			continue
		picture.generate_mipmaps()
		_locations[id] = entry
		_location_textures[id] = ImageTexture.create_from_image(picture)
	for id: String in stage_profile.location_ids:
		if not _locations.has(id):
			_load_errors.append("The location catalog does not provide " + id)


func _random_location_id(exclude_current: bool = false) -> String:
	var choices: Array[String] = []
	for id: String in stage_profile.location_ids:
		if _locations.has(id) and (not exclude_current or id != _location_id):
			choices.append(id)
	return choices[_location_rng.randi_range(0, choices.size() - 1)] if not choices.is_empty() else _location_id


func _select_location(id: String, announce_entry: bool = false) -> void:
	if not _locations.has(id) or (id == _location_id and not announce_entry):
		return
	if id != _location_id:
		_establishing.clear()
		_restore_establishing_labels()
	if id != _location_id or not _dialogue_camera.initialized:
		var background: Texture2D = _location_textures[id]
		_load_errors.append_array(_dialogue_camera.initialize(DESIGN_SIZE, _background_rect(DESIGN_SIZE, background.get_size())))
	_location_id = id
	_location_title_elapsed = 0.0
	_location_title.text = String(_locations[id]["name"])
	_location_detail.text = String(_locations[id]["detail"])
	_subtitle.text = String(_locations[id]["name"])
	_update_location_title()
	queue_redraw()


func _change_scene() -> void:
	# Scenery is independent of the current presentation mode and dialogue beat.
	_select_location(_random_location_id(true))


func _location_title_opacity() -> float:
	if _location_title_elapsed < LOCATION_TITLE_FADE_IN:
		return smoothstep(0.0, LOCATION_TITLE_FADE_IN, _location_title_elapsed)
	return 1.0 - smoothstep(LOCATION_TITLE_FADE_IN + LOCATION_TITLE_HOLD,
		LOCATION_TITLE_SECONDS, _location_title_elapsed)


func _update_location_title() -> void:
	var opacity := _location_title_opacity() if not _location_id.is_empty() else 0.0
	_location_title.modulate.a = opacity
	_location_detail.modulate.a = opacity
	# Restore the quiet header only after the location title has fully faded.
	# Crossfading two different strings in the same rectangle makes both unreadable.
	var settled_opacity := smoothstep(LOCATION_TITLE_SECONDS, LOCATION_HEADER_SETTLE_SECONDS, _location_title_elapsed)
	if _location_id.is_empty():
		settled_opacity = 1.0
	_title.modulate.a = settled_opacity
	_subtitle.modulate.a = settled_opacity


func _background_rect(viewport_size: Vector2, image_size: Vector2) -> Rect2:
	var factor := maxf(viewport_size.x / image_size.x, viewport_size.y / image_size.y)
	var drawn_size := image_size * factor
	return Rect2((viewport_size - drawn_size) * 0.5, drawn_size)


func _presented_background_rect(viewport_size: Vector2, image_size: Vector2) -> Rect2:
	var base := _background_rect(viewport_size, image_size)
	var shot: Dictionary = establishing_sample()
	var extent := base.size * float(shot["zoom"])
	var margin := (extent - viewport_size) * 0.5
	var offset := Vector2(clampf(float(shot["pan_x"]), -margin.x, margin.x), 0.0)
	return _dialogue_camera_rect(Rect2((viewport_size - extent) * 0.5 + offset, extent))


func _draw_location_background() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), STAGE)
	if _location_textures.has(_location_id):
		var background: Texture2D = _location_textures[_location_id]
		draw_texture_rect(background, _presented_background_rect(size, background.get_size()), false)
	# Keep the place visible while easing its contrast behind faces and marks.
	var veil_opacity := 0.33
	if not String(establishing_sample()["location_id"]).is_empty():
		veil_opacity = lerpf(0.08, 0.33, smoothstep(0.0, 1.0, _entry))
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.035, 0.055, 0.075, veil_opacity))
	if _mode == "manpu_gallery":
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.035, 0.055, 0.075, 0.42))
	# Fixed interface chrome is drawn independently of the scene camera.
	draw_rect(Rect2(0, 0, size.x, 98), Color(0.035, 0.055, 0.073, 0.94))
	draw_line(Vector2(24, 98), Vector2(size.x - 24, 98), Color("43515a"), 1.0)
	draw_rect(Rect2(24, 25, 3, 53), WARM)
	draw_rect(Rect2(24, 97, 86, 3), WARM)
	for index in 3:
		var x := size.x - 69 + index * 14
		draw_line(Vector2(x, 91), Vector2(x + 6, 85), Color("65747b"), 1.0, true)
	if _mode != "dialogue" and not is_establishing():
		_draw_dialogue_scrim(self)


func _draw_dialogue_scrim(canvas: CanvasItem) -> void:
	_draw_tactical_panel(canvas, Rect2(20, size.y - 236, size.x - 40, 232),
		Color(0.035, 0.055, 0.073, 0.92), Color("43515a"))
	canvas.draw_rect(Rect2(32, size.y - 236, 72, 3), WARM)
	canvas.draw_line(Vector2(32, size.y - 108), Vector2(size.x - 32, size.y - 108), Color(0.36, 0.44, 0.48, 0.30), 1.0)


## Code-drawn clipped corners; visual geometry never changes Control hit boxes.
func _draw_tactical_panel(canvas: CanvasItem, rect: Rect2, fill: Color, border: Color, cut: float = 12.0) -> void:
	var points := PackedVector2Array([
		rect.position, Vector2(rect.end.x - cut, rect.position.y),
		Vector2(rect.end.x, rect.position.y + cut), rect.end,
		Vector2(rect.position.x + cut, rect.end.y), Vector2(rect.position.x, rect.end.y - cut)])
	canvas.draw_colored_polygon(points, fill)
	points.append(points[0])
	canvas.draw_polyline(points, border, 1.0, true)


func _apply_interface_typography() -> void:
	for heading: Label in [_title, _location_title, _speaker]:
		if heading != null:
			heading.add_theme_font_override("font", TACTICAL_THEME.heading_font())
			heading.uppercase = true


# Each actor has its own material state. The shader only samples that actor's
# PNG; background, manpu, contact feedback, and interface use separate items.
func _build_character_layers() -> void:
	for actor: Dictionary in stage_profile.actors:
		var id := String(actor["id"])
		var sprite := TextureRect.new()
		sprite.name = actor["name"] + "Sprite"
		sprite.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		sprite.stretch_mode = TextureRect.STRETCH_SCALE
		sprite.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(sprite)
		_actor_nodes[id] = sprite
		var effect_material := ShaderMaterial.new()
		effect_material.shader = HOLOGRAM_SHADER
		_actor_materials[id] = effect_material
	_actor_overlay = Control.new()
	_actor_overlay.set_script(ACTOR_OVERLAY_SCRIPT)
	_actor_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_actor_overlay)


func _reset_character_effects() -> void:
	_effect_target = stage_profile.default_hologram_actor_id
	if _effect_target.is_empty() and not stage_profile.actors.is_empty():
		_effect_target = String(stage_profile.actors[0]["id"])
	_character_effects.clear()
	for actor: Dictionary in stage_profile.actors:
		var id := String(actor["id"])
		_character_effects[id] = {"enabled": id == stage_profile.default_hologram_actor_id, "strength": 0.9}


func _cycle_effect_target() -> void:
	if _mode != "dialogue" or stage_profile.actors.is_empty():
		return
	var index := (_dialogue_actor_index(_effect_target) + 1) % stage_profile.actors.size()
	_effect_target = stage_profile.actors[index]["id"]
	_update_interface()


func _toggle_character_effect() -> void:
	if _mode != "dialogue" or not _character_effects.has(_effect_target):
		return
	_character_effects[_effect_target]["enabled"] = not _character_effects[_effect_target]["enabled"]
	_update_interface()


func _set_effect_strength(value: float) -> void:
	if not _character_effects.has(_effect_target):
		return
	_character_effects[_effect_target]["strength"] = clampf(value / 100.0, 0.0, 1.0)
	_effect_strength_label.text = "%d%%" % roundi(value)
	_update_character_layers()


func _update_character_layers() -> void:
	if stage_profile == null:
		return
	if not _can_use_dialogue_camera():
		_dialogue_camera.clear()
	_update_establishing_visibility()
	_update_location_flare()
	_sync_actor_focus()
	_sync_manpu_animation()
	for index in stage_profile.actors.size():
		var actor: Dictionary = stage_profile.actors[index]
		var id := String(actor["id"])
		var sprite: TextureRect = _actor_nodes[id]
		var key := _texture_key() if id == stage_profile.portrait_actor_id else String(actor["texture"])
		if _mode == "reach_out" and id == stage_profile.contact_actor_id:
			key = stage_profile.contact_texture
		var selected := (_mode == "full_body" and id == stage_profile.portrait_actor_id) or (_mode == "reach_out" and id == stage_profile.contact_actor_id)
		sprite.visible = _textures.has(key) and (_mode == "dialogue" or selected)
		sprite.visible = sprite.visible and not is_establishing() and _actor_is_visible(id)
		if not sprite.visible:
			continue
		var rect := _presented_dialogue_rect(size, index) if _mode == "dialogue" else _image_rect(size, _mode)
		if _mode != "dialogue":
			var motion := _actor_visual_sample(id)
			rect.position += rect.size.y * Vector2(float(motion.get("offset_x_ratio", 0.0)), float(motion.get("offset_y_ratio", 0.0)))
		sprite.position = rect.position
		sprite.size = rect.size
		sprite.texture = _textures[key]
		var tint := Color.WHITE
		var focus: Dictionary = _actor_focus.sample(id)
		if _mode == "dialogue":
			var brightness: float = focus["brightness"]
			tint = Color(brightness, brightness, brightness, float(focus["opacity"]))
		tint.a *= smoothstep(0.0, 1.0, _entry)
		var departure: Dictionary = _actor_visual_sample(id)
		# Fade color into black at unchanged silhouette coverage, then fade that
		# silhouette. One source-alpha sample avoids doubled translucent edges.
		var exit_brightness := float(departure["brightness"])
		tint *= Color(exit_brightness, exit_brightness, exit_brightness, float(departure["opacity"]))
		sprite.modulate = tint
		var effect: Dictionary = _character_effects[id]
		var effect_material: ShaderMaterial = _actor_materials[id]
		effect_material.set_shader_parameter("strength", float(effect["strength"]))
		effect_material.set_shader_parameter("effect_time", _elapsed)
		sprite.material = effect_material if effect["enabled"] else null
	if _actor_overlay != null:
		_actor_overlay.size = size
		_actor_overlay.queue_redraw()


func _build_interface() -> void:
	_title = _label(stage_profile.display_title, 27, PAPER)
	_subtitle = _label("A moment, at your own pace.", 13, MUTED)
	_location_title = _label("", 27, PAPER)
	_location_detail = _label("", 13, WARM)
	_line = _label("", 25, PAPER, HORIZONTAL_ALIGNMENT_CENTER)
	_speaker = _label("", 15, WARM, HORIZONTAL_ALIGNMENT_CENTER)
	_hint = _label("", 14, MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	_footer = _label("", 12, MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	_full_button = _button("Full body", func() -> void: _set_mode("full_body"))
	_reach_button = _button("Reach out", func() -> void: _set_mode("reach_out"))
	_dialogue_button = _button("Dialogue", func() -> void: _set_mode("dialogue"))
	_manpu_button = _button("Manpu gallery", func() -> void: _set_mode("manpu_gallery"))
	_next_button = _button("Next →", _advance_dialogue)
	_blink_button = _button("Close eyes", _toggle_eyes)
	_auto_button = _button("Auto blink · on", _toggle_natural_blink)
	_restart_button = _button("Restart", _restart)
	_scene_button = _button("Change scene", _change_scene)
	_effect_target_button = _button("", _cycle_effect_target)
	_effect_toggle_button = _button("", _toggle_character_effect)
	_effect_strength_slider = HSlider.new()
	_effect_strength_slider.min_value = 0.0
	_effect_strength_slider.max_value = 100.0
	_effect_strength_slider.step = 5.0
	_effect_strength_slider.value_changed.connect(_set_effect_strength)
	_effect_strength_slider.tooltip_text = "Character effect strength. Zero restores the original appearance."
	add_child(_effect_strength_slider)
	_effect_strength_label = _label("80%", 13, MUTED)
	_effect_target_button.tooltip_text = "Choose which actor to adjust. Keyboard: T"
	_effect_toggle_button.tooltip_text = "Toggle the selected actor between Normal and Hologram. Keyboard: E"
	_blink_button.tooltip_text = "Open or close her eyes. Keyboard: B"
	_auto_button.tooltip_text = "Allow a gentle automatic blink. Keyboard: N"
	_full_button.tooltip_text = "Full-body view. Keyboard: 1"
	_reach_button.tooltip_text = "Reach-out view. Keyboard: 2"
	_dialogue_button.tooltip_text = "Multi-actor dialogue. Keyboard: 3"
	_manpu_button.tooltip_text = "Static manpu / emanata marks. Keyboard: 4"
	_next_button.tooltip_text = "Next line. Keyboard: Space or Enter"
	_restart_button.tooltip_text = "Begin again. Keyboard: R"
	_scene_button.tooltip_text = "Visit another place. Keyboard: L"


func _label(value: String, font_size: int, colour: Color,
		alignment: HorizontalAlignment = HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var made := Label.new()
	made.text = value
	made.add_theme_font_size_override("font_size", font_size)
	made.add_theme_color_override("font_color", colour)
	made.horizontal_alignment = alignment
	made.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	made.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(made)
	return made


func _button(value: String, pressed: Callable) -> Button:
	var made := Button.new()
	made.text = value
	made.add_theme_font_size_override("font_size", 14)
	made.pressed.connect(pressed)
	add_child(made)
	return made


func _button_style(hovered: bool, selected: bool) -> StyleBoxFlat:
	return TACTICAL_THEME.button_style(hovered, selected) as StyleBoxFlat


func _focus_style() -> StyleBoxFlat:
	return TACTICAL_THEME.focus_style() as StyleBoxFlat


func _layout_interface() -> void:
	if _title == null:
		return
	_title.position = Vector2(32, 22)
	_title.size = Vector2(size.x - 296, 40)
	_title.add_theme_font_size_override("font_size", 27)
	_subtitle.position = Vector2(33, 62)
	_subtitle.size = Vector2(size.x - 297, 24)
	_location_title.position = _title.position
	_location_title.size = _title.size
	_location_title.add_theme_font_size_override("font_size", 27)
	_location_detail.position = _subtitle.position
	_location_detail.size = _subtitle.size
	_restart_button.position = Vector2(size.x - 126, 32)
	_restart_button.size = Vector2(94, 36)
	_scene_button.position = Vector2(size.x - 258, 32)
	_scene_button.size = Vector2(120, 36)
	_line.position = Vector2(32, size.y - 197)
	_line.size = Vector2(size.x - 64, 54)
	_line.add_theme_font_size_override("font_size", 25)
	_speaker.position = Vector2(32, size.y - 222)
	_speaker.size = Vector2(size.x - 64, 25)
	_hint.position = Vector2(32, size.y - 142)
	_hint.size = Vector2(size.x - 64, 30)
	var left := (size.x - 556.0) * 0.5
	for button: Button in [_full_button, _reach_button, _dialogue_button, _manpu_button]:
		button.position = Vector2(left, size.y - 99)
		button.size = Vector2(130.0, 38)
		left += 142.0
	var secondary: Array[Button] = []
	if _mode in ["full_body", "dialogue"]:
		secondary.assign([_blink_button, _auto_button])
	if _mode == "dialogue":
		secondary.append(_next_button)
	var total := 0.0
	for button: Button in secondary:
		total += 136.0 if button == _auto_button else 116.0
	total += maxf(0.0, secondary.size() - 1) * 12.0
	left = (size.x - total) * 0.5
	for button: Button in secondary:
		var width := 136.0 if button == _auto_button else 116.0
		button.position = Vector2(left, size.y - 48)
		button.size = Vector2(width, 32)
		button.add_theme_font_size_override("font_size", 13)
		left += width + 12.0
	var effect_left := (size.x - 470.0) * 0.5
	_effect_target_button.position = Vector2(effect_left, size.y - 139)
	_effect_target_button.size = Vector2(112, 28)
	_effect_toggle_button.position = Vector2(effect_left + 122, size.y - 139)
	_effect_toggle_button.size = Vector2(142, 28)
	_effect_strength_slider.position = Vector2(effect_left + 280, size.y - 136)
	_effect_strength_slider.size = Vector2(130, 22)
	_effect_strength_label.position = Vector2(effect_left + 424, size.y - 139)
	_effect_strength_label.size = Vector2(46, 28)
	_footer.position = Vector2(32, size.y - 46)
	_footer.size = Vector2(size.x - 64, 25)
	_update_character_layers()
	queue_redraw()


func _process(delta: float) -> void:
	if not _capture_frozen:
		_elapsed += delta
		var presentation_delta := delta
		if is_establishing():
			var state: Dictionary = save_establishing()
			var remaining := float(state["active_settings"]["duration_seconds"]) - float(state["elapsed"])
			_establishing.advance(delta)
			_location_title_elapsed = minf(LOCATION_TITLE_FADE_IN + LOCATION_TITLE_HOLD, _location_title_elapsed + minf(delta, remaining))
			presentation_delta = maxf(0.0, delta - remaining)
			if not is_establishing():
				_finish_establishing()
		_actor_focus.advance(presentation_delta)
		_manpu_animation.advance(presentation_delta)
		_character_exit.advance(presentation_delta)
		if _can_use_dialogue_camera():
			_dialogue_camera.advance(presentation_delta)
		else:
			_dialogue_camera.clear()
		_location_title_elapsed = minf(LOCATION_HEADER_SETTLE_SECONDS, _location_title_elapsed + presentation_delta)
		_entry = minf(1.0, _entry + presentation_delta * 2.4)
		_reaction = maxf(0.0, _reaction - delta)
		if _mode in ["full_body", "dialogue"] and _natural_blink and not _manual_closed:
			if _blink_remaining > 0.0:
				_blink_remaining = maxf(0.0, _blink_remaining - delta)
			else:
				_blink_wait -= delta
				if _blink_wait <= 0.0:
					_blink_remaining = 0.14
					_blink_cycle += 1
					_blink_wait = [4.5, 3.4, 5.2, 4.0][_blink_cycle % 4]
	if not _capturing:
		var over := _mode == "reach_out" and _actor_is_present(stage_profile.contact_actor_id) and _inside_hotspot(_pointer, size)
		mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND if over else Control.CURSOR_ARROW
	_update_location_title()
	_update_character_layers()
	queue_redraw()


func _draw() -> void:
	if stage_profile == null:
		return
	_draw_location_background()
	if _reaction > 0.0:
		var strength := sin((_reaction / REACTION_SECONDS) * PI) * 0.055
		draw_rect(Rect2(Vector2.ZERO, size), Color(WARM.r, WARM.g, WARM.b, strength))
	if _mode == "manpu_gallery":
		_draw_manpu_gallery()


func _draw_character_overlay(canvas: CanvasItem) -> void:
	if is_establishing():
		return
	if _mode == "dialogue":
		# Dialogue now covers the actors' legs. Its backing belongs above the
		# sprites and below the labels, so bright clothing cannot obscure text.
		_draw_dialogue_scrim(canvas)
		_draw_manpu(canvas)
	if _mode == "reach_out" and _actor_is_present(stage_profile.contact_actor_id) and _layout_loaded and _textures.has(stage_profile.contact_texture):
		_draw_contact(canvas)
	if _show_hotspot:
		canvas.draw_string(ThemeDB.fallback_font, Vector2(34, 124),
			"H · fingertip target" if _mode == "reach_out" else "H · target appears in reach-out view",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("bacbc9"))


func _dialogue_rect(viewport_size: Vector2, actor_index: int) -> Rect2:
	var key := String(stage_profile.actors[actor_index]["texture"])
	var image_size := Vector2(1024, 1536)
	if _textures.has(key):
		image_size = (_textures[key] as Texture2D).get_size()
	# Authored framing for this fixed canvas: larger cast, slightly lower heads,
	# and legs behind dialogue. Parameterization is deferred in request P19.
	var drawn := image_size * (716.0 / image_size.y)
	var center_x := viewport_size.x * 0.5 + (actor_index - (stage_profile.actors.size() - 1) * 0.5) * 390.0
	return Rect2(Vector2(center_x - drawn.x * 0.5, 146.0), drawn)


func _presented_dialogue_rect(viewport_size: Vector2, actor_index: int) -> Rect2:
	return _dialogue_camera_rect(_posed_dialogue_rect(viewport_size, actor_index))


func _posed_dialogue_rect(viewport_size: Vector2, actor_index: int) -> Rect2:
	var base := _dialogue_rect(viewport_size, actor_index)
	var focus: Dictionary = _actor_focus.sample(String(stage_profile.actors[actor_index]["id"]))
	var drawn := base.size * float(focus["scale"])
	# Focus animation is relative to the authored pose, around its bottom center.
	# Sampling never feeds last frame's transformed rectangle back into layout.
	var origin := Vector2(base.get_center().x - drawn.x * 0.5, base.end.y - drawn.y)
	var departure := _actor_visual_sample(String(stage_profile.actors[actor_index]["id"]))
	origin.x += base.size.y * (float(focus.get("offset_x_ratio", 0.0)) + float(departure.get("offset_x_ratio", 0.0)))
	origin.y += base.size.y * (float(focus["offset_y_ratio"]) + float(departure.get("offset_y_ratio", 0.0)))
	return Rect2(origin, drawn)


func _dialogue_actor_index(id: String) -> int:
	for index in stage_profile.actors.size():
		if stage_profile.actors[index]["id"] == id:
			return index
	return -1


## The current line owns which marks exist. Animation state is independent
## per actor/mark pair and survives while that pair remains in the conversation.
func _active_manpu() -> Array:
	return _current_beat().get("manpu", []) if _mode == "dialogue" else []


func _presented_manpu_cues() -> Array:
	var cues: Array = []
	if is_establishing():
		return cues
	for cue: Dictionary in _active_manpu():
		var actor := String(cue["actor"])
		# An attached reaction leaves with its owner, never floating alone after
		# an exit. Showing the actor again creates a fresh authored introduction.
		if _actor_is_present(actor):
			cues.append(cue)
	return cues


func _manpu_cue_errors(cues: Variant) -> Array[String]:
	var errors: Array[String] = []
	if not (cues is Array):
		errors.append("A dialogue line's manpu cues must be an array.")
		return errors
	for cue: Variant in cues:
		if not (cue is Dictionary):
			errors.append("A manpu cue must name an actor and an id.")
			continue
		var actor := String(cue.get("actor", ""))
		var id := String(cue.get("id", ""))
		if not stage_profile.manpu_head_anchors.has(actor):
			errors.append("A manpu cue names an unknown actor: " + actor)
		if not stage_profile.manpu_ids.has(id) or not _manpu_textures.has(id):
			errors.append("A manpu cue names an unavailable mark: " + id)
		if cue.get("frames", []) is Array:
			for frame_id: Variant in cue.get("frames", []):
				if not _manpu_textures.has(frame_id):
					errors.append("A manpu cue names an unavailable frame: " + str(frame_id))
	return errors


func _manpu_stage(viewport_size: Vector2) -> Rect2:
	return Rect2(Vector2(28, 110), Vector2(viewport_size.x - 56, viewport_size.y - 347))


func _manpu_rect(viewport_size: Vector2, actor: String, id: String) -> Rect2:
	return _dialogue_camera_rect(_manpu_world_rect(viewport_size, actor, id))


func _manpu_world_rect(viewport_size: Vector2, actor: String, id: String) -> Rect2:
	var actor_rect := _posed_dialogue_rect(viewport_size, _dialogue_actor_index(actor))
	var anchor: Vector2 = stage_profile.manpu_head_anchors[actor]
	if id in ["sigh", "sigh_puff"]:
		# The puff sits outside the right cheek, with its tail toward the mouth.
		anchor = Vector2(0.80, 0.12)
	elif id == "gloom_lines":
		anchor = Vector2(0.55, -0.045)
	# In-game punctuation follows the actor's size, never a screen-pixel limit.
	var width := actor_rect.size.y * MANPU_ACTOR_HEIGHT_RATIO
	var center := actor_rect.position + actor_rect.size * anchor
	var stage := _manpu_stage(viewport_size)
	var half := width * 0.5
	if id == "gloom_lines" and center.y - half < stage.position.y:
		# When the actor reaches the stage top, keep this mark beside the brow
		# instead of clamping it downward across the actor's eyes.
		center.x = actor_rect.position.x + actor_rect.size.x * 0.80
	center.x = clampf(center.x, stage.position.x + half, stage.end.x - half)
	center.y = clampf(center.y, stage.position.y + half, stage.end.y - half)
	return Rect2(center - Vector2(half, half), Vector2(width, width))


func _presented_manpu_rect(viewport_size: Vector2, actor: String, id: String) -> Rect2:
	var animation: Dictionary = _manpu_animation.sample(actor, id)
	return _composed_manpu_rect(viewport_size, actor, id, animation)


func _composed_manpu_rect(viewport_size: Vector2, actor: String, id: String, animation: Dictionary) -> Rect2:
	var attached := _manpu_world_rect(viewport_size, actor, id)
	var drawn := attached.size * float(animation["scale"])
	# Local mark motion composes after the owner's transform, around its center.
	var origin := attached.get_center() - drawn * 0.5
	origin.x += attached.size.y * float(animation.get("offset_x_ratio", 0.0))
	origin.y += attached.size.y * float(animation["offset_y_ratio"])
	# Keep its world attachment through the camera crop. Re-clamping in screen
	# space would detach the mark from an actor that has moved offscreen.
	return _dialogue_camera_rect(Rect2(origin, drawn))


func _manpu_color(actor: String, id: String) -> Color:
	var animation: Dictionary = _manpu_animation.sample(actor, id)
	var brightness: float = animation["brightness"]
	return Color(brightness, brightness, brightness,
		float(animation["opacity"]) * smoothstep(0.0, 1.0, _entry))


func _draw_manpu(canvas: CanvasItem) -> void:
	for cue: Dictionary in _presented_manpu_cues():
		var id := String(cue["id"])
		var actor := String(cue["actor"])
		if _manpu_textures.has(id):
			var sample: Dictionary = _manpu_animation.sample(actor, id)
			_draw_manpu_sample(canvas, actor, id, sample)
	for event: Dictionary in _manpu_animation.one_shots():
		var actor := str(event["actor"])
		var id := str(event["id"])
		if not _actor_is_present(actor): continue
		_draw_manpu_sample(canvas, actor, id, event["sample"])


func _draw_manpu_sample(canvas: CanvasItem, actor: String, id: String, sample: Dictionary) -> void:
	var rect := _composed_manpu_rect(size, actor, id, sample)
	var brightness := float(sample["brightness"])
	var color := Color(brightness, brightness, brightness, float(sample["opacity"]) * smoothstep(0.0, 1.0, _entry))
	# The rectangle already includes the world camera. Rotate locally around its
	# projected center, then restore the canvas for the next mark or overlay.
	canvas.draw_set_transform(rect.get_center(), deg_to_rad(float(sample.get("rotation_degrees", 0.0))))
	canvas.draw_texture_rect(_manpu_textures[str(sample.get("sprite_id", id))], Rect2(-rect.size * 0.5, rect.size), false, color)
	canvas.draw_set_transform(Vector2.ZERO)


func _manpu_gallery_cell(viewport_size: Vector2, index: int) -> Rect2:
	var stage := _manpu_stage(viewport_size)
	var gap := 12.0
	var rows := ceili(stage_profile.manpu_ids.size() / 4.0)
	var cell_size := Vector2((stage.size.x - gap * 3.0) / 4.0, (stage.size.y - gap * (rows - 1)) / rows)
	return Rect2(stage.position + Vector2(index % 4, index / 4) * (cell_size + Vector2(gap, gap)), cell_size)


func _draw_manpu_gallery() -> void:
	for index in stage_profile.manpu_ids.size():
		var id: String = stage_profile.manpu_ids[index]
		if not _manpu_textures.has(id):
			continue
		var cell := _manpu_gallery_cell(size, index)
		var style := _button_style(false, false)
		style.bg_color = Color(0.10, 0.15, 0.18, 0.68)
		style.border_color = Color(0.40, 0.48, 0.50, 0.28)
		draw_style_box(style, cell)
		var icon_size := minf(100.0, minf(cell.size.x - 26.0, cell.size.y - 48.0))
		var icon := Rect2(Vector2(cell.position.x + (cell.size.x - icon_size) * 0.5,
			cell.position.y + (cell.size.y - icon_size - 28.0) * 0.5), Vector2(icon_size, icon_size))
		draw_texture_rect(_manpu_textures[id], icon, false, Color.WHITE)
		draw_string(ThemeDB.fallback_font, Vector2(cell.position.x, icon.end.y + 22.0),
			String(_manpu_catalog[id].get("label", id)), HORIZONTAL_ALIGNMENT_CENTER,
			cell.size.x, 14, PAPER)


func _draw_contact(canvas: CanvasItem) -> void:
	var point := _fingertip_center(size)
	var hit_radius := _fingertip_radius(size)
	var hover := _inside_hotspot(_pointer, size)
	var pulse := 0.5 + 0.5 * sin(_elapsed * 2.3)
	var hint_radius := maxf(9.0, hit_radius * 0.57)
	var hint_alpha := (0.36 if hover else 0.19) + pulse * 0.08
	canvas.draw_arc(point, hint_radius, 0.0, TAU, 64, Color(WARM.r, WARM.g, WARM.b, hint_alpha), 1.3, true)
	canvas.draw_circle(point, 2.0, Color(WARM.r, WARM.g, WARM.b, 0.55))
	if _reaction > 0.0:
		var progress := 1.0 - _reaction / REACTION_SECONDS
		for index in 2:
			var phase := clampf((progress - index * 0.18) / 0.82, 0.0, 1.0)
			if phase > 0.0 and phase < 1.0:
				var radius := hint_radius + phase * 90.0
				var alpha := pow(1.0 - phase, 2.0) * 0.9
				canvas.draw_arc(point, radius, 0.0, TAU, 96, Color(WARM.r, WARM.g, WARM.b, alpha), 2.0, true)
		canvas.draw_circle(point, hint_radius * 0.75, Color(WARM.r, WARM.g, WARM.b, (1.0 - progress) * 0.19))
	if _show_hotspot:
		canvas.draw_circle(point, hit_radius, Color(0.44, 0.94, 0.79, 0.10))
		canvas.draw_arc(point, hit_radius, 0.0, TAU, 96, Color(0.44, 0.94, 0.79, 0.8), 1.0, true)
		canvas.draw_line(point - Vector2(7, 0), point + Vector2(7, 0), Color(0.44, 0.94, 0.79, 0.9), 1.0)
		canvas.draw_line(point - Vector2(0, 7), point + Vector2(0, 7), Color(0.44, 0.94, 0.79, 0.9), 1.0)


func _texture_key() -> String:
	if _mode == "reach_out":
		return stage_profile.contact_texture
	if (_manual_closed or _blink_remaining > 0.0) and not stage_profile.portrait_closed_texture.is_empty():
		return stage_profile.portrait_closed_texture
	return stage_profile.portrait_open_texture


## Draw and input share this transform. Coordinates from layout.json refer to
## the original image canvas, including transparent margins.
func _image_rect(viewport_size: Vector2, selected_mode: String) -> Rect2:
	var key := stage_profile.contact_texture if selected_mode == "reach_out" else stage_profile.portrait_open_texture
	var image_size := Vector2(1536, 1024) if selected_mode == "reach_out" else Vector2(1024, 1536)
	if _textures.has(key):
		image_size = (_textures[key] as Texture2D).get_size()
	var available := Rect2(Vector2(28, 112), Vector2(maxf(1, viewport_size.x - 56), maxf(1, viewport_size.y - 341)))
	var scale_factor := minf(available.size.x / image_size.x, available.size.y / image_size.y)
	var drawn_size := image_size * scale_factor
	return Rect2(available.position + (available.size - drawn_size) * 0.5, drawn_size)


func _fingertip_center(viewport_size: Vector2) -> Vector2:
	var rect := _image_rect(viewport_size, "reach_out")
	return rect.position + rect.size * _touch_point


func _fingertip_radius(viewport_size: Vector2) -> float:
	return _image_rect(viewport_size, "reach_out").size.x * _touch_radius


func _inside_hotspot(point: Vector2, viewport_size: Vector2) -> bool:
	return _layout_loaded and POINT_CONTACT_SCRIPT.hit_test(point, _fingertip_center(viewport_size), _fingertip_radius(viewport_size))


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		_pointer = event.position
	elif event is InputEventMouseButton:
		_pointer = event.position
		if event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
			if _connect_at(event.position):
				accept_event()
	elif event is InputEventScreenTouch and event.pressed:
		_pointer = event.position
		if _connect_at(event.position):
			accept_event()


func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_1: _set_mode("full_body")
		KEY_2: _set_mode("reach_out")
		KEY_3: _set_mode("dialogue")
		KEY_4: _set_mode("manpu_gallery")
		KEY_B: _toggle_eyes()
		KEY_N: _toggle_natural_blink()
		KEY_R: _restart()
		KEY_L: _change_scene()
		KEY_T: _cycle_effect_target()
		KEY_E: _toggle_character_effect()
		KEY_H:
			_show_hotspot = not _show_hotspot
			_update_interface()
		_: return
	get_viewport().set_input_as_handled()


## Handle advance before GUI focus can turn Space into a second button click.
## Other keys retain the ordinary buttons' keyboard accessibility.
func _input(event: InputEvent) -> void:
	if _mode != "dialogue" or not (event is InputEventKey):
		return
	if event.pressed and not event.echo and event.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		_advance_dialogue()
		get_viewport().set_input_as_handled()


func _advance_dialogue() -> void:
	if _mode != "dialogue" or not _load_errors.is_empty() or stage_profile.dialogue.is_empty():
		return
	_dialogue_index = (_dialogue_index + 1) % stage_profile.dialogue.size()
	_update_interface()


func _connect_at(point: Vector2) -> bool:
	if _mode != "reach_out" or not _actor_is_present(stage_profile.contact_actor_id) or _entry < 0.8 or not _load_errors.is_empty() or not _inside_hotspot(point, size):
		return false
	if not _contact.confirm_at(point, _fingertip_center(size), _fingertip_radius(size)):
		return false
	_reaction = REACTION_SECONDS
	_update_interface()
	return true


func _set_mode(selected: String) -> void:
	if not MODES.has(selected) or _mode == selected:
		return
	_mode = selected
	_dialogue_index = 0
	_entry = 0.0
	_reaction = 0.0
	_connected = false
	_blink_remaining = 0.0
	_update_interface()


func _toggle_eyes() -> void:
	if not _mode in ["full_body", "dialogue"]:
		return
	_manual_closed = not _manual_closed
	_blink_remaining = 0.0
	_blink_wait = 3.8
	_update_interface()


func _toggle_natural_blink() -> void:
	if not _mode in ["full_body", "dialogue"]:
		return
	_natural_blink = not _natural_blink
	_blink_remaining = 0.0
	_blink_wait = 3.8
	_update_interface()


func _restart() -> void:
	# Restart preserves the original prototype's full-body opening; --mode
	# dialogue selects the demonstration only on launch.
	_mode = "full_body"
	_dialogue_index = 0
	_manual_closed = false
	_natural_blink = true
	_blink_remaining = 0.0
	_blink_wait = 3.8
	_blink_cycle = 0
	_entry = 0.0
	_reaction = 0.0
	_connected = false
	_show_hotspot = false
	_actor_focus.clear()
	_manpu_animation.clear()
	_character_exit.clear()
	_reset_character_effects()
	_select_location(_random_location_id(), true)
	_update_interface()


func _update_interface() -> void:
	if _line == null:
		return
	_full_button.add_theme_stylebox_override("normal", _button_style(false, _mode == "full_body"))
	_reach_button.add_theme_stylebox_override("normal", _button_style(false, _mode == "reach_out"))
	_dialogue_button.add_theme_stylebox_override("normal", _button_style(false, _mode == "dialogue"))
	_manpu_button.add_theme_stylebox_override("normal", _button_style(false, _mode == "manpu_gallery"))
	_blink_button.text = "Open eyes" if _manual_closed else "Close eyes"
	_auto_button.text = "Auto blink · on" if _natural_blink else "Auto blink · off"
	_blink_button.disabled = not _mode in ["full_body", "dialogue"]
	_auto_button.disabled = not _mode in ["full_body", "dialogue"]
	_blink_button.visible = _mode in ["full_body", "dialogue"]
	_auto_button.visible = _mode in ["full_body", "dialogue"]
	_next_button.visible = _mode == "dialogue"
	_next_button.disabled = stage_profile.dialogue.is_empty()
	_next_button.text = "Read again" if _dialogue_index == stage_profile.dialogue.size() - 1 else "Next →"
	_speaker.visible = _mode == "dialogue"
	_speaker.text = String(_current_beat().get("speaker", ""))
	var effect: Dictionary = _character_effects.get(_effect_target, {"enabled": false, "strength": 0.0})
	var actor_index := _dialogue_actor_index(_effect_target)
	_effect_target_button.text = "T · " + String(stage_profile.actors[actor_index]["name"]) if actor_index >= 0 else "No actors"
	_effect_toggle_button.text = "E · Hologram" if effect["enabled"] else "E · Normal"
	_effect_toggle_button.add_theme_stylebox_override("normal", _button_style(false, effect["enabled"]))
	_effect_strength_slider.set_value_no_signal(float(effect["strength"]) * 100.0)
	_effect_strength_slider.editable = effect["enabled"]
	_effect_strength_label.text = "%d%%" % roundi(float(effect["strength"]) * 100.0)
	for control: Control in [_effect_target_button, _effect_toggle_button, _effect_strength_slider, _effect_strength_label]:
		control.visible = _mode == "dialogue" and actor_index >= 0
	_full_button.disabled = stage_profile.portrait_actor_id.is_empty()
	_reach_button.disabled = stage_profile.contact_actor_id.is_empty()
	_hint.visible = _mode != "dialogue"
	if not _load_errors.is_empty():
		_line.text = "The scene is waiting for its artwork."
		_hint.text = " · ".join(_load_errors)
		_hint.add_theme_font_size_override("font_size", 12)
	elif _mode == "full_body":
		_line.text = String(stage_profile.preview_copy.get("standing_line", "Standing pose."))
		_hint.text = String(stage_profile.preview_copy.get("standing_hint", ""))
	elif _mode == "reach_out":
		_line.text = String(stage_profile.preview_copy.get("connected_line", "Contact confirmed.")) if _connected else String(stage_profile.preview_copy.get("contact_line", "Touch the offered fingertip."))
		_hint.text = String(stage_profile.preview_copy.get("connected_hint", "Contact confirmed.")) if _connected else "Touch my fingertip."
	elif _mode == "dialogue":
		_line.text = String(_current_beat().get("line", ""))
		_hint.text = "Space / Enter · read again" if _dialogue_index == stage_profile.dialogue.size() - 1 else "Space / Enter · next line"
	else:
		_line.text = "Small marks. A little more feeling."
		_hint.text = "Manpu / emanata · eight static marks"
	_footer.visible = _mode == "reach_out"
	_footer.text = "Touch target visible · H to hide" if _show_hotspot and _mode == "reach_out" else ""
	_layout_interface()
	queue_redraw()


func _arguments() -> Dictionary:
	var args := OS.get_cmdline_user_args()
	var result := {}
	var index := 0
	while index < args.size():
		var argument := String(args[index])
		if argument.begins_with("--"):
			var key := argument.substr(2)
			if index + 1 < args.size() and not String(args[index + 1]).begins_with("--"):
				result[key] = String(args[index + 1])
				index += 1
			else:
				result[key] = true
		index += 1
	return result


## Input-injection helpers used by the independent QA scripts. Fixture assertions
## and capture scenarios live in qa/legacy_presentation.gd.
func _route_mouse(point: Vector2) -> void:
	_route_window_mouse(get_viewport().get_final_transform() * point)


func _route_window_mouse(point: Vector2) -> void:
	for pressed in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = point
		event.global_position = point
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		get_viewport().push_input(event, false)


func _route_touch(point: Vector2) -> void:
	_route_window_touch(get_viewport().get_final_transform() * point)


func _route_window_touch(point: Vector2) -> void:
	for pressed in [true, false]:
		var event := InputEventScreenTouch.new()
		event.position = point
		event.index = 0
		event.pressed = pressed
		get_viewport().push_input(event, false)


func _route_key(key: Key) -> void:
	for pressed in [true, false]:
		var event := InputEventKey.new()
		event.keycode = key
		event.pressed = pressed
		get_viewport().push_input(event, true)
