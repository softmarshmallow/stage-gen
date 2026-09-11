extends "res://qa/one_shot_manpu_integration_checks.gd"

## Concrete clock, texture and centered-rotation integration. Controller boundary
## cases belong to the focused Manpu checks; this fixture verifies native hosts.
const LOOP_OUTPUT := "res://qa/looping-manpu"
var _loop_captures: Array[Dictionary] = []
var _loop_metrics: Array[Dictionary] = []


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Looping Manpu integration requires a native renderer.")
		quit(2)
		return
	_capture_enabled = true
	DirAccess.make_dir_recursive_absolute(LOOP_OUTPUT)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	for factor in [1, 2]:
		root.size = Vector2i(DESIGN_SIZE) * factor
		await _story_loop(factor)
		await _afterlight_loop(factor)
		await _tactical_loop(factor)
		await _laboratory_loop(factor)
	var sources := {}
	for path: String in ["res://addons/game_presentation/motion/presentation_animation.gd", "res://addons/game_presentation/actors/manpu_animation.gd", "res://addons/game_presentation/actors/presets/manpu.json", "res://presentation/stage.gd", "res://games/bishoujo_afterlight/cast_stage.gd", "res://games/bishoujo_afterlight/root.gd", "res://games/bishoujo_afterlight/story.gd", "res://games/bishoujo_afterlight/story_beats.gd", "res://games/presentation_lab/afterlight/sigh_puff_study.gd", "res://games/presentation_lab/afterlight/billboard_puff_preview.gd"]:
		sources[path] = FileAccess.get_sha256(path)
	var manifest := FileAccess.open(LOOP_OUTPUT.path_join("manifest.json"), FileAccess.WRITE)
	manifest.store_string(JSON.stringify({"sources": sources, "captures": _loop_captures, "metrics": _loop_metrics, "errors": _errors}, "\t"))
	_app.queue_free()
	_app = null
	for frame in 3: await process_frame
	for issue: String in _errors: printerr("FAIL Looping Manpu integration: " + issue)
	if _errors.is_empty():
		print("PASS Looping Manpu integration: native 1x/2x stepped poses and raster frames, both 2D renderers, centered camera composition, atomic art validation, story continuity, loop/event independence and camera-facing 3D rotation")
	quit(0 if _errors.is_empty() else 1)


func _story_loop(factor: int) -> void:
	var game := await _open("game:bishoujo_afterlight/new_game")
	_seek(game, "no_ordinary_post")
	_expect(game.current_beat()["id"] == "no_ordinary_post" and _healthy(game), "The first looping reaction must be reachable in the existing story.")
	var actor := str(game.current_beat()["speaker"])
	var mark := str(game.current_beat()["mark"])
	game._process(0.2)
	var sample: Dictionary = game._cast._manpu.sample(actor, mark)
	_expect(is_zero_approx(float(sample["rotation_degrees"])) and is_equal_approx(float(sample["scale"]), 1.0), "The first half-cycle must hold the original pose.")
	await _record_loop("story-base-" + str(factor), sample)
	game._process(0.25)
	sample = game._cast._manpu.sample(actor, mark)
	_expect(is_equal_approx(float(sample["rotation_degrees"]), 30.0) and is_equal_approx(float(sample["scale"]), 0.8), "The second half-cycle must hold the rotated smaller pose.")
	await _record_loop("story-alternate-" + str(factor), sample)
	var before: Dictionary = game._cast._manpu.get_state()
	game._toggle_pause()
	game._process(2.0)
	game.set_language("en")
	game.set_language("ko")
	_expect(_same_loop(before, game._cast._manpu.get_state()), "Pause and language switching must preserve the loop phase.")
	await _open("game:presentation_lab")
	game = await _open("game:bishoujo_afterlight")
	_expect(_same_loop(before, game._cast._manpu.get_state()), "Lab replay must reconstruct the active persistent loop phase.")
	game._process(2.0)
	_expect(is_equal_approx(float(game._cast._manpu.sample(actor, mark)["rotation_degrees"]), 0.0), "A loop must keep advancing beyond its first duration.")
	game._continue_story()
	_expect(not game._cast._manpu.get_state()["states"].has(actor + ":" + mark), "The following story beat must remove the old loop cue.")


func _afterlight_loop(factor: int) -> void:
	var study := await _open("game:presentation_lab/sigh_puff_study")
	var cast: Control = study._cast_layer
	var actor := str(study._guest_id)
	_expect(cast.mark(actor, "surprise", "step_loop").is_empty(), "Afterlight must bind the per-cue step loop.")
	cast.advance(0.45)
	cast.present(Transform2D.IDENTITY)
	var node: TextureRect = cast._mark_nodes[actor + ":surprise"]
	var rect := node.get_rect()
	var sample: Dictionary = cast._manpu.sample(actor, "surprise")
	_expect(is_equal_approx(node.rotation_degrees, 30.0) and node.pivot_offset.is_equal_approx(node.size * 0.5), "Afterlight rotation must use the mark's center.")
	var camera := Transform2D(Vector2(1.3, 0), Vector2(0, 1.3), Vector2(-170, -80))
	cast.present(camera)
	_expect(node.get_rect().is_equal_approx(camera * rect) and node.pivot_offset.is_equal_approx(node.size * 0.5), "Camera projection must apply once before centered mark rotation.")
	var before: Dictionary = cast._manpu.get_state()
	var cues: Array = cast._marks.duplicate(true)
	var invalid: Array[String] = cast.set_marks([{"actor": actor, "id": "surprise", "preset": "frame_loop", "frames": ["surprise", "missing_raster"]}])
	_expect(not invalid.is_empty() and _same_loop(before, cast._manpu.get_state()) and cues == cast._marks and node.texture == cast._mark_textures["surprise"], "Unavailable frame art must reject the complete cue update without mutation.")
	cast.present(Transform2D.IDENTITY)
	var event: Dictionary = cast.emit_manpu(actor, "sigh_puff")
	cast.advance(0.2)
	cast.present(Transform2D.IDENTITY)
	_expect(event["errors"].is_empty() and cast._manpu.one_shots().size() == 1 and cast._manpu.get_state()["states"].size() == 1, "Persistent looping and the existing one-shot puff must coexist.")
	cast.advance(0.5)
	cast.present(Transform2D.IDENTITY)
	_expect(cast._manpu.one_shots().is_empty() and cast._one_shot_nodes.is_empty() and node.visible, "Puff expiry must leave the persistent loop alive.")
	_expect(cast.mark(actor, "surprise", "frame_loop", ["surprise", "sparkle"]).is_empty(), "A sequence may bind existing interchangeable rasters.")
	cast.advance(0.35)
	cast.present(Transform2D.IDENTITY)
	_expect(cast._manpu.sample(actor, "surprise")["sprite_id"] == "sparkle" and node.texture == cast._mark_textures["sparkle"], "The Afterlight node must render the current frame rather than the attachment ID.")
	await _record_loop("afterlight-frame-" + str(factor), cast._manpu.sample(actor, "surprise"))
	cast.set_cast([])
	_expect(cast._manpu.get_state()["states"].is_empty() and not node.visible, "Replacing the cast must clear looping marks and their render visibility.")
	_loop_metrics.append({"factor": factor, "centered_sample": sample, "camera": camera})


func _tactical_loop(factor: int) -> void:
	var stage := await _open("game:presentation_lab/demos/manpu")
	stage._capture_frozen = true
	stage._entry = 1.0
	stage._natural_blink = false
	stage._mode = "dialogue"
	var cue := {"actor": "mira", "id": "surprise", "preset": "step_loop", "frames": ["surprise", "sparkle"]}
	stage.stage_profile.dialogue[stage._dialogue_index]["manpu"] = [cue]
	stage._update_character_layers()
	var initial := await _frame_image()
	stage._manpu_animation.advance(0.45)
	stage._update_character_layers()
	var sample: Dictionary = stage._manpu_animation.sample("mira", "surprise")
	_expect(sample["sprite_id"] == "sparkle" and is_equal_approx(float(sample["rotation_degrees"]), 30.0), "The tactical presenter must receive the same selected raster and stepped pose.")
	var rotated := await _frame_image()
	var region: Rect2 = stage._manpu_rect(DESIGN_SIZE, "mira", "surprise").grow(30.0)
	_expect(_different_pixels(initial, rotated, root.get_final_transform() * region) > 20, "The native tactical draw path must visibly change the raster and pose.")
	var frozen: Dictionary = stage._manpu_animation.get_state()
	for redraw in 4: stage._update_character_layers()
	_expect(_same_loop(frozen, stage._manpu_animation.get_state()), "Repeated tactical synchronization must not restart the selected loop.")
	await _record_loop("tactical-frame-rotation-" + str(factor), sample)
	_expect(not stage._manpu_cue_errors([{"actor": "mira", "id": "surprise", "frames": ["surprise", "missing_raster"]}]).is_empty(), "Tactical authored cues must reject unavailable frame art.")
	stage.exit_actor("mira")
	_expect(not stage._manpu_animation.get_state()["states"].has("mira:surprise"), "A departing tactical owner must remove its looping mark.")


func _laboratory_loop(factor: int) -> void:
	var study := await _open("game:presentation_lab/sigh_puff_study")
	study._select_mode("step_loop")
	study._trigger_puff()
	study._process(0.45)
	study._toggle_pause()
	var before: Dictionary = study._controller().get_state()
	study._process(2.0)
	study.set_language("en")
	_expect(_same_loop(before, study._controller().get_state()), "Study pause and language changes must preserve the active stepped loop.")
	await _record_loop("lab-step-2d-en-" + str(factor), study._controller().sample(study._guest_id, "sigh_puff"))
	study._set_presentation("3d")
	study._toggle_angle()
	_expect(_same_loop(before, study._controller().get_state()), "3D presentation and camera-angle changes must retain the same loop and phase.")
	var preview: Control = study._billboard
	_expect(preview._puffs.size() == 1 and preview._viewport.size == root.size, "The 3D study must have one persistent mark at native resolution.")
	var puff: Sprite3D = preview._puffs.values()[0]
	var sample: Dictionary = study._controller().sample(study._guest_id, "sigh_puff")
	var radians := deg_to_rad(float(sample["rotation_degrees"]))
	var basis: Basis = preview._camera_3d.global_basis
	_expect(puff.global_basis.z.normalized().is_equal_approx(basis.z.normalized()) and puff.global_basis.x.normalized().is_equal_approx((basis.x * cos(radians) - basis.y * sin(radians)).normalized()), "Rotated 3D marks must retain the sampled screen rotation while facing the orbited camera.")
	await _record_loop("lab-step-3d-angled-en-" + str(factor), sample)
	await _click(study._replay_button)
	_expect(is_zero_approx(float(study._controller().sample(study._guest_id, "sigh_puff")["rotation_degrees"])) and study._paused, "Replay must restart the sampled loop while preserving explicit pause.")
	await _click(study._remove_button)
	_expect(study._controller().get_state()["states"].is_empty() and preview._puffs.is_empty(), "Remove must discard a looping cue from both presentations.")
	for mode: String in ["two_frame_loop", "three_frame_loop"]:
		await _click(study._mode_buttons[mode])
		await _click(study._trigger_button)
		study._process(0.45)
		var frame_sample: Dictionary = study._controller().sample(study._guest_id, "sigh_puff")
		var expected_id := "sparkle" if mode == "two_frame_loop" else "heart"
		_expect(frame_sample["sprite_id"] == expected_id and preview._puffs.values()[0].texture == study._fixture_textures[expected_id], "The 3D study must display the selected frame from the same persistent controller: " + mode)
		if mode == "three_frame_loop":
			study.set_language("ko")
			await _record_loop("lab-three-frame-ko-" + str(factor), frame_sample)
	study._reset_puffs()
	_expect(study._controller().get_state()["states"].is_empty() and study._billboard._puffs.is_empty(), "Study reset must clear the persistent loop in both renderers.")
	for mode: String in ["static", "shake", "one_shot"]:
		study._select_mode(mode)
		study._trigger_puff()
		study._process(1.0)
		_expect(_healthy(study), "Existing study mode must remain valid: " + mode)


func _record_loop(label: String, sample: Dictionary) -> void:
	var picture := await _frame_image()
	var path := LOOP_OUTPUT.path_join(label + ".png")
	_expect(picture.get_size() == root.size and picture.save_png(path) == OK, "The native looping capture must save at window resolution: " + label)
	_loop_captures.append({"file": path, "sha256": FileAccess.get_sha256(path), "window": [picture.get_width(), picture.get_height()], "sample": sample.duplicate(true)})
	print("Captured Looping Manpu: " + label)


func _frame_image() -> Image:
	await _settle()
	# A background native window need not redraw spontaneously on macOS.
	RenderingServer.force_draw(false)
	return root.get_texture().get_image()


func _same_loop(a: Variant, b: Variant) -> bool:
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size(): return false
		for key: Variant in a:
			if not b.has(key) or not _same_loop(a[key], b[key]): return false
		return true
	if a is Array and b is Array:
		if a.size() != b.size(): return false
		for index in a.size():
			if not _same_loop(a[index], b[index]): return false
		return true
	if (a is float or a is int) and (b is float or b is int):
		return is_equal_approx(float(a), float(b))
	return a == b
