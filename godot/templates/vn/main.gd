extends Control

## The game owns bindings, resources, input and UI. Scenario alone executes the
## authored narrative, choices, gates and operation lifetimes.
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
const SCENARIO_PROGRAM = preload("res://addons/scenario_runtime/program/program.gd")
const SCENARIO_CATALOG = preload("res://addons/scenario_runtime/program/catalog.gd")
const SESSION = preload("res://addons/scenario_runtime/execution/session.gd")
const REFUSAL = preload("res://addons/scenario_runtime/refusal.gd")
var WORDS: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://text/en.json"))
var _program: Dictionary = {}
var _catalog: Dictionary = {}
var _session = SESSION.new()
var _current: Dictionary = {}
var _revealed_visit := ""
var _contact_operation := ""
var _feedback_operation := ""
var _contact_settings: Dictionary = {}
var _session_serial := 0

# Set these in the scene/editor, in code, or via the optional local-root flags.
@export var background_texture: Texture2D
@export var mara_texture: Texture2D
@export var ivo_texture: Texture2D
@export var mark_texture: Texture2D
@export var welcome_voice: AudioStream

var errors: Array[String] = []
# Observations retained for the starter's owned behavior checks; never execution selectors.
var beat_index: int:
	get: return int(_current.get("presentation", {}).get("progress_index", 0))
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
	_load_narrative()
	_start_scenario()
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


func _load_narrative() -> void:
	var types: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://bindings/capabilities.json"))
	_catalog = SCENARIO_CATALOG.parse(JSON.parse_string(FileAccess.get_file_as_string("res://narrative/catalog.json")), types)
	if REFUSAL.is_refusal(_catalog):
		errors.append(REFUSAL.line(_catalog))
		return
	_program = SCENARIO_PROGRAM.parse(JSON.parse_string(FileAccess.get_file_as_string("res://narrative/episode.json")), _catalog)
	if REFUSAL.is_refusal(_program): errors.append(REFUSAL.line(_program))


func _start_scenario() -> void:
	if not errors.is_empty(): return
	_session_serial += 1
	_session = SESSION.new()
	var result: Dictionary = _session.start(_program, _catalog, {
		"session_id": "starter_%d" % _session_serial,
		"capabilities": {"point_contact": 1, "radial_burst": 1},
		"channels": ["dialogue"], "bindings": ["relay", "mara", "ivo"],
	})
	_accept(result)


func _present(node: Dictionary) -> void:
	_current = node.duplicate(true)
	_audio.stop()
	_contact.reset()
	_contact_operation = ""
	_feedback_operation = ""
	_contact_seconds = -1.0
	_burst.clear()
	_manpu.clear()
	_revealed_visit = ""
	var direction: Dictionary = node["presentation"]
	var key := str(node.get("text_key", ""))
	var words := _text_set.text(key) if not key.is_empty() else str(node.get("text", ""))
	errors.append_array(_reveal.start(words, {"chars_per_second": float(direction.get("chars_per_second", 38.0))}))
	var camera: Dictionary = direction.get("camera", {})
	if camera.get("mode", "wide") == "wide":
		errors.append_array(_camera.wide(float(camera.get("duration", 0.55))))
	else:
		var actor_id := str(camera["actor"])
		var local: Array = camera.get("local_offset", [150, 155])
		var anchor: Array = camera.get("anchor", [640, 270])
		errors.append_array(_camera.focus(actor_id, _actor_rect(actor_id).position + Vector2(local[0], local[1]), Vector2(anchor[0], anchor[1]), float(camera["zoom"]), float(camera["duration"])))
	errors.append_array(_manpu.sync(direction.get("manpu", [])))
	var voices := {"welcome": welcome_voice}
	var voice: AudioStream = voices.get(str(direction.get("voice", "")))
	if voice != null: _reveal.request_advance()
	_audio.begin(words, voice, int(_reveal.sample()["visible_characters"]))
	_audio.set_paused(paused)
	_render()


func _accept(result: Dictionary) -> void:
	if REFUSAL.is_refusal(result):
		errors.append(REFUSAL.line(result))
		return
	for event: Dictionary in _session.drain_events():
		var when := float(event.get("clocks", {}).get("presentation", _clock))
		_advance_mechanisms(maxf(0.0, when - _clock))
		match str(event["type"]):
			"scenario/presented": _present(event["presentation"])
			"scenario/reveal_requested":
				_reveal.request_advance()
				_audio.sync_reveal(int(_reveal.sample()["visible_characters"]))
			"scenario/chosen": choice_id = str(event["choice_id"])
			"scenario/effect_started": _start_effect(event)
			"scenario/effect_finished", "scenario/effect_cancelled":
				if event["operation_id"] == _contact_operation: _contact_operation = ""
				if event["operation_id"] == _feedback_operation: _feedback_operation = ""
	_notify_revealed()
	_render()


func _notify_revealed() -> void:
	if _current.is_empty() or _reveal.sample()["phase"] != "holding": return
	var view: Dictionary = _session.view()
	var visit := str(view.get("visit_id", ""))
	if visit.is_empty() or visit == _revealed_visit or view.get("status") != "running": return
	_revealed_visit = visit
	_accept(_session.submit({"kind": "host_event", "session_id": "starter_%d" % _session_serial, "node_id": view["node_id"], "visit_id": visit, "name": "text_revealed"}))


func _start_effect(event: Dictionary) -> void:
	var parameters: Dictionary = event["effect"]["parameters"]
	match str(event["effect"]["type"]):
		"point_contact":
			_contact.reset()
			_contact_operation = str(event["operation_id"])
			_contact_settings = parameters.duplicate(true)
		"radial_burst":
			_feedback_operation = str(event["operation_id"])
			_contact_seconds = 0.0
			var settings := parameters.duplicate(true)
			settings["duration"] = event["duration"]
			var result: Dictionary = _burst.emit_burst(CONTACT_POINT, [mark_texture] as Array[Texture2D], settings)
			errors.append_array(result["errors"])


func _advance_mechanisms(delta: float) -> void:
	if delta <= 0.0: return
	_clock += delta
	_camera.advance(delta)
	_manpu.advance(delta)
	_burst.advance(delta)
	_reveal.advance(delta)
	_audio.update_reveal(int(_reveal.sample()["visible_characters"]), delta)
	if _contact_seconds >= 0.0: _contact_seconds += delta


func _process(delta: float) -> void:
	if paused or not errors.is_empty(): return
	var remaining := delta
	while remaining > 0.000000001:
		var step := remaining
		var reveal: Dictionary = _reveal.get_state()
		if reveal["phase"] == "revealing":
			step = minf(step, maxf(0.000000001, float(str(reveal["text"]).length()) / float(reveal["chars_per_second"]) - float(reveal["elapsed"])))
		var target := _clock + step
		_accept(_session.tick(step))
		_advance_mechanisms(maxf(0.0, target - _clock))
		_notify_revealed()
		remaining -= step
	_render()


func advance_story() -> void:
	if paused or not errors.is_empty(): return
	_accept(_session.submit({"kind": "advance"}))


func choose(option: String) -> void:
	if paused or not errors.is_empty() or _reveal.sample()["phase"] != "holding": return
	_accept(_session.submit({"kind": "choose", "choice_id": option}))


func contact_target() -> Dictionary:
	var camera := _world()
	return {"center": camera * CONTACT_POINT, "radius": float(_contact_settings.get("radius", 43.0)) * camera.x.length(),
		"ready": not paused and not _contact_operation.is_empty() and _reveal.sample()["phase"] == "holding" and not _contact.is_confirmed()}


func try_contact(point: Vector2) -> bool:
	var target := contact_target()
	if not target["ready"] or not _contact.confirm_at(point, target["center"], target["radius"]): return false
	_accept(_session.submit({"kind": "operation_completed", "session_id": "starter_%d" % _session_serial, "operation_id": _contact_operation}))
	return true


func toggle_pause() -> void:
	paused = not paused
	_accept(_session.suspend() if paused else _session.resume())
	_audio.set_paused(paused)
	_render()


func restart() -> void:
	_session.cancel("restart")
	_session.drain_events()
	paused = false
	choice_id = ""
	_clock = 0.0
	_camera.clear()
	_start_scenario()


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
	var beat: Dictionary = _current
	if beat.is_empty(): return
	var thought: bool = beat["presentation"].get("profile") == "intertitle"
	var camera := _world()
	for id: String in _actors:
		var actor: TextureRect = _actors[id]
		actor.visible = not thought
		var rect: Rect2 = camera * _actor_rect(id)
		actor.position = rect.position
		actor.size = rect.size
	var marks: bool = not thought and not beat["presentation"].get("manpu", []).is_empty()
	_mark.visible = marks
	if marks:
		var cue: Dictionary = beat["presentation"]["manpu"][0]
		var sample: Dictionary = _manpu.sample(cue["actor"], cue["id"])
		var base: Rect2 = _actor_rect(cue["actor"])
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
	_speaker.text = str(beat.get("speaker") if beat.get("speaker") != null else "").capitalize()
	_ready_dot.visible = words["phase"] == "holding" and beat["kind"] == "line" and not beat["presentation"].get("terminal", false) and _session.view().get("pending_gate", {}).is_empty() and not paused
	for button: Button in _choices: button.visible = beat["kind"] == "choice" and words["phase"] == "holding" and not paused
	_pause_button.text = "Resume" if paused else "Pause"
	_restart_button.visible = bool(beat["presentation"].get("terminal", false)) or paused
	queue_redraw()


func _draw() -> void:
	if _current.is_empty() or _current["presentation"].get("profile") == "intertitle":
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
	if _current["presentation"].get("show_relay", false):
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
	if not _session.view().is_empty(): _session.cancel("host_exit")
	_audio.stop()
	_burst.clear()
