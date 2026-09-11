extends Control

## Concrete laboratory navigation for Command Link. The mission does not own this browser.
signal navigate(route_id: String)
const DEMOS := [
	["characters", "Character expressions", "Standing poses, eye states, and automatic blinking."],
	["contact", "Fingertip contact", "Touch the offered fingertip."],
	["dialogue", "Multi-actor dialogue", "An exchange between three actors."],
	["actor_focus", "Actor Focus", "Bounce, scale, dimming, or no emphasis."],
	["manpu", "Manpu / emanata", "Reactions and eight painted marks."],
	["locations", "Locations", "Backgrounds and location titles."],
	["hologram", "Character visual effects", "Per-actor hologram controls."],
	["character_exit", "Character Exit", "Silhouette Fade and opacity fade."],
	["cast_transition", "Cast Transition", "Sequential exit, movement, and entrance."],
	["establishing_shot", "Establishing Shot", "Camera pan, zoom, and lens flare."],
	["dialogue_camera", "Dialogue Camera", "Directed speaker close-ups and wide framing."],
]
var collection := ""
var _demo_buttons: Dictionary = {}
var _collection_buttons: Dictionary = {}
var _story_buttons: Dictionary = {}


func _ready() -> void:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Apple SD Gothic Neo", "sans-serif"])
	theme = Theme.new()
	theme.default_font = font
	_label("COMMAND LINK LAB", Rect2(48, 35, 1184, 56), 38)
	_label("Focused experiments with prepared game fixtures. Story progress stays paused.", Rect2(50, 98, 1180, 34), 19)
	if collection == "command_link":
		_build_command_studies()
	else:
		_build_collections()
	_story_buttons["command_link"] = _button("Play Command Link", Rect2(48, 815, 360, 44), "game:command_link/game")
	if not collection.is_empty():
		_button("All collections", Rect2(872, 815, 360, 44), "menu")
	queue_redraw()


func _build_collections() -> void:
	_label("Choose a collection", Rect2(48, 172, 1184, 40), 25)
	_collection_buttons["command_link"] = _button("Command Link studies", Rect2(48, 250, 574, 240), "command_link")
	_label("Actor presentation, manpu, contact, transitions,\nlocation direction, and dialogue camera.", Rect2(76, 513, 518, 110), 21)


func _build_command_studies() -> void:
	_label("Command Link studies", Rect2(48, 157, 1184, 40), 25)
	for index in DEMOS.size():
		var entry: Array = DEMOS[index]
		var point := Vector2(48 + (index % 3) * 400, 224 + int(index / 3) * 137)
		var button := _button(str(entry[1]), Rect2(point, Vector2(384, 72)), "demos/" + str(entry[0]))
		button.tooltip_text = str(entry[2])
		_demo_buttons[str(entry[0])] = button
		_label(str(entry[2]), Rect2(point + Vector2(8, 80), Vector2(370, 45)), 16)


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, Vector2(1280, 900)), Color("171923"))
	draw_line(Vector2(48, 145), Vector2(1232, 145), Color("777d98"), 1)
	draw_line(Vector2(48, 792), Vector2(1232, 792), Color("777d98"), 1)


func _label(value: String, bounds: Rect2, font_size: int) -> Label:
	var label := Label.new()
	label.text = value
	label.position = bounds.position
	label.size = bounds.size
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", font_size)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(label)
	return label


func _button(value: String, bounds: Rect2, route_id: String) -> Button:
	var button := Button.new()
	button.text = value
	button.position = bounds.position
	button.size = bounds.size
	button.add_theme_font_size_override("font_size", 23)
	button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	button.pressed.connect(navigate.emit.bind(route_id))
	add_child(button)
	return button


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_ESCAPE and not collection.is_empty():
		navigate.emit("menu")
		get_viewport().set_input_as_handled()
