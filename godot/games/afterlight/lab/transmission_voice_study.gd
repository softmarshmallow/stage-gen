extends "res://lab/study_host.gd"

## This host owns the listening comparison, prepared Eira clip and controls.
## The processor only receives a voice bus; changing its mix never replays it.
const VOICE_EFFECTS = preload("res://addons/game_presentation/audio/voice_effects.gd")
const TEXT_AUDIO = preload("res://addons/game_presentation/audio/text_reveal_audio.gd")
const DISPLAY = preload("res://transmission_display.gd")
const LINE_ID := "episode.eira_on_the_relay"
var _processor = VOICE_EFFECTS.new()
var _audio = TEXT_AUDIO.new()
var _display: Control
var _eira: Dictionary = {}
var _portrait: Texture2D
var _clock := 0.0
var _paused := false
var _has_started := false
var _dry := true
var _strength := 0.65
var _play_button: Button
var _pause_button: Button
var _dry_button: Button
var _wet_button: Button
var _strength_slider: HSlider
var _strength_label: Label


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	var backgrounds: Array = content.get("backgrounds", [])
	if backgrounds.size() > 3:
		_backgrounds.append(_load_texture(backgrounds[3]["path"]))
		if _backgrounds[0] != null:
			var extent := _backgrounds[0].get_size()
			extent *= maxf(DESIGN_SIZE.x / extent.x, DESIGN_SIZE.y / extent.y)
			_base_background = Rect2((DESIGN_SIZE - extent) * 0.5, extent)
	for actor: Dictionary in content.get("supporting_cast", []):
		if actor["id"] == "eira":
			_eira = actor.duplicate(true)
			_portrait = _load_texture(actor["path"])
	_display = DISPLAY.new()
	_display.name = "PreparedEiraTransmission"
	add_child(_display)
	_processor.name = "LabVoiceProcessor"
	add_child(_processor)
	_load_errors.append_array(_processor.configure({"preset": "transmission_voice", "strength": _strength, "bypass": _dry}))
	_audio.name = "LabVoicePlayback"
	add_child(_audio)
	if _load_errors.is_empty():
		_load_errors.append_array(_audio.configure({"mode": "auto", "voice_bus": _processor.get_output_bus()}))
	_build_voice_ui()
	_update_voice_ui()
	_present_voice()


func _voice_stream() -> AudioStream:
	return content.get("voiceovers", {}).get(get_language(), {}).get(LINE_ID)


func _play_voice() -> void:
	var stream := _voice_stream()
	if stream == null or not _load_errors.is_empty(): return
	_audio.stop()
	_processor.reset()
	_paused = false
	_audio.set_paused(false)
	_has_started = true
	var text := _text(LINE_ID)
	_audio.begin(text, stream, text.length())
	_update_voice_ui()


func _stop_voice() -> void:
	_audio.stop()
	_processor.reset()
	_audio.set_paused(false)
	_paused = false
	_has_started = false
	_update_voice_ui()


func _toggle_pause() -> void:
	if not _has_started or bool(_audio.get_state()["voice_finished"]): return
	_paused = not _paused
	_audio.set_paused(_paused)
	_update_voice_ui()


func _select_dry(dry: bool) -> void:
	_dry = dry
	_load_errors.append_array(_processor.set_bypassed(dry))
	_update_voice_ui()


func _set_strength(value: float) -> void:
	_strength = value
	_load_errors.append_array(_processor.set_strength(value))
	_update_voice_ui()


func _process(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0: return
	if not _paused: _clock += delta
	_update_voice_ui()
	_present_voice()


func _present_voice() -> void:
	if _display == null: return
	var settings: Dictionary = _eira.get("transmission_display", {}).duplicate(true)
	settings["frame_rect"] = Rect2(365, 150, 550, 412)
	_display.present("eira", _portrait, Transform2D.IDENTITY, _clock, settings)
	queue_redraw()


func voice_study_state() -> Dictionary:
	return {"dry": _dry, "strength": _strength, "paused": _paused,
		"started": _has_started, "language": get_language(), "line_id": LINE_ID,
		"processor": _processor.get_state(), "audio": _audio.get_state()}


func _build_voice_ui() -> void:
	_ui = Control.new()
	_ui.name = "TransmissionVoiceStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(24, 22, 1232, 103), Color("211b28"))
	_label_text("study.transmission_voice.title", Rect2(46, 31, 700, 47), 29, INK)
	var description := _label_text("study.transmission_voice.description", Rect2(48, 82, 940, 30), 17, MUTED)
	description.size = Vector2(940, 30)
	_build_language_picker(Rect2(800, 39, 192, 38))
	_return_button = _button_text("ui.effects_menu", Rect2(1021, 48, 211, 44), func() -> void: navigate.emit("effects_menu"))
	_panel(Rect2(24, 596, 1232, 284), Color("211b28"))
	_label_text("guest.eira.name", Rect2(46, 611, 270, 30), 21, ACCENT)
	_line = _label("", Rect2(46, 649, 1165, 77), 21, INK)
	_line.size = Vector2(1165, 77)
	_dry_button = _button_text("study.transmission_voice.dry", Rect2(46, 741, 182, 42), _select_dry.bind(true))
	_dry_button.name = "DryVoice"
	_dry_button.toggle_mode = true
	_wet_button = _button_text("study.transmission_voice.wet", Rect2(240, 741, 212, 42), _select_dry.bind(false))
	_wet_button.name = "ProcessedVoice"
	_wet_button.toggle_mode = true
	_strength_label = _label("", Rect2(482, 735, 315, 26), 17, INK)
	_strength_slider = HSlider.new()
	_strength_slider.name = "VoiceStrengthSlider"
	_strength_slider.position = Vector2(482, 768)
	_strength_slider.size = Vector2(315, 24)
	_strength_slider.min_value = 0.0
	_strength_slider.max_value = 1.0
	_strength_slider.step = 0.05
	_strength_slider.value = _strength
	_strength_slider.value_changed.connect(_set_strength)
	_ui.add_child(_strength_slider)
	_play_button = _button_text("study.transmission_voice.play", Rect2(826, 741, 126, 42), _play_voice)
	_play_button.name = "PlayVoice"
	_pause_button = _button_text("ui.pause", Rect2(964, 741, 124, 42), _toggle_pause)
	_pause_button.name = "PauseVoice"
	_button_text("study.transmission_voice.stop", Rect2(1100, 741, 132, 42), _stop_voice).name = "StopVoice"
	_status = _label("", Rect2(46, 805, 1170, 24), 16, ACCENT)
	_status.name = "VoiceStudyStatus"
	var hint := _label_text("study.transmission_voice.hint", Rect2(46, 841, 1170, 26), 15, MUTED)
	hint.size = Vector2(1170, 26)


func _update_voice_ui() -> void:
	if _status == null: return
	_line.text = _text(LINE_ID)
	_dry_button.set_pressed_no_signal(_dry)
	_wet_button.set_pressed_no_signal(not _dry)
	_strength_label.text = _text("study.transmission_voice.strength", {"value": roundi(_strength * 100.0)})
	_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
	var state: Dictionary = _audio.get_state()
	_pause_button.disabled = not _has_started or bool(state["voice_finished"])
	_play_button.disabled = _voice_stream() == null or not _load_errors.is_empty()
	var phase := "idle" if not _has_started else ("finished" if state["voice_finished"] else ("paused" if _paused else "playing"))
	_status.text = _text("study.transmission_voice.status", {"mode": _text("study.transmission_voice.dry" if _dry else "study.transmission_voice.wet"), "phase": _text("study.transmission_voice." + phase), "seconds": "%.1f" % float(state["voice_position_seconds"])})
	if _voice_stream() == null: _status.text = _text("study.transmission_voice.unavailable")
	if not _load_errors.is_empty(): _status.text = "\n".join(_load_errors)


func _refresh_language() -> void:
	var active := _has_started and not bool(_audio.get_state()["voice_finished"])
	var was_paused := _paused
	_stop_voice()
	if active:
		_play_voice()
		if was_paused: _toggle_pause()
	_update_voice_ui()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		draw_texture_rect(_backgrounds[0], _base_background, false)


func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		_toggle_language()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
	else: return
	get_viewport().set_input_as_handled()


func _exit_tree() -> void:
	_audio.stop()
	_processor.cleanup()
