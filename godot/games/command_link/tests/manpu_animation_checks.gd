extends RefCounted

## Independent lifecycle and renderer proof for per-pair manpu animation.
const MANPU = preload("res://addons/game_presentation/actors/manpu_animation.gd")
const CATALOG := "res://addons/game_presentation/actors/presets/manpu.json"
const DESIGN_SIZE := Vector2(1280, 900)
const NEUTRAL := {"offset_x_ratio": 0.0, "offset_y_ratio": 0.0, "scale": 1.0, "opacity": 1.0, "brightness": 1.0}
const FIRST := {"actor": "mira", "id": "sweat_drop"}
const SECOND := {"actor": "lena", "id": "sweat_drop"}
var _errors: Array[String] = []
var _capture_count := 0


func run(root: Control, options: Dictionary) -> void:
	_check_controller()
	await _check_runtime(root)
	if _errors.is_empty() and options.has("capture-manpu-animation"):
		if DisplayServer.get_name() == "headless":
			_errors.append("Manpu animation captures require a real renderer.")
		else:
			await _capture_proof(root, String(options.get("capture-dir", "res://tests/manpu-animation/captures")))
	for issue: String in _errors:
		printerr("FAIL Manpu animation: " + issue)
	if _errors.is_empty():
		print("PASS Manpu animation: independent pair clocks, introduction/removal/reintroduction, targeted replay, atomic validation, continuous preset change, composed geometry/color, frozen clocks, gallery/reset/resume")
		if _capture_count > 0:
			print("Manpu animation captures complete: %d PNG and metadata pairs" % _capture_count)
	root.get_tree().quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _equal(left: Dictionary, right: Dictionary) -> bool:
	for channel: String in NEUTRAL:
		if not left.has(channel) or not right.has(channel) or not is_equal_approx(float(left[channel]), float(right[channel])):
			return false
	return true


func _states(animation: MANPU) -> Dictionary:
	return animation.get_state()["states"]


func _time(animation: MANPU, actor: String, id: String) -> float:
	var states: Dictionary = _states(animation)
	return float(states[actor + ":" + id]["elapsed"]) if states.has(actor + ":" + id) else -1.0


func _sample_cue(animation: MANPU, cue: Dictionary) -> Dictionary:
	return animation.sample(String(cue["actor"]), String(cue["id"]))


func _check_controller() -> void:
	var animation: MANPU = MANPU.new()
	_expect(animation.initialize(CATALOG).is_empty(), "The checked-in manpu preset catalog must initialize.")
	if not animation.initialized:
		return
	var ids: Array[String] = []
	for preset: Dictionary in animation.get_presets():
		ids.append(String(preset["id"]))
	_expect(ids == ["none", "shake", "scale_pulse", "fade_in", "sigh_puff", "step_loop", "frame_loop", "sweat_drop_fall"], "The manpu presets must retain their declared order and append the falling-sweat example.")
	animation.configure("fade_in")
	animation.sync([FIRST])
	_expect(is_zero_approx(float(_sample_cue(animation, FIRST)["opacity"])), "A newly introduced fade must begin at authored opacity zero.")
	animation.advance(0.08)
	var previous: Dictionary = animation.get_state()
	animation.sync([FIRST])
	animation.configure("fade_in")
	_expect(animation.get_state() == previous, "The same pair and preset must preserve the current clock.")
	animation.sync([SECOND, FIRST])
	_expect(is_equal_approx(_time(animation, "mira", "sweat_drop"), 0.08) and is_zero_approx(_time(animation, "lena", "sweat_drop")), "Adding another actor's same mark must create an independent clock.")
	animation.advance(0.04)
	_expect(is_equal_approx(_time(animation, "mira", "sweat_drop"), 0.12) and is_equal_approx(_time(animation, "lena", "sweat_drop"), 0.04), "Concurrent marks must retain their different introduction times.")
	previous = animation.get_state()
	animation.sync([FIRST, SECOND], false)
	_expect(animation.get_state() == previous, "Cue order and settled sync must not restart or settle existing pairs.")
	var second_before: Dictionary = _sample_cue(animation, SECOND)
	animation.replay("mira", "sweat_drop")
	_expect(is_zero_approx(_time(animation, "mira", "sweat_drop")) and is_zero_approx(float(_sample_cue(animation, FIRST)["opacity"])), "Named replay must restart that pair's authored introduction.")
	_expect(is_equal_approx(_time(animation, "lena", "sweat_drop"), 0.04) and _equal(second_before, _sample_cue(animation, SECOND)), "Named replay must leave the other pair unchanged.")
	animation.sync([SECOND])
	_expect(not _states(animation).has("mira:sweat_drop"), "Removed cues must discard their animation state.")
	animation.advance(0.03)
	animation.sync([FIRST, SECOND])
	_expect(is_zero_approx(_time(animation, "mira", "sweat_drop")) and is_equal_approx(_time(animation, "lena", "sweat_drop"), 0.07), "Reintroduced cues must reset without disturbing surviving marks.")
	var another: Dictionary = {"actor": "mira", "id": "surprise"}
	animation.sync([FIRST, SECOND, another], false)
	_expect(is_equal_approx(float(_sample_cue(animation, another)["opacity"]), 1.0) and is_zero_approx(_time(animation, "mira", "sweat_drop")), "Settled sync must affect only newly added pairs, including a second mark on one actor.")
	animation.replay()
	for state: Dictionary in _states(animation).values():
		_expect(is_zero_approx(float(state["elapsed"])), "Replay all must restart every active pair.")
	animation.advance(0.06)
	var samples_before: Array[Dictionary] = [_sample_cue(animation, FIRST), _sample_cue(animation, SECOND)]
	animation.configure("shake")
	_expect(_equal(samples_before[0], _sample_cue(animation, FIRST)) and _equal(samples_before[1], _sample_cue(animation, SECOND)), "Changing presets must preserve each current sample continuously.")
	animation.advance(3.0)
	_expect(_equal(_sample_cue(animation, FIRST), NEUTRAL), "Completed shake must settle to identity without fading residue.")
	animation.clear()
	animation.sync([FIRST])
	animation.advance(0.36 * 0.12)
	_expect(is_equal_approx(float(_sample_cue(animation, FIRST)["offset_y_ratio"]), -0.08), "Shake must reach its authored upward displacement.")
	animation.configure("scale_pulse")
	animation.replay()
	animation.advance(0.3 * 0.45)
	_expect(is_equal_approx(float(_sample_cue(animation, FIRST)["scale"]), 1.12), "Scale pulse must reach its authored enlargement.")
	previous = animation.get_state()
	var detached: Dictionary = animation.get_state()
	detached["states"]["mira:sweat_drop"]["elapsed"] = 100.0
	var detached_sample: Dictionary = _sample_cue(animation, FIRST)
	detached_sample["scale"] = 100.0
	for index in 10:
		_sample_cue(animation, FIRST)
	_expect(animation.get_state() == previous, "Sampling and returned state mutation must not alter active clocks.")
	_check_invalid(animation)
	animation.configure("none")
	_expect(_equal(_sample_cue(animation, FIRST), NEUTRAL), "None must immediately restore the original mark appearance.")
	animation.sync([])
	_expect(_states(animation).is_empty() and _equal(animation.sample("absent", "absent"), NEUTRAL), "An empty cue set must discard all pairs and return neutral absent samples.")
	animation.clear()
	_expect(_states(animation).is_empty(), "Clear must leave no pair state.")


func _check_invalid(animation: MANPU) -> void:
	var initial: Dictionary = animation.get_state()
	_expect(not animation.configure("missing").is_empty(), "Unknown presets must be rejected.")
	for cues: Array in [[FIRST, FIRST], [{"actor": "mira", "id": ""}], [{"actor": "mira:other", "id": "heart"}], [{"actor": "mira", "id": "heart", "extra": true}], [42]]:
		_expect(not animation.sync(cues).is_empty() and animation.get_state() == initial, "Malformed cue sets must fail atomically.")
	_expect(not animation.replay("mira").is_empty(), "A partial replay target must be rejected.")
	_expect(not animation.replay("lena", "missing").is_empty(), "An absent replay target must not create a cue.")
	animation.advance(-1.0)
	animation.advance(INF)
	animation.advance(NAN)
	_expect(animation.get_state() == initial, "Invalid operations must preserve every active clock.")
	var valid: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
	var duplicate: Dictionary = valid.duplicate(true)
	duplicate["presets"].append(duplicate["presets"][0].duplicate(true))
	var unknown: Dictionary = valid.duplicate(true)
	unknown["presets"][0]["tracks"]["rotation"] = [[0, 0], [1, 1]]
	var invalid: Dictionary = valid.duplicate(true)
	invalid["presets"][0]["tracks"]["opacity"] = [[0, -0.1], [1, 1]]
	var temporary: String = "/tmp/manpu_animation_checks_%d.json" % OS.get_process_id()
	for catalog: Dictionary in [duplicate, unknown, invalid]:
		var file: FileAccess = FileAccess.open(temporary, FileAccess.WRITE)
		file.store_string(JSON.stringify(catalog))
		file.close()
		_expect(not animation.initialize(temporary).is_empty() and animation.get_state() == initial, "Invalid preset catalogs must not replace an active controller.")
	var malformed: FileAccess = FileAccess.open(temporary, FileAccess.WRITE)
	malformed.store_string("{bad json")
	malformed.close()
	_expect(not animation.initialize(temporary).is_empty() and animation.get_state() == initial, "Malformed JSON must be rejected atomically.")
	invalid = valid.duplicate(true)
	invalid["presets"][0]["tracks"]["opacity"] = [[0, NAN], [1, 1]]
	var checked: Dictionary = animation.call("_validate_catalog", invalid)
	_expect(not (checked["errors"] as Array).is_empty() and animation.get_state() == initial, "Nonfinite channels must fail validation without mutation.")
	DirAccess.remove_absolute(temporary)


func _controller(scene: Control) -> MANPU:
	return scene.get("_manpu_animation") as MANPU


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
	_expect((scene.get("_load_errors") as Array).is_empty(), "Route artwork and animation initialization must succeed.")
	return scene


func _tick(scene: Control, seconds: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", seconds)
	scene.set("_capture_frozen", true)


func _prepare(scene: Control, preset: String, line_index: int = 0, focus_preset: String = "none") -> void:
	scene.set("_dialogue_index", line_index)
	scene.call("set_actor_focus_preset", focus_preset)
	var focus: RefCounted = scene.get("_actor_focus")
	focus.call("clear")
	scene.call("set_manpu_animation_preset", preset)
	_controller(scene).clear()
	scene.call("_sync_actor_focus")
	scene.call("_sync_manpu_animation")
	scene.call("_update_interface")


func _mark_rect(scene: Control, method: String, actor: String = "mira", id: String = "surprise") -> Rect2:
	return scene.call(method, DESIGN_SIZE, actor, id)


func _check_runtime(root: Control) -> void:
	var scene: Control = await _open(root, "demos/manpu")
	_prepare(scene, "shake", 0, "scale_pulse")
	_tick(scene, 0.0432)
	var base: Rect2 = _mark_rect(scene, "_manpu_rect")
	var presented: Rect2 = _mark_rect(scene, "_presented_manpu_rect")
	var actor_rect: Rect2 = scene.call("_presented_dialogue_rect", DESIGN_SIZE, 0)
	_expect(is_equal_approx(base.size.y / actor_rect.size.y, 0.1), "The attached mark must follow its owner's animated scale.")
	_expect(is_equal_approx(presented.get_center().y - base.get_center().y, -0.08 * base.size.y), "Local shake must use the current attached mark height.")
	_expect(presented.size.is_equal_approx(base.size), "Shake must not change mark scale.")
	_prepare(scene, "scale_pulse", 0, "bounce")
	_tick(scene, 0.135)
	base = _mark_rect(scene, "_manpu_rect")
	presented = _mark_rect(scene, "_presented_manpu_rect")
	_expect(is_equal_approx(presented.size.y / base.size.y, 1.12) and presented.get_center().is_equal_approx(base.get_center()), "Local enlargement must use the owner-attached center as its pivot.")
	var frozen: Dictionary = _controller(scene).get_state()
	for index in 10:
		scene.call("_layout_interface")
		scene.call("_update_character_layers")
		scene.call("_process", 0.4)
	_expect(_controller(scene).get_state() == frozen and _mark_rect(scene, "_presented_manpu_rect").is_equal_approx(presented), "Frozen redraw and layout must not advance or restart mark clocks.")
	_prepare(scene, "fade_in", 6, "listener_fade")
	var focus: RefCounted = scene.get("_actor_focus")
	focus.call("advance", 1.0)
	_controller(scene).advance(0.1)
	scene.set("_entry", 0.5)
	scene.call("_update_character_layers")
	var color: Color = scene.call("_manpu_color", "lena", "sparkle")
	_expect(is_equal_approx(color.a, 0.25), "Entry alpha and local fade opacity must multiply once, independently of owner opacity.")
	_expect(is_equal_approx(color.r, 1.0) and is_equal_approx(color.g, 1.0) and is_equal_approx(color.b, 1.0), "Actor focus tint must not recolor the painted mark.")
	var effects: Dictionary = scene.get("_character_effects")
	effects["lena"]["enabled"] = true
	scene.call("_update_character_layers")
	_expect((scene.get("_actor_overlay") as Control).material == null and (scene.call("_manpu_color", "lena", "sparkle") as Color).is_equal_approx(color), "The actor hologram must leave mark color and its foreground canvas independent.")
	scene.set("_entry", 1.0)
	_prepare(scene, "fade_in", 3)
	_tick(scene, 0.1)
	var other_time: float = _time(_controller(scene), "mira", "sweat_drop")
	scene.set("_manpu_target_index", -1)
	scene.call("_route_key", KEY_T)
	scene.call("_route_key", KEY_F)
	_expect(is_zero_approx(_time(_controller(scene), "lena", "anger_vein")) and is_equal_approx(_time(_controller(scene), "mira", "sweat_drop"), other_time), "T/F replay must restart the selected pair and preserve the other mark.")
	scene.call("_route_key", KEY_G)
	_expect(_states(_controller(scene)).is_empty(), "The gallery must discard conversational mark clocks.")
	scene.call("_route_key", KEY_G)
	_expect(is_zero_approx(_time(_controller(scene), "lena", "anger_vein")), "Returning from the gallery must introduce visible conversation marks afresh.")
	scene.call("_route_key", KEY_R)
	_expect(String(scene.get("manpu_animation_preset")) == "shake" and _states(_controller(scene)).size() == 1 and is_zero_approx(_time(_controller(scene), "mira", "surprise")), "Demo reset must restore the default preset and opening cue.")
	scene = await _open(root, "new_game")
	scene.call("skip_establishing")
	scene.set("_entry", 1.0)
	scene.call("_update_interface")
	_tick(scene, 0.08)
	root.call("open_route", "demos/manpu")
	scene = await _open(root, "game")
	var resumed: Dictionary = _states(_controller(scene))
	_expect(not resumed.is_empty(), "The resumed opening beat must retain its authored mark.")
	for state: Dictionary in resumed.values():
		_expect(is_equal_approx(float(state["elapsed"]), float(state["duration_seconds"])), "Game resume must settle current introductions rather than replay them.")
	scene = await _open(root, "demos/actor_focus")
	_expect(String(scene.get("manpu_animation_preset")) == "none", "Actor Focus must retain independent, static manpu by default.")


func _capture_proof(root: Control, folder: String) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "Cannot create the manpu capture directory.")
	var scene: Control = await _open(root, "demos/manpu")
	scene.call("_select_location", "forward_command", true)
	scene.set("_capturing", true)
	scene.set("_natural_blink", false)
	scene.set("_blink_remaining", 0.0)
	scene.set("_location_title_elapsed", 3.7)
	scene.set("_elapsed", 1.0)
	scene.call("_update_location_title")
	var sequences := {
		"shake": [0.0, 0.0432, 0.1008, 0.1584, 0.216, 0.36],
		"scale_pulse": [0.0, 0.075, 0.135, 0.225, 0.3],
		"fade_in": [0.0, 0.05, 0.1, 0.15, 0.2],
		"combined": [0.0, 0.0432, 0.1, 0.16, 0.3, 0.42]}
	for name: String in sequences:
		var path: String = folder.path_join(name)
		DirAccess.make_dir_recursive_absolute(path)
		_prepare(scene, "shake" if name == "combined" else name, 0, "bounce" if name == "combined" else "none")
		var previous := 0.0
		for phase: float in sequences[name]:
			_tick(scene, phase - previous)
			previous = phase
			await _capture(root, scene, path, "frame_%04d" % roundi(phase * 10000.0), phase)
	var multi_path: String = folder.path_join("targeted_replay")
	DirAccess.make_dir_recursive_absolute(multi_path)
	_prepare(scene, "fade_in", 3)
	_tick(scene, 0.1)
	await _capture(root, scene, multi_path, "before_replay", 0.1)
	scene.call("_replay_manpu_animation", "lena", "anger_vein")
	await _capture(root, scene, multi_path, "replay_lena", 0.1)
	_tick(scene, 0.05)
	await _capture(root, scene, multi_path, "after_0050", 0.15)
	_tick(scene, 0.05)
	await _capture(root, scene, multi_path, "after_0100", 0.2)
	_prepare(scene, "none")
	await _capture(root, scene, folder, "none", 0.0)


func _rect_array(rect: Rect2) -> Array[float]:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _capture(root: Control, scene: Control, folder: String, name: String, sequence_time: float) -> void:
	root.get_viewport().gui_release_focus()
	if root.get_viewport().gui_get_hovered_control() != null:
		root.get_viewport().notify_mouse_exited()
	scene.call("_update_interface")
	await root.get_tree().process_frame
	scene.queue_redraw()
	for index in 4:
		RenderingServer.force_draw(false)
	var picture: Image = root.get_viewport().get_texture().get_image()
	_expect(picture.get_size() == Vector2i(1280, 900) and picture.save_png(folder.path_join(name + ".png")) == OK, "Cannot save a logical viewport capture: " + name)
	var output: Transform2D = root.get_viewport().get_final_transform()
	var extent: Vector2 = output.basis_xform(DESIGN_SIZE)
	var metadata := {"state": name, "route": "demos/manpu", "sequence_time_seconds": sequence_time,
		"capture_space": "logical_viewport", "viewport": [1280, 900], "window_size": [root.get_window().size.x, root.get_window().size.y],
		"output_rect": [output.origin.x, output.origin.y, extent.x, extent.y], "output_scale": [output.x.x, output.y.y],
		"manpu_animation": _controller(scene).get_state(), "actor_focus_preset": scene.get("actor_focus_preset"),
		"entry": scene.get("_entry"), "marks": [], "actor_rects": {}}
	var cues: Array = scene.call("_active_manpu")
	for cue: Dictionary in cues:
		var actor: String = cue["actor"]
		var id: String = cue["id"]
		var color: Color = scene.call("_manpu_color", actor, id)
		metadata["marks"].append({"actor": actor, "id": id, "channels": _controller(scene).sample(actor, id),
			"attached_rect": _rect_array(_mark_rect(scene, "_manpu_rect", actor, id)),
			"presented_rect": _rect_array(_mark_rect(scene, "_presented_manpu_rect", actor, id)), "color": [color.r, color.g, color.b, color.a]})
	var actors: Dictionary = scene.get("_actor_nodes")
	for id: String in actors:
		metadata["actor_rects"][id] = _rect_array((actors[id] as TextureRect).get_rect())
	var record: FileAccess = FileAccess.open(folder.path_join(name + ".json"), FileAccess.WRITE)
	if record == null:
		_errors.append("Cannot save metadata for " + name)
	else:
		record.store_string(JSON.stringify(metadata, "\t"))
	_capture_count += 1
	print("Manpu animation capture: " + ProjectSettings.globalize_path(folder.path_join(name + ".png")))
