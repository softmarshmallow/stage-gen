extends "res://tests/afterlight_ensemble_checks.gd"

## Native group-pan proof: background/UI stay put while actor-local behavior
## continues beneath an independently sampled layer transform.
const PAN_OUTPUT := "res://tests/cast-pan"
const FIRST_PAN_BEAT := "riko_on_the_glass"
const BACKGROUND_REGION := Rect2i(0, 200, 1280, 410)
var _pan_captures: Array[Dictionary] = []
var _pan_metrics: Array[Dictionary] = []


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Cast Pan integration captures require a native renderer.")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(PAN_OUTPUT)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "afterlight", "Use --game afterlight.")
	for factor in [1, 2]:
		root.size = Vector2i(1280, 900) * factor
		await _story_pan(factor)
		await _laboratory_pan(factor)
	var sources := {}
	for source: String in ["res://addons/game_presentation/motion/layer_pan.gd", "res://cast_stage.gd", "res://root.gd", "res://story.gd", "res://story_beats.gd", "res://lab/cast_pan_study.gd"]:
		sources[source] = FileAccess.get_sha256(source)
	var output := FileAccess.open(PAN_OUTPUT.path_join("manifest.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"sources": sources, "captures": _pan_captures, "metrics": _pan_metrics, "errors": _errors}, "\t"))
	await _dispose_app()
	for issue: String in _errors:
		printerr("FAIL Cast Pan integration: " + issue)
	if _errors.is_empty():
		print("PASS Cast Pan integration: native 1x/2x fixed-background pixels, common cast/manpu translation, unchanged local blocking/scale, wide-camera actor centering, retarget/hold, pause/language/Lab replay, scene cleanup and independent Quick Approach composition")
	quit(0 if _errors.is_empty() else 1)


func _seek_pan() -> Control:
	_expect(_app.open_route("new_game"), "A fresh episode must be reachable.")
	await _settle()
	var game := _active()
	game.set_language("ko")
	_expect(game.beats.size() == EPISODE_BEAT_COUNT, "Cast Pan must use the current authored episode.")
	for iteration in game.beats.size():
		if str(game.current_beat()["id"]) == FIRST_PAN_BEAT:
			return game
		game._process(6.0)
		if _fulfill_contact_gate(game): continue
		if game.current_beat()["type"] == "choice":
			game._choices[str(game.current_beat()["id"])] = "help_first"
		game._continue_story()
	_expect(false, "The physical relay setup must remain reachable.")
	return game


func _story_pan(factor: int) -> void:
	var game := await _seek_pan()
	var delay := float(game.current_beat()["cast_pan"]["delay_seconds"])
	var duration := float(game.content["cast_pan"]["duration_seconds"])
	var stage: Control = game._cast
	var local := _local_rects(stage)
	var world: Transform2D = game._world_transform()
	_expect(world.is_equal_approx(Transform2D.IDENTITY), "The physical conversation must retain the wide, unpanned world camera.")
	var background := await _background_pixels(stage, factor)
	game._process(delay - 0.01)
	_expect(game._cast_pan.sample_transform().is_equal_approx(Transform2D.IDENTITY), "The first cast pan must wait for its authored delay.")
	await _pan_frame("story-before-" + str(factor), game._cast_pan, stage, game)
	game._process(0.01 + duration * 0.5)
	_expect(game._load_errors.is_empty() and game._cast_pan.is_moving(), "The first actor target must start a valid group pan.")
	_assert_story_group(game, local, world)
	_expect(background == await _background_pixels(stage, factor), "Native background pixels must remain fixed while the cast moves.")
	await _pan_frame("story-riko-midpoint-" + str(factor), game._cast_pan, stage, game)
	await _language_and_detour(game, FIRST_PAN_BEAT)
	game = _active()
	stage = game._cast
	game._process(duration * 0.5 + 0.01)
	_assert_story_group(game, local, world)
	_expect(is_equal_approx(stage._sprites["riko"].get_rect().get_center().x, 640.0), "Riko must reach the requested screen center without moving the wide background.")
	await _pan_frame("story-riko-centered-" + str(factor), game._cast_pan, stage, game)
	var held: Transform2D = game._cast_pan.sample_transform()
	game._process(1.0)
	_expect(held.is_equal_approx(game._cast_pan.sample_transform()), "A completed cast pan must hold while independent focus motion continues.")
	game._continue_story()
	_expect(str(game.current_beat()["id"]) == "two_green_lamps", "The next existing line must retarget Yuzu.")
	_expect(held.is_equal_approx(game._cast_pan.sample_transform()), "Changing actor targets must begin from the current group offset without snapping.")
	game._process(duration * 0.5)
	await _pan_frame("story-yuzu-midpoint-" + str(factor), game._cast_pan, stage, game)
	game._process(duration * 0.5 + 0.01)
	_assert_story_group(game, local, world)
	_expect(is_equal_approx(stage._sprites["yuzu"].get_rect().get_center().x, 640.0), "The opposite-side actor must also reach the same anchor without background panning.")
	_expect(background == await _background_pixels(stage, factor), "The background must remain pixel-identical after panning in the opposite direction.")
	await _pan_frame("story-yuzu-centered-" + str(factor), game._cast_pan, stage, game)
	game._continue_story()
	_expect(str(game.current_beat()["id"]) == "waiting_for_the_signal", "The final existing line must retarget Riko again.")
	game._process(duration + 0.01)
	_assert_story_group(game, local, world)
	_expect(is_equal_approx(stage._sprites["riko"].get_rect().get_center().x, 640.0), "Repeated targeting must not accumulate earlier offsets.")
	var final_state: Dictionary = game._cast_pan.get_state()
	game._continue_story()
	_expect(str(game.current_beat()["id"]) == "hold_the_message" and stage.visible_ids().is_empty(), "The next monologue must clear the panned physical cast.")
	_expect(game._cast_pan.sample_transform().is_equal_approx(Transform2D.IDENTITY) and not game._cast_pan.is_moving(), "A changed background/explicit empty cast must reset its prior pan before the monologue.")
	_pan_metrics.append({"check": "story cast pan", "factor": factor, "fixed_background_pixels": BACKGROUND_REGION.get_area() * factor * factor, "delay_seconds": delay, "duration_seconds": duration, "final_state": final_state})


func _local_rects(stage: Control) -> Dictionary:
	var result := {}
	for actor_id: String in stage.visible_ids():
		result[actor_id] = stage.get_actor_rect(actor_id)
	return result


func _assert_story_group(game: Control, local: Dictionary, world: Transform2D) -> void:
	var stage: Control = game._cast
	_expect(_same(local, _local_rects(stage)), "Group pan must not modify actor-local blocking positions, scale or pair spacing.")
	_expect(game._world_transform().is_equal_approx(world), "Group pan must not change the camera/background transform.")
	_expect(game._cast_transform().is_equal_approx(world * game._cast_pan.sample_transform()), "Cast framing must compose the world and group transforms in order.")
	var delta: float = game._cast_transform().origin.x
	for actor_id: String in stage.visible_ids():
		var actual: Rect2 = stage._sprites[actor_id].get_rect()
		_expect(is_equal_approx(actual.get_center().x - (local[actor_id] as Rect2).get_center().x, delta), "All actors must receive the same horizontal group offset: " + actor_id)
		_expect(actual.is_equal_approx(game._cast_transform() * stage._posed_rect(actor_id)), "Existing actor focus/bounce must compose beneath the pan: " + actor_id)
	_assert_manpu_transform(stage, game._cast_transform())


func _assert_manpu_transform(stage: Control, transform: Transform2D) -> void:
	stage.present(Transform2D.IDENTITY)
	var local_marks := {}
	for key: String in stage._mark_nodes:
		if stage._mark_nodes[key].visible:
			local_marks[key] = stage._mark_nodes[key].get_rect()
	stage.present(transform)
	for key: String in local_marks:
		_expect(stage._mark_nodes[key].get_rect().is_equal_approx(transform * (local_marks[key] as Rect2)), "Manpu must follow the same pan without duplicating its own animation: " + key)


func _world_snapshot(game: Control) -> Dictionary:
	var result := super._world_snapshot(game)
	result["cast_pan"] = game._cast_pan.get_state()
	result["cast_transform"] = game._cast_transform()
	var presented := {}
	for actor_id: String in game._cast.visible_ids():
		presented[actor_id] = game._cast._sprites[actor_id].get_rect()
	result["presented_cast"] = presented
	return result


func _background_pixels(stage: Control, factor: int) -> PackedByteArray:
	var was_visible := stage.visible
	stage.hide()
	await _settle()
	RenderingServer.force_draw(false)
	var pixels := root.get_texture().get_image().get_region(Rect2i(BACKGROUND_REGION.position * factor, BACKGROUND_REGION.size * factor)).get_data()
	stage.visible = was_visible
	await _settle()
	return pixels


func _pan_frame(label: String, pan: RefCounted, stage: Control, game: Control = null) -> void:
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Cast Pan captures must retain native window resolution.")
	var path := PAN_OUTPUT.path_join(label + ".png")
	_expect(picture.save_png(path) == OK, "Cast Pan capture must save: " + label)
	var actors := {}
	for actor_id: String in stage.visible_ids():
		actors[actor_id] = {"local_rect": stage.get_actor_rect(actor_id), "presented_rect": stage._sprites[actor_id].get_rect()}
	var metadata := {"file": path, "sha256": FileAccess.get_sha256(path), "window": [picture.get_width(), picture.get_height()], "pan": pan.get_state(), "actors": actors}
	if game != null:
		metadata["beat"] = game.current_beat()["id"]
		metadata["elapsed"] = game._elapsed
		metadata["world"] = game._world_transform()
		metadata["cast_transform"] = game._cast_transform()
	_pan_captures.append(metadata)


func _laboratory_pan(factor: int) -> void:
	_expect(_app.open_route("game:lab/cast_pan_study"), "Cast Pan must have its dedicated laboratory route.")
	await _settle()
	var lab := _active()
	lab.set_language("ko")
	_expect(lab._load_errors.is_empty(), "The pan study must initialize without errors: " + str(lab._load_errors))
	var stage: Control = lab._cast_layer
	var local := _local_rects(stage)
	var background := await _background_pixels(stage, factor)
	await _click_pan(lab._guest_buttons["sena"])
	var duration := float(lab._pan_settings["duration_seconds"])
	lab._process(duration * 0.5)
	var interrupted: Transform2D = lab._pan.sample_transform()
	await _click_pan(lab._guest_buttons["nami"])
	_expect(lab._pan.sample_transform().is_equal_approx(interrupted) and (lab._pan.get_state()["from"] as Vector2).is_equal_approx(interrupted.origin), "Retargeting during an active pan must capture its current offset without a jump.")
	lab._process(duration * 0.5)
	_expect(_same(local, _local_rects(stage)), "Laboratory target changes must preserve every actor-local rectangle.")
	_assert_manpu_transform(stage, lab._pan.sample_transform())
	_expect(background == await _background_pixels(stage, factor), "Laboratory background pixels must remain fixed during interrupted pans.")
	await _click_pan(lab._pause_button)
	var frozen: Dictionary = lab.pan_state()
	lab._process(2.0)
	lab.set_language("en")
	_expect(_same(frozen, lab.pan_state()), "Pausing and language switching must preserve the active laboratory pan.")
	await _pan_frame("lab-retarget-paused-en-" + str(factor), lab._pan, stage)
	await _click_pan(lab._pause_button)
	lab._process(duration * 0.5 + 0.01)
	_expect(is_equal_approx(stage._sprites["nami"].get_rect().get_center().x, lab._anchor_x), "The laboratory target must reach its selected screen anchor.")
	await _click_pan(lab._home_button)
	lab._process(duration + 0.01)
	_expect(lab._pan.sample_transform().is_equal_approx(Transform2D.IDENTITY), "Home must restore original group framing without resetting local blocking.")
	# Local approach is driven by the same host clock while Layer Pan moves the
	# whole cast. The two transforms must remain independent and compose once.
	_expect(stage.approach_actor("nami", "yuzu", {"duration_seconds": 0.32, "stop_distance": 280.0, "curve": "ease_in_out"}).is_empty(), "The focused composition fixture must start local Quick Approach.")
	await _click_pan(lab._guest_buttons["sena"])
	lab._process(0.16)
	var moving: Dictionary = stage.movement_state()
	_expect(bool(moving["active"]) and lab._pan.is_moving(), "The fixture must exercise local approach and group pan concurrently.")
	_expect(is_equal_approx(stage.get_actor_rect("nami").get_center().x, 305.0) and stage.get_actor_rect("yuzu") == local["yuzu"] and stage.get_actor_rect("sena") == local["sena"], "Local Quick Approach must move only Nami while group panning leaves every local target independent.")
	for actor_id: String in stage.visible_ids():
		_expect(stage._sprites[actor_id].get_rect().is_equal_approx(lab._pan.sample_transform() * stage.get_actor_rect(actor_id)), "The no-focus fixture must apply pan exactly once after local movement: " + actor_id)
	_assert_manpu_transform(stage, lab._pan.sample_transform())
	_expect(background == await _background_pixels(stage, factor), "Composing local and group actor motion must still leave the background fixed.")
	lab.set_language("ko")
	await _pan_frame("lab-local-approach-composition-ko-" + str(factor), lab._pan, stage)
	await _click_pan(lab.find_child("ResetPan", true, false))
	_expect(lab._pan.sample_transform().is_equal_approx(Transform2D.IDENTITY) and stage.movement_state().is_empty() and _same(local, _local_rects(stage)), "Reset must independently clear group pan and the fixture's local movement.")
	_pan_metrics.append({"check": "laboratory retarget and local composition", "factor": factor, "interrupted_offset": interrupted.origin, "local_approach": moving, "fixed_background_pixels": BACKGROUND_REGION.get_area() * factor * factor})
	_expect(_app.open_route("game:afterlight"), "The laboratory must return to the saved story.")
	await _settle()


func _click_pan(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The intended cast-pan control must be visible and enabled.")
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
	if node.has_method("pan_state"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)
