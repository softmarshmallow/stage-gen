extends "res://tests/one_shot_manpu_integration_checks.gd"

## Command Link owns the native tactical loop proof and its prepared artwork.
const LOOP_OUTPUT := "res://tests/looping-manpu"
var _loop_captures: Array[Dictionary] = []


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
		await _tactical_loop(factor)
	var sources := {}
	for path: String in ["res://addons/game_presentation/motion/presentation_animation.gd", "res://addons/game_presentation/actors/manpu_animation.gd", "res://addons/game_presentation/actors/presets/manpu.json", "res://presentation/stage.gd", "res://presentation/stage_assets.gd", "res://presentation/stage_controls.gd"]:
		sources[path] = FileAccess.get_sha256(path)
	var manifest := FileAccess.open(LOOP_OUTPUT.path_join("manifest.json"), FileAccess.WRITE)
	manifest.store_string(JSON.stringify({"sources": sources, "captures": _loop_captures, "errors": _errors}, "\t"))
	_app.queue_free()
	_app = null
	for frame in 3: await process_frame
	for issue: String in _errors: printerr("FAIL Command Link looping Manpu: " + issue)
	if _errors.is_empty(): print("PASS Command Link looping Manpu: native 1x/2x raster changes, centered poses, frozen rendering, art validation and departing-owner cleanup")
	quit(0 if _errors.is_empty() else 1)


func _tactical_loop(factor: int) -> void:
	var stage := await _open("game:lab/demos/manpu")
	if stage == null: return
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
