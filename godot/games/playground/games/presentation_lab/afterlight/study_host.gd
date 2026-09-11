extends Control

## Presentation Lab's concrete Afterlight study host and rendering adapter.
## Camera timing and animation sampling are reusable; this interface is not.
signal navigate(route_id: String)
signal language_changed(language: String)
@export var study_mode := false
const WALKING = preload("res://addons/game_presentation/camera/walking_approach.gd")
const EYE = preload("res://addons/game_presentation/transitions/eye_transition.gd")
const EYE_SHADER = preload("res://addons/game_presentation/effects/shaders/eye_transition.gdshader")
const ANIMATION = preload("res://addons/game_presentation/motion/presentation_animation.gd")
const CONTENT_ADAPTER = preload("res://games/bishoujo_afterlight/content_adapter.gd")
const DESIGN_SIZE := Vector2(1280, 900)
const INK := Color("f4eee6")
const MUTED := Color("c7bccd")
const ACCENT := Color("e4bbac")
const REVEAL_TRACKS := {"opacity": [[0.0, 0.0], [1.0, 1.0]]}
var content: Dictionary = {}
var saved_state: Dictionary = {}
var text_set: RefCounted
var content_factory: Callable
var _language_button: Button
var _text_bindings: Array[Dictionary] = []
var _camera = WALKING.new()
var _eye = EYE.new()
var _eye_layer: ColorRect
var _eye_material: ShaderMaterial
var _load_errors: Array[String] = []
var _backgrounds: Array[Texture2D] = []
var _background_index := 0
var _guest_id := ""
var _guest_textures: Dictionary = {}
var _guest_close_textures: Dictionary = {}
var _guest_buttons: Dictionary = {}
var _background_button: Button
var _base_background := Rect2()
var _phase := "walking"
var _choice_index := -1
var _reveal_elapsed := 0.0
var _actor: TextureRect
var _ui: Control
var _dialogue_panel: Panel
var _speaker: Label
var _line: Label
var _status: Label
var _location: Label
var _next_button: Button
var _skip_button: Button
var _study_button: Button
var _eye_study_button: Button
var _return_button: Button
var _replay_button: Button
var _choice_buttons: Array[Button] = []
var _sliders: Dictionary = {}
var _slider_values: Dictionary = {}


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_actor = TextureRect.new()
	_actor.name = "Guest"
	_actor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_actor.stretch_mode = TextureRect.STRETCH_SCALE
	_actor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_actor.hide()
	add_child(_actor)
	# The mask covers scenery and actors. This host's UI stays above it.
	_eye_layer = ColorRect.new()
	_eye_layer.name = "EyeTransitionMask"
	_eye_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_eye_material = ShaderMaterial.new()
	_eye_material.shader = EYE_SHADER
	_eye_material.set_shader_parameter("viewport_size", DESIGN_SIZE)
	_eye_material.set_shader_parameter("edge_softness", float(content.get("eye_mask", {}).get("edge_softness", 28.0)))
	_eye_layer.material = _eye_material
	add_child(_eye_layer)
	_eye_layer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_guest_id = str(content.get("default_guest_id", ""))
	_build_ui()
	if content.is_empty():
		_load_errors.append("Afterlight's root must supply its content before the route enters the tree.")
	else:
		for background: Dictionary in content["backgrounds"]:
			_backgrounds.append(_load_texture(background["path"]))
		for guest: Dictionary in content["guests"]:
			var guest_id := str(guest["id"])
			_guest_textures[guest_id] = _load_texture(guest["path"])
			if not str(guest.get("eye_close_path", "")).is_empty():
				_guest_close_textures[guest_id] = _load_texture(guest["eye_close_path"])
		if not _guest_textures.has(_guest_id):
			_load_errors.append("Afterlight's default guest must name an authored cast profile.")
		else:
			_bind_guest()
	if _load_errors.is_empty():
		_load_errors.append_array(_camera.configure(content["approach"]))
		_load_errors.append_array(_eye.configure(content["eye_transition"]))
		if saved_state.is_empty() or study_mode:
			replay_approach()
		else:
			_restore_game()
	_update_ui()
	_update_visuals()


func _load_texture(path: String) -> Texture2D:
	var loaded := CONTENT_ADAPTER.load_texture(content.get("content_loader", CONTENT_ADAPTER.LOCAL_CONTENT.new()), path)
	_load_errors.append_array(loaded.errors)
	return loaded.resource


func guest_profile() -> Dictionary:
	for guest: Dictionary in content.get("guests", []):
		if str(guest["id"]) == _guest_id:
			return guest
	return {}


func _bind_guest() -> void:
	_actor.texture = _guest_textures.get(_guest_id)


func _select_guest(guest_id: String) -> void:
	if not _load_errors.is_empty() or not _guest_textures.has(guest_id):
		return
	if guest_id == _guest_id:
		_update_guest_picker()
		return
	_guest_id = guest_id
	_bind_guest()
	replay_approach()


func _update_guest_picker() -> void:
	for guest_id: String in _guest_buttons:
		_guest_buttons[guest_id].set_pressed_no_signal(guest_id == _guest_id)
		_guest_buttons[guest_id].text = _text("guest." + guest_id + ".name")


func _build_guest_picker() -> void:
	_label_text("ui.meet", Rect2(642, 141, 64, 30), 16, INK)
	var guests: Array = content.get("guests", [])
	for index in guests.size():
		var guest: Dictionary = guests[index]
		var guest_id := str(guest["id"])
		var button := _button(str(guest["name"]), Rect2(710 + index * 112, 134, 102, 40), _select_guest.bind(guest_id))
		button.toggle_mode = true
		_guest_buttons[guest_id] = button
	_background_button = _button_text("ui.change_backdrop", Rect2(1030, 184, 190, 40), _change_background)


func _bind_background() -> void:
	var source := _backgrounds[_background_index].get_size()
	var factor := maxf(DESIGN_SIZE.x / source.x, DESIGN_SIZE.y / source.y)
	_base_background = Rect2((DESIGN_SIZE - source * factor) * 0.5, source * factor)
	_load_errors.append_array(_camera.initialize(DESIGN_SIZE, _base_background))


func replay_approach() -> void:
	if not _load_errors.is_empty():
		return
	_bind_background()
	_load_errors.append_array(_camera.start())
	_eye.clear()
	_phase = "walking"
	_choice_index = -1
	_reveal_elapsed = 0.0
	_update_ui()
	_update_visuals()


func skip_approach() -> void:
	if not _load_errors.is_empty() or not _camera.is_active():
		return
	_camera.skip()
	_finish_approach()
	_update_visuals()


func _finish_approach() -> void:
	_phase = "held" if study_mode else "eye_transition"
	_reveal_elapsed = 0.45
	if not study_mode:
		_load_errors.append_array(_eye.start("blink"))
	_update_ui()


func skip_eye_transition() -> void:
	if not _load_errors.is_empty() or _phase != "eye_transition":
		return
	_eye.skip()
	_phase = "greeting"
	_update_ui()
	_update_visuals()


func _skip_presentation() -> void:
	if _phase == "eye_transition":
		skip_eye_transition()
	else:
		skip_approach()


func camera_sample() -> Dictionary:
	return _camera.sample()


func _camera_rect(rect: Rect2) -> Rect2:
	var pose: Dictionary = camera_sample()
	var zoom := float(pose["zoom"])
	return Rect2(rect.position * zoom + Vector2(float(pose["offset_x"]), float(pose["offset_y"])), rect.size * zoom)


func presented_background_rect() -> Rect2:
	return _camera_rect(_base_background)


func _process(delta: float) -> void:
	if not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0:
		return
	var remaining := delta
	if _camera.is_active():
		var before: Dictionary = _camera.get_state()
		var shot_remaining := float(before["shot_settings"]["duration_seconds"]) - float(before["elapsed"])
		_camera.advance(remaining)
		remaining = maxf(0.0, remaining - shot_remaining)
		if not _camera.is_active():
			_finish_approach()
	if _phase == "eye_transition":
		_eye.advance(remaining)
		if not _eye.is_active():
			_phase = "greeting"
			_update_ui()
	elif _phase != "walking":
		_reveal_elapsed = minf(0.45, _reveal_elapsed + remaining)
	_update_visuals()


func _update_visuals() -> void:
	if _actor == null:
		return
	var eye_pose: Dictionary = _eye.sample()
	var guest_revealed := _phase != "walking" and (_phase != "eye_transition" or bool(eye_pose["reached_closed"]))
	_actor.visible = _load_errors.is_empty() and not study_mode and guest_revealed
	_eye_layer.visible = _load_errors.is_empty() and float(eye_pose["openness"]) < 1.0
	_eye_material.set_shader_parameter("openness", float(eye_pose["openness"]))
	if _actor.visible:
		var height := 700.0
		var width := height * _actor.texture.get_width() / _actor.texture.get_height()
		var rect := _camera_rect(Rect2(470.0 - width * 0.5, 177.0, width, height))
		_actor.position = rect.position
		_actor.size = rect.size
		_actor.modulate.a = float(ANIMATION.sample(REVEAL_TRACKS, _reveal_elapsed, 0.45)["opacity"])
	if _load_errors.is_empty() and study_mode:
		var progress := float(camera_sample()["progress"])
		_status.text = _text("status.walking_progress", {"progress": roundi(progress * 100.0)}) if _camera.is_active() else _text("status.arrived")
	queue_redraw()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if not _load_errors.is_empty() or _backgrounds.is_empty():
		return
	draw_texture_rect(_backgrounds[_background_index], presented_background_rect(), false)
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color(0.07, 0.045, 0.1, 0.12))


func _next() -> void:
	if not _load_errors.is_empty():
		return
	if _phase == "walking":
		skip_approach()
	elif _phase == "eye_transition":
		skip_eye_transition()
	elif _phase == "greeting":
		_phase = "answer"
	elif _phase == "ending":
		replay_approach()
	_update_ui()


func _choose(index: int) -> void:
	if _phase != "answer" or index < 0 or index >= _choice_buttons.size() or not _load_errors.is_empty():
		return
	_choice_index = index
	_phase = "ending"
	_update_ui()


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode == KEY_F6:
		_toggle_language()
		get_viewport().set_input_as_handled()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("menu")
		get_viewport().set_input_as_handled()
	elif not study_mode and event.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		var focused := get_viewport().gui_get_focus_owner()
		if focused != null and focused != _next_button and focused != _skip_button:
			return
		_next()
		get_viewport().set_input_as_handled()


func save_game() -> Dictionary:
	return {"phase": _phase, "choice_index": _choice_index, "background_index": _background_index,
		"guest_id": _guest_id, "reveal_elapsed": _reveal_elapsed, "camera": _camera.get_state(), "eye_transition": _eye.get_state(), "language": get_language()}


func _restore_game() -> void:
	_guest_id = str(saved_state.get("guest_id", content["default_guest_id"]))
	if not _guest_textures.has(_guest_id):
		_load_errors.append("Cannot resume an unknown Afterlight guest.")
		return
	_bind_guest()
	_background_index = int(saved_state.get("background_index", 0))
	_phase = str(saved_state.get("phase", "walking"))
	_choice_index = int(saved_state.get("choice_index", -1))
	_reveal_elapsed = float(saved_state.get("reveal_elapsed", 0.0))
	if _background_index < 0 or _background_index >= _backgrounds.size() or _phase not in ["walking", "eye_transition", "greeting", "answer", "ending"] or not is_finite(_reveal_elapsed) or _reveal_elapsed < 0.0 or _reveal_elapsed > 0.45:
		_load_errors.append("Cannot resume this Afterlight scene state.")
		return
	if _phase == "ending" and (_choice_index < 0 or _choice_index >= content["choices"].size()):
		_load_errors.append("Cannot resume an unknown Afterlight choice.")
		return
	_bind_background()
	_load_errors.append_array(_camera.restore(saved_state.get("camera", {})))
	if not _load_errors.is_empty():
		return
	var restored: Dictionary = _camera.get_state()
	var view: Array = restored["viewport_size"]
	var bounds: Array = restored["background_rect"]
	var saved_bounds := Rect2(float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
	if not Vector2(float(view[0]), float(view[1])).is_equal_approx(DESIGN_SIZE) or not saved_bounds.is_equal_approx(_base_background):
		_load_errors.append("The saved camera does not match this background and canvas.")
	if not restored["initialized"] or not restored["has_shot"]:
		_load_errors.append("The saved scene requires an initialized approach shot.")
	if _load_errors.is_empty() and (_camera.is_active() != (_phase == "walking")):
		_load_errors.append("The saved approach and story phase do not agree.")
	if saved_state.has("eye_transition"):
		_load_errors.append_array(_eye.restore(saved_state["eye_transition"]))
	var eye_pose: Dictionary = _eye.sample()
	if _phase == "eye_transition":
		if not _eye.is_active() or _eye.get_state()["mode"] != "blink":
			_load_errors.append("The saved reveal requires an active Blink Transition.")
	elif _eye.is_active() or float(eye_pose["openness"]) != 1.0:
		_load_errors.append("The saved story requires an open, idle eye mask.")


func _tune(value: float, key: String) -> void:
	_load_errors.append_array(_camera.configure({key: value}))
	_slider_values[key].text = _value_text(key, value)


func _value_text(key: String, value: float) -> String:
	match key:
		"duration_seconds": return _text("unit.seconds", {"value": "%.1f" % value})
		"target_zoom": return _text("unit.zoom", {"value": "%.2f" % value})
		"bob_amplitude": return _text("unit.pixels", {"value": "%.0f" % value})
		_: return _text("unit.per_second", {"value": "%.1f" % value})


func _reset_study() -> void:
	_load_errors.append_array(_camera.configure(content["approach"]))
	for key: String in _sliders:
		_sliders[key].set_value_no_signal(float(content["approach"][key]))
		_slider_values[key].text = _value_text(key, float(content["approach"][key]))
	replay_approach()


func _change_background() -> void:
	if not _load_errors.is_empty() or _backgrounds.is_empty():
		return
	_background_index = (_background_index + 1) % _backgrounds.size()
	replay_approach()


func _update_ui() -> void:
	if _line == null:
		return
	if not _load_errors.is_empty():
		_line.text = _text("error.scene_load") + "\n" + "\n".join(_load_errors)
		_line.add_theme_font_size_override("font_size", 16)
		_line.position = Vector2(64, 706)
		_line.size = Vector2(1150, 158)
		for child: Node in _ui.get_children():
			if child is BaseButton: child.disabled = true
			if child is Slider: child.editable = false
		if _return_button != null: _return_button.disabled = false
		return
	if content.is_empty():
		return
	_update_guest_picker()
	_location.text = content["backgrounds"][_background_index]["name"]
	_skip_button.visible = _camera.is_active() or _phase == "eye_transition"
	if study_mode:
		_line.text = _text("study.walking.instructions")
		return
	var showing_dialogue := _phase != "eye_transition"
	_dialogue_panel.visible = showing_dialogue
	_speaker.visible = showing_dialogue
	_line.visible = showing_dialogue
	_status.visible = showing_dialogue
	_skip_button.text = _text("ui.skip_transition" if _phase == "eye_transition" else "ui.skip_approach")
	_status.text = _text("status.meeting") if _phase == "walking" else _text("status.moment", {"guest": str(guest_profile()["name"])})
	_speaker.text = "" if _phase == "walking" else str(guest_profile()["name"])
	_line.text = str(content["arrival"])
	if _phase == "greeting": _line.text = str(content["greeting"])
	if _phase == "answer": _line.text = str(content["question"])
	if _phase == "ending": _line.text = str(content["choices"][_choice_index]["reply"])
	_next_button.visible = _phase in ["greeting", "ending"]
	_next_button.text = _text("ui.walk_again" if _phase == "ending" else "ui.next")
	for index in _choice_buttons.size():
		_choice_buttons[index].visible = _phase == "answer"
		_choice_buttons[index].text = str(content["choices"][index]["label"])


func _build_ui() -> void:
	_ui = Control.new()
	_ui.name = "AfterlightInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(32, 24, 1216, 96), Color(0.09, 0.075, 0.12, 0.84))
	_label_text("game.kicker", Rect2(56, 36, 300, 18), 12, ACCENT)
	_label_text("game.title", Rect2(54, 51, 400, 53), 37, INK)
	_location = _label("", Rect2(634, 52, 202, 40), 18, INK)
	if study_mode:
		_build_language_picker(Rect2(674, 570, 240, 38))
		_return_button = _button_text("ui.return_to_story", Rect2(1030, 49, 190, 44), func() -> void: navigate.emit("game:bishoujo_afterlight"))
		_eye_study_button = _button_text("ui.eye_transitions", Rect2(840, 49, 178, 44), func() -> void: navigate.emit("eye_study"))
		_panel(Rect2(40, 628, 1200, 244), Color(0.09, 0.075, 0.12, 0.94))
		_status = _label_text("study.walking.title", Rect2(64, 645, 700, 30), 22, INK)
		_line = _label("", Rect2(64, 678, 1150, 25), 14, MUTED)
		_build_tuning()
		_replay_button = _button_text("ui.replay", Rect2(64, 808, 140, 44), replay_approach)
		_skip_button = _button_text("ui.skip", Rect2(218, 808, 140, 44), skip_approach)
		_button_text("ui.reset", Rect2(372, 808, 140, 44), _reset_study)
		_button("Presentation Lab", Rect2(542, 808, 220, 44), func() -> void: navigate.emit("menu"))
		_button_text("ui.change_backdrop", Rect2(1000, 564, 240, 44), _change_background)
	else:
		_build_language_picker(Rect2(674, 184, 138, 40))
		_build_guest_picker()
		_study_button = _button_text("ui.camera_study", Rect2(840, 49, 178, 44), func() -> void: navigate.emit("approach_study"))
		_eye_study_button = _button_text("ui.eye_transitions", Rect2(1030, 49, 190, 44), func() -> void: navigate.emit("eye_study"))
		_dialogue_panel = _panel(Rect2(40, 658, 1200, 214), Color(0.09, 0.075, 0.12, 0.94))
		_status = _label("", Rect2(64, 679, 700, 22), 13, MUTED)
		_speaker = _label("", Rect2(64, 704, 400, 33), 23, ACCENT)
		_line = _label("", Rect2(64, 742, 1146, 57), 23, INK)
		_next_button = _button_text("ui.next", Rect2(1040, 810, 174, 43), _next)
		_skip_button = _button_text("ui.skip_approach", Rect2(1014, 810, 200, 43), _skip_presentation)
		for index in 2:
			_choice_buttons.append(_button("", Rect2(64 + index * 584, 810, 568, 43), _choose.bind(index)))
		_next_button.hide()
		for button: Button in _choice_buttons: button.hide()


func _build_tuning() -> void:
	var controls := [
		["duration_seconds", "study.walking.duration", 1.0, 15.0, 0.5, 5.5],
		["target_zoom", "study.walking.final_zoom", 1.0, 1.8, 0.02, 1.24],
		["bob_amplitude", "study.walking.step_height", 0.0, 40.0, 1.0, 12.0],
		["bob_cycles_per_second", "study.walking.step_pace", 0.5, 3.0, 0.1, 1.6],
	]
	for index in controls.size():
		var spec: Array = controls[index]
		var configured := float(content.get("approach", {}).get(spec[0], spec[5]))
		var x := 64.0 + index * 292.0
		_label_text(spec[1], Rect2(x, 717, 160, 25), 16, INK)
		var value := _label(_value_text(spec[0], configured), Rect2(x + 158, 717, 96, 25), 15, ACCENT)
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		var slider := HSlider.new()
		slider.position = Vector2(x, 756)
		slider.size = Vector2(252, 24)
		slider.min_value = spec[2]
		slider.max_value = spec[3]
		slider.step = spec[4]
		slider.value = configured
		slider.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		slider.value_changed.connect(_tune.bind(spec[0]))
		_ui.add_child(slider)
		_sliders[spec[0]] = slider
		_slider_values[spec[0]] = value


func _panel(rect: Rect2, fill: Color) -> Panel:
	var panel := Panel.new()
	panel.position = rect.position
	panel.size = rect.size
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = Color(0.8, 0.68, 0.66, 0.35)
	style.set_border_width_all(1)
	style.set_corner_radius_all(8)
	panel.add_theme_stylebox_override("panel", style)
	_ui.add_child(panel)
	return panel


func _label(text: String, rect: Rect2, font_size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text
	label.position = rect.position
	label.size = rect.size
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(label)
	return label


func _button(text: String, rect: Rect2, action: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.position = rect.position
	button.size = rect.size
	button.add_theme_font_size_override("font_size", 17)
	button.add_theme_color_override("font_color", INK)
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	for state: String in ["normal", "hover", "pressed", "focus"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("52404d") if state in ["hover", "pressed"] else Color("302a38")
		style.border_color = ACCENT if state in ["hover", "focus"] else Color("76616b")
		style.set_border_width_all(2 if state == "focus" else 1)
		style.set_corner_radius_all(5)
		button.add_theme_stylebox_override(state, style)
	button.pressed.connect(action)
	_ui.add_child(button)
	return button


func _text(key: String, values: Dictionary = {}) -> String:
	return text_set.text(key, values) if text_set != null else "[" + key + "]"


func get_language() -> String:
	return text_set.get_language() if text_set != null else "en"


func set_language(language: String) -> Array[String]:
	if text_set == null or not content_factory.is_valid():
		return ["The host must bind its text set and content resolver first."]
	var errors: Array[String] = text_set.set_language(language)
	if not errors.is_empty():
		return errors
	content = content_factory.call(text_set)
	for binding: Dictionary in _text_bindings:
		if is_instance_valid(binding["node"]):
			binding["node"].text = _text(binding["key"], binding["values"])
	_update_language_picker()
	_refresh_language()
	language_changed.emit(language)
	return []


func _refresh_language() -> void:
	_update_ui()
	for key: String in _slider_values:
		_slider_values[key].text = _value_text(key, _sliders[key].value)
	_update_visuals()


func _toggle_language() -> void:
	set_language("ko" if get_language() == "en" else "en")
	get_viewport().gui_release_focus()


func _build_language_picker(rect: Rect2) -> void:
	_language_button = _button("", rect, _toggle_language)
	_language_button.name = "LanguageSwitch"
	_update_language_picker()


func _update_language_picker() -> void:
	if _language_button != null:
		_language_button.text = _text("ui.language_target")
		_language_button.tooltip_text = _text("ui.language") + " · F6"


func _label_text(key: String, rect: Rect2, font_size: int, color: Color, values: Dictionary = {}) -> Label:
	var node := _label(_text(key, values), rect, font_size, color)
	_text_bindings.append({"node": node, "key": key, "values": values.duplicate()})
	return node


func _button_text(key: String, rect: Rect2, action: Callable) -> Button:
	var node := _button(_text(key), rect, action)
	_text_bindings.append({"node": node, "key": key, "values": {}})
	return node
