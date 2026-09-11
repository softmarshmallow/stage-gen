extends Control

## This file owns the game, art bindings and complete UI. SDK components only
## receive resources, geometry, cues and time; they never choose the next beat.
const CAMERA = preload("res://addons/game_presentation/camera/dialogue_camera.gd")
const MANPU = preload("res://addons/game_presentation/actors/manpu_animation.gd")
const TEXT_SET = preload("res://addons/game_presentation/text/text_set.gd")
const REVEAL = preload("res://addons/game_presentation/text/intertitle.gd")
const TEXT_AUDIO = preload("res://addons/game_presentation/audio/text_reveal_audio.gd")
const CONTACT = preload("res://addons/game_presentation/interaction/point_contact.gd")
const BURST = preload("res://addons/game_presentation/effects/particles/sprite_burst.gd")
const CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const SIZE := Vector2(1280, 900)
const BACKGROUND := Rect2(-160, -112.5, 1600, 1125)
const CONTACT_POINT := Vector2(640, 438)
const WORDS := {
	"title": "THE SIGNAL ROOM", "intro": "At the last station, one light is still on.",
	"welcome": "You made it. We kept the relay warm in case anyone found their way here.",
	"choice": "One message can leave before dawn. What should we send?",
	"light": "A light", "note": "A note",
	"reply_light": "A light, then. No names or explanations. Just a small reason to look up.",
	"reply_note": "A note, then. Something simple: we are here, and there is room for one more.",
	"contact": "Rest your hand on the light. The relay needs someone on this side, too.",
	"delivery": "There. Somewhere beyond the hills, another window is waking up.",
	"ending": "For the first time tonight, the station does not feel like the end of the line.",
}
const BEATS := [
	{"kind": "intertitle", "text": "intro"},
	{"kind": "dialogue", "speaker": "mara", "text": "welcome"},
	{"kind": "choice", "speaker": "ivo", "text": "choice"},
	{"kind": "dialogue", "speaker": "mara", "text": "reply"},
	{"kind": "contact", "speaker": "ivo", "text": "contact"},
	{"kind": "dialogue", "speaker": "mara", "text": "delivery"},
	{"kind": "intertitle", "text": "ending"},
]

# Set these in the scene/editor, in code, or via the optional local-root flags.
@export var background_texture: Texture2D
@export var mara_texture: Texture2D
@export var ivo_texture: Texture2D
@export var mark_texture: Texture2D
@export var welcome_voice: AudioStream

var errors: Array[String] = []
var beat_index := 0
var choice_id := ""
var paused := false
var _clock := 0.0
var _contact_seconds := -1.0
var _camera = CAMERA.new()
var _manpu = MANPU.new()
var _text_set = TEXT_SET.new()
var _reveal = REVEAL.new()
var _audio = TEXT_AUDIO.new()
var _contact = CONTACT.new()
var _burst = BURST.new()
var _actors: Dictionary = {}
var _mark := TextureRect.new()
var _chrome := Control.new()
var _speaker := Label.new()
var _dialogue := Label.new()
var _thought := Label.new()
var _ready_dot := Label.new()
var _choices: Array[Button] = []
var _pause_button := Button.new()
var _restart_button := Button.new()


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	_bind_content()
	errors.append_array(_text_set.configure({"en": WORDS}))
	errors.append_array(_camera.initialize(SIZE, BACKGROUND))
	errors.append_array(_manpu.initialize("res://addons/game_presentation/actors/presets/manpu.json"))
	add_child(_burst)
	for id: String in ["mara", "ivo"]:
		var actor := TextureRect.new()
		actor.name = id.capitalize()
		actor.texture = mara_texture if id == "mara" else ivo_texture
		actor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		actor.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(actor)
		_actors[id] = actor
	_mark.texture = mark_texture
	_mark.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_mark.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_mark)
	add_child(_audio)
	errors.append_array(_audio.configure({"mode": "auto"}))
	_build_ui()
	_enter_beat()
	if not errors.is_empty():
		paused = true
		_dialogue.text = "Content could not be loaded:\n" + "\n".join(errors)
		_dialogue.visible_characters = -1
		_chrome.show()
		_thought.hide()
		for message: String in errors: push_error(message)


func _bind_content() -> void:
	var flags := {}
	var args := OS.get_cmdline_user_args()
	for index in range(0, args.size() - 1):
		if args[index] in ["--content-root", "--background", "--mara", "--ivo", "--mark", "--voice"]:
			flags[args[index]] = args[index + 1]
	if flags.has("--content-root"):
		var loader = CONTENT.new()
		var content_root := str(flags["--content-root"])
		errors.append_array(loader.configure(content_root, "resources" if content_root.begins_with("res://") else "files"))
		if errors.is_empty():
			for flag: String in ["--background", "--mara", "--ivo", "--mark", "--voice"]:
				if not flags.has(flag): continue
				var loaded: Dictionary = loader.load_audio(flags[flag]) if flag == "--voice" else loader.load_texture(flags[flag])
				errors.append_array(loaded["errors"])
				if not loaded["errors"].is_empty(): continue
				match flag:
					"--background": background_texture = loaded["resource"]
					"--mara": mara_texture = loaded["resource"]
					"--ivo": ivo_texture = loaded["resource"]
					"--mark": mark_texture = loaded["resource"]
					"--voice": welcome_voice = loaded["resource"]
	elif flags.size() > 0:
		errors.append("Media flags require --content-root with a local directory or res:// resource root.")
	if mara_texture == null: mara_texture = _avatar(Color("de987d"))
	if ivo_texture == null: ivo_texture = _avatar(Color("729fb4"))
	if mark_texture == null: mark_texture = _glint()


func _enter_beat() -> void:
	_audio.stop()
	_contact.reset()
	_contact_seconds = -1.0
	_burst.clear()
	_manpu.clear()
	var beat: Dictionary = BEATS[beat_index]
	var key := str(beat["text"])
	if key == "reply": key = "reply_" + choice_id
	errors.append_array(_reveal.start(_text_set.text(key), {"chars_per_second": 38.0}))
	if beat["kind"] == "intertitle" or beat["kind"] == "contact":
		errors.append_array(_camera.wide(0.55))
	else:
		var actor_id := str(beat["speaker"])
		errors.append_array(_camera.focus(actor_id, _actor_rect(actor_id).position + Vector2(150, 155), Vector2(640, 270), 1.2, 0.65))
	if beat_index == 3:
		errors.append_array(_manpu.sync([{"actor": "mara", "id": "glint", "preset": "step_loop"}]))
	if beat_index == 5:
		errors.append_array(_manpu.sync([{"actor": "mara", "id": "glint", "preset": "scale_pulse"}]))
	var voice: AudioStream = welcome_voice if beat_index == 1 else null
	if voice != null: _reveal.request_advance()
	_audio.begin(_text_set.text(key), voice, int(_reveal.sample()["visible_characters"]))
	_audio.set_paused(paused)
	_render()


func _process(delta: float) -> void:
	if paused or not errors.is_empty(): return
	_clock += delta
	_camera.advance(delta)
	_manpu.advance(delta)
	_burst.advance(delta)
	_reveal.advance(delta)
	_audio.update_reveal(int(_reveal.sample()["visible_characters"]), delta)
	if _contact_seconds >= 0.0:
		_contact_seconds += delta
		if _contact_seconds >= 0.65:
			beat_index += 1
			_enter_beat()
	_render()


func advance_story() -> void:
	if paused or not errors.is_empty(): return
	if _reveal.sample()["phase"] == "revealing":
		_reveal.request_advance()
		_audio.sync_reveal(int(_reveal.sample()["visible_characters"]))
	elif BEATS[beat_index]["kind"] not in ["choice", "contact"] and beat_index < BEATS.size() - 1:
		beat_index += 1
		_enter_beat()
	_render()


func choose(option: String) -> void:
	if paused or BEATS[beat_index]["kind"] != "choice" or _reveal.sample()["phase"] != "holding" or option not in ["light", "note"]: return
	choice_id = option
	beat_index += 1
	_enter_beat()


func contact_target() -> Dictionary:
	var camera := _world()
	return {"center": camera * CONTACT_POINT, "radius": 43.0 * camera.x.length(),
		"ready": not paused and BEATS[beat_index]["kind"] == "contact" and _reveal.sample()["phase"] == "holding" and not _contact.is_confirmed()}


func try_contact(point: Vector2) -> bool:
	var target := contact_target()
	if not target["ready"] or not _contact.confirm_at(point, target["center"], target["radius"]): return false
	_contact_seconds = 0.0
	var result: Dictionary = _burst.emit_burst(CONTACT_POINT, [mark_texture] as Array[Texture2D], {"count": 18, "duration": 0.65, "distance": 240.0, "sprite_size": 32.0, "seed": 21})
	errors.append_array(result["errors"])
	_render()
	return true


func toggle_pause() -> void:
	paused = not paused
	_audio.set_paused(paused)
	_render()


func restart() -> void:
	paused = false
	beat_index = 0
	choice_id = ""
	_clock = 0.0
	_camera.clear()
	_enter_beat()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE: toggle_pause()
		elif event.keycode in [KEY_SPACE, KEY_ENTER]: advance_story()
		else: return
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if event.device == InputEvent.DEVICE_ID_EMULATION: return
		if not try_contact(event.position): advance_story()
		get_viewport().set_input_as_handled()
	elif event is InputEventScreenTouch and event.pressed:
		if not try_contact(event.position): advance_story()
		get_viewport().set_input_as_handled()


func _world() -> Transform2D:
	var pose: Dictionary = _camera.sample()
	var zoom := float(pose["zoom"])
	return Transform2D(Vector2(zoom, 0), Vector2(0, zoom), Vector2(pose["offset_x"], pose["offset_y"]))


func _actor_rect(actor_id: String) -> Rect2:
	var texture: Texture2D = mara_texture if actor_id == "mara" else ivo_texture
	var dimensions := Vector2(610.0 * texture.get_width() / texture.get_height(), 610)
	return Rect2(Vector2(390 if actor_id == "mara" else 890, 125) - Vector2(dimensions.x * 0.5, 0), dimensions)


func _render() -> void:
	var beat: Dictionary = BEATS[beat_index]
	var thought: bool = beat["kind"] == "intertitle"
	var camera := _world()
	for id: String in _actors:
		var actor: TextureRect = _actors[id]
		actor.visible = not thought
		var rect: Rect2 = camera * _actor_rect(id)
		actor.position = rect.position
		actor.size = rect.size
	var marks: bool = not thought and beat_index in [3, 5]
	_mark.visible = marks
	if marks:
		var sample: Dictionary = _manpu.sample("mara", "glint")
		var base: Rect2 = _actor_rect("mara")
		var size_px := 62.0 * float(sample["scale"])
		var mark_rect: Rect2 = camera * Rect2(base.position + Vector2(base.size.x - 22, 48) - Vector2.ONE * size_px * 0.5 + Vector2(sample["offset_x_ratio"], sample["offset_y_ratio"]) * 62.0, Vector2.ONE * size_px)
		_mark.position = mark_rect.position
		_mark.size = mark_rect.size
		_mark.pivot_offset = mark_rect.size * 0.5
		_mark.rotation_degrees = float(sample["rotation_degrees"])
		_mark.modulate.a = float(sample["opacity"])
	_burst.present(camera)
	var words: Dictionary = _reveal.sample()
	_chrome.visible = not thought
	_thought.visible = thought
	_thought.text = words["text"]
	_thought.visible_characters = words["visible_characters"]
	_dialogue.text = words["text"]
	_dialogue.visible_characters = words["visible_characters"]
	_speaker.text = str(beat.get("speaker", "")).capitalize()
	_ready_dot.visible = words["phase"] == "holding" and beat["kind"] not in ["choice", "contact"] and beat_index < BEATS.size() - 1 and not paused
	for button: Button in _choices: button.visible = beat["kind"] == "choice" and words["phase"] == "holding" and not paused
	_pause_button.text = "Resume" if paused else "Pause"
	_restart_button.visible = beat_index == BEATS.size() - 1 or paused
	queue_redraw()


func _draw() -> void:
	if BEATS[beat_index]["kind"] == "intertitle":
		draw_rect(Rect2(Vector2.ZERO, SIZE), Color("111823"))
		return
	draw_set_transform_matrix(_world())
	if background_texture != null:
		draw_texture_rect(background_texture, BACKGROUND, false)
	else:
		draw_rect(BACKGROUND, Color("26394a"))
		draw_rect(Rect2(-160, 490, 1600, 560), Color("172a38"))
		for index in 5:
			var x := -35.0 + index * 305.0
			draw_style_box(_style(Color("425b69"), 12), Rect2(x, 45, 250, 320))
			draw_rect(Rect2(x + 10, 55, 230, 295), Color("7597a4"))
			draw_line(Vector2(x + 125, 55), Vector2(x + 125, 350), Color("344b5c"), 10)
		draw_rect(Rect2(525, 412, 230, 220), Color("263442"))
		draw_rect(Rect2(520, 602, 240, 18), Color("bda585"))
	if BEATS[beat_index]["kind"] == "contact":
		var glow := 0.12 + 0.04 * sin(_clock * 3.0)
		for radius in [60, 48, 36]: draw_circle(CONTACT_POINT, radius, Color(0.8, 0.95, 1, glow))
		draw_circle(CONTACT_POINT, 26, Color("e1f5ee"))
		draw_arc(CONTACT_POINT, 43, 0, TAU, 64, Color("e1f5ee"), 2, true)
	draw_set_transform_matrix(Transform2D.IDENTITY)


func _build_ui() -> void:
	_chrome.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_chrome)
	var wash := GradientTexture2D.new()
	wash.gradient = Gradient.new()
	wash.gradient.colors = PackedColorArray([Color(0.05, 0.08, 0.12, 0), Color(0.05, 0.08, 0.12, 0.98)])
	wash.fill_from = Vector2(0, 0)
	wash.fill_to = Vector2(0, 0.65)
	var sheet := TextureRect.new()
	sheet.texture = wash
	sheet.position = Vector2(0, 615)
	sheet.size = Vector2(1280, 285)
	sheet.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_chrome.add_child(sheet)
	_label(_chrome, _speaker, Rect2(72, 694, 1000, 35), 26)
	_speaker.modulate = Color("e9cba3")
	_label(_chrome, _dialogue, Rect2(72, 742, 1110, 120), 28)
	_label(self, _thought, Rect2(170, 335, 940, 210), 34)
	_thought.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_thought.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_label(_chrome, _ready_dot, Rect2(1200, 831, 24, 30), 24)
	_ready_dot.text = "•"
	var title := Label.new()
	_label(self, title, Rect2(48, 32, 730, 42), 21)
	title.text = WORDS["title"]
	title.modulate = Color("e9cba3")
	_make_button(_pause_button, "Pause", Rect2(1100, 28, 130, 44), toggle_pause)
	_make_button(_restart_button, "Restart", Rect2(940, 28, 140, 44), restart)
	for index in 2:
		var option := "light" if index == 0 else "note"
		var button := Button.new()
		_make_button(button, WORDS[option], Rect2(365, 498 + index * 68, 550, 56), choose.bind(option))
		_choices.append(button)


func _label(parent: Node, label: Label, rect: Rect2, font_size: int) -> void:
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.position = rect.position
	label.size = rect.size
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color("f1f2ed"))
	parent.add_child(label)


func _make_button(button: Button, text: String, rect: Rect2, callback: Callable) -> void:
	button.text = text
	button.position = rect.position
	button.size = rect.size
	button.add_theme_font_size_override("font_size", 21)
	button.add_theme_stylebox_override("normal", _style(Color("334a5b"), 10))
	button.add_theme_stylebox_override("hover", _style(Color("506778"), 10))
	button.add_theme_stylebox_override("pressed", _style(Color("243747"), 10))
	button.pressed.connect(callback)
	add_child(button)


func _style(color: Color, radius: int) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.set_corner_radius_all(radius)
	return style


static func _avatar(color: Color) -> Texture2D:
	# Deliberately neutral stand-ins: a small raster portrait, not generated art.
	var image := Image.create(180, 360, false, Image.FORMAT_RGBA8)
	for y in 360:
		for x in 180:
			var point := Vector2(x, y)
			var head := (point - Vector2(90, 78)) / Vector2(49, 61)
			var body := (point - Vector2(90, 230)) / Vector2(83, 160)
			if body.length_squared() <= 1 and y > 135: image.set_pixel(x, y, color.darkened(0.15))
			if head.length_squared() <= 1: image.set_pixel(x, y, Color("edcfb1"))
			if head.length_squared() <= 1 and y < 57: image.set_pixel(x, y, color.darkened(0.62))
			if (point - Vector2(73, 83)).length() < 4 or (point - Vector2(107, 83)).length() < 4: image.set_pixel(x, y, Color("253243"))
			if y in range(107, 111) and x > 81 and x < 100: image.set_pixel(x, y, color.darkened(0.2))
	return ImageTexture.create_from_image(image)


static func _glint() -> Texture2D:
	var image := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	for y in 64:
		for x in 64:
			var p := (Vector2(x, y) - Vector2(31.5, 31.5)) / 31.5
			var d := pow(absf(p.x), 0.65) + pow(absf(p.y), 0.65)
			image.set_pixel(x, y, Color(1, 0.9, 0.6, 1 - smoothstep(0.88, 1.05, d)))
	return ImageTexture.create_from_image(image)


func _exit_tree() -> void:
	_audio.stop()
	_burst.clear()
