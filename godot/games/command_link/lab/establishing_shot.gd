extends "res://presentation/stage.gd"

var _demo_settings: Dictionary = {}
var _demos_button: Button
var _play_button: Button
var _location_button: Button
var _replay_button: Button
var _skip_button: Button
var _flare_button: Button
var _shot_status: Label
var _controls_hint: Label
var _setting_labels: Dictionary = {}
var _setting_sliders: Dictionary = {}


func _build_interface() -> void:
	_title = _label("Establishing Shot", 27, PAPER)
	_subtitle = _label("", 13, MUTED)
	_location_title = _label("", 27, PAPER)
	_location_detail = _label("", 13, WARM)
	_speaker = _label("Mira", 15, WARM, HORIZONTAL_ALIGNMENT_CENTER)
	_line = _label("Commander, the squad is in position.", 25, PAPER, HORIZONTAL_ALIGNMENT_CENTER)
	_hint = _label("", 13, MUTED)
	_footer = _label("", 12, MUTED)
	_shot_status = _label("", 15, PAPER)
	_controls_hint = _label("L · location     E · replay     Space · skip     F · flare     R · reset", 12, MUTED)
	_demos_button = _button("Demos", func() -> void: navigate.emit("command_link"))
	_play_button = _button("Play", func() -> void: navigate.emit("game:command_link/game"))
	_location_button = _button("", _cycle_location)
	_replay_button = _button("Replay · E", _replay_shot)
	TACTICAL_THEME.style_primary(_replay_button)
	_skip_button = _button("Skip · Space", _skip_shot)
	_flare_button = _button("", _toggle_flare)
	_restart_button = _button("Reset · R", _restart)
	for spec: Array in [["duration_seconds", 2.0, 8.0, 0.1], ["pan_amount", -120.0, 120.0, 1.0], ["zoom_amount", 0.0, 0.16, 0.01], ["flare_strength", 0.0, 1.0, 0.05]]:
		var key := String(spec[0])
		_setting_labels[key] = _label("", 13, MUTED)
		var slider := HSlider.new()
		slider.min_value = float(spec[1])
		slider.max_value = float(spec[2])
		slider.step = float(spec[3])
		slider.value_changed.connect(_set_setting.bind(key))
		add_child(slider)
		_setting_sliders[key] = slider


func _configure_route() -> void:
	_mode = "dialogue"
	_natural_blink = false
	_actor_focus.clear()
	_manpu_animation.clear()
	_character_exit.clear()
	var opening := "coastal_staging" if _locations.has("coastal_staging") else _location_id
	_set_profile(opening)
	_load_errors.append_array(start_establishing(opening, _demo_settings))


func _reset_character_effects() -> void:
	for actor: Dictionary in stage_profile.actors:
		_character_effects[String(actor["id"])] = {"enabled": false, "strength": 0.8}


func _current_beat() -> Dictionary:
	return {"speaker": "Mira", "line": "Commander, the squad is in position.", "manpu": [{"actor": "mira", "id": "surprise"}]}


func _set_profile(location_id: String) -> void:
	_demo_settings = ESTABLISHING_SHOT_SCRIPT.DEFAULTS.duplicate(true)
	if _locations.has(location_id):
		_demo_settings.merge(_locations[location_id].get("establishing_shot", {}), true)


func _cycle_location() -> void:
	var index := (stage_profile.location_ids.find(_location_id) + 1) % stage_profile.location_ids.size()
	var location_id: String = stage_profile.location_ids[index]
	_set_profile(location_id)
	start_establishing(location_id, _demo_settings)
	_update_interface()


func _replay_shot() -> void:
	start_establishing(_location_id, _demo_settings)
	_update_interface()


func _skip_shot() -> void:
	skip_establishing()
	_update_interface()


func _toggle_flare() -> void:
	if is_establishing():
		return
	_demo_settings["flare_enabled"] = not bool(_demo_settings["flare_enabled"])
	_update_interface()


func _set_setting(value: float, key: String) -> void:
	if is_establishing():
		return
	_demo_settings[key] = value
	_update_interface()


func _restart() -> void:
	_configure_route()
	_update_interface()


func _draw_character_overlay(canvas: CanvasItem) -> void:
	if not is_establishing():
		super._draw_character_overlay(canvas)
	_draw_tactical_panel(canvas, Rect2(20, 658, size.x - 40, 238),
		Color(0.035, 0.055, 0.073, 0.97), TACTICAL_THEME.BORDER)
	canvas.draw_rect(Rect2(32, 658, 72, 3), WARM)


func _process(delta: float) -> void:
	super._process(delta)
	if _shot_status != null and not _demo_settings.is_empty():
		_update_status()


func _update_status() -> void:
	var active := is_establishing()
	var state: Dictionary = save_establishing()
	_shot_status.text = "Establishing location · %.1f / %.1f seconds" % [float(state["elapsed"]), float(_demo_settings["duration_seconds"])] if active else "The location is established. Adjust the next shot, then replay."
	_skip_button.disabled = not active
	_flare_button.disabled = active
	_flare_button.text = "Flare · on" if _demo_settings["flare_enabled"] else "Flare · off"
	_location_button.text = "L · " + String(_locations.get(_location_id, {}).get("name", _location_id))
	for key: String in _setting_sliders:
		var slider: HSlider = _setting_sliders[key]
		slider.set_value_no_signal(float(_demo_settings[key]))
		slider.editable = not active and (key != "flare_strength" or bool(_demo_settings["flare_enabled"]))
	_setting_labels["duration_seconds"].text = "Duration · %.1fs" % float(_demo_settings["duration_seconds"])
	_setting_labels["pan_amount"].text = "Pan · %d px" % roundi(float(_demo_settings["pan_amount"]))
	_setting_labels["zoom_amount"].text = "Opening zoom · %d%%" % roundi(float(_demo_settings["zoom_amount"]) * 100.0)
	_setting_labels["flare_strength"].text = "Flare strength · %d%%" % roundi(float(_demo_settings["flare_strength"]) * 100.0)


func _update_interface() -> void:
	if _line == null or _demo_settings.is_empty():
		return
	_update_status()
	if not _load_errors.is_empty():
		_shot_status.text = " · ".join(_load_errors)
	_layout_interface()


func _layout_interface() -> void:
	if _title == null:
		return
	_place(_title, Vector2(32, 22), Vector2(920, 40))
	_place(_subtitle, Vector2(33, 62), Vector2(920, 24))
	_place(_location_title, _title.position, _title.size)
	_place(_location_detail, _subtitle.position, _subtitle.size)
	_place(_demos_button, Vector2(1012, 32), Vector2(112, 36))
	_place(_play_button, Vector2(1136, 32), Vector2(112, 36))
	_place(_speaker, Vector2(32, 607), Vector2(1216, 25))
	_place(_line, Vector2(32, 632), Vector2(1216, 36))
	_place(_shot_status, Vector2(32, 670), Vector2(1216, 26))
	_place(_location_button, Vector2(32, 713), Vector2(290, 36))
	_place(_replay_button, Vector2(336, 713), Vector2(150, 36))
	_place(_skip_button, Vector2(500, 713), Vector2(150, 36))
	_place(_flare_button, Vector2(664, 713), Vector2(180, 36))
	_place(_restart_button, Vector2(858, 713), Vector2(110, 36))
	var keys := ["duration_seconds", "pan_amount", "zoom_amount", "flare_strength"]
	for index in keys.size():
		var key: String = keys[index]
		var point := Vector2(32 + (index % 2) * 616, 769 + (index / 2) * 47)
		_place(_setting_labels[key], point, Vector2(188, 26))
		_place(_setting_sliders[key], point + Vector2(192, 4), Vector2(394, 20))
	_place(_controls_hint, Vector2(32, 868), Vector2(1216, 24))
	_update_character_layers()
	queue_redraw()


func _place(control: Control, point: Vector2, extent: Vector2) -> void:
	control.position = point
	control.size = extent


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_SPACE and get_viewport().gui_get_focus_owner() == null:
		if is_establishing():
			_skip_shot()
		else:
			_replay_shot()
		get_viewport().set_input_as_handled()


func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_ESCAPE: navigate.emit("command_link")
		KEY_L: _cycle_location()
		KEY_E: _replay_shot()
		KEY_F: _toggle_flare()
		KEY_R: _restart()
		_: return
	get_viewport().set_input_as_handled()
