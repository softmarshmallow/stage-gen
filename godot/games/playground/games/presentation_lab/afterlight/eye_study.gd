extends "res://games/presentation_lab/afterlight/study_host.gd"

## The laboratory's Afterlight fixture UI. The eye controller and shader own no UI.
var _selected_mode := "waking_opening"
var _mode_buttons: Dictionary = {}
var _eye_sliders: Dictionary = {}
var _eye_values: Dictionary = {}
var _softness_slider: HSlider
var _softness_value: Label


func _bind_guest() -> void:
	_actor.texture = _guest_close_textures.get(_guest_id, _guest_textures.get(_guest_id))


func replay_approach() -> void:
	if not _load_errors.is_empty():
		return
	_bind_background()
	_load_errors.append_array(_camera.start())
	_camera.skip()
	replay_eye()


func replay_eye() -> void:
	if not _load_errors.is_empty():
		return
	_load_errors.append_array(_eye.start(_selected_mode))
	_phase = "eye_study"
	_update_ui()
	_update_visuals()


func skip_eye_transition() -> void:
	_eye.skip()
	_update_ui()
	_update_visuals()


func _select_mode(mode: String) -> void:
	_selected_mode = mode
	replay_eye()


func _process(delta: float) -> void:
	if not _load_errors.is_empty():
		return
	_eye.advance(delta)
	_update_ui()
	_update_visuals()


func _update_visuals() -> void:
	super._update_visuals()
	if not _load_errors.is_empty() or _actor.texture == null:
		return
	var profile := guest_profile()
	var close_portrait := _guest_close_textures.has(_guest_id)
	var eye_uv: Array = profile.get("eye_close_uv", [0.5, 0.4]) if close_portrait else profile.get("eye_uv", [0.5, 0.12])
	var height := float(profile.get("eye_close_height", 820.0)) if close_portrait else 1380.0
	var width := height * _actor.texture.get_width() / _actor.texture.get_height()
	_actor.position = Vector2(640.0 - width * float(eye_uv[0]), 425.0 - height * float(eye_uv[1]))
	_actor.size = Vector2(width, height)
	_actor.visible = true
	_actor.modulate.a = 1.0
	_status.text = _text("study.eye.status", {"phase": _text("phase." + str(_eye.sample()["phase"]))})


func _update_ui() -> void:
	if _line == null:
		return
	if not _load_errors.is_empty():
		super._update_ui()
		return
	var pose: Dictionary = _eye.sample()
	_status.text = _text("study.eye.status", {"phase": _text("phase." + str(pose["phase"]))})
	_update_guest_picker()
	var portrait_kind := _text("study.eye.portrait_dedicated" if _guest_close_textures.has(_guest_id) else "study.eye.portrait_cropped")
	_line.text = _text("study.eye.instructions", {"guest": guest_profile()["name"], "portrait_kind": portrait_kind})
	_skip_button.disabled = not _eye.is_active()
	for mode: String in _mode_buttons:
		_mode_buttons[mode].set_pressed_no_signal(mode == _selected_mode)


func _tune_eye(value: float, key: String) -> void:
	_load_errors.append_array(_eye.configure({key: value}))
	_eye_values[key].text = _eye_value_text(key, value)


func _eye_value_text(key: String, value: float) -> String:
	if key == "peek_openness":
		return _text("unit.percent", {"value": "%.0f" % (value * 100.0)})
	return _text("unit.seconds", {"value": "%.2f" % value})


func _reset_eye() -> void:
	var settings := EYE.DEFAULT_SETTINGS.duplicate()
	settings.merge(content.get("eye_transition", {}), true)
	_load_errors.append_array(_eye.configure(settings))
	for key: String in _eye_sliders:
		var value := float(_eye.get_settings()[key])
		_eye_sliders[key].set_value_no_signal(value)
		_eye_values[key].text = _eye_value_text(key, value)
	var softness := float(content.get("eye_mask", {}).get("edge_softness", 28.0))
	_softness_slider.set_value_no_signal(softness)
	_set_softness(softness)
	replay_eye()


func _set_softness(value: float) -> void:
	_eye_material.set_shader_parameter("edge_softness", value)
	_softness_value.text = _text("unit.pixels", {"value": "%.0f" % value})


func _refresh_language() -> void:
	_update_language_picker()
	for key: String in _eye_values:
		_eye_values[key].text = _eye_value_text(key, _eye_sliders[key].value)
	if _softness_value != null:
		_softness_value.text = _text("unit.pixels", {"value": "%.0f" % _softness_slider.value})
	_update_ui()


func _build_ui() -> void:
	_ui = Control.new()
	_ui.name = "AfterlightEyeStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(32, 24, 1216, 96), Color(0.09, 0.075, 0.12, 0.84))
	_label_text("game.kicker", Rect2(56, 36, 300, 18), 12, ACCENT)
	_label_text("game.title", Rect2(54, 51, 400, 53), 37, INK)
	_build_language_picker(Rect2(584, 51, 224, 40))
	_study_button = _button_text("ui.walking_approach", Rect2(830, 49, 190, 44), func() -> void: navigate.emit("approach_study"))
	_return_button = _button_text("ui.return_to_story", Rect2(1030, 49, 190, 44), func() -> void: navigate.emit("game:bishoujo_afterlight"))
	_build_guest_picker()
	_button("Presentation Lab", Rect2(56, 184, 230, 40), func() -> void: navigate.emit("menu"))
	_panel(Rect2(40, 640, 1200, 232), Color(0.09, 0.075, 0.12, 0.94))
	_status = _label("", Rect2(64, 656, 600, 30), 22, INK)
	_line = _label("", Rect2(64, 689, 1150, 24), 14, MUTED)
	var choices := [["waking_opening", "study.eye.waking_opening"], ["eye_opening", "study.eye.eye_opening"], ["eye_closing", "study.eye.eye_closing"], ["blink", "study.eye.blink"]]
	for index in choices.size():
		var item: Array = choices[index]
		var button := _button_text(item[1], Rect2(64 + (index % 2) * 232, 720 + (index / 2) * 44, 222, 38), _select_mode.bind(item[0]))
		button.toggle_mode = true
		_mode_buttons[item[0]] = button
	var settings := [["opening_seconds", "study.eye.opening"], ["closing_seconds", "study.eye.closing"], ["closed_hold_seconds", "study.eye.closed_hold"], ["peek_seconds", "study.eye.peek_seconds"], ["peek_openness", "study.eye.peek_openness"]]
	for index in settings.size():
		var spec: Array = settings[index]
		var x := 586.0 + (index % 3) * 212.0
		var y := 718.0 + (index / 3) * 70.0
		var value := float(content.get("eye_transition", {}).get(spec[0], EYE.DEFAULT_SETTINGS[spec[0]]))
		_label_text(spec[1], Rect2(x, y, 120, 23), 14, INK)
		_eye_values[spec[0]] = _label(_eye_value_text(spec[0], value), Rect2(x + 120, y, 80, 23), 14, ACCENT)
		var slider := HSlider.new()
		slider.position = Vector2(x, y + 26)
		slider.size = Vector2(182, 24)
		slider.min_value = EYE.SETTING_RANGES[spec[0]][0]
		slider.max_value = EYE.SETTING_RANGES[spec[0]][1]
		slider.step = 0.01
		slider.value = value
		slider.value_changed.connect(_tune_eye.bind(spec[0]))
		_ui.add_child(slider)
		_eye_sliders[spec[0]] = slider
	_replay_button = _button_text("ui.replay", Rect2(64, 818, 142, 38), replay_eye)
	_skip_button = _button_text("ui.skip", Rect2(220, 818, 142, 38), skip_eye_transition)
	_button_text("ui.reset", Rect2(376, 818, 142, 38), _reset_eye)
	_label_text("study.eye.edge_softness", Rect2(1010, 788, 120, 23), 14, INK)
	var softness := float(content.get("eye_mask", {}).get("edge_softness", 28.0))
	_softness_value = _label(_text("unit.pixels", {"value": "%.0f" % softness}), Rect2(1130, 788, 80, 23), 14, ACCENT)
	_softness_slider = HSlider.new()
	_softness_slider.position = Vector2(1010, 814)
	_softness_slider.size = Vector2(182, 24)
	_softness_slider.min_value = 0.0
	_softness_slider.max_value = 64.0
	_softness_slider.step = 1.0
	_softness_slider.value = softness
	_softness_slider.value_changed.connect(_set_softness)
	_ui.add_child(_softness_slider)
	_label_text("study.eye.timing_hint", Rect2(586, 848, 620, 20), 13, MUTED)
