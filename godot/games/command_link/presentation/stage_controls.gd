extends RefCounted

## Command Link's local control construction and layout. The stage owns callback
## behavior, visibility and time; this builder creates the same child order and
## positions without choosing routes or advancing a presentation controller.


static func build_interface(host) -> void:
	host._title = host._label(host.stage_profile.display_title, 27, host.PAPER)
	host._subtitle = host._label("A moment, at your own pace.", 13, host.MUTED)
	host._location_title = host._label("", 27, host.PAPER)
	host._location_detail = host._label("", 13, host.WARM)
	host._line = host._label("", 25, host.PAPER, HORIZONTAL_ALIGNMENT_CENTER)
	host._speaker = host._label("", 15, host.WARM, HORIZONTAL_ALIGNMENT_CENTER)
	host._hint = host._label("", 14, host.MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	host._footer = host._label("", 12, host.MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	host._full_button = host._button("Full body", func() -> void: host._set_mode("full_body"))
	host._reach_button = host._button("Reach out", func() -> void: host._set_mode("reach_out"))
	host._dialogue_button = host._button("Dialogue", func() -> void: host._set_mode("dialogue"))
	host._manpu_button = host._button("Manpu gallery", func() -> void: host._set_mode("manpu_gallery"))
	host._next_button = host._button("Next →", host._advance_dialogue)
	host._blink_button = host._button("Close eyes", host._toggle_eyes)
	host._auto_button = host._button("Auto blink · on", host._toggle_natural_blink)
	host._restart_button = host._button("Restart", host._restart)
	host._scene_button = host._button("Change scene", host._change_scene)
	host._effect_target_button = host._button("", host._cycle_effect_target)
	host._effect_toggle_button = host._button("", host._toggle_character_effect)
	host._effect_strength_slider = HSlider.new()
	host._effect_strength_slider.min_value = 0.0
	host._effect_strength_slider.max_value = 100.0
	host._effect_strength_slider.step = 5.0
	host._effect_strength_slider.value_changed.connect(host._set_effect_strength)
	host._effect_strength_slider.tooltip_text = "Character effect strength. Zero restores the original appearance."
	host.add_child(host._effect_strength_slider)
	host._effect_strength_label = host._label("80%", 13, host.MUTED)
	host._effect_target_button.tooltip_text = "Choose which actor to adjust. Keyboard: T"
	host._effect_toggle_button.tooltip_text = "Toggle the selected actor between Normal and Hologram. Keyboard: E"
	host._blink_button.tooltip_text = "Open or close her eyes. Keyboard: B"
	host._auto_button.tooltip_text = "Allow a gentle automatic blink. Keyboard: N"
	host._full_button.tooltip_text = "Full-body view. Keyboard: 1"
	host._reach_button.tooltip_text = "Reach-out view. Keyboard: 2"
	host._dialogue_button.tooltip_text = "Multi-actor dialogue. Keyboard: 3"
	host._manpu_button.tooltip_text = "Static manpu / emanata marks. Keyboard: 4"
	host._next_button.tooltip_text = "Next line. Keyboard: Space or Enter"
	host._restart_button.tooltip_text = "Begin again. Keyboard: R"
	host._scene_button.tooltip_text = "Visit another place. Keyboard: L"


static func label(host, value: String, font_size: int, colour: Color,
		alignment: HorizontalAlignment = HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var made := Label.new()
	made.text = value
	made.add_theme_font_size_override("font_size", font_size)
	made.add_theme_color_override("font_color", colour)
	made.horizontal_alignment = alignment
	made.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	made.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	host.add_child(made)
	return made


static func button(host, value: String, pressed: Callable) -> Button:
	var made := Button.new()
	made.text = value
	made.add_theme_font_size_override("font_size", 14)
	made.pressed.connect(pressed)
	host.add_child(made)
	return made


static func layout_interface(host) -> void:
	if host._title == null:
		return
	host._title.position = Vector2(32, 22)
	host._title.size = Vector2(host.size.x - 296, 40)
	host._title.add_theme_font_size_override("font_size", 27)
	host._subtitle.position = Vector2(33, 62)
	host._subtitle.size = Vector2(host.size.x - 297, 24)
	host._location_title.position = host._title.position
	host._location_title.size = host._title.size
	host._location_title.add_theme_font_size_override("font_size", 27)
	host._location_detail.position = host._subtitle.position
	host._location_detail.size = host._subtitle.size
	host._restart_button.position = Vector2(host.size.x - 126, 32)
	host._restart_button.size = Vector2(94, 36)
	host._scene_button.position = Vector2(host.size.x - 258, 32)
	host._scene_button.size = Vector2(120, 36)
	host._line.position = Vector2(32, host.size.y - 197)
	host._line.size = Vector2(host.size.x - 64, 54)
	host._line.add_theme_font_size_override("font_size", 25)
	host._speaker.position = Vector2(32, host.size.y - 222)
	host._speaker.size = Vector2(host.size.x - 64, 25)
	host._hint.position = Vector2(32, host.size.y - 142)
	host._hint.size = Vector2(host.size.x - 64, 30)
	var left: float = (host.size.x - 556.0) * 0.5
	for button: Button in [host._full_button, host._reach_button, host._dialogue_button, host._manpu_button]:
		button.position = Vector2(left, host.size.y - 99)
		button.size = Vector2(130.0, 38)
		left += 142.0
	var secondary: Array[Button] = []
	if host._mode in ["full_body", "dialogue"]:
		secondary.assign([host._blink_button, host._auto_button])
	if host._mode == "dialogue":
		secondary.append(host._next_button)
	var total := 0.0
	for button: Button in secondary:
		total += 136.0 if button == host._auto_button else 116.0
	total += maxf(0.0, secondary.size() - 1) * 12.0
	left = (host.size.x - total) * 0.5
	for button: Button in secondary:
		var width := 136.0 if button == host._auto_button else 116.0
		button.position = Vector2(left, host.size.y - 48)
		button.size = Vector2(width, 32)
		button.add_theme_font_size_override("font_size", 13)
		left += width + 12.0
	var effect_left: float = (host.size.x - 470.0) * 0.5
	host._effect_target_button.position = Vector2(effect_left, host.size.y - 139)
	host._effect_target_button.size = Vector2(112, 28)
	host._effect_toggle_button.position = Vector2(effect_left + 122, host.size.y - 139)
	host._effect_toggle_button.size = Vector2(142, 28)
	host._effect_strength_slider.position = Vector2(effect_left + 280, host.size.y - 136)
	host._effect_strength_slider.size = Vector2(130, 22)
	host._effect_strength_label.position = Vector2(effect_left + 424, host.size.y - 139)
	host._effect_strength_label.size = Vector2(46, 28)
	host._footer.position = Vector2(32, host.size.y - 46)
	host._footer.size = Vector2(host.size.x - 64, 25)
