extends "res://games/presentation_lab/afterlight/study_host.gd"

## One lab host owns the controls and a single cast/manpu clock. A 2D stage and
## a real Sprite3D preview consume the same samples without restarting events.
const ACTOR_CAST = preload("res://games/bishoujo_afterlight/cast_stage.gd")
const BILLBOARD = preload("res://games/presentation_lab/afterlight/billboard_puff_preview.gd")
const MODES: Array[String] = ["static", "shake", "one_shot", "step_loop", "two_frame_loop", "three_frame_loop"]
const ONE_SHOT_VARIANTS: Array[String] = ["sigh_puff", "sweat_drop"]
const PUFF_PATH := "res://assets/manpu/sigh_puff.png"
var _cast_layer: Control
var _billboard: Control
var _puff_texture: Texture2D
var _fixture_textures: Dictionary = {}
var _selected_mode := "one_shot"
var _one_shot_id := "sigh_puff"
var _presentation := "2d"
var _mode_buttons: Dictionary = {}
var _presentation_buttons: Dictionary = {}
var _variant_buttons: Dictionary = {}
var _trigger_button: Button
var _pause_button: Button
var _reset_button: Button
var _remove_button: Button
var _angle_button: Button
var _hint: Label
var _instance_label: Label
var _paused := false
var _persistent := false
var _elapsed := 0.0
var _camera_angle := 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_guest_id = str(content.get("default_guest_id", ""))
	for profile: Dictionary in content.get("guests", []):
		_guest_textures[str(profile["id"])] = _load_texture(str(profile["path"]))
	for background: Dictionary in content.get("backgrounds", []):
		_backgrounds.append(_load_texture(str(background["path"])))
	_puff_texture = _load_texture(PUFF_PATH)
	_fixture_textures["sigh_puff"] = _puff_texture
	for mark_id: String in ["sparkle", "heart", "sweat_drop"]:
		_fixture_textures[mark_id] = _load_texture("res://assets/manpu/" + mark_id + ".png")
	_cast_layer = ACTOR_CAST.new()
	_cast_layer.name = "PuffCast"
	add_child(_cast_layer)
	_load_errors.append_array(_cast_layer.initialize(content.get("guests", []), _guest_textures, content.get("manpu_textures", {})))
	_billboard = BILLBOARD.new()
	_billboard.name = "BillboardPuffPreview"
	add_child(_billboard)
	_build_puff_ui()
	_reset_puffs()
	_set_presentation("2d")


func _controller() -> RefCounted:
	return _cast_layer.get("_manpu")


func _select_guest(actor_id: String) -> void:
	if not _guest_textures.has(actor_id): return
	_guest_id = actor_id
	_reset_puffs()


func _select_mode(mode: String) -> void:
	if mode not in MODES: return
	_selected_mode = mode
	_reset_puffs()


func _select_one_shot_variant(mark_id: String) -> void:
	if mark_id not in ONE_SHOT_VARIANTS: return
	if mark_id == _one_shot_id:
		_update_puff_ui()
		return
	_one_shot_id = mark_id
	_reset_puffs()


func _reset_puffs() -> void:
	_paused = false
	_persistent = false
	_elapsed = 0.0
	if _load_errors.is_empty():
		_load_errors.append_array(_cast_layer.set_cast([_guest_id]))
		_cast_layer.cancel_manpu()
		var rect: Rect2 = _cast_layer.get_actor_rect(_guest_id)
		var eye: Array = guest_profile().get("eye_uv", [0.5, 0.14])
		var mark_id := _one_shot_id if _selected_mode == "one_shot" else "sigh_puff"
		var anchor_y := maxf(0.035, float(eye[1]) - 0.05) if mark_id == "sweat_drop" else float(eye[1]) + 0.055
		var anchor := Vector2(clampf(float(eye[0]) + 0.23, 0.1, 0.85), anchor_y)
		_billboard.bind_actor(_guest_textures[_guest_id], rect, anchor, _fixture_textures[mark_id], rect.size.y * ACTOR_CAST.MARK_HEIGHT_RATIO)
	_present_puffs()
	_update_puff_ui()
	queue_redraw()


func _trigger_puff() -> void:
	if not _load_errors.is_empty(): return
	if _selected_mode == "one_shot":
		var preset_id := "sweat_drop_fall" if _one_shot_id == "sweat_drop" else "sigh_puff"
		var result: Dictionary = _cast_layer.emit_manpu(_guest_id, _one_shot_id, preset_id)
		_load_errors.append_array(result["errors"])
	else:
		_load_errors.append_array(_cast_layer.set_marks([_persistent_cue()]))
		_load_errors.append_array(_controller().replay(_guest_id, "sigh_puff"))
		_persistent = _load_errors.is_empty()
	_present_puffs()
	_update_puff_ui()


func _persistent_cue() -> Dictionary:
	var cue := {"actor": _guest_id, "id": "sigh_puff"}
	match _selected_mode:
		"static": cue["preset"] = "none"
		"shake": cue["preset"] = "shake"
		"step_loop": cue["preset"] = "step_loop"
		"two_frame_loop":
			cue["preset"] = "frame_loop"
			cue["frames"] = ["sigh_puff", "sparkle"]
		"three_frame_loop":
			cue["preset"] = "frame_loop"
			cue["frames"] = ["sigh_puff", "sparkle", "heart"]
	return cue


func _replay_puffs() -> void:
	if not _load_errors.is_empty(): return
	_elapsed = 0.0
	if _selected_mode == "one_shot":
		_cast_layer.cancel_manpu()
		_trigger_puff()
	elif _persistent:
		_load_errors.append_array(_controller().replay(_guest_id, "sigh_puff"))
		_present_puffs()
		_update_puff_ui()
	else:
		_trigger_puff()


func _remove_puffs() -> void:
	if not _load_errors.is_empty(): return
	_load_errors.append_array(_cast_layer.set_marks([]))
	_cast_layer.cancel_manpu()
	_persistent = false
	_present_puffs()
	_update_puff_ui()


func _toggle_pause() -> void:
	_paused = not _paused
	_update_puff_ui()


func _set_presentation(value: String) -> void:
	if value not in ["2d", "3d"]: return
	_presentation = value
	_cast_layer.visible = value == "2d"
	_billboard.set_preview_visible(value == "3d")
	_present_puffs()
	_update_puff_ui()


func _toggle_angle() -> void:
	_camera_angle = 25.0 if is_zero_approx(_camera_angle) else 0.0
	_billboard.set_angle(_camera_angle)
	_update_puff_ui()


func _process(delta: float) -> void:
	_billboard.sync_resolution()
	if not _load_errors.is_empty() or _paused or not is_finite(delta) or delta <= 0.0: return
	_elapsed += delta
	_cast_layer.advance(delta)
	_present_puffs()
	_update_puff_ui()


func _present_puffs() -> void:
	if not _load_errors.is_empty(): return
	_cast_layer.present(Transform2D.IDENTITY)
	var samples: Array = []
	if _persistent:
		var sample: Dictionary = _controller().sample(_guest_id, "sigh_puff")
		samples.append({"key": "persistent", "sample": sample, "texture": _sample_texture(sample)})
	for event: Dictionary in _controller().one_shots():
		samples.append({"key": "shot_" + str(event["instance_id"]), "sample": event["sample"], "texture": _sample_texture(event["sample"], str(event["id"]))})
	_billboard.present(samples)


func _sample_texture(sample: Dictionary, fallback_id: String = "sigh_puff") -> Texture2D:
	return _fixture_textures.get(str(sample.get("sprite_id", fallback_id)), _puff_texture)


func puff_state() -> Dictionary:
	var ids: Array[int] = []
	for event: Dictionary in _controller().one_shots():
		ids.append(int(event["instance_id"]))
	return {"actor_id": _guest_id, "mode": _selected_mode, "presentation": _presentation,
		"one_shot_id": _one_shot_id,
		"paused": _paused, "elapsed": _elapsed, "persistent": _persistent, "instance_ids": ids,
		"camera_angle": _camera_angle,
		"persistent_sample": _controller().sample(_guest_id, "sigh_puff") if _persistent else {}}


func _build_puff_ui() -> void:
	_ui = Control.new()
	_ui.name = "SighPuffStudyInterface"
	_ui.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_ui)
	_ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_panel(Rect2(32, 24, 1216, 96), Color("211b28"))
	_label_text("game.kicker", Rect2(56, 36, 600, 18), 12, ACCENT)
	_label_text("study.puff.title", Rect2(54, 55, 650, 49), 31, INK)
	_build_language_picker(Rect2(758, 52, 248, 40))
	_return_button = _button_text("ui.effects_menu", Rect2(1030, 49, 190, 44), func() -> void: navigate.emit("effects_menu"))
	var guests: Array = content.get("guests", [])
	for index in guests.size():
		var actor_id := str(guests[index]["id"])
		var button := _button(str(guests[index]["name"]), Rect2(56 + index * 294, 138, 282, 40), _select_guest.bind(actor_id))
		button.toggle_mode = true
		_guest_buttons[actor_id] = button
	for index in ONE_SHOT_VARIANTS.size():
		var mark_id := ONE_SHOT_VARIANTS[index]
		var button := _button_text("study.puff." + mark_id, Rect2(56 + index * 262, 192, 248, 40), _select_one_shot_variant.bind(mark_id))
		button.name = "OneShot" + mark_id.to_pascal_case()
		button.toggle_mode = true
		_variant_buttons[mark_id] = button
	_angle_button = _button_text("study.puff.angle", Rect2(588, 192, 208, 40), _toggle_angle)
	for index in 2:
		var value := "2d" if index == 0 else "3d"
		var button := _button_text("study.puff." + value, Rect2(810 + index * 210, 192, 198, 40), _set_presentation.bind(value))
		button.toggle_mode = true
		_presentation_buttons[value] = button
	_panel(Rect2(32, 590, 1216, 286), Color("211b28"))
	_status = _label("", Rect2(56, 604, 766, 31), 20, INK)
	_instance_label = _label("", Rect2(850, 607, 374, 31), 15, MUTED)
	for index in MODES.size():
		var mode := MODES[index]
		var button := _button_text("study.puff." + mode, Rect2(56 + (index % 3) * 394, 650 + floorf(float(index) / 3.0) * 51, 382, 40), _select_mode.bind(mode))
		button.toggle_mode = true
		_mode_buttons[mode] = button
	_trigger_button = _button_text("study.puff.trigger", Rect2(56, 773, 232, 42), _trigger_puff)
	_replay_button = _button_text("ui.replay", Rect2(304, 773, 208, 42), _replay_puffs)
	_replay_button.name = "ReplayManpu"
	_pause_button = _button_text("ui.pause", Rect2(528, 773, 208, 42), _toggle_pause)
	_remove_button = _button_text("study.puff.remove", Rect2(752, 773, 248, 42), _remove_puffs)
	_remove_button.name = "RemoveManpu"
	_reset_button = _button_text("ui.reset", Rect2(1016, 773, 208, 42), _reset_puffs)
	_hint = _label("", Rect2(56, 836, 1168, 31), 16, MUTED)


func _update_puff_ui() -> void:
	if _status == null: return
	_update_guest_picker()
	for mode: String in _mode_buttons:
		_mode_buttons[mode].set_pressed_no_signal(mode == _selected_mode)
	for value: String in _presentation_buttons:
		_presentation_buttons[value].set_pressed_no_signal(value == _presentation)
	for mark_id: String in _variant_buttons:
		_variant_buttons[mark_id].visible = _selected_mode == "one_shot"
		_variant_buttons[mark_id].set_pressed_no_signal(mark_id == _one_shot_id)
	var state := puff_state()
	var handles: Array = state["instance_ids"]
	_status.text = _text("study.puff.status", {"mode": _text("study.puff." + _selected_mode),
		"count": handles.size() + int(_persistent), "elapsed": "%.2f" % _elapsed})
	_instance_label.text = _text("study.puff.instances", {"ids": str(handles)}) if not handles.is_empty() else _text("study.puff.no_instances")
	_hint.text = _text("study.puff.hint.sweat_drop" if _selected_mode == "one_shot" and _one_shot_id == "sweat_drop" else "study.puff.hint." + _selected_mode)
	_pause_button.text = _text("ui.resume" if _paused else "ui.pause")
	_angle_button.visible = _presentation == "3d"
	_angle_button.text = _text("study.puff.angle_value", {"angle": int(_camera_angle)})
	if not _load_errors.is_empty():
		_status.text = "\n".join(_load_errors)
		_trigger_button.disabled = true
		_pause_button.disabled = true
		_replay_button.disabled = true
		_remove_button.disabled = true


func _refresh_language() -> void:
	_update_puff_ui()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, DESIGN_SIZE), Color("15121d"))
	if _backgrounds.is_empty() or _backgrounds[0] == null: return
	var texture := _backgrounds[0]
	var factor := maxf(DESIGN_SIZE.x / texture.get_width(), DESIGN_SIZE.y / texture.get_height())
	var extent := texture.get_size() * factor
	draw_texture_rect(texture, Rect2((DESIGN_SIZE - extent) * 0.5, extent), false)


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo: return
	if event.keycode == KEY_F6:
		_toggle_language()
	elif event.keycode == KEY_ESCAPE:
		navigate.emit("effects_menu")
	else:
		return
	get_viewport().set_input_as_handled()
