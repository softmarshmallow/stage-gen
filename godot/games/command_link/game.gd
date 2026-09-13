extends "res://presentation/stage.gd"

## The game owns its stage, controls and world. Scenario executes the mission.
const BRIEFING_CAST_SCRIPT = preload("res://addons/game_presentation/actors/cast_transition.gd")
const BRIEFING_CAST_SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
const SCENARIO_PROGRAM = preload("res://addons/scenario_runtime/program/program.gd")
const SCENARIO_CATALOG = preload("res://addons/scenario_runtime/program/catalog.gd")
const SCENARIO_SESSION = preload("res://addons/scenario_runtime/execution/session.gd")
var saved_state: Dictionary = {}
var _story_id: String:
	get: return str(_presented.get("presentation", {}).get("checkpoint", _presented.get("id", "arrival")))
var _priority: String:
	get: return "" if _facts.get("priority", "unset") == "unset" else str(_facts.priority)
var _approach: String:
	get: return "" if _facts.get("approach", "unset") == "unset" else str(_facts.approach)
var _session = SCENARIO_SESSION.new()
var _program: Dictionary = {}
var _catalog: Dictionary = {}
var _presented: Dictionary = {}
var _frame: Dictionary = {}
var _facts: Dictionary = {}
var _handoff_operation := ""
var _scenario_ready := false
var _restoring := false
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
	var capabilities: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://presentation/scenario_capabilities.json"))
	_catalog = SCENARIO_CATALOG.parse(_read_narrative("catalog.json"), capabilities)
	if _scenario_error(_catalog): return
	_program = SCENARIO_PROGRAM.parse(_read_narrative("mission.json"), _catalog)
	if _scenario_error(_program): return
	_load_errors.append_array(_mission_binding_errors(_program))
	if not _load_errors.is_empty(): return
	var result: Dictionary
	_restoring = not saved_state.is_empty()
	if _restoring:
		if saved_state.get("schema_version") != 2 or not saved_state.get("scenario") is Dictionary:
			_load_errors.append("This mission checkpoint predates Scenario content identity. Start a new mission; the old state was preserved.")
			return
		result = _session.restore(_program, _catalog, _scenario_policy(), saved_state.scenario)
	else:
		result = _session.start(_program, _catalog, _scenario_policy())
	if _scenario_error(result): return
	if _restoring:
		var checkpoint_errors := _checkpoint_errors(saved_state, result.state)
		if not checkpoint_errors.is_empty():
			_load_errors.append_array(checkpoint_errors)
			return
	_scenario_ready = true
	_facts = result.state.facts.duplicate(true)
	_presented = _session.view()
	_frame = _frame_from_state(result.state)
	_mode = str(_frame.get("mode", "dialogue"))
	_connected = bool(saved_state.get("connected", false))
	_natural_blink = true
	_select_location(String(saved_state.get("location", "forward_command")), true)
	_initialize_briefing_cast(saved_state)
	if _restoring:
		_load_errors.append_array(restore_establishing(saved_state.get("establishing_shot", {})))
		_location_title_elapsed = float(saved_state.get("location_title_elapsed", LOCATION_HEADER_SETTLE_SECONDS))
		_entry = 1.0 if not is_establishing() else 0.0
		_actor_focus.clear()
		_manpu_animation.clear()
		_sync_actor_focus(false)
		_sync_manpu_animation(false)
		if saved_state.has("dialogue_camera"):
			_load_errors.append_array(restore_dialogue_camera(saved_state["dialogue_camera"]))
	else:
		_load_errors.append_array(start_establishing("forward_command"))
	_apply_scenario(result, _restoring)
	_restoring = false
	if not _load_errors.is_empty(): _scenario_ready = false


func _mission_binding_errors(program: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for node: Dictionary in program.nodes.values():
		var effects: Array = [node] if node.kind == "effect" else node.get("cues", [])
		for cue: Dictionary in effects:
			if cue.effect.type != "squad_frame": continue
			var frame: Dictionary = cue.effect.parameters
			errors.append_array(_manpu_cue_errors(frame.get("manpu", [])))
			if frame.has("location") and (not _locations.has(frame.location) or not _location_textures.has(frame.location)):
				errors.append("Mission node %s names an unavailable location: %s" % [node.id, frame.location])
			if frame.has("camera") and frame.camera.shot != "wide":
				var actor_id := str(frame.camera.get("target", "speaker"))
				if actor_id == "speaker": actor_id = str(node.get("speaker", ""))
				if _dialogue_actor_index(actor_id) < 0:
					errors.append("Mission node %s camera names an unavailable actor: %s" % [node.id, actor_id])
	return errors


## The game envelope must agree with the admitted narrative, so a contact,
## location or cast flag cannot create a second, contradictory progression state.
func _checkpoint_errors(saved: Dictionary, state: Dictionary) -> Array[String]:
	var fields := ["schema_version", "scenario", "story_id", "priority", "approach", "connected", "location", "location_title_elapsed", "establishing_shot", "briefing_cast_active", "briefing_handoff_started", "briefing_handoff_elapsed", "dialogue_camera"]
	if saved.size() != fields.size(): return ["Mission checkpoint fields are incomplete or unknown; start a new mission."]
	for field: String in fields:
		if not saved.has(field): return ["Mission checkpoint is missing " + field]
	if state.status != "running": return ["Only a running mission checkpoint can resume."]
	for field: String in ["connected", "briefing_cast_active", "briefing_handoff_started"]:
		if not saved[field] is bool: return ["Mission checkpoint " + field + " must be a boolean."]
	for field: String in ["location_title_elapsed", "briefing_handoff_elapsed"]:
		if not (saved[field] is int or saved[field] is float) or not is_finite(float(saved[field])) or float(saved[field]) < 0.0:
			return ["Mission checkpoint " + field + " must be finite and nonnegative."]
	if not saved.establishing_shot is Dictionary or not saved.dialogue_camera is Dictionary:
		return ["Mission checkpoint camera states must be objects."]
	var expected_priority := "" if state.facts.priority == "unset" else str(state.facts.priority)
	var expected_approach := "" if state.facts.approach == "unset" else str(state.facts.approach)
	var view: Dictionary = _session.view()
	if saved.connected != state.facts.connected or saved.priority != expected_priority or saved.approach != expected_approach or saved.story_id != view.presentation.get("checkpoint", view.id):
		return ["Mission checkpoint observations disagree with Scenario; start a new mission."]
	var operations: Array = state.operations.values()
	operations.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return str(a.operation_id).get_slice(":", 2).to_int() < str(b.operation_id).get_slice(":", 2).to_int())
	var location := "forward_command"
	var cast_active := true
	var handoff := {}
	for operation: Dictionary in operations:
		if operation.effect.type == "squad_frame" and operation.effect.parameters.has("location"):
			if location != str(operation.effect.parameters.location): cast_active = false
			location = str(operation.effect.parameters.location)
		elif operation.effect.type == "squad_handoff": handoff = operation
	if saved.location != location or saved.briefing_cast_active != cast_active or saved.briefing_handoff_started != (not handoff.is_empty()):
		return ["Mission checkpoint location or cast state disagrees with its admitted operations."]
	var handoff_elapsed := 0.0 if handoff.is_empty() else minf(float(handoff.duration), float(state.clocks[handoff.clock]) - float(handoff.start_time))
	if absf(float(saved.briefing_handoff_elapsed) - handoff_elapsed) > 0.0001:
		return ["Mission checkpoint handoff time disagrees with its operation clock."]
	var establishing = ESTABLISHING_SHOT_SCRIPT.new()
	var errors: Array[String] = establishing.restore(saved.establishing_shot)
	var camera = DIALOGUE_CAMERA_SCRIPT.new()
	errors.append_array(camera.restore(saved.dialogue_camera))
	if not errors.is_empty(): return errors
	if saved.establishing_shot.location_id != location or not _location_textures.has(location):
		return ["Mission checkpoint establishing view names another location."]
	var texture: Texture2D = _location_textures[location]
	var expected_bounds := _background_rect(DESIGN_SIZE, texture.get_size())
	var bounds: Array = saved.dialogue_camera.background_rect
	if not expected_bounds.is_equal_approx(Rect2(float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))) or saved.dialogue_camera.viewport_size != [DESIGN_SIZE.x, DESIGN_SIZE.y]:
		return ["Mission checkpoint camera bounds disagree with the loaded world."]
	if not camera.focus_id.is_empty() and _dialogue_actor_index(camera.focus_id) < 0:
		return ["Mission checkpoint camera names an unavailable actor."]
	var frame := _frame_from_state(state)
	var can_focus: bool = frame.get("mode", "dialogue") == "dialogue" and not saved.establishing_shot.active and (handoff.is_empty() or handoff.status != "running")
	if not can_focus and (camera.sample() != DIALOGUE_CAMERA_SCRIPT.IDENTITY or camera.is_moving() or not camera.focus_id.is_empty()):
		return ["Mission checkpoint camera conflicts with its current presentation."]
	return []


func save_game() -> Dictionary:
	if not _scenario_ready: return saved_state.duplicate(true)
	return {"schema_version": 2, "scenario": _session.snapshot(),
		"story_id": _story_id, "priority": _priority, "approach": _approach,
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
	_briefing_handoff_started = bool(saved.get("briefing_handoff_started", false))
	_briefing_handoff_elapsed = 0.0
	_briefing_handoff_duration = 0.0
	if _briefing_handoff_started and _briefing_cast.initialized:
		_briefing_cast.start()
		_briefing_handoff_duration = _handoff_duration()
		var elapsed := float(saved.get("briefing_handoff_elapsed", _briefing_handoff_duration))
		_briefing_handoff_elapsed = clampf(elapsed, 0.0, _briefing_handoff_duration) if is_finite(elapsed) else 0.0
		_briefing_cast.advance(_briefing_handoff_elapsed)


func _handoff_duration() -> float:
	var state: Dictionary = _briefing_cast.get_state()
	var settings: Dictionary = _briefing_cast.get_settings()
	var motion_phases := 2.0 if settings["pattern"] == "shift_and_replace" else 1.0
	return float(state["phase_duration"]) + float(settings["motion_duration_seconds"]) * motion_phases


func _is_briefing_handoff_active() -> bool:
	return _briefing_cast_active and not _handoff_operation.is_empty()


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
	var beat := _frame.duplicate(true)
	var speaker_id := str(_presented.get("speaker", ""))
	if speaker_id == "<null>": speaker_id = ""
	beat["speaker"] = str(_program.get("speakers", {}).get(speaker_id, {}).get("display_name", ""))
	beat["line"] = str(_presented.get("text", ""))
	if _presented.get("kind", "") == "choice":
		beat["choices"] = []
		for option: Dictionary in _session.view().get("options", []):
			beat.choices.append({"id": option.id, "label": option.get("text", ""), "next": option.target})
	return beat


func _active_manpu() -> Array:
	return [] if _is_briefing_handoff_active() else _current_beat().get("manpu", [])


func _enter_beat(presentation: Dictionary) -> void:
	_presented = presentation.duplicate(true)
	_update_interface()


func _apply_frame(parameters: Dictionary) -> void:
	var previous_mode := _mode
	_frame = parameters.duplicate(true)
	_mode = str(_frame.get("mode", "dialogue"))
	if _mode != previous_mode:
		_entry = 0.0
		_reaction = 0.0
		_pointer = Vector2(-1000, -1000)
	if _frame.has("location") and str(_frame.location) != _location_id:
		var errors := start_establishing(str(_frame.location))
		_load_errors.append_array(errors)
		if errors.is_empty(): _briefing_cast_active = false
	_apply_camera_cue(_current_beat())
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
	if is_establishing() or _is_briefing_handoff_active() or is_dialogue_camera_moving() or index < 0 or index >= choices.size() or not _load_errors.is_empty(): return
	get_viewport().gui_release_focus()
	_apply_scenario(_session.submit({"kind": "choose", "choice_id": choices[index].id}))


func _advance_dialogue() -> void:
	if not _load_errors.is_empty() or not _scenario_ready: return
	if is_establishing():
		_skip_view()
		return
	_apply_scenario(_session.submit({"kind": "advance"}))


func _connect_at(point: Vector2) -> bool:
	if not bool(_frame.get("contact", false)) or is_establishing() or _is_briefing_handoff_active() or _connected: return false
	if not super._connect_at(point): return false
	var view := _session.view()
	_apply_scenario(_session.submit({"kind": "host_event", "session_id": "mission", "node_id": view.node_id, "visit_id": view.visit_id, "name": "contact_confirmed"}))
	return true


func _skip_view() -> void:
	skip_establishing()
	get_viewport().gui_release_focus()
	_update_interface()


func _restart() -> void:
	if _scenario_ready:
		_session.cancel("new_mission")
		_session.drain_events()
	_session = SCENARIO_SESSION.new()
	_handoff_operation = ""
	_actor_focus.clear()
	_manpu_animation.clear()
	_character_exit.clear()
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
	_apply_scenario(_session.start(_program, _catalog, _scenario_policy()))
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
	if _scenario_ready and not _capture_frozen:
		_apply_scenario(_session.tick(0.0 if was_establishing else delta))
	if was_handoff and not _is_briefing_handoff_active():
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
		_line.text = "The mission could not load. Use Menu to start a new mission."
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


func _read_narrative(name: String) -> Dictionary:
	var value = JSON.parse_string(FileAccess.get_file_as_string("res://narrative/" + name))
	if value is Dictionary: return value
	_load_errors.append("Unreadable narrative content: " + name)
	return {}


func _scenario_policy() -> Dictionary:
	return {"session_id": "mission", "capabilities": {"squad_frame": 1, "squad_handoff": 1}, "channels": ["dialogue"], "bindings": []}


func _scenario_error(result: Dictionary) -> bool:
	if result.has("error"):
		_load_errors.append(str(result.error.get("message", "Invalid Scenario content")))
		return true
	return false


func _frame_from_state(state: Dictionary) -> Dictionary:
	var latest := -1
	var frame := {}
	for operation: Dictionary in state.get("operations", {}).values():
		var serial := str(operation.operation_id).get_slice(":", 2).to_int()
		if operation.effect.type == "squad_frame" and serial > latest:
			latest = serial
			frame = operation.effect.parameters.duplicate(true)
	return frame


func _apply_scenario(result: Dictionary, restoring: bool = false) -> void:
	if _scenario_error(result): return
	_facts = result.get("state", {}).get("facts", {}).duplicate(true)
	_session.drain_events()
	for event: Dictionary in result.get("events", []):
		match str(event.type):
			"scenario/presented":
				if not restoring: _enter_beat(event.presentation)
			"scenario/effect_started", "scenario/effect_restored":
				if event.effect.type == "squad_frame" and not restoring:
					_apply_frame(event.effect.parameters)
				elif event.effect.type == "squad_handoff":
					_handoff_operation = str(event.operation_id)
					if not restoring: _start_briefing_handoff()
			"scenario/effect_finished", "scenario/effect_cancelled":
				if str(event.operation_id) == _handoff_operation: _handoff_operation = ""
			"scenario/ended":
				_restart()
			"scenario/failed":
				_load_errors.append("Mission sequence failed: " + str(event.get("reason", "unknown")))
	_update_interface()


func _exit_tree() -> void:
	if _scenario_ready:
		_session.cancel("route_exit")
		_session.drain_events()
