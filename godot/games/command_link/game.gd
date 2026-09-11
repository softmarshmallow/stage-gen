extends "res://presentation/stage.gd"

## Authored mission beats and player decisions belong to this disposable route.
const BRIEFING_CAST_SCRIPT = preload("res://addons/game_presentation/actors/cast_transition.gd")
const BRIEFING_CAST_SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
const STORY := {
	"arrival": {"speaker": "Mira", "line": "Commander on deck. Good timing — the evacuation convoy is almost ready.", "manpu": [{"actor": "mira", "id": "surprise"}], "next": "briefing"},
	"briefing": {"speaker": "Lena", "line": "The coast road is exposed, and our relay beacon has gone dark.", "manpu": [{"actor": "lena", "id": "sweat_drop"}], "camera": {"shot": "close_up", "target": "speaker", "zoom": 3.5, "duration_seconds": 0.9}, "next": "briefing_risk"},
	"briefing_risk": {"speaker": "Lena", "line": "Every transport has civilians aboard. If we stop in those blind corners, we're holding them on open ground.", "manpu": [{"actor": "lena", "id": "sweat_drop"}], "next": "briefing_plan"},
	"briefing_plan": {"speaker": "Lena", "line": "We'll keep them moving. Give the reserve team one clear job, and Mira and I will cover the rest.", "next": "orders"},
	"orders": {"speaker": "Mira", "line": "Your call, Commander. What gets our first reserve team?", "camera": {"shot": "wide", "duration_seconds": 0.8}, "choices": [
		{"label": "Keep the convoy covered.", "next": "escort", "priority": "escort_priority"},
		{"label": "Restore the relay beacon.", "next": "beacon", "priority": "beacon_priority"}]},
	"escort": {"speaker": "Mira", "line": "People first. I'll keep our reserve with the transports. Nobody gets left on that road.", "manpu": [{"actor": "mira", "id": "sparkle"}], "next": "departure"},
	"beacon": {"speaker": "Mira", "line": "Copy. Our reserve goes with the repair team. Once that beacon is up, the convoy can see its way home.", "manpu": [{"actor": "mira", "id": "sparkle"}], "next": "departure"},
	"departure": {"speaker": "Lena", "line": "I'll scout ahead. Sera, take over the route briefing. I'll meet you at staging.", "next": "analysis"},
	"analysis": {"speaker": "Sera", "line": "I have two routes out. Before we move, Mira needs to pair your command link with the squad channel.", "next": "link"},
	"link": {"speaker": "Mira", "line": "One touch, Commander. Then, wherever we go, you'll be right here with us.", "mode": "reach_out", "contact": true, "next": "approach"},
	"approach": {"speaker": "Mira", "line": "We can meet Lena at the overlook, or follow Sera straight down the shore. Which way, Commander?", "choices": [
		{"label": "Check the perimeter overlook first.", "next": "overlook", "approach": "high_road"},
		{"label": "Head straight to coastal staging.", "next": "shore", "approach": "shore_road"}]},
	"overlook": {"speaker": "Lena", "line": "Clear view from here. Two blind corners on the coast road — I'll mark them and take overwatch.", "manpu": [{"actor": "lena", "id": "sparkle"}], "location": "perimeter_overlook", "next": "deploy"},
	"shore": {"speaker": "Sera", "line": "Shore route clear. The transports are staged under the palms. We made it ahead of schedule.", "manpu": [{"actor": "sera", "id": "sparkle"}], "location": "coastal_staging", "next": "deploy"},
	"deploy": {"speaker": "Mira", "line": "There they are. Engines running, everyone aboard. Give the word and we'll bring them through.", "location": "coastal_staging", "next": "remembered"},
	"remembered": {"speaker": "Sera", "line": "", "next": "end"},
	"end": {"speaker": "", "line": "The command link holds. Your squad takes its positions, and the first transport rolls toward the coast road.", "ending": true},
}
var saved_state: Dictionary = {}
var _story_id := "arrival"
var _priority := ""
var _approach := ""
var _menu_button: Button
var _skip_button: Button
var _choice_buttons: Array[Button] = []
var _briefing_cast = BRIEFING_CAST_SCRIPT.new()
var _briefing_cast_active := true
var _briefing_handoff_started := false
var _briefing_handoff_elapsed := 0.0
var _briefing_handoff_duration := 0.0


func _build_interface() -> void:
	_title = _label("Command Link", 27, PAPER)
	_subtitle = _label("", 13, MUTED)
	_location_title = _label("", 27, PAPER)
	_location_detail = _label("", 13, WARM)
	_line = _label("", 24, PAPER)
	_speaker = _label("", 18, PAPER)
	_hint = _label("", 13, MUTED)
	_footer = _label("", 13, MUTED)
	_menu_button = _button("Menu", func() -> void: navigate.emit("menu"))
	_menu_button.tooltip_text = "Pause the mission. Keyboard: Esc"
	_next_button = _button("Next →", _advance_dialogue)
	_next_button.tooltip_text = "Continue. Keyboard: Space or Enter"
	_skip_button = _button("Skip view →", _skip_view)
	_skip_button.tooltip_text = "Finish the location introduction. Keyboard: Space or Enter"
	TACTICAL_THEME.style_primary(_next_button)
	TACTICAL_THEME.style_primary(_skip_button)
	for index in 2:
		var choice := _button("", _choose.bind(index))
		choice.add_theme_font_size_override("font_size", 18)
		_choice_buttons.append(choice)


func _draw_dialogue_scrim(canvas: CanvasItem) -> void:
	if is_establishing() or _is_briefing_handoff_active():
		return
	_draw_tactical_panel(canvas, Rect2(32, 667, 1216, 211),
		Color(0.035, 0.055, 0.073, 0.94), TACTICAL_THEME.BORDER, 16.0)
	canvas.draw_line(Vector2(56, 805), Vector2(1224, 805), Color(0.36, 0.44, 0.48, 0.35), 1.0)
	var accent: Color = {"Mira": TACTICAL_THEME.SECONDARY, "Lena": WARM,
		"Sera": Color("8cb6d8")}.get(String(_current_beat()["speaker"]), WARM)
	canvas.draw_rect(Rect2(32, 667, 4, 68), accent)
	if _speaker != null and _speaker.visible:
		_draw_tactical_panel(canvas, Rect2(56, 646, 220, 39), TACTICAL_THEME.PANEL_RAISED, accent, 9.0)
		canvas.draw_rect(Rect2(56, 646, 4, 39), accent)
	canvas.draw_line(Vector2(1188, 681), Vector2(1224, 681), accent, 2.0)
	canvas.draw_line(Vector2(1218, 687), Vector2(1224, 687), accent, 2.0)


func _configure_route() -> void:
	for id: String in _character_effects:
		_character_effects[id]["enabled"] = false
	_story_id = String(saved_state.get("story_id", "arrival"))
	if not STORY.has(_story_id):
		_story_id = "arrival"
	_priority = String(saved_state.get("priority", ""))
	_approach = String(saved_state.get("approach", ""))
	_connected = bool(saved_state.get("connected", false))
	_mode = String(STORY[_story_id].get("mode", "dialogue"))
	_natural_blink = true
	_select_location(String(saved_state.get("location", "forward_command")), true)
	_initialize_briefing_cast(saved_state)
	if not saved_state.is_empty():
		_load_errors.append_array(restore_establishing(saved_state.get("establishing_shot", {})))
		_location_title_elapsed = float(saved_state.get("location_title_elapsed", LOCATION_HEADER_SETTLE_SECONDS))
		_entry = 1.0 if not is_establishing() else 0.0
		# Returning from a demo resumes the held speaker without a fresh pulse.
		_actor_focus.clear()
		_manpu_animation.clear()
		_sync_actor_focus(false)
		_sync_manpu_animation(false)
		if saved_state.has("dialogue_camera"):
			_load_errors.append_array(restore_dialogue_camera(saved_state["dialogue_camera"]))
	else:
		_load_errors.append_array(start_establishing("forward_command"))
	for beat: Dictionary in STORY.values():
		_load_errors.append_array(_manpu_cue_errors(beat.get("manpu", [])))


func save_game() -> Dictionary:
	return {"story_id": _story_id, "priority": _priority, "approach": _approach,
		"connected": _connected, "location": _location_id,
		"location_title_elapsed": _location_title_elapsed, "establishing_shot": save_establishing(),
		"briefing_cast_active": _briefing_cast_active, "briefing_handoff_started": _briefing_handoff_started,
		"briefing_handoff_elapsed": _briefing_handoff_elapsed, "dialogue_camera": save_dialogue_camera()}


## Only this authored handoff is resumed here. The reusable controller keeps
## its existing API; the route reconstructs its timeline from elapsed time.
func _initialize_briefing_cast(saved: Dictionary = {}) -> void:
	var ids: Array[String] = ["lena", "mira", "sera"]
	_load_errors.append_array(_briefing_cast.initialize(ids, CHARACTER_EXIT_CATALOG, BRIEFING_CAST_SPEC))
	_briefing_cast_active = bool(saved.get("briefing_cast_active", _location_id == "forward_command"))
	var after_departure := _story_id in ["analysis", "link", "approach", "overlook", "shore", "deploy", "remembered", "end"]
	_briefing_handoff_started = bool(saved.get("briefing_handoff_started", after_departure))
	_briefing_handoff_elapsed = 0.0
	_briefing_handoff_duration = 0.0
	if _briefing_handoff_started and _briefing_cast.initialized:
		_briefing_cast.start()
		_briefing_handoff_duration = _handoff_duration()
		var elapsed := float(saved.get("briefing_handoff_elapsed", _briefing_handoff_duration))
		_briefing_handoff_elapsed = clampf(elapsed, 0.0, _briefing_handoff_duration) if is_finite(elapsed) else 0.0
		_briefing_cast.advance(_briefing_handoff_elapsed)
		if not _briefing_cast.is_busy() and _story_id == "departure":
			_story_id = "analysis"


func _handoff_duration() -> float:
	var state: Dictionary = _briefing_cast.get_state()
	var settings: Dictionary = _briefing_cast.get_settings()
	var motion_phases := 2.0 if settings["pattern"] == "shift_and_replace" else 1.0
	return float(state["phase_duration"]) + float(settings["motion_duration_seconds"]) * motion_phases


func _is_briefing_handoff_active() -> bool:
	return _briefing_cast_active and _briefing_handoff_started and _story_id == "departure"


func _can_use_dialogue_camera() -> bool:
	return super._can_use_dialogue_camera() and not _is_briefing_handoff_active()


func _start_briefing_handoff() -> void:
	if _briefing_handoff_started or not _briefing_cast.initialized:
		return
	_load_errors.append_array(_briefing_cast.start())
	clear_dialogue_camera()
	_briefing_handoff_started = true
	_briefing_handoff_elapsed = 0.0
	_briefing_handoff_duration = _handoff_duration()
	# Rapid progression after skipping the opening view must still show the
	# departure's full-coverage silhouette, independent of the entry fade.
	_entry = 1.0
	_actor_focus.clear()
	_manpu_animation.clear()
	get_viewport().gui_release_focus()
	_update_interface()


func _sync_actor_focus(animate: bool = true) -> void:
	if _is_briefing_handoff_active():
		_actor_focus.clear()
		return
	super._sync_actor_focus(animate)


func _actor_is_visible(actor_id: String) -> bool:
	return super._actor_is_visible(actor_id) and (not _briefing_cast_active or not _briefing_cast.initialized or bool(_briefing_cast.sample(actor_id)["visible"]))


func _actor_is_present(actor_id: String) -> bool:
	return super._actor_is_present(actor_id) and _actor_is_visible(actor_id) and not _is_briefing_handoff_active()


func _actor_visual_sample(actor_id: String) -> Dictionary:
	var appearance := super._actor_visual_sample(actor_id)
	if _briefing_cast_active and _briefing_cast.initialized:
		var cast: Dictionary = _briefing_cast.sample(actor_id)
		appearance["brightness"] = float(appearance["brightness"]) * float(cast["brightness"])
		appearance["opacity"] = float(appearance["opacity"]) * float(cast["opacity"])
		for axis: String in ["offset_x_ratio", "offset_y_ratio"]:
			appearance[axis] = float(appearance.get(axis, 0.0)) + float(cast.get(axis, 0.0))
	return appearance


func _dialogue_rect(viewport_size: Vector2, actor_index: int) -> Rect2:
	var rect := super._dialogue_rect(viewport_size, actor_index)
	if _briefing_cast_active and _briefing_cast.initialized:
		var actor_id := String(stage_profile.actors[actor_index]["id"])
		rect.position.x = float(_briefing_cast.sample(actor_id)["center_x"]) - rect.size.x * 0.5
	return rect


func _current_beat() -> Dictionary:
	var beat: Dictionary = STORY[_story_id].duplicate(true)
	if _story_id == "link" and _connected:
		beat["line"] = "There you are. Link confirmed. I hear you clearly, Commander. Let's bring everyone home."
	if _story_id == "remembered":
		beat["line"] = "Your reserve is with the convoy. I'll patch the beacon remotely while Lena watches the road." if _priority == "escort_priority" else "The repair team has your reserve, as ordered. The beacon is coming online; I'll guide the convoy through."
		beat["manpu"] = [{"actor": "sera", "id": "sparkle"}]
	return beat


func _active_manpu() -> Array:
	return [] if _is_briefing_handoff_active() else _current_beat().get("manpu", [])


func _enter_beat(id: String) -> void:
	var previous_mode := _mode
	_story_id = id
	var beat := _current_beat()
	_mode = String(beat.get("mode", "dialogue"))
	if _mode != previous_mode:
		_entry = 0.0
		_reaction = 0.0
		_pointer = Vector2(-1000, -1000)
	if beat.has("location") and String(beat["location"]) != _location_id:
		var errors := start_establishing(String(beat["location"]))
		_load_errors.append_array(errors)
		if errors.is_empty():
			# Restore the full squad only while the new location owns the screen.
			# The next cast reveal uses ordinary three-person scene framing.
			_briefing_cast_active = false
	_apply_camera_cue(beat)
	_update_interface()


## Camera direction is authored once on entry. Missing cues hold the shot,
## including across later lines and speaker changes; there is no auto-follow.
func _apply_camera_cue(beat: Dictionary) -> void:
	if not beat.has("camera"):
		return
	var cue: Dictionary = beat["camera"]
	var duration := float(cue.get("duration_seconds", 0.7))
	if cue["shot"] == "wide":
		_load_errors.append_array(wide_dialogue_camera(duration))
		return
	var actor_id := String(cue.get("target", "speaker"))
	if actor_id == "speaker":
		actor_id = ""
		for actor: Dictionary in stage_profile.actors:
			if actor["name"] == beat.get("speaker", ""):
				actor_id = String(actor["id"])
				break
	_load_errors.append_array(focus_dialogue_camera(actor_id, float(cue.get("zoom", 2.0)), duration))


func _choose(index: int) -> void:
	var choices: Array = _current_beat().get("choices", [])
	if is_establishing() or _is_briefing_handoff_active() or is_dialogue_camera_moving() or index < 0 or index >= choices.size() or not _load_errors.is_empty():
		return
	var choice: Dictionary = choices[index]
	if choice.has("priority"):
		_priority = choice["priority"]
	if choice.has("approach"):
		_approach = choice["approach"]
	get_viewport().gui_release_focus()
	_enter_beat(choice["next"])


func _advance_dialogue() -> void:
	if not _load_errors.is_empty():
		return
	if is_establishing():
		_skip_view()
		return
	if _is_briefing_handoff_active():
		return
	if _story_id == "departure" and not _briefing_handoff_started:
		_start_briefing_handoff()
		return
	var beat := _current_beat()
	if beat.has("choices") or (beat.get("contact", false) and not _connected):
		return
	if beat.get("ending", false):
		_restart()
	else:
		_enter_beat(beat["next"])


func _connect_at(point: Vector2) -> bool:
	if _story_id != "link" or is_establishing() or _is_briefing_handoff_active() or _connected:
		return false
	return super._connect_at(point)


func _skip_view() -> void:
	skip_establishing()
	get_viewport().gui_release_focus()
	_update_interface()


func _restart() -> void:
	_actor_focus.clear()
	_manpu_animation.clear()
	_character_exit.clear()
	_story_id = "arrival"
	_priority = ""
	_approach = ""
	_connected = false
	_reaction = 0.0
	_mode = "dialogue"
	_manual_closed = false
	_natural_blink = true
	_blink_remaining = 0.0
	_blink_wait = 3.8
	_briefing_cast_active = true
	_initialize_briefing_cast({"briefing_cast_active": true})
	_load_errors.append_array(start_establishing("forward_command"))
	get_viewport().gui_release_focus()
	_update_interface()


func _process(delta: float) -> void:
	var was_establishing := is_establishing()
	var camera_was_moving := is_dialogue_camera_moving()
	var was_handoff := _is_briefing_handoff_active()
	var handoff_overflow := 0.0
	if was_handoff and not was_establishing and not _capture_frozen:
		var remaining := maxf(0.0, _briefing_handoff_duration - _briefing_handoff_elapsed)
		_briefing_cast.advance(delta)
		_briefing_handoff_elapsed = minf(_briefing_handoff_duration, _briefing_handoff_elapsed + delta)
		handoff_overflow = maxf(0.0, delta - remaining)
	super._process(delta)
	if was_handoff and not _briefing_cast.is_busy() and not is_establishing() and not _capture_frozen:
		_enter_beat("analysis")
		_actor_focus.advance(handoff_overflow)
		_manpu_animation.advance(handoff_overflow)
		_update_character_layers()
	elif was_establishing != is_establishing() or camera_was_moving != is_dialogue_camera_moving():
		_update_interface()


func _input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode == KEY_ESCAPE:
		navigate.emit("menu")
		get_viewport().set_input_as_handled()
	elif event.keycode in [KEY_SPACE, KEY_ENTER, KEY_KP_ENTER]:
		# A focused choice or Menu button keeps its ordinary keyboard action.
		var focused := get_viewport().gui_get_focus_owner()
		if focused != null and focused != _next_button and focused != _skip_button:
			return
		_advance_dialogue()
		get_viewport().set_input_as_handled()


func _unhandled_key_input(_event: InputEvent) -> void:
	pass


func _update_interface() -> void:
	if _line == null:
		return
	var beat := _current_beat()
	var choices: Array = beat.get("choices", [])
	var introducing := is_establishing()
	var transitioning := _is_briefing_handoff_active()
	var hide_dialogue := introducing or transitioning
	var awaiting_contact: bool = beat.get("contact", false) and not _connected
	_line.text = String(beat["line"])
	_line.visible = not hide_dialogue
	_speaker.text = String(beat["speaker"])
	_speaker.visible = not hide_dialogue and not _speaker.text.is_empty()
	_skip_button.visible = introducing
	_next_button.visible = not hide_dialogue and choices.is_empty() and not awaiting_contact
	_next_button.text = "Begin again" if beat.get("ending", false) else "Next →"
	_footer.text = "Briefing complete · Convoy underway" if beat.get("ending", false) else ""
	_footer.visible = not hide_dialogue
	_hint.text = "Touch Mira's fingertip to connect" if awaiting_contact else ("Choose your order" if not choices.is_empty() else "")
	_hint.visible = not hide_dialogue
	for index in _choice_buttons.size():
		_choice_buttons[index].visible = not hide_dialogue and index < choices.size()
		_choice_buttons[index].disabled = is_dialogue_camera_moving()
		if index < choices.size():
			_choice_buttons[index].text = String(choices[index]["label"])
	if not _load_errors.is_empty():
		_line.text = "The scene could not load its artwork."
		_hint.text = " · ".join(_load_errors)
		_line.show()
		_hint.show()
		_next_button.disabled = true
		_skip_button.disabled = true
		for choice: Button in _choice_buttons:
			choice.disabled = true
	_layout_interface()
	queue_redraw()


func _layout_interface() -> void:
	if _title == null:
		return
	_title.position = Vector2(32, 22)
	_title.size = Vector2(1000, 40)
	_subtitle.position = Vector2(33, 62)
	_subtitle.size = Vector2(1000, 24)
	_location_title.position = _title.position
	_location_title.size = _title.size
	_location_detail.position = _subtitle.position
	_location_detail.size = _subtitle.size
	_menu_button.position = Vector2(1144, 32)
	_menu_button.size = Vector2(104, 36)
	_speaker.position = Vector2(74, 649)
	_speaker.size = Vector2(184, 32)
	_line.position = Vector2(64, 699)
	_line.size = Vector2(1152, 78)
	_hint.position = Vector2(64, 777)
	_hint.size = Vector2(1152, 25)
	_next_button.position = Vector2(1048, 818)
	_next_button.size = Vector2(176, 44)
	_next_button.add_theme_font_size_override("font_size", 18)
	_skip_button.position = _next_button.position
	_skip_button.size = _next_button.size
	_footer.position = Vector2(64, 818)
	_footer.size = Vector2(900, 44)
	for index in _choice_buttons.size():
		_choice_buttons[index].position = Vector2(64 + index * 588, 818)
		_choice_buttons[index].size = Vector2(572, 44)
	_update_character_layers()
	queue_redraw()
