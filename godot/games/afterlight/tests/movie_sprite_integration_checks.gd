extends SceneTree

## Real prepared movie sprites are tested through the actual Lab route. Native
## capture mode also runs two wall-clock loops and records every supported face.
const DESIGN_SIZE := Vector2i(1280, 900)
const DIRECTORY := "res://tests/movie-sprite"
const ACTORS := ["yuzu", "riko"]
const EYES := {"yuzu": ["rest", "eyes_half", "eyes_closed"], "riko": ["rest", "eyes_closed"]}
const MOUTHS := ["rest", "mouth_a", "mouth_o"]
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false
var _checks := 0
var _evidence := {"schema_version": 1, "checks": [], "captures": [], "states": []}


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-movie-sprite")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Movie sprite captures require a native renderer.")
		quit(2)
		return
	root.size = DESIGN_SIZE
	node_added.connect(_freeze_routes)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	if not _expect(_app.selected_game_id == "afterlight", "Begin from the real Afterlight story root."):
		await _finish()
		return
	var story: Control = _app.active_scene
	if not _expect(story._load_errors.is_empty(), "The existing story initializes before the diagnostic detour."):
		await _finish()
		return
	story._process(0.2)
	var saved: Dictionary = story.save_game()
	if not _expect(_app.open_route("game:lab/movie_sprite_study"), "Movie sprite diagnostic is an explicit Afterlight Lab route."):
		await _finish()
		return
	await _settle()
	var study: Control = _app.active_scene
	if not await _wait_ready(study):
		await _finish()
		return
	_expect(_app.selected_game_id == "lab" and _app.current_route == "movie_sprite_study", "The diagnostic belongs to Lab, separately from episode progression.")
	_expect(study._players.size() == 2, "The diagnostic binds exactly Yuzu and Riko.")
	await _clock_and_controls(study)
	await _face_states(study, DESIGN_SIZE)
	if _capture_enabled: await _alpha_and_registration(study)
	await _speech_and_language(study)
	if _capture_enabled:
		await _real_time_loops(study)
		await _moving_face_samples(study)
		await _face_states(study, DESIGN_SIZE * 2)
		await _alpha_and_registration(study)
	await _lifecycle(study, saved)
	await _finish()


func _clock_and_controls(study: Control) -> void:
	study.stop_line()
	study.restart_loops()
	await _wait_ready(study)
	study._eye_pickers.yuzu.item_selected.emit(3)
	_expect(_state(study, "yuzu").eyes == "eyes_closed" and _state(study, "riko").eyes == "rest", "The Yuzu eye selector controls Yuzu only.")
	study._eye_pickers.riko.item_selected.emit(2)
	_expect(_state(study, "riko").eyes == "eyes_closed", "The Riko selector invokes the canvas-left wink.")
	study._mouth_pickers.yuzu.item_selected.emit(2)
	_expect(_state(study, "yuzu").mouth == "mouth_a" and _state(study, "riko").mouth == "rest", "The Yuzu mouth selector stays bound to Yuzu.")
	study._mouth_pickers.riko.item_selected.emit(3)
	_expect(_state(study, "riko").mouth == "mouth_o", "The Riko mouth selector stays bound to Riko.")
	for actor: String in ACTORS:
		study._eye_pickers[actor].item_selected.emit(0)
		study._mouth_pickers[actor].item_selected.emit(0)
	for actor: String in ACTORS:
		var initial := _state(study, actor)
		_expect(int(initial.get("frame_index", -1)) == 0 and int(initial.get("loop_count", -1)) == 0, actor + " replay returns to frame zero without replacing the scene.")
	for step in 202:
		study._process(0.125)
		if not await _wait_ready(study): return
	for actor: String in ACTORS:
		var state := _state(study, actor)
		_expect(int(state.get("loop_count", 0)) >= 2, actor + " crosses at least two 12-second loop boundaries.")
		_expect(int(state.get("frame_index", -1)) >= 0 and int(state.get("frame_index", 192)) < 192, actor + " keeps the 192-frame timebase in range.")
		_expect(int(state.get("resident_page_count", 99)) <= 2 and int(state.get("max_resident_pages", 0)) == 2, actor + " uses a bounded two-page cache.")
		_evidence.states.append({"phase": "repeated_wraps", "actor": actor, "state": state})
	study.toggle_pause()
	var before := _states(study)
	study._process(2.0)
	await _wait_ready(study)
	_expect(_same_clocks(before, _states(study)), "Paused body clocks and face states do not advance.")
	study.select_language("ko")
	study._process(0.0)
	_expect(_same_clocks(before, _states(study)), "Changing language preserves paused body playback.")
	study.toggle_pause()
	study._process(0.25)
	await _wait_ready(study)
	for actor: String in ACTORS:
		_expect(float(_state(study, actor).get("clock_seconds", 0.0)) > float(before[actor].get("clock_seconds", 0.0)), actor + " resumes its existing clock.")
	study.restart_loops()
	await _wait_ready(study)
	for actor: String in ACTORS:
		_expect(int(_state(study, actor).get("frame_index", -1)) == 0, actor + " can replay after repeated wraps.")


func _face_states(study: Control, window_size: Vector2i) -> void:
	root.size = window_size
	await _settle()
	study.stop_line()
	study.restart_loops()
	await _wait_ready(study)
	study.toggle_pause()
	var before := _states(study)
	for actor: String in ACTORS:
		for other: String in ACTORS:
			study.select_eye(other, "rest")
			study.select_mouth(other, "rest")
		for eyes: String in EYES[actor]:
			for mouth: String in MOUTHS:
				study.select_eye(actor, eyes)
				study.select_mouth(actor, mouth)
				study._process(0.0)
				var state := _state(study, actor)
				_expect(str(state.get("eyes")) == eyes and str(state.get("mouth")) == mouth, "%s admits independent %s / %s controls." % [actor, eyes, mouth])
				_expect(_same_body_clocks(before, _states(study)), "Facial replacement does not restart or retime body playback.")
				await _capture("%s-%s-%s-%d" % [actor, eyes, mouth, window_size.x], study)
	study.select_eye("yuzu", "rest")
	study.select_mouth("yuzu", "rest")
	study.select_eye("riko", "rest")
	study.select_mouth("riko", "rest")
	study.toggle_pause()
	_expect(study.size.is_equal_approx(Vector2(DESIGN_SIZE)) and root.content_scale_mode == Window.CONTENT_SCALE_MODE_CANVAS_ITEMS, "Movie sprites retain the logical canvas at native window resolution.")


func _speech_and_language(study: Control) -> void:
	study.stop_line()
	for actor: String in ACTORS: study.select_mouth(actor, "auto")
	for language: String in ["en", "ko"]:
		study.select_language(language)
		for index in 2:
			study.play_line(index)
			var mouth_states: Array[String] = []
			for step in 8:
				study._process(0.11)
				await _wait_ready(study)
				var view: Dictionary = study.study_state()
				var speaker: String = ACTORS[index] if bool(view.get("speaking", false)) else ""
				if ACTORS.has(speaker):
					mouth_states.append(str(_state(study, speaker).get("mouth", "")))
				for actor: String in ACTORS:
					if actor != speaker:
						_expect(str(_state(study, actor).get("mouth", "")) == "rest", "Only the selected speaker animates her mouth.")
			_expect(mouth_states.has("mouth_a") or mouth_states.has("mouth_o"), "The %s diagnostic line %d visibly drives speech mouth states." % [language, index])
			await _capture("spoken-%s-%d" % [language, index], study)
			study.stop_line()
			for actor: String in ACTORS:
				_expect(str(_state(study, actor).get("mouth", "")) == "rest", "Stopping speech restores the mouth to the moving body's rest state.")
	_expect(study._load_errors.is_empty(), "Prepared bilingual playback and controls remain error-free.")


func _real_time_loops(study: Control) -> void:
	study.stop_line()
	study.restart_loops()
	await _wait_ready(study)
	var initial := _states(study)
	var started := Time.get_ticks_msec()
	var previous := started
	while int(_state(study, "yuzu").get("loop_count", 0)) < 2 or int(_state(study, "riko").get("loop_count", 0)) < 2:
		await process_frame
		var now := Time.get_ticks_msec()
		study._process(float(now - previous) / 1000.0)
		previous = now
		if now - started > 60000:
			_expect(false, "Two native real-time loops complete within the bounded 60-second check.")
			return
	_expect(study._load_errors.is_empty(), "Native wall-clock playback completes two wraps without decoding failure.")
	_evidence.states.append({"phase": "native_wall_clock", "elapsed_seconds": float(Time.get_ticks_msec() - started) / 1000.0, "initial": initial, "players": _states(study)})
	await _capture("two-live-wraps", study)


func _moving_face_samples(study: Control) -> void:
	study.stop_line()
	study.toggle_pause()
	for actor: String in ACTORS:
		study.select_eye(actor, "eyes_closed")
		study.select_mouth(actor, "mouth_a")
	for frame_index in [0, 48, 96, 144, 191]:
		for actor: String in ACTORS:
			_expect(study._players[actor].seek(float(frame_index) / 16.0).is_empty(), "A sampled body frame remains available under independent face controls.")
		await _wait_ready(study)
		for actor: String in ACTORS:
			_expect(int(_state(study, actor).frame_index) == frame_index and _state(study, actor).eyes == "eyes_closed" and _state(study, actor).mouth == "mouth_a", "Seeking body motion preserves both independent facial states.")
		await _capture("moving-face-%03d" % frame_index, study)
	study.toggle_pause()
	study.restart_loops()
	await _wait_ready(study)


func _alpha_and_registration(study: Control) -> void:
	study.stop_line()
	study.restart_loops()
	await _wait_ready(study)
	study.toggle_pause()
	study._contrast = true
	study.queue_redraw()
	for actor: String in ACTORS:
		study.select_eye(actor, "rest")
		study.select_mouth(actor, "rest")
		study._players[actor].hide()
	var background: Image = await _frame_image()
	for actor: String in ACTORS: study._players[actor].show()
	var body: Image = await _frame_image()
	var transparent_samples := 0
	var unexpected_opaque := 0
	for actor: String in ACTORS:
		var manifest_result: Dictionary = study.content.content_loader.read_json("assets/movie_sprite/%s/manifest.json" % actor)
		var manifest: Dictionary = manifest_result.value
		var page_result: Dictionary = study.content.content_loader.read_bytes(manifest.pages[0].file)
		var source := Image.new()
		_expect(source.load_png_from_buffer(page_result.bytes) == OK, "Independently decode the first body page for alpha checks.")
		var transform: Transform2D = root.get_final_transform() * study._players[actor].get_global_transform()
		for y in range(12, 830, 24):
			for x in range(12, 708, 24):
				var blank := true
				for offset_y in range(-2, 3):
					for offset_x in range(-2, 3):
						if source.get_pixel(x + offset_x, y + offset_y).a > 0.0: blank = false
				if not blank: continue
				var point := Vector2i(transform * Vector2(x, y))
				if point.y >= int(660 * root.get_final_transform().get_scale().y): continue
				transparent_samples += 1
				if _color_difference(body.get_pixelv(point), background.get_pixelv(point)) > 0.012:
					unexpected_opaque += 1
		var face_rect := Rect2()
		for family: String in ["eyes", "mouths"]:
			var state_name := "eyes_closed" if family == "eyes" else "mouth_o"
			var face_result: Dictionary = study.content.content_loader.read_bytes(manifest[family][state_name].file)
			var face := Image.new()
			_expect(face.load_png_from_buffer(face_result.bytes) == OK, "Independently decode the replacement support.")
			var region := Rect2(face.get_used_rect()).grow(3.0)
			face_rect = region if face_rect.size == Vector2.ZERO else face_rect.merge(region)
		study.select_eye(actor, "eyes_closed")
		study.select_mouth(actor, "mouth_o")
		var changed: Image = await _frame_image()
		var allowed: Rect2 = transform * face_rect
		var changed_inside := 0
		var changed_outside := 0
		for y in range(int(78 * root.get_final_transform().get_scale().y), int(658 * root.get_final_transform().get_scale().y), 2):
			for x in range(body.get_width()):
				if _color_difference(body.get_pixel(x, y), changed.get_pixel(x, y)) <= 0.012: continue
				if allowed.has_point(Vector2(x, y)): changed_inside += 1
				else: changed_outside += 1
		_expect(changed_inside > 30 and changed_outside == 0, "%s replacement changes visible pixels only within its recorded source-space face support (%d inside, %d outside)." % [actor, changed_inside, changed_outside])
		study.select_eye(actor, "rest")
		study.select_mouth(actor, "rest")
	_expect(transparent_samples > 100 and unexpected_opaque == 0, "The actual native shader preserves source transparency over the checkerboard (%d samples, %d unexpected)." % [transparent_samples, unexpected_opaque])
	await _capture("alpha-check-%d" % root.size.x, study)
	study._contrast = false
	study.queue_redraw()
	study.toggle_pause()


func _color_difference(left: Color, right: Color) -> float:
	return maxf(absf(left.r - right.r), maxf(absf(left.g - right.g), absf(left.b - right.b)))


func _frame_image() -> Image:
	await _settle()
	RenderingServer.force_draw(false)
	return root.get_texture().get_image()


func _lifecycle(study: Control, saved: Dictionary) -> void:
	var weak_study: WeakRef = weakref(study)
	var players: Array[WeakRef] = []
	for actor: String in ACTORS:
		players.append(weakref(study._players[actor]))
	study.play_line(0)
	_expect(_app.open_route("effects_menu"), "The diagnostic can leave while body decoding and speech are active.")
	await _settle()
	_expect(weak_study.get_ref() == null, "Scene replacement releases the diagnostic route.")
	for player: WeakRef in players:
		_expect(player.get_ref() == null, "Scene removal releases the player's frame cache and node.")
	_expect(_app.open_route("game:afterlight"), "Returning from Lab resumes the existing story.")
	await _settle()
	var restored: Control = _app.active_scene
	_expect(restored._load_errors.is_empty(), "The resumed story accepts its preserved checkpoint.")
	var actual: Dictionary = restored.save_game()
	_evidence.states.append({"phase": "story_checkpoint", "expected": saved, "actual": actual})
	_expect(actual.get("session") == saved.get("session") and is_equal_approx(float(actual.get("elapsed", -1.0)), float(saved.get("elapsed", -2.0))), "The diagnostic detour preserves Scenario identity and story time.")
	_expect(_app.open_route("game:lab/movie_sprite_study"), "The diagnostic can be entered again after cleanup.")
	await _settle()
	var reopened: Control = _app.active_scene
	if await _wait_ready(reopened):
		for actor: String in ACTORS:
			_expect(int(_state(reopened, actor).get("loop_count", -1)) == 0, "A new diagnostic scene starts a fresh body clock.")


func _state(study: Control, actor: String) -> Dictionary:
	return study._players[actor].snapshot()


func _states(study: Control) -> Dictionary:
	var result := {}
	for actor: String in ACTORS: result[actor] = _state(study, actor)
	return result


func _same_body_clocks(left: Dictionary, right: Dictionary) -> bool:
	for actor: String in ACTORS:
		for key: String in ["clock_seconds", "frame_index", "loop_count"]:
			if left[actor].get(key) != right[actor].get(key): return false
	return true


func _same_clocks(left: Dictionary, right: Dictionary) -> bool:
	if not _same_body_clocks(left, right): return false
	for actor: String in ACTORS:
		for key: String in ["eyes", "mouth"]:
			if left[actor].get(key) != right[actor].get(key): return false
	return true


func _wait_ready(study: Control) -> bool:
	var started := Time.get_ticks_msec()
	while Time.get_ticks_msec() - started < 20000:
		study._process(0.0)
		if not study._load_errors.is_empty():
			return _expect(false, "Movie sprite initialization/playback errors: " + str(study._load_errors))
		var ready: bool = study._players.size() == 2
		for actor: String in ACTORS:
			if not study._players.has(actor):
				ready = false
				continue
			var state := _state(study, actor)
			if str(state.get("state", "")) == "failed":
				return _expect(false, "Movie sprite decode failed: " + str(state.get("errors", [])))
			if bool(state.get("buffering", true)): ready = false
		if ready: return true
		await process_frame
	return _expect(false, "Prepared movie pages become ready within twenty seconds.")


func _capture(label: String, study: Control) -> void:
	if not _capture_enabled: return
	_expect(DirAccess.make_dir_recursive_absolute(DIRECTORY) == OK, "The native capture directory is writable.")
	await _settle()
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	var path := DIRECTORY.path_join(label + ".png")
	_expect(image.get_size() == root.size and image.save_png(path) == OK, "The diagnostic captures actual native window pixels: " + label)
	_evidence.captures.append({"file": path, "sha256": FileAccess.get_sha256(path), "window_size": [image.get_width(), image.get_height()], "players": _states(study)})


func _freeze_routes(node: Node) -> void:
	if node.has_method("study_state") or node.has_method("save_game"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _settle() -> void:
	for frame in 4:
		await process_frame
		if _app != null and _app.active_scene != null: _app.active_scene.set_process(false)


func _expect(condition: bool, message: String) -> bool:
	_checks += 1
	if not condition: _errors.append(message)
	_evidence.checks.append({"passed": condition, "message": message})
	return condition


func _finish() -> void:
	if _app != null:
		_app.queue_free()
		_app = null
		await _settle()
	DirAccess.make_dir_recursive_absolute(DIRECTORY)
	_evidence["failed"] = _errors.duplicate()
	_evidence["native_captures"] = _capture_enabled
	_evidence["check_count"] = _checks
	var file := FileAccess.open(DIRECTORY.path_join("native-summary.json" if _capture_enabled else "summary.json"), FileAccess.WRITE)
	if file != null: file.store_string(JSON.stringify(_evidence, "\t") + "\n")
	for issue: String in _errors: printerr("FAIL Movie Sprite Integration: " + issue)
	if _errors.is_empty(): print("PASS Movie Sprite Integration: %d checks; body loops, independent face controls, bounded loading, speaker/language policy, pause/replay and story/Lab lifecycle; native visual review remains separate" % _checks)
	quit(0 if _errors.is_empty() else 1)
