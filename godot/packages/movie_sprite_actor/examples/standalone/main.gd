extends Node2D

## This composition root owns all timing, face direction, transforms and UI.
## Its assets are original procedural fixtures written locally without providers.
const ACTOR = preload("res://addons/movie_sprite_actor/movie_sprite_actor.gd")
const CONTENT_IO = preload("res://addons/content_io/local_content.gd")
const FIXTURES = preload("res://fixture_factory.gd")
var _actors: Array[Node2D] = []
var _labels: Array[Label] = []
var _clock := 0.0
var _paused := false
var _speaking := true
var _checking := false
var _checks := 0
var _failures: Array[String] = []
var _content_root := ""
var _capture_directory := ""


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	_checking = "--smoke" in args
	var capture_index := args.find("--capture-dir")
	if capture_index >= 0 and capture_index + 1 < args.size(): _capture_directory = args[capture_index + 1]
	_content_root = ProjectSettings.globalize_path("user://synthetic_content")
	if not _capture_directory.is_empty(): _content_root = _capture_directory.path_join("synthetic_content")
	# Each launch writes a fresh fixture set; a failed write cannot reuse old data.
	_content_root = _content_root.path_join(str(Time.get_ticks_usec()))
	_make_ui()
	_add_actor("left", Vector2i(129, 225), 11, 7.5, Vector2i(3, 2), Vector2(185, 180), 2.0, false)
	_add_actor("right", Vector2i(193, 257), 17, 13.25, Vector2i(2, 2), Vector2(650, 180), 1.75, true)
	if _checking: _run_proof.call_deferred()


func _add_actor(name: String, canvas: Vector2i, count: int, fps: float, grid: Vector2i, at: Vector2, size: float, wink: bool) -> void:
	var directory := _content_root.path_join(name)
	var manifest: Dictionary = FIXTURES.create(directory, canvas, count, fps, grid, wink)
	if manifest.has("errors"):
		_expect(false, name + ": " + str(manifest.errors))
		return
	var loader := CONTENT_IO.new()
	_expect(loader.configure(directory, "files").is_empty(), name + ": independent loader configures.")
	var actor := ACTOR.new()
	add_child(actor)
	actor.position = at
	actor.scale = Vector2.ONE * size
	_expect(actor.configure(loader, "manifest.json").is_empty(), name + ": copied addon configures.")
	_actors.append(actor)
	var label := _label(Vector2(at.x - 25, 650), "%d x %d  /  %d frames  /  %s FPS" % [canvas.x, canvas.y, count, str(fps)], 18)
	_labels.append(label)


func _process(delta: float) -> void:
	if _checking: return
	if not _paused: _clock += delta
	for index: int in range(_actors.size()):
		var actor := _actors[index]
		actor.advance(delta)
		if actor.snapshot().state != "ready": continue
		var blink := fmod(_clock + index * 0.7, 3.2) < 0.18
		actor.set_eye_state("eyes_closed" if blink else "rest")
		var mouth := "rest"
		if _speaking and fmod(_clock, 4.0) < 2.9:
			mouth = "mouth_a" if int(_clock / 0.16) % 2 == 0 else "mouth_o"
		actor.set_mouth_state(mouth)
		_labels[index].text = "%d x %d  /  %d frames  /  %s FPS\nFrame %02d  |  loop %d  |  %s" % [actor.snapshot().frame_size.x, actor.snapshot().frame_size.y, actor.snapshot().frame_count, str(actor.snapshot().fps), actor.snapshot().frame_index, actor.snapshot().loop_count, "bilateral blink" if index == 0 else "canvas-left wink"]


func _unhandled_key_input(event: InputEvent) -> void:
	if _checking or not event is InputEventKey or not event.pressed or event.echo: return
	if event.keycode == KEY_SPACE:
		_paused = not _paused
		for actor: Node2D in _actors: actor.set_paused(_paused)
	elif event.keycode == KEY_M:
		_speaking = not _speaking
	elif event.keycode == KEY_R:
		_clock = 0.0
		for actor: Node2D in _actors: actor.seek(0.0)


func _draw() -> void:
	draw_rect(Rect2(0, 0, 1100, 760), Color("101b29"))
	for x: int in range(0, 1100, 40): draw_line(Vector2(x, 148), Vector2(x, 630), Color("1a2b3d"), 1.0)
	for y: int in range(150, 630, 40): draw_line(Vector2(0, y), Vector2(1100, y), Color("1a2b3d"), 1.0)
	draw_line(Vector2(70, 630), Vector2(1030, 630), Color("5e8daa"), 2.0)


func _make_ui() -> void:
	_label(Vector2(54, 34), "MOVIE SPRITE ACTOR", 32)
	_label(Vector2(54, 84), "Independent body playback + host-controlled eyes and mouth", 21)
	_label(Vector2(54, 116), "Original procedural fixtures  /  two different canvases, grids and timebases", 16)
	_label(Vector2(54, 724), "SPACE  pause    M  speaking motion    R  replay", 16)


func _label(at: Vector2, text: String, font_size: int) -> Label:
	var label := Label.new()
	label.position = at
	label.text = text
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color("dcebf3"))
	add_child(label)
	return label


func _run_proof() -> void:
	_expect(_actors.size() == 2, "Both independent fixtures were prepared successfully.")
	for actor: Node2D in _actors: await _settle(actor)
	for actor: Node2D in _actors:
		_expect(actor.snapshot().state == "ready", "Copied consumer reaches ready.")
		var duration: float = actor.snapshot().duration_seconds
		actor.seek(duration * 3.0 + 0.2 / float(actor.snapshot().fps))
		await _settle(actor)
		_expect(actor.snapshot().loop_count == 3 and actor.snapshot().frame_index == 0, "Independent consumer wraps its authored timebase.")
		actor.set_paused(true)
		var before: float = actor.snapshot().clock_seconds
		actor.advance(30.0)
		_expect(actor.snapshot().clock_seconds == before, "Independent host pause freezes playback.")
		actor.set_eye_state("eyes_closed")
		actor.set_mouth_state("mouth_a")
		_expect(actor.snapshot().eyes == "eyes_closed" and actor.snapshot().mouth == "mouth_a", "Facial channels coexist independently.")
	if DisplayServer.get_name() != "headless" and _actors.size() == 2:
		await _verify_rendering()
		if not _capture_directory.is_empty():
			DirAccess.make_dir_recursive_absolute(_capture_directory)
			await RenderingServer.frame_post_draw
			_expect(get_viewport().get_texture().get_image().save_png(_capture_directory.path_join("independent-consumer.png")) == OK, "Native consumer capture writes.")
	var snapshots: Array = []
	for actor: Node2D in _actors:
		snapshots.append(actor.snapshot())
		actor.shutdown()
		_expect(actor.snapshot().resident_page_count == 0 and not actor.snapshot().worker_active, "Independent consumer shuts down with no resident pages or worker.")
	var report := {"schema_version": 1, "status": "passed" if _failures.is_empty() else "failed", "checks": _checks, "errors": _failures, "renderer": DisplayServer.get_name(), "pixel_checks_executed": DisplayServer.get_name() != "headless", "snapshots": snapshots}
	if not _capture_directory.is_empty():
		DirAccess.make_dir_recursive_absolute(_capture_directory)
		FIXTURES.write_json(_capture_directory.path_join("verification.json"), report)
	print(JSON.stringify(report))
	get_tree().quit(0 if _failures.is_empty() else 1)


func _verify_rendering() -> void:
	var canvas := Vector2i(129, 225)
	var viewport := SubViewport.new()
	viewport.size = canvas * 2 + Vector2i(40, 40)
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(viewport)
	var actor := ACTOR.new()
	viewport.add_child(actor)
	actor.position = Vector2(20, 20)
	actor.scale = Vector2(2, 2)
	var loader := CONTENT_IO.new()
	loader.configure(_content_root.path_join("left"), "files")
	actor.configure(loader, "manifest.json")
	await _settle(actor)
	actor.seek(10.2 / 7.5)
	await _settle(actor)
	actor.set_paused(true)
	await RenderingServer.frame_post_draw
	var baseline := viewport.get_texture().get_image()
	actor.set_eye_state("eyes_closed")
	actor.set_mouth_state("mouth_a")
	await RenderingServer.frame_post_draw
	var changed := viewport.get_texture().get_image()
	var eye := FIXTURES.eye_rect(canvas)
	var mouth := FIXTURES.mouth_rect(canvas)
	var eye_pixel := Vector2i(20, 20) + (eye.position + eye.size / 2) * 2
	var mouth_pixel := Vector2i(20, 20) + (mouth.position + mouth.size / 2) * 2
	var outside := Vector2i(20, 20) + Vector2i(64, 125) * 2
	_expect(baseline.get_pixelv(Vector2i(2, 2)).a == 0.0 and changed.get_pixelv(Vector2i(2, 2)).a == 0.0, "Transparent canvas remains transparent outside the body.")
	_expect(absf(changed.get_pixelv(eye_pixel).a - baseline.get_pixelv(eye_pixel).a) < 0.01 and changed.get_pixelv(eye_pixel).a < 0.9, "Eye replacement preserves translucent original body alpha.")
	_expect(absf(changed.get_pixelv(mouth_pixel).a - baseline.get_pixelv(mouth_pixel).a) < 0.01, "Mouth replacement preserves original body alpha.")
	_expect(_rgb_distance(changed.get_pixelv(eye_pixel), baseline.get_pixelv(eye_pixel)) > 0.08, "Eye patch changes its registered eye region.")
	_expect(_rgb_distance(changed.get_pixelv(mouth_pixel), baseline.get_pixelv(mouth_pixel)) > 0.08, "Mouth patch changes its registered mouth region.")
	_expect(changed.get_pixelv(outside).is_equal_approx(baseline.get_pixelv(outside)), "Facial patches leave unrelated body pixels unchanged.")
	actor.set_eye_state("rest")
	await RenderingServer.frame_post_draw
	var mouth_only := viewport.get_texture().get_image()
	_expect(mouth_only.get_pixelv(eye_pixel).is_equal_approx(baseline.get_pixelv(eye_pixel)), "Eye rest restores underlying body while mouth remains active.")
	_expect(mouth_only.get_pixelv(mouth_pixel).is_equal_approx(changed.get_pixelv(mouth_pixel)), "Eye direction cannot reset mouth selection.")
	if not _capture_directory.is_empty():
		DirAccess.make_dir_recursive_absolute(_capture_directory)
		baseline.save_png(_capture_directory.path_join("source-frame.png"))
		changed.save_png(_capture_directory.path_join("registered-face.png"))
	actor.shutdown()
	viewport.queue_free()
	await get_tree().process_frame


func _rgb_distance(left: Color, right: Color) -> float:
	return Vector3(left.r - right.r, left.g - right.g, left.b - right.b).length()


func _settle(actor: Node2D) -> void:
	var deadline := Time.get_ticks_msec() + 10000
	while Time.get_ticks_msec() < deadline:
		actor.advance(0.0)
		if actor.snapshot().state in ["ready", "failed", "closed"]: return
		await get_tree().create_timer(0.002).timeout
	_expect(false, "Independent consumer decoding completed within deadline.")


func _expect(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)
		push_error(message)
