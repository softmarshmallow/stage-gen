extends SceneTree

## Command Link-owned integration assertions, formerly run from Afterlight's
## combined-project harness. Routes, prepared art and renderer belong here.
var _app: Control
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)


func _open(route: String) -> Control:
	if not _app.open_route(route):
		_expect(false, "Route must open: " + route)
		return null
	await _settle()
	return _app.active_scene


func _settle() -> void:
	for frame in 3:
		await process_frame
		if _app != null and _app.active_scene != null: _app.active_scene.set_process(false)


func _freeze_route(node: Node) -> void:
	if node.has_method("_update_character_layers"):
		node.set_process(false)
		node.ready.connect(node.set_process.bind(false), CONNECT_ONE_SHOT)


const DESIGN_SIZE := Vector2(1280, 900)
const DIRECTORY := "res://tests/one-shot-manpu"
var _capture_enabled := false
var _capture_count := 0


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-one-shot")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("One-shot captures require a native renderer.")
		quit(2)
		return
	root.size = Vector2i(DESIGN_SIZE)
	node_added.connect(_freeze_route)
	_app = load("res://main.tscn").instantiate()
	root.add_child(_app)
	await _settle()
	await _check_tactical_renderer()
	_app.queue_free()
	await process_frame
	for issue: String in _errors: printerr("FAIL Command Link one-shot: " + issue)
	if _errors.is_empty(): print("PASS Command Link one-shot: attached drift, frozen render, overlapping events and departing-owner cancellation")
	quit(0 if _errors.is_empty() else 1)


func _check_tactical_renderer() -> void:
	var stage := await _open("game:lab/demos/manpu")
	if stage == null or not _healthy(stage): return
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

func _healthy(scene: Control) -> bool:
	var errors: Array = scene.get("_load_errors") if scene.get("_load_errors") != null else []
	if not errors.is_empty(): _errors.append("Scene validation: " + str(errors))
	return errors.is_empty()

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
