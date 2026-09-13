extends Control

## Afterlight owns its application, UI, audio, bindings and save envelope.
## Scenario Session exclusively executes the authored episode and timed cues.
signal navigate(route_id: String)
signal language_changed(language: String)
const SESSION = preload("res://addons/scenario_runtime/execution/session.gd")
const PROGRAM = preload("res://addons/scenario_runtime/program/program.gd")
const CATALOG = preload("res://addons/scenario_runtime/program/catalog.gd")
const TRANSPORT = preload("res://addons/scenario_runtime/execution/transport.gd")
const FRONT_STAGE = preload("res://addons/scenario_runtime/presentation/front_stage.gd")
const BINDING = preload("res://narrative_binding.gd")
const EPISODE = preload("res://story_beats.gd")
const REVEAL = preload("res://addons/game_presentation/text/intertitle.gd")
const TEXT_AUDIO = preload("res://addons/game_presentation/audio/text_reveal_audio.gd")
const VOICE_EFFECTS = preload("res://addons/game_presentation/audio/voice_effects.gd")
const POINT_CONTACT = preload("res://addons/game_presentation/interaction/point_contact.gd")
const CONTENT_ADAPTER = preload("res://content_adapter.gd")
const TRANSMISSION_DISPLAY = preload("res://transmission_display.gd")
const DESIGN_SIZE := Vector2(1280, 900)
const INK := Color("f4eee6")
const ACCENT := Color("e4bbac")
var content: Dictionary = {}
var beats: Array = []
var saved_state: Dictionary = {}
var text_set: RefCounted
var voice_policy: RefCounted
var content_factory: Callable
var text_audio_settings: Dictionary = {}
var _session = SESSION.new()
var _transport = TRANSPORT.new()
var _stage = FRONT_STAGE.new()
var _program: Dictionary = {}
var _catalog: Dictionary = {}
var _catalog_document: Dictionary = {}
var _types: Dictionary = {}
var _policy: Dictionary = {}
var _shown: Dictionary = {}
var _reported_gate_events: Dictionary = {}
var _current_review: Dictionary = {}
var _clock := {"sequence": 0.0, "presentation": 0.0, "reading": 0.0}
var _elapsed := 0.0
var _history: Array[float] = []
var _manpu_history: Array[float] = []
var _manpu_event_time := -1.0
var _contact_history: Array[float] = []
var _contact_time := -1.0
var _journal: Array = []
var _replaying_checkpoint := false
var _paused := false
var _voice_state: Dictionary = {}
var _voice_waiting := false
var _load_errors: Array[String] = []
var _checkpoint_refused := false
var _recovery_button: Button
var _reveal = REVEAL.new()
var _text_audio = TEXT_AUDIO.new()
var _voice_effects = VOICE_EFFECTS.new()
var _contact = POINT_CONTACT.new()
var _beat_index: int:
	get:
		for index in beats.size():
			if beats[index]["id"] == current_beat().get("id"): return index
		return 0
var _choices: Dictionary:
	get:
		var result := {}
		if not _session.view().is_empty():
			for key: String in _session.snapshot()["state"]["facts"]:
				var value: Variant = _session.snapshot()["state"]["facts"][key]
				if value != "": result[key] = value
		return result
var _autoplay_enabled: bool:
	get: return _transport._enabled
	set(value): _transport._enabled = value
var _autoplay_elapsed: float:
	get: return _transport._elapsed
	set(value): _transport._elapsed = value
var _cast: Control:
	get: return _stage._cast
var _transmission_display: Control:
	get: return _stage._transmission_display
var _portrait: TextureRect:
	get: return _stage._portrait
var _halo: TextureRect:
	get: return _stage._halo
var _eye_layer: ColorRect:
	get: return _stage._eye_layer
var _flare: ColorRect:
	get: return _stage._flare
var _background_index: int:
	get: return _stage._background_index
var _base_background: Rect2:
	get: return _stage._base_background
var _effect_time: float:
	get: return _stage._effect_time
var _walking: RefCounted:
	get: return _stage._walking
var _camera: RefCounted:
	get: return _stage._camera
var _establish: RefCounted:
	get: return _stage._establish
var _drift: RefCounted:
	get: return _stage._drift
var _eye: RefCounted:
	get: return _stage._eye
var _shake: RefCounted:
	get: return _stage._shake
var _heat_haze: Control:
	get: return _stage._heat_haze
var _world_corruption: Control:
	get: return _stage._world_corruption
var _local_corruption: Control:
	get: return _stage._local_corruption
var _barrier: Control:
	get: return _stage._barrier
var _sprite_burst: Control:
	get: return _stage._sprite_burst
var _background_blackout: Control:
	get: return _stage._background_blackout
var _cast_pan: RefCounted:
	get: return _stage._cast_pan
var _atmosphere_layer: Control:
	get: return _stage._atmosphere_layer
var _ambient_emitters: Array:
	get: return _stage._ambient_emitters
var _backgrounds: Array:
	get: return _stage._backgrounds
var _portraits: Dictionary:
	get: return _stage._portraits
var _details: Dictionary:
	get: return _stage._details
var _contact_textures: Dictionary:
	get: return _stage._contact_textures
var _burst_textures: Dictionary:
	get: return _stage._burst_textures
var _textures: Dictionary:
	get: return _stage._textures
var _ui: Control
var _header: Control
var _dialogue: Control
var _speaker: Label
var _line: Label
var _location: Label
var _ready_dot: Control
var _contact_ring: Panel
var _contact_dot: Panel
var _choice_buttons: Array[Button] = []
var _language_button: Button
var _autoplay_button: Button
var _black: Control
var _monologue: Label
var _monologue_dot: Control
var _pause_menu: Control
var _ui_bindings: Array[Dictionary] = []


func _load_texture(path: String) -> Texture2D:
	var loaded := CONTENT_ADAPTER.load_texture(content.get("content_loader", CONTENT_ADAPTER.LOCAL_CONTENT.new()), path)
	_load_errors.append_array(loaded.errors)
	return loaded.resource


func _cast_profiles() -> Array:
	return content.get("guests", []) + content.get("supporting_cast", [])


func _profile(actor_id: String) -> Dictionary:
	for profile: Dictionary in _cast_profiles():
		if profile["id"] == actor_id: return profile
	return {}


func _contact_feedback_seconds() -> float:
	return float(content.get("contact", {}).get("feedback_seconds", 0.45))


func _contact_complete() -> bool:
	return current_beat().get("type") == "contact" and _contact.is_confirmed() and _contact_time >= 0.0 and _elapsed - _contact_time + 0.000000001 >= _contact_feedback_seconds()


func contact_target() -> Dictionary:
	var result := {"center": Vector2.ZERO, "radius": 0.0, "visible": false,
		"ready": false, "confirmed": _contact.is_confirmed()}
	if current_beat().get("type") != "contact" or not _load_errors.is_empty(): return result
	var profile := _profile(str(current_beat().get("speaker", "")))
	var uv: Array = profile.get("contact_uv", [0.5, 0.52])
	var rect := _contact_world_rect()
	var camera := _world_transform()
	result["center"] = camera * (rect.position + rect.size * Vector2(float(uv[0]), float(uv[1])))
	result["radius"] = rect.size.y * float(profile.get("contact_radius_ratio", 0.035)) * minf(camera.x.length(), camera.y.length())
	result["visible"] = not _paused and rect.has_area()
	result["ready"] = result["visible"] and _reveal.sample()["phase"] == "holding" and not _contact.is_confirmed()
	return result


func _try_contact(point: Vector2) -> bool:
	var target := contact_target()
	if not bool(target["ready"]): return false
	if not _contact.confirm_at(point, target["center"], float(target["radius"])): return false
	_contact_time = _elapsed
	_host_event("contact_confirmed")
	_render()
	return true


func _present_contact() -> void:
	var target := contact_target()
	_contact_ring.visible = bool(target["visible"]) and (_reveal.sample()["phase"] == "holding")
	if not _contact_ring.visible: return
	var progress := clampf((_elapsed - _contact_time) / _contact_feedback_seconds(), 0.0, 1.0) if _contact.is_confirmed() else 0.0
	var pulse := 1.0 if _contact.is_confirmed() else 0.88 + 0.12 * sin(_elapsed * 3.2)
	var diameter := float(target["radius"]) * (1.0 + progress * 1.7)
	_contact_ring.size = Vector2.ONE * diameter
	_contact_ring.position = (target["center"] as Vector2) - _contact_ring.size * 0.5
	_contact_ring.modulate.a = (1.0 - progress) * pulse
	_contact_dot.size = Vector2.ONE * maxf(4.0, float(target["radius"]) * 0.20)
	_contact_dot.position = (_contact_ring.size - _contact_dot.size) * 0.5


func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		set_language("ko" if get_language() == "en" else "en")
	elif event.keycode == KEY_ESCAPE: _toggle_pause()
	elif event.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		if _paused: return
		var owner := get_viewport().gui_get_focus_owner()
		if owner != null: return
		_next()
	else: return
	get_viewport().set_input_as_handled()


func _toggle_pause() -> void:
	_paused = not _paused
	_apply(_session.suspend() if _paused else _session.resume())
	_text_audio.set_paused(_paused)
	get_viewport().gui_release_focus()
	_render()


func _valid_time(value: Variant, allow_unemitted: bool = false) -> bool:
	if not (value is float or value is int) or not is_finite(float(value)): return false
	return float(value) >= 0.0 or (allow_unemitted and float(value) == -1.0)


func _text(key: String) -> String:
	return text_set.text(key) if text_set != null else "[" + key + "]"


func get_language() -> String:
	return text_set.get_language() if text_set != null else "en"


func set_language(language: String) -> Array[String]:
	var same_language := language == get_language()
	var voice_position := _voice_position() if same_language else 0.0
	var voice_revision := str(_voice_state.get("source_revision", "")) if same_language else ""
	var errors: Array[String] = text_set.set_language(language)
	if not errors.is_empty(): return errors
	if not same_language: _autoplay_elapsed = 0.0
	var words: Dictionary = _reveal.get_state()
	var fraction := minf(1.0, float(words["elapsed"]) * float(words["chars_per_second"]) / maxf(1.0, str(words["text"]).length()))
	content = content_factory.call(text_set)
	for binding: Dictionary in _ui_bindings: binding["node"].text = _text(binding["key"])
	_reveal.start(_text(_resolved_text_key()), {"chars_per_second": float(words["chars_per_second"])})
	_set_reveal_fraction(fraction)
	_begin_text_audio(voice_position, voice_revision)
	language_changed.emit(language)
	_render()
	return []


func _set_reveal_fraction(fraction: float) -> void:
	var state: Dictionary = _reveal.get_state()
	state["elapsed"] = float(str(state["text"]).length()) / float(state["chars_per_second"]) * fraction
	state["phase"] = "holding" if fraction >= 1.0 else "revealing"
	_load_errors.append_array(_reveal.restore(state))
	if fraction >= 1.0: _emit_revealed_manpu()


func _begin_text_audio(voice_position: float = 0.0, resume_revision: String = "") -> void:
	# Replay rebuilds visual controllers only; start audio once at the final cue.
	if _replaying_checkpoint: return
	_voice_waiting = false
	var settings: Dictionary = content.get("text_audio", {}).duplicate()
	settings.merge(current_beat().get("text_audio", {}), true)
	settings.merge(text_audio_settings, true)
	var voices: Dictionary = content.get("voiceovers", {}).get(get_language(), {})
	var supplied: AudioStream = voices.get(_resolved_text_key())
	_voice_state = voice_policy.resolve(_resolved_text_key(), get_language(), supplied) if voice_policy != null else {"status": "none", "voice_policy": "none", "stream": null}
	var voice: AudioStream = _voice_state.get("stream") if _voice_state["status"] == "ready" else null
	# Speech begins when the cinematic's caption becomes visible. Its existing
	# first-input motion completion stays intact; no voice ends or skips a beat.
	if voice != null and settings.get("mode", "auto") == "auto":
		if _cinematic() and not _cinematic_complete():
			_voice_waiting = true
			settings["mode"] = "silent"
			voice = null
		else:
			_set_reveal_fraction(1.0)
			_emit_revealed_manpu()
	elif _cinematic():
		settings["mode"] = "silent"
	_text_audio.stop()
	_voice_effects.reset()
	# Visual and vocal coordination belongs to this host, keyed by the actual
	# voiced speaker. An offscreen voice or protagonist reply stays dry.
	var speaker_id := str(_voice_state.get("speaker_id", ""))
	var display: Dictionary = _profile(speaker_id).get("transmission_display", {})
	var transmitted: bool = voice != null and settings.get("mode", "auto") == "auto" and _cast.visible_ids().has(speaker_id) and bool(_cast._projection.get(speaker_id, false)) and display.get("voice_effect", "") == "transmission_voice"
	_voice_effects.set_bypassed(not transmitted)
	if transmitted: settings["voice_bus"] = _voice_effects.get_output_bus()
	var errors: Array[String] = _text_audio.configure(settings)
	_load_errors.append_array(errors)
	if not errors.is_empty(): return
	var words: Dictionary = _reveal.sample()
	var resume := voice_position if not resume_revision.is_empty() and resume_revision == str(_voice_state.get("source_revision", "")) else 0.0
	_text_audio.begin(str(words["text"]), voice, int(words["visible_characters"]), resume)
	_text_audio.set_paused(_paused)


func _start_waiting_voice() -> void:
	if _voice_waiting and not _replaying_checkpoint and _cinematic_complete():
		_begin_text_audio()


func get_voice_state() -> Dictionary:
	var result := _voice_state.duplicate(true)
	result.erase("stream")
	result["waiting_for_cinematic"] = _voice_waiting
	result["playback"] = _text_audio.get_state()
	result["processing"] = _voice_effects.get_state()
	return result


func _voice_position() -> float:
	var audio: Dictionary = _text_audio.get_state()
	return -1.0 if bool(audio["voice_finished"]) else float(audio["voice_position_seconds"])


func _exit_tree() -> void:
	if not _session.view().is_empty():
		_session.cancel("host_exit")
		_session.drain_events()
	_text_audio.stop()
	_voice_effects.cleanup()


func _build_ui() -> void:
	gui_input.connect(_on_scene_input)
	_ui = _container(self)
	_header = _container(_ui)
	_edge_gradient(_header, "TopGradient", Rect2(0, 0, 1280, 190), true)
	var title := _label(_header, "episode.title", Rect2(40, 26, 720, 34), 22)
	title.add_theme_color_override("font_color", ACCENT)
	_location = _label(_header, "", Rect2(40, 72, 1000, 38), 22)
	_language_button = _button(_header, "ui.language_target", Rect2(930, 26, 150, 38), func() -> void: set_language("ko" if get_language() == "en" else "en"))
	var menu := _button(_header, "episode.ui.menu", Rect2(1096, 26, 146, 38), _toggle_pause)
	for button: Button in [_language_button, menu]:
		for state in ["normal", "hover", "pressed"]:
			button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
		button.add_theme_color_override("font_hover_color", ACCENT)
	_dialogue = _container(_ui)
	_edge_gradient(_dialogue, "BottomGradient", Rect2(0, 620, 1280, 280), false)
	_speaker = _label(_dialogue, "", Rect2(58, 702, 1100, 34), 24)
	_speaker.add_theme_color_override("font_color", ACCENT)
	_line = _label(_dialogue, "", Rect2(58, 752, 1135, 108), 26)
	_ready_dot = _indicator(_dialogue, Vector2(1207, 853))
	_contact_ring = Panel.new()
	_contact_ring.name = "FingertipContactRing"
	_contact_ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var ring_style := StyleBoxFlat.new()
	ring_style.bg_color = Color(ACCENT, 0.04)
	ring_style.border_color = Color(INK, 0.90)
	ring_style.set_border_width_all(2)
	ring_style.set_corner_radius_all(128)
	_contact_ring.add_theme_stylebox_override("panel", ring_style)
	_ui.add_child(_contact_ring)
	_contact_dot = _indicator(_contact_ring, Vector2.ZERO)
	for index in 2:
		var button := _button(_ui, "", Rect2(360, 482 + index * 68, 560, 58))
		button.name = "StoryChoice" + str(index + 1)
		button.add_theme_font_size_override("font_size", 21)
		button.pressed.connect(func() -> void: _choose(str(button.get_meta("choice_id", ""))))
		_choice_buttons.append(button)
		for state in ["normal", "hover", "pressed", "focus"]:
			var style := StyleBoxFlat.new()
			style.bg_color = Color(0.25, 0.18, 0.24, 0.96) if state in ["hover", "pressed"] else Color(0.085, 0.065, 0.11, 0.92)
			style.border_color = ACCENT if state in ["focus", "hover"] else Color(0.89, 0.73, 0.67, 0.42)
			style.set_border_width_all(1)
			style.set_corner_radius_all(3)
			button.add_theme_stylebox_override(state, style)
	_black = _container(self)
	var backdrop := ColorRect.new()
	backdrop.color = Color.BLACK
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_black.add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_monologue = _label(_black, "", Rect2(170, 280, 940, 340), 30)
	_monologue.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_monologue.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_monologue_dot = _indicator(_black, Vector2(636, 748))
	# Keep the user's transport control reachable even when cinematic direction
	# hides the normal header or a monologue covers the world with black.
	_autoplay_button = _button(self, "", Rect2(730, 26, 190, 38), func() -> void: set_autoplay_enabled(not _autoplay_enabled))
	_autoplay_button.name = "AutoplayToggle"
	_autoplay_button.toggle_mode = true
	for state in ["normal", "hover", "pressed"]:
		_autoplay_button.add_theme_stylebox_override(state, StyleBoxEmpty.new())
	_autoplay_button.add_theme_color_override("font_hover_color", ACCENT)

	_pause_menu = _container(self)
	_pause_menu.mouse_filter = Control.MOUSE_FILTER_STOP
	var veil := ColorRect.new()
	veil.color = Color(0.03, 0.025, 0.05, 0.85)
	veil.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_pause_menu.add_child(veil)
	veil.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(_pause_menu, Rect2(390, 200, 500, 510))
	var pause_title := _label(_pause_menu, "episode.title", Rect2(420, 233, 440, 64), 25)
	pause_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_button(_pause_menu, "episode.ui.resume", Rect2(435, 318, 410, 54), _toggle_pause)
	_button(_pause_menu, "episode.ui.restart", Rect2(435, 388, 410, 54), _restart)
	_button(_pause_menu, "episode.ui.lab", Rect2(435, 458, 410, 54), func() -> void: navigate.emit("game:lab"))
	_button(_pause_menu, "ui.language_target", Rect2(435, 610, 410, 46), func() -> void: set_language("ko" if get_language() == "en" else "en"))


func _on_scene_input(event: InputEvent) -> void:
	var clicked: bool = event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed
	var touched: bool = event is InputEventScreenTouch and event.pressed
	if clicked or touched:
		accept_event()
		if current_beat().get("type") == "contact" and _reveal.sample()["phase"] == "holding":
			_try_contact(event.position)
		else:
			_next()


func _edge_gradient(parent: Node, node_name: String, rect: Rect2, top: bool) -> void:
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.5, 1.0])
	var clear := Color(0.045, 0.03, 0.065, 0.0)
	var middle := Color(0.045, 0.03, 0.065, 0.67)
	var edge := Color(0.045, 0.03, 0.065, 0.97)
	gradient.colors = PackedColorArray([edge, middle, clear] if top else [clear, middle, edge])
	var texture := GradientTexture2D.new()
	texture.gradient = gradient
	texture.width = 2
	texture.height = 512
	texture.fill_from = Vector2(0, 0)
	texture.fill_to = Vector2(0, 1)
	var node := TextureRect.new()
	node.name = node_name
	node.texture = texture
	node.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	node.position = rect.position
	node.size = rect.size
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(node)


func _indicator(parent: Node, point: Vector2) -> Control:
	var node := Panel.new()
	node.position = point
	node.size = Vector2(8, 8)
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = ACCENT
	style.set_corner_radius_all(4)
	node.add_theme_stylebox_override("panel", style)
	parent.add_child(node)
	return node


func _container(parent: Node) -> Control:
	var node := Control.new()
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(node)
	node.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return node


func _panel(parent: Node, rect: Rect2, fill: Color = Color(0.075, 0.065, 0.10, 0.95)) -> void:
	var node := Panel.new()
	node.position = rect.position
	node.size = rect.size
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = Color("76616b")
	style.set_border_width_all(1)
	style.set_corner_radius_all(5)
	node.add_theme_stylebox_override("panel", style)
	parent.add_child(node)


func _label(parent: Node, key: String, rect: Rect2, font_size: int) -> Label:
	var node := Label.new()
	node.position = rect.position
	node.size = rect.size
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	node.add_theme_font_size_override("font_size", font_size)
	node.add_theme_color_override("font_color", INK)
	if not key.is_empty():
		node.text = _text(key)
		_ui_bindings.append({"node": node, "key": key})
	parent.add_child(node)
	return node


func _button(parent: Node, key: String, rect: Rect2, action: Callable = Callable()) -> Button:
	var node := Button.new()
	node.text = _text(key) if not key.is_empty() else ""
	node.position = rect.position
	node.size = rect.size
	node.add_theme_font_size_override("font_size", 17)
	node.add_theme_color_override("font_color", INK)
	node.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	for state in ["normal", "hover", "pressed", "focus"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("52404d") if state in ["hover", "pressed"] else Color("302a38")
		style.border_color = ACCENT if state in ["focus", "hover"] else Color("76616b")
		style.set_border_width_all(1)
		style.set_corner_radius_all(5)
		node.add_theme_stylebox_override(state, style)
	node.pressed.connect(func() -> void:
		get_viewport().gui_release_focus()
		if action.is_valid(): action.call())
	if not key.is_empty(): _ui_bindings.append({"node": node, "key": key})
	parent.add_child(node)
	return node
func _render() -> void:
	if _line == null: return
	if _recovery_button != null: _recovery_button.visible = _checkpoint_refused
	if not _load_errors.is_empty():
		_black.hide()
		_dialogue.show()
		_line.text = _text("error.scene_load") + "\n" + "\n".join(_load_errors)
		_line.visible_characters = -1
		_line.add_theme_font_size_override("font_size", 17)
		_ready_dot.hide()
		_contact_ring.hide()
		for button: Button in _choice_buttons: button.hide()
		return
	var beat := current_beat()
	var kind := str(beat["type"])
	_stage.present()
	_ui.visible = kind != "monologue"
	_header.visible = kind not in ["eye", "detail", "contact"]
	_dialogue.visible = not _cinematic() or _cinematic_complete()
	var words: Dictionary = _reveal.sample()
	_line.text = str(words["text"])
	_line.visible_characters = int(words["visible_characters"])
	var speaker := str(beat.get("speaker", ""))
	_speaker.text = _text(str(beat["speaker_name"])) if beat.has("speaker_name") else (_text("guest." + speaker + ".name") if not speaker.is_empty() else _text("episode.ui.protagonist"))
	_location.text = _text(str(beat["place_name"])) if beat.has("place_name") else str(content["backgrounds"][_background_index]["name"])
	_location.modulate.a = 1.0 if kind in ["walk", "establish"] else clampf(1.0 - (_elapsed - 1.8) / 1.2, 0.0, 1.0)
	_black.visible = kind == "monologue"
	_monologue.text = str(words["text"])
	_monologue.visible_characters = int(words["visible_characters"])
	var held := str(words["phase"]) == "holding"
	var ready := held and kind != "contact" and not _choice_pending() and not _paused and (not _cinematic() or _cinematic_complete())
	_ready_dot.visible = ready and kind != "monologue"
	_monologue_dot.visible = ready and kind == "monologue"
	var pulse := 0.65 + 0.35 * sin(_elapsed * 3.2) * sin(_elapsed * 3.2)
	_ready_dot.modulate.a = pulse
	_monologue_dot.modulate.a = pulse
	var options: Array = beat.get("choices", [])
	var autoplay := get_autoplay_state()
	for index in _choice_buttons.size():
		var button := _choice_buttons[index]
		button.visible = _choice_pending() and held and not _paused and index < options.size()
		if button.visible:
			button.text = _text(str(options[index]["text"]))
			var is_default: bool = autoplay["enabled"] and str(options[index]["id"]) == str(autoplay["default_choice"])
			if is_default and str(autoplay["blocked_reason"]).is_empty():
				button.text += "  ·  " + _text("episode.ui.autoplay_choice").replace("{seconds}", str(ceili(float(autoplay["remaining_seconds"]))))
			button.add_theme_color_override("font_color", ACCENT if is_default else INK)
			button.set_meta("choice_id", str(options[index]["id"]))
	_pause_menu.visible = _paused
	_language_button.text = _text("ui.language_target")
	_autoplay_button.text = _text("episode.ui.autoplay_on" if _autoplay_enabled else "episode.ui.autoplay_off")
	_autoplay_button.set_pressed_no_signal(_autoplay_enabled)
	_autoplay_button.add_theme_color_override("font_color", ACCENT if _autoplay_enabled else INK)
	_present_contact()
	queue_redraw()



func _ready() -> void:
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_voice_effects)
	add_child(_text_audio)
	_load_errors.append_array(_voice_effects.configure(content.get("transmission_voice", {})))
	var resources := {"backgrounds": [], "actors": {}, "portraits": {}, "details": {}, "contacts": {}, "burst": {}, "manpu": content.get("manpu_textures", {})}
	for item: Dictionary in content.get("backgrounds", []): resources["backgrounds"].append(_load_texture(item["path"]))
	for profile: Dictionary in _cast_profiles():
		resources["actors"][profile["id"]] = _load_texture(profile["path"])
		for field: String in {"eye_close_path": "portraits", "detail_path": "details", "contact_path": "contacts"}:
			if profile.has(field): resources[{"eye_close_path": "portraits", "detail_path": "details", "contact_path": "contacts"}[field]][profile["id"]] = _load_texture(profile[field])
	for id: String in content.get("sprite_burst", {}).get("sprites", {}): resources["burst"][id] = _load_texture(content["sprite_burst"]["sprites"][id])
	_load_errors.append_array(_stage.configure(BINDING.settings(content), resources, TRANSMISSION_DISPLAY.new()))
	if _load_errors.is_empty():
		add_child(_stage)
		_stage.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		_load_errors.append_array(_stage._load_errors)
	_build_ui()
	_recovery_button = _button(self, "episode.ui.restart", Rect2(450, 520, 380, 64), _restart)
	_recovery_button.hide()
	if not _load_errors.is_empty(): _render(); return
	if not _admit_documents(
		JSON.parse_string(FileAccess.get_file_as_string("res://addons/scenario_runtime/presentation/front_types.json")),
		JSON.parse_string(FileAccess.get_file_as_string("res://narrative/catalog.json")),
		JSON.parse_string(FileAccess.get_file_as_string("res://narrative/program.json"))):
		_render()
		return
	_load_errors.append_array(_transport.configure(content.get("autoplay", {})))
	if _load_errors.is_empty():
		if saved_state.is_empty(): _restart()
		else: _restore_game()
	_render()


func _admit_documents(types_document: Variant, catalog_document: Variant, program_document: Variant) -> bool:
	if not types_document is Dictionary:
		_load_errors.append("Afterlight requires valid installed capability schemas.")
		return false
	var admitted_catalog: Dictionary = CATALOG.parse(catalog_document, types_document)
	if admitted_catalog.has("error"):
		_load_errors.append(str(admitted_catalog))
		return false
	var admitted_program: Dictionary = PROGRAM.parse(program_document, admitted_catalog)
	if admitted_program.has("error"):
		_load_errors.append(str(admitted_program))
		return false
	var binding_errors: Array[String] = []
	for node: Dictionary in admitted_program["nodes"].values():
		for cue: Dictionary in node.get("cues", []):
			binding_errors.append_array(_stage.validate_operation(str(cue["effect"]["type"]), cue["effect"]["parameters"]))
	if not binding_errors.is_empty():
		_load_errors.append_array(binding_errors)
		return false
	var capabilities := {}
	for id: String in types_document: capabilities[id] = types_document[id]["version"]
	_types = types_document.duplicate(true)
	_catalog_document = catalog_document.duplicate(true)
	_catalog = admitted_catalog
	_program = admitted_program
	_policy = {"session_id": "afterlight_episode", "capabilities": capabilities, "channels": ["afterlight_vn"], "bindings": ["stage"]}
	return true


func current_beat() -> Dictionary:
	return _current_review


func _restart(_restored_choices: Dictionary = {}) -> void:
	if not _session.view().is_empty():
		_session.cancel("restart")
		_session.drain_events()
	if _checkpoint_refused: _load_errors.clear()
	_checkpoint_refused = false
	_paused = false
	_history.clear()
	_manpu_history.clear()
	_contact_history.clear()
	_current_review.clear()
	_shown.clear()
	_journal.clear()
	_clock = {"sequence": 0.0, "presentation": 0.0, "reading": 0.0}
	_stage.reset()
	_elapsed = 0.0
	_session = SESSION.new()
	_apply(_session.start(_program, _catalog, _policy))
	_render()


func _present_node(node: Dictionary) -> void:
	if not _shown.is_empty():
		_history.append(_elapsed)
		_manpu_history.append(_manpu_event_time)
		_contact_history.append(_contact_time)
	_shown = node.duplicate(true)
	_reported_gate_events.clear()
	_current_review = EPISODE.inspect(node, _catalog_document)
	_elapsed = 0.0
	_manpu_event_time = -1.0
	_contact_time = -1.0
	_contact.reset()
	_text_audio.stop()
	_voice_effects.set_bypassed(true)
	_voice_effects.reset()
	_reveal.clear()
	_load_errors.append_array(_reveal.start(_text(str(node.get("text_key", ""))), {"chars_per_second": float(node.get("presentation", {}).get("chars_per_second", 48.0))}))
	var choices: Array = []
	for option: Dictionary in node.get("options", []): choices.append(option["id"])
	_load_errors.append_array(_transport.enter(str(node["id"]), current_beat().get("autoplay", {}), choices))


func _apply(report: Dictionary) -> void:
	if report.has("error"):
		_load_errors.append(str(report))
		return
	_session.drain_events()
	if report.has("failure"):
		_load_errors.append(str(report["failure"]))
		return
	var needs_audio := false
	for event: Dictionary in report.get("events", []):
		_advance_to(event["clocks"])
		match event["type"]:
			"scenario/presented":
				_present_node(event["presentation"])
				needs_audio = true
			"scenario/effect_started":
				var effect: Dictionary = event["effect"]
				var type := str(effect["type"])
				_load_errors.append_array(_stage.execute(type, effect["parameters"]))
				_journal.append({"operation_id": event["operation_id"], "clocks": event["clocks"].duplicate(), "type": type, "parameters": effect["parameters"].duplicate(true)})
				if type == "front_reaction": _manpu_event_time = _elapsed
			"scenario/reveal_requested":
				_reveal.request_advance()
				_text_audio.sync_reveal(int(_reveal.sample()["visible_characters"]))
				_emit_revealed_manpu()
			"scenario/finish_requested":
				if event["gate_event"] == "cinematic_ready":
					_advance_clocks(30.0)
					_start_waiting_voice()
	if report.has("state") and report["state"].has("clocks"): _advance_to(report["state"]["clocks"])
	if needs_audio: _begin_text_audio()


func _advance_to(clocks: Dictionary) -> void:
	var sequence := maxf(0.0, float(clocks["sequence"]) - float(_clock["sequence"]))
	var presentation := maxf(0.0, float(clocks["presentation"]) - float(_clock["presentation"]))
	_elapsed += sequence
	_reveal.advance(sequence)
	if presentation > 0.0:
		_stage.advance(presentation)
		if not _journal.is_empty() and _journal.back().has("advance"):
			_journal.back()["advance"] = float(_journal.back()["advance"]) + presentation
		else: _journal.append({"advance": presentation})
	for key: String in _clock: _clock[key] = maxf(float(_clock[key]), float(clocks[key]))


func _host_event(name: String) -> void:
	var view := _session.view()
	if view.is_empty(): return
	var key := str(view["visit_id"]) + ":" + name
	if _reported_gate_events.has(key): return
	var report: Dictionary = _session.submit({"kind": "host_event", "session_id": _policy["session_id"], "node_id": view["node_id"], "visit_id": view["visit_id"], "name": name})
	if bool(report.get("consumed", false)): _reported_gate_events[key] = true
	_apply(report)


func _emit_revealed_manpu() -> void:
	if _reveal.sample()["phase"] == "holding": _host_event("text_revealed")


func _advance_clocks(delta: float) -> void:
	if not is_finite(delta) or delta < 0.0: return
	# Reveal is a bound capability event. Split exactly at its completion, then
	# Session schedules every authored cue and operation on the supplied clocks.
	var words: Dictionary = _reveal.get_state()
	var remaining := maxf(0.0, float(str(words["text"]).length()) / float(words["chars_per_second"]) - float(words["elapsed"]))
	if _reveal.sample()["phase"] == "revealing" and remaining <= delta:
		_tick_session(remaining)
		_emit_revealed_manpu()
		_tick_session(delta - remaining)
	else:
		_tick_session(delta)
		_emit_revealed_manpu()
	if _cinematic() and _cinematic_complete(): _host_event("cinematic_ready")


func _tick_session(delta: float) -> void:
	var world_paused := bool(_shown.get("presentation", {}).get("world_paused", false))
	_apply(_session.tick({"sequence": delta, "presentation": 0.0 if world_paused else delta, "reading": delta}))


func _process(delta: float) -> void:
	if _paused or not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0: return
	var ready := str(get_autoplay_state()["blocked_reason"]).is_empty()
	var previous := str(_shown.get("id", ""))
	var step := delta
	if current_beat().get("type") == "contact" and _contact.is_confirmed(): step = minf(delta, maxf(0.0, _contact_feedback_seconds() - (_elapsed - _contact_time)))
	_advance_clocks(step)
	_start_waiting_voice()
	_text_audio.update_reveal(int(_reveal.sample()["visible_characters"]), step)
	if previous == _shown.get("id"): _update_autoplay(step if ready else 0.0)
	_render()


func _cinematic() -> bool:
	return not str(_shown.get("presentation", {}).get("cinematic_controller", "")).is_empty()


func _cinematic_complete() -> bool:
	var controller := str(_shown.get("presentation", {}).get("cinematic_controller", ""))
	if controller == "duration": return _elapsed >= float(_shown["presentation"]["cinematic_seconds"])
	return _stage.cinematic_complete(controller) if not controller.is_empty() else false


func _next() -> void:
	if _paused or not _load_errors.is_empty(): return
	_transport.manual_action()
	_emit_revealed_manpu()
	if _session.view().get("pending_gate", {}).get("event") == "host_return": _toggle_pause()
	else: _apply(_session.submit({"kind": "advance"}))
	_render()


func _continue_story() -> void:
	_apply(_session.submit({"kind": "advance"}))


func _choice_pending() -> bool:
	return _session.view().get("kind") == "choice"


func _choose(option_id: String) -> void:
	if _paused or not _load_errors.is_empty(): return
	_transport.manual_action()
	_emit_revealed_manpu()
	_apply(_session.submit({"kind": "choose", "choice_id": option_id}))
	_render()


func _resolved_text_key(_beat: Dictionary = {}) -> String:
	return str(_shown.get("text_key", ""))


func set_autoplay_enabled(enabled: bool) -> void:
	_transport.set_enabled(enabled)
	_render()


func _autoplay_settings() -> Dictionary:
	var settings: Dictionary = content.get("autoplay", {}).duplicate()
	settings.merge(current_beat().get("autoplay", {}), true)
	return settings


func get_autoplay_state() -> Dictionary:
	var reason := ""
	var audio: Dictionary = _text_audio.get_state()
	if not _load_errors.is_empty(): reason = "load_error"
	elif _paused: reason = "paused"
	elif _cinematic() and not _cinematic_complete(): reason = "cinematic"
	elif _reveal.sample()["phase"] != "holding": reason = "text"
	elif _voice_waiting or (audio["active_mode"] == "voice" and not audio["voice_finished"]): reason = "voice"
	elif current_beat().get("type") == "contact": reason = "required_input"
	elif current_beat().get("type") == "ending": reason = "ended"
	return _transport.state(reason, _choice_pending())


func _update_autoplay(delta: float) -> void:
	if _replaying_checkpoint: return
	var action: Dictionary = _transport.tick(delta, str(get_autoplay_state()["blocked_reason"]), _choice_pending(), true)
	if not action.is_empty(): _apply(_session.submit(action))


func _validate_autoplay() -> void:
	_load_errors.append_array(TRANSPORT.validate(content.get("autoplay", {}), false))
	for beat: Dictionary in beats:
		var ids: Array = []
		for option: Dictionary in beat.get("choices", []): ids.append(option["id"])
		_load_errors.append_array(TRANSPORT.validate(beat.get("autoplay", {}), true, ids))


func _world_transform() -> Transform2D: return _stage._world_transform()
func _cast_transform() -> Transform2D: return _stage._cast_transform()
func presented_background_rect() -> Rect2: return _stage.presented_background_rect()
func _contact_world_rect() -> Rect2: return _stage._contact_world_rect()
func _portrait_rect(detail: bool) -> Rect2: return _stage._portrait_rect(detail)
func get_atmosphere_state() -> Dictionary: return _stage.get_atmosphere_state()


func save_game() -> Dictionary:
	var words: Dictionary = _reveal.get_state()
	return {"story_version": 5, "beat_id": current_beat()["id"], "history": _history.duplicate(), "elapsed": _elapsed,
		"choices": _choices.duplicate(true), "manpu_history": _manpu_history.duplicate(), "manpu_event_time": _manpu_event_time,
		"contact_history": _contact_history.duplicate(), "contact_time": _contact_time,
		"reveal_fraction": minf(1.0, float(words["elapsed"]) * float(words["chars_per_second"]) / maxf(1.0, str(words["text"]).length())),
		"voice_position_seconds": _voice_position(), "voice_source_revision": str(_voice_state.get("source_revision", "")), "language": get_language(),
		"autoplay": {"enabled": _autoplay_enabled, "elapsed_seconds": _autoplay_elapsed},
		"session": _session.snapshot(), "presentation_journal": _journal.duplicate(true)}


func _restore_game() -> void:
	_checkpoint_refused = true
	# The game envelope is independently versioned. The Session validates its
	# program/catalog identities before any visual or audio state is applied.
	if saved_state.get("story_version") != 5:
		_load_errors.append("Afterlight checkpoint requires story_version 5; earlier director checkpoints require migration.")
		return
	var candidate = SESSION.new()
	var admitted: Dictionary = candidate.restore(_program, _catalog, _policy, saved_state.get("session"))
	if admitted.has("error"):
		_load_errors.append(str(admitted))
		return
	var checkpoint_state: Dictionary = candidate.snapshot()["state"]
	var current_node: Dictionary = _program["nodes"][candidate.view()["node_id"]]
	if saved_state.get("beat_id") != current_node.get("presentation", {}).get("review", {}).get("id"):
		_load_errors.append("Checkpoint beat does not match its admitted Session node."); return
	if not saved_state.get("voice_source_revision", "") is String or not saved_state.get("language") is String or not saved_state.get("choices") is Dictionary:
		_load_errors.append("Checkpoint language, voice revision and choice records are invalid."); return
	var facts := {}
	for key: String in checkpoint_state["facts"]:
		if checkpoint_state["facts"][key] != "": facts[key] = checkpoint_state["facts"][key]
	if not CATALOG.equivalent(facts, saved_state["choices"]):
		_load_errors.append("Checkpoint choices disagree with Session facts."); return
	for field: String in ["history", "manpu_history", "contact_history"]:
		if not saved_state.get(field) is Array or saved_state[field].size() >= beats.size():
			_load_errors.append("Checkpoint history must be bounded arrays."); return
		for value: Variant in saved_state[field]:
			if not _valid_time(value, field != "history"):
				_load_errors.append("Checkpoint history contains invalid elapsed time."); return
	if saved_state["history"].size() != saved_state["manpu_history"].size() or saved_state["history"].size() != saved_state["contact_history"].size():
		_load_errors.append("Checkpoint history lengths disagree."); return
	var journal: Variant = saved_state.get("presentation_journal")
	if not journal is Array or journal.size() > 100000:
		_load_errors.append("Afterlight presentation journal must be a bounded array.")
		return
	var operations: Dictionary = candidate.snapshot()["state"]["operations"]
	var seen_operations := {}
	var presentation_time := 0.0
	var sequence_time := 0.0
	var entered_at := 0.0
	for record: Variant in journal:
		if not record is Dictionary or (not record.has("advance") and not record.has("type")):
			_load_errors.append("Afterlight presentation journal record is invalid.")
			return
		if record.has("advance"):
			if record.size() != 1 or not _valid_time(record["advance"]): _load_errors.append("Invalid presentation elapsed time."); return
			presentation_time += float(record["advance"])
		else:
			if not _types.has(record["type"]) or not record.get("parameters") is Dictionary:
				_load_errors.append("Unknown presentation journal capability."); return
			var operation_id := str(record.get("operation_id", ""))
			if not operations.has(operation_id) or seen_operations.has(operation_id):
				_load_errors.append("Presentation journal must match unique Session operations."); return
			var operation: Dictionary = operations[operation_id]
			if operation["effect"]["type"] != record["type"] or not CATALOG.equivalent(operation["effect"]["parameters"], record["parameters"]):
				_load_errors.append("Presentation journal does not match its admitted Session command."); return
			var clocks: Variant = record.get("clocks")
			if record.size() != 4 or not clocks is Dictionary or clocks.size() != 3:
				_load_errors.append("Presentation journal requires explicit clocks."); return
			for clock: String in ["sequence", "presentation", "reading"]:
				if not _valid_time(clocks.get(clock)) or float(clocks[clock]) > float(checkpoint_state["clocks"][clock]) + 0.00000001:
					_load_errors.append("Presentation journal clock exceeds its Session."); return
			if float(clocks["sequence"]) < sequence_time or not is_equal_approx(float(clocks["presentation"]), presentation_time) or not is_equal_approx(float(clocks[operation["clock"]]), float(operation["start_time"])):
				_load_errors.append("Presentation journal clocks disagree with Session operation order."); return
			sequence_time = float(clocks["sequence"])
			if record["type"] == "front_view" and operation["node_id"] == current_node["id"]: entered_at = float(clocks["sequence"])
			seen_operations[operation_id] = true
			var checked: Dictionary = CATALOG.resolve({"type": record["type"], "parameters": record["parameters"]}, _catalog)
			if checked.has("error"): _load_errors.append(str(checked)); return
	if seen_operations.size() != operations.size():
		_load_errors.append("Presentation journal is missing Session operations."); return
	for key: String in ["elapsed", "reveal_fraction", "voice_position_seconds", "manpu_event_time", "contact_time"]:
		if not _valid_time(saved_state.get(key), key in ["voice_position_seconds", "manpu_event_time", "contact_time"]):
			_load_errors.append("Invalid Afterlight checkpoint time: " + key); return
	if not is_equal_approx(presentation_time, float(checkpoint_state["clocks"]["presentation"])) or not is_equal_approx(float(saved_state["elapsed"]), float(checkpoint_state["clocks"]["sequence"]) - entered_at):
		_load_errors.append("Checkpoint presentation and node clocks disagree with Session."); return
	if float(saved_state["manpu_event_time"]) > float(saved_state["elapsed"]) or float(saved_state["contact_time"]) > float(saved_state["elapsed"]):
		_load_errors.append("Checkpoint event time exceeds the current presentation."); return
	if float(saved_state["reveal_fraction"]) > 1.0:
		_load_errors.append("Invalid Afterlight reveal fraction."); return
	var autoplay: Variant = saved_state.get("autoplay", {"enabled": false, "elapsed_seconds": 0.0})
	if not autoplay is Dictionary or not autoplay.get("enabled") is bool or not _valid_time(autoplay.get("elapsed_seconds")):
		_load_errors.append("Invalid Afterlight transport checkpoint."); return
	_checkpoint_refused = false
	_replaying_checkpoint = true
	_stage.reset()
	for record: Dictionary in journal:
		if record.has("advance"): _stage.advance(float(record["advance"]))
		else: _load_errors.append_array(_stage.execute(str(record["type"]), record["parameters"]))
	_session = candidate
	_session.drain_events()
	_shown.clear()
	_present_node(_program["nodes"][_session.view()["node_id"]])
	_clock = _session.snapshot()["state"]["clocks"].duplicate()
	for event: String in _session.snapshot()["state"]["gate_events"]:
		_reported_gate_events[str(_session.view()["visit_id"]) + ":" + event] = true
	_elapsed = float(saved_state["elapsed"])
	_history.assign(saved_state.get("history", []))
	_manpu_history.assign(saved_state.get("manpu_history", []))
	_contact_history.assign(saved_state.get("contact_history", []))
	_manpu_event_time = float(saved_state["manpu_event_time"])
	_contact_time = float(saved_state["contact_time"])
	_contact.reset(_contact_time >= 0.0)
	_journal = journal.duplicate(true)
	_paused = false
	_set_reveal_fraction(float(saved_state["reveal_fraction"]))
	if _session.view()["status"] == "suspended": _apply(_session.resume())
	_replaying_checkpoint = false
	_begin_text_audio(float(saved_state["voice_position_seconds"]), str(saved_state.get("voice_source_revision", "")))
	_autoplay_enabled = bool(autoplay["enabled"])
	if str(saved_state.get("voice_source_revision", "")) == str(_voice_state.get("source_revision", "")) and saved_state.get("language") == get_language() and str(get_autoplay_state()["blocked_reason"]).is_empty():
		_autoplay_elapsed = minf(float(autoplay["elapsed_seconds"]), float(get_autoplay_state()["delay_seconds"]))
