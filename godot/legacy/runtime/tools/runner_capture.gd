extends SceneTree

## Pictures of the runner host: one named step, or the whole gate sheet.
##
##   Godot --path godot/legacy/runtime --rendering-driver metal --disable-render-loop \
##       --audio-driver Dummy --quit-after 30000 -s res://tools/runner_capture.gd -- \
##       --run <abs run dir> --seed <int> --out <abs png> [--at <frame>]
##
##   ... --out <abs directory> --shots all
##
## The simulation is driven directly rather than by waiting for frames: the host
## banks real time and pays out fixed steps, and a capture wants a *named* step
## rather than however many a machine happened to manage. So the loop below
## hands it exact deltas, which is the same thing a replay does and is why the
## picture is reproducible.
##
## A real display server is required, so a small window opens and is shrunk.
##
## The sheet's four steps are not arbitrary. Each one is the frame at which a
## defect this host shipped would be visible, and `tools/runner_shots_check.py`
## measures exactly that:
##
##   boot   the moment, over the world it stopped
##   run    the graded bands, the sized canopy, a turning coin, dust, a shadow
##   fight  the boss, its shots, its bar, and a body inside its immunity window
##   death  the card
##
## The background is painted a sentinel magenta first, so a region nothing drew
## is unmistakable to the checker and to a reviewer both. The bare engine grey it
## replaces was mistaken for scenery for two hundred pixels down the right of
## every frame.

const FIXED_STEP := 1.0 / 60.0
const SHOT_SIZE := Vector2i(1280, 720)
## Nothing in this package is anywhere near it, which is the point.
const UNPAINTED := Color(1.0, 0.0, 1.0, 1.0)

## The gate sheet: a name, and the simulation frame it is taken at.
const SHOTS := [
	["boot", 70],
	["run", 205],
	["fight", 1455],
	["death", 1620],
]


func _initialize() -> void:
	var args := _args()
	var out_path := String(args.get("out", ""))
	if out_path.is_empty():
		printerr("runner capture: --out is required (a png, or a directory with --shots all)")
		quit(2)
		return
	var sheet := String(args.get("shots", "")) == "all"
	DisplayServer.window_set_size(SHOT_SIZE)

	var scene: PackedScene = load("res://hosts/sideview_runner/main.tscn")
	if scene == null:
		printerr("runner capture: the host scene did not load")
		quit(1)
		return
	var node: Node = scene.instantiate()
	root.add_child(node)
	# A region nothing draws must look like nothing drew it.
	RenderingServer.set_default_clear_color(UNPAINTED)
	await process_frame

	var world: RunnerWorld = node.get("world")
	if world == null:
		printerr("runner capture: the host refused the run")
		quit(1)
		return

	var wanted: Array = SHOTS if sheet else [["", int(args.get("at", "180"))]]
	for entry: Variant in wanted:
		var shot: Array = entry
		var at := int(shot[1])
		while int(node.get("_frame")) < at:
			node.call("_process", FIXED_STEP)
		var target := out_path
		if sheet:
			target = out_path.path_join("%s.png" % shot[0])
		if not await _write(node, world, String(shot[0]), target):
			quit(1)
			return
	quit(0)


func _write(node: Node, world: RunnerWorld, name: String, target: String) -> bool:
	# One idle frame so the view's node changes reach the rendering server, then
	# a few forced draws so the frame buffer holds this step rather than the one
	# before it.
	await process_frame
	for _i in 4:
		RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	if image == null:
		printerr("runner capture: no image came back")
		return false
	DirAccess.make_dir_recursive_absolute(target.get_base_dir())
	var error := image.save_png(target)
	if error != OK:
		printerr("runner capture: could not write %s (error %d)" % [target, error])
		return false
	print(
		"[runner capture] %s frame %d  distance %.2f  score %d  %dx%d -> %s"
		% [
			name if name != "" else "shot",
			int(node.get("_frame")),
			float(world.avatar["distanceColumns"]),
			int(world.score["total"]),
			image.get_width(),
			image.get_height(),
			target,
		]
	)
	return true


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
