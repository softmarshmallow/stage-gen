extends SceneTree

## Independent integration proof for two hosts and the routed laboratory.
## Uses prepared artwork, explicit clocks, and optional native 1x/2x captures.
const SIZE := Vector2(1280, 900)
const ART_ROOT = preload("res://root.gd")
const CAST_STAGE = preload("res://cast_stage.gd")
const CAPTURES := "res://tests/walk-away"
const EXITS: Array[String] = ["walk_away", "walk_away_right"]
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false
var _capture_count := 0
var _paths: Array = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-walk-away")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Walk-Away captures require a native renderer.")
		quit(2)
		return
	root.size = Vector2i(SIZE)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	var stage := _prepared_cast()
	if stage == null:
		_finish()
		return
	_check_afterlight_exits(stage)
	_check_afterlight_bounce(stage)
	stage.queue_free()
	await _check_integrated_exits()
	await _check_integrated_bounce()
	await _check_handoff_resume()
	_check_story_restless()
	await _check_lab_controls()
	if _capture_enabled and _errors.is_empty():
		await _capture_native()
	_finish()


func _prepared_cast() -> Control:
	var stage = CAST_STAGE.new()
	root.add_child(stage)
	var textures := {}
	for profile: Dictionary in ART_ROOT.CONTENT["guests"]:
		var picture := Image.load_from_file(str(profile["path"]))
		if picture == null or picture.is_empty():
			_expect(false, "Prepared actor image must load: " + str(profile["id"]))
			stage.queue_free()
			return null
		textures[str(profile["id"])] = ImageTexture.create_from_image(picture)
	_expect(stage.initialize(ART_ROOT.CONTENT["guests"], textures).is_empty(), "Prepared Afterlight cast must initialize.")
	return stage


func _afterlight_ids() -> Array[String]:
	var ids: Array[String] = []
	for profile: Dictionary in ART_ROOT.CONTENT["guests"]: ids.append(str(profile["id"]))
	return ids


func _check_afterlight_exits(stage: Control) -> void:
	var ids := _afterlight_ids()
	for mode: String in EXITS:
		for id: String in ids:
			stage.set_cast(ids)
			stage.focus("", "none")
			stage.present(Transform2D.IDENTITY)
			var base: Rect2 = stage.get_actor_rect(id)
			var other := ids[(ids.find(id) + 1) % ids.size()]
			var observer := _sprite_state(stage._sprites[other])
			_expect(stage.dismiss(id, mode).is_empty(), "Afterlight must accept " + mode)
			var duration := _duration(stage.EXIT_CATALOG, mode)
			var samples: Array = []
			var previous := 0.0
			for phase: float in [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.99]:
				stage.advance((phase - previous) * duration)
				previous = phase
				stage.present(Transform2D.IDENTITY)
				var sprite: TextureRect = stage._sprites[id]
				samples.append(_rect(sprite))
				_expect(sprite.visible and sprite.modulate.is_equal_approx(Color.WHITE) and sprite.material == null, "Afterlight exit stays fully colored and opaque through 99%: " + id + "/" + mode)
				_expect(_same(_sprite_state(stage._sprites[other]), observer), "Another Afterlight actor must remain independent of departure.")
				var motion: Dictionary = stage._appearance(id)
				_expect(is_equal_approx(sprite.position.x, base.position.x + base.size.y * float(motion["offset_x_ratio"])), "Afterlight must apply X travel exactly once.")
			_check_path(samples, mode, "Afterlight " + id)
			_expect(_offscreen(samples.back()), "The full prepared Afterlight rectangle must leave the viewport before its terminal fade: " + id + "/" + mode)
			stage.advance(duration)
			stage.present(Transform2D.IDENTITY)
			_expect(not stage._sprites[id].visible and not stage.is_busy(), "Afterlight completion must hide the actor and settle.")
			stage.set_cast(ids)
			stage.dismiss(id, mode)
			stage.advance(duration * 0.3)
			stage.set_cast(ids)
			stage.present(Transform2D.IDENTITY)
			_expect(_rect(stage._sprites[id]).is_equal_approx(base) and stage._sprites[id].modulate.is_equal_approx(Color.WHITE) and not stage.is_busy(), "Immediate Afterlight placement must cancel departure and restore its baseline.")
	print("PASS Walk-Away group 1: all four prepared Afterlight actors, both directions, opaque motion, geometry coverage, independent actors and cancellation")


func _check_afterlight_bounce(stage: Control) -> void:
	stage.set_cast(["nami", "yuzu"])
	stage._manpu.configure("none")
	stage.mark("nami", "surprise")
	stage.focus("nami", "restless_bounce", true)
	stage.present(Transform2D.IDENTITY)
	var actor: TextureRect = stage._sprites["nami"]
	var mark: TextureRect = stage._mark_nodes["nami:surprise"]
	var base := _rect(actor)
	var mark_base := _rect(mark)
	var observer := _sprite_state(stage._sprites["yuzu"])
	var duration := _duration(stage.FOCUS_CATALOG, "restless_bounce")
	var ys: Array[float] = []
	var previous := 0.0
	for phase: float in [0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0]:
		stage.advance((phase - previous) * duration)
		previous = phase
		stage.present(Transform2D.IDENTITY)
		ys.append(actor.position.y)
		_expect(actor.visible and is_equal_approx(actor.position.x, base.position.x) and actor.modulate.is_equal_approx(Color.WHITE), "Restless Bounce changes Y only and leaves the actor fully visible.")
		_expect(is_equal_approx(mark.position.y - mark_base.position.y, actor.position.y - base.position.y) and mark.size.is_equal_approx(mark_base.size), "Manpu must remain proportionally attached to its bouncing actor.")
		_expect(_same(observer, _sprite_state(stage._sprites["yuzu"])), "Another actor must not inherit Restless Bounce.")
	_expect(_turn_count(ys) >= 6 and _rect(actor).is_equal_approx(base), "Restless Bounce must make multiple hops and settle exactly on its baseline.")
	stage.focus("nami", "restless_bounce", true)
	stage.advance(duration * 0.125)
	stage.present(Transform2D.IDENTITY)
	var posed := _rect(actor)
	var mark_posed := _rect(mark)
	var camera := Transform2D(Vector2(1.7, 0), Vector2(0, 1.7), Vector2(-340, -150))
	stage.present(camera)
	_expect(_rect(actor).is_equal_approx(camera * posed) and _rect(mark).is_equal_approx(camera * mark_posed), "Camera scaling must apply once to posed actor and attached manpu.")
	var frozen: Dictionary = _focus_state(stage._focus)
	stage.present(camera)
	_expect(_focus_state(stage._focus) == frozen, "Rendering must not replay or advance Restless Bounce.")
	stage.present(Transform2D.IDENTITY)
	print("PASS Walk-Away group 2: Y-only multi-hop cue, manpu attachment, independent actors, camera composition and frozen rendering")


func _check_integrated_exits() -> void:
	var scene := await _open("game:lab/demos/dialogue")
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


func _check_handoff_resume() -> void:
	var game := await _open("game:afterlight/new_game")
	for index in 20:
		if str(game.current_beat()["id"]) == "sena_takes_over": break
		game._process(8.0)
		if game._choice_pending(): game._choose("help_first")
		else: game._next()
	_expect(str(game.current_beat()["id"]) == "sena_takes_over", "The bounded authored prefix must reach Nami's handoff.")
	_expect(game.current_beat().get("exit_preset") == "walk_away", "The authored handoff must select Walk-Away.")
	game._process(0.45)
	var before := _handoff_state(game)
	var base: Rect2 = game._cast.get_actor_rect("nami")
	var motion: Dictionary = game._cast._appearance("nami")
	var rect: Rect2 = game._cast._posed_rect("nami")
	_expect(is_equal_approx(rect.position.x, base.position.x + base.size.y * float(motion["offset_x_ratio"])), "Handoff must not add outgoing X travel into both center and local offset.")
	_expect(not game._cast._sprites["sena"].visible, "Incoming actor must wait until departure and survivor translation finish.")
	game._toggle_pause()
	game._process(2.0)
	_expect(_same(before, _handoff_state(game)), "The episode menu must freeze the outgoing movement.")
	await _open("game:lab/actor_motion_study")
	game = await _open("game:afterlight")
	_expect(_same(before, _handoff_state(game)), "A real laboratory detour must resume the same handoff geometry and clocks.")
	game._process(0.2)
	_expect(game._cast._sprites["nami"].position.x < rect.position.x, "Resumed departure must continue left rather than replay or double its displacement.")
	game._process(8.0)
	_expect(game._cast.visible_ids() == ["yuzu", "sena"] and not game._cast.is_busy(), "Resumed handoff must settle once to survivor and arrival.")
	print("PASS Walk-Away group 5: authored Nami departure, strict sequencing, pause, actual Lab detour and exact resume")


func _check_story_restless() -> void:
	var game: Control = _app.active_scene
	for index in 8:
		if str(game.current_beat()["id"]) == "riko_on_the_glass": break
		game._process(8.0)
		if game._choice_pending(): game._choose("help_first")
		else: game._next()
	game._render()
	_expect(str(game.current_beat()["id"]) == "riko_on_the_glass" and game._cast._focus.preset_id == "restless_bounce", "Riko's impatient physical entrance must select Restless Bounce.")
	var sprite: TextureRect = game._cast._sprites["riko"]
	var baseline := _rect(sprite)
	var material := sprite.material
	_expect(material == null and not bool(game._cast._projection["riko"]), "Riko must remain physical during her impatient entrance.")
	var observer := _sprite_state(game._cast._sprites["yuzu"])
	game._process(_duration(game._cast.FOCUS_CATALOG, "restless_bounce") * 0.125)
	_expect(sprite.visible and sprite.position.y < baseline.position.y and is_equal_approx(sprite.position.x, baseline.position.x), "The authored entrance must bounce Riko vertically without moving her sideways.")
	_expect(sprite.material == material and _same(observer, _sprite_state(game._cast._sprites["yuzu"])), "Riko's motion must preserve her physical appearance and leave Yuzu independent.")
	game._process(2.0)
	_expect(sprite.visible and _rect(sprite).is_equal_approx(baseline) and sprite.material == material, "The physical actor must settle visibly at baseline.")
	print("PASS Walk-Away group 6: authored physical Riko cue, independent Y-only motion and unchanged observer")


func _check_lab_controls() -> void:
	var lab := await _open("game:lab/actor_motion_study")
	_expect(lab._load_errors.is_empty(), "Actor Motion study must load all three prepared modes.")
	for mode: String in ["walk_away", "walk_away_right", "restless_bounce"]:
		for id: String in _afterlight_ids():
			lab._select_motion(mode)
			lab._select_guest(id)
			var baseline := _sprite_state(lab._cast_layer._sprites[id])
			_expect(not lab.motion_state()["playing"] and lab._cast_layer._sprites[id].visible, "Actor/mode selection must restore a visible baseline without autoplay.")
			lab._play_button.pressed.emit()
			lab._process(0.18)
			lab._pause_button.pressed.emit()
			var paused: Dictionary = lab.motion_state()
			var frozen := _sprite_state(lab._cast_layer._sprites[id])
			lab._process(2.0)
			_expect(lab.motion_state() == paused and _same(frozen, _sprite_state(lab._cast_layer._sprites[id])), "Lab pause must freeze its motion clock and actual actor.")
			var language := str(lab.get_language())
			var key := InputEventKey.new()
			key.keycode = KEY_F6
			key.pressed = true
			lab._input(key)
			_expect(lab.get_language() != language and lab.motion_state() == paused and _same(frozen, _sprite_state(lab._cast_layer._sprites[id])), "F6 must translate controls without resetting motion, actor or pause.")
			lab._pause_button.pressed.emit()
			lab._process(5.0)
			_expect(not lab.motion_state()["playing"], "Each lab cue must complete with a large delta.")
			_expect(lab._cast_layer._sprites[id].visible == (mode == "restless_bounce"), "Only exit modes end hidden in the lab.")
			lab._reset_button.pressed.emit()
			_expect(_same(baseline, _sprite_state(lab._cast_layer._sprites[id])) and not lab.motion_state()["has_played"], "Restore must cancel prior motion and show the original baseline.")
	print("PASS Walk-Away group 7: all 12 lab actor/mode combinations, explicit play, pause, F6 continuity, completion and restore")


func _capture_native() -> void:
	for window: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window
		var lab := await _open("game:lab/actor_motion_study")
		lab.set_language("ko")
		lab._select_motion("walk_away")
		lab._select_guest("nami")
		await _capture("afterlight-walk-start", lab)
		lab._play_motion()
		var last := 0.0
		for frame: Array in [["hop-one", 0.125], ["hop-two", 0.375], ["offscreen-opaque", 0.99], ["hidden", 1.0]]:
			lab._process((float(frame[1]) - last) * float(lab.motion_state()["duration"]))
			last = float(frame[1])
			await _capture("afterlight-walk-" + str(frame[0]), lab)
		lab._select_motion("restless_bounce")
		lab._play_motion()
		lab._process(float(lab.motion_state()["duration"]) * 0.125)
		await _capture("afterlight-restless-hop", lab)
		lab._process(2.0)
		await _capture("afterlight-restless-settled", lab)
		_check_ui_bounds(lab._ui)
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
		var menu := await _open("game:lab/effects_menu")
		menu.set_language("ko")
		await _capture("afterlight-effects-menu", menu)
		_check_ui_bounds(menu._ui)
	print("PASS Walk-Away group 8: native 1x/2x rendered keyframes and fixed logical controls")


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


func _handoff_state(game: Control) -> Dictionary:
	var actors := {}
	for id: String in game._textures:
		actors[id] = {"appearance": game._cast._appearance(id), "posed": game._cast._posed_rect(id)}
	return {"beat": game.current_beat()["id"], "elapsed": game._elapsed, "actors": actors, "cast_state": game._cast._cast.get_state(), "focus": _focus_state(game._cast._focus)}


func _focus_state(focus: RefCounted) -> Dictionary:
	return {"focus_id": focus.focus_id, "preset_id": focus.preset_id, "elapsed": focus.elapsed, "duration": focus.duration_seconds, "samples": focus._current_samples()}


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


func _sprite_state(sprite: TextureRect) -> Dictionary:
	return {"rect": _rect(sprite), "visible": sprite.visible, "modulate": sprite.modulate}


func _check_ui_bounds(node: Node) -> void:
	if node is BaseButton and node.is_visible_in_tree():
		_expect(Rect2(Vector2.ZERO, SIZE).encloses(node.get_global_rect()), "A lab button must fit the fixed logical canvas: " + str(node.name))
	for child: Node in node.get_children(): _check_ui_bounds(child)


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


func _rect_array(rect: Rect2) -> Array:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _open(route: String) -> Control:
	_expect(_app.open_route(route), "Application route must open: " + route)
	await _settle()
	var scene: Control = _app.active_scene
	_expect(scene._load_errors.is_empty(), "Route must initialize: " + route + " " + str(scene._load_errors))
	return scene


func _freeze_route(node: Node) -> void:
	if node.has_method("current_beat") or node.has_method("motion_state") or node.has_method("_route_key"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _app.active_scene != null: _app.active_scene.set_process(false)


func _same(a: Variant, b: Variant) -> bool:
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size(): return false
		for key: Variant in a:
			if not b.has(key) or not _same(a[key], b[key]): return false
		return true
	if a is Array and b is Array:
		if a.size() != b.size(): return false
		for index in a.size():
			if not _same(a[index], b[index]): return false
		return true
	if (a is float or a is int) and (b is float or b is int): return is_equal_approx(float(a), float(b))
	if a is Rect2 and b is Rect2: return a.is_equal_approx(b)
	return a == b


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)


func _finish() -> void:
	if _capture_enabled:
		DirAccess.make_dir_recursive_absolute(CAPTURES)
		var record := FileAccess.open(CAPTURES.path_join("motion-paths.json"), FileAccess.WRITE)
		record.store_string(JSON.stringify({"paths": _paths, "errors": _errors, "capture_count": _capture_count}, "\t"))
	for issue: String in _errors: printerr("FAIL Walk-Away: " + issue)
	if _errors.is_empty():
		print("PASS Walk-Away integration: both renderers, all prepared casts, left/right travel, repeated Y motion, terminal visibility, manpu composition, actual story/Lab resume and laboratory controls")
		if _capture_count > 0: print("Walk-Away native captures: " + str(_capture_count))
	quit(0 if _errors.is_empty() else 1)
