extends Control

signal navigate(route_id: String)

const TACTICAL_THEME = preload("res://presentation/ui/tactical_theme.gd")
var has_saved_game := false
var _background: Texture2D
var _play_button: Button
var _new_button: Button
var _lab_button: Button
var _heading_font: Font


func _ready() -> void:
	theme = TACTICAL_THEME.build()
	_heading_font = TACTICAL_THEME.heading_font()
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	var picture := Image.load_from_file("res://assets/locations/forward_command.png")
	if picture != null:
		picture.generate_mipmaps()
		_background = ImageTexture.create_from_image(picture)
	_label("COMMAND / MENU", Vector2(48, 27), Vector2(900, 20), 12, TACTICAL_THEME.MUTED)
	var title := _label("Command Link", Vector2(48, 49), Vector2(1120, 60), 48, TACTICAL_THEME.TEXT, true)
	title.uppercase = true
	_label("Mira, Lena, and Sera await your orders.", Vector2(50, 110), Vector2(1100, 26), 17, TACTICAL_THEME.MUTED)
	_label("BRIEFING PAUSED" if has_saved_game else "BEGIN THE MISSION", Vector2(72, 179), Vector2(740, 22), 12, TACTICAL_THEME.ACCENT)
	_label("Your command is waiting." if has_saved_game else "The squad is ready.", Vector2(72, 204), Vector2(744, 34), 27, TACTICAL_THEME.TEXT, true)
	_label("Resume with your squad, orders, and progress intact." if has_saved_game else "Lead the briefing, link with your squad, and choose a route.", Vector2(72, 243), Vector2(744, 24), 15, TACTICAL_THEME.MUTED)
	_play_button = _button("CONTINUE BRIEFING  →" if has_saved_game else "BEGIN BRIEFING  →", Vector2(864, 177 if has_saved_game else 197), Vector2(344, 50), func() -> void: navigate.emit("game"))
	_play_button.add_theme_font_override("font", _heading_font)
	_play_button.add_theme_font_size_override("font_size", 21)
	TACTICAL_THEME.style_primary(_play_button)
	_new_button = _button("START A NEW BRIEFING", Vector2(864, 236), Vector2(344, 30), func() -> void: navigate.emit("new_game"))
	_style_secondary(_new_button)
	_new_button.visible = has_saved_game
	_label("The mission continues when you are ready.", Vector2(72, 351), Vector2(1000, 40), 26, TACTICAL_THEME.TEXT, true)
	_label("Take a moment to review your orders, then return to the squad.", Vector2(72, 405), Vector2(1070, 52), 19, TACTICAL_THEME.MUTED)
	_lab_button = _button("OPEN PRESENTATION LAB", Vector2(72, 751), Vector2(390, 44), func() -> void: navigate.emit("game:presentation_lab"))
	_style_secondary(_lab_button)
	_label("Your briefing stays paused while another game is open.", Vector2(72, 815), Vector2(1050, 28), 15, TACTICAL_THEME.MUTED)

	queue_redraw()


func _style_secondary(button: Button) -> void:
	button.add_theme_font_override("font", _heading_font)
	button.add_theme_font_size_override("font_size", 17)
	button.add_theme_color_override("font_color", TACTICAL_THEME.MUTED)
	button.add_theme_color_override("font_hover_color", TACTICAL_THEME.TEXT)
	for state: String in ["normal", "hover", "pressed", "hover_pressed", "focus"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color.TRANSPARENT if state in ["normal", "focus"] else _alpha(TACTICAL_THEME.TEXT, 0.035)
		style.border_color = _alpha(TACTICAL_THEME.MUTED, 0.3) if state == "normal" else TACTICAL_THEME.ACCENT
		style.border_width_bottom = 1
		style.content_margin_top = 3
		style.content_margin_bottom = 3
		style.content_margin_left = 12
		style.content_margin_right = 12
		if state == "focus":
			style.set_border_width_all(1)
		button.add_theme_stylebox_override(state, style)


func _draw() -> void:
	if _background != null:
		var factor := maxf(size.x / _background.get_width(), size.y / _background.get_height())
		var extent := _background.get_size() * factor
		draw_texture_rect(_background, Rect2((size - extent) * 0.5, extent), false)
	draw_rect(Rect2(Vector2.ZERO, size), _alpha(TACTICAL_THEME.BG, 0.94))
	var divider := _alpha(TACTICAL_THEME.MUTED, 0.3)
	draw_line(Vector2(48, 145), Vector2(1232, 145), divider, 1.0)
	draw_line(Vector2(48, 145), Vector2(176, 145), TACTICAL_THEME.ACCENT, 2.0)
	var panel := PackedVector2Array([Vector2(60, 162), Vector2(1232, 162), Vector2(1232, 266), Vector2(1220, 278), Vector2(48, 278), Vector2(48, 174)])
	draw_colored_polygon(panel, _alpha(TACTICAL_THEME.BG.lightened(0.035), 0.96))
	var outline := panel.duplicate()
	outline.append(panel[0])
	draw_polyline(outline, divider, 1.0)
	draw_line(Vector2(48, 183), Vector2(48, 257), TACTICAL_THEME.ACCENT, 3.0)
	draw_line(Vector2(48, 343), Vector2(1232, 343), divider, 1.0)
	draw_line(Vector2(48, 852), Vector2(1232, 852), divider, 1.0)
	# Short brackets frame the menu without adding fictional telemetry.
	for x: float in [32.0, 1248.0]:
		var direction := 1.0 if x < 640.0 else -1.0
		draw_line(Vector2(x, 49), Vector2(x + direction * 8, 49), divider, 1.0)
		draw_line(Vector2(x, 49), Vector2(x, 111), divider, 1.0)


func _alpha(colour: Color, opacity: float) -> Color:
	return Color(colour.r, colour.g, colour.b, opacity)


func _label(value: String, point: Vector2, extent: Vector2, font_size: int, colour: Color, heading: bool = false) -> Label:
	return _child_label(self, value, point, extent, font_size, colour, heading)


func _child_label(parent: Control, value: String, point: Vector2, extent: Vector2, font_size: int, colour: Color, heading: bool = false) -> Label:
	var label := Label.new()
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", colour)
	if heading:
		label.add_theme_font_override("font", _heading_font)
	label.text = value
	label.position = point
	label.size = extent
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(label)
	return label


func _button(value: String, point: Vector2, extent: Vector2, action: Callable) -> Button:
	var button := Button.new()
	button.text = value
	button.position = point
	button.size = extent
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	button.pressed.connect(action)
	add_child(button)
	return button


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_ESCAPE:
		navigate.emit("game")
		get_viewport().set_input_as_handled()
