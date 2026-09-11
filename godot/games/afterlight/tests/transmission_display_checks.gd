extends SceneTree

## Focused native proof of the shared TV shader on Eira's framed transmission feed:
## the 70% default, exact zero-strength bypass, locality and animation.
const OUTPUT := "res://tests/transmission-display"
var _errors: Array[String] = []
var _metrics: Array[Dictionary] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	if DisplayServer.get_name() == "headless":
		printerr("Transmission display pixel checks require a native renderer.")
		quit(2)
		return
	_expect(DirAccess.make_dir_recursive_absolute(OUTPUT) == OK, "Capture directory must be writable.")
	for window_size: Vector2i in [Vector2i(1280, 900), Vector2i(2560, 1800)]:
		root.size = window_size
		await _transmission(window_size.x)
	var report := FileAccess.open(OUTPUT.path_join("pixel-checks.json"), FileAccess.WRITE)
	report.store_string(JSON.stringify({"shader_sha256": FileAccess.get_sha256("res://addons/game_presentation/effects/shaders/character_hologram.gdshader"), "checks": _metrics, "errors": _errors}, "\t"))
	for issue: String in _errors: printerr("FAIL transmission display: " + issue)
	if _errors.is_empty(): print("PASS transmission display: native 1x/2x framed Eira feed, 70% default, zero-strength pixel bypass, temporal animation, and unchanged pixels outside the feed")
	quit(0 if _errors.is_empty() else 1)


func _transmission(width: int) -> void:
	var app: Control = load("res://main.tscn").instantiate()
	root.add_child(app)
	app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	await _settle()
	_expect(app.open_route("game:afterlight/new_game"), "The actual Afterlight host must open.")
	await _settle()
	var game: Control = app.active_scene
	game.set_process(false)
	game.set_language("ko")
	game._bind_background(3)
	_seek(game, "eira_on_the_relay")
	var display: Control = game._transmission_display
	var before: Dictionary = display.snapshot()
	_expect(before["visible"] and before["feed_clipped"] and before["actor_id"] == "eira", "Eira must appear inside her clipped floating display.")
	_expect(is_equal_approx(float(before["hologram_strength"]), 0.70), "The framed TV feed must use the stronger 70% default.")
	var shader_material: ShaderMaterial = display._feed.material
	display._feed.material = null
	var normal := await _capture("eira-normal-" + str(width))
	display._feed.material = shader_material
	shader_material.set_shader_parameter("strength", 0.0)
	var zero := await _capture("eira-zero-" + str(width))
	shader_material.set_shader_parameter("strength", float(before["hologram_strength"]))
	var current := await _capture("eira-default-" + str(width))
	shader_material.set_shader_parameter("effect_time", float(before["effect_time"]) + 2.0)
	var later := await _capture("eira-later-" + str(width))
	var feed := _pixels(before["feed_rect"]).grow(2.0)
	_compare(normal, zero, [], "framed zero bypass " + str(width), false)
	_compare(normal, current, [feed], "framed effect locality " + str(width), true)
	_compare(current, later, [feed], "framed animated output " + str(width), true)
	_seek(game, "the_return_channel")
	var close: Dictionary = display.snapshot()
	_expect((close["feed_rect"] as Rect2).encloses(close["face_rect"]), "The stronger close-up must retain the complete face within the feed.")
	_expect(not (close["frame_rect"] as Rect2).intersects(game._speaker.get_rect()), "The close TV frame must remain clear of dialogue text.")
	await _capture("eira-close-" + str(width))
	app.queue_free()
	await _settle()


func _seek(game: Control, beat_id: String) -> void:
	for index in game.beats.size():
		if game.beats[index]["id"] == beat_id:
			game._beat_index = index
			game._enter_beat()
			game._process(1.8)
			game._reveal.request_advance()
			game._render()
			return
	_expect(false, "Missing focused capture beat: " + beat_id)


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
