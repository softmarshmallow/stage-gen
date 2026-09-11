extends "res://qa/afterlight_ensemble_checks.gd"

## Focused native checks for horizontal actor approach and host continuity.
const APPROACH_OUTPUT := "res://qa/quick-approach"
const APPROACH_BEAT := "the_useful_kind"
var _approach_captures: Array[Dictionary] = []
var _approach_metrics: Array[Dictionary] = []


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Quick Approach integration captures require a native renderer.")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(APPROACH_OUTPUT)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "bishoujo_afterlight", "Use --game bishoujo_afterlight.")
	for factor in [1, 2]:
		root.size = Vector2i(1280, 900) * factor
		await _story_approach(factor)
		await _laboratory_approach(factor)
	var sources := {}
	for source: String in ["res://games/bishoujo_afterlight/cast_stage.gd", "res://games/bishoujo_afterlight/root.gd", "res://games/bishoujo_afterlight/story.gd", "res://games/bishoujo_afterlight/story_beats.gd", "res://games/presentation_lab/afterlight/actor_motion_study.gd"]:
		sources[source] = FileAccess.get_sha256(source)
	var output := FileAccess.open(APPROACH_OUTPUT.path_join("manifest.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"sources": sources, "captures": _approach_captures, "metrics": _approach_metrics, "errors": _errors}, "\t"))
	await _dispose_app()
	for issue: String in _errors:
		printerr("FAIL Quick Approach integration: " + issue)
	if _errors.is_empty():
		print("PASS Quick Approach integration: native 1x/2x horizontal story blocking, stationary partner, unchanged Y/size/alpha, attached manpu/camera framing, held endpoint, pause/language/Lab replay, early cancellation and both laboratory directions")
	quit(0 if _errors.is_empty() else 1)


func _seek_approach() -> Control:
	_expect(_app.open_route("new_game"), "A fresh episode must be reachable.")
	await _settle()
	var game := _active()
	game.set_language("ko")
	_expect(game.beats.size() == EPISODE_BEAT_COUNT, "Quick Approach must use the current authored episode.")
	for iteration in game.beats.size():
		if str(game.current_beat()["id"]) == APPROACH_BEAT:
			return game
		game._process(6.0)
		if _fulfill_contact_gate(game): continue
		if game.current_beat()["type"] == "choice":
			game._choices[str(game.current_beat()["id"])] = "help_first"
		game._continue_story()
	_expect(false, "The existing Yuzu/Sena exchange must remain reachable.")
	return game


func _story_approach(factor: int) -> void:
	var game := await _seek_approach()
	var cue: Dictionary = game.current_beat()["quick_approach"]
	var settings: Dictionary = game.content["quick_approach"].duplicate(true)
	settings.merge(cue.get("settings", {}), true)
	var delay := float(cue["delay_seconds"])
	var duration := float(settings["duration_seconds"])
	var stage: Control = game._cast
	_expect(stage.visible_ids() == ["yuzu", "sena"], "Quick Approach must follow the settled two-character handoff.")
	var initial_mover := _sprite_snapshot(stage._sprites["yuzu"])
	var initial_partner := _sprite_snapshot(stage._sprites["sena"])
	var initial_world: Transform2D = game._world_transform()
	_expect(is_equal_approx(stage.get_actor_rect("yuzu").get_center().x, 410.0) and is_equal_approx(stage.get_actor_rect("sena").get_center().x, 890.0), "The authored pair must begin at the prior handoff's 410/890 centers.")
	game._process(delay - 0.01)
	_expect(stage.movement_state().is_empty() and _same(initial_mover, _sprite_snapshot(stage._sprites["yuzu"])), "The actor must wait for the authored approach delay.")
	await _approach_frame("story-before-" + str(factor), stage, game)
	game._process(0.01 + duration * 0.5)
	var middle: Dictionary = stage.movement_state()
	_expect(game._load_errors.is_empty(), "The story approach must initialize without errors: " + str(game._load_errors))
	_expect(bool(middle["active"]) and float(middle["center_x"]) > 410.0 and float(middle["center_x"]) < 610.0, "Yuzu must move toward Sena during the quick approach.")
	_assert_horizontal(stage, "yuzu", "sena", initial_mover, initial_partner, "story midpoint")
	_expect(initial_world.is_equal_approx(game._world_transform()), "Approach must not move or zoom the camera.")
	await _approach_frame("story-midpoint-" + str(factor), stage, game)
	_check_frozen_camera_composition(stage, "yuzu", "yuzu:sweat_drop")
	game._render()
	await _language_and_detour(game, APPROACH_BEAT)
	game = _active()
	stage = game._cast
	game._process(duration * 0.5 + 0.01)
	var settled: Dictionary = stage.movement_state()
	_expect(not bool(settled["active"]) and is_equal_approx(float(settled["center_x"]), 610.0), "Yuzu must settle exactly at the captured 610 destination.")
	_assert_horizontal(stage, "yuzu", "sena", initial_mover, initial_partner, "story endpoint")
	_expect(is_equal_approx(absf(stage.get_actor_rect("sena").get_center().x - stage.get_actor_rect("yuzu").get_center().x), float(settings["stop_distance"])), "The held destination must preserve the authored center-to-center stopping distance.")
	await _approach_frame("story-settled-" + str(factor), stage, game)
	var held := _sprite_snapshot(stage._sprites["yuzu"])
	game._process(3.0)
	_expect(str(game.current_beat()["id"]) == APPROACH_BEAT and _same(held, _sprite_snapshot(stage._sprites["yuzu"])), "The approached position must hold for explicit story continuation.")
	game._continue_story()
	_expect(str(game.current_beat()["id"]) == "reading_room" and stage.visible_ids().is_empty() and stage.movement_state().is_empty(), "The next establishing shot must clear the previous pair and movement state.")
	game = await _seek_approach()
	game._process(delay + duration * 0.4)
	_expect(bool(game._cast.movement_state().get("active", false)), "The interruption check must begin during an active approach.")
	game._continue_story()
	game._process(0.4)
	_expect(game._cast.movement_state().is_empty() and game._cast.visible_ids().is_empty(), "Early continuation must cancel the movement and leave no hidden actor drift.")
	_approach_metrics.append({"check": "story approach", "factor": factor, "delay_seconds": delay, "duration_seconds": duration, "start_centers": [410, 890], "midpoint": middle, "settled": settled})


func _world_snapshot(game: Control) -> Dictionary:
	var result := super._world_snapshot(game)
	result["actor_movement"] = game._cast.movement_state()
	return result


func _sprite_snapshot(sprite: TextureRect) -> Dictionary:
	return {"position": sprite.position, "size": sprite.size, "scale": sprite.scale,
		"rotation": sprite.rotation, "modulate": sprite.modulate, "self_modulate": sprite.self_modulate,
		"material": sprite.material, "visible": sprite.visible}


func _assert_horizontal(stage: Control, mover: String, partner: String, initial_mover: Dictionary, initial_partner: Dictionary, context: String) -> void:
	var current := _sprite_snapshot(stage._sprites[mover])
	_expect(is_equal_approx((current["position"] as Vector2).y, (initial_mover["position"] as Vector2).y), "Horizontal approach must preserve actor Y: " + context)
	for key: String in ["size", "scale", "rotation", "modulate", "self_modulate", "material", "visible"]:
		_expect(_same(current[key], initial_mover[key]), "Horizontal approach must preserve " + key + ": " + context)
	_expect(_same(initial_partner, _sprite_snapshot(stage._sprites[partner])), "The approached partner must remain stationary and unchanged: " + context)


func _check_frozen_camera_composition(stage: Control, actor_id: String, mark_key: String) -> void:
	var actor_before: Rect2 = stage._sprites[actor_id].get_rect()
	_expect(stage._mark_nodes.has(mark_key), "The moving actor must retain its prepared story manpu.")
	if not stage._mark_nodes.has(mark_key):
		return
	var mark_before: Rect2 = stage._mark_nodes[mark_key].get_rect()
	var frozen: Dictionary = stage.movement_state()
	var camera := Transform2D(Vector2(1.3, 0), Vector2(0, 1.3), Vector2(-150, -75))
	stage.present(camera)
	_expect(stage._sprites[actor_id].get_rect().is_equal_approx(camera * actor_before), "The already-posed moving actor must receive camera framing exactly once.")
	_expect(stage._mark_nodes[mark_key].get_rect().is_equal_approx(camera * mark_before), "Its attached manpu must receive the same final camera transform.")
	_expect(_same(frozen, stage.movement_state()), "Presenting the moving actor must not advance or restart its motion.")
	stage.present(Transform2D.IDENTITY)


func _approach_frame(label: String, stage: Control, game: Control = null) -> void:
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Approach captures must retain native window resolution.")
	var path := APPROACH_OUTPUT.path_join(label + ".png")
	_expect(picture.save_png(path) == OK, "Approach capture must save: " + label)
	var sprites := {}
	for actor_id: String in stage.visible_ids():
		sprites[actor_id] = {"rect": stage._sprites[actor_id].get_rect(), "modulate": stage._sprites[actor_id].modulate}
	var metadata := {"file": path, "sha256": FileAccess.get_sha256(path), "window": [picture.get_width(), picture.get_height()], "movement": stage.movement_state(), "sprites": sprites}
	if game != null:
		metadata["beat"] = game.current_beat()["id"]
		metadata["elapsed"] = game._elapsed
		metadata["world"] = game._world_transform()
	_approach_captures.append(metadata)


func _click_approach(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The intended motion-study control must be visible and enabled.")
	if button == null or not button.is_visible_in_tree() or button.disabled:
		return
	var point := root.get_final_transform() * button.get_global_rect().get_center()
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.global_position = point
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _freeze_route(node: Node) -> void:
	super._freeze_route(node)
	if node.has_method("motion_state"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _laboratory_approach(factor: int) -> void:
	_expect(_app.open_route("game:presentation_lab/actor_motion_study"), "Quick Approach must be available in the existing actor-motion study.")
	await _settle()
	var lab := _active()
	lab.set_language("ko")
	_expect(lab._load_errors.is_empty(), "The expanded motion study must initialize without missing presets or labels: " + str(lab._load_errors))
	await _click_approach(lab._guest_buttons["yuzu"])
	await _click_approach(lab._mode_buttons["quick_approach"])
	for direction: String in ["from-left", "from-right"]:
		if direction == "from-right":
			await _click_approach(lab._approach_direction_button)
			await _click_approach(lab._approach_curve_button)
			_expect(lab._approach_settings["curve"] == "linear", "The curve button must select a different interpolation profile.")
			await _step_slider(lab._approach_duration_slider)
			await _step_slider(lab._approach_gap_slider)
			_expect(float(lab._approach_settings["duration_seconds"]) > 0.32 and float(lab._approach_settings["stop_distance"]) > 280.0, "Duration and spacing controls must update the study's next approach.")
			_expect(lab._cast_layer.movement_state().is_empty() and not lab._playing, "Parameter changes must reset the previous held movement for a clean replay.")
		var stage: Control = lab._cast_layer
		var mover := str(lab._guest_id)
		var partner := str(lab._approach_partner())
		var original := _sprite_snapshot(stage._sprites[mover])
		var observer := _sprite_snapshot(stage._sprites[partner])
		var start_x: float = stage.get_actor_rect(mover).get_center().x
		await _click_approach(lab._play_button)
		var duration := float(lab.motion_state()["duration"])
		lab._process(duration * 0.5)
		_assert_horizontal(stage, mover, partner, original, observer, "laboratory " + direction)
		var middle: Dictionary = stage.movement_state()
		_expect(float(middle["center_x"]) > start_x if direction == "from-left" else float(middle["center_x"]) < start_x, "The direction control must reverse which side the actor approaches from.")
		await _approach_frame("lab-" + direction + "-midpoint-" + str(factor), stage)
		await _click_approach(lab._pause_button)
		var frozen_motion: Dictionary = lab.motion_state()
		var frozen_cast: Dictionary = stage.movement_state()
		lab._process(1.0)
		lab.set_language("en")
		_expect(_same(frozen_motion, lab.motion_state()) and _same(frozen_cast, stage.movement_state()), "Pausing and changing language must preserve an active laboratory approach.")
		await _click_approach(lab._pause_button)
		lab._process(duration * 0.5 + 0.01)
		_assert_horizontal(stage, mover, partner, original, observer, "laboratory held " + direction)
		_expect(not bool(stage.movement_state()["active"]) and not lab._playing, "Laboratory approach must finish and hold both actors visibly.")
		_expect(is_equal_approx(absf(stage.get_actor_rect(mover).get_center().x - stage.get_actor_rect(partner).get_center().x), float(lab._approach_settings["stop_distance"])), "Both approach directions must stop at the selected center spacing.")
		if direction == "from-right":
			await _approach_frame("lab-from-right-settled-en-" + str(factor), stage)
		_approach_metrics.append({"check": "laboratory approach", "factor": factor, "direction": direction, "midpoint": middle, "settled": stage.movement_state()})
		lab.set_language("ko")
	await _click_approach(lab._reset_button)
	_expect(lab._cast_layer.movement_state().is_empty() and not lab._playing and not lab._paused, "Reset must restore the original pair and clear movement state.")
	# Existing modes remain part of this route, with their original actor count.
	for mode: String in ["walk_away", "walk_away_right", "restless_bounce"]:
		await _click_approach(lab._mode_buttons[mode])
		_expect(lab._cast_layer.visible_ids() == [lab._guest_id] and not lab._approach_direction_button.visible, "Existing modes must keep their solo staging and hide approach-only controls.")
		await _click_approach(lab._play_button)
		lab._process(float(lab.motion_state()["duration"]) + 0.01)
		_expect(not lab._playing and lab._load_errors.is_empty(), "Existing actor motion must still complete after selecting Quick Approach: " + mode)
	_expect(_app.open_route("game:bishoujo_afterlight"), "The motion study must return to the saved episode.")
	await _settle()


func _step_slider(slider: HSlider) -> void:
	slider.grab_focus()
	for pressed: bool in [true, false]:
		var key := InputEventKey.new()
		key.keycode = KEY_RIGHT
		key.pressed = pressed
		root.push_input(key, false)
	await _settle()
