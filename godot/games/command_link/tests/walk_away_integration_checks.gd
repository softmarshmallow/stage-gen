extends SceneTree

## Command Link-owned integration assertions, formerly run from Afterlight's
## combined-project harness. Routes, prepared art and renderer belong here.
var _app: Control
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)


func _open(route: String) -> Control:
	if not _app.open_route(route):
		_expect(false, "Route must open: " + route)
		return null
	await _settle()
	return _app.active_scene


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _app.active_scene != null: _app.active_scene.set_process(false)


func _freeze_route(node: Node) -> void:
	if node.has_method("_update_character_layers"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


const SIZE := Vector2(1280, 900)
const EXITS: Array[String] = ["walk_away", "walk_away_right"]
var _paths: Array = []
var _capture_count := 0
const CAPTURES := "res://tests/walk-away"


func _run() -> void:
	var capture := OS.get_cmdline_user_args().has("--capture-walk-away")
	if capture and DisplayServer.get_name() == "headless":
		printerr("Walk-away captures require a native renderer.")
		quit(2)
		return
	root.size = Vector2i(SIZE)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	await _check_integrated_exits()
	await _check_integrated_bounce()
	if capture and _errors.is_empty(): await _capture_native()
	_app.queue_free()
	await process_frame
	for issue: String in _errors: printerr("FAIL Command Link walk-away: " + issue)
	if _errors.is_empty(): print("PASS Command Link walk-away: three prepared actors, both departures, independent focus and attached marks")
	quit(0 if _errors.is_empty() else 1)


func _check_integrated_exits() -> void:
	var scene := await _open("game:lab/demos/dialogue")
	if scene == null: return
	_legacy_neutral(scene)
	for mode: String in EXITS:
		for index in scene.stage_profile.actors.size():
			var id := str(scene.stage_profile.actors[index]["id"])
			scene._character_exit.clear()
			scene._update_character_layers()
			var base: Rect2 = scene._dialogue_rect(SIZE, index)
			_expect(scene.set_character_exit_preset(mode).is_empty() and scene.exit_actor(id).is_empty(), "The integrated renderer must accept " + mode)
			var duration := _duration(scene.CHARACTER_EXIT_CATALOG, mode)
			var samples: Array = []
			var previous := 0.0
			for phase: float in [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.99]:
				scene._character_exit.advance((phase - previous) * duration)
				previous = phase
				scene._update_character_layers()
				var sprite: TextureRect = scene._actor_nodes[id]
				samples.append(_rect(sprite))
				_expect(sprite.visible and sprite.modulate.is_equal_approx(Color.WHITE) and sprite.material == null, "Integrated departure stays fully colored and opaque through 99%.")
				var motion: Dictionary = scene._character_exit.sample(id)
				_expect(is_equal_approx(sprite.position.x, base.position.x + base.size.y * float(motion["offset_x_ratio"])), "The integrated renderer must apply X travel exactly once.")
			_check_path(samples, mode, "Integrated " + id)
			_expect(_offscreen(samples.back()), "The full prepared integrated actor rectangle must leave before terminal fade: " + id + "/" + mode)
			scene._character_exit.advance(duration)
			scene._update_character_layers()
			_expect(not scene._actor_nodes[id].visible, "The integrated exit must end hidden.")
			scene.show_actor(id)
			_expect(_rect(scene._actor_nodes[id]).is_equal_approx(base) and scene._actor_nodes[id].visible, "Integrated show must restore its exact base rectangle.")
	print("PASS Walk-Away group 3: all three integrated prepared actors, both directions, opaque motion and one-time spatial composition")

func _check_integrated_bounce() -> void:
	var scene := await _open("game:lab/demos/actor_focus")
	if scene == null: return
	_legacy_neutral(scene)
	scene.set_manpu_animation_preset("none")
	scene.set_actor_focus_preset("restless_bounce")
	scene._actor_focus.set_focus("mira")
	scene._actor_focus.replay()
	scene._update_character_layers()
	var actor: TextureRect = scene._actor_nodes["mira"]
	var base := _rect(actor)
	var duration := _duration(scene.ACTOR_FOCUS_CATALOG, "restless_bounce")
	var ys: Array[float] = []
	var previous := 0.0
	var cues: Array = scene._active_manpu()
	var mark_id := ""
	for cue: Dictionary in cues:
		if str(cue["actor"]) == "mira": mark_id = str(cue["id"])
	_expect(not mark_id.is_empty(), "The integrated fixture must supply Mira's prepared manpu cue.")
	var mark_base: Rect2 = scene._manpu_rect(SIZE, "mira", mark_id) if not mark_id.is_empty() else Rect2()
	for phase: float in [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]:
		scene._actor_focus.advance((phase - previous) * duration)
		previous = phase
		scene._update_character_layers()
		ys.append(actor.position.y)
		_expect(actor.visible and is_equal_approx(actor.position.x, base.position.x), "Integrated Restless Bounce must preserve X and visibility.")
		if not mark_id.is_empty():
			var current: Rect2 = scene._manpu_rect(SIZE, "mira", mark_id)
			_expect(is_equal_approx(current.position.y - mark_base.position.y, actor.position.y - base.position.y), "Integrated manpu must follow the same Y offset.")
	_expect(_turn_count(ys) >= 6 and _rect(actor).is_equal_approx(base), "Integrated Restless Bounce must make multiple hops and settle.")
	print("PASS Walk-Away group 4: integrated Restless Bounce and prepared manpu attachment")

func _legacy_neutral(scene: Control) -> void:
	scene._capture_frozen = true
	scene._entry = 1.0
	scene._natural_blink = false
	scene._blink_remaining = 0.0
	scene._dialogue_camera.clear()
	scene._character_exit.clear()
	scene._actor_focus.clear()
	scene.set_actor_focus_preset("none")
	for id: String in scene._character_effects: scene._character_effects[id]["enabled"] = false
	scene._update_character_layers()

func _check_path(samples: Array, mode: String, label: String) -> void:
	var direction := -1.0 if mode == "walk_away" else 1.0
	var ys: Array[float] = []
	for index in samples.size():
		var rect: Rect2 = samples[index]
		ys.append(rect.position.y)
		if index > 0:
			_expect((rect.position.x - samples[index - 1].position.x) * direction > 0.0, label + " must travel monotonically in the selected X direction.")
	_expect(_turn_count(ys) >= 6, label + " must show multiple vertical hops during departure.")
	var serialized: Array = []
	for rect: Rect2 in samples: serialized.append(_rect_array(rect))
	_paths.append({"renderer_actor": label, "preset": mode, "rects": serialized})

func _duration(path: String, preset: String) -> float:
	var parsed: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	for value: Dictionary in parsed["presets"]:
		if value["id"] == preset: return float(value["duration_seconds"])
	_expect(false, "Missing prepared motion preset: " + preset)
	return 1.0

func _offscreen(rect: Rect2) -> bool:
	return rect.end.x <= 0.0 or rect.position.x >= SIZE.x

func _turn_count(values: Array[float]) -> int:
	var count := 0
	var previous := 0.0
	for index in range(1, values.size()):
		var direction := signf(values[index] - values[index - 1])
		if direction != 0.0:
			if previous != 0.0 and direction != previous: count += 1
			previous = direction
	return count

func _rect(sprite: TextureRect) -> Rect2:
	return Rect2(sprite.position, sprite.size)

func _rect_array(rect: Rect2) -> Array:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _capture_native() -> void:
	for window: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window
		var scene := await _open("game:lab/demos/actor_focus")
		_legacy_neutral(scene)
		scene.set_character_exit_preset("walk_away_right")
		scene.exit_actor("lena")
		scene._character_exit.advance(_duration(scene.CHARACTER_EXIT_CATALOG, "walk_away_right") * 0.125)
		scene._update_interface()
		await _capture("integrated-walk-right-hop", scene)
		scene.show_actor("lena")
		scene.set_actor_focus_preset("restless_bounce")
		scene._actor_focus.set_focus("mira")
		scene._actor_focus.replay()
		scene._actor_focus.advance(_duration(scene.ACTOR_FOCUS_CATALOG, "restless_bounce") * 0.125)
		scene._update_interface()
		await _capture("integrated-restless-hop", scene)


func _capture(label: String, scene: Control) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(CAPTURES) == OK, "Capture directory must be writable.")
	root.gui_release_focus()
	if root.gui_get_hovered_control() != null: root.notify_mouse_exited()
	await _settle()
	await RenderingServer.frame_post_draw
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Capture must render at native window resolution.")
	var stem := label + "-" + str(root.size.x)
	_expect(picture.save_png(CAPTURES.path_join(stem + ".png")) == OK, "Native capture must save: " + stem)
	var metadata := {"route": _app.current_route, "window": [root.size.x, root.size.y], "label": label, "actors": {}}
	if scene.has_method("motion_state"):
		metadata["motion"] = scene.motion_state()
		for id: String in scene._cast_layer._sprites:
			var sprite: TextureRect = scene._cast_layer._sprites[id]
			metadata["actors"][id] = {"rect": _rect_array(_rect(sprite)), "visible": sprite.visible, "color": [sprite.modulate.r, sprite.modulate.g, sprite.modulate.b, sprite.modulate.a]}
	elif scene.get("_actor_nodes") is Dictionary:
		for id: String in scene._actor_nodes:
			var sprite: TextureRect = scene._actor_nodes[id]
			metadata["actors"][id] = {"rect": _rect_array(_rect(sprite)), "visible": sprite.visible, "color": [sprite.modulate.r, sprite.modulate.g, sprite.modulate.b, sprite.modulate.a]}
	var record := FileAccess.open(CAPTURES.path_join(stem + ".json"), FileAccess.WRITE)
	record.store_string(JSON.stringify(metadata, "\t"))
	_capture_count += 1
