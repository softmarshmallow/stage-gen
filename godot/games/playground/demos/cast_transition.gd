extends "res://presentation/stage.gd"

## Fixed-canvas choreography workbench; story state remains in its own route.
const CAST = preload("res://addons/game_presentation/actors/cast_transition.gd")
const GRAPH = preload("res://presentation/animation/motion_curve_graph.gd")
const CAST_SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
const PATTERNS := ["shift_and_replace", "replace_in_place"]
const CURVES := ["linear", "ease_in_out", "spring"]
const CURVE_LABELS := {"linear": "Linear", "ease_in_out": "Ease in / out", "spring": "Spring"}
var _cast_transition = CAST.new()
var _default_settings: Dictionary = {}
var _demos_button: Button
var _play_button: Button
var _pattern_button: Button
var _curve_button: Button
var _run_button: Button
var _curve_graph: Control
var _frequency_slider: HSlider
var _damping_slider: HSlider
var _duration_slider: HSlider
var _travel_slider: HSlider
var _frequency_label: Label
var _damping_label: Label
var _duration_label: Label
var _travel_label: Label


func _build_interface() -> void:
	_title = _label("Cast Transition", 27, PAPER)
	_subtitle = _label("", 13, MUTED)
	_location_title = _label("", 27, PAPER)
	_location_detail = _label("", 13, WARM)
	_line = _label("", 23, PAPER)
	_hint = _label("", 15, MUTED)
	_speaker = _label("", 15, WARM)
	_speaker.visible = false
	_footer = _label("", 12, MUTED)
	_demos_button = _button("Demos", func() -> void: navigate.emit("command_link"))
	_play_button = _button("Play", func() -> void: navigate.emit("game:command_link/game"))
	_pattern_button = _button("", _cycle_pattern)
	_curve_button = _button("", _cycle_curve)
	_run_button = _button("Run · E", _start_handoff)
	TACTICAL_THEME.style_primary(_run_button)
	_restart_button = _button("Reset · R", _reset_cast)
	_curve_graph = Control.new()
	_curve_graph.set_script(GRAPH)
	_curve_graph.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_curve_graph)
	_frequency_label = _label("", 13, MUTED)
	_damping_label = _label("", 13, MUTED)
	_duration_label = _label("", 13, MUTED)
	_travel_label = _label("", 13, MUTED)
	_frequency_slider = _setting_slider(1.0, 3.0, 0.1, "frequency")
	_damping_slider = _setting_slider(0.2, 1.0, 0.05, "damping_ratio")
	_duration_slider = _setting_slider(0.4, 1.4, 0.1, "motion_duration_seconds")
	_travel_slider = _setting_slider(40.0, 120.0, 5.0, "travel_distance")
	_frequency_slider.tooltip_text = "Spring cycles per step. The graph previews the same translation curve."
	_damping_slider.tooltip_text = "Higher damping reduces the spring's overshoot."
	_duration_slider.tooltip_text = "Duration of repositioning and entrance, in seconds. The silhouette exit remains 0.9 seconds."
	_travel_slider.tooltip_text = "Travel distance for exit and entrance. Repositioning spans the two standing positions."


func _setting_slider(minimum: float, maximum: float, step_size: float, key: String) -> HSlider:
	var slider := HSlider.new()
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = step_size
	slider.value_changed.connect(_set_setting.bind(key))
	add_child(slider)
	return slider


func _configure_route() -> void:
	_mode = "dialogue"
	_entry = 1.0
	_natural_blink = false
	_actor_focus.clear()
	_character_exit.clear()
	var ids: Array[String] = []
	for actor: Dictionary in stage_profile.actors:
		ids.append(String(actor["id"]))
	_load_errors.append_array(_cast_transition.initialize(ids, CHARACTER_EXIT_CATALOG, CAST_SPEC))
	_default_settings = _cast_transition.get_settings()


func _reset_character_effects() -> void:
	for actor: Dictionary in stage_profile.actors:
		_character_effects[String(actor["id"])] = {"enabled": false, "strength": 0.8}


func _current_beat() -> Dictionary:
	return {"speaker": "", "manpu": []}


func _active_manpu() -> Array:
	return []


func _actor_is_visible(actor_id: String) -> bool:
	return bool(_cast_transition.sample(actor_id)["visible"]) if _cast_transition.initialized else super._actor_is_visible(actor_id)


func _actor_is_present(actor_id: String) -> bool:
	return _actor_is_visible(actor_id)


func _actor_visual_sample(actor_id: String) -> Dictionary:
	return _cast_transition.sample(actor_id) if _cast_transition.initialized else super._actor_visual_sample(actor_id)


func _dialogue_rect(viewport_size: Vector2, actor_index: int) -> Rect2:
	var rect := super._dialogue_rect(viewport_size, actor_index)
	if _cast_transition.initialized:
		var pose: Dictionary = _cast_transition.sample(String(stage_profile.actors[actor_index]["id"]))
		rect.position.x = float(pose["center_x"]) - rect.size.x * 0.5
	return rect


func _draw_character_overlay(canvas: CanvasItem) -> void:
	# This route uses the lower band for motion controls and the actual curve.
	_draw_tactical_panel(canvas, Rect2(20, 610, size.x - 40, 286),
		Color(0.035, 0.055, 0.073, 0.94), TACTICAL_THEME.BORDER)
	canvas.draw_rect(Rect2(32, 610, 72, 3), WARM)


func _process(delta: float) -> void:
	if _cast_transition.initialized and not _capture_frozen:
		_cast_transition.advance(delta)
	super._process(delta)
	if _cast_transition.initialized and _run_button != null:
		_update_cast_status()


func _place(control: Control, position: Vector2, extent: Vector2) -> void:
	control.position = position
	control.size = extent


func _layout_interface() -> void:
	if _title == null:
		return
	_place(_title, Vector2(32, 22), Vector2(920, 40))
	_place(_subtitle, Vector2(33, 62), Vector2(920, 24))
	_place(_location_title, _title.position, _title.size)
	_place(_location_detail, _subtitle.position, _subtitle.size)
	_place(_demos_button, Vector2(1012, 32), Vector2(112, 36))
	_place(_play_button, Vector2(1136, 32), Vector2(112, 36))
	_place(_line, Vector2(36, 625), Vector2(1208, 34))
	_place(_hint, Vector2(36, 663), Vector2(1208, 28))
	_place(_curve_graph, Vector2(36, 705), Vector2(280, 163))
	_place(_pattern_button, Vector2(340, 704), Vector2(234, 36))
	_place(_curve_button, Vector2(588, 704), Vector2(200, 36))
	_place(_run_button, Vector2(992, 704), Vector2(132, 36))
	_place(_restart_button, Vector2(1138, 704), Vector2(110, 36))
	_place(_frequency_label, Vector2(340, 754), Vector2(148, 26))
	_place(_frequency_slider, Vector2(496, 758), Vector2(250, 20))
	_place(_damping_label, Vector2(788, 754), Vector2(162, 26))
	_place(_damping_slider, Vector2(958, 758), Vector2(290, 20))
	_place(_duration_label, Vector2(340, 802), Vector2(148, 26))
	_place(_duration_slider, Vector2(496, 806), Vector2(250, 20))
	_place(_travel_label, Vector2(788, 802), Vector2(162, 26))
	_place(_travel_slider, Vector2(958, 806), Vector2(290, 20))
	_place(_footer, Vector2(340, 850), Vector2(908, 28))
	_update_character_layers()
	queue_redraw()


func _actor_name(id: String) -> String:
	var index := _dialogue_actor_index(id)
	return String(stage_profile.actors[index]["name"]) if index >= 0 else id.capitalize()


func _update_interface() -> void:
	if _line == null:
		return
	if _cast_transition.initialized:
		_update_cast_status()
	if not _load_errors.is_empty():
		_line.text = "The cast transition could not load."
		_hint.text = " · ".join(_load_errors)
		_run_button.disabled = true
	_layout_interface()


func _update_cast_status() -> void:
	var state: Dictionary = _cast_transition.get_state()
	var settings: Dictionary = _cast_transition.get_settings()
	var busy: bool = _cast_transition.is_busy()
	var phase := String(state["phase"])
	var occupancy: Dictionary = state["occupancy"]
	var left := String(occupancy["left"])
	var right := String(occupancy["right"])
	var newcomer := ""
	for actor: Dictionary in stage_profile.actors:
		if actor["id"] != left and actor["id"] != right:
			newcomer = String(actor["id"])
	_pattern_button.text = "P · Shift, then replace" if settings["pattern"] == "shift_and_replace" else "P · Replace in place"
	_curve_button.text = "C · " + String(CURVE_LABELS[settings["curve"]])
	_pattern_button.disabled = busy
	_curve_button.disabled = busy
	_run_button.disabled = busy or not _load_errors.is_empty()
	_frequency_slider.set_value_no_signal(float(settings["frequency"]))
	_damping_slider.set_value_no_signal(float(settings["damping_ratio"]))
	_duration_slider.set_value_no_signal(float(settings["motion_duration_seconds"]))
	_travel_slider.set_value_no_signal(float(settings["travel_distance"]))
	_frequency_slider.editable = not busy and settings["curve"] == "spring"
	_damping_slider.editable = not busy and settings["curve"] == "spring"
	_duration_slider.editable = not busy
	_travel_slider.editable = not busy
	_frequency_label.text = "Frequency · %.1f" % float(settings["frequency"])
	_damping_label.text = "Damping · %.2f" % float(settings["damping_ratio"])
	_duration_label.text = "Move / enter · %.1fs" % float(settings["motion_duration_seconds"])
	_travel_label.text = "Exit / enter · %d px" % roundi(float(settings["travel_distance"]))
	if busy:
		var subject := String(state["outgoing"] if phase == "exit" else state["survivor"] if phase == "move" else state["incoming"])
		_line.text = _actor_name(subject) + {"exit": " leaves.", "move": " moves into the open position.", "enter": " arrives."}.get(phase, "")
		_hint.text = "Exit → reposition → enter" if settings["pattern"] == "shift_and_replace" else "Exit → enter the same position"
		_footer.text = "Each step finishes before the next. Reset can interrupt the sequence."
		var progress := float(state["phase_elapsed"]) / float(state["phase_duration"])
		_curve_graph.set_state(state["active_settings"], progress)
	else:
		_line.text = _actor_name(left) + " and " + _actor_name(right) + " are here."
		_hint.text = "Next: %s leaves → %s moves left → %s arrives." % [_actor_name(left), _actor_name(right), _actor_name(newcomer)] if settings["pattern"] == "shift_and_replace" else "Next: %s leaves → %s enters her position. %s stays." % [_actor_name(left), _actor_name(newcomer), _actor_name(right)]
		_footer.text = "P · pattern     C · curve     E / Space · run     R · reset     Tune the next handoff above."
		_curve_graph.set_state(settings)


func _set_setting(value: float, key: String) -> void:
	if not _cast_transition.initialized or _cast_transition.is_busy():
		return
	_cast_transition.configure({key: value})
	_update_interface()


func _cycle_pattern() -> void:
	if _cast_transition.is_busy():
		return
	var settings: Dictionary = _cast_transition.get_settings()
	_cast_transition.configure({"pattern": PATTERNS[(PATTERNS.find(settings["pattern"]) + 1) % PATTERNS.size()]})
	_update_interface()


func _cycle_curve() -> void:
	if _cast_transition.is_busy():
		return
	var settings: Dictionary = _cast_transition.get_settings()
	_cast_transition.configure({"curve": CURVES[(CURVES.find(settings["curve"]) + 1) % CURVES.size()]})
	_update_interface()


func _start_handoff() -> void:
	if not _load_errors.is_empty():
		return
	_cast_transition.start()
	_update_interface()


func _reset_cast() -> void:
	_cast_transition.reset()
	_cast_transition.configure(_default_settings)
	_entry = 1.0
	_update_interface()


func _restart() -> void:
	_reset_cast()


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode == KEY_SPACE and get_viewport().gui_get_focus_owner() == null:
		_start_handoff()
		get_viewport().set_input_as_handled()


func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_ESCAPE: navigate.emit("command_link")
		KEY_E: _start_handoff()
		KEY_P: _cycle_pattern()
		KEY_C: _cycle_curve()
		KEY_R: _reset_cast()
		_: return
	get_viewport().set_input_as_handled()
