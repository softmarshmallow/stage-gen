extends SceneTree

## One picture of the platformer host, for a person to look at.
##
##   Godot --path godot --rendering-driver metal --disable-render-loop \
##       --audio-driver Dummy -s res://tools/platformer_shot.gd -- \
##       --run <abs run dir> --out <abs png> [--at <frame>] [--hold right,run]
##
## Not a gate and not a sheet. Step 9's picture evidence is the person playing
## it; this exists so that a build can be shown to draw *something* before it is
## handed over, which is a different and much smaller claim.

const SHOT_SIZE := Vector2i(1280, 720)
const STEP := 1.0 / 30.0
const UNPAINTED := Color(0.0, 0.0, 0.0, 0.0)


func _initialize() -> void:
	var args := _args()
	var out_path := String(args.get("out", ""))
	if out_path.is_empty():
		printerr("platformer shot: --out is required")
		quit(2)
		return
	DisplayServer.window_set_size(SHOT_SIZE)
	var scene: PackedScene = load("res://hosts/sideview_platformer/main.tscn")
	var node: Node = scene.instantiate()
	root.add_child(node)
	RenderingServer.set_default_clear_color(UNPAINTED)
	await process_frame

	var world = node.get("world")
	if world == null:
		printerr("platformer shot: the host refused the run")
		quit(1)
		return
	# Open on a named map rather than walking to it. A capture that had to play
	# its way across a village to photograph a road spends four hundred frames of
	# forced draws to answer a question about the road.
	if args.has("map"):
		var wanted := String(args["map"])
		var spawn = PlatformerMaps.spawn_position(world.package, _spawn_on(world, wanted))
		if not spawn.is_empty():
			world.open_on(String(spawn["mapId"]))
			PlatformerMapEntrySystem.place(world, float(spawn["x"]), float(spawn["y"]))
			world.camera = PlatformerCameraSystem.snapped(
				float(world.player["x"]),
				PlatformerCameraSystem.bounds_of(world),
				float(world.player["y"])
			)
	if args.has("at_x"):
		world.player["x"] = float(args["at_x"])
		world.camera = PlatformerCameraSystem.snapped(
			float(world.player["x"]),
			PlatformerCameraSystem.bounds_of(world),
			float(world.player["y"])
		)
	var held := PackedStringArray()
	if args.has("hold"):
		held = String(args["hold"]).split(",")
	var at := int(args.get("at", "60"))
	while int(node.get("_frame")) < at:
		if not held.is_empty():
			node.set("_forced_intent", held)
		node.call("_process", STEP)
	await process_frame
	for _i in 4:
		RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	if image == null:
		printerr("platformer shot: no image came back")
		quit(1)
		return
	DirAccess.make_dir_recursive_absolute(out_path.get_base_dir())
	image.save_png(out_path)
	print(
		"[platformer shot] frame %d  map %s  x %.1f  hp %d  mobs %d -> %s"
		% [
			int(node.get("_frame")),
			String(world.map_id),
			float(world.player["x"]),
			int(world.player["hp"]),
			(world.mobs as Array).size(),
			out_path,
		]
	)
	quit(0)


## The spawn a named map is entered at.
func _spawn_on(world, map_id: String) -> String:
	var spawns: Dictionary = world.package["spawns"]
	for key: Variant in spawns.keys():
		var spawn: Dictionary = spawns[key]
		if str(spawn["mapId"]) == map_id:
			return str(key)
	return str(world.package["entrySpawnId"])


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
