extends "res://lab/study_host.gd"

## Three individually routed Afterlight studies. Only effect behavior is shared
## across games; this UI, framing, text, and control arrangement belong here.
const DRIFT = preload("res://addons/game_presentation/camera/camera_drift.gd")
const INTERTITLE = preload("res://addons/game_presentation/text/intertitle.gd")
const HALO = preload("res://addons/game_presentation/effects/actor_halo.gd")
const PREVIEW_RECT := Rect2(32, 148, 1216, 468)
@export_enum("intertitle", "drift", "halo") var effect_kind := "intertitle"
var _drift = DRIFT.new()
var _intertitle = INTERTITLE.new()
var _halo: TextureRect
var _preview: Control
var _background_view: TextureRect
var _title_text: Label
var _study_heading: Label
var _draft_text: TextEdit
var _duration_slider: HSlider
var _duration_value: Label
var _action_button: Button
var _pause_button: Button
var _halo_toggle: Button
var _halo_color: ColorPickerButton
var _feedback: Label
var _paused := false
var _halo_enabled := true
var _drift_settings: Dictionary = {}
var _effect_sliders: Dictionary = {}
var _effect_values: Dictionary = {}
var _base_portrait := Rect2()
var _world_offset := Vector2.ZERO
var _guest_detail_textures: Dictionary = {}
var _draft_is_default := true
var _active_text_is_default := true
var _setting_default_draft := false
var _feedback_key := ""


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_guest_id = str(content.get("default_guest_id", ""))
	_drift_settings = DRIFT.DEFAULT_SETTINGS.duplicate()
	_drift_settings.merge(content.get("drift", {}), true)
	_build_preview()
	_build_effect_ui()
	if effect_kind != "intertitle":
		_load_cast_and_scenery()
	if _load_errors.is_empty():
		if effect_kind == "halo":
			_load_errors.append_array(_halo.configure(content.get("halo", {})))
		_replay_effect()
	_update_effect_ui()
	_update_visuals()


func _build_preview() -> void:
	_preview = Control.new()
	_preview.name = "EffectPreview"
	_preview.position = PREVIEW_RECT.position
	_preview.size = PREVIEW_RECT.size
	_preview.clip_contents = true
	_preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_preview)
	var black := ColorRect.new()
	black.color = Color.BLACK
	black.size = PREVIEW_RECT.size
	black.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_preview.add_child(black)
	if effect_kind == "intertitle":
		_title_text = Label.new()
		_title_text.position = Vector2(80, 36)
		_title_text.size = PREVIEW_RECT.size - Vector2(160, 72)
		_title_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		_title_text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		_title_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_title_text.add_theme_font_size_override("font_size", 31)
		_title_text.add_theme_color_override("font_color", INK)
		_title_text.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_preview.add_child(_title_text)
		return
	_background_view = TextureRect.new()
	_background_view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_background_view.stretch_mode = TextureRect.STRETCH_SCALE
	_background_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_preview.add_child(_background_view)
	var shade := ColorRect.new()
	shade.color = Color(0.08, 0.05, 0.13, 0.24)
	shade.size = PREVIEW_RECT.size
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_preview.add_child(shade)
	_halo = HALO.new()
	_halo.name = "ActorHalo"
	_preview.add_child(_halo)
	_actor = TextureRect.new()
	_actor.name = "CroppedGuest"
	_actor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_actor.stretch_mode = TextureRect.STRETCH_SCALE
	_actor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_preview.add_child(_actor)


func _load_cast_and_scenery() -> void:
	for background: Dictionary in content.get("backgrounds", []):
		_backgrounds.append(_load_texture(str(background["path"])))
	for guest: Dictionary in content.get("guests", []):
		var guest_id := str(guest["id"])
		_guest_textures[guest_id] = _load_texture(str(guest["path"]))
		if not str(guest.get("eye_close_path", "")).is_empty():
			_guest_close_textures[guest_id] = _load_texture(str(guest["eye_close_path"]))
		if not str(guest.get("detail_path", "")).is_empty():
			_guest_detail_textures[guest_id] = _load_texture(str(guest["detail_path"]))
	if _backgrounds.is_empty() or not _guest_textures.has(_guest_id):
		_load_errors.append("This study requires Afterlight's background and guest profiles.")
	if not _load_errors.is_empty():
		return
	_bind_study_background()
	_bind_guest()


func _bind_guest() -> void:
	if _actor == null:
		return
	_actor.texture = _guest_detail_textures.get(_guest_id, _guest_close_textures.get(_guest_id, _guest_textures.get(_guest_id)))
	if _actor.texture == null:
		return
	var profile := guest_profile()
	if _guest_detail_textures.has(_guest_id):
		var height := float(profile.get("detail_height", 1600.0))
		var width := height * _actor.texture.get_width() / _actor.texture.get_height()
		var y := float(profile.get("study_detail_y", profile.get("detail_y", -200.0)))
		_base_portrait = Rect2(PREVIEW_RECT.size.x * 0.5 - width * 0.5, y, width, height)
	else:
		var close_portrait := _guest_close_textures.has(_guest_id)
		var eye_uv: Array = profile.get("eye_close_uv", [0.5, 0.4]) if close_portrait else profile.get("eye_uv", [0.5, 0.12])
		var height := 1800.0 if close_portrait else 3000.0
		var width := height * _actor.texture.get_width() / _actor.texture.get_height()
		# Preserve the original alpha and full texture rectangle. The preview clips
		# the framing; no crop rectangle becomes a false glowing silhouette edge.
		_base_portrait = Rect2(PREVIEW_RECT.size.x * 0.5 - width * float(eye_uv[0]), -240.0 - height * float(eye_uv[1]), width, height)
	_halo.set_source(_actor.texture)
	_update_guest_picker()


func _bind_study_background() -> void:
	_background_view.texture = _backgrounds[_background_index]
	var source := _background_view.texture.get_size()
	var factor := maxf(PREVIEW_RECT.size.x / source.x, PREVIEW_RECT.size.y / source.y) * 1.16
	_base_background = Rect2((PREVIEW_RECT.size - source * factor) * 0.5, source * factor)
	if not DRIFT.can_cover(_base_background, PREVIEW_RECT.size):
		_load_errors.append("The study background must cover its preview before drift starts.")


func _select_guest(guest_id: String) -> void:
	if not _load_errors.is_empty() or not _guest_textures.has(guest_id):
		return
	_guest_id = guest_id
	_bind_guest()
	_replay_effect()


func _change_background() -> void:
	if not _load_errors.is_empty() or _backgrounds.is_empty():
		return
	_background_index = (_background_index + 1) % _backgrounds.size()
	_bind_study_background()
	_update_visuals()


func _replay_effect() -> void:
	if not _load_errors.is_empty():
		return
	match effect_kind:
		"intertitle":
			if _draft_text.text.strip_edges().is_empty():
				_feedback_key = "study.intertitle.enter_thought"
				_feedback.text = _text(_feedback_key)
				return
			var rate := float(_draft_text.text.length()) / _duration_slider.value
			var errors: Array[String] = _intertitle.start(_draft_text.text, {"chars_per_second": rate})
			if not errors.is_empty():
				_feedback_key = ""
				_feedback.text = " ".join(errors)
				return
			_active_text_is_default = _draft_is_default
			_feedback_key = "study.intertitle.advance_hint"
			_feedback.text = _text(_feedback_key)
		"drift":
			_load_errors.append_array(_drift.start(_drift_settings))
			_paused = false
		"halo":
			_halo.set_strength(1.0 if _halo_enabled else 0.0)
	_update_effect_ui()
	_update_visuals()


func _process(delta: float) -> void:
	if not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0:
		return
	if effect_kind == "intertitle":
		_intertitle.advance(delta)
	elif effect_kind == "drift" and not _paused:
		_drift.advance(delta)
	_update_effect_ui()
	_update_visuals()


func _update_visuals() -> void:
	if not _load_errors.is_empty():
		return
	if effect_kind == "intertitle":
		var pose: Dictionary = _intertitle.sample()
		_title_text.text = str(pose["text"]) if str(pose["phase"]) != "finished" else ""
		_title_text.visible_characters = int(pose["visible_characters"])
		return
	if _actor == null or _actor.texture == null:
		return
	_world_offset = Vector2.ZERO
	if effect_kind == "drift":
		var pose: Dictionary = _drift.sample()
		_world_offset = DRIFT.constrain_offset(_base_background, PREVIEW_RECT.size, Vector2(float(pose["offset_x"]), float(pose["offset_y"])))
	_background_view.position = _base_background.position + _world_offset
	_background_view.size = _base_background.size
	_actor.position = _base_portrait.position + _world_offset
	_actor.size = _base_portrait.size
	_halo.set_rect(Rect2(_actor.position, _actor.size))
	_halo.set_strength(1.0 if effect_kind == "halo" and _halo_enabled else 0.0)


func presented_background_rect() -> Rect2:
	return Rect2(_base_background.position + _world_offset, _base_background.size)


func _advance_intertitle() -> void:
	_intertitle.request_advance()
	_update_effect_ui()
	_update_visuals()


func _toggle_pause() -> void:
	_paused = not _paused
	_update_effect_ui()


func _clear_drift() -> void:
	_drift.clear()
	_paused = false
	_update_effect_ui()
	_update_visuals()


func _toggle_halo() -> void:
	_halo_enabled = not _halo_enabled
	_update_effect_ui()
	_update_visuals()


func _tune_effect(value: float, key: String) -> void:
	if effect_kind == "drift":
		_drift_settings[key] = value
	else:
		_load_errors.append_array(_halo.configure({key: value}))
	_effect_values[key].text = _effect_value_text(key, value)
	_update_visuals()


func _set_halo_color(color: Color) -> void:
	_load_errors.append_array(_halo.configure({"color": color}))
	_update_visuals()


func _effect_value_text(key: String, value: float) -> String:
	if key.begins_with("period"):
		return _text("unit.seconds", {"value": "%.1f" % value})
	if key == "intensity":
		return "%.2f" % value
	return _text("unit.pixels", {"value": "%.0f" % value})


func _draft_changed() -> void:
	if not _setting_default_draft:
		_draft_is_default = false
	if _draft_text.text.length() > 512:
		_draft_text.text = _draft_text.text.left(512)
	_update_duration_bounds()


func _update_duration_bounds() -> void:
	var count := float(maxi(1, _draft_text.text.length()))
	_duration_slider.min_value = maxf(0.5, count / INTERTITLE.MAX_CHARS_PER_SECOND)
	_duration_slider.max_value = minf(20.0, count / INTERTITLE.MIN_CHARS_PER_SECOND)
	_duration_value.text = _text("unit.seconds", {"value": "%.1f" % _duration_slider.value})


func _duration_changed(value: float) -> void:
	_duration_value.text = _text("unit.seconds", {"value": "%.1f" % value})


func _refresh_language() -> void:
	_update_language_picker()
	_update_guest_picker()
	if _study_heading != null:
		_study_heading.text = _text("study.effects.study_title", {"game": _text("game.title"), "effect": _text("study.%s.title" % effect_kind)})
	if effect_kind == "intertitle" and _draft_text != null:
		if _draft_is_default:
			_setting_default_draft = true
			_draft_text.text = _text("study.intertitle.sample")
			_update_duration_bounds()
			_setting_default_draft = false
		if _active_text_is_default:
			_translate_default_intertitle()
		_duration_changed(_duration_slider.value)
	for key: String in _effect_values:
		_effect_values[key].text = _effect_value_text(key, float(_effect_sliders[key].value))
	if not _feedback_key.is_empty():
		_feedback.text = _text(_feedback_key)
	_update_effect_ui()
	_update_visuals()


func _translate_default_intertitle() -> void:
	var state: Dictionary = _intertitle.get_state()
	if str(state["phase"]) == "idle":
		return
	var old_count := float(str(state["text"]).length())
	var duration := old_count / float(state["chars_per_second"])
	var fraction := float(state["elapsed"]) / duration
	var translated := _text("study.intertitle.sample")
	# The sample changes language, but keeps its selected duration and reveal
	# position. A user-authored draft or active custom cue is never replaced.
	state["text"] = translated
	state["chars_per_second"] = clampf(float(translated.length()) / duration, INTERTITLE.MIN_CHARS_PER_SECOND, INTERTITLE.MAX_CHARS_PER_SECOND)
	var new_duration := float(translated.length()) / float(state["chars_per_second"])
	state["elapsed"] = fraction * new_duration
	if str(state["phase"]) == "revealing":
		state["elapsed"] = minf(float(state["elapsed"]), (float(translated.length()) - 0.000001) / float(state["chars_per_second"]))
	_load_errors.append_array(_intertitle.restore(state))


func _update_effect_ui() -> void:
	if _status == null:
		return
	if not _load_errors.is_empty():
		_status.text = _text("error.study_load")
		_feedback.text = " ".join(_load_errors)
		return
	match effect_kind:
		"intertitle":
			var phase := str(_intertitle.sample()["phase"])
			_status.text = _text("study.effects.status", {"effect": _text("study.intertitle.title"), "phase": _text("phase." + phase)})
			_action_button.text = _text("ui.reveal_text" if phase == "revealing" else "ui.continue")
			_action_button.disabled = phase not in ["revealing", "holding"]
		"drift":
			var phase := "paused" if _paused else "playing" if _drift.is_active() else "cleared"
			_status.text = _text("study.effects.status", {"effect": _text("study.drift.title"), "phase": _text("phase." + phase)})
			_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
			_pause_button.disabled = not _drift.is_active()
		"halo":
			_status.text = _text("study.effects.status", {"effect": _text("study.halo.title"), "phase": _text("phase.on" if _halo_enabled else "phase.off")})
			_halo_toggle.text = _text("ui.halo_off" if _halo_enabled else "ui.halo_on")


func _build_effect_ui() -> void:
	_ui = Control.new()
	_ui.name = "AfterlightEffectStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(32, 24, 1216, 96), Color("211b28"))
	_label_text("game.kicker", Rect2(56, 36, 600, 18), 12, ACCENT)
	_study_heading = _label(_text("study.effects.study_title", {"game": _text("game.title"), "effect": _text("study.%s.title" % effect_kind)}), Rect2(54, 55, 650, 49), 31, INK)
	_build_language_picker(Rect2(758, 52, 248, 40))
	_return_button = _button_text("ui.effects_menu", Rect2(1030, 49, 190, 44), func() -> void: navigate.emit("effects_menu"))
	_panel(Rect2(32, 636, 1216, 240), Color("211b28"))
	_status = _label("", Rect2(56, 650, 780, 29), 22, INK)
	_feedback = _label("", Rect2(56, 846, 1160, 22), 14, MUTED)
	if effect_kind == "intertitle":
		_build_intertitle_controls()
	else:
		_build_portrait_controls()


func _build_intertitle_controls() -> void:
	_label_text("study.intertitle.monologue_text", Rect2(56, 689, 280, 23), 15, MUTED)
	_draft_text = TextEdit.new()
	_draft_text.position = Vector2(56, 718)
	_draft_text.size = Vector2(770, 66)
	_draft_text.text = _text("study.intertitle.sample")
	_draft_text.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_draft_text.add_theme_font_size_override("font_size", 16)
	_draft_text.text_changed.connect(_draft_changed)
	_ui.add_child(_draft_text)
	_label_text("study.intertitle.reveal_duration", Rect2(858, 689, 240, 23), 15, MUTED)
	_duration_value = _label("", Rect2(1120, 689, 96, 23), 15, ACCENT)
	_duration_slider = HSlider.new()
	_duration_slider.position = Vector2(858, 731)
	_duration_slider.size = Vector2(354, 25)
	_duration_slider.min_value = 0.5
	_duration_slider.max_value = 20.0
	_duration_slider.step = 0.1
	_duration_slider.value = float(_draft_text.text.length()) / float(content.get("intertitle", {}).get("chars_per_second", 32.0))
	_duration_slider.value_changed.connect(_duration_changed)
	_ui.add_child(_duration_slider)
	_update_duration_bounds()
	_replay_button = _button_text("ui.replay", Rect2(56, 799, 160, 40), _replay_effect)
	_action_button = _button("", Rect2(230, 799, 200, 40), _advance_intertitle)
	_label_text("study.intertitle.timing_hint", Rect2(858, 797, 354, 39), 14, MUTED)


func _build_portrait_controls() -> void:
	var guests: Array = content.get("guests", [])
	for index in guests.size():
		var guest: Dictionary = guests[index]
		var guest_id := str(guest["id"])
		var button := _button(str(guest["name"]), Rect2(720 + index * 124, 646, 116, 38), _select_guest.bind(guest_id))
		button.toggle_mode = true
		_guest_buttons[guest_id] = button
	var controls: Array = [
		["amplitude_x", "study.drift.amplitude_x", 0.0, 64.0, 1.0],
		["amplitude_y", "study.drift.amplitude_y", 0.0, 64.0, 1.0],
		["period_x", "study.drift.period_x", 0.5, 20.0, 0.5],
		["period_y", "study.drift.period_y", 0.5, 20.0, 0.5],
	] if effect_kind == "drift" else [
		["radius", "study.halo.radius", 0.0, 128.0, 1.0],
		["intensity", "study.halo.intensity", 0.0, 4.0, 0.05],
	]
	var configured: Dictionary = _drift_settings if effect_kind == "drift" else HALO.DEFAULTS.merged(content.get("halo", {}), true)
	for index in controls.size():
		var spec: Array = controls[index]
		var x := 56.0 + index * 292.0
		var key := str(spec[0])
		var value := float(configured[key])
		_label_text(str(spec[1]), Rect2(x, 707, 180, 25), 15, INK)
		_effect_values[key] = _label(_effect_value_text(key, value), Rect2(x + 178, 707, 92, 25), 15, ACCENT)
		var slider := HSlider.new()
		slider.position = Vector2(x, 752)
		slider.size = Vector2(258, 25)
		slider.min_value = float(spec[2])
		slider.max_value = float(spec[3])
		slider.step = float(spec[4])
		slider.value = value
		slider.value_changed.connect(_tune_effect.bind(key))
		_ui.add_child(slider)
		_effect_sliders[key] = slider
	if effect_kind == "drift":
		_replay_button = _button_text("ui.replay", Rect2(56, 799, 152, 40), _replay_effect)
		_pause_button = _button("", Rect2(222, 799, 152, 40), _toggle_pause)
		_button_text("ui.clear", Rect2(388, 799, 152, 40), _clear_drift)
		_feedback_key = "study.drift.timing_hint"
		_feedback.text = _text(_feedback_key)
	else:
		_label_text("study.halo.color", Rect2(640, 707, 220, 25), 15, INK)
		_halo_color = ColorPickerButton.new()
		_halo_color.position = Vector2(640, 745)
		_halo_color.size = Vector2(234, 39)
		_halo_color.color = configured["color"]
		_halo_color.edit_alpha = true
		_halo_color.color_changed.connect(_set_halo_color)
		_ui.add_child(_halo_color)
		_halo_toggle = _button("", Rect2(56, 799, 220, 40), _toggle_halo)
		_feedback_key = "study.halo.timing_hint"
		_feedback.text = _text(_feedback_key)
	_button_text("ui.change_backdrop", Rect2(1000, 799, 212, 40), _change_background)


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode == KEY_F6:
		super._input(event)
		return
	if event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
		get_viewport().set_input_as_handled()
	elif effect_kind == "intertitle" and event.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		var focused := get_viewport().gui_get_focus_owner()
		if focused != null and focused != _action_button:
			return
		_advance_intertitle()
		get_viewport().set_input_as_handled()
