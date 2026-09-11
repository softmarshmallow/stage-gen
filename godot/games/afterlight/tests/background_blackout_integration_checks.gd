extends "res://tests/afterlight_ensemble_checks.gd"

## Native layering and host continuity checks for Background Blackout.
const BLACKOUT_OUTPUT := "res://tests/background-blackout"
const BLACKOUT_BEAT := "the_warning"
const BACKGROUND_SAMPLE := Rect2i(40, 210, 180, 350)
var _blackout_captures: Array[Dictionary] = []
var _blackout_metrics: Array[Dictionary] = []


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Background Blackout integration captures require a native renderer.")
		quit(2)
		return
	DirAccess.make_dir_recursive_absolute(BLACKOUT_OUTPUT)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	_app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(_app.selected_game_id == "afterlight", "Use --game afterlight.")
	for factor in [1, 2]:
		root.size = Vector2i(1280, 900) * factor
		await _story_blackout(factor)
		await _laboratory_blackout(factor)
		await _opaque_sprite_fixture(factor)
	var sources := {}
	for source: String in ["res://addons/game_presentation/transitions/background_blackout.gd", "res://story.gd", "res://story_beats.gd", "res://lab/background_blackout_study.gd", "res://lab/effects_menu.gd"]:
		sources[source] = FileAccess.get_sha256(source)
	var output := FileAccess.open(BLACKOUT_OUTPUT.path_join("manifest.json"), FileAccess.WRITE)
	output.store_string(JSON.stringify({"sources": sources, "captures": _blackout_captures, "metrics": _blackout_metrics, "errors": _errors}, "\t"))
	await _dispose_app()
	for issue: String in _errors:
		printerr("FAIL Background Blackout integration: " + issue)
	if _errors.is_empty():
		print("PASS Background Blackout integration: native 1x/2x black-background/restoration pixels, preserved actor geometry/material with original alpha composition, exact opaque-sprite pixels, delayed solo story cue, hold/return/reset, EN/KO/pause/Lab continuity and actual study controls")
	quit(0 if _errors.is_empty() else 1)


func _seek_warning() -> Control:
	_expect(_app.open_route("new_game"), "A fresh episode must be reachable.")
	await _settle()
	var game := _active()
	game.set_language("ko")
	_expect(game.beats.size() == EPISODE_BEAT_COUNT, "The blackout must use the current authored episode.")
	for iteration in game.beats.size():
		if str(game.current_beat()["id"]) == BLACKOUT_BEAT:
			return game
		game._process(6.0)
		if _fulfill_contact_gate(game): continue
		if game.current_beat()["type"] == "choice":
			game._choices[str(game.current_beat()["id"])] = "help_first"
		game._continue_story()
	_expect(false, "The warning must remain in the playable episode.")
	return game


func _story_blackout(factor: int) -> void:
	var game := await _seek_warning()
	var cue: Dictionary = game.current_beat()["background_blackout"]
	var delay := float(cue.get("delay_seconds", 1.0))
	var duration := float(cue.get("fade_seconds", game.content.get("background_blackout", {}).get("fade_seconds", 0.45)))
	var blackout: ColorRect = game._background_blackout
	_expect(blackout.get_index() < game._cast.get_index() and game._cast.get_index() < game._ui.get_index(), "Background Blackout must render below actors and interface chrome.")
	_expect(game._cast.visible_ids() == ["yuzu"], "The warning must be a solo Yuzu reaction.")
	_expect(float(blackout.get_state()["strength"]) == 0.0, "Story entry must initially preserve the location.")
	game._process(delay - 0.01)
	_expect(float(blackout.get_state()["strength"]) == 0.0, "The background must remain visible until the authored delay.")
	var actor: TextureRect = game._cast._sprites["yuzu"]
	var actor_before := _actor_snapshot(actor)
	var camera_before: Transform2D = game._world_transform()
	var before := await _blackout_frame("story-before-" + str(factor), blackout, game)
	game._process(0.01 + duration * 0.5)
	var middle_state: Dictionary = blackout.get_state()
	_expect(float(middle_state["strength"]) > 0.0 and float(middle_state["strength"]) < 1.0 and bool(middle_state["active"]), "The story must show a real partial background fade.")
	_expect(_same(actor_before, _actor_snapshot(actor)) and camera_before.is_equal_approx(game._world_transform()), "Fading the background must not move, scale or recolor the settled actor/camera.")
	await _blackout_frame("story-midpoint-" + str(factor), blackout, game)
	await _language_and_detour(game, BLACKOUT_BEAT)
	game = _active()
	blackout = game._background_blackout
	actor = game._cast._sprites["yuzu"]
	game._process(duration * 0.5 + 0.01)
	_expect(float(blackout.get_state()["strength"]) == 1.0 and not bool(blackout.get_state()["active"]), "The story cue must reach exact held black.")
	_expect(_same(actor_before, _actor_snapshot(actor)) and camera_before.is_equal_approx(game._world_transform()), "Completion must preserve the actor pose, material, colors and camera.")
	var full := await _blackout_frame("story-black-" + str(factor), blackout, game)
	_expect(_is_black(full, factor), "The exposed story background must be solid black at full strength.")
	var core := _actor_core_difference(before, full, actor, factor)
	_expect(int(core["samples"]) > 100 and int(core["unexpected_changes"]) == 0, "Story actor cores must retain their art with only the original source-alpha composition difference: " + str(core))
	game._process(8.0)
	_expect(str(game.current_beat()["id"]) == BLACKOUT_BEAT and float(blackout.get_state()["strength"]) == 1.0, "Full black must hold for explicit story continuation.")
	game._continue_story()
	_expect(str(game.current_beat()["id"]) == "verified_trouble", "Explicit continuation must resume the existing next line.")
	var restore: Dictionary = blackout.get_state()
	_expect(float(restore["target"]) == 0.0 and bool(restore["active"]), "The following beat must fade the background back in.")
	game._process(float(restore["duration_seconds"]) + 1.0)
	_expect(float(blackout.get_state()["strength"]) == 0.0 and not blackout.visible, "The following scene must fully release the black layer.")
	var returned := await _blackout_frame("story-returned-" + str(factor), blackout, game)
	_expect(not _is_black(returned, factor), "The story location must become visible again.")
	game = await _seek_warning()
	game._process(delay + duration * 0.5)
	game._continue_story()
	game._process(3.0)
	_expect(float(game._background_blackout.get_state()["strength"]) == 0.0, "Continuing during the fade must restore rather than leak the interrupted blackout.")
	_expect(_app.open_route("new_game"), "Restart must remain available after a blackout.")
	await _settle()
	_expect(float(_active()._background_blackout.get_state()["strength"]) == 0.0, "A new game must not retain blackout state.")
	_blackout_metrics.append({"check": "story cue and continuity", "factor": factor, "delay_seconds": delay, "duration_seconds": duration, "opaque_actor_pixels": core})


func _world_snapshot(game: Control) -> Dictionary:
	var result := super._world_snapshot(game)
	result["background_blackout"] = game._background_blackout.get_state()
	return result


func _actor_snapshot(actor: TextureRect) -> Dictionary:
	return {"position": actor.position, "size": actor.size, "scale": actor.scale, "rotation": actor.rotation,
		"modulate": actor.modulate, "self_modulate": actor.self_modulate, "material": actor.material,
		"texture_size": actor.texture.get_size(), "texture_pixels": hash(actor.texture.get_image().get_data()),
		"visible": actor.visible, "global_rect": actor.get_global_rect()}


func _blackout_frame(label: String, blackout: ColorRect = null, game: Control = null) -> Image:
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	_expect(picture.get_size() == root.size, "Blackout captures must retain native window resolution.")
	var path := BLACKOUT_OUTPUT.path_join(label + ".png")
	_expect(picture.save_png(path) == OK, "Blackout capture must save: " + label)
	var metadata := {"file": path, "sha256": FileAccess.get_sha256(path), "window": [picture.get_width(), picture.get_height()], "blackout": blackout.get_state() if is_instance_valid(blackout) else {}}
	if game != null:
		metadata["beat"] = game.current_beat()["id"]
		metadata["elapsed"] = game._elapsed
		metadata["world"] = game._world_transform()
		metadata["cast"] = game._cast.visible_ids()
	_blackout_captures.append(metadata)
	return picture


func _is_black(picture: Image, factor: int) -> bool:
	var region := picture.get_region(Rect2i(BACKGROUND_SAMPLE.position * factor, BACKGROUND_SAMPLE.size * factor))
	for y in region.get_height():
		for x in region.get_width():
			var pixel := region.get_pixel(x, y)
			if pixel.r != 0.0 or pixel.g != 0.0 or pixel.b != 0.0:
				return false
	return true


func _actor_core_difference(before: Image, after: Image, actor: TextureRect, factor: int) -> Dictionary:
	var source := actor.texture.get_image()
	var rect := actor.get_global_rect()
	var samples := 0
	var changed := 0
	var maximum_error := 0.0
	# Prepared sprites peak at alpha254/255, so even their cores retain a small
	# background contribution. Check only source-alpha interiors, allowing their
	# authored transparency plus two 8-bit levels of texture/blend quantization.
	for y in range(170, 620, 2):
		for x in range(260, 1010, 2):
			var logical := Vector2(float(x) + 0.5 / factor, float(y) + 0.5 / factor)
			if not rect.has_point(logical):
				continue
			var uv := (logical - rect.position) / rect.size
			var source_point := Vector2i(uv * Vector2(source.get_size()))
			if source_point.x < 4 or source_point.y < 4 or source_point.x >= source.get_width() - 4 or source_point.y >= source.get_height() - 4:
				continue
			var minimum_alpha := 1.0
			for offset: Vector2i in [Vector2i.ZERO, Vector2i(-4, 0), Vector2i(4, 0), Vector2i(0, -4), Vector2i(0, 4), Vector2i(-4, -4), Vector2i(-4, 4), Vector2i(4, -4), Vector2i(4, 4)]:
				minimum_alpha = minf(minimum_alpha, source.get_pixelv(source_point + offset).a)
			if minimum_alpha < 0.985:
				continue
			var a := before.get_pixel(x * factor, y * factor)
			var b := after.get_pixel(x * factor, y * factor)
			var error := maxf(absf(a.r - b.r), maxf(absf(a.g - b.g), absf(a.b - b.b)))
			samples += 1
			if error > 1.0 - minimum_alpha + 2.0 / 255.0:
				changed += 1
			maximum_error = maxf(maximum_error, error)
	return {"samples": samples, "unexpected_changes": changed, "maximum_rgb_error": maximum_error}


func _click_blackout(button: Button) -> void:
	_expect(button != null and button.is_visible_in_tree() and not button.disabled, "The intended blackout control must be visible and enabled.")
	if button == null or not button.is_visible_in_tree() or button.disabled:
		return
	var point := root.get_final_transform() * button.get_global_rect().get_center()
	for pressed: bool in [true, false]:
		var event := InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.position = point
		event.global_position = point
		event.pressed = pressed
		root.push_input(event, false)
	await _settle()


func _laboratory_blackout(factor: int) -> void:
	_expect(_app.open_route("game:lab/background_blackout_study"), "Background Blackout must have a dedicated study route.")
	await _settle()
	var lab := _active()
	_expect(lab._load_errors.is_empty(), "The blackout study must initialize without errors: " + str(lab._load_errors))
	lab.set_language("ko")
	var blackout: ColorRect = lab._blackout
	var actor: TextureRect = lab._actor
	_expect(blackout.get_index() < actor.get_index() and actor.get_index() < lab._ui.get_index(), "The study must draw unchanged actors above the background blackout, with its UI last.")
	_expect(blackout.get_rect().is_equal_approx(Rect2(Vector2.ZERO, DESIGN_SIZE)), "The blackout layer must cover the complete logical viewport.")
	_expect(blackout.material == null and blackout.mouse_filter == Control.MOUSE_FILTER_IGNORE, "The black background coverage must need no shader and intercept no input.")
	var baseline := _actor_snapshot(actor)
	var before := await _blackout_frame("lab-before-ko-" + str(factor), blackout)
	_expect(not _is_black(before, factor), "The original laboratory scene must have visible background pixels.")
	await _click_blackout(lab._blackout_button)
	var duration: float = blackout.get_state()["duration_seconds"]
	lab._process(duration * 0.5)
	_expect(_same(baseline, _actor_snapshot(actor)), "Starting/fading the laboratory blackout must preserve all actor presentation properties.")
	var midpoint := await _blackout_frame("lab-midpoint-ko-" + str(factor), blackout)
	var midpoint_state: Dictionary = blackout.get_state()
	var partial := _background_blend_error(before, midpoint, factor, float(midpoint_state["strength"]))
	_expect(float(partial["maximum_rgb_error"]) < 0.012, "The midpoint must darken only the background by its sampled opacity: " + str(partial))
	await _click_blackout(lab._pause_button)
	var frozen: Dictionary = lab.blackout_state()
	lab._process(4.0)
	_expect(_same(frozen, lab.blackout_state()), "The study Pause button must freeze an active fade.")
	lab.set_language("en")
	_expect(_same(frozen, lab.blackout_state()) and _same(baseline, _actor_snapshot(actor)), "Language changes must preserve the active fade and actor.")
	await _blackout_frame("lab-paused-en-" + str(factor), blackout)
	lab.set_language("ko")
	await _click_blackout(lab._pause_button)
	lab._process(duration * 0.5 + 0.01)
	_expect(float(blackout.get_state()["strength"]) == 1.0 and not blackout.is_active(), "The study fade must reach exact opaque black and stop advancing.")
	var full := await _blackout_frame("lab-black-ko-" + str(factor), blackout)
	_expect(_is_black(full, factor), "Exposed laboratory scenery must be exact black.")
	var core := _actor_core_difference(before, full, actor, factor)
	_expect(int(core["samples"]) > 100 and int(core["unexpected_changes"]) == 0, "Prepared actor cores must retain their original art and source-alpha composition over black: " + str(core))
	_expect(_same(baseline, _actor_snapshot(actor)), "At full black the original actor position/scale/material/colors must remain intact.")
	lab._process(5.0)
	_expect(float(blackout.get_state()["strength"]) == 1.0, "Black background must hold until a new explicit request.")
	await _click_blackout(lab._restore_button)
	lab._process(float(blackout.get_state()["duration_seconds"]) + 0.01)
	_expect(float(blackout.get_state()["strength"]) == 0.0 and not blackout.visible, "Restore must completely remove the coverage layer.")
	var restored := await _blackout_frame("lab-restored-ko-" + str(factor), blackout)
	var world_crop := Rect2i(0, 130, 1280, 560)
	world_crop.position *= factor
	world_crop.size *= factor
	_expect(before.get_region(world_crop).get_data() == restored.get_region(world_crop).get_data(), "Restoration must reproduce all isolated world/actor pixels, including alpha edges, exactly.")
	await _click_blackout(lab._blackout_button)
	lab._process(0.1)
	await _click_blackout(lab.find_child("ResetBlackout", true, false))
	_expect(float(blackout.get_state()["strength"]) == 0.0 and not blackout.is_active() and not lab._paused, "Reset must clear an unfinished fade without moving the actor.")
	# A real keyboard event on the focused slider selects its minimum duration.
	lab._duration_slider.grab_focus()
	for pressed: bool in [true, false]:
		var key := InputEventKey.new()
		key.keycode = KEY_HOME
		key.pressed = pressed
		root.push_input(key, false)
	await _settle()
	_expect(lab._duration == 0.0 and lab._duration_slider.value == 0.0, "The duration slider must accept real keyboard adjustment.")
	await _click_blackout(lab._blackout_button)
	_expect(float(blackout.get_state()["strength"]) == 1.0 and not blackout.is_active(), "Zero-duration study blackout must be immediate.")
	await _click_blackout(lab._restore_button)
	_expect(float(blackout.get_state()["strength"]) == 0.0 and _same(baseline, _actor_snapshot(actor)), "An immediate restore must also preserve the actor.")
	_expect(_app.open_route("effects_menu"), "The study must return to the effects menu.")
	await _settle()
	await _effects_menu_frames(factor)
	_expect(_app.open_route("game:afterlight"), "The lab must return to the saved episode.")
	await _settle()
	_blackout_metrics.append({"check": "laboratory pixels and controls", "factor": factor, "opaque_actor_pixels": core, "midpoint_blend": partial})


func _effects_menu_frames(factor: int) -> void:
	var menu := _active()
	for language: String in ["ko", "en"]:
		menu.set_language(language)
		await _settle()
		var cards := 0
		for binding: Dictionary in menu._text_bindings:
			var key := str(binding["key"])
			if not key.begins_with("study.") or not key.ends_with(".description") or key == "study.effects.description":
				continue
			var description: Label = binding["node"]
			_expect(description.size.x <= 354.01 and description.get_line_count() <= 3, "Effects-menu descriptions must fit their column without crossing Explore controls: " + language + " / " + key)
			cards += 1
		_expect(cards == 7, "All seven effects cards must remain readable in the new two-column menu.")
		await _blackout_frame("lab-effects-menu-" + ("en-" if language == "en" else "") + str(factor))


func _background_blend_error(before: Image, after: Image, factor: int, strength: float) -> Dictionary:
	var maximum := 0.0
	var total := 0.0
	var samples := 0
	for y in range(BACKGROUND_SAMPLE.position.y, BACKGROUND_SAMPLE.end.y, 3):
		for x in range(BACKGROUND_SAMPLE.position.x, BACKGROUND_SAMPLE.end.x, 3):
			var a := before.get_pixel(x * factor, y * factor)
			var b := after.get_pixel(x * factor, y * factor)
			var error := maxf(absf(b.r - a.r * (1.0 - strength)), maxf(absf(b.g - a.g * (1.0 - strength)), absf(b.b - a.b * (1.0 - strength))))
			maximum = maxf(maximum, error)
			total += error
			samples += 1
	return {"samples": samples, "maximum_rgb_error": maximum, "mean_rgb_error": total / maxf(samples, 1)}


func _freeze_route(node: Node) -> void:
	super._freeze_route(node)
	if node.has_method("blackout_state"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


func _opaque_sprite_fixture(factor: int) -> void:
	_app.hide()
	var holder := Control.new()
	root.add_child(holder)
	holder.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var background := ColorRect.new()
	background.color = Color(0.4, 0.65, 0.8)
	background.size = DESIGN_SIZE
	holder.add_child(background)
	var blackout: ColorRect = load("res://addons/game_presentation/transitions/background_blackout.gd").new()
	holder.add_child(blackout)
	var pixels := Image.create_empty(48, 64, false, Image.FORMAT_RGBA8)
	pixels.fill(Color(1.0, 0.25, 0.45, 0.5))
	pixels.fill_rect(Rect2i(4, 4, 40, 56), Color(1.0, 0.25, 0.45, 1.0))
	var actor := TextureRect.new()
	actor.texture = ImageTexture.create_from_image(pixels)
	actor.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	actor.position = Vector2(320, 240)
	actor.size = Vector2(200, 300)
	holder.add_child(actor)
	var ui := ColorRect.new()
	ui.color = Color(0.25, 1.0, 0.3)
	ui.position = Vector2(20, 20)
	ui.size = Vector2(210, 60)
	holder.add_child(ui)
	var before := await _blackout_frame("opaque-fixture-before-" + str(factor), blackout)
	blackout.fade_to(1.0, 0.0)
	var after := await _blackout_frame("opaque-fixture-black-" + str(factor), blackout)
	var opaque_region := Rect2i(Vector2i(350, 275) * factor, Vector2i(140, 230) * factor)
	var ui_region := Rect2i(Vector2i(20, 20) * factor, Vector2i(210, 60) * factor)
	_expect(before.get_region(opaque_region).get_data() == after.get_region(opaque_region).get_data(), "Opaque sprite pixels must be exactly invariant when the background alone changes.")
	_expect(before.get_region(ui_region).get_data() == after.get_region(ui_region).get_data(), "UI rendered above the actor must also be pixel-identical during blackout.")
	_expect(_is_black(after, factor), "The independent fixture must also reach exact black background.")
	blackout.fade_to(0.0, 0.0)
	await _settle()
	RenderingServer.force_draw(false)
	var restored := root.get_texture().get_image()
	_expect(before.get_data() == restored.get_data(), "The complete fixture, including partially transparent sprite edges, must restore pixel-for-pixel.")
	_blackout_metrics.append({"check": "opaque sprite and transparent-edge fixture", "factor": factor, "opaque_pixels": opaque_region.get_area(), "exact_core_and_ui_match": true})
	holder.queue_free()
	await _settle()
	_app.show()
