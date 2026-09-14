extends Control

## Movie Sprite Actor diagnostic: body time, facial direction and reading/audio
## are independent. This is not a Scenario capability or a new episode director.
signal navigate(route_id: String)
signal language_changed(language: String)
const MOVIE_SPRITE_ACTOR = preload("res://addons/movie_sprite_actor/movie_sprite_actor.gd")
const TEXT_AUDIO = preload("res://addons/game_presentation/audio/text_reveal_audio.gd")
const SIZE := Vector2(1280, 900)
const CAST := ["yuzu", "riko"]
const LINES := [
	{"speaker": "yuzu", "text": "episode.a_glass_record"},
	{"speaker": "riko", "text": "episode.riko_on_the_glass"},
]
const MOUTH_CYCLE := ["rest", "mouth_a", "mouth_o", "mouth_a", "rest", "mouth_o"]
var content: Dictionary = {}
var text_set: RefCounted
var content_factory: Callable
var _load_errors: Array[String] = []
var _players: Dictionary = {}
var _eyes := {"yuzu": "auto", "riko": "auto"}
var _mouths := {"yuzu": "auto", "riko": "auto"}
var _eye_pickers: Dictionary = {}
var _mouth_pickers: Dictionary = {}
var _eye_clocks := {"yuzu": 0.0, "riko": 1.4}
var _audio = TEXT_AUDIO.new()
var _background: Texture2D
var _background_rect := Rect2()
var _contrast := false
var _paused := false
var _speech_clock := 0.0
var _reveal_clock := 0.0
var _line_index := -1
var _speaking := false
var _caption: Label
var _status: Label
var _pause_button: Button
var _language_button: Button
var _ui: Control


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	add_child(_audio)
	_load_errors.append_array(_audio.configure({"mode": "auto", "typing_volume_db": -18.0}))
	if _load_errors.is_empty():
		var loaded: Dictionary = content.content_loader.load_texture("assets/locations/reading_lounge.png", true)
		_load_errors.append_array(loaded.errors)
		_background = loaded.resource
		if _background != null:
			var extent := _background.get_size()
			extent *= maxf(SIZE.x / extent.x, SIZE.y / extent.y)
			_background_rect = Rect2((SIZE - extent) * 0.5, extent)
		for index in CAST.size():
			var actor_id: String = CAST[index]
			var actor = MOVIE_SPRITE_ACTOR.new()
			actor.name = actor_id.capitalize() + "MovieSprite"
			actor.position = Vector2(138 + index * 522, 78)
			actor.scale = Vector2.ONE * 0.68
			add_child(actor)
			_players[actor_id] = actor
			actor.failed.connect(_on_failure)
			_load_errors.append_array(actor.configure(content.content_loader, "assets/movie_sprite/%s/manifest.json" % actor_id))
			if actor.snapshot().get("character_id", "") != actor_id:
				_load_errors.append("Movie sprite identity differs from the host binding: " + actor_id)
	_build_ui()
	_update_caption()
	queue_redraw()


func _on_failure(errors: Array[String]) -> void:
	for issue: String in errors:
		if issue not in _load_errors: _load_errors.append(issue)
	stop_line()


func _process(delta: float) -> void:
	if not _load_errors.is_empty():
		_status.text = "Movie-sprite content unavailable: " + " | ".join(_load_errors)
		return
	for actor_id: String in _players:
		_players[actor_id].advance(delta)
	if not _paused:
		_speech_clock += delta
		_reveal_clock += delta
		_update_speech(delta)
		for actor_id: String in _players:
			_eye_clocks[actor_id] += delta
			_apply_face(actor_id)
	# Detailed counters are exposed by study_state() for QA; keep the display compact.
	_status.text = "Paused" if _paused else "Body: 16 FPS / 12-second loop · eyes and speaking mouth controlled separately"
	for actor_id: String in _players:
		var state: Dictionary = _players[actor_id].snapshot()
		_status.text += "  |  %s: %s / %s" % [actor_id.capitalize(), state.get("frame_index", 0), state.get("state", "loading")]


func _update_speech(delta: float) -> void:
	_speaking = false
	if _line_index < 0: return
	var text: String = text_set.text(LINES[_line_index].text)
	var state: Dictionary = _audio.get_state()
	if state.active_mode == "voice":
		_speaking = bool(state.voice_playing) and not bool(state.voice_finished)
		_caption.visible_characters = -1
	else:
		var visible := mini(text.length(), int(_reveal_clock * 36.0))
		_caption.visible_characters = visible
		_audio.update_reveal(visible, delta)
		_speaking = visible < text.length()


func _apply_face(actor_id: String) -> void:
	var eye: String = _eyes[actor_id]
	if eye == "auto":
		var time := fmod(float(_eye_clocks[actor_id]), 4.3 if actor_id == "yuzu" else 5.1)
		eye = "rest"
		if time >= 3.75 and time < 3.99:
			eye = "eyes_closed"
			if actor_id == "yuzu" and (time < 3.81 or time >= 3.93): eye = "eyes_half"
	_players[actor_id].set_eye_state(eye)
	var mouth: String = _mouths[actor_id]
	if mouth == "auto":
		mouth = "rest"
		if _speaking and _line_index >= 0 and LINES[_line_index].speaker == actor_id:
			mouth = MOUTH_CYCLE[int(_speech_clock / 0.115) % MOUTH_CYCLE.size()]
	_players[actor_id].set_mouth_state(mouth)


func select_eye(actor_id: String, state: String) -> void:
	if actor_id not in _players: return
	if state not in (["auto", "rest", "eyes_half", "eyes_closed"] if actor_id == "yuzu" else ["auto", "rest", "eyes_closed"]): return
	_eyes[actor_id] = state
	if _eye_pickers.has(actor_id):
		var states: Array = ["auto", "rest", "eyes_half", "eyes_closed"] if actor_id == "yuzu" else ["auto", "rest", "eyes_closed"]
		_eye_pickers[actor_id].select(states.find(state))
	_apply_face(actor_id)


func select_mouth(actor_id: String, state: String) -> void:
	if actor_id not in _players or state not in ["auto", "rest", "mouth_a", "mouth_o"]: return
	_mouths[actor_id] = state
	if _mouth_pickers.has(actor_id): _mouth_pickers[actor_id].select(["auto", "rest", "mouth_a", "mouth_o"].find(state))
	_apply_face(actor_id)


func play_line(index: int) -> void:
	if index < 0 or index >= LINES.size() or not _load_errors.is_empty(): return
	stop_line()
	_line_index = index
	var entry: Dictionary = LINES[index]
	var text: String = text_set.text(entry.text)
	var stream: AudioStream = content.get("voiceovers", {}).get(get_language(), {}).get(entry.text)
	_audio.begin(text, stream, text.length() if stream != null else 0)
	_audio.set_paused(_paused)
	_update_caption()


func stop_line() -> void:
	_audio.stop()
	_line_index = -1
	_speaking = false
	_speech_clock = 0.0
	_reveal_clock = 0.0
	for actor_id: String in _players: _apply_face(actor_id)
	if _caption != null: _update_caption()


func toggle_pause() -> void:
	_paused = not _paused
	_audio.set_paused(_paused)
	for actor_id: String in _players: _players[actor_id].set_paused(_paused)
	_pause_button.text = "Resume" if _paused else "Pause"


func restart_loops() -> void:
	stop_line()
	_eye_clocks = {"yuzu": 0.0, "riko": 1.4}
	for actor_id: String in _players:
		_players[actor_id].seek(0.0)
		_apply_face(actor_id)


func get_language() -> String:
	return text_set.get_language() if text_set != null else "en"


func select_language(language: String) -> void:
	if text_set == null: return
	stop_line()
	_load_errors.append_array(text_set.set_language(language))
	language_changed.emit(language)
	_language_button.text = "English" if language == "en" else "Korean"
	_update_caption()


func _update_caption() -> void:
	if _line_index < 0:
		_caption.text = "Yuzu: bilateral blink   ·   Riko: canvas-left wink\nPlay an existing story line to drive its speaker's mouth. A/O cycling is not phoneme alignment."
		_caption.visible_characters = -1
	else:
		_caption.text = text_set.text(LINES[_line_index].text)
		_caption.visible_characters = -1 if _audio.get_state().active_mode == "voice" else 0


func study_state() -> Dictionary:
	var actors := {}
	for actor_id: String in _players: actors[actor_id] = _players[actor_id].snapshot()
	return {"actors": actors, "paused": _paused, "speaking": _speaking, "line_index": _line_index,
		"language": get_language(), "audio": _audio.get_state(), "errors": _load_errors.duplicate(),
		"eye_modes": _eyes.duplicate(), "mouth_modes": _mouths.duplicate()}


func _build_ui() -> void:
	_ui = Control.new()
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_panel(Rect2(0, 0, 1280, 72), Color(0.08, 0.055, 0.10, 0.95))
	_label("AFTERLIGHT / MOVIE SPRITES", Rect2(24, 13, 480, 31), 25)
	_label("Movie Sprite Actors · body + facial controls", Rect2(25, 46, 480, 23), 14)
	_pause_button = _button("Pause", Rect2(530, 19, 112, 38), toggle_pause)
	_button("Restart loops", Rect2(653, 19, 143, 38), restart_loops)
	_button("Alpha check", Rect2(807, 19, 131, 38), func() -> void: _contrast = not _contrast; queue_redraw())
	_language_button = _button("English" if get_language() == "en" else "Korean", Rect2(949, 19, 122, 38), func() -> void: select_language("ko" if get_language() == "en" else "en"))
	_button("Back to Lab", Rect2(1082, 19, 173, 38), func() -> void: navigate.emit("effects_menu"))
	_panel(Rect2(0, 660, 1280, 240), Color(0.09, 0.06, 0.12, 0.94))
	_button("Yuzu · speak", Rect2(25, 675, 171, 37), play_line.bind(0))
	_button("Riko · speak", Rect2(207, 675, 171, 37), play_line.bind(1))
	_button("Stop voice", Rect2(390, 675, 143, 37), stop_line)
	_caption = _label("", Rect2(25, 722, 1225, 65), 20)
	_caption.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	for index in CAST.size():
		var actor_id: String = CAST[index]
		var x := 25.0 + index * 635.0
		_label(actor_id.capitalize(), Rect2(x, 796, 72, 35), 18)
		_eye_pickers[actor_id] = _picker(Rect2(x + 78, 792, 236, 39), ["Auto blink", "Eyes open", "Half closed", "Eyes closed"] if index == 0 else ["Auto wink", "Eyes open", "Canvas-left wink"], ["auto", "rest", "eyes_half", "eyes_closed"] if index == 0 else ["auto", "rest", "eyes_closed"], func(state: String) -> void: select_eye(actor_id, state))
		_mouth_pickers[actor_id] = _picker(Rect2(x + 325, 792, 272, 39), ["Speaking mouth", "Mouth rest", "Mouth A", "Mouth O"], ["auto", "rest", "mouth_a", "mouth_o"], func(state: String) -> void: select_mouth(actor_id, state))
	_status = _label("Loading prepared body pages…", Rect2(25, 850, 1230, 45), 14)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART


func _picker(rect: Rect2, labels: Array, states: Array, callback: Callable) -> OptionButton:
	var picker := OptionButton.new()
	picker.position = rect.position
	picker.size = rect.size
	for text: String in labels: picker.add_item(text)
	picker.item_selected.connect(func(index: int) -> void: callback.call(states[index]))
	_ui.add_child(picker)
	return picker


func _button(text: String, rect: Rect2, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.position = rect.position
	button.size = rect.size
	button.add_theme_font_size_override("font_size", 17)
	button.pressed.connect(callback)
	_ui.add_child(button)
	return button


func _label(text: String, rect: Rect2, font_size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.position = rect.position
	label.size = rect.size
	label.add_theme_font_size_override("font_size", font_size)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(label)
	return label


func _panel(rect: Rect2, tint: Color) -> void:
	var panel := ColorRect.new()
	panel.position = rect.position
	panel.size = rect.size
	panel.color = tint
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(panel)


func _draw() -> void:
	if _contrast:
		for y in range(0, 900, 40):
			for x in range(0, 1280, 40):
				draw_rect(Rect2(x, y, 40, 40), Color("dde4e7") if (x / 40 + y / 40) % 2 == 0 else Color("263246"))
	elif _background != null:
		draw_texture_rect(_background, _background_rect, false)


func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			navigate.emit("effects_menu")
			get_viewport().set_input_as_handled()


func _exit_tree() -> void:
	_audio.stop()
	for actor_id: String in _players: _players[actor_id].shutdown()
