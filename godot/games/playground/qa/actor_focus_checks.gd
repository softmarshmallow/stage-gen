extends RefCounted

## Independent behavioral checks and renderer captures for the spike's cue.
const FOCUS = preload("res://addons/game_presentation/actors/actor_focus.gd")
const CATALOG := "res://addons/game_presentation/actors/presets/focus.json"
const ACTORS: Array[String] = ["mira", "lena", "sera"]
const PRESETS: Array[String] = ["none", "listener_dim", "listener_fade", "bounce", "scale_pulse", "restless_bounce"]
const DESIGN_SIZE := Vector2(1280, 900)
const NEUTRAL := {"offset_x_ratio": 0.0, "offset_y_ratio": 0.0, "scale": 1.0, "opacity": 1.0, "brightness": 1.0}
var _errors: Array[String] = []
var _capture_count := 0


func run(root: Control, options: Dictionary) -> void:
	_check_engine()
	await _check_runtime(root)
	if _errors.is_empty() and options.has("capture-focus"):
		if DisplayServer.get_name() == "headless":
			_errors.append("Actor Focus captures require a real renderer.")
		else:
			await _capture_proof(root, String(options.get("capture-dir", "res://qa/actor-focus/captures")))
	for issue: String in _errors:
		printerr("FAIL Actor Focus: " + issue)
	if _errors.is_empty():
		print("PASS Actor Focus: atomic catalog validation, all configured presets, speaker ownership/replay, retarget continuity/rest, frozen time, composed actor/manpu transforms, alpha/material, narrator, same-speaker story, and resume")
		if _capture_count > 0:
			print("Actor Focus captures complete: %d PNG and metadata pairs" % _capture_count)
	root.get_tree().quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _channels_equal(left: Dictionary, right: Dictionary) -> bool:
	for channel: String in NEUTRAL:
		if not left.has(channel) or not right.has(channel) or not is_equal_approx(float(left[channel]), float(right[channel])):
			return false
	return true


func _samples(focus: FOCUS) -> Dictionary:
	var result := {}
	for id: String in ACTORS:
		result[id] = focus.sample(id)
	return result


func _same_samples(left: Dictionary, right: Dictionary) -> bool:
	for id: String in ACTORS:
		if not _channels_equal(left[id], right[id]):
			return false
	return true


func _snapshot(focus: FOCUS) -> Dictionary:
	return {"focus_id": focus.focus_id, "preset_id": focus.preset_id, "elapsed": focus.elapsed,
		"duration_seconds": focus.duration_seconds, "samples": _samples(focus), "presets": focus.get_presets()}


func _start(focus: FOCUS, preset: String, actor: String = "mira") -> void:
	focus.clear()
	_expect(focus.configure(preset).is_empty(), "Could not configure " + preset)
	_expect(focus.set_focus(actor).is_empty(), "Could not focus " + actor)


func _neutral(focus: FOCUS, message: String) -> void:
	for id: String in ACTORS:
		_expect(_channels_equal(focus.sample(id), NEUTRAL), message + ": " + id)


func _check_engine() -> void:
	var focus: FOCUS = FOCUS.new()
	_expect(focus.initialize(ACTORS, CATALOG).is_empty(), "The checked-in catalog must initialize.")
	if not focus.initialized:
		return
	var ids: Array[String] = []
	for preset: Dictionary in focus.get_presets():
		ids.append(String(preset["id"]))
	_expect(ids == PRESETS, "The focus demonstration presets must retain their declared order.")
	_check_invalid_catalogs(focus)
	_start(focus, "bounce")
	focus.advance(0.42 * 0.32)
	_expect(is_equal_approx(float(focus.sample("mira")["offset_y_ratio"]), -0.015), "Bounce must reach its authored upward displacement.")
	var before: Dictionary = _snapshot(focus)
	focus.set_focus("mira")
	focus.configure("bounce")
	_expect(_snapshot(focus) == before, "Repeated same-speaker/configure cues must not replay.")
	var detached: Dictionary = focus.sample("mira")
	detached["scale"] = 9.0
	for index in 30:
		_expect(_snapshot(focus) == before, "Sampling must be stable and return independent dictionaries.")
	focus.advance(0.42 * (0.7 - 0.32))
	_expect(is_equal_approx(float(focus.sample("mira")["offset_y_ratio"]), 0.006), "Bounce must cross below its baseline before settling.")
	focus.advance(5.0)
	_neutral(focus, "A completed bounce must settle without drift")
	_start(focus, "scale_pulse")
	focus.advance(0.42 * 0.45)
	_expect(is_equal_approx(float(focus.sample("mira")["scale"]), 1.035), "Scale pulse must reach its authored 3.5 percent enlargement.")
	for id: String in ["lena", "sera"]:
		_expect(_channels_equal(focus.sample(id), NEUTRAL), "A scale pulse must leave other actors neutral.")
	focus.advance(3.0)
	_neutral(focus, "A completed scale pulse must settle without drift")
	for preset: String in ["listener_dim", "listener_fade"]:
		_start(focus, preset)
		focus.advance(1.0)
		_expect(_channels_equal(focus.sample("mira"), NEUTRAL), "The focused actor stays neutral for " + preset)
		var channel: String = "brightness" if preset == "listener_dim" else "opacity"
		var value: float = 0.76 if preset == "listener_dim" else 0.6
		_expect(is_equal_approx(float(focus.sample("lena")[channel]), value), "Listeners must hold their selected " + channel)
		var incoming: Dictionary = _samples(focus)
		focus.set_focus("lena")
		_expect(_same_samples(incoming, _samples(focus)), "Role changes must begin from the current samples.")
		focus.advance(1.0)
		_expect(_channels_equal(focus.sample("lena"), NEUTRAL), "The incoming actor must recover its full appearance.")
		focus.set_focus("")
		focus.advance(1.0)
		_neutral(focus, "Narrator focus must return every actor to neutral")
	_start(focus, "bounce")
	for index in 24:
		focus.advance(0.037 + (index % 3) * 0.021)
		var current: Dictionary = _samples(focus)
		focus.set_focus(ACTORS[(index + 1) % ACTORS.size()])
		_expect(_same_samples(current, _samples(focus)), "Rapid retargeting must preserve the exact current pose.")
	focus.advance(2.0)
	_neutral(focus, "Repeated interrupted cues must have no resting drift")
	_start(focus, "bounce")
	focus.advance(0.1)
	before = _samples(focus)
	focus.configure("scale_pulse")
	_expect(_same_samples(before, _samples(focus)), "Changing preset mid-pulse must preserve the current pose.")
	focus.advance(0.1)
	before = _samples(focus)
	focus.replay()
	_expect(is_zero_approx(focus.elapsed) and _same_samples(before, _samples(focus)), "Explicit replay must restart time without a pose discontinuity.")
	var invalid_snapshot: Dictionary = _snapshot(focus)
	_expect(not focus.set_focus("missing_actor").is_empty(), "Unknown focus actors must be rejected.")
	_expect(not focus.configure("missing_preset").is_empty(), "Unknown presets must be rejected.")
	focus.advance(-1.0)
	focus.advance(NAN)
	focus.advance(INF)
	_expect(_snapshot(focus) == invalid_snapshot, "Invalid cues and time deltas must leave the engine intact.")
	focus.configure("none")
	_neutral(focus, "None must be exact identity even during an interrupted cue")
	_expect(_channels_equal(focus.sample("missing_actor"), NEUTRAL), "Unknown actor samples must be neutral.")
	focus.clear()
	_expect(focus.focus_id.is_empty() and focus.elapsed == 0.0, "Clear must reset focus and time.")
	_neutral(focus, "Clear must immediately remove presentation residue")


func _check_invalid_catalogs(focus: FOCUS) -> void:
	_start(focus, "bounce")
	focus.advance(0.1)
	var initial: Dictionary = _snapshot(focus)
	var valid: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
	var variants: Array[Dictionary] = []
	var duplicate: Dictionary = valid.duplicate(true)
	duplicate["presets"].append(duplicate["presets"][0].duplicate(true))
	variants.append(duplicate)
	var unknown: Dictionary = valid.duplicate(true)
	unknown["presets"][0]["focused"]["rotation"] = [[0, 0], [1, 1]]
	variants.append(unknown)
	var opacity: Dictionary = valid.duplicate(true)
	opacity["presets"][0]["focused"]["opacity"] = [[0, 1], [1, 1.2]]
	variants.append(opacity)
	var scale: Dictionary = valid.duplicate(true)
	scale["presets"][0]["focused"]["scale"] = [[0, 1], [1, 0]]
	variants.append(scale)
	var unordered: Dictionary = valid.duplicate(true)
	unordered["presets"][0]["focused"]["scale"] = [[0, 1], [0, 1], [1, 1]]
	variants.append(unordered)
	var endpoints: Dictionary = valid.duplicate(true)
	endpoints["presets"][0]["focused"]["scale"] = [[0.1, 1], [0.8, 1]]
	variants.append(endpoints)
	var nonfinite: Dictionary = valid.duplicate(true)
	nonfinite["presets"][0]["duration_seconds"] = INF
	variants.append(nonfinite)
	var invalid_frame: Dictionary = valid.duplicate(true)
	invalid_frame["presets"][0]["focused"]["scale"] = [[0, NAN], [1, 1]]
	variants.append(invalid_frame)
	var wrong_type: Dictionary = valid.duplicate(true)
	wrong_type["presets"][0]["listeners"] = "invalid"
	variants.append(wrong_type)
	var temporary: String = "/tmp/actor_focus_checks_%d.json" % OS.get_process_id()
	for variant_index in variants.size():
		var variant: Dictionary = variants[variant_index]
		var checked: Dictionary = focus.call("_validate_catalog", variant)
		_expect(not (checked["errors"] as Array).is_empty(), "Malformed, out-of-range, or nonfinite preset data must be rejected.")
		if variant_index in [6, 7]:
			# Nonfinite values cannot be represented in JSON. Test the validator
			# directly rather than converting them into a different invalid value.
			_expect(_snapshot(focus) == initial, "Nonfinite validation must leave an active engine intact.")
			continue
		var file: FileAccess = FileAccess.open(temporary, FileAccess.WRITE)
		file.store_string(JSON.stringify(variant))
		file.close()
		_expect(not focus.initialize(ACTORS, temporary).is_empty(), "Invalid initialization must report a failure.")
		_expect(_snapshot(focus) == initial, "Invalid initialization must be atomic.")
	var malformed: FileAccess = FileAccess.open(temporary, FileAccess.WRITE)
	malformed.store_string("{malformed")
	malformed.close()
	_expect(not focus.initialize(ACTORS, temporary).is_empty() and _snapshot(focus) == initial, "Malformed JSON must not replace an active engine.")
	var duplicated_actors: Array[String] = ["mira", "mira"]
	_expect(not focus.initialize(duplicated_actors, CATALOG).is_empty() and _snapshot(focus) == initial, "Duplicate actor ids must be rejected atomically.")
	DirAccess.remove_absolute(temporary)


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
	_expect((scene.get("_load_errors") as Array).is_empty(), "Route assets and preset initialization must succeed.")
	return scene


func _focus(scene: Control) -> FOCUS:
	return scene.get("_actor_focus") as FOCUS


func _rect(scene: Control, method: String, index: int = 0) -> Rect2:
	return scene.call(method, DESIGN_SIZE, index)


func _tick(scene: Control, seconds: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", seconds)
	scene.set("_capture_frozen", true)


func _check_runtime(root: Control) -> void:
	var scene: Control = await _open(root, "demos/actor_focus")
	var focus: FOCUS = _focus(scene)
	scene.call("set_actor_focus_preset", "bounce")
	focus.clear()
	scene.call("_sync_actor_focus")
	var base: Rect2 = _rect(scene, "_dialogue_rect")
	var mark_before: Rect2 = scene.call("_manpu_rect", DESIGN_SIZE, "mira", "surprise")
	_tick(scene, 0.42 * 0.32)
	var shown: Rect2 = _rect(scene, "_presented_dialogue_rect")
	var mark_after: Rect2 = scene.call("_manpu_rect", DESIGN_SIZE, "mira", "surprise")
	_expect(is_equal_approx(shown.position.y - base.position.y, -0.015 * base.size.y), "The rendered bounce must use unscaled actor-height displacement.")
	_expect(is_equal_approx(mark_after.position.y - mark_before.position.y, shown.position.y - base.position.y), "A painted manpu must travel with its moving actor.")
	var sampled: Dictionary = _snapshot(focus)
	for index in 10:
		scene.call("_layout_interface")
		scene.call("_update_character_layers")
		scene.call("_process", 0.5)
	_expect(_snapshot(focus) == sampled and _rect(scene, "_presented_dialogue_rect").is_equal_approx(shown), "Frozen time, redraw, and layout must not restart or drift the cue.")
	scene.call("set_actor_focus_preset", "scale_pulse")
	focus.clear()
	scene.call("_sync_actor_focus")
	_tick(scene, 0.42 * 0.45)
	shown = _rect(scene, "_presented_dialogue_rect")
	var scaled_mark: Rect2 = scene.call("_manpu_rect", DESIGN_SIZE, "mira", "surprise")
	_expect(is_equal_approx(shown.size.y / base.size.y, 1.035) and is_equal_approx(shown.end.y, base.end.y) and is_equal_approx(shown.get_center().x, base.get_center().x), "Scale pulse must grow about the bottom-center pivot.")
	_expect(is_equal_approx(scaled_mark.size.y / shown.size.y, 0.1), "Manpu size must track the final actor height.")
	var sprites: Dictionary = scene.get("_actor_nodes")
	_expect((sprites["mira"] as TextureRect).get_rect().is_equal_approx(shown), "The sampled final rectangle must be the actual sprite rectangle.")
	scene.call("set_actor_focus_preset", "listener_fade")
	focus.advance(1.0)
	scene.set("_entry", 0.5)
	var effects: Dictionary = scene.get("_character_effects")
	effects["lena"]["enabled"] = true
	scene.call("_update_character_layers")
	var listener: TextureRect = sprites["lena"] as TextureRect
	var materials: Dictionary = scene.get("_actor_materials")
	_expect(is_equal_approx(listener.modulate.a, 0.3), "Entry alpha and listener opacity must multiply once.")
	_expect(listener.material == materials["lena"] and (sprites["mira"] as TextureRect).material == null, "Focus opacity must preserve the actor's independent hologram material.")
	scene.call("set_actor_focus_preset", "none")
	scene.set("_entry", 1.0)
	scene.call("_update_character_layers")
	_expect(listener.modulate.is_equal_approx(Color.WHITE), "None must remove all old listener dim/fade behavior.")
	scene = await _open(root, "new_game")
	scene.call("skip_establishing")
	scene.set("_entry", 1.0)
	scene.call("_update_interface")
	focus = _focus(scene)
	for index in 4:
		scene.call("_route_mouse", (scene.get("_next_button") as Button).get_global_rect().get_center())
	_tick(scene, 0.8)
	var same_speaker_time: float = focus.elapsed
	var choices: Array = scene.get("_choice_buttons")
	scene.call("_route_mouse", (choices[0] as Button).get_global_rect().get_center())
	_expect(String(scene.get("_story_id")) == "escort" and focus.focus_id == "mira" and is_equal_approx(focus.elapsed, same_speaker_time), "Mira's consecutive orders and escort lines must not replay focus.")
	root.call("open_route", "demos/actor_focus")
	scene = await _open(root, "game")
	focus = _focus(scene)
	_expect(String(scene.get("_story_id")) == "escort" and focus.focus_id == "mira" and is_equal_approx(focus.elapsed, focus.duration_seconds), "Resume must restore the current speaker at its settled pose.")
	scene.call("set_actor_focus_preset", "listener_dim")
	focus.advance(1.0)
	scene.set("_story_id", "end")
	scene.call("_update_interface")
	_tick(scene, 1.0)
	_expect(focus.focus_id.is_empty(), "Narration must have no focused actor.")
	_neutral(focus, "Narration must not leave all actors dimmed")
	scene.call("_restart")
	_expect(_focus(scene).focus_id.is_empty() and bool(scene.call("is_establishing")), "Story replay must clear old motion during the opening view.")
	scene.call("skip_establishing")
	scene.call("_update_interface")
	_expect(_focus(scene).focus_id == "mira" and is_zero_approx(_focus(scene).elapsed), "Finishing the opening view must cue the opening actor.")
	for route: String in ["demos/contact", "demos/locations", "demos/characters"]:
		scene = await _open(root, route)
		_expect(_focus(scene).focus_id.is_empty(), "Non-dialogue routes must clear actor focus.")
		_neutral(_focus(scene), "No focus residue may leak into " + route)


func _capture_proof(root: Control, folder: String) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "Cannot create focus capture directory.")
	var scene: Control = await _open(root, "demos/actor_focus")
	scene.call("_select_location", "forward_command", true)
	scene.set("_natural_blink", false)
	scene.set("_blink_remaining", 0.0)
	scene.set("_location_title_elapsed", 3.7)
	scene.set("_elapsed", 1.0)
	scene.set("_capturing", true)
	scene.call("_update_location_title")
	for preset: String in PRESETS:
		scene.call("set_actor_focus_preset", preset)
		var focus: FOCUS = _focus(scene)
		focus.clear()
		scene.call("_sync_actor_focus")
		scene.call("_update_interface")
		await _save_capture(root, scene, folder, preset + "_opening", 0.0)
		var peak: float = 0.1344 if preset == "bounce" else (0.189 if preset == "scale_pulse" else 0.11)
		focus.advance(peak)
		scene.call("_update_character_layers")
		await _save_capture(root, scene, folder, preset + "_middle", peak)
		focus.advance(2.0)
		scene.call("_update_character_layers")
		await _save_capture(root, scene, folder, preset + "_settled", 0.42)
	for preset: String in ["bounce", "scale_pulse"]:
		var sequence_folder: String = folder.path_join(preset + "_sequence")
		DirAccess.make_dir_recursive_absolute(sequence_folder)
		scene.call("set_actor_focus_preset", preset)
		scene.set("_dialogue_index", 0)
		_focus(scene).clear()
		scene.call("_sync_actor_focus")
		var previous := 0.0
		for phase: float in [0.0, 0.1, 0.2, 0.3, 0.42]:
			_focus(scene).advance(phase - previous)
			previous = phase
			scene.call("_update_interface")
			await _save_capture(root, scene, sequence_folder, "frame_%03d" % roundi(phase * 1000.0), phase)
	var handoff_folder: String = folder.path_join("handoff_sequence")
	DirAccess.make_dir_recursive_absolute(handoff_folder)
	scene.call("set_actor_focus_preset", "bounce")
	scene.set("_dialogue_index", 0)
	_focus(scene).clear()
	scene.call("_sync_actor_focus")
	var prior := 0.0
	for phase: float in [0.0, 0.1, 0.2, 0.3, 0.42]:
		_focus(scene).advance(phase - prior)
		prior = phase
		if is_equal_approx(phase, 0.2):
			scene.call("_advance_dialogue")
		scene.call("_update_interface")
		await _save_capture(root, scene, handoff_folder, "frame_%03d" % roundi(phase * 1000.0), phase)


func _rect_array(rect: Rect2) -> Array[float]:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _save_capture(root: Control, scene: Control, folder: String, name: String, sequence_time: float) -> void:
	root.get_viewport().gui_release_focus()
	if root.get_viewport().gui_get_hovered_control() != null:
		root.get_viewport().notify_mouse_exited()
	await root.get_tree().process_frame
	scene.queue_redraw()
	for index in 4:
		RenderingServer.force_draw(false)
	var picture: Image = root.get_viewport().get_texture().get_image()
	_expect(picture.save_png(folder.path_join(name + ".png")) == OK, "Could not save focus capture " + name)
	var focus: FOCUS = _focus(scene)
	var metadata := {"state": name, "route": "demos/actor_focus", "sequence_time_seconds": sequence_time,
		"focus_id": focus.focus_id, "preset_id": focus.preset_id, "elapsed_seconds": focus.elapsed, "duration_seconds": focus.duration_seconds,
		"channels": _samples(focus), "actor_rects": {}, "manpu_rects": [], "capture_space": "logical_viewport", "viewport": [1280, 900]}
	for index in ACTORS.size():
		metadata["actor_rects"][ACTORS[index]] = _rect_array(_rect(scene, "_presented_dialogue_rect", index))
	var cues: Array = scene.call("_active_manpu")
	for cue: Dictionary in cues:
		var rect: Rect2 = scene.call("_manpu_rect", DESIGN_SIZE, String(cue["actor"]), String(cue["id"]))
		metadata["manpu_rects"].append({"actor": cue["actor"], "id": cue["id"], "rect": _rect_array(rect)})
	var record: FileAccess = FileAccess.open(folder.path_join(name + ".json"), FileAccess.WRITE)
	if record == null:
		_errors.append("Cannot write focus metadata for " + name)
	else:
		record.store_string(JSON.stringify(metadata, "\t"))
	_capture_count += 1
	print("Actor Focus capture: " + ProjectSettings.globalize_path(folder.path_join(name + ".png")))
