extends "res://presentation/stage.gd"

## Explicit shot cues are independent of speaker changes and dialogue length.
const CAMERA_LINES := [
	{"speaker": "Mira", "line": "Commander, the convoy is ready. I want you to see that we're ready too.", "manpu": [{"actor": "mira", "id": "surprise"}]},
	{"speaker": "Mira", "line": "We'll stay with the transports all the way through the coast road.", "manpu": [{"actor": "mira", "id": "surprise"}]},
	{"speaker": "Mira", "line": "One clear order. Then we'll move together.", "manpu": []},
	{"speaker": "Lena", "line": "The high road has two blind corners. I've marked both approaches.", "manpu": [{"actor": "lena", "id": "sweat_drop"}]},
	{"speaker": "Lena", "line": "I'll watch the ridge while the repair team reaches the relay.", "manpu": [{"actor": "lena", "id": "sweat_drop"}]},
	{"speaker": "Lena", "line": "Nobody gets left outside our cover. That's a promise.", "manpu": []},
	{"speaker": "Sera", "line": "I have a clean signal, Commander. Let me show you the safe route.", "manpu": [{"actor": "sera", "id": "sparkle"}]},
	{"speaker": "Sera", "line": "The beacon will guide the lead transport. The others can follow its lights.", "manpu": [{"actor": "sera", "id": "sparkle"}]},
	{"speaker": "Sera", "line": "Your squad is listening. We're ready when you are.", "manpu": []},
]
var _demo_line_index := 0
var _requested_zoom := 4.0
var _camera_duration_seconds := 0.9
var _demos_button: Button
var _play_button: Button
var _speaker_button: Button
var _close_button: Button
var _wide_button: Button
var _zoom_slider: HSlider
var _duration_slider: HSlider
var _zoom_label: Label
var _duration_label: Label
var _camera_status: Label


func _build_interface() -> void:
	_title = _label("Dialogue Camera", 27, PAPER)
	_subtitle = _label("", 13, MUTED)
	_location_title = _label("", 27, PAPER)
	_location_detail = _label("", 13, WARM)
	_speaker = _label("", 16, WARM, HORIZONTAL_ALIGNMENT_CENTER)
	_line = _label("", 23, PAPER, HORIZONTAL_ALIGNMENT_CENTER)
	_hint = _label("C · frame speaker     W · wide     T · speaker     Space · next line     L · location     R · reset", 12, MUTED)
	_footer = _label("", 12, MUTED)
	_camera_status = _label("", 14, MUTED)
	_demos_button = _button("Demos", func() -> void: navigate.emit("command_link"))
	_play_button = _button("Play", func() -> void: navigate.emit("game:command_link/game"))
	_speaker_button = _button("", _cycle_speaker)
	_close_button = _button("Frame speaker · C", _frame_speaker)
	TACTICAL_THEME.style_primary(_close_button)
	_wide_button = _button("Wide · W", _frame_wide)
	_next_button = _button("Next line →", _advance_dialogue)
	_scene_button = _button("", _cycle_location)
	_restart_button = _button("Reset · R", _restart)
	_zoom_label = _label("", 13, MUTED)
	_duration_label = _label("", 13, MUTED)
	_zoom_slider = _camera_slider(1.0, 4.0, 0.1, _set_zoom)
	_duration_slider = _camera_slider(0.2, 2.0, 0.1, _set_duration)
	_close_button.tooltip_text = "Resolve the current speaker once and move the whole scene into a close-up."
	_next_button.tooltip_text = "Change the dialogue without changing the camera cue."
	_zoom_slider.tooltip_text = "Requested shot zoom. Edit, then press Frame speaker."
	_duration_slider.tooltip_text = "Duration of the next camera move. A running move keeps its own timing."


func _camera_slider(minimum: float, maximum: float, step_size: float, action: Callable) -> HSlider:
	var slider := HSlider.new()
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = step_size
	slider.value_changed.connect(action)
	add_child(slider)
	return slider


func _configure_route() -> void:
	_mode = "dialogue"
	_entry = 1.0
	_natural_blink = true
	_demo_line_index = 0
	_requested_zoom = 4.0
	_camera_duration_seconds = 0.9
	_actor_focus.clear()
	_actor_focus.configure("none")
	actor_focus_preset = "none"
	_manpu_animation.clear()
	_character_exit.clear()
	clear_dialogue_camera()
	_select_location("forward_command", true)
	for beat: Dictionary in CAMERA_LINES:
		_load_errors.append_array(_manpu_cue_errors(beat.get("manpu", [])))


func _reset_character_effects() -> void:
	for actor: Dictionary in stage_profile.actors:
		_character_effects[String(actor["id"])] = {"enabled": false, "strength": 0.8}


func _current_beat() -> Dictionary:
	return CAMERA_LINES[_demo_line_index]


func _speaker_actor_id() -> String:
	for actor: Dictionary in stage_profile.actors:
		if actor["name"] == _current_beat()["speaker"]:
			return String(actor["id"])
	return ""


func _frame_speaker() -> void:
	_load_errors.append_array(focus_dialogue_camera(_speaker_actor_id(), _requested_zoom, _camera_duration_seconds))
	_update_interface()


func _frame_wide() -> void:
	_load_errors.append_array(wide_dialogue_camera(_camera_duration_seconds))
	_update_interface()


func _cycle_speaker() -> void:
	_demo_line_index = ((int(_demo_line_index / 3) + 1) % 3) * 3
	_update_interface()


func _advance_dialogue() -> void:
	_demo_line_index = (_demo_line_index + 1) % CAMERA_LINES.size()
	_update_interface()


func _cycle_location() -> void:
	clear_dialogue_camera()
	var index := (stage_profile.location_ids.find(_location_id) + 1) % stage_profile.location_ids.size()
	_select_location(stage_profile.location_ids[index], true)
	_update_interface()


func _set_zoom(value: float) -> void:
	_requested_zoom = value
	_update_interface()


func _set_duration(value: float) -> void:
	_camera_duration_seconds = value
	_update_interface()


func _restart() -> void:
	_configure_route()
	_update_interface()


func _process(delta: float) -> void:
	super._process(delta)
	if _camera_status != null:
		_update_camera_status()


func _update_camera_status() -> void:
	var sample: Dictionary = dialogue_camera_sample()
	var saved: Dictionary = save_dialogue_camera()
	var focus_id := String(saved.get("focus_id", ""))
	var framing := "Wide" if focus_id.is_empty() else focus_id.capitalize()
	_camera_status.text = "%s · %.2f× · %s. Next line changes the dialogue; Frame speaker issues a new camera cue." % [framing, float(sample["zoom"]), "moving" if is_dialogue_camera_moving() else "held"]


func _update_interface() -> void:
	if _line == null:
		return
	_speaker.text = String(_current_beat()["speaker"])
	_line.text = String(_current_beat()["line"])
	_speaker_button.text = "T · " + _speaker.text
	_scene_button.text = "L · " + String(_locations.get(_location_id, {}).get("name", _location_id))
	_zoom_label.text = "Requested zoom · %.1f×" % _requested_zoom
	_duration_label.text = "Move duration · %.1fs" % _camera_duration_seconds
	_zoom_slider.set_value_no_signal(_requested_zoom)
	_duration_slider.set_value_no_signal(_camera_duration_seconds)
	_update_camera_status()
	if not _load_errors.is_empty():
		_camera_status.text = " · ".join(_load_errors)
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
	_place(_speaker, Vector2(32, 675), Vector2(1216, 25))
	_place(_line, Vector2(32, 704), Vector2(1216, 56))
	_place(_camera_status, Vector2(32, 762), Vector2(1216, 26))
	_place(_speaker_button, Vector2(32, 797), Vector2(180, 36))
	_place(_close_button, Vector2(224, 797), Vector2(180, 36))
	_place(_wide_button, Vector2(416, 797), Vector2(120, 36))
	_place(_next_button, Vector2(548, 797), Vector2(140, 36))
	_place(_scene_button, Vector2(700, 797), Vector2(300, 36))
	_place(_restart_button, Vector2(1012, 797), Vector2(112, 36))
	_place(_zoom_label, Vector2(32, 841), Vector2(200, 26))
	_place(_zoom_slider, Vector2(232, 847), Vector2(354, 20))
	_place(_duration_label, Vector2(648, 841), Vector2(190, 26))
	_place(_duration_slider, Vector2(838, 847), Vector2(394, 20))
	_place(_hint, Vector2(32, 873), Vector2(1216, 24))
	_update_character_layers()
	queue_redraw()


func _place(control: Control, point: Vector2, extent: Vector2) -> void:
	control.position = point
	control.size = extent


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		var focused := get_viewport().gui_get_focus_owner()
		if focused != null and focused != _next_button:
			return
		_advance_dialogue()
		get_viewport().set_input_as_handled()


func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_ESCAPE: navigate.emit("command_link")
		KEY_C: _frame_speaker()
		KEY_W: _frame_wide()
		KEY_T: _cycle_speaker()
		KEY_L: _cycle_location()
		KEY_R: _restart()
		_: return
	get_viewport().set_input_as_handled()
