extends SceneTree

## Focused native proof of the shared TV shader on a tactical actor. The framed
## Eira feed is proven by Afterlight's transmission_display_checks.
const LEGACY = preload("res://tests/legacy_presentation.gd")
const DEMOS = preload("res://lab/fixture.gd")
const HOLOGRAM = preload("res://addons/game_presentation/effects/shaders/character_hologram.gdshader")
const DESIGN_SIZE := Vector2(1280, 900)
const OUTPUT := "res://tests/hologram-defaults"
var _errors: Array[String] = []
var _metrics: Array[Dictionary] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Hologram pixel checks require a native renderer.")
		quit(2)
		return
	_expect(DirAccess.make_dir_recursive_absolute(OUTPUT) == OK, "Capture directory must be writable.")
	for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window_size
		await _tactical(window_size.x)
		await _alpha_fixture(window_size.x / 1280)
	var report := FileAccess.open(OUTPUT.path_join("pixel-checks.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"shader_sha256": FileAccess.get_sha256("res://addons/game_presentation/effects/shaders/character_hologram.gdshader"), "checks": _metrics, "errors": _errors}, "\t"))
	for issue: String in _errors: printerr("FAIL hologram defaults: " + issue)
	if _errors.is_empty(): print("PASS hologram defaults: native 1x/2x tactical actor, 90% default, zero-strength pixel bypass, temporal animation, alpha outline, independent controls, and unchanged pixels outside the intended actor/feed")
	quit(0 if _errors.is_empty() else 1)


func _tactical(width: int) -> void:
	var stage := LEGACY.new()
	DEMOS.prepare_scene(stage)
	stage.standalone_checks = true
	root.add_child(stage)
	stage.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	stage.set_process(false)
	await _settle()
	_errors.append_array(stage._load_errors)
	_errors.append_array(stage._validate_character_effects())
	var captures := {}
	for state: String in ["effect_normal", "effect_zero", "hologram_sera", "hologram_sera_later"]:
		stage._prepare_capture(state)
		stage.queue_redraw()
		captures[state] = await _capture("tactical-" + state + "-" + str(width))
	_expect(is_equal_approx(float(stage._character_effects["sera"]["strength"]), 0.9), "The tactical actor must use the stronger 90% default.")
	var controls: Array[Rect2] = []
	for control: Control in [stage._effect_target_button, stage._effect_toggle_button, stage._effect_strength_slider, stage._effect_strength_label]:
		controls.append(_pixels(control.get_rect()).grow(2.0))
	var actor := _pixels(stage._actor_nodes["sera"].get_rect()).grow(2.0)
	_compare(captures["effect_normal"], captures["effect_zero"], controls, "tactical zero bypass " + str(width), false)
	var actor_and_controls := controls.duplicate()
	actor_and_controls.append(actor)
	_compare(captures["effect_normal"], captures["hologram_sera"], actor_and_controls, "tactical effect locality " + str(width), true)
	_compare(captures["hologram_sera"], captures["hologram_sera_later"], [actor], "tactical animated output " + str(width), true)
	stage.queue_free()
	await _settle()


func _alpha_fixture(scale_factor: int) -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(96, 96) * scale_factor
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var picture := Image.create(48, 48, false, Image.FORMAT_RGBA8)
	for y in 48:
		for x in 48:
			var inside := Vector2(x - 24, y - 24).length() < 17.0
			picture.set_pixel(x, y, Color(0.85, 0.35, 0.22, 1.0 if inside else 0.0))
	var sprite := TextureRect.new()
	sprite.texture = ImageTexture.create_from_image(picture)
	sprite.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	sprite.size = viewport.size
	viewport.add_child(sprite)
	await _settle()
	RenderingServer.force_draw(false)
	var normal := viewport.get_texture().get_image()
	var material := ShaderMaterial.new()
	material.shader = HOLOGRAM
	material.set_shader_parameter("strength", 0.0)
	sprite.material = material
	RenderingServer.force_draw(false)
	var zero := viewport.get_texture().get_image()
	_expect(normal.get_data() == zero.get_data(), "Zero-strength shader must preserve exact RGBA including transparent edges at " + str(scale_factor) + "x.")
	material.set_shader_parameter("strength", 0.9)
	material.set_shader_parameter("effect_time", 1.75)
	RenderingServer.force_draw(false)
	var effected := viewport.get_texture().get_image()
	var leaked_pixels := 0
	for y in normal.get_height():
		for x in normal.get_width():
			if normal.get_pixel(x, y).a == 0.0 and effected.get_pixel(x, y).a > 0.0: leaked_pixels += 1
	_expect(leaked_pixels == 0, "Transmission displacement must not paint outside the original alpha silhouette.")
	_metrics.append({"check": "transparent outline " + str(scale_factor) + "x", "outside_alpha_pixels": leaked_pixels, "zero_rgba_identical": normal.get_data() == zero.get_data()})
	viewport.queue_free()
	await _settle()


func _compare(first: Image, second: Image, allowed: Array, label: String, must_change: bool) -> void:
	_expect(first.get_size() == second.get_size(), "Pixel comparison dimensions must match: " + label)
	var a := first.get_data()
	var b := second.get_data()
	var outside := 0
	var changed := 0
	var width := first.get_width()
	for offset in range(0, a.size(), 4):
		if a[offset] == b[offset] and a[offset + 1] == b[offset + 1] and a[offset + 2] == b[offset + 2] and a[offset + 3] == b[offset + 3]: continue
		changed += 1
		var pixel := offset / 4
		var point := Vector2(pixel % width, pixel / width)
		var in_target := false
		for rect: Rect2 in allowed:
			if rect.has_point(point):
				in_target = true
				break
		if not in_target: outside += 1
	_expect(outside == 0, "Pixels changed outside the intended treatment region: " + label + " (" + str(outside) + ")")
	if must_change: _expect(changed > 100, "The TV effect or its animated time must visibly change pixels: " + label)
	_metrics.append({"check": label, "changed_pixels": changed, "outside_allowed_pixels": outside})


func _pixels(rect: Rect2) -> Rect2:
	return root.get_final_transform() * rect


func _capture(label: String) -> Image:
	await _settle()
	RenderingServer.force_draw(false)
	var picture := root.get_texture().get_image()
	picture.convert(Image.FORMAT_RGBA8)
	_expect(picture.get_size() == root.size, "Captures must render at native window resolution.")
	_expect(picture.save_png(OUTPUT.path_join(label + ".png")) == OK, "Capture must save: " + label)
	return picture


func _settle() -> void:
	for frame in 3: await process_frame


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
