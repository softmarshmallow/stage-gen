extends "res://lab/study_host.gd"

## The lab owns selection, UI, and time. Afterlight's concrete renderer adapts
## the reusable exit/focus controllers to prepared actor textures and geometry.
const ACTOR_CAST = preload("res://cast_stage.gd")
const MODES: Array[String] = ["walk_away", "walk_away_right", "restless_bounce", "quick_approach"]
const APPROACH_CURVES: Array[String] = ["ease_in_out", "linear", "spring"]
var _cast_layer: Control
var _selected_mode := "walk_away"
var _mode_buttons: Dictionary = {}
var _motion_durations: Dictionary = {}
var _play_button: Button
var _pause_button: Button
var _reset_button: Button
var _hint: Label
var _playing := false
var _paused := false
var _has_played := false
var _motion_elapsed := 0.0
var _approach_settings := {"duration_seconds": 0.32, "stop_distance": 280.0,
	"curve": "ease_in_out", "frequency": 1.5, "damping_ratio": 0.8}
var _mover_on_left := true
var _approach_controls: Array[Control] = []
var _approach_duration_slider: HSlider
var _approach_gap_slider: HSlider
var _approach_duration_label: Label
var _approach_gap_label: Label
var _approach_curve_button: Button
var _approach_direction_button: Button


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_guest_id = str(content.get("default_guest_id", ""))
	_approach_settings.merge(content.get("quick_approach", {}), true)
	_motion_durations["quick_approach"] = float(_approach_settings["duration_seconds"])
	for profile: Dictionary in content.get("guests", []):
		_guest_textures[str(profile["id"])] = _load_texture(str(profile["path"]))
	for background: Dictionary in content.get("backgrounds", []):
		_backgrounds.append(_load_texture(str(background["path"])))
	_load_durations()
	_cast_layer = ACTOR_CAST.new()
	_cast_layer.name = "ActorMotionCast"
	add_child(_cast_layer)
	_load_errors.append_array(_cast_layer.initialize(content.get("guests", []), _guest_textures, content.get("manpu_textures", {})))
	_build_motion_ui()
	_reset_motion()


func _load_durations() -> void:
	for path: String in [ACTOR_CAST.EXIT_CATALOG, ACTOR_CAST.FOCUS_CATALOG]:
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
		if not (parsed is Dictionary) or not (parsed.get("presets") is Array):
			_load_errors.append("The motion study requires valid prepared preset catalogs.")
			continue
		for preset: Dictionary in parsed["presets"]:
			var mode := str(preset.get("id", ""))
			if mode in MODES:
				_motion_durations[mode] = float(preset["duration_seconds"])
	for mode: String in MODES:
		if mode == "quick_approach": continue
		if not _motion_durations.has(mode):
			_load_errors.append("The motion study requires the prepared preset: " + mode)


func _select_guest(guest_id: String) -> void:
	if not _guest_textures.has(guest_id):
		return
	_guest_id = guest_id
	_reset_motion()


func _select_motion(mode: String) -> void:
	if mode not in MODES:
		return
	_selected_mode = mode
	_reset_motion()


func _reset_motion() -> void:
	_playing = false
	_paused = false
	_has_played = false
	_motion_elapsed = 0.0
	if _load_errors.is_empty():
		if _selected_mode == "quick_approach":
			var partner := _approach_partner()
			if partner.is_empty():
				_load_errors.append("Quick Approach requires two distinct prepared actors.")
			else:
				var pair := [_guest_id, partner] if _mover_on_left else [partner, _guest_id]
				_load_errors.append_array(_cast_layer.set_cast(pair))
		else:
			_load_errors.append_array(_cast_layer.set_cast([_guest_id]))
		_cast_layer.present(Transform2D.IDENTITY)
	_update_motion_ui()
	queue_redraw()


func _play_motion() -> void:
	if not _load_errors.is_empty():
		return
	_reset_motion()
	var errors: Array[String] = []
	if _selected_mode == "quick_approach":
		errors = _cast_layer.approach_actor(_guest_id, _approach_partner(), _approach_settings)
	elif _selected_mode == "restless_bounce":
		errors = _cast_layer.focus(_guest_id, _selected_mode, true)
	else:
		errors = _cast_layer.dismiss(_guest_id, _selected_mode)
	_load_errors.append_array(errors)
	_playing = errors.is_empty()
	_has_played = _playing
	_cast_layer.present(Transform2D.IDENTITY)
	_update_motion_ui()


func _toggle_motion_pause() -> void:
	if not _playing:
		return
	_paused = not _paused
	_update_motion_ui()


func _process(delta: float) -> void:
	if not _load_errors.is_empty() or not _playing or _paused or not is_finite(delta) or delta <= 0.0:
		return
	var duration := float(_motion_durations[_selected_mode])
	_cast_layer.advance(delta)
	_motion_elapsed = minf(duration, _motion_elapsed + delta)
	if _motion_elapsed >= duration:
		_playing = false
	_cast_layer.present(Transform2D.IDENTITY)
	_update_motion_ui()


func motion_state() -> Dictionary:
	return {"actor_id": _guest_id, "mode": _selected_mode, "elapsed": _motion_elapsed,
		"duration": float(_motion_durations.get(_selected_mode, 0.0)), "playing": _playing,
		"paused": _paused, "has_played": _has_played,
		"partner_id": _approach_partner() if _selected_mode == "quick_approach" else "",
		"mover_on_left": _mover_on_left, "approach_settings": _approach_settings.duplicate()}


func _approach_partner() -> String:
	var guests: Array = content.get("guests", [])
	for index in guests.size():
		if str(guests[index]["id"]) == _guest_id and guests.size() > 1:
			return str(guests[(index + 1) % guests.size()]["id"])
	return ""


func _set_approach_duration(value: float) -> void:
	_approach_settings["duration_seconds"] = value
	_motion_durations["quick_approach"] = value
	_reset_motion()


func _set_approach_gap(value: float) -> void:
	_approach_settings["stop_distance"] = value
	_reset_motion()


func _cycle_approach_curve() -> void:
	var index := APPROACH_CURVES.find(str(_approach_settings["curve"]))
	_approach_settings["curve"] = APPROACH_CURVES[(index + 1) % APPROACH_CURVES.size()]
	_reset_motion()


func _toggle_approach_direction() -> void:
	_mover_on_left = not _mover_on_left
	_reset_motion()


func _build_motion_ui() -> void:
	_ui = Control.new()
	_ui.name = "ActorMotionStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(32, 24, 1216, 96), Color("211b28"))
	_label_text("game.kicker", Rect2(56, 36, 600, 18), 12, ACCENT)
	_label_text("study.motion.title", Rect2(54, 55, 650, 49), 31, INK)
	_build_language_picker(Rect2(758, 52, 248, 40))
	_return_button = _button_text("ui.effects_menu", Rect2(1030, 49, 190, 44), func() -> void: navigate.emit("effects_menu"))
	var guests: Array = content.get("guests", [])
	for index in guests.size():
		var actor_id := str(guests[index]["id"])
		var button := _button(str(guests[index]["name"]), Rect2(56 + index * 294, 138, 282, 40), _select_guest.bind(actor_id))
		button.toggle_mode = true
		_guest_buttons[actor_id] = button
	_panel(Rect2(32, 590, 1216, 286), Color("211b28"))
	_status = _label("", Rect2(56, 604, 1168, 31), 22, INK)
	for index in MODES.size():
		var mode := MODES[index]
		var button := _button_text("study.motion." + mode, Rect2(56 + index * 294, 649, 282, 44), _select_motion.bind(mode))
		button.toggle_mode = true
		_mode_buttons[mode] = button
	_build_approach_controls()
	_play_button = _button_text("study.motion.play", Rect2(56, 779, 200, 44), _play_motion)
	_pause_button = _button_text("ui.pause", Rect2(272, 779, 200, 44), _toggle_motion_pause)
	_reset_button = _button_text("study.motion.reset", Rect2(488, 779, 250, 44), _reset_motion)
	_hint = _label("", Rect2(56, 841, 1168, 25), 16, MUTED)


func _build_approach_controls() -> void:
	_approach_duration_label = _label("", Rect2(56, 707, 264, 26), 17, INK)
	_approach_gap_label = _label("", Rect2(338, 707, 264, 26), 17, INK)
	_approach_duration_slider = HSlider.new()
	_approach_duration_slider.name = "ApproachDurationSlider"
	_approach_duration_slider.position = Vector2(56, 736)
	_approach_duration_slider.size = Vector2(264, 26)
	_approach_duration_slider.min_value = 0.15
	_approach_duration_slider.max_value = 1.2
	_approach_duration_slider.step = 0.01
	_approach_duration_slider.value = float(_approach_settings["duration_seconds"])
	_approach_duration_slider.value_changed.connect(_set_approach_duration)
	_ui.add_child(_approach_duration_slider)
	_approach_gap_slider = HSlider.new()
	_approach_gap_slider.name = "ApproachGapSlider"
	_approach_gap_slider.position = Vector2(338, 736)
	_approach_gap_slider.size = Vector2(264, 26)
	_approach_gap_slider.min_value = 180.0
	_approach_gap_slider.max_value = 420.0
	_approach_gap_slider.step = 5.0
	_approach_gap_slider.value = float(_approach_settings["stop_distance"])
	_approach_gap_slider.value_changed.connect(_set_approach_gap)
	_ui.add_child(_approach_gap_slider)
	_approach_curve_button = _button("", Rect2(620, 715, 290, 43), _cycle_approach_curve)
	_approach_curve_button.name = "ApproachCurve"
	_approach_direction_button = _button("", Rect2(928, 715, 292, 43), _toggle_approach_direction)
	_approach_direction_button.name = "ApproachDirection"
	_approach_controls.assign([_approach_duration_label, _approach_gap_label,
		_approach_duration_slider, _approach_gap_slider,
		_approach_curve_button, _approach_direction_button])


func _update_motion_ui() -> void:
	if _status == null:
		return
	_update_guest_picker()
	for mode: String in _mode_buttons:
		_mode_buttons[mode].set_pressed_no_signal(mode == _selected_mode)
	for control: Control in _approach_controls:
		control.visible = _selected_mode == "quick_approach"
	_approach_duration_label.text = _text("study.motion.approach_duration", {"value": "%.2f" % float(_approach_settings["duration_seconds"])})
	_approach_gap_label.text = _text("study.motion.approach_gap", {"value": int(_approach_settings["stop_distance"])})
	_approach_curve_button.text = _text("study.motion.approach_curve", {"value": _text("study.motion.curve." + str(_approach_settings["curve"]))})
	_approach_direction_button.text = _text("study.motion.approach_from_left" if _mover_on_left else "study.motion.approach_from_right")
	var phase := "idle"
	if _playing:
		phase = "paused" if _paused else "playing"
	elif _has_played:
		phase = "finished"
	_status.text = _text("study.motion.status", {"mode": _text("study.motion." + _selected_mode),
		"phase": _text("phase." + phase), "elapsed": "%.2f" % _motion_elapsed,
		"duration": "%.2f" % float(_motion_durations.get(_selected_mode, 0.0))})
	_hint.text = _text("study.motion.hint." + _selected_mode)
	_play_button.text = _text("ui.replay" if _has_played else "study.motion.play")
	_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
	_pause_button.disabled = not _playing
	if not _load_errors.is_empty():
		_status.text = "\n".join(_load_errors)
		_play_button.disabled = true
		_pause_button.disabled = true


func _refresh_language() -> void:
	_update_motion_ui()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if _backgrounds.is_empty() or _backgrounds[0] == null:
		return
	var texture := _backgrounds[0]
	var factor := maxf(DESIGN_SIZE.x / texture.get_width(), DESIGN_SIZE.y / texture.get_height())
	var extent := texture.get_size() * factor
	draw_texture_rect(texture, Rect2((DESIGN_SIZE - extent) * 0.5, extent), false)


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode == KEY_F6:
		_toggle_language()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
	else:
		return
	get_viewport().set_input_as_handled()
