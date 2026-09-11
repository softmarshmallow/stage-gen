extends "res://lab/study_host.gd"

## This fixture owns sprite choices, attachment points, layer order and controls.
## The shared burst takes world-space inputs and advances only on this clock.
const BURST = preload("res://addons/game_presentation/effects/particles/sprite_burst.gd")
const IMPACT = preload("res://addons/game_presentation/camera/impact_shake.gd")
const TEXTURES: Array[String] = ["sparkle", "heart", "mixed"]
const PLACEMENTS: Array[String] = ["behind", "around", "front"]
var _burst_back: Control
var _burst_front: Control
var _burst_textures: Dictionary = {}
var _texture_id := "sparkle"
var _placement := "around"
var _count := 16
var _duration := 1.2
var _distance := 245.0
var _zoom := 1.0
var _paused := false
var _elapsed := 0.0
var _world := Transform2D.IDENTITY
var _impact = IMPACT.new()
var _texture_buttons: Dictionary = {}
var _placement_buttons: Dictionary = {}
var _burst_sliders: Dictionary = {}
var _burst_value_labels: Dictionary = {}
var _emit_button: Button
var _pause_button: Button
var _zoom_button: Button
var _shake_button: Button


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	for profile: Dictionary in content.get("guests", []):
		if profile["id"] == "nami":
			_guest_textures["nami"] = _load_texture(profile["path"])
	for background: Dictionary in content.get("backgrounds", []):
		_backgrounds.append(_load_texture(background["path"]))
	var sprite_paths: Dictionary = content.get("sprite_burst", {}).get("sprites", {})
	for texture_id: String in ["sparkle", "heart"]:
		_burst_textures[texture_id] = _load_texture(str(sprite_paths.get(texture_id, "")))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		var extent := _backgrounds[0].get_size()
		extent *= maxf(DESIGN_SIZE.x / extent.x, DESIGN_SIZE.y / extent.y)
		_base_background = Rect2((DESIGN_SIZE - extent) * 0.5, extent)
	_burst_back = BURST.new()
	_burst_back.name = "BurstBehindActor"
	add_child(_burst_back)
	_actor = TextureRect.new()
	_actor.name = "PreparedNamiSprite"
	_actor.texture = _guest_textures.get("nami")
	_actor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_actor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_actor)
	_burst_front = BURST.new()
	_burst_front.name = "BurstInFrontOfActor"
	add_child(_burst_front)
	_build_burst_ui()
	_present_bursts()
	_emit_burst()


func _actor_rect() -> Rect2:
	var texture: Texture2D = _guest_textures.get("nami")
	if texture == null: return Rect2(360, 130, 560, 840)
	var height := 840.0
	var width := height * texture.get_width() / texture.get_height()
	return Rect2(640.0 - width * 0.5, 130.0, width, height)


func _burst_origin() -> Vector2:
	var actor_rect := _actor_rect()
	return actor_rect.position + actor_rect.size * Vector2(0.5, 0.28)


func _selected_textures() -> Array[Texture2D]:
	var result: Array[Texture2D] = []
	if _texture_id == "mixed":
		for texture_id: String in ["sparkle", "heart"]:
			result.append(_burst_textures[texture_id])
	else:
		result.append(_burst_textures[_texture_id])
	return result


func _emit_burst() -> void:
	if not _load_errors.is_empty(): return
	var layer := _burst_back if _placement == "behind" else _burst_front
	# Around starts on a ring outside the torso. Depth is still a host decision.
	var result: Dictionary = layer.emit_burst(_burst_origin(), _selected_textures(), {
		"count": _count, "duration": _duration, "distance": _distance,
		"start_radius": 145.0 if _placement == "around" else 12.0,
		"sprite_size": 44.0, "seed": 73,
	})
	_load_errors.append_array(result["errors"])
	_present_bursts()


func _clear_bursts() -> void:
	_burst_back.clear()
	_burst_front.clear()
	_present_bursts()


func _select_texture(texture_id: String) -> void:
	if texture_id not in TEXTURES: return
	_texture_id = texture_id
	_update_burst_ui()


func _select_placement(placement: String) -> void:
	if placement not in PLACEMENTS: return
	_placement = placement
	_update_burst_ui()


func _set_burst_value(value: float, key: String) -> void:
	match key:
		"count": _count = int(value)
		"duration": _duration = value
		"distance": _distance = value
	_update_burst_ui()


func _toggle_pause() -> void:
	_paused = not _paused
	_update_burst_ui()


func _toggle_zoom() -> void:
	_zoom = 1.2 if _zoom == 1.0 else 1.0
	_present_bursts()


func _play_shake() -> void:
	_load_errors.append_array(_impact.start({"amplitude_x": 24.0, "amplitude_y": 20.0, "duration": 1.4, "seed": 73}))
	_present_bursts()


func _process(delta: float) -> void:
	if _paused or not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0: return
	_elapsed += delta
	_impact.advance(delta)
	_burst_back.advance(delta)
	_burst_front.advance(delta)
	_present_bursts()


func _present_bursts() -> void:
	if _status == null: return
	var center := DESIGN_SIZE * 0.5
	var base := Transform2D(Vector2(_zoom, 0), Vector2(0, _zoom), center * (1.0 - _zoom))
	_world = _impact.compose(base, _base_background, DESIGN_SIZE)
	var actor_rect := _world * _actor_rect()
	_actor.position = actor_rect.position
	_actor.size = actor_rect.size
	_load_errors.append_array(_burst_back.present(_world))
	_load_errors.append_array(_burst_front.present(_world))
	_update_burst_ui()
	queue_redraw()


func burst_state() -> Dictionary:
	return {"texture_id": _texture_id, "placement": _placement, "count": _count,
		"duration": _duration, "distance": _distance, "paused": _paused,
		"elapsed": _elapsed, "zoom": _zoom, "world": _world,
		"impact": _impact.get_state(), "behind": _burst_back.get_state(),
		"front": _burst_front.get_state()}


func _build_burst_ui() -> void:
	_ui = Control.new()
	_ui.name = "SpriteBurstStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(24, 22, 1232, 103), Color("211b28"))
	_label_text("study.burst.title", Rect2(46, 31, 690, 47), 32, INK)
	_label_text("study.burst.description", Rect2(48, 82, 948, 30), 17, MUTED)
	_build_language_picker(Rect2(787, 38, 206, 38))
	_return_button = _button_text("ui.effects_menu", Rect2(1021, 48, 211, 44), func() -> void: navigate.emit("effects_menu"))
	_panel(Rect2(24, 634, 1232, 246), Color("211b28"))
	_label_text("study.burst.texture", Rect2(46, 648, 150, 33), 17, MUTED)
	for index in TEXTURES.size():
		var texture_id := TEXTURES[index]
		var button := _button_text("study.burst." + texture_id, Rect2(195 + index * 160, 644, 148, 39), _select_texture.bind(texture_id))
		button.toggle_mode = true
		_texture_buttons[texture_id] = button
	_label_text("study.burst.placement", Rect2(695, 648, 130, 33), 17, MUTED)
	for index in PLACEMENTS.size():
		var placement := PLACEMENTS[index]
		var button := _button_text("study.burst." + placement, Rect2(824 + index * 137, 644, 130, 39), _select_placement.bind(placement))
		button.toggle_mode = true
		_placement_buttons[placement] = button
	_add_burst_slider("count", Rect2(46, 699, 365, 66), 4.0, 64.0, 1.0, _count)
	_add_burst_slider("duration", Rect2(444, 699, 365, 66), 0.5, 3.0, 0.1, _duration)
	_add_burst_slider("distance", Rect2(842, 699, 365, 66), 60.0, 330.0, 5.0, _distance)
	_emit_button = _button_text("study.burst.emit", Rect2(46, 773, 210, 42), _emit_burst)
	_emit_button.name = "EmitBurst"
	_button_text("study.burst.clear", Rect2(270, 773, 164, 42), _clear_bursts).name = "ClearBursts"
	_pause_button = _button_text("ui.pause", Rect2(448, 773, 164, 42), _toggle_pause)
	_pause_button.name = "PauseBursts"
	_zoom_button = _button("", Rect2(626, 773, 180, 42), _toggle_zoom)
	_zoom_button.name = "ZoomCamera"
	_shake_button = _button_text("study.burst.shake", Rect2(820, 773, 188, 42), _play_shake)
	_shake_button.name = "ShakeCamera"
	_status = _label("", Rect2(1025, 773, 207, 47), 15, MUTED)
	_status.name = "BurstStatus"
	_label_text("study.burst.hint", Rect2(46, 837, 1170, 30), 16, MUTED)


func _add_burst_slider(key: String, rect: Rect2, minimum: float, maximum: float, step: float, value: float) -> void:
	_burst_value_labels[key] = _label("", Rect2(rect.position, Vector2(rect.size.x, 28)), 18, INK)
	var slider := HSlider.new()
	slider.name = key.capitalize() + "Slider"
	slider.position = rect.position + Vector2(0, 32)
	slider.size = Vector2(rect.size.x, 30)
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = step
	slider.value = value
	slider.value_changed.connect(_set_burst_value.bind(key))
	_ui.add_child(slider)
	_burst_sliders[key] = slider


func _update_burst_ui() -> void:
	if _status == null: return
	for texture_id: String in _texture_buttons:
		_texture_buttons[texture_id].set_pressed_no_signal(texture_id == _texture_id)
	for placement: String in _placement_buttons:
		_placement_buttons[placement].set_pressed_no_signal(placement == _placement)
	_burst_value_labels["count"].text = _text("study.burst.count", {"value": _count})
	_burst_value_labels["duration"].text = _text("study.burst.duration", {"value": "%.1f" % _duration})
	_burst_value_labels["distance"].text = _text("study.burst.distance", {"value": int(_distance)})
	_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
	_zoom_button.text = _text("study.burst.zoom", {"value": "%.1f" % _zoom})
	_status.text = _text("study.burst.status", {"count": _burst_back.get_state().size() + _burst_front.get_state().size(), "elapsed": "%.1f" % _elapsed})
	if not _load_errors.is_empty():
		_status.text = "\n".join(_load_errors)
		_emit_button.disabled = true
		_pause_button.disabled = true
		_shake_button.disabled = true


func _refresh_language() -> void:
	_update_burst_ui()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		draw_texture_rect(_backgrounds[0], _world * _base_background, false)


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		_toggle_language()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
	else:
		return
	get_viewport().set_input_as_handled()
