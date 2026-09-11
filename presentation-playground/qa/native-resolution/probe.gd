extends SceneTree

const DESIGN := Vector2(1280, 900)
var app: Control
var rows: Array[Dictionary] = []
var errors: Array[String] = []

func _initialize() -> void:
	_run.call_deferred()

func _run() -> void:
	app = load("res://main.tscn").instantiate()
	root.add_child(app)
	app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for configuration in [
		["before_2x", Window.CONTENT_SCALE_MODE_VIEWPORT, Vector2i(2560, 1800)],
		["base", Window.CONTENT_SCALE_MODE_CANVAS_ITEMS, Vector2i(1280, 900)],
		["large", Window.CONTENT_SCALE_MODE_CANVAS_ITEMS, Vector2i(1920, 1350)],
		["double", Window.CONTENT_SCALE_MODE_CANVAS_ITEMS, Vector2i(2560, 1800)],
		["wide", Window.CONTENT_SCALE_MODE_CANVAS_ITEMS, Vector2i(1920, 1080)],
	]:
		root.content_scale_mode = configuration[1]
		root.size = configuration[2]
		app.open_route("demos/dialogue")
		for index in 4:
			await process_frame
		var stage: Control = app.active_scene
		stage.set("_capture_frozen", true)
		stage.set("_entry", 1.0)
		stage.set("_natural_blink", false)
		stage.set("_dialogue_index", 3)
		stage.call("_update_interface")
		stage.queue_redraw()
		for index in 3:
			await process_frame
		RenderingServer.force_draw()
		var picture := root.get_texture().get_image()
		var transform := root.get_final_transform()
		var extent := transform.basis_xform(DESIGN)
		var row := {"case": configuration[0], "window": [root.size.x, root.size.y],
			"logical_size": [app.size.x, app.size.y],
			"image_size": [picture.get_width(), picture.get_height()],
			"texture_size": [root.get_texture().get_width(), root.get_texture().get_height()],
			"output_origin": [transform.origin.x, transform.origin.y],
			"output_extent": [extent.x, extent.y],
			"scale": [transform.x.x, transform.y.y]}
		rows.append(row)
		if not app.size.is_equal_approx(DESIGN): errors.append("Logical layout changed: " + str(configuration[0]))
		var expected := Vector2i(1280, 900) if configuration[1] == Window.CONTENT_SCALE_MODE_VIEWPORT else Vector2i(roundi(extent.x), roundi(extent.y))
		if picture.get_size() != expected: errors.append("Unexpected raster dimensions: " + str(row))
		picture.save_png("res://qa/native-resolution/" + str(configuration[0]) + ".png")
	root.size = Vector2i(2560, 1800)
	app.open_route("opening")
	await create_timer(0.7).timeout
	var video: VideoStreamPlayer = app.active_scene.get("_player")
	if video == null or video.get_video_texture().get_size() != Vector2(1920, 1080):
		errors.append("Opening source must retain its 1080p decode.")
	elif not video.size.is_equal_approx(Vector2(1280, 720)):
		errors.append("Opening logical placement changed at 2x size.")
	var point := root.get_final_transform() * Vector2(1126, 855)
	for pressed in [true, false]:
		var click := InputEventMouseButton.new()
		click.button_index = MOUSE_BUTTON_LEFT
		click.position = point
		click.global_position = point
		click.pressed = pressed
		root.push_input(click, false)
	for index in 4:
		await process_frame
	if app.current_route != "game" or app.active_scene.get("_story_id") != "arrival":
		errors.append("Scaled opening click must enter the first story beat.")
	var result := {"rows": rows, "scaled_opening_click": app.current_route == "game", "errors": errors}
	FileAccess.open("res://qa/native-resolution/probe.json", FileAccess.WRITE).store_string(JSON.stringify(result, "\t"))
	print(JSON.stringify(result))
	quit(0 if errors.is_empty() else 1)
