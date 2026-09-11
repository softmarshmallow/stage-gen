extends RefCounted

## Independent authored-camera checks; the UI remains outside the world transform.
const CAMERA = preload("res://addons/game_presentation/camera/dialogue_camera.gd")
const DESIGN_SIZE := Vector2(1280, 900)
const WORLD_BACKGROUND := Rect2(-35, 0, 1350, 900)
const ACTORS: Array[String] = ["mira", "lena", "sera"]
const LOCATIONS: Array[String] = ["forward_command", "perimeter_overlook", "coastal_staging"]
var _errors: Array[String] = []
var _capture_count := 0


func run(root: Control, options: Dictionary) -> void:
	_check_controller()
	await _check_runtime(root)
	await _check_story(root)
	if _errors.is_empty() and options.has("capture-dialogue-camera"):
		if DisplayServer.get_name() == "headless":
			_errors.append("Dialogue-camera captures require a real renderer.")
		else:
			await _capture_proof(root, String(options.get("capture-dir", "res://tests/dialogue-camera/captures")))
	for issue: String in _errors:
		printerr("FAIL Dialogue Camera: " + issue)
	if _errors.is_empty():
		print("PASS Dialogue Camera: explicit held cues, bounded zoom and world coverage, interrupted continuity, atomic errors, fixed UI, actor/manpu composition, frozen time, exact camera restore and wide non-dialogue boundaries")
		if _capture_count > 0:
			print("Dialogue-camera captures complete: %d PNG and metadata pairs" % _capture_count)
	root.get_tree().quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _new_camera() -> CAMERA:
	var camera: CAMERA = CAMERA.new()
	_expect(camera.initialize(DESIGN_SIZE, WORLD_BACKGROUND).is_empty(), "Camera geometry must initialize.")
	return camera


func _same(left: Dictionary, right: Dictionary) -> bool:
	for field: String in ["zoom", "offset_x", "offset_y"]:
		if not is_equal_approx(float(left[field]), float(right[field])):
			return false
	return true


func _wide(sample: Dictionary) -> bool:
	return is_equal_approx(float(sample["zoom"]), 1.0) and is_zero_approx(float(sample["offset_x"])) and is_zero_approx(float(sample["offset_y"]))


func _transform_rect(rect: Rect2, sample: Dictionary) -> Rect2:
	var zoom: float = sample["zoom"]
	return Rect2(rect.position * zoom + Vector2(float(sample["offset_x"]), float(sample["offset_y"])), rect.size * zoom)


func _covered(rect: Rect2, context: String) -> void:
	_expect(rect.position.x <= 0.001 and rect.position.y <= 0.001 and rect.end.x >= DESIGN_SIZE.x - 0.001 and rect.end.y >= DESIGN_SIZE.y - 0.001, context + " must cover the viewport without empty edges.")


func _bounded(sample: Dictionary) -> void:
	for field: String in ["zoom", "offset_x", "offset_y"]:
		_expect(is_finite(float(sample[field])), "Camera samples must remain finite: " + field)
	_expect(float(sample["zoom"]) >= 1.0 and float(sample["zoom"]) <= 4.0, "The camera must clamp requested zoom to its usable range.")
	_covered(_transform_rect(WORLD_BACKGROUND, sample), "Every camera interpolation sample")


func _check_controller() -> void:
	var camera: CAMERA = _new_camera()
	_expect(_wide(camera.sample()) and not camera.is_moving(), "A fresh camera must start wide.")
	_expect(camera.focus("mira", Vector2(250, 240), Vector2(640, 310), 100.0, 0.7).is_empty(), "The core must clamp an excessive finite zoom request.")
	camera.advance(0.7)
	_expect(is_equal_approx(float(camera.sample()["zoom"]), 4.0), "A completed maximum cue must reach the exact zoom limit.")
	camera.focus("lena", Vector2(640, 240), Vector2(640, 310), 0.1, 0.0)
	_expect(is_equal_approx(float(camera.sample()["zoom"]), 1.0), "A below-wide request must clamp to the minimum valid zoom.")
	camera.focus("mira", Vector2(250, 240), Vector2(640, 310), 3.5, 0.7)
	camera.advance(0.23)
	var interrupted: Dictionary = camera.sample()
	camera.focus("sera", Vector2(1030, 240), Vector2(640, 310), 4.0, 0.7)
	_expect(_same(interrupted, camera.sample()), "An interrupted cue must start from the current camera without a jump.")
	for index in 14:
		camera.advance(0.05)
		_bounded(camera.sample())
	_expect(not camera.is_moving(), "A finite cue must finish its movement.")
	var held: Dictionary = camera.get_state()
	for index in 8:
		camera.advance(1.0)
		camera.sample()
	_expect(camera.get_state() == held, "A completed camera cue must remain held until an explicit new cue.")
	camera.wide(0.7)
	camera.advance(0.19)
	var saved: Dictionary = camera.get_state()
	var restored: CAMERA = _new_camera()
	_expect(restored.restore(saved).is_empty() and _same(restored.sample(), camera.sample()), "A saved mid-motion camera must restore exactly.")
	for invalid: Array in [[Vector2(INF, 0), Vector2(640, 310), 2.0, 0.7], [Vector2(250, 240), Vector2(NAN, 310), 2.0, 0.7], [Vector2(250, 240), Vector2(640, 310), NAN, 0.7], [Vector2(250, 240), Vector2(640, 310), 2.0, -1.0]]:
		_expect(not camera.focus("mira", invalid[0], invalid[1], invalid[2], invalid[3]).is_empty() and camera.get_state() == saved, "Invalid camera cue data must fail atomically.")
	_expect(not camera.restore({"invalid": true}).is_empty() and camera.get_state() == saved, "Malformed camera state must fail without changing the active motion.")
	var invalid_saved: Dictionary = saved.duplicate(true)
	invalid_saved["to"]["zoom"] = 5.0
	_expect(not camera.restore(invalid_saved).is_empty() and camera.get_state() == saved, "Persisted out-of-range camera poses must be rejected rather than silently clamped.")
	_expect(not camera.initialize(Vector2.ZERO, WORLD_BACKGROUND).is_empty() and camera.get_state() == saved, "Invalid camera geometry must not replace active state.")
	for delta: float in [-1.0, INF, NAN]:
		camera.advance(delta)
	_expect(camera.get_state() == saved, "Invalid time deltas must leave camera state unchanged.")
	camera.wide(0.0)
	_expect(_wide(camera.sample()) and not camera.is_moving(), "An immediate wide cue must restore the exact original view.")
	for elapsed: float in [0.0, 0.2, 0.35, 0.7, 1.0]:
		var once: CAMERA = _new_camera()
		var parts: CAMERA = _new_camera()
		once.focus("sera", Vector2(1030, 240), Vector2(640, 310), 4.0, 0.7)
		parts.focus("sera", Vector2(1030, 240), Vector2(640, 310), 4.0, 0.7)
		once.advance(elapsed)
		for index in 40:
			parts.advance(elapsed / 40.0)
		_expect(_same(once.sample(), parts.sample()) and once.is_moving() == parts.is_moving(), "Camera interpolation must be independent of frame partition.")
		_bounded(once.sample())


func _open(root: Control, route: String) -> Control:
	if route in ["game", "new_game", "menu"]:
		route = "game:command_link/" + route
	_expect(bool(root.call("open_route", route)), "Could not open " + route)
	var scene: Control = root.get("active_scene") as Control
	scene.set("_capture_frozen", true)
	await root.get_tree().process_frame
	await root.get_tree().process_frame
	scene.set("_entry", 1.0)
	scene.call("_update_character_layers")
	_expect((scene.get("_load_errors") as Array).is_empty(), "Dialogue-camera assets and controllers must load.")
	return scene


func _tick(scene: Control, seconds: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", seconds)
	scene.set("_capture_frozen", true)


func _sample(scene: Control) -> Dictionary:
	return scene.call("dialogue_camera_sample")


func _background_rect(scene: Control) -> Rect2:
	var texture: Texture2D = (scene.get("_location_textures") as Dictionary)[String(scene.get("_location_id"))]
	return scene.call("_presented_background_rect", DESIGN_SIZE, texture.get_size())


func _ui_rects(scene: Control) -> Dictionary:
	var result := {}
	for field: String in ["_title", "_line", "_speaker", "_next_button", "_demos_button", "_play_button"]:
		var control: Control = scene.get(field) as Control
		if control != null:
			result[field] = control.get_rect()
	return result


func _actor_composition(scene: Control, actor: String) -> void:
	var index: int = ACTORS.find(actor)
	var posed: Rect2 = scene.call("_posed_dialogue_rect", DESIGN_SIZE, index)
	var shown: Rect2 = scene.call("_presented_dialogue_rect", DESIGN_SIZE, index)
	_expect(shown.is_equal_approx(_transform_rect(posed, _sample(scene))), "The actor's focus pose must pass through the world camera exactly once: " + actor)
	var sprite: TextureRect = (scene.get("_actor_nodes") as Dictionary)[actor] as TextureRect
	_expect(sprite.get_rect().is_equal_approx(shown), "The displayed actor must use the sampled camera rectangle: " + actor)
	var mark: Rect2 = scene.call("_manpu_rect", DESIGN_SIZE, actor, "surprise")
	var world_mark: Rect2 = scene.call("_manpu_world_rect", DESIGN_SIZE, actor, "surprise")
	_expect(mark.is_equal_approx(_transform_rect(world_mark, _sample(scene))) and is_equal_approx(mark.size.y / shown.size.y, 0.1), "Manpu must retain its world attachment and scale through the same camera: " + actor)


func _check_runtime(root: Control) -> void:
	var scene: Control = await _open(root, "demos/dialogue")
	scene.call("set_actor_focus_preset", "none")
	scene.call("set_manpu_animation_preset", "none")
	var fixed_ui: Dictionary = _ui_rects(scene)
	for location: String in LOCATIONS:
		scene.call("clear_dialogue_camera")
		scene.call("_select_location", location, true)
		for actor: String in ACTORS:
			_expect((scene.call("focus_dialogue_camera", actor, 100.0, 0.7) as Array).is_empty(), "Every actor must be a valid authored camera target.")
			for index in 7:
				_tick(scene, 0.1)
				_covered(_background_rect(scene), "Every actor/location camera path")
				_actor_composition(scene, actor)
			_expect(_ui_rects(scene) == fixed_ui, "Zooming and retargeting the world must leave dialogue and navigation controls fixed.")
			_expect(is_equal_approx(float(_sample(scene)["zoom"]), 4.0), "Every scene and actor must support the declared maximum camera zoom.")
	scene.call("focus_dialogue_camera", "mira", 0.1, 0.0)
	_expect(is_equal_approx(float(_sample(scene)["zoom"]), 1.0), "The stage must clamp a below-wide finite zoom request to its minimum.")
	scene.set("_dialogue_index", 0)
	scene.call("set_actor_focus_preset", "bounce")
	scene.call("set_manpu_animation_preset", "shake")
	(scene.get("_actor_focus") as RefCounted).call("clear")
	(scene.get("_manpu_animation") as RefCounted).call("clear")
	scene.call("_update_interface")
	scene.call("focus_dialogue_camera", "mira", 3.0, 0.0)
	_tick(scene, 0.0432)
	_actor_composition(scene, "mira")
	var mark_world: Rect2 = scene.call("_manpu_world_rect", DESIGN_SIZE, "mira", "surprise")
	var animation: Dictionary = (scene.get("_manpu_animation") as RefCounted).call("sample", "mira", "surprise")
	var animated_size: Vector2 = mark_world.size * float(animation["scale"])
	var animated_world := Rect2(mark_world.get_center() - animated_size * 0.5 + Vector2(0, mark_world.size.y * float(animation["offset_y_ratio"])), animated_size)
	var final_mark: Rect2 = scene.call("_presented_manpu_rect", DESIGN_SIZE, "mira", "surprise")
	_expect(final_mark.is_equal_approx(_transform_rect(animated_world, _sample(scene))), "Local mark animation and actor focus must compose before the world camera, once each.")
	var held: Dictionary = scene.call("save_dialogue_camera")
	for index in 3:
		scene.call("_advance_dialogue")
	_expect(scene.call("save_dialogue_camera") == held, "Changing speakers or dialogue lines must not automatically issue a new camera cue.")
	scene.call("focus_dialogue_camera", "mira", 2.0, 0.7)
	_tick(scene, 0.2)
	var before: Dictionary = _sample(scene)
	scene.call("focus_dialogue_camera", "lena", 3.0, 0.7)
	_expect(_same(before, _sample(scene)), "A runtime camera retarget must be continuous at the interruption.")
	var saved: Dictionary = scene.call("save_dialogue_camera")
	for index in 8:
		scene.call("_layout_interface")
		scene.call("_process", 0.5)
	_expect(scene.call("save_dialogue_camera") == saved, "Frozen layout and redraw must not advance a camera cue.")
	_expect(not (scene.call("focus_dialogue_camera", "unknown_actor", 2.0, 0.7) as Array).is_empty() and scene.call("save_dialogue_camera") == saved, "Unknown actor targets must fail atomically at the stage boundary.")
	scene.call("clear_dialogue_camera")
	_expect((scene.call("restore_dialogue_camera", saved) as Array).is_empty() and _same(before, _sample(scene)), "Runtime restore must reproduce an interrupted view exactly.")
	scene.call("start_establishing", "coastal_staging")
	_expect(_wide(_sample(scene)), "An establishing shot must begin from the wide dialogue-camera view.")
	scene.call("skip_establishing")
	scene.call("focus_dialogue_camera", "mira", 3.0, 0.0)
	scene.call("_set_mode", "reach_out")
	_expect(_wide(_sample(scene)), "Contact mode must keep its independently authored fingertip framing.")


func _story_next(scene: Control) -> void:
	var button: Button = scene.get("_next_button") as Button
	_expect(button.visible and not button.disabled, "The authored story must provide an enabled Next action.")
	scene.call("_route_mouse", button.get_global_rect().get_center())


func _check_story(root: Control) -> void:
	var scene: Control = await _open(root, "new_game")
	scene.call("skip_establishing")
	scene.set("_entry", 1.0)
	scene.call("_update_interface")
	var initial_camera: Dictionary = scene.call("save_dialogue_camera")
	_expect(not (scene.call("focus_dialogue_camera", "sera", 2.0, 0.7) as Array).is_empty() and scene.call("save_dialogue_camera") == initial_camera, "The camera must reject a known actor who is absent from the current cast.")
	_story_next(scene)
	_expect(String(scene.get("_story_id")) == "briefing" and String((scene.call("save_dialogue_camera") as Dictionary)["focus_id"]) == "lena" and bool(scene.call("is_dialogue_camera_moving")), "Lena's briefing must explicitly begin the authored close-up.")
	_tick(scene, 0.3)
	var partial: Dictionary = scene.call("save_dialogue_camera")
	var partial_sample: Dictionary = _sample(scene)
	_expect(float(partial_sample["zoom"]) > 1.0 and float(partial_sample["zoom"]) < 3.5, "The main close-up must animate into its authored framing.")
	root.call("open_route", "menu")
	scene = await _open(root, "game")
	_expect(String(scene.get("_story_id")) == "briefing" and scene.call("save_dialogue_camera") == partial and _same(_sample(scene), partial_sample), "Main-game resume must preserve the exact mid-push camera timeline and view.")
	_tick(scene, 0.6)
	var held: Dictionary = scene.call("save_dialogue_camera")
	_expect(is_equal_approx(float(_sample(scene)["zoom"]), 3.5), "The authored briefing must settle at its selected close-up zoom.")
	for beat: String in ["briefing_risk", "briefing_plan"]:
		_story_next(scene)
		_expect(String(scene.get("_story_id")) == beat and scene.call("save_dialogue_camera") == held, "The explicit close-up must hold across " + beat + " without restarting.")
	_story_next(scene)
	_expect(String(scene.get("_story_id")) == "orders" and bool(scene.call("is_dialogue_camera_moving")), "Orders must explicitly return the camera to wide.")
	var choices: Array = scene.get("_choice_buttons")
	for button: Button in choices:
		_expect(button.disabled, "Mission orders must wait until the wide view is ready.")
	scene.call("_route_mouse", (choices[0] as Button).get_global_rect().get_center())
	scene.call("_choose", 0)
	_expect(String(scene.get("_story_id")) == "orders" and String((scene.call("save_game") as Dictionary)["priority"]).is_empty(), "A disabled order and direct choice call must not skip the wide-camera gate.")
	_tick(scene, 0.8)
	_expect(_wide(_sample(scene)) and not (choices[0] as Button).disabled, "Completing the wide cue must enable the order choices.")
	scene.call("_route_mouse", (choices[0] as Button).get_global_rect().get_center())
	_story_next(scene)
	_story_next(scene)
	_expect(bool(scene.call("_is_briefing_handoff_active")) and _wide(_sample(scene)), "The authored cast handoff must run from the wide view.")
	_tick(scene, 2.5)
	_story_next(scene)
	_expect(String(scene.get("_story_id")) == "link" and _wide(_sample(scene)), "The required fingertip interaction must retain its own wide camera framing.")
	_tick(scene, 0.5)
	scene.call("_route_mouse", scene.call("_fingertip_center", DESIGN_SIZE))
	_story_next(scene)
	choices = scene.get("_choice_buttons")
	scene.call("_route_mouse", (choices[0] as Button).get_global_rect().get_center())
	_expect(bool(scene.call("is_establishing")) and _wide(_sample(scene)), "Changing locations must hand over to the establishing shot from a wide dialogue camera.")


func _capture_proof(root: Control, folder: String) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "Cannot create dialogue-camera capture directory.")
	var scene: Control = await _open(root, "demos/dialogue_camera")
	scene.set("_capturing", true)
	scene.set("_natural_blink", false)
	scene.set("_blink_remaining", 0.0)
	scene.set("_pointer", Vector2(-1000, -1000))
	for location: String in LOCATIONS:
		scene.call("clear_dialogue_camera")
		scene.call("_select_location", location, true)
		for actor: String in ACTORS:
			_frame_capture(scene, actor)
			_tick(scene, 0.7)
			await _capture(root, scene, folder, location + "_" + actor + "_maximum")
	scene.call("_frame_wide")
	_tick(scene, 0.7)
	await _capture(root, scene, folder, "wide_control")
	_frame_capture(scene, "mira")
	_tick(scene, 0.3)
	await _capture(root, scene, folder, "push_in_middle")
	_frame_capture(scene, "sera")
	_tick(scene, 0.3)
	await _capture(root, scene, folder, "interrupted_retarget_middle")


func _frame_capture(scene: Control, actor: String) -> void:
	scene.set("_demo_line_index", ACTORS.find(actor) * 3)
	scene.call("_set_zoom", 4.0)
	scene.call("_set_duration", 0.7)
	scene.call("_frame_speaker")


func _rect_array(rect: Rect2) -> Array[float]:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _capture(root: Control, scene: Control, folder: String, name: String) -> void:
	root.get_viewport().gui_release_focus()
	root.get_viewport().notify_mouse_exited()
	scene.set("_location_title_elapsed", 3.7)
	scene.call("_update_location_title")
	scene.call("_update_interface")
	await root.get_tree().process_frame
	scene.queue_redraw()
	for index in 4:
		RenderingServer.force_draw(false)
	var picture: Image = root.get_viewport().get_texture().get_image()
	_expect(picture.get_size() == Vector2i(1280, 900) and picture.save_png(folder.path_join(name + ".png")) == OK, "Cannot save dialogue-camera frame " + name)
	var transform: Transform2D = root.get_viewport().get_final_transform()
	var extent: Vector2 = transform.basis_xform(DESIGN_SIZE)
	var metadata := {"state": name, "route": "demos/dialogue_camera", "location": scene.get("_location_id"), "camera": scene.call("save_dialogue_camera"), "sample": _sample(scene),
		"background_rect": _rect_array(_background_rect(scene)), "actors": {}, "manpu": {}, "capture_space": "logical_viewport", "viewport": [1280, 900],
		"window_size": [root.get_window().size.x, root.get_window().size.y], "output_rect": [transform.origin.x, transform.origin.y, extent.x, extent.y], "output_scale": [transform.x.x, transform.y.y]}
	for actor: String in ACTORS:
		var sprite: TextureRect = (scene.get("_actor_nodes") as Dictionary)[actor] as TextureRect
		metadata["actors"][actor] = {"visible": sprite.visible, "rect": _rect_array(sprite.get_rect())}
	for cue: Dictionary in scene.call("_presented_manpu_cues"):
		metadata["manpu"][String(cue["actor"]) + ":" + String(cue["id"])] = _rect_array(scene.call("_presented_manpu_rect", DESIGN_SIZE, String(cue["actor"]), String(cue["id"])))
	var record: FileAccess = FileAccess.open(folder.path_join(name + ".json"), FileAccess.WRITE)
	if record == null:
		_errors.append("Cannot write dialogue-camera metadata " + name)
	else:
		record.store_string(JSON.stringify(metadata, "\t"))
	_capture_count += 1
	print("Dialogue-camera capture: " + ProjectSettings.globalize_path(folder.path_join(name + ".png")))
