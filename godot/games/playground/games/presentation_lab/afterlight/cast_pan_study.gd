extends "res://games/presentation_lab/afterlight/study_host.gd"

## The cast consumes one group transform. Scenery and interface keep identity
## framing, while each actor retains its own local position and attached marks.
const ACTOR_CAST = preload("res://games/bishoujo_afterlight/cast_stage.gd")
const LAYER_PAN = preload("res://addons/game_presentation/motion/layer_pan.gd")
const PAN_CURVES: Array[String] = ["ease_in_out", "linear", "spring"]
var _cast_layer: Control
var _pan = LAYER_PAN.new()
var _cast_ids: Array[String] = []
var _target_id := ""
var _anchor_x := 640.0
var _paused := false
var _pan_settings := {"duration_seconds": 0.45, "curve": "ease_in_out",
	"frequency": 1.5, "damping_ratio": 0.8}
var _duration_slider: HSlider
var _anchor_slider: HSlider
var _duration_label: Label
var _anchor_label: Label
var _curve_button: Button
var _pause_button: Button
var _home_button: Button


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_pan_settings.merge(content.get("cast_pan", {}), true)
	var profiles: Array[Dictionary] = []
	for profile: Dictionary in content.get("guests", []):
		if profiles.size() == 3: break
		profiles.append(profile)
		var actor_id := str(profile["id"])
		_cast_ids.append(actor_id)
		_guest_textures[actor_id] = _load_texture(str(profile["path"]))
	var backgrounds: Array = content.get("backgrounds", [])
	if not backgrounds.is_empty():
		_backgrounds.append(_load_texture(str(backgrounds[0]["path"])))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		var extent := _backgrounds[0].get_size()
		extent *= maxf(DESIGN_SIZE.x / extent.x, DESIGN_SIZE.y / extent.y)
		_base_background = Rect2((DESIGN_SIZE - extent) * 0.5, extent)
	_cast_layer = ACTOR_CAST.new()
	_cast_layer.name = "PannedCast"
	add_child(_cast_layer)
	_load_errors.append_array(_cast_layer.initialize(profiles, _guest_textures, content.get("manpu_textures", {})))
	_build_pan_ui()
	_reset_pan()


func _select_target(actor_id: String) -> void:
	if actor_id not in _cast_ids or not _load_errors.is_empty(): return
	var rect: Rect2 = _cast_layer.get_actor_rect(actor_id)
	var offset := Vector2(_anchor_x - rect.get_center().x, 0.0)
	var errors: Array[String] = _pan.pan_to(offset, _pan_settings)
	_load_errors.append_array(errors)
	if errors.is_empty(): _target_id = actor_id
	_present_pan()


func _home_pan() -> void:
	if not _load_errors.is_empty(): return
	_load_errors.append_array(_pan.pan_to(Vector2.ZERO, _pan_settings))
	_target_id = ""
	_present_pan()


func _toggle_pause() -> void:
	_paused = not _paused
	_update_pan_ui()


func _reset_pan() -> void:
	_pan.clear()
	_paused = false
	_target_id = ""
	if _load_errors.is_empty():
		_load_errors.append_array(_cast_layer.set_cast(_cast_ids))
		_load_errors.append_array(_cast_layer.focus("", "none"))
		_load_errors.append_array(_cast_layer.set_marks([{"actor": _cast_ids[0], "id": "sparkle"}]))
	_present_pan()


func _set_duration(value: float) -> void:
	_pan_settings["duration_seconds"] = value
	_update_pan_ui()


func _set_target_anchor(value: float) -> void:
	_anchor_x = value
	if _target_id.is_empty():
		_update_pan_ui()
	else:
		_select_target(_target_id)


func _cycle_curve() -> void:
	var index := PAN_CURVES.find(str(_pan_settings["curve"]))
	_pan_settings["curve"] = PAN_CURVES[(index + 1) % PAN_CURVES.size()]
	_update_pan_ui()


func _process(delta: float) -> void:
	if _paused or not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0: return
	_pan.advance(delta)
	_cast_layer.advance(delta)
	_present_pan()


func _present_pan() -> void:
	if _status == null: return
	_cast_layer.present(_pan.sample_transform())
	_update_pan_ui()


func pan_state() -> Dictionary:
	return {"target_id": _target_id, "anchor_x": _anchor_x, "paused": _paused,
		"settings": _pan_settings.duplicate(), "cast_ids": _cast_ids.duplicate(),
		"pan": _pan.get_state()}


func _build_pan_ui() -> void:
	_ui = Control.new()
	_ui.name = "CastPanStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(24, 22, 1232, 103), Color("211b28"))
	_label_text("study.cast_pan.title", Rect2(46, 31, 690, 47), 32, INK)
	var description := _label_text("study.cast_pan.description", Rect2(48, 82, 948, 30), 17, MUTED)
	description.size = Vector2(948, 30)
	_build_language_picker(Rect2(787, 38, 206, 38))
	_return_button = _button_text("ui.effects_menu", Rect2(1021, 48, 211, 44), func() -> void: navigate.emit("effects_menu"))
	for index in _cast_ids.size():
		var actor_id := _cast_ids[index]
		var button := _button("", Rect2(56 + index * 394, 142, 382, 44), _select_target.bind(actor_id))
		button.name = "PanTo" + actor_id.capitalize()
		button.toggle_mode = true
		_guest_buttons[actor_id] = button
	_panel(Rect2(24, 699, 1232, 181), Color("211b28"))
	_duration_label = _label("", Rect2(46, 713, 285, 29), 18, INK)
	_duration_slider = HSlider.new()
	_duration_slider.name = "PanDurationSlider"
	_duration_slider.position = Vector2(46, 746)
	_duration_slider.size = Vector2(285, 28)
	_duration_slider.min_value = 0.15
	_duration_slider.max_value = 1.2
	_duration_slider.step = 0.01
	_duration_slider.value = float(_pan_settings["duration_seconds"])
	_duration_slider.value_changed.connect(_set_duration)
	_ui.add_child(_duration_slider)
	_anchor_label = _label("", Rect2(355, 713, 300, 29), 18, INK)
	_anchor_slider = HSlider.new()
	_anchor_slider.name = "PanAnchorSlider"
	_anchor_slider.position = Vector2(355, 746)
	_anchor_slider.size = Vector2(300, 28)
	_anchor_slider.min_value = 320.0
	_anchor_slider.max_value = 960.0
	_anchor_slider.step = 10.0
	_anchor_slider.value = _anchor_x
	_anchor_slider.value_changed.connect(_set_target_anchor)
	_ui.add_child(_anchor_slider)
	_curve_button = _button("", Rect2(680, 726, 307, 43), _cycle_curve)
	_curve_button.name = "PanCurve"
	_status = _label("", Rect2(1008, 718, 224, 52), 17, MUTED)
	_status.name = "CastPanStatus"
	_home_button = _button_text("study.cast_pan.home", Rect2(46, 787, 280, 42), _home_pan)
	_home_button.name = "PanHome"
	_pause_button = _button_text("ui.pause", Rect2(342, 787, 210, 42), _toggle_pause)
	_pause_button.name = "PausePan"
	_button_text("ui.reset", Rect2(568, 787, 210, 42), _reset_pan).name = "ResetPan"
	var hint := _label_text("study.cast_pan.hint", Rect2(46, 846, 1170, 26), 15, MUTED)
	hint.size = Vector2(1170, 26)


func _update_pan_ui() -> void:
	if _status == null: return
	for actor_id: String in _guest_buttons:
		_guest_buttons[actor_id].text = _text("guest." + actor_id + ".name")
		_guest_buttons[actor_id].set_pressed_no_signal(actor_id == _target_id)
	_duration_label.text = _text("study.cast_pan.duration", {"value": "%.2f" % float(_pan_settings["duration_seconds"])})
	_anchor_label.text = _text("study.cast_pan.anchor", {"value": int(_anchor_x)})
	_curve_button.text = _text("study.cast_pan.curve", {"value": _text("study.motion.curve." + str(_pan_settings["curve"]))})
	_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
	_status.text = _text("study.cast_pan.status", {"value": "%.1f" % _pan.sample_transform().origin.x})
	if not _load_errors.is_empty():
		_status.text = "\n".join(_load_errors)
		_home_button.disabled = true
		_pause_button.disabled = true
		for button: Button in _guest_buttons.values(): button.disabled = true


func _refresh_language() -> void:
	_update_pan_ui()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		draw_texture_rect(_backgrounds[0], _base_background, false)


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		_toggle_language()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
	else:
		return
	get_viewport().set_input_as_handled()
