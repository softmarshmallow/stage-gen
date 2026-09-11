extends RefCounted

## Independent, finite checks of route ownership and actual viewport input.
const DEMOS: Array[String] = ["characters", "contact", "dialogue", "actor_focus", "manpu", "locations", "hologram", "character_exit", "cast_transition", "establishing_shot", "dialogue_camera"]
const MODES := {"characters": "full_body", "contact": "reach_out", "locations": "background", "dialogue": "dialogue", "actor_focus": "dialogue", "manpu": "dialogue", "hologram": "dialogue", "character_exit": "dialogue"}
const DESIGN_SIZE := Vector2(1280, 900)
const STAGE_SCRIPT = preload("res://presentation/stage.gd")
var _errors: Array[String] = []
var _captures: Array[String] = []


func run(root: Control, options: Dictionary) -> void:
	if root.selected_game_id != "command_link":
		printerr("The mission route suite requires --game command_link.")
		root.get_tree().quit(2)
		return
	await _settle(root)
	for priority_index in 2:
		for approach_index in 2:
			await _story_branch(root, priority_index, approach_index)
	await _handoff_resume(root)
	await _resume_and_demos(root)
	await _scaled_input(root)
	if _errors.is_empty() and options.has("capture-routes"):
		if DisplayServer.get_name() == "headless":
			_errors.append("Route screenshots require a real renderer.")
		else:
			await _capture_routes(root, String(options.get("capture-dir", "res://tests/routes/captures")))
	if not _errors.is_empty():
		for issue: String in _errors:
			printerr("FAIL routes: " + issue)
		root.get_tree().quit(1)
		return
	print("PASS routes: four mission branches, required fingertip contact, authored cast handoff, per-phase resume, establishing-shot and choice gating, keyboard choices, replay, resume/new game, all menu/demo links, demo shortcut ownership/reset, and scaled physical input")
	if not _captures.is_empty():
		print("Route captures complete: %d states" % _captures.size())
	root.get_tree().quit(0)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _active(root: Control) -> Control:
	return root.get("active_scene") as Control


func _route(root: Control) -> String:
	return String(root.get("current_route"))


func _story(scene: Control) -> String:
	return String(scene.get("_story_id"))


func _button(scene: Control, property: String) -> Button:
	return scene.get(property) as Button


func _freeze(scene: Control) -> void:
	if scene.has_method("_update_character_layers"):
		scene.set("_capture_frozen", true)
		scene.set("_entry", 1.0)
		scene.call("_update_character_layers")


func _settle(root: Control) -> void:
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	var scene: Control = _active(root)
	if scene != null:
		_freeze(scene)
		if scene.has_method("_update_character_layers"):
			var load_errors: Array = scene.get("_load_errors")
			_expect(load_errors.is_empty(), "%s asset errors: %s" % [_route(root), load_errors])


func _open(root: Control, route_id: String) -> void:
	_expect(bool(root.call("open_route", route_id)), "Could not open " + route_id)
	_freeze(_active(root))
	await _settle(root)


func _key(root: Control, keycode: Key) -> void:
	for pressed: bool in [true, false]:
		var event := InputEventKey.new()
		event.keycode = keycode
		event.pressed = pressed
		root.get_viewport().push_input(event, true)


func _click(root: Control, button: Button) -> void:
	if button == null or not button.is_visible_in_tree() or button.disabled:
		_errors.append("A required route button is missing, hidden, or disabled.")
		return
	var point: Vector2 = root.get_viewport().get_final_transform() * button.get_global_rect().get_center()
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.position = point
		event.global_position = point
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		root.get_viewport().push_input(event, false)


func _next(root: Control) -> void:
	_click(root, _button(_active(root), "_next_button"))


func _choose(root: Control, index: int, keyboard: bool = false) -> void:
	var buttons: Array = _active(root).get("_choice_buttons")
	var button: Button = buttons[index] as Button
	if keyboard:
		button.grab_focus()
		_key(root, KEY_ENTER)
	else:
		_click(root, button)


func _finish_shot(root: Control) -> void:
	var scene: Control = _active(root)
	if not bool(scene.call("is_establishing")):
		return
	var held_story: String = _story(scene)
	root.get_viewport().gui_release_focus()
	_key(root, KEY_SPACE)
	_expect(not bool(scene.call("is_establishing")) and _story(scene) == held_story, "Skipping an establishing shot must reveal its held beat without advancing the story.")


func _reach_orders(root: Control) -> void:
	_finish_shot(root)
	for index in 4:
		_next(root)
	_expect(_story(_active(root)) == "orders", "The three-line briefing must lead to the mission-priority choice.")
	_settle_dialogue_camera(_active(root))


func _settle_dialogue_camera(scene: Control) -> void:
	if not bool(scene.call("is_dialogue_camera_moving")):
		return
	var saved: Dictionary = scene.call("save_dialogue_camera")
	_tick_game(scene, float(saved["duration_seconds"]) - float(saved["elapsed"]))


func _reach_link(root: Control, priority_index: int = 0) -> void:
	_reach_orders(root)
	_choose(root, priority_index)
	_finish_briefing(root)
	_next(root)
	_expect(_story(_active(root)) == "link", "Both mission priorities must lead to the required command-link interaction.")
	_freeze(_active(root))


func _actor_sprite(scene: Control, actor: String) -> TextureRect:
	return (scene.get("_actor_nodes") as Dictionary)[actor] as TextureRect


func _expect_initial_cast(scene: Control) -> void:
	var lena: TextureRect = _actor_sprite(scene, "lena")
	var mira: TextureRect = _actor_sprite(scene, "mira")
	_expect(lena.visible and mira.visible and not _actor_sprite(scene, "sera").visible and lena.get_rect().get_center().x < mira.get_rect().get_center().x, "The briefing must open with Lena left, Mira right, and Sera absent.")
	var saved: Dictionary = scene.call("save_game")
	_expect(bool(saved["briefing_cast_active"]) and not bool(saved["briefing_handoff_started"]) and is_zero_approx(float(saved["briefing_handoff_elapsed"])), "A fresh briefing must reset its handoff and reserve Sera for her arrival.")


func _tick_game(scene: Control, seconds: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", seconds)
	scene.set("_capture_frozen", true)


func _briefing_state(scene: Control) -> Dictionary:
	var controller: RefCounted = scene.get("_briefing_cast")
	return controller.call("get_state")


func _start_briefing(root: Control) -> void:
	_freeze(_active(root))
	_next(root)
	_expect(_story(_active(root)) == "departure", "Both orders must lead to Lena's authored departure beat.")
	_next(root)
	_expect(_story(_active(root)) == "departure" and bool(_active(root).call("_is_briefing_handoff_active")), "Advancing Lena's farewell must hold that beat while the cast handoff runs.")


func _expect_handoff_gate(root: Control) -> void:
	var scene: Control = _active(root)
	var before: Dictionary = scene.call("save_game")
	root.get_viewport().gui_release_focus()
	_key(root, KEY_SPACE)
	_key(root, KEY_ENTER)
	scene.call("_advance_dialogue")
	_expect(scene.call("save_game") == before, "Next and keyboard progression must not bypass the active cast handoff.")
	_expect(not _button(scene, "_next_button").visible and not (scene.get("_line") as Label).visible and not (scene.get("_speaker") as Label).visible, "The pending speaker and Next must remain hidden until the handoff completes.")
	for button: Button in scene.get("_choice_buttons"):
		_expect(not button.visible, "Choices must remain hidden during the cast handoff.")
	_expect((scene.call("_presented_manpu_cues") as Array).is_empty(), "The arriving actor's manpu must wait for the completed handoff.")


func _finish_briefing(root: Control) -> void:
	var scene: Control = _active(root)
	var left: float = _actor_sprite(scene, "lena").get_rect().get_center().x
	var right: float = _actor_sprite(scene, "mira").get_rect().get_center().x
	_start_briefing(root)
	_expect_handoff_gate(root)
	_tick_game(scene, 0.3)
	var outgoing: TextureRect = _actor_sprite(scene, "lena")
	_expect(outgoing.visible and is_equal_approx(outgoing.modulate.a, 1.0) and outgoing.modulate.r > 0.0 and outgoing.modulate.r < 1.0, "Lena's first exit phase must remove color without losing opacity.")
	_tick_game(scene, 0.195)
	_expect(outgoing.modulate.is_equal_approx(Color(0, 0, 0, 1)), "Lena must reach a fully opaque black silhouette before fading away.")
	_tick_game(scene, 0.805)
	_expect(String(_briefing_state(scene)["phase"]) == "move" and not outgoing.visible and not _actor_sprite(scene, "sera").visible and _actor_sprite(scene, "mira").visible, "Only Mira may remain visible while she takes Lena's place.")
	_expect(not is_equal_approx(_actor_sprite(scene, "mira").get_rect().get_center().x, right), "The survivor must actually change position during the handoff.")
	_tick_game(scene, 0.8)
	_expect(String(_briefing_state(scene)["phase"]) == "enter" and _actor_sprite(scene, "sera").visible and _actor_sprite(scene, "sera").modulate.a > 0.0 and _actor_sprite(scene, "sera").modulate.a < 1.0, "Sera must enter after Mira's move, with her own bounded opacity.")
	_expect_handoff_gate(root)
	_tick_game(scene, 0.4)
	_expect(_story(scene) == "analysis" and not bool(scene.call("_is_briefing_handoff_active")) and (scene.get("_line") as Label).visible and (scene.get("_speaker") as Label).text == "Sera", "The completed handoff must reveal Sera's pending analysis once.")
	_expect(not outgoing.visible and is_equal_approx(_actor_sprite(scene, "mira").get_rect().get_center().x, left) and is_equal_approx(_actor_sprite(scene, "sera").get_rect().get_center().x, right), "The main story must finish with Mira at the old left slot and Sera in Mira's previous slot.")


func _handoff_resume(root: Control) -> void:
	for spec: Array in [[0.3, "exit"], [1.3, "move"], [2.1, "enter"]]:
		await _open(root, "new_game")
		_reach_orders(root)
		_choose(root, 0)
		_start_briefing(root)
		_tick_game(_active(root), float(spec[0]))
		var before: Dictionary = _briefing_state(_active(root))
		var saved: Dictionary = _active(root).call("save_game")
		_key(root, KEY_ESCAPE)
		await _settle(root)
		_expect(_route(root) == "menu", "Esc must pause every phase of the authored handoff.")
		await _open(root, "game")
		var scene: Control = _active(root)
		_saved_story_equal(saved, scene.call("save_game"), "Resumed " + String(spec[1]) + " phase")
		var after: Dictionary = _briefing_state(scene)
		_expect(String(after["phase"]) == String(spec[1]) and after == before, "Resuming the handoff must reproduce the same phase, actors, colors, and positions.")
		_expect_handoff_gate(root)
		for index in 4:
			scene.call("_layout_interface")
			scene.call("_process", 0.5)
		_expect(_briefing_state(scene) == before, "Frozen redraws must not advance or restart a resumed handoff.")
		_tick_game(scene, 2.5 - float(spec[0]))
		_expect(_story(scene) == "analysis" and not bool(scene.call("_is_briefing_handoff_active")), "Each resumed phase must finish at Sera's analysis without replaying the exit.")


func _touch(root: Control, hit: bool) -> void:
	var scene: Control = _active(root)
	var point: Vector2 = scene.call("_fingertip_center", DESIGN_SIZE) if hit else Vector2(28, 400)
	scene.call("_route_mouse", point)


func _story_branch(root: Control, priority_index: int, approach_index: int) -> void:
	await _open(root, "new_game")
	var scene: Control = _active(root)
	var initial: Dictionary = scene.call("save_game")
	_expect(_story(scene) == "arrival" and String(initial["priority"]).is_empty() and String(initial["approach"]).is_empty() and not bool(initial["connected"]), "New game must start at arrival with no remembered orders or connection.")
	_expect(bool(scene.call("is_establishing")), "New game must introduce Forward Command with an establishing shot.")
	var effects: Dictionary = scene.get("_character_effects")
	for effect: Dictionary in effects.values():
		_expect(not bool(effect["enabled"]), "Ordinary play must begin without demo holograms.")
	_reach_orders(root)
	_expect_initial_cast(scene)
	root.get_viewport().gui_release_focus()
	_key(root, KEY_SPACE)
	_key(root, KEY_ENTER)
	_expect(_story(scene) == "orders", "Unfocused Space/Enter must not skip a mission choice.")
	_choose(root, priority_index, approach_index == 1)
	var reply: String = "escort" if priority_index == 0 else "beacon"
	var priority: String = "escort_priority" if priority_index == 0 else "beacon_priority"
	_expect(_story(scene) == reply and String((scene.call("save_game") as Dictionary)["priority"]) == priority, "A chosen order must apply once and remember its branch.")
	_finish_briefing(root)
	_next(root)
	_expect(_story(scene) == "link" and not bool(scene.get("_connected")), "The mission must require a fresh fingertip connection.")
	_freeze(scene)
	root.get_viewport().gui_release_focus()
	_key(root, KEY_SPACE)
	_key(root, KEY_ENTER)
	scene.call("_advance_dialogue")
	_touch(root, false)
	_expect(_story(scene) == "link" and not bool(scene.get("_connected")), "Misses and dialogue advances must not bypass the contact requirement.")
	_touch(root, true)
	_expect(_story(scene) == "link" and bool(scene.get("_connected")) and float(scene.get("_reaction")) > 0.0, "A fingertip hit must acknowledge the connection while holding its beat.")
	_next(root)
	_expect(_story(scene) == "approach", "Only confirmed contact may advance to the route choice.")
	_choose(root, approach_index, priority_index == 1)
	var destination: String = "overlook" if approach_index == 0 else "shore"
	var approach: String = "high_road" if approach_index == 0 else "shore_road"
	var location: String = "perimeter_overlook" if approach_index == 0 else "coastal_staging"
	var selected: Dictionary = scene.call("save_game")
	_expect(_story(scene) == destination and String(selected["approach"]) == approach and String(selected["location"]) == location, "The tactical route choice must select its matching mission beat and place.")
	_expect(bool(scene.call("is_establishing")), "A newly selected mission location must receive an establishing shot.")
	_finish_shot(root)
	_freeze(scene)
	_expect(not bool(scene.get("_briefing_cast_active")), "The first location shot must release the briefing cast restriction.")
	for actor: String in ["mira", "lena", "sera"]:
		_expect(_actor_sprite(scene, actor).visible, "After the briefing, the mission must restore actor " + actor)
	_next(root)
	_expect(_story(scene) == "deploy" and String(scene.get("_location_id")) == "coastal_staging", "Both approaches must converge at the coastal deployment.")
	_expect(bool(scene.call("is_establishing")) == (approach_index == 0), "Deployment must introduce the coast only when arriving from another location.")
	_finish_shot(root)
	_next(root)
	_expect(_story(scene) == "remembered", "The mission must report its remembered priority.")
	var line: String = (_button_or_label(scene, "_line") as Label).text.to_lower()
	_expect(line.contains("reserve is with the convoy") if priority_index == 0 else line.contains("repair team"), "The mission outcome must acknowledge the selected priority.")
	_next(root)
	_expect(_story(scene) == "end" and _button(scene, "_next_button").text == "Begin again", "The mission must end with an explicit replay action.")
	_next(root)
	var replay: Dictionary = scene.call("save_game")
	_expect(_story(scene) == "arrival" and String(replay["priority"]).is_empty() and String(replay["approach"]).is_empty() and not bool(replay["connected"]) and String(replay["location"]) == "forward_command", "Replay must reset the story, orders, connection, and location.")
	_finish_shot(root)
	_expect_initial_cast(scene)
	root.get_viewport().gui_release_focus()
	for keycode: Key in [KEY_1, KEY_2, KEY_3, KEY_4, KEY_L, KEY_T, KEY_E, KEY_H, KEY_G, KEY_B, KEY_N, KEY_R, KEY_P, KEY_F, KEY_C]:
		_key(root, keycode)
	_expect(_story(scene) == "arrival" and String(scene.get("_location_id")) == "forward_command", "Demo shortcuts must not alter ordinary gameplay.")


func _button_or_label(scene: Control, property: String) -> Control:
	return scene.get(property) as Control


func _menu_demo(root: Control, demo_id: String) -> void:
	if root.selected_game_id == "command_link":
		_click(root, _button(_active(root), "_lab_button"))
		await _settle(root)
		_expect(root.selected_game_id == "lab", "The mission menu must open the dedicated laboratory game.")
		var collections: Dictionary = _active(root).get("_collection_buttons")
		_click(root, collections["command_link"] as Button)
		await _settle(root)
	var menu: Control = _active(root)
	var buttons: Dictionary = menu.get("_demo_buttons")
	_click(root, buttons[demo_id] as Button)
	await _settle(root)
	_expect(_route(root) == "demos/" + demo_id, "Menu button must open demos/" + demo_id)


func _saved_story_equal(expected: Dictionary, actual: Dictionary, context: String) -> void:
	for field: String in ["story_id", "priority", "approach", "connected", "location", "briefing_cast_active", "briefing_handoff_started", "briefing_handoff_elapsed", "dialogue_camera"]:
		_expect(actual[field] == expected[field], context + " must preserve " + field)


func _resume_and_demos(root: Control) -> void:
	await _open(root, "new_game")
	# Check a held camera shot survives routing without starting from zero.
	var scene: Control = _active(root)
	scene.set("_capture_frozen", false)
	scene.call("_process", 1.1)
	scene.set("_capture_frozen", true)
	var shot_before: Dictionary = scene.call("save_establishing")
	await _open(root, "menu")
	await _open(root, "game")
	scene = _active(root)
	var shot_after: Dictionary = scene.call("save_establishing")
	_expect(bool(scene.call("is_establishing")) and absf(float(shot_after["elapsed"]) - float(shot_before["elapsed"])) < 0.1, "Resuming a location introduction must preserve its active camera timeline.")
	_reach_link(root, 1)
	for connected: bool in [false, true]:
		if connected:
			_touch(root, true)
		var link_before: Dictionary = _active(root).call("save_game")
		await _open(root, "menu")
		await _open(root, "game")
		_saved_story_equal(link_before, _active(root).call("save_game"), "Paused fingertip interaction")
		_expect(_story(_active(root)) == "link" and bool(_active(root).get("_connected")) == connected, "Contact resume must retain the exact acknowledgement gate.")
	_next(root)
	_choose(root, 1)
	_finish_shot(root)
	var expected_state: Dictionary = _active(root).call("save_game")
	_click(root, _button(_active(root), "_menu_button"))
	await _settle(root)
	_expect(_route(root) == "menu", "The game Menu button must open the menu.")
	for demo_id: String in DEMOS:
		await _menu_demo(root, demo_id)
		if _route(root) != "demos/" + demo_id:
			return
		var demo: Control = _active(root)
		_check_demo(root, demo, demo_id)
		_button(demo, "_demos_button").grab_focus()
		_key(root, KEY_ENTER)
		await _settle(root)
		_expect(root.selected_game_id == "lab" and _route(root) == "command_link", "Demo Back must return to the laboratory collection: " + demo_id)
		await _menu_demo(root, demo_id)
		_click(root, _button(_active(root), "_play_button"))
		await _settle(root)
		_expect(root.selected_game_id == "command_link" and _route(root) == "game", "Demo Play must return to the original game: " + demo_id)
		_saved_story_equal(expected_state, _active(root).call("save_game"), "Demo navigation")
		_key(root, KEY_ESCAPE)
		await _settle(root)
		_expect(_route(root) == "menu", "Esc from game must pause into menu.")
	_click(root, _button(_active(root), "_play_button"))
	await _settle(root)
	_expect(_route(root) == "game" and _story(_active(root)) == "shore", "Menu Resume must preserve the paused mission.")
	_key(root, KEY_ESCAPE)
	await _settle(root)
	_click(root, _button(_active(root), "_new_button"))
	await _settle(root)
	var reset: Dictionary = _active(root).call("save_game")
	_expect(_route(root) == "game" and _story(_active(root)) == "arrival" and String(reset["priority"]).is_empty() and String(reset["approach"]).is_empty() and not bool(reset["connected"]), "Menu New game must discard saved mission state.")


func _demo_state(scene: Control) -> Dictionary:
	if scene.has_method("_frame_speaker"):
		return {"dialogue_camera": scene.call("save_dialogue_camera"), "line": scene.get("_demo_line_index"), "requested_zoom": scene.get("_requested_zoom"), "duration": scene.get("_camera_duration_seconds"), "_location_id": scene.get("_location_id")}
	if scene.has_method("_replay_shot"):
		return {"establishing_shot": scene.call("save_establishing"), "settings": (scene.get("_demo_settings") as Dictionary).duplicate(true), "_location_id": scene.get("_location_id")}
	if scene.has_method("_start_handoff"):
		var controller: RefCounted = scene.get("_cast_transition")
		return {"cast_transition": controller.call("get_state"), "_location_id": scene.get("_location_id")}
	var result := {}
	for field: String in ["_mode", "_dialogue_index", "_manual_closed", "_natural_blink", "_show_hotspot", "_effect_target", "_character_effects", "_location_id", "actor_focus_preset", "manpu_animation_preset", "_manpu_target_index", "character_exit_preset", "_exit_target"]:
		result[field] = scene.get(field)
	var exit_controller: RefCounted = scene.get("_character_exit")
	result["character_exit"] = exit_controller.call("get_state")
	return result.duplicate(true)


func _check_demo(root: Control, demo: Control, demo_id: String) -> void:
	if demo_id == "dialogue_camera":
		_check_dialogue_camera_route(root, demo)
		return
	if demo_id == "establishing_shot":
		_check_establishing_route(root, demo)
		return
	if demo_id == "cast_transition":
		_check_cast_route(root, demo)
		return
	_expect(String(demo.get("_mode")) == MODES[demo_id], "Wrong opening presentation for " + demo_id)
	var opening: Dictionary = _demo_state(demo)
	var allowed := {"characters": [KEY_B, KEY_N], "contact": [KEY_H], "actor_focus": [KEY_P, KEY_F], "manpu": [KEY_G, KEY_P, KEY_T, KEY_F], "locations": [KEY_L, KEY_P], "hologram": [KEY_T, KEY_E], "character_exit": [KEY_T, KEY_P, KEY_E, KEY_S]}
	var allowed_keys: Array = allowed.get(demo_id, [])
	root.get_viewport().gui_release_focus()
	for keycode: Key in [KEY_1, KEY_2, KEY_3, KEY_4, KEY_B, KEY_N, KEY_H, KEY_G, KEY_L, KEY_P, KEY_F, KEY_T, KEY_E, KEY_S]:
		if not allowed_keys.has(keycode):
			_key(root, keycode)
	_expect(_demo_state(demo) == opening, "Unrelated shortcuts changed the " + demo_id + " demo.")
	var effects: Dictionary = demo.get("_character_effects")
	for actor: String in effects:
		_expect(bool(effects[actor]["enabled"]) == (demo_id == "hologram" and actor == "sera"), "Effect isolation failed in " + demo_id)
	match demo_id:
		"characters":
			_key(root, KEY_B)
			_expect(bool(demo.get("_manual_closed")), "Characters B must select the closed-eye frame.")
		"contact":
			_key(root, KEY_H)
			demo.call("_route_mouse", demo.call("_fingertip_center", DESIGN_SIZE))
			_expect(bool(demo.get("_connected")) and bool(demo.get("_show_hotspot")), "Contact controls must target the actual fingertip.")
		"dialogue":
			_key(root, KEY_SPACE)
			_expect(int(demo.get("_dialogue_index")) == 1, "Dialogue Space must advance once.")
		"actor_focus":
			_key(root, KEY_P)
			_expect(String(demo.get("actor_focus_preset")) == "scale_pulse", "Actor Focus P must select the next data preset.")
			var focus: RefCounted = demo.get("_actor_focus")
			focus.call("advance", 0.1)
			_key(root, KEY_F)
			_expect(is_zero_approx(float(focus.get("elapsed"))), "Actor Focus F must replay the current cue.")
			_key(root, KEY_SPACE)
			_expect(int(demo.get("_dialogue_index")) == 1 and String(focus.get("focus_id")) == "lena", "Actor Focus Next must transfer the cue to the next speaker.")
		"manpu":
			_key(root, KEY_G)
			_expect(String(demo.get("_mode")) == "manpu_gallery", "Manpu G must open the gallery.")
			_key(root, KEY_G)
		"locations":
			_key(root, KEY_L)
			_expect(demo.get("_location_id") != opening["_location_id"], "Locations L must switch places.")
		"hologram":
			_key(root, KEY_T)
			_key(root, KEY_E)
			var changed: Dictionary = demo.get("_character_effects")
			_expect(String(demo.get("_effect_target")) == "mira" and bool(changed["mira"]["enabled"]) and bool(changed["sera"]["enabled"]), "Hologram target and toggle must change Mira independently.")
		"character_exit":
			var exit_controller: RefCounted = demo.get("_character_exit")
			_key(root, KEY_T)
			_key(root, KEY_E)
			_expect(String(demo.get("_exit_target")) == "mira" and bool(exit_controller.call("is_exiting", "mira")) and not bool(exit_controller.call("is_exiting", "sera")), "Exit target and E must affect Mira independently.")
			_key(root, KEY_S)
			_expect(bool(exit_controller.call("is_visible", "mira")) and not bool(exit_controller.call("is_exiting", "mira")), "Show must cancel the selected actor's exit.")
			_key(root, KEY_P)
			_expect(String(demo.get("character_exit_preset")) == "opacity_fade", "P must select the comparison exit preset.")
	_key(root, KEY_R)
	var reset: Dictionary = _demo_state(demo)
	reset.erase("_location_id")
	opening.erase("_location_id")
	_expect(reset == opening and _route(root) == "demos/" + demo_id, "Reset must restore the same demo's initial state: " + demo_id)


func _check_cast_route(root: Control, scene: Control) -> void:
	var controller: RefCounted = scene.get("_cast_transition")
	var before: Dictionary = controller.call("get_state")
	root.get_viewport().gui_release_focus()
	for keycode: Key in [KEY_1, KEY_2, KEY_3, KEY_4, KEY_B, KEY_N, KEY_H, KEY_G, KEY_L, KEY_T, KEY_F, KEY_S]:
		_key(root, keycode)
	_expect(controller.call("get_state") == before, "Unrelated shortcuts must not alter the cast-transition route.")
	var settings: Dictionary = controller.call("get_settings")
	_key(root, KEY_P)
	_expect(controller.call("get_settings") != settings, "Cast P must change its presentation pattern.")
	settings = controller.call("get_settings")
	_key(root, KEY_C)
	_expect(controller.call("get_settings") != settings, "Cast C must change its motion curve.")
	_key(root, KEY_E)
	_expect(bool(controller.call("is_busy")), "Cast E must start a handoff.")
	_key(root, KEY_R)
	_expect(not bool(controller.call("is_busy")) and _route(root) == "demos/cast_transition", "Cast R must reset its sequence without leaving the route.")
	var first: Dictionary = controller.call("sample", "mira")
	var second: Dictionary = controller.call("sample", "lena")
	var third: Dictionary = controller.call("sample", "sera")
	_expect(bool(first["visible"]) and bool(second["visible"]) and not bool(third["visible"]), "Cast reset must restore exactly the initial two actors.")


func _check_establishing_route(root: Control, scene: Control) -> void:
	var opening: Dictionary = _demo_state(scene)
	_expect(bool(scene.call("is_establishing")) and String(scene.get("_location_id")) == "coastal_staging", "The establishing demo must introduce coastal staging.")
	root.get_viewport().gui_release_focus()
	for keycode: Key in [KEY_1, KEY_2, KEY_3, KEY_4, KEY_B, KEY_N, KEY_H, KEY_G, KEY_P, KEY_T, KEY_S, KEY_C, KEY_F]:
		_key(root, keycode)
	_expect(_demo_state(scene) == opening, "Unrelated shortcuts and active flare tuning must not alter a running shot.")
	var sliders: Dictionary = scene.get("_setting_sliders")
	for slider: HSlider in sliders.values():
		_expect(not slider.editable, "Establishing settings must be locked during the shot.")
	_key(root, KEY_SPACE)
	_expect(not bool(scene.call("is_establishing")), "Establishing Space must skip the active camera view.")
	var settings: Dictionary = (scene.get("_demo_settings") as Dictionary).duplicate(true)
	_key(root, KEY_F)
	_expect(bool((scene.get("_demo_settings") as Dictionary)["flare_enabled"]) != bool(settings["flare_enabled"]), "F must change the next shot's flare toggle while idle.")
	var slider: HSlider = sliders["duration_seconds"] as HSlider
	scene.call("_route_mouse", slider.get_global_rect().position + Vector2(slider.size.x * 0.9, slider.size.y * 0.5))
	_expect(float((scene.get("_demo_settings") as Dictionary)["duration_seconds"]) != float(settings["duration_seconds"]), "A native slider click must retune the next establishing shot.")
	_key(root, KEY_E)
	var active: Dictionary = scene.call("save_establishing")
	_expect(bool(scene.call("is_establishing")) and active["active_settings"] == scene.get("_demo_settings"), "Replay must snapshot the edited shot settings.")
	_key(root, KEY_L)
	_expect(String(scene.get("_location_id")) != "coastal_staging" and bool(scene.call("is_establishing")), "L must introduce the next configured location.")
	_key(root, KEY_R)
	_expect(_route(root) == "demos/establishing_shot" and String(scene.get("_location_id")) == "coastal_staging" and scene.get("_demo_settings") == opening["settings"] and bool(scene.call("is_establishing")), "Reset must restore and replay this demo's opening profile.")


func _check_dialogue_camera_route(root: Control, scene: Control) -> void:
	var opening: Dictionary = _demo_state(scene)
	root.get_viewport().gui_release_focus()
	for keycode: Key in [KEY_1, KEY_2, KEY_3, KEY_4, KEY_B, KEY_N, KEY_H, KEY_G, KEY_P, KEY_E, KEY_F, KEY_S]:
		_key(root, keycode)
	_expect(_demo_state(scene) == opening, "Unrelated shortcuts must not alter the dialogue camera demo.")
	_key(root, KEY_C)
	_settle_dialogue_camera(scene)
	var held: Dictionary = scene.call("save_dialogue_camera")
	_expect(String(held["focus_id"]) == "mira" and is_equal_approx(float((scene.call("dialogue_camera_sample") as Dictionary)["zoom"]), 4.0), "C must explicitly frame the current speaker at the requested zoom.")
	_key(root, KEY_SPACE)
	_expect(int(scene.get("_demo_line_index")) == 1 and scene.call("save_dialogue_camera") == held, "Next line must preserve the held camera cue.")
	_key(root, KEY_T)
	_expect(int(scene.get("_demo_line_index")) == 3 and scene.call("save_dialogue_camera") == held, "Selecting another speaker must not move the camera automatically.")
	var zoom: HSlider = scene.get("_zoom_slider") as HSlider
	scene.call("_route_mouse", zoom.get_global_rect().position + Vector2(zoom.size.x * 0.4, zoom.size.y * 0.5))
	_expect(float(scene.get("_requested_zoom")) < 4.0 and scene.call("save_dialogue_camera") == held, "The zoom slider must configure the next explicit shot without changing a held shot.")
	_key(root, KEY_C)
	_expect(String((scene.call("save_dialogue_camera") as Dictionary)["focus_id"]) == "lena" and bool(scene.call("is_dialogue_camera_moving")), "A new C cue must explicitly retarget the selected speaker.")
	_key(root, KEY_W)
	_settle_dialogue_camera(scene)
	_expect(is_equal_approx(float((scene.call("dialogue_camera_sample") as Dictionary)["zoom"]), 1.0), "W must return the scene to wide.")
	_key(root, KEY_L)
	_expect(String(scene.get("_location_id")) != String(opening["_location_id"]) and is_equal_approx(float((scene.call("dialogue_camera_sample") as Dictionary)["zoom"]), 1.0), "Changing the demo location must begin with its wide framing.")
	_key(root, KEY_R)
	_expect(_demo_state(scene) == opening and _route(root) == "demos/dialogue_camera", "Reset must restore the same demo's opening speaker, settings, place, and wide camera.")


func _scaled_input(root: Control) -> void:
	var original_size: Vector2i = root.get_window().size
	for shape: Vector2i in [Vector2i(640, 450), Vector2i(1280, 580), Vector2i(1920, 1350)]:
		root.get_window().size = shape
		await _open(root, "new_game")
		_expect(root.size.is_equal_approx(DESIGN_SIZE), "Routes must retain the logical 1280x900 canvas.")
		_expect(root.get_window().content_scale_mode == Window.CONTENT_SCALE_MODE_CANVAS_ITEMS, "Routes must render canvas items at output resolution.")
		var transform: Transform2D = root.get_viewport().get_final_transform()
		var expected_scale: float = minf(shape.x / DESIGN_SIZE.x, shape.y / DESIGN_SIZE.y)
		var extent: Vector2 = transform.basis_xform(DESIGN_SIZE)
		_expect(absf(extent.x - DESIGN_SIZE.x * expected_scale) <= 1.0 and absf(extent.y - DESIGN_SIZE.y * expected_scale) <= 1.0, "Routes must retain uniform native window scaling within output pixel rounding.")
		_reach_orders(root)
		_choose(root, 0)
		_expect(_story(_active(root)) == "escort", "Physical window input must reach the visible choice at %s." % shape)
	root.get_window().size = original_size
	await _settle(root)


func _capture_routes(root: Control, folder: String) -> void:
	var directory_error: Error = DirAccess.make_dir_recursive_absolute(folder)
	if directory_error != OK:
		_errors.append("Could not create route capture directory.")
		return
	await _open(root, "new_game")
	_advance_capture_shot(_active(root))
	await _capture(root, folder, "game_establishing")
	_finish_shot(root)
	await _capture(root, folder, "game_arrival")
	_next(root)
	_settle_dialogue_camera(_active(root))
	await _capture(root, folder, "game_briefing_closeup")
	_next(root)
	await _capture(root, folder, "game_briefing_hold")
	_next(root)
	_next(root)
	_settle_dialogue_camera(_active(root))
	await _capture(root, folder, "game_orders")
	_choose(root, 0)
	await _capture(root, folder, "game_escort")
	await _open(root, "new_game")
	_reach_orders(root)
	_choose(root, 1)
	await _capture(root, folder, "game_beacon")
	_start_briefing(root)
	var previous_time := 0.0
	for frame: Array in [["game_handoff_color", 0.3], ["game_handoff_matte", 0.495], ["game_handoff_move", 1.3], ["game_handoff_enter", 2.1], ["game_analysis", 2.5]]:
		_tick_game(_active(root), float(frame[1]) - previous_time)
		previous_time = float(frame[1])
		await _capture(root, folder, String(frame[0]))
	_next(root)
	_freeze(_active(root))
	await _capture(root, folder, "game_link")
	_touch(root, true)
	_active(root).set("_reaction", STAGE_SCRIPT.REACTION_SECONDS - 0.2)
	await _capture(root, folder, "game_link_connected")
	_next(root)
	await _capture(root, folder, "game_approach")
	_choose(root, 0)
	_finish_shot(root)
	await _capture(root, folder, "game_overlook")
	_next(root)
	_advance_capture_shot(_active(root))
	await _capture(root, folder, "game_coastal_establishing")
	_finish_shot(root)
	_next(root)
	_next(root)
	await _capture(root, folder, "game_end")
	await _open(root, "menu")
	await _capture(root, folder, "menu")
	for demo_id: String in DEMOS:
		await _open(root, "demos/" + demo_id)
		await _capture(root, folder, "demo_" + demo_id)
		if demo_id == "manpu":
			_key(root, KEY_G)
			await _capture(root, folder, "demo_manpu_gallery")


func _advance_capture_shot(scene: Control) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", 1.2)
	scene.set("_capture_frozen", true)


func _capture(root: Control, folder: String, name: String) -> void:
	var scene: Control = _active(root)
	root.get_viewport().gui_release_focus()
	if root.get_viewport().gui_get_hovered_control() != null:
		root.get_viewport().notify_mouse_exited()
	if scene.has_method("_update_character_layers"):
		_freeze(scene)
		scene.set("_capturing", true)
		scene.set("_natural_blink", false)
		scene.set("_blink_remaining", 0.0)
		scene.set("_elapsed", 1.0)
		scene.set("_pointer", Vector2(-1000, -1000))
		if not bool(scene.call("is_establishing")):
			scene.set("_location_title_elapsed", 1.0 if name in ["game_arrival", "game_overlook", "demo_locations"] else 3.7)
		scene.call("_update_location_title")
		scene.call("_update_interface")
	await root.get_tree().process_frame
	scene.queue_redraw()
	for index in 4:
		RenderingServer.force_draw(false)
	var picture: Image = root.get_viewport().get_texture().get_image()
	var output: String = folder.path_join(name + ".png")
	_expect(picture.save_png(output) == OK, "Could not save " + output)
	var output_transform: Transform2D = root.get_viewport().get_final_transform()
	var output_extent: Vector2 = output_transform.basis_xform(DESIGN_SIZE)
	_expect(picture.get_size() == Vector2i(roundi(output_extent.x), roundi(output_extent.y)), "Route captures must render at the output content resolution.")
	var metadata := {"state": name, "route": _route(root), "capture_space": "render_target", "geometry_space": "logical_canvas", "viewport": [1280, 900], "render_size": [picture.get_width(), picture.get_height()],
		"window_size": [root.get_window().size.x, root.get_window().size.y],
		"output_rect": [output_transform.origin.x, output_transform.origin.y, output_extent.x, output_extent.y],
		"output_scale": [output_transform.x.x, output_transform.y.y], "stretch_mode": "canvas_items", "stretch_aspect": "keep",
		"manpu_actor_height_ratio": STAGE_SCRIPT.MANPU_ACTOR_HEIGHT_RATIO}
	if scene.has_method("save_game"):
		metadata["game_state"] = scene.call("save_game")
		metadata["briefing_cast"] = _briefing_state(scene)
		metadata["dialogue_camera"] = scene.call("save_dialogue_camera")
		metadata["actors"] = {}
		for actor: String in ["mira", "lena", "sera"]:
			var sprite: TextureRect = _actor_sprite(scene, actor)
			var rect: Rect2 = sprite.get_rect()
			metadata["actors"][actor] = {"visible": sprite.visible, "rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y], "modulate": [sprite.modulate.r, sprite.modulate.g, sprite.modulate.b, sprite.modulate.a]}
	elif scene.has_method("_update_character_layers"):
		metadata["demo_state"] = _demo_state(scene)
	var record: FileAccess = FileAccess.open(folder.path_join(name + ".json"), FileAccess.WRITE)
	if record == null:
		_errors.append("Could not write capture metadata for " + name)
	else:
		record.store_string(JSON.stringify(metadata, "\t"))
	_captures.append(name)
	print("Route capture: " + ProjectSettings.globalize_path(output))
