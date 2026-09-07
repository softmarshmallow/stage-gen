extends SceneTree

## A picture of the runner host, for a reviewer.
##
##   Godot --path godot --rendering-driver metal --disable-render-loop \
##       --audio-driver Dummy --quit-after 3000 -s res://tools/runner_capture.gd -- \
##       --run <abs run dir> --seed <int> --out <abs png> [--at <frame>]
##
## The simulation is driven directly rather than by waiting for frames: the host
## banks real time and pays out fixed steps, and a capture wants a *named* step
## rather than however many a machine happened to manage. So the loop below
## hands it exact deltas, which is the same thing a replay does and is why the
## picture is reproducible.
##
## A real display server is required, so a small window opens and is shrunk.

const FIXED_STEP := 1.0 / 60.0


func _initialize() -> void:
	var args := _args()
	var out_path := String(args.get("out", ""))
	if out_path.is_empty():
		printerr("runner capture: --out <png> is required")
		quit(2)
		return
	var at := int(args.get("at", "180"))
	DisplayServer.window_set_size(Vector2i(1280, 720))

	var scene: PackedScene = load("res://hosts/sideview_runner/main.tscn")
	if scene == null:
		printerr("runner capture: the host scene did not load")
		quit(1)
		return
	var node: Node = scene.instantiate()
	root.add_child(node)
	await process_frame

	var world: RunnerWorld = node.get("world")
	if world == null:
		printerr("runner capture: the host refused the run")
		quit(1)
		return
	while int(node.get("_frame")) < at:
		node.call("_process", FIXED_STEP)
	# One idle frame so the view's node changes reach the rendering server, then
	# a few forced draws so the frame buffer holds this step rather than the one
	# before it.
	await process_frame
	for _i in 4:
		RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	if image == null:
		printerr("runner capture: no image came back")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())
	var error := image.save_png(out_path)
	if error != OK:
		printerr("runner capture: could not write %s (error %d)" % [out_path, error])
		quit(1)
		return
	print(
		"[runner capture] frame %d  distance %.2f  score %d  %dx%d -> %s"
		% [
			int(node.get("_frame")),
			float(world.avatar["distanceColumns"]),
			int(world.score["total"]),
			image.get_width(),
			image.get_height(),
			out_path,
		]
	)
	quit(0)


func _args() -> Dictionary:
	var made := {}
	var argv := OS.get_cmdline_user_args()
	var index := 0
	while index < argv.size():
		var key := String(argv[index])
		if key.begins_with("--") and index + 1 < argv.size():
			made[key.substr(2)] = argv[index + 1]
			index += 2
			continue
		index += 1
	return made
