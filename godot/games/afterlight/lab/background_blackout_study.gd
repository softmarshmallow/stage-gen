extends "res://lab/study_host.gd"

## The host isolates scenery by placing the blackout before its unchanged actor.
## The transition knows only its opacity, destination, and explicit time.
const BLACKOUT = preload("res://addons/game_presentation/transitions/background_blackout.gd")
var _blackout: ColorRect
var _paused := false
var _duration := 0.45
var _duration_slider: HSlider
var _duration_label: Label
var _blackout_button: Button
var _restore_button: Button
var _pause_button: Button


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_duration = float(content.get("background_blackout", {}).get("fade_seconds", 0.45))
	for profile: Dictionary in content.get("guests", []):
		if profile["id"] == "nami":
			_guest_textures["nami"] = _load_texture(profile["path"])
	var backgrounds: Array = content.get("backgrounds", [])
	if not backgrounds.is_empty():
		_backgrounds.append(_load_texture(str(backgrounds[0]["path"])))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		var extent := _backgrounds[0].get_size()
		extent *= maxf(DESIGN_SIZE.x / extent.x, DESIGN_SIZE.y / extent.y)
		_base_background = Rect2((DESIGN_SIZE - extent) * 0.5, extent)
	_blackout = BLACKOUT.new()
	_blackout.name = "BackgroundBlackout"
	add_child(_blackout)
	_actor = TextureRect.new()
	_actor.name = "UnchangedNamiSprite"
	_actor.texture = _guest_textures.get("nami")
	_actor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_actor.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_actor)
	if _actor.texture != null:
		var height := 840.0
		var width := height * _actor.texture.get_width() / _actor.texture.get_height()
		_actor.position = Vector2(640.0 - width * 0.5, 130.0)
		_actor.size = Vector2(width, height)
	_build_blackout_ui()
	_update_blackout_ui()


func _fade_to(strength: float) -> void:
	if not _load_errors.is_empty(): return
	_load_errors.append_array(_blackout.fade_to(strength, _duration))
	_update_blackout_ui()


func _set_duration(value: float) -> void:
	_duration = value
	_update_blackout_ui()


func _toggle_pause() -> void:
	_paused = not _paused
	_update_blackout_ui()


func _reset_blackout() -> void:
	_blackout.clear()
	_paused = false
	_update_blackout_ui()


func _process(delta: float) -> void:
	if _paused or not _load_errors.is_empty() or not is_finite(delta) or delta <= 0.0: return
	_load_errors.append_array(_blackout.advance(delta))
	_update_blackout_ui()


func blackout_state() -> Dictionary:
	return {"paused": _paused, "duration": _duration, "blackout": _blackout.get_state()}


func _build_blackout_ui() -> void:
	_ui = Control.new()
	_ui.name = "BackgroundBlackoutStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(24, 22, 1232, 103), Color("211b28"))
	_label_text("study.blackout.title", Rect2(46, 31, 690, 47), 32, INK)
	_label_text("study.blackout.description", Rect2(48, 82, 948, 30), 17, MUTED)
	_build_language_picker(Rect2(787, 38, 206, 38))
	_return_button = _button_text("ui.effects_menu", Rect2(1021, 48, 211, 44), func() -> void: navigate.emit("effects_menu"))
	_panel(Rect2(24, 699, 1232, 181), Color("211b28"))
	_duration_label = _label("", Rect2(46, 715, 320, 34), 20, INK)
	_duration_slider = HSlider.new()
	_duration_slider.name = "DurationSlider"
	_duration_slider.position = Vector2(375, 718)
	_duration_slider.size = Vector2(600, 30)
	_duration_slider.min_value = 0.0
	_duration_slider.max_value = 1.5
	_duration_slider.step = 0.05
	_duration_slider.value = _duration
	_duration_slider.value_changed.connect(_set_duration)
	_ui.add_child(_duration_slider)
	_status = _label("", Rect2(996, 716, 236, 34), 18, MUTED)
	_status.name = "BlackoutStatus"
	_label_text("study.blackout.hint", Rect2(46, 766, 1170, 31), 16, MUTED)
	_blackout_button = _button_text("study.blackout.blackout", Rect2(46, 813, 240, 42), _fade_to.bind(1.0))
	_blackout_button.name = "FadeBackgroundToBlack"
	_restore_button = _button_text("study.blackout.restore", Rect2(302, 813, 320, 42), _fade_to.bind(0.0))
	_restore_button.name = "RestoreBackground"
	_pause_button = _button_text("ui.pause", Rect2(638, 813, 240, 42), _toggle_pause)
	_pause_button.name = "PauseBlackout"
	_button_text("ui.reset", Rect2(894, 813, 338, 42), _reset_blackout).name = "ResetBlackout"


func _update_blackout_ui() -> void:
	if _status == null: return
	_duration_label.text = _text("study.blackout.duration", {"value": "%.2f" % _duration})
	_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
	_status.text = _text("study.blackout.status", {"value": int(roundf(float(_blackout.get_state()["strength"]) * 100.0))})
	if not _load_errors.is_empty():
		_status.text = "\n".join(_load_errors)
		_blackout_button.disabled = true
		_restore_button.disabled = true
		_pause_button.disabled = true


func _refresh_language() -> void:
	_update_blackout_ui()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if not _backgrounds.is_empty() and _backgrounds[0] != null:
		draw_texture_rect(_backgrounds[0], _base_background, false)


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		_toggle_language()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
	else:
		return
	get_viewport().set_input_as_handled()
