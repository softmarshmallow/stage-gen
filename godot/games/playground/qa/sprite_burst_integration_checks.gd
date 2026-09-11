extends "res://qa/afterlight_ensemble_checks.gd"

## Native story and coordinate checks for the finite, texture-agnostic burst.
const BURST_OUTPUT := "res://qa/sprite-burst"
const BURST_BEAT := "the_reroute"
const BURST = preload("res://addons/game_presentation/effects/particles/sprite_burst.gd")
var _burst_captures: Array[Dictionary] = []
var _burst_metrics: Array[Dictionary] = []


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Sprite Burst integration captures require a native renderer.")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(BURST_OUTPUT)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "bishoujo_afterlight", "Use --game bishoujo_afterlight.")
	for factor in [1, 2]:
		root.size = Vector2i(1280, 900) * factor
		await _story_burst(factor)
		await _coordinate_fixture(factor)
		await _laboratory_burst(factor)
	var sources := {}
	for source: String in ["res://addons/game_presentation/effects/particles/sprite_burst.gd", "res://games/bishoujo_afterlight/story.gd", "res://games/bishoujo_afterlight/story_beats.gd", "res://games/bishoujo_afterlight/root.gd", "res://games/presentation_lab/afterlight/sprite_burst_study.gd"]:
		sources[source] = FileAccess.get_sha256(source)
	var output := FileAccess.open(BURST_OUTPUT.path_join("manifest.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"sources": sources, "captures": _burst_captures, "metrics": _burst_metrics, "errors": _errors}, "\t"))
	await _dispose_app()
	for issue: String in _errors: printerr("FAIL Sprite Burst integration: " + issue)
	if _errors.is_empty(): print("PASS Sprite Burst integration: native 1x/2x delayed finite story bursts, behind-actor layering, final world camera binding, fixed UI, active EN/KO/pause/Lab restore, cancellation, natural completion, interchangeable textures, and rendered translation/zoom correspondence")
	quit(0 if _errors.is_empty() else 1)


func _seek_burst() -> Control:
	_expect(_app.open_route("new_game"), "A fresh episode must be reachable.")
	await _settle()
	var game := _active()
	game.set_language("ko")
	for iteration in game.beats.size():
		if str(game.current_beat()["id"]) == BURST_BEAT: return game
		game._process(6.0)
		if _fulfill_contact_gate(game): continue
		if game.current_beat()["type"] == "choice": game._choices[str(game.current_beat()["id"])] = "help_first"
		game._continue_story()
	_expect(false, "The authored ward-repair burst must remain in the playable episode.")
	return game


func _story_burst(factor: int) -> void:
	var game := await _seek_burst()
	var cue: Dictionary = game.current_beat()["sprite_burst"]
	var delay := float(cue["delay_seconds"])
	var burst: Control = game._sprite_burst
	_expect(burst.get_index() < game._cast.get_index() and game._cast.get_index() < game._ui.get_index(), "The host must place the burst behind actors and before interface chrome.")
	_expect(burst.get_state().is_empty(), "The story burst must wait for its authored delay.")
	game._process(delay - 0.02)
	_expect(burst.get_state().is_empty(), "The burst must not emit before its cue boundary.")
	for age: float in [0.08, 0.35, 0.95, 1.45]:
		game._process(delay + age - game._elapsed)
		_expect(game._load_errors.is_empty(), "The story must accept the authored burst: " + str(game._load_errors))
		var state: Array = game._sprite_burst.get_state()
		_expect(game._sprite_burst._camera.is_equal_approx(game._world_transform()), "Story particles must use the final world camera, including zoom and shake.")
		_expect(state.size() == (0 if age > 1.35 else 1), "One cue must create exactly one finite burst event.")
		if not state.is_empty():
			var actor_rect: Rect2 = game._cast.get_actor_rect(str(cue["actor"]))
			var expected_origin := actor_rect.position + actor_rect.size * (cue["origin_uv"] as Vector2)
			_expect((state[0]["origin"] as Vector2).is_equal_approx(expected_origin), "Story emission must use the actor's authored world anchor.")
		await _burst_frame("story-age-" + str(age) + "-" + str(factor), game)
		if is_equal_approx(age, 0.35):
			await _language_and_detour(game, BURST_BEAT)
			game = _active()
	game._process(10.0)
	_expect(game._sprite_burst.get_state().is_empty(), "Expired story bursts must not continuously respawn.")
	game._continue_story()
	_expect(game._sprite_burst.get_state().is_empty(), "The next scene must contain no retained burst.")
	game = await _seek_burst()
	game._process(delay + 0.2)
	_expect(game._sprite_burst.get_state().size() == 1, "The cancellation check must interrupt a visible event.")
	game._continue_story()
	_expect(game._sprite_burst.get_state().is_empty(), "Advancing early must cancel the prior scene's burst immediately.")
	_burst_metrics.append({"check": "story lifecycle", "factor": factor, "cue": cue})


func _world_snapshot(game: Control) -> Dictionary:
	var result := super._world_snapshot(game)
	var events: Array = game._sprite_burst.get_state()
	for event: Dictionary in events: event.erase("instance_id")
	result["sprite_burst"] = events
	return result


func _burst_frame(label: String, game: Control = null) -> Image:
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Sprite Burst captures must retain native window resolution.")
	var path := BURST_OUTPUT.path_join(label + ".png")
	_expect(picture.save_png(path) == OK, "Sprite Burst capture must save: " + label)
	var metadata := {"file": path, "sha256": FileAccess.get_sha256(path), "window": [picture.get_width(), picture.get_height()]}
	if game != null:
		metadata["beat"] = game.current_beat()["id"]
		metadata["elapsed"] = game._elapsed
		metadata["world"] = game._world_transform()
		metadata["state"] = game._sprite_burst.get_state()
	_burst_captures.append(metadata)
	return picture


func _coordinate_fixture(factor: int) -> void:
	_app.hide()
	var holder := Control.new()
	root.add_child(holder)
	var background := ColorRect.new()
	background.color = Color.BLACK
	background.size = DESIGN_SIZE
	holder.add_child(background)
	var burst := BURST.new()
	holder.add_child(burst)
	var ui := ColorRect.new()
	ui.position = Vector2(24, 24)
	ui.size = Vector2(220, 54)
	ui.color = Color(1.0, 0.0, 0.0)
	holder.add_child(ui)
	var white := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	white.fill(Color.WHITE)
	var white_texture := ImageTexture.create_from_image(white)
	var textures: Array[Texture2D] = [white_texture]
	var options := {"count": 8, "duration": 2.0, "distance": 100.0, "start_radius": 20.0, "sprite_size": 20.0, "pop_seconds": 0.0, "seed": 88}
	_expect(burst.emit_burst(Vector2(350, 300), textures, options)["errors"].is_empty(), "The native coordinate fixture must initialize.")
	burst.advance(0.35)
	var frozen := burst.get_state()
	var base := await _burst_frame("coordinate-identity-" + str(factor))
	var translation := Vector2(48, 32)
	burst.present(Transform2D(0.0, translation))
	var shifted := await _burst_frame("coordinate-translation-" + str(factor))
	var zoom := Transform2D(Vector2(2, 0), Vector2(0, 2), Vector2.ZERO)
	burst.present(zoom)
	var zoomed := await _burst_frame("coordinate-zoom-" + str(factor))
	_expect(not burst.present(Transform2D(0.1, Vector2.ZERO)).is_empty(), "Unsupported camera rotation must be rejected.")
	var rejected := await _burst_frame("coordinate-rejected-" + str(factor))
	_expect(zoomed.get_data() == rejected.get_data(), "Rejecting a camera must preserve the previously rendered pose pixel-for-pixel.")
	var base_shape := _white_shape(base, factor)
	var shift_shape := _white_shape(shifted, factor)
	var zoom_shape := _white_shape(zoomed, factor)
	_expect(float(base_shape["area"]) > 50.0, "The particle fixture must draw visible nonempty sprite pixels.")
	_expect((shift_shape["center"] as Vector2).distance_to((base_shape["center"] as Vector2) + translation) < 0.8, "Rendered particles must translate with the world camera.")
	_expect((zoom_shape["center"] as Vector2).distance_to((base_shape["center"] as Vector2) * 2.0) < 1.5, "Rendered particle positions must scale with camera zoom.")
	_expect(absf(float(zoom_shape["area"]) / maxf(1.0, float(base_shape["area"])) - 4.0) < 0.25, "Rendered sprite area must grow with world zoom instead of remaining UI-sized.")
	var ui_rect := Rect2i(Vector2i(24, 24) * factor, Vector2i(220, 54) * factor)
	_expect(base.get_region(ui_rect).get_data() == shifted.get_region(ui_rect).get_data() and base.get_region(ui_rect).get_data() == zoomed.get_region(ui_rect).get_data(), "Camera movement must leave later UI pixels fixed.")
	_expect(_same(frozen, burst.get_state()), "Presenting multiple camera poses must never advance or reseed particles.")
	_burst_metrics.append({"check": "native coordinates", "factor": factor, "identity": base_shape, "translation": shift_shape, "zoom": zoom_shape})
	burst.present(Transform2D.IDENTITY)
	burst.advance(1.25)
	var fading := await _burst_frame("coordinate-fading-" + str(factor))
	var fading_shape := _white_shape(fading, factor)
	var expected_alpha := float(burst.get_state()[0]["particles"][0]["alpha"])
	_expect(absf(float(fading_shape["area"]) / float(base_shape["area"]) - expected_alpha) < 0.035, "The native renderer must apply the sampled fade alpha to sprite pixels.")
	burst.clear()
	burst.present(Transform2D.IDENTITY)
	var sparkle: Texture2D = load("res://assets/manpu/sparkle.png")
	var heart: Texture2D = load("res://assets/manpu/heart.png")
	var first: Array[Texture2D] = [sparkle]
	var second: Array[Texture2D] = [heart]
	var mixed: Array[Texture2D] = [heart, sparkle]
	var signatures: Array = []
	for palette: Array[Texture2D] in [first, second, mixed]:
		burst.clear()
		burst.emit_burst(Vector2(640, 450), palette, {"count": 18, "duration": 1.35, "distance": 230.0, "start_radius": 42.0, "sprite_size": 38.0, "seed": 88})
		burst.advance(0.35)
		signatures.append(_motion_signature(burst.get_state()))
		await _burst_frame("texture-palette-" + str(signatures.size()) + "-" + str(factor))
	_expect(_same(signatures[0], signatures[1]) and _same(signatures[0], signatures[2]), "Swapping one or many sprite inputs must preserve every seeded trajectory, pop, rotation and fade sample.")
	var prior_id := int(burst.get_state()[0]["instance_id"])
	var second_event: Dictionary = burst.emit_burst(Vector2(500, 400), first, {"duration": 0.25, "seed": 89})
	_expect(burst.get_state().size() == 2, "Independent triggers must overlap as separate events.")
	burst.advance(0.3)
	_expect(burst.get_state().size() == 1 and int(burst.get_state()[0]["instance_id"]) == prior_id, "A later shorter event must expire independently without resetting an existing event.")
	burst.cancel(prior_id)
	_expect(burst.get_state().is_empty() and not burst.visible, "Cancelling the last burst must remove every sprite immediately.")
	_expect(int(second_event["instance_id"]) != prior_id, "Simultaneous events need distinct handles.")
	holder.queue_free()
	await _settle()
	_app.show()


func _motion_signature(events: Array) -> Array:
	var result := events.duplicate(true)
	for event: Dictionary in result:
		event.erase("instance_id")
		event.erase("texture_count")
		for particle: Dictionary in event["particles"]:
			particle.erase("texture_index")
			particle.erase("size")
	return result


func _white_shape(picture: Image, factor: int) -> Dictionary:
	var total := Vector2.ZERO
	var area := 0.0
	for y in range(0, picture.get_height(), factor):
		for x in range(0, picture.get_width(), factor):
			var color := picture.get_pixel(x, y)
			var weight := minf(color.g, color.b)
			if weight < 0.02: continue
			total += Vector2(x, y) * weight / factor
			area += weight
	return {"center": total / maxf(1.0, area), "area": area}


func _laboratory_burst(factor: int) -> void:
	_expect(_app.open_route("game:presentation_lab/sprite_burst_study"), "The shared burst must have a dedicated laboratory route.")
	await _settle()
	var lab := _active()
	_expect(lab._load_errors.is_empty(), "The laboratory fixture must initialize without missing textures or text.")
	_expect(lab._burst_back.get_index() < lab._actor.get_index() and lab._actor.get_index() < lab._burst_front.get_index() and lab._burst_front.get_index() < lab._ui.get_index(), "The laboratory must demonstrate independent behind/front world layers beneath its UI.")
	for placement: String in ["behind", "around", "front"]:
		lab._clear_bursts()
		await _click_burst(lab._placement_buttons[placement])
		await _click_burst(lab._texture_buttons["heart" if placement == "front" else "sparkle"])
		await _click_burst(lab._emit_button)
		lab._process(0.35)
		var state: Dictionary = lab.burst_state()
		_expect(state["behind"].size() == (1 if placement == "behind" else 0), "Behind placement must emit only in the back layer.")
		_expect(state["front"].size() == (0 if placement == "behind" else 1), "Around/front placement must use the explicit foreground layer.")
		await _burst_frame("lab-" + placement + "-ko-" + str(factor))
	var prior: Dictionary = lab.burst_state()
	lab.set_language("en")
	_expect(_same(prior, lab.burst_state()), "Changing laboratory language must preserve active effects and timing.")
	await _burst_frame("lab-front-en-" + str(factor))
	lab._select_texture("mixed")
	_expect(_same(prior["front"], lab.burst_state()["front"]), "Changing a sprite palette must affect future bursts only.")
	await _click_burst(lab._emit_button)
	_expect(lab._burst_front.get_state().size() == 2, "The laboratory must permit repeated explicit bursts to overlap.")
	await _click_burst(lab._zoom_button)
	await _click_burst(lab._shake_button)
	var fixed_ui: Rect2 = lab._ui.get_rect()
	var motion_seen := false
	var previous_world: Transform2D = lab._world
	for frame in 12:
		lab._process(0.02)
		var world: Transform2D = lab._world
		motion_seen = motion_seen or not world.is_equal_approx(previous_world)
		_expect(lab._burst_back._camera.is_equal_approx(world) and lab._burst_front._camera.is_equal_approx(world), "Both burst layers must receive the final moving camera.")
		_expect(lab._actor.get_rect().is_equal_approx(world * lab._actor_rect()), "Actor and burst positions must use the same moving world coordinates.")
		_expect(lab._ui.get_rect().is_equal_approx(fixed_ui), "The interface must remain fixed during camera shake and zoom.")
		var coverage: Rect2 = world * lab._base_background
		_expect(coverage.encloses(Rect2(Vector2.ZERO, DESIGN_SIZE)), "Camera shake must keep the background covering the viewport.")
		previous_world = world
	_expect(motion_seen and lab._zoom == 1.2, "The camera test must exercise actual shake and zoom.")
	await _click_burst(lab._pause_button)
	var paused: Dictionary = lab.burst_state()
	lab._process(3.0)
	_expect(_same(paused, lab.burst_state()), "Pausing must freeze all burst, shake and host clocks.")
	await _burst_frame("lab-shake-zoom-paused-" + str(factor))
	await _click_burst(lab._pause_button)
	await _click_burst(lab.find_child("ClearBursts", true, false))
	_expect(lab._burst_back.get_state().is_empty() and lab._burst_front.get_state().is_empty(), "Clear must remove both laboratory layers immediately.")
	lab._process(8.0)
	_expect(lab._burst_back.get_state().is_empty() and lab._burst_front.get_state().is_empty(), "Laboratory events must never respawn without an explicit trigger.")
	_expect(_app.open_route("effects_menu"), "The new study must link back to the effects menu.")
	await _settle()
	await _burst_frame("lab-effects-menu-" + str(factor))
	_expect(_app.open_route("game:bishoujo_afterlight"), "The laboratory must return to the saved episode.")
	await _settle()
	_burst_metrics.append({"check": "laboratory lifecycle and camera", "factor": factor, "actual_shake_motion": motion_seen})


func _freeze_route(node: Node) -> void:
	super._freeze_route(node)
	if node.has_method("burst_state"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _click_burst(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The intended burst control must be visible and enabled.")
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
