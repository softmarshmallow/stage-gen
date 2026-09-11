extends RefCounted

## Independent exit lifecycle/composition checks and bounded renderer proof.
const EXIT = preload("res://addons/game_presentation/actors/character_exit.gd")
const CATALOG := "res://addons/game_presentation/actors/presets/exit.json"
const ACTORS: Array[String] = ["mira", "lena", "sera"]
const DESIGN_SIZE := Vector2(1280, 900)
const IDENTITY := {"offset_x_ratio": 0.0, "offset_y_ratio": 0.0, "scale": 1.0, "opacity": 1.0, "brightness": 1.0}
var _errors: Array[String] = []
var _capture_count := 0


func run(root: Control, options: Dictionary) -> void:
	_check_controller()
	await _check_runtime(root)
	if _errors.is_empty() and options.has("capture-character-exit"):
		if DisplayServer.get_name() == "headless":
			_errors.append("Character Exit captures require a real renderer.")
		else:
			await _capture_proof(root, String(options.get("capture-dir", "res://tests/character-exit/captures")))
	for issue: String in _errors:
		printerr("FAIL Character Exit: " + issue)
	if _errors.is_empty():
		print("PASS Character Exit: opaque color phase, black matte/fade, persistent hidden state, independent actors, duplicate exit, show cancellation, future-only presets, frozen redraw, composition, reaction cleanup, reset and route isolation")
		if _capture_count > 0:
			print("Character Exit captures complete: %d PNG and metadata pairs" % _capture_count)
	root.get_tree().quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _identity(sample: Dictionary) -> bool:
	for channel: String in IDENTITY:
		if not sample.has(channel) or not is_equal_approx(float(sample[channel]), float(IDENTITY[channel])):
			return false
	return true


func _states(controller: EXIT) -> Dictionary:
	return controller.get_state()["states"]


func _check_controller() -> void:
	var controller: EXIT = EXIT.new()
	_expect(controller.initialize(ACTORS, CATALOG).is_empty(), "The exit catalog and cast must initialize.")
	if not controller.initialized:
		return
	var presets: Array[String] = []
	for preset: Dictionary in controller.get_presets():
		presets.append(String(preset["id"]))
	_expect(presets == ["silhouette_fade", "opacity_fade", "walk_away", "walk_away_right"], "Both fade baselines and directional walk presets must retain their declared order.")
	controller.exit_actor("sera")
	var previous_time := 0.0
	for phase: float in [0.0, 0.1, 0.2475, 0.4, 0.495]:
		controller.advance(phase - previous_time)
		previous_time = phase
		var sample: Dictionary = controller.sample("sera")
		_expect(controller.is_visible("sera") and controller.is_exiting("sera") and is_equal_approx(float(sample["opacity"]), 1.0), "The entire color-to-black phase must preserve drawable coverage.")
		_expect(is_equal_approx(float(sample["scale"]), 1.0) and is_zero_approx(float(sample["offset_x_ratio"])) and is_zero_approx(float(sample["offset_y_ratio"])), "The silhouette baseline must not alter the actor's transform.")
		for id: String in ["mira", "lena"]:
			_expect(_identity(controller.sample(id)), "An idle actor must remain unchanged during another actor's exit.")
	_expect(is_zero_approx(float(controller.sample("sera")["brightness"])), "The phase boundary must be an opaque black silhouette.")
	controller.advance(0.2025)
	var matte: Dictionary = controller.sample("sera")
	_expect(is_zero_approx(float(matte["brightness"])) and is_equal_approx(float(matte["opacity"]), 0.5), "The second phase must fade black coverage, not colored artwork.")
	var before: Dictionary = controller.get_state()
	controller.exit_actor("sera")
	_expect(controller.get_state() == before, "A repeated exit must not restart its active clock.")
	controller.advance(1.0)
	_expect(not controller.is_visible("sera") and not controller.is_exiting("sera") and is_zero_approx(float(controller.sample("sera")["opacity"])), "Completion must leave the actor hidden.")
	before = controller.get_state()
	controller.exit_actor("sera")
	controller.advance(10.0)
	_expect(controller.get_state() == before, "Hidden actors must remain hidden until explicitly shown.")
	controller.clear()
	controller.exit_actor("mira")
	controller.advance(0.2)
	var mira_snapshot: Dictionary = _states(controller)["mira"].duplicate(true)
	controller.configure("opacity_fade")
	_expect(_states(controller)["mira"] == mira_snapshot, "Changing the selected preset must not alter an active exit.")
	controller.exit_actor("lena")
	controller.advance(0.2)
	var current: Dictionary = _states(controller)
	_expect(current["mira"]["preset_id"] == "silhouette_fade" and current["lena"]["preset_id"] == "opacity_fade", "Only a future exit must use a newly selected preset.")
	_expect(is_equal_approx(float(current["mira"]["elapsed"]), 0.4) and is_equal_approx(float(current["lena"]["elapsed"]), 0.2), "Concurrent actors must retain independent start times.")
	var lena_snapshot: Dictionary = current["lena"].duplicate(true)
	controller.show_actor("mira")
	_expect(controller.is_visible("mira") and not controller.is_exiting("mira") and _identity(controller.sample("mira")), "Show must cancel a partial exit and immediately restore identity.")
	_expect(_states(controller)["lena"] == lena_snapshot, "Showing one actor must leave another exit untouched.")
	controller.advance(0.25)
	_expect(is_equal_approx(float(controller.sample("lena")["brightness"]), 1.0) and is_equal_approx(float(controller.sample("lena")["opacity"]), 0.5), "The comparison preset must perform an ordinary opacity fade.")
	before = controller.get_state()
	var detached: Dictionary = controller.get_state()
	detached["states"]["lena"]["elapsed"] = 100.0
	for index in 10:
		controller.sample("lena")
	_expect(controller.get_state() == before, "Sampling and returned-state mutation must not advance clocks.")
	_expect(not controller.exit_actor("unknown").is_empty() and not controller.show_actor("").is_empty() and not controller.configure("unknown").is_empty(), "Invalid target and preset commands must be rejected.")
	controller.advance(-1.0)
	controller.advance(INF)
	controller.advance(NAN)
	_expect(controller.get_state() == before, "Invalid commands and deltas must preserve every actor state.")
	var duplicate_ids: Array[String] = ["mira", "mira"]
	_expect(not controller.initialize(duplicate_ids, CATALOG).is_empty() and controller.get_state() == before, "Invalid reinitialization must be atomic.")
	for channel: String in ["scale", "rotation"]:
		var invalid_catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
		invalid_catalog["presets"][0]["tracks"][channel] = [[0, 1], [1, 1]]
		var checked: Dictionary = controller.call("_validate_catalog", invalid_catalog)
		_expect(not (checked["errors"] as Array).is_empty() and controller.get_state() == before, "Exit presets must reject unsupported scale/rotation tracks rather than silently ignore them.")
	controller.clear()
	for id: String in ACTORS:
		_expect(controller.is_visible(id) and not controller.is_exiting(id) and _identity(controller.sample(id)), "Reset must restore every actor independently of the selected preset.")


func _controller(scene: Control) -> EXIT:
	return scene.get("_character_exit") as EXIT


func _sprite(scene: Control, actor: String) -> TextureRect:
	var actors: Dictionary = scene.get("_actor_nodes")
	return actors[actor] as TextureRect


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
	_expect((scene.get("_load_errors") as Array).is_empty(), "Exit stage assets and catalogs must load.")
	return scene


func _tick(scene: Control, seconds: float) -> void:
	scene.set("_capture_frozen", false)
	scene.call("_process", seconds)
	scene.set("_capture_frozen", true)


func _check_runtime(root: Control) -> void:
	var scene: Control = await _open(root, "demos/character_exit")
	var controller: EXIT = _controller(scene)
	var sera: TextureRect = _sprite(scene, "sera")
	var source_rect: Rect2 = sera.get_rect()
	_expect(String(scene.get("actor_focus_preset")) == "none" and sera.material == null, "The dedicated exit demonstration must start with ordinary actor rendering.")
	scene.set("_entry", 0.5)
	scene.call("_route_key", KEY_E)
	_expect(not controller.is_exiting("sera"), "The demo must wait until entry is fully visible before starting an exit.")
	scene.set("_entry", 1.0)
	scene.call("_route_key", KEY_E)
	_expect(controller.is_exiting("sera"), "E must start the selected actor's exit once fully entered.")
	_tick(scene, 0.2475)
	_expect(sera.visible and is_equal_approx(sera.modulate.a, 1.0) and is_equal_approx(sera.modulate.r, 0.5), "Rendered color darkening must keep full alpha in its first phase.")
	_expect(sera.get_rect().is_equal_approx(source_rect), "The exit must retain the exact authored actor rectangle.")
	var frozen: Dictionary = controller.get_state()
	for index in 10:
		scene.call("_layout_interface")
		scene.call("_update_character_layers")
		scene.call("_process", 0.2)
	_expect(controller.get_state() == frozen, "Frozen redraw and layout must not advance or replay exits.")
	_tick(scene, 0.2475)
	_expect(sera.visible and is_equal_approx(sera.modulate.a, 1.0) and is_zero_approx(sera.modulate.r) and is_zero_approx(sera.modulate.g) and is_zero_approx(sera.modulate.b), "The rendered matte boundary must be black while preserving full alpha.")
	_tick(scene, 0.2025)
	_expect(is_equal_approx(sera.modulate.a, 0.5) and is_zero_approx(sera.modulate.r), "The rendered second phase must fade only black coverage.")
	_tick(scene, 0.2025)
	for index in 10:
		scene.call("_update_character_layers")
	_expect(not sera.visible and not controller.is_visible("sera"), "A completed exit must stay hidden through redraws.")
	scene.call("_route_key", KEY_S)
	_expect(sera.visible and sera.modulate.is_equal_approx(Color.WHITE), "S must restore the hidden actor immediately.")
	scene.call("exit_actor", "mira")
	_tick(scene, 0.1)
	scene.call("_route_key", KEY_R)
	for actor: String in ACTORS:
		_expect(_sprite(scene, actor).visible and _identity(controller.sample(actor)), "Demo reset must clear every exit state.")
	scene = await _open(root, "new_game")
	scene.call("skip_establishing")
	scene.set("_entry", 1.0)
	scene.call("_update_interface")
	var cues: Array = scene.call("_presented_manpu_cues")
	_expect(not cues.is_empty(), "The opening beat must provide an authored reaction for ownership checks.")
	scene.call("exit_actor", "mira")
	_expect((scene.call("_presented_manpu_cues") as Array).is_empty(), "A departing actor must not leave an orphaned manpu.")
	var marks: RefCounted = scene.get("_manpu_animation")
	_expect((marks.call("get_state")["states"] as Dictionary).is_empty(), "Departure must clear the departing owner's mark clocks.")
	_tick(scene, 1.0)
	scene = await _open(root, "demos/dialogue")
	for actor: String in ACTORS:
		_expect(_sprite(scene, actor).visible, "Exit state must not leak into another route.")
	scene = await _open(root, "demos/contact")
	var fingertip: Vector2 = scene.call("_fingertip_center", DESIGN_SIZE)
	scene.call("_route_mouse", fingertip)
	_expect(bool(scene.get("_connected")), "Ordinary contact must work before an exit.")
	scene.call("exit_actor", "mira")
	scene.call("_route_mouse", fingertip)
	_expect(not bool(scene.get("_connected")) and is_zero_approx(float(scene.get("_reaction"))), "A departing actor must clear contact feedback and reject new contact.")
	_tick(scene, 1.0)
	scene.call("_route_mouse", fingertip)
	_expect(not bool(scene.get("_connected")), "A hidden actor's fingertip must not accept contact.")
	scene.call("show_actor", "mira")
	scene.call("_route_mouse", fingertip)
	_expect(bool(scene.get("_connected")), "Showing the actor must restore fingertip interaction.")
	scene = await _open(root, "demos/character_exit")
	_expect(String(scene.get("_exit_target")) == "sera" and String(scene.get("character_exit_preset")) == "silhouette_fade", "Reopening the demo must restore its default target and preset.")


func _prepare(scene: Control, preset: String = "silhouette_fade") -> void:
	_controller(scene).clear()
	scene.call("set_character_exit_preset", preset)
	scene.set("_exit_target", "sera")
	scene.set("_entry", 1.0)
	scene.call("_update_interface")


func _capture_proof(root: Control, folder: String) -> void:
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "Cannot create exit capture directory.")
	var scene: Control = await _open(root, "demos/character_exit")
	scene.call("_select_location", "forward_command", true)
	scene.set("_capturing", true)
	scene.set("_natural_blink", false)
	scene.set("_blink_remaining", 0.0)
	scene.set("_location_title_elapsed", 3.7)
	scene.set("_elapsed", 1.0)
	scene.call("_update_location_title")
	_prepare(scene)
	await _capture(root, scene, folder, "all_visible", 0.0)
	scene.call("exit_actor", "sera")
	var previous := 0.0
	for frame: Array in [["silhouette_color_half", 0.2475], ["silhouette_matte", 0.495], ["silhouette_fade_half", 0.6975], ["silhouette_hidden", 0.9]]:
		_tick(scene, float(frame[1]) - previous)
		previous = float(frame[1])
		await _capture(root, scene, folder, String(frame[0]), previous)
	_prepare(scene, "opacity_fade")
	scene.call("exit_actor", "sera")
	_tick(scene, 0.45)
	await _capture(root, scene, folder, "opacity_half", 0.45)
	_tick(scene, 0.45)
	await _capture(root, scene, folder, "opacity_hidden", 0.9)
	_prepare(scene)
	scene.call("exit_actor", "mira")
	_tick(scene, 0.2)
	scene.call("exit_actor", "lena")
	_tick(scene, 0.2)
	await _capture(root, scene, folder, "concurrent_stagger", 0.4)
	scene.call("show_actor", "mira")
	await _capture(root, scene, folder, "show_interrupt", 0.4)
	_prepare(scene)
	await _capture(root, scene, folder, "hidden_control", 0.0, "sera")
	scene.call("show_actor", "sera")
	await _capture(root, scene, folder, "show_restored", 0.0)


func _rect_array(rect: Rect2) -> Array[float]:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]


func _capture(root: Control, scene: Control, folder: String, name: String, sequence_time: float, control_hide_actor: String = "") -> void:
	root.get_viewport().gui_release_focus()
	if root.get_viewport().gui_get_hovered_control() != null:
		root.get_viewport().notify_mouse_exited()
	scene.call("_update_interface")
	await root.get_tree().process_frame
	# The control plate removes just one sprite after ordinary presentation has
	# updated. It supplies background pixels without running any fade/shader.
	if not control_hide_actor.is_empty():
		_sprite(scene, control_hide_actor).hide()
	scene.queue_redraw()
	for index in 4:
		RenderingServer.force_draw(false)
	var image: Image = root.get_viewport().get_texture().get_image()
	_expect(image.get_size() == Vector2i(1280, 900) and image.save_png(folder.path_join(name + ".png")) == OK, "Cannot save the logical exit capture " + name)
	var transform: Transform2D = root.get_viewport().get_final_transform()
	var extent: Vector2 = transform.basis_xform(DESIGN_SIZE)
	var controller: EXIT = _controller(scene)
	var metadata := {"state": name, "route": "demos/character_exit", "sequence_time_seconds": sequence_time,
		"character_exit": controller.get_state(), "control_hide_actor": control_hide_actor, "actors": {}, "entry": scene.get("_entry"),
		"capture_space": "logical_viewport", "viewport": [1280, 900], "window_size": [root.get_window().size.x, root.get_window().size.y],
		"output_rect": [transform.origin.x, transform.origin.y, extent.x, extent.y], "output_scale": [transform.x.x, transform.y.y]}
	for actor: String in ACTORS:
		var sprite: TextureRect = _sprite(scene, actor)
		metadata["actors"][actor] = {"visible": sprite.visible, "exiting": controller.is_exiting(actor), "channels": controller.sample(actor),
			"rect": _rect_array(sprite.get_rect()), "modulate": [sprite.modulate.r, sprite.modulate.g, sprite.modulate.b, sprite.modulate.a],
			"has_material": sprite.material != null}
	var record: FileAccess = FileAccess.open(folder.path_join(name + ".json"), FileAccess.WRITE)
	if record == null:
		_errors.append("Cannot write exit metadata for " + name)
	else:
		record.store_string(JSON.stringify(metadata, "\t"))
	_capture_count += 1
	print("Character Exit capture: " + ProjectSettings.globalize_path(folder.path_join(name + ".png")))
