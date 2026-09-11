extends SceneTree

## Concrete renderer/input proof; lifecycle edge cases live in the controller
## checks. Run with --capture-one-shot for native 1x/2x evidence.
const DESIGN_SIZE := Vector2(1280, 900)
const DIRECTORY := "res://qa/one-shot-manpu"
const FALLING_DIRECTORY := "res://qa/falling-sweat"
var _app: Control
var _errors: Array[String] = []
var _capture_enabled := false
var _capture_count := 0
var _falling_captures: Array[Dictionary] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var falling_only := OS.get_cmdline_user_args().has("--falling-sweat-only")
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-one-shot") or falling_only
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("One-shot Manpu captures require a native renderer.")
		quit(2)
		return
	root.size = Vector2i(DESIGN_SIZE)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	if falling_only:
		await _check_falling_sweat_hosts()
		return
	await _check_menu()
	await _check_afterlight_renderer()
	await _check_tactical_renderer()
	await _check_story_events()
	for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		await _check_lab_controls_and_views(window_size)
	for issue: String in _errors: printerr("FAIL One-Shot Manpu integration: " + issue)
	if _errors.is_empty():
		print("PASS One-Shot Manpu integration: both 2D hosts, proportional camera composition, expired/hidden-owner cleanup, natural story emissions with mid-event Lab restore, static/shake/event controls, mouse/F6/pause/reset, same-instance 2D/3D camera-facing sprites and native 1x/2x output")
		if _capture_count > 0: print("One-shot Manpu captures: " + str(_capture_count))
	quit(0 if _errors.is_empty() else 1)


func _check_menu() -> void:
	var menu := await _open("game:presentation_lab/effects_menu")
	_expect(_healthy(menu), "The expanded effect menu must initialize.")
	await _capture("effects-menu-1280")
	var study := await _open("game:presentation_lab/sigh_puff_study")
	_expect(_healthy(study) and study.has_method("puff_state"), "The dedicated Sigh Puff laboratory route must be reachable.")


func _check_afterlight_renderer() -> void:
	var study: Control = _app.active_scene
	if not _healthy(study): return
	var cast: Control = study._cast_layer
	var actor_id: String = study._guest_id
	var emitted: Dictionary = cast.emit_manpu(actor_id, "sigh_puff")
	_expect(emitted["errors"].is_empty(), "Afterlight must accept an event for a visible actor and prepared puff.")
	if not emitted["errors"].is_empty(): return
	var handle := int(emitted["instance_id"])
	cast.advance(0.2)
	cast.present(Transform2D.IDENTITY)
	var node: TextureRect = cast._one_shot_nodes[handle]
	var wide := Rect2(node.position, node.size)
	var sample: Dictionary = cast._manpu.one_shots()[0]["sample"]
	var owner: Rect2 = cast._posed_rect(actor_id)
	var original_height: float = owner.size.y * cast.MARK_HEIGHT_RATIO
	_expect(is_equal_approx(node.size.y, original_height * float(sample["scale"])), "Event scale must use the original attached mark height.")
	var camera := Transform2D(Vector2(1.6, 0), Vector2(0, 1.6), Vector2(-250, -110))
	cast.present(camera)
	_expect(Rect2(node.position, node.size).is_equal_approx(camera * wide), "Afterlight puff geometry must pass through the actor's camera transform once.")
	var frozen: Dictionary = cast._manpu.get_state()
	for redraw in 5: cast.present(camera)
	_expect(cast._manpu.get_state() == frozen, "Afterlight rendering must not restart or advance emitted puffs.")
	var duplicate: Dictionary = cast.emit_manpu(actor_id, "sigh_puff")
	_expect(duplicate["errors"].is_empty() and cast._one_shot_nodes.size() == 2, "Two same-actor emissions must own separate rendered nodes.")
	cast.cancel_manpu(actor_id)
	_expect(cast._one_shot_nodes.is_empty() and cast._manpu.one_shots().is_empty(), "Actor cancellation must remove both Afterlight event and rendered node.")
	cast.emit_manpu(actor_id, "sigh_puff")
	cast.set_cast([])
	_expect(cast._one_shot_nodes.is_empty() and cast._manpu.one_shots().is_empty(), "Replacing the staged cast must discard orphaned puffs.")
	var refused: Dictionary = cast.emit_manpu(actor_id, "sigh_puff")
	_expect(not refused["errors"].is_empty(), "A hidden Afterlight actor must not emit an attached puff.")
	cast.set_cast([actor_id])
	cast.emit_manpu(actor_id, "sigh_puff")
	cast.advance(1.0)
	cast.present(Transform2D.IDENTITY)
	_expect(cast._one_shot_nodes.is_empty() and cast._manpu.one_shots().is_empty(), "Natural expiry must reclaim Afterlight event nodes.")


func _check_tactical_renderer() -> void:
	var stage := await _open("game:presentation_lab/demos/manpu")
	if not _healthy(stage): return
	stage._capture_frozen = true
	stage._entry = 1.0
	stage._natural_blink = false
	stage._mode = "dialogue"
	stage._update_character_layers()
	var event: Dictionary = stage.emit_manpu("mira", "sigh_puff")
	_expect(event["errors"].is_empty(), "The tactical presenter must consume the same one-shot contract and puff raster.")
	if not event["errors"].is_empty(): return
	stage._manpu_animation.advance(0.2)
	stage._update_character_layers()
	var sample: Dictionary = stage._manpu_animation.one_shots()[0]["sample"]
	var attached: Rect2 = stage._manpu_world_rect(DESIGN_SIZE, "mira", "sigh_puff")
	var posed: Rect2 = stage._composed_manpu_rect(DESIGN_SIZE, "mira", "sigh_puff", sample)
	var delta_center: Vector2 = posed.get_center() - attached.get_center()
	_expect(delta_center.is_equal_approx(attached.size.y * Vector2(float(sample["offset_x_ratio"]), float(sample["offset_y_ratio"]))), "Tactical puff drift must use original mark height in world space.")
	var before: Dictionary = stage._manpu_animation.get_state()
	for redraw in 5: stage._update_character_layers()
	_expect(stage._manpu_animation.get_state() == before, "Repeated tactical synchronization/redraw must preserve event instances and clocks.")
	await _capture("tactical-puff-1280")
	if _capture_enabled:
		var visible := await _frame_image()
		stage._manpu_animation.cancel_one_shots()
		stage._update_character_layers()
		var absent := await _frame_image()
		_expect(_different_pixels(visible, absent, root.get_final_transform() * posed) > 20, "The tactical draw path must visibly render the puff raster, not only update its controller.")
	stage.emit_manpu("mira", "sigh_puff")
	stage.emit_manpu("mira", "sigh_puff")
	_expect(stage._manpu_animation.one_shots().size() >= 2, "The tactical draw path must preserve overlapping events.")
	stage.exit_actor("mira")
	_expect(stage._manpu_animation.one_shots().is_empty(), "A departing tactical actor must cancel attached events.")
	var refused: Dictionary = stage.emit_manpu("mira", "sigh_puff")
	_expect(not refused["errors"].is_empty(), "A departing tactical actor must not create another puff.")


func _check_story_events() -> void:
	var game := await _open("game:bishoujo_afterlight/new_game")
	if not _healthy(game): return
	for pair: Array in [["no_forwarding_address", "nami"], ["courier_reply", "nami"], ["all_clear", "riko"]]:
		_seek(game, pair[0])
		_expect(str(game.current_beat()["id"]) == pair[0], "The natural Sigh Puff story beat must remain reachable: " + str(pair[0]))
		_expect(_healthy(game), "The story event must bind valid art and actor identities.")
		if game._reveal.sample()["phase"] == "revealing":
			_expect(game._cast._manpu.one_shots().is_empty(), "An after-reveal puff must wait while its dialogue is still typing: " + str(pair[0]))
			if pair[0] == "no_forwarding_address":
				var words: Dictionary = game._reveal.get_state()
				game._process(float(str(words["text"]).length()) / float(words["chars_per_second"]) + 0.01)
			else:
				game._next()
		_expect(str(game.current_beat()["id"]) == pair[0] and game._reveal.sample()["phase"] == "holding", "Finishing text must emit its puff while retaining the dialogue beat.")
		var events: Array = game._cast._manpu.one_shots()
		_expect(events.size() == 1 and str(events[0]["actor"]) == pair[1] and str(events[0]["id"]) == "sigh_puff", "The authored beat must emit one puff for its speaker: " + str(pair[0]))
		if events.size() != 1: return
		game._process(0.2)
		var before := _event_fingerprint(game._cast._manpu)
		var handle: int = game._cast._manpu.one_shots()[0]["instance_id"]
		var node: TextureRect = game._cast._one_shot_nodes[handle]
		var rect := Rect2(node.position, node.size)
		for redraw in 5: game._render()
		game.set_language("en")
		game.set_language("ko")
		_expect(_event_fingerprint(game._cast._manpu) == before, "Story redraw and language switches must not re-emit or retime the authored event.")
		await _capture("story-" + str(pair[1]) + "-puff-1280")
		game._toggle_pause()
		game._process(2.0)
		_expect(_event_fingerprint(game._cast._manpu) == before, "The story menu must pause an active puff.")
		await _open("game:presentation_lab")
		game = await _open("game:bishoujo_afterlight")
		_expect(_healthy(game) and str(game.current_beat()["id"]) == pair[0], "A Lab detour must resume the current Sigh Puff story beat.")
		_expect(_same_events(_event_fingerprint(game._cast._manpu), before), "Story replay must reconstruct exactly one puff with matching elapsed time and samples.")
		if game._cast._manpu.one_shots().is_empty(): return
		handle = int(game._cast._manpu.one_shots()[0]["instance_id"])
		node = game._cast._one_shot_nodes[handle]
		_expect(Rect2(node.position, node.size).is_equal_approx(rect), "Story restoration must reproduce the composed puff geometry.")
		game._process(0.6)
		_expect(game._cast._manpu.one_shots().is_empty() and game._cast._one_shot_nodes.is_empty(), "The restored puff must expire normally without replaying.")


func _check_lab_controls_and_views(window_size: Vector2i) -> void:
	root.size = window_size
	var study := await _open("game:presentation_lab/sigh_puff_study")
	if not _healthy(study): return
	await _click(study._mode_buttons["static"])
	await _click(study._trigger_button)
	study._process(1.0)
	_expect(study._persistent and study._controller().one_shots().is_empty(), "Static mode must show a persistent mark without emitting events.")
	_expect(is_equal_approx(float(study._controller().sample(study._guest_id, "sigh_puff")["opacity"]), 1.0), "The puff raster must remain visible in static mode.")
	if window_size.x == 1280: await _capture("lab-static-1280")
	await _click(study._mode_buttons["shake"])
	await _click(study._trigger_button)
	study._process(0.0432)
	_expect(float(study._controller().sample(study._guest_id, "sigh_puff")["offset_y_ratio"]) < 0, "Shake mode must animate the persistent raster independently.")
	await _click(study._mode_buttons["one_shot"])
	await _click(study._trigger_button)
	study._process(0.2)
	var before: Dictionary = study._controller().get_state()
	await _click(study._pause_button)
	study._process(0.4)
	_expect(study._paused and study._controller().get_state() == before, "The Lab pause button must freeze all puff clocks.")
	var language: String = study.get_language()
	await _key(KEY_F6)
	_expect(study.get_language() != language and study._controller().get_state() == before, "Language changes must preserve live event handles and samples.")
	await _key(KEY_F6)
	await _capture("lab-2d-live-" + str(window_size.x))
	await _click(study._presentation_buttons["3d"])
	_expect(study._controller().get_state() == before and study._billboard.visible and not study._cast_layer.visible, "Switching from2D to3D must preserve the same event pool and clocks.")
	_check_billboard(study, window_size)
	if window_size.x == 1280: await _capture("lab-3d-live-1280")
	await _click(study._angle_button)
	_expect(study._controller().get_state() == before and not is_zero_approx(study._camera_angle), "Changing the3D camera angle must not restart or replace events.")
	_check_billboard(study, window_size)
	await _capture("lab-3d-angle-" + str(window_size.x))
	await _click(study._presentation_buttons["2d"])
	_expect(study._controller().get_state() == before and study._cast_layer.visible, "Returning to2D must preserve the same live instance.")
	await _click(study._trigger_button)
	_expect(study.puff_state()["instance_ids"].size() == 2 and study._cast_layer._one_shot_nodes.size() == 2 and study._billboard._puffs.size() == 2, "A second trigger must create independent representations in both renderers.")
	await _click(study._pause_button)
	study._process(1.0)
	_expect(study._controller().one_shots().is_empty() and study._cast_layer._one_shot_nodes.is_empty() and study._billboard._puffs.is_empty(), "Event expiry must remove both 2D nodes and3D billboards.")
	await _click(study._trigger_button)
	await _click(study._reset_button)
	_expect(study._controller().one_shots().is_empty() and study._billboard._puffs.is_empty() and not study._paused, "Reset must clear every representation and resume the study clock.")
	await _click(study._trigger_button)
	await _click(study._guest_buttons["yuzu"])
	_expect(study._guest_id == "yuzu" and study._controller().one_shots().is_empty() and study._billboard._puffs.is_empty(), "Changing actors must remove events attached to the old cast.")
	_expect(_healthy(study), "All Lab control actions must finish without load/runtime validation errors.")


func _check_billboard(study: Control, window_size: Vector2i) -> void:
	var preview: Control = study._billboard
	var events: Array = study._controller().one_shots()
	_expect(preview._actor is Sprite3D and preview._actor.billboard == BaseMaterial3D.BILLBOARD_ENABLED, "The preview must use a genuine camera-facing Sprite3D actor.")
	_expect(preview._viewport.size == window_size, "The3D viewport must render at native 1x/2x resolution.")
	_expect(preview._puffs.size() == events.size(), "Each live event must have exactly one3D sprite.")
	for event: Dictionary in events:
		var puff: Sprite3D = preview._puffs["shot_" + str(event["instance_id"])]
		var sample: Dictionary = event["sample"]
		_expect(puff.texture == preview._mark_texture, "Each3D event must use its selected prepared raster.")
		var camera_basis: Basis = preview._camera_3d.global_basis
		var rotation := deg_to_rad(float(sample.get("rotation_degrees", 0.0)))
		var expected_right: Vector3 = camera_basis.x * cos(rotation) - camera_basis.y * sin(rotation)
		_expect(puff.global_basis.z.normalized().is_equal_approx(camera_basis.z.normalized()) and puff.global_basis.x.normalized().is_equal_approx(expected_right.normalized()), "Each3D puff must face the camera with its sampled centered rotation preserved after orbiting.")
		_expect(is_equal_approx(puff.pixel_size * puff.texture.get_height(), preview._mark_height * preview.WORLD_PIXEL_SIZE), "Billboard size must derive from original mark height before animation scale.")
		_expect(is_equal_approx(puff.scale.x, float(sample["scale"])) and is_equal_approx(puff.modulate.a, float(sample["opacity"])), "The3D renderer must consume the same scale and opacity samples as2D.")
		var anchor: Vector2 = (preview._anchor_uv - Vector2(0.5, 0.5)) * preview._actor_rect.size
		var displacement: Vector3 = puff.position - preview._actor.position
		var local_x: float = displacement.dot(preview._camera_3d.global_basis.x) / preview.WORLD_PIXEL_SIZE
		var local_y: float = -displacement.dot(preview._camera_3d.global_basis.y) / preview.WORLD_PIXEL_SIZE
		_expect(is_equal_approx(local_x, anchor.x + preview._mark_height * float(sample["offset_x_ratio"])) and is_equal_approx(local_y, anchor.y + preview._mark_height * float(sample["offset_y_ratio"])), "Billboard drift must remain in the actor's camera-facing plane after orbiting.")


func _event_fingerprint(controller: RefCounted) -> Array:
	var result: Array = []
	var states: Dictionary = controller.get_state()["one_shots"]
	for event: Dictionary in controller.one_shots():
		result.append({"actor": event["actor"], "id": event["id"], "elapsed": states[event["instance_id"]]["elapsed"], "sample": event["sample"]})
	return result


func _same_events(a: Array, b: Array) -> bool:
	if a.size() != b.size(): return false
	for index in a.size():
		if a[index]["actor"] != b[index]["actor"] or a[index]["id"] != b[index]["id"] or not is_equal_approx(float(a[index]["elapsed"]), float(b[index]["elapsed"])): return false
		for channel: String in a[index]["sample"]:
			if a[index]["sample"][channel] is String:
				if a[index]["sample"][channel] != b[index]["sample"][channel]: return false
			elif not is_equal_approx(float(a[index]["sample"][channel]), float(b[index]["sample"][channel])): return false
	return true


func _seek(game: Control, id: String) -> void:
	for step in 180:
		if str(game.current_beat()["id"]) == id or not game._load_errors.is_empty(): return
		# Let a prior beat's deliberately surviving one-shot finish as the fixture
		# traverses dialogue; zero-time navigation can carry it into a later cue.
		game._process(0.7)
		if game.current_beat().get("type") == "contact":
			if not bool(game.contact_target()["ready"]): game._next()
			_expect(game._try_contact(game.contact_target()["center"]), "Navigation must explicitly fulfill the required contact.")
			game._process(1.0)
			continue
		if game._choice_pending() and game._reveal.sample()["phase"] == "holding":
			game._choose("help_first")
		else:
			game._next()


func _open(route: String) -> Control:
	_expect(_app.open_route(route), "Route must open: " + route)
	await _settle()
	return _app.active_scene


func _healthy(scene: Control) -> bool:
	var errors: Array = scene.get("_load_errors") if scene.get("_load_errors") != null else []
	if not errors.is_empty(): _errors.append("Scene validation: " + str(errors))
	return errors.is_empty()


func _freeze_route(node: Node) -> void:
	if node.has_method("current_beat") or node.has_method("puff_state") or node.has_method("_update_character_layers"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _app.active_scene != null: _app.active_scene.set_process(false)


func _click(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The intended Lab button must be visible and enabled.")
	if button == null or not button.is_visible_in_tree() or button.disabled: return
	var point := root.get_final_transform() * button.get_global_rect().get_center()
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.global_position = point
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _key(keycode: Key) -> void:
	for pressed: bool in [true, false]:
		var event := InputEventKey.new()
		event.keycode = keycode
		event.physical_keycode = keycode
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _frame_image() -> Image:
	await _settle()
	RenderingServer.force_draw(false)
	return root.get_texture().get_image()


func _capture(label: String) -> void:
	if not _capture_enabled: return
	_expect(DirAccess.make_dir_recursive_absolute(DIRECTORY) == OK, "The Manpu capture directory must be writable.")
	var picture := await _frame_image()
	_expect(picture.get_size() == root.size, "The capture must use native window resolution.")
	_expect(picture.save_png(DIRECTORY.path_join(label + ".png")) == OK, "The capture must save: " + label)
	_capture_count += 1


func _different_pixels(a: Image, b: Image, region: Rect2) -> int:
	var bounds := Rect2i(region).intersection(Rect2i(Vector2i.ZERO, a.get_size()))
	var count := 0
	for y in range(bounds.position.y, bounds.end.y):
		for x in range(bounds.position.x, bounds.end.x):
			var left := a.get_pixel(x, y)
			var right := b.get_pixel(x, y)
			if absf(left.r - right.r) + absf(left.g - right.g) + absf(left.b - right.b) > 0.08: count += 1
	return count


func _check_falling_sweat_hosts() -> void:
	DirAccess.make_dir_recursive_absolute(FALLING_DIRECTORY)
	for factor in [1, 2]:
		root.size = Vector2i(DESIGN_SIZE) * factor
		var game := await _open("game:bishoujo_afterlight/new_game")
		var beat_id := "a_modest_name" if factor == 1 else "a_proper_hello"
		_seek(game, beat_id)
		_expect(_healthy(game) and game.current_beat()["id"] == beat_id, "The authored falling-sweat reaction must remain reachable: " + beat_id)
		if game._reveal.sample()["phase"] == "revealing":
			_expect(game._cast._manpu.one_shots().is_empty(), "The falling-sweat story cue must wait for the dialogue reveal.")
			game._next()
		var events: Array = game._cast._manpu.one_shots()
		_expect(events.size() == 1 and events[0]["id"] == "sweat_drop", "Completing the line must emit exactly one drop using the existing raster.")
		if events.size() != 1: break
		game._process(0.3)
		var handle: int = events[0]["instance_id"]
		_expect(game._cast._one_shot_nodes[handle].texture == game._cast._mark_textures["sweat_drop"], "Story presentation must select sweat-drop art for its event.")
		await _capture_falling("story-" + beat_id + "-" + str(factor), game._cast._manpu.one_shots()[0]["sample"])
		game._process(0.45)
		_expect(game._cast._manpu.one_shots().is_empty() and game._cast._one_shot_nodes.is_empty(), "The story drop must expire after its finite lifetime.")
		var study := await _open("game:presentation_lab/sigh_puff_study")
		await _click(study._variant_buttons["sweat_drop"])
		await _click(study._trigger_button)
		var cast: Control = study._cast_layer
		var actor := str(study._guest_id)
		events = cast._manpu.one_shots()
		_expect(events.size() == 1 and events[0]["id"] == "sweat_drop", "The study variant selector must emit the selected drop.")
		if events.size() != 1: break
		handle = int(events[0]["instance_id"])
		study._process(0.1)
		var node: TextureRect = cast._one_shot_nodes[handle]
		var first_center := node.get_rect().get_center()
		var first_sample: Dictionary = cast._manpu.one_shots()[0]["sample"]
		var owner: Rect2 = cast._posed_rect(actor)
		study._process(0.2)
		var last_sample: Dictionary = cast._manpu.one_shots()[0]["sample"]
		var descent := node.get_rect().get_center() - first_center
		var expected_y: float = owner.size.y * cast.MARK_HEIGHT_RATIO * (float(last_sample["offset_y_ratio"]) - float(first_sample["offset_y_ratio"]))
		_expect(cast._posed_rect(actor).is_equal_approx(owner) and is_zero_approx(descent.x) and is_equal_approx(descent.y, expected_y) and descent.y > 0.0, "On a fixed actor anchor, the rendered drop must descend by the sampled mark-height distance without lateral motion.")
		await _click(study._pause_button)
		var before := _event_fingerprint(study._controller())
		study._process(0.5)
		study.set_language("en" if factor == 1 else "ko")
		_expect(_same_events(before, _event_fingerprint(study._controller())), "Pause and language switching must preserve the falling drop's phase.")
		await _capture_falling("lab-2d-" + str(factor), last_sample)
		await _click(study._presentation_buttons["3d"])
		await _click(study._angle_button)
		_expect(_same_events(before, _event_fingerprint(study._controller())), "Changing presentation or orbit angle must preserve the existing drop instance.")
		_check_billboard(study, root.size)
		await _capture_falling("lab-3d-angled-" + str(factor), last_sample)
		# Reuse the same cast adapter for a direct coexistence check. The study
		# variant selector intentionally clears prior events when changing anchors.
		cast.mark(actor, "surprise", "step_loop")
		var puff: Dictionary = cast.emit_manpu(actor, "sigh_puff")
		_expect(puff["errors"].is_empty() and cast._manpu.one_shots().size() == 2, "A drop and Sigh Puff must coexist with the persistent loop in the event pool.")
		cast.advance(0.45)
		cast.present(Transform2D.IDENTITY)
		_expect(cast._manpu.one_shots().size() == 1 and cast._manpu.one_shots()[0]["id"] == "sigh_puff", "Drop expiry must leave a later Sigh Puff alive.")
		cast.advance(0.2)
		cast.present(Transform2D.IDENTITY)
		_expect(cast._manpu.one_shots().is_empty() and cast._one_shot_nodes.is_empty() and cast._manpu.get_state()["states"].has(actor + ":surprise"), "Both finite effects must finish while their independent persistent loop remains.")
	var sources := {}
	for path: String in ["res://addons/game_presentation/actors/presets/manpu.json", "res://addons/game_presentation/actors/manpu_animation.gd", "res://games/bishoujo_afterlight/cast_stage.gd", "res://games/bishoujo_afterlight/story.gd", "res://games/bishoujo_afterlight/story_beats.gd", "res://games/presentation_lab/afterlight/sigh_puff_study.gd", "res://games/presentation_lab/afterlight/billboard_puff_preview.gd"]:
		sources[path] = FileAccess.get_sha256(path)
	var manifest := FileAccess.open(FALLING_DIRECTORY.path_join("manifest.json"), FileAccess.WRITE)
	manifest.store_string(JSON.stringify({"sources": sources, "captures": _falling_captures, "errors": _errors}, "\t"))
	_app.queue_free()
	_app = null
	for frame in 3: await process_frame
	for issue: String in _errors: printerr("FAIL Falling Sweat integration: " + issue)
	if _errors.is_empty(): print("PASS Falling Sweat integration: existing story/2D/3D hosts, selected raster, fixed-anchor downward motion, finite expiry, Sigh Puff/loop coexistence and pause/language continuity at native 1x/2x")
	quit(0 if _errors.is_empty() else 1)


func _capture_falling(label: String, sample: Dictionary) -> void:
	var picture := await _frame_image()
	var path := FALLING_DIRECTORY.path_join(label + ".png")
	_expect(picture.get_size() == root.size and picture.save_png(path) == OK, "Falling-sweat capture must save at native resolution: " + label)
	_falling_captures.append({"file": path, "sha256": FileAccess.get_sha256(path), "sample": sample.duplicate(true), "window": [picture.get_width(), picture.get_height()]})
	print("Captured Falling Sweat: " + label)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
