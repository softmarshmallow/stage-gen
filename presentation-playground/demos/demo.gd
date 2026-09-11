extends "res://presentation/stage.gd"

## Each scene selects one demonstration. These are spike routes, not modules.
@export var demo_id := "characters"

const DEMOS := {
	"characters": {"title": "Characters", "description": "Standing artwork and matched eye states."},
	"contact": {"title": "Fingertip contact", "description": "A small moment of direct interaction."},
	"dialogue": {"title": "Dialogue", "description": "Three actors taking turns in a conversation."},
	"actor_focus": {"title": "Actor Focus", "description": "One speaker-change cue, interchangeable animation presets."},
	"character_exit": {"title": "Character Exit", "description": "Choose a silhouette fade, opacity fade, or walking departure."},
	"manpu": {"title": "Manpu / emanata", "description": "Visual punctuation attached to the current exchange."},
	"locations": {"title": "Locations", "description": "A place, a change of scenery, and its location title."},
	"hologram": {"title": "Hologram", "description": "A character visual effect, applied independently to each actor."},
}

var _demos_button: Button
var _play_button: Button
var _target_button: Button
var _gallery_button: Button
var _replay_title_button: Button
var _focus_preset_button: Button
var _focus_replay_button: Button
var _manpu_preset_button: Button
var _manpu_target_button: Button
var _manpu_replay_button: Button
var _manpu_target_index := -1
var _exit_target := "sera"
var _exit_preset_button: Button
var _exit_target_button: Button
var _exit_actor_button: Button
var _show_actor_button: Button
var _demo_controls: Array[Control] = []


func _build_interface() -> void:
	var spec: Dictionary = DEMOS.get(demo_id, DEMOS["characters"])
	_title = _label(String(spec["title"]), 27, PAPER)
	_subtitle = _label("", 13, MUTED)
	_location_title = _label("", 27, PAPER)
	_location_detail = _label("", 13, WARM)
	_line = _label("", 25, PAPER, HORIZONTAL_ALIGNMENT_CENTER)
	_speaker = _label("", 15, WARM, HORIZONTAL_ALIGNMENT_CENTER)
	_hint = _label("", 14, MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	_footer = _label(String(spec["description"]), 12, MUTED, HORIZONTAL_ALIGNMENT_CENTER)
	_demos_button = _button("Demos", func() -> void: navigate.emit("command_link"))
	_play_button = _button("Play", func() -> void: navigate.emit("game:command_link/game"))
	_demos_button.tooltip_text = "Return to the demonstrations. Keyboard: Esc"
	match demo_id:
		"characters":
			_blink_button = _button("Close eyes", _toggle_eyes)
			_auto_button = _button("Auto blink · on", _toggle_natural_blink)
			_demo_controls.assign([_blink_button, _auto_button])
		"contact":
			_target_button = _button("Show target", _toggle_target)
			_demo_controls.append(_target_button)
		"dialogue":
			_next_button = _button("Next →", _advance_dialogue)
			_demo_controls.append(_next_button)
		"actor_focus":
			_focus_preset_button = _button("", _cycle_focus_preset)
			_focus_replay_button = _button("Replay focus · F", _replay_focus)
			_next_button = _button("Next →", _advance_dialogue)
			_demo_controls.assign([_focus_preset_button, _focus_replay_button, _next_button])
		"character_exit":
			_exit_target_button = _button("", _cycle_exit_target)
			_exit_preset_button = _button("", _cycle_exit_preset)
			_exit_actor_button = _button("Exit · E", _exit_selected_actor)
			_show_actor_button = _button("Show · S", _show_selected_actor)
			_demo_controls.assign([_exit_target_button, _exit_preset_button, _exit_actor_button, _show_actor_button])
		"manpu":
			_manpu_preset_button = _button("", _cycle_manpu_preset)
			_manpu_target_button = _button("", _cycle_manpu_target)
			_manpu_replay_button = _button("Replay mark · F", _replay_selected_manpu)
			_next_button = _button("Next →", _advance_dialogue)
			_gallery_button = _button("Open gallery", _toggle_gallery)
			_demo_controls.assign([_manpu_preset_button, _manpu_target_button,
				_manpu_replay_button, _next_button, _gallery_button])
		"locations":
			_scene_button = _button("Change scene", _change_scene)
			_replay_title_button = _button("Replay title", _replay_title)
			_demo_controls.assign([_scene_button, _replay_title_button])
		"hologram":
			_effect_target_button = _button("", _cycle_effect_target)
			_effect_toggle_button = _button("", _toggle_character_effect)
			_effect_strength_slider = HSlider.new()
			_effect_strength_slider.min_value = 0.0
			_effect_strength_slider.max_value = 100.0
			_effect_strength_slider.step = 5.0
			_effect_strength_slider.value_changed.connect(_set_effect_strength)
			add_child(_effect_strength_slider)
			_effect_strength_label = _label("80%", 13, MUTED)
			_next_button = _button("Next →", _advance_dialogue)
			_demo_controls.assign([_effect_target_button, _effect_toggle_button, _effect_strength_slider,
				_effect_strength_label, _next_button])
	_restart_button = _button("Reset", _restart)
	_demo_controls.append(_restart_button)
	var primary: Button = {"characters": _blink_button, "dialogue": _next_button,
		"actor_focus": _focus_replay_button, "character_exit": _exit_actor_button,
		"manpu": _manpu_replay_button, "locations": _scene_button,
		"hologram": _next_button}.get(demo_id)
	if primary != null:
		TACTICAL_THEME.style_primary(primary)


func _configure_route() -> void:
	_actor_focus.clear()
	_manpu_animation.clear()
	_character_exit.clear()
	_exit_target = "sera"
	if demo_id == "character_exit":
		set_character_exit_preset("silhouette_fade")
	_manpu_target_index = -1
	if demo_id == "manpu":
		_manpu_animation.configure("shake")
		manpu_animation_preset = "shake"
	if demo_id == "actor_focus":
		_actor_focus.configure("bounce")
		actor_focus_preset = "bounce"
	_mode = {"characters": "full_body", "contact": "reach_out", "locations": "background"}.get(demo_id, "dialogue")
	_dialogue_index = 10 if demo_id == "hologram" else 0
	_manual_closed = false
	_natural_blink = demo_id == "characters"
	_blink_remaining = 0.0
	_blink_wait = 3.8
	_blink_cycle = 0
	_entry = 0.0
	_reaction = 0.0
	_connected = false
	_show_hotspot = false
	_pointer = Vector2(-1000, -1000)
	_reset_character_effects()


func _reset_character_effects() -> void:
	_effect_target = "sera"
	for actor: Dictionary in stage_profile.actors:
		var id := String(actor["id"])
		_character_effects[id] = {"enabled": demo_id == "hologram" and id == "sera", "strength": 0.8}


func _restart() -> void:
	_configure_route()
	_select_location(_random_location_id(), true)
	_update_interface()


func _layout_interface() -> void:
	if _title == null:
		return
	_title.position = Vector2(32, 22)
	_title.size = Vector2(920, 40)
	_subtitle.position = Vector2(33, 62)
	_subtitle.size = Vector2(920, 24)
	_location_title.position = _title.position
	_location_title.size = _title.size
	_location_detail.position = _subtitle.position
	_location_detail.size = _subtitle.size
	_demos_button.position = Vector2(1012, 32)
	_demos_button.size = Vector2(112, 36)
	_play_button.position = Vector2(1136, 32)
	_play_button.size = Vector2(112, 36)
	_speaker.position = Vector2(32, 677)
	_speaker.size = Vector2(1216, 25)
	_line.position = Vector2(32, 704)
	_line.size = Vector2(1216, 56)
	_hint.position = Vector2(32, 765)
	_hint.size = Vector2(1216, 26)
	_footer.position = Vector2(32, 859)
	_footer.size = Vector2(1216, 25)
	var total := maxf(0.0, _demo_controls.size() - 1) * 14.0
	for control: Control in _demo_controls:
		total += _control_width(control)
	var left := (DESIGN_SIZE.x - total) * 0.5
	for control: Control in _demo_controls:
		var width := _control_width(control)
		control.position = Vector2(left, 812)
		control.size = Vector2(width, 38)
		if control == _effect_strength_slider:
			control.position.y = 820
			control.size.y = 22
		left += width + 14.0
	_update_character_layers()
	queue_redraw()


func _control_width(control: Control) -> float:
	if control == _focus_preset_button or control == _manpu_preset_button or control == _exit_preset_button:
		return 246.0
	if control == _focus_replay_button or control == _manpu_replay_button:
		return 164.0
	if control == _restart_button:
		return 104.0
	if control == _effect_strength_slider:
		return 180.0
	if control == _effect_strength_label:
		return 56.0
	if control == _auto_button or control == _gallery_button:
		return 168.0
	return 144.0


func _update_interface() -> void:
	if _line == null:
		return
	_speaker.visible = _mode == "dialogue"
	_speaker.text = String(_current_beat().get("speaker", ""))
	if _next_button != null:
		_next_button.text = "Read again" if _dialogue_index == stage_profile.dialogue.size() - 1 else "Next →"
		_next_button.disabled = _mode != "dialogue"
	match demo_id:
		"characters":
			_line.text = "Standing by, Commander."
			_hint.text = "B · open / close eyes     N · automatic blink"
			_blink_button.text = "Open eyes" if _manual_closed else "Close eyes"
			_auto_button.text = "Auto blink · on" if _natural_blink else "Auto blink · off"
		"contact":
			_line.text = "Command link confirmed. I hear you clearly." if _connected else "One touch, Commander. Then we're connected."
			_hint.text = "Squad channel connected." if _connected else "Touch my fingertip."
			_target_button.text = "Hide target · H" if _show_hotspot else "Show target · H"
		"dialogue":
			_line.text = String(_current_beat().get("line", ""))
			_hint.text = "Space / Enter · next line"
		"actor_focus":
			_line.text = String(_current_beat().get("line", ""))
			_hint.text = "P · change preset     F · replay focus     Space / Enter · next speaker"
			for preset: Dictionary in _actor_focus.get_presets():
				if preset["id"] == actor_focus_preset:
					_focus_preset_button.text = "P · " + String(preset["label"])
					break
		"character_exit":
			_hint.text = "T · select actor     P · next exit preset     E · exit     S · show again"
			for preset: Dictionary in _character_exit.get_presets():
				if preset["id"] == character_exit_preset:
					_exit_preset_button.text = "P · " + String(preset["label"])
					break
			_update_exit_status()
		"manpu":
			_line.text = "Small marks. A little more feeling." if _mode == "manpu_gallery" else String(_current_beat().get("line", ""))
			_hint.text = "G · return to conversation" if _mode == "manpu_gallery" else "P · preset     T · replay target     F · replay mark     Space / Enter · next line"
			_gallery_button.text = "Return to dialogue" if _mode == "manpu_gallery" else "Open gallery · G"
			for preset: Dictionary in _manpu_animation.get_presets():
				if preset["id"] == manpu_animation_preset:
					_manpu_preset_button.text = "P · " + String(preset["label"])
					break
			var cues := _active_manpu()
			if _manpu_target_index >= cues.size():
				_manpu_target_index = -1
			var target_name := "All marks"
			if _manpu_target_index >= 0:
				var actor := String(cues[_manpu_target_index]["actor"])
				target_name = String(stage_profile.actors[_dialogue_actor_index(actor)]["name"])
			_manpu_target_button.text = "T · " + target_name
			_manpu_target_button.disabled = cues.is_empty()
			_manpu_replay_button.disabled = cues.is_empty()
			_manpu_preset_button.disabled = _mode != "dialogue"
		"locations":
			_line.text = "The next position is yours to choose, Commander."
			_hint.text = "L · change scene     P · replay location title"
		"hologram":
			_line.text = String(_current_beat().get("line", ""))
			_hint.text = "T · select actor     E · toggle effect     Space / Enter · next line"
			var effect: Dictionary = _character_effects[_effect_target]
			_effect_target_button.text = "T · " + String(stage_profile.actors[_dialogue_actor_index(_effect_target)]["name"])
			_effect_toggle_button.text = "E · Hologram" if effect["enabled"] else "E · Normal"
			_effect_toggle_button.add_theme_stylebox_override("normal", _button_style(false, effect["enabled"]))
			_effect_strength_slider.set_value_no_signal(float(effect["strength"]) * 100.0)
			_effect_strength_slider.editable = effect["enabled"]
			_effect_strength_label.text = "%d%%" % roundi(float(effect["strength"]) * 100.0)
	if not _load_errors.is_empty():
		_line.text = "The scene is waiting for its artwork."
		_hint.text = " · ".join(_load_errors)
	_layout_interface()
	queue_redraw()


func _active_manpu() -> Array:
	return super._active_manpu() if demo_id in ["manpu", "actor_focus"] else []


func _advance_dialogue() -> void:
	if demo_id in ["dialogue", "actor_focus", "manpu", "hologram"]:
		_manpu_target_index = -1
		super._advance_dialogue()


func _cycle_focus_preset() -> void:
	var presets: Array[Dictionary] = _actor_focus.get_presets()
	for index in presets.size():
		if presets[index]["id"] == actor_focus_preset:
			set_actor_focus_preset(String(presets[(index + 1) % presets.size()]["id"]))
			_update_interface()
			return


func _replay_focus() -> void:
	_actor_focus.replay()
	_update_character_layers()


func _process(delta: float) -> void:
	super._process(delta)
	if demo_id == "character_exit" and _exit_actor_button != null:
		_update_exit_status()


func _update_exit_status() -> void:
	var actor_name := String(stage_profile.actors[_dialogue_actor_index(_exit_target)]["name"])
	_exit_target_button.text = "T · " + actor_name
	_speaker.text = actor_name
	var exiting: bool = _character_exit.is_exiting(_exit_target)
	var visible_actor: bool = _character_exit.is_visible(_exit_target)
	_exit_actor_button.disabled = not visible_actor or exiting or _entry < 1.0
	_show_actor_button.disabled = visible_actor and not exiting
	if exiting:
		_line.text = "Leaving the scene."
		var appearance: Dictionary = _character_exit.sample(_exit_target)
		var active: Dictionary = _character_exit.get_state()["states"][_exit_target]
		if active["tracks"].has("offset_x_ratio"):
			_footer.text = "Horizontal travel and repeated step bounce. Color stays opaque until offscreen."
		elif is_zero_approx(float(appearance["brightness"])):
			_footer.text = "The black silhouette fades away."
		elif is_equal_approx(float(appearance["opacity"]), 1.0):
			_footer.text = "Color fades into black. The silhouette keeps its coverage."
		else:
			_footer.text = "Ordinary opacity fade: the background shows through the colored actor."
	elif not visible_actor:
		_line.text = "Gone, until you bring her back."
		_footer.text = "Show restores the selected actor. Reset restores everyone."
	else:
		_line.text = "Ready when you are."
		_footer.text = "Select an actor and an exit preset, then let her leave."


func _cycle_exit_target() -> void:
	var index := (_dialogue_actor_index(_exit_target) + 1) % stage_profile.actors.size()
	_exit_target = String(stage_profile.actors[index]["id"])
	_update_interface()


func _cycle_exit_preset() -> void:
	var presets: Array[Dictionary] = _character_exit.get_presets()
	for index in presets.size():
		if presets[index]["id"] == character_exit_preset:
			set_character_exit_preset(String(presets[(index + 1) % presets.size()]["id"]))
			_update_interface()
			return


func _exit_selected_actor() -> void:
	if _entry < 1.0:
		return
	exit_actor(_exit_target)
	_update_interface()


func _show_selected_actor() -> void:
	show_actor(_exit_target)
	_update_interface()


func _cycle_manpu_preset() -> void:
	if _mode != "dialogue":
		return
	var presets: Array[Dictionary] = _manpu_animation.get_presets()
	for index in presets.size():
		if presets[index]["id"] == manpu_animation_preset:
			set_manpu_animation_preset(String(presets[(index + 1) % presets.size()]["id"]))
			_update_interface()
			return


func _cycle_manpu_target() -> void:
	var cues := _active_manpu()
	if cues.is_empty():
		return
	_manpu_target_index += 1
	if _manpu_target_index >= cues.size():
		_manpu_target_index = -1
	_update_interface()


func _replay_selected_manpu() -> void:
	var cues := _active_manpu()
	if cues.is_empty():
		return
	if _manpu_target_index >= 0 and _manpu_target_index < cues.size():
		var cue: Dictionary = cues[_manpu_target_index]
		_replay_manpu_animation(String(cue["actor"]), String(cue["id"]))
	else:
		_replay_manpu_animation()


func _toggle_target() -> void:
	_show_hotspot = not _show_hotspot
	_update_interface()


func _toggle_gallery() -> void:
	_mode = "dialogue" if _mode == "manpu_gallery" else "manpu_gallery"
	_update_interface()


func _replay_title() -> void:
	_select_location(_location_id, true)


func _input(event: InputEvent) -> void:
	if demo_id in ["dialogue", "actor_focus", "manpu", "hologram"]:
		var focused := get_viewport().gui_get_focus_owner()
		if focused != null and focused != _next_button:
			return
		super._input(event)


func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode == KEY_ESCAPE:
		navigate.emit("command_link")
	elif event.keycode == KEY_R:
		_restart()
	elif demo_id == "characters" and event.keycode == KEY_B:
		_toggle_eyes()
	elif demo_id == "characters" and event.keycode == KEY_N:
		_toggle_natural_blink()
	elif demo_id == "actor_focus" and event.keycode == KEY_P:
		_cycle_focus_preset()
	elif demo_id == "actor_focus" and event.keycode == KEY_F:
		_replay_focus()
	elif demo_id == "character_exit" and event.keycode == KEY_T:
		_cycle_exit_target()
	elif demo_id == "character_exit" and event.keycode == KEY_P:
		_cycle_exit_preset()
	elif demo_id == "character_exit" and event.keycode == KEY_E:
		_exit_selected_actor()
	elif demo_id == "character_exit" and event.keycode == KEY_S:
		_show_selected_actor()
	elif demo_id == "contact" and event.keycode == KEY_H:
		_toggle_target()
	elif demo_id == "manpu" and event.keycode == KEY_G:
		_toggle_gallery()
	elif demo_id == "manpu" and event.keycode == KEY_P:
		_cycle_manpu_preset()
	elif demo_id == "manpu" and event.keycode == KEY_T:
		_cycle_manpu_target()
	elif demo_id == "manpu" and event.keycode == KEY_F:
		_replay_selected_manpu()
	elif demo_id == "locations" and event.keycode == KEY_L:
		_change_scene()
	elif demo_id == "locations" and event.keycode == KEY_P:
		_replay_title()
	elif demo_id == "hologram" and event.keycode == KEY_T:
		_cycle_effect_target()
	elif demo_id == "hologram" and event.keycode == KEY_E:
		_toggle_character_effect()
	else:
		return
	get_viewport().set_input_as_handled()
