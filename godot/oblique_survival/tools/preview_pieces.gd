extends SceneTree

## A windowed capture of the pieces alone, for builder V3's own proof.
##
##   Godot --path godot/oblique_survival --resolution 160x100 --position 0,0 \
##       --disable-render-loop --audio-driver Dummy -s res://tools/preview_pieces.gd \
##       -- --run <run dir> --out <png> [--yaw 45] [--night 0] [--look ""]
##
## It builds `view/pieces.gd` over the verdict framing (camp at the origin, the
## manifest's camera block) and nothing else, so what lands in the PNG is this
## module's work and no one else's. The flat plate under it is a stand-in for
## the ground module, not a port of it: a dull unshaded quad so the pieces have
## something to sit on.
##
## This is a builder's tool, not the host's capture harness.

const OUT_DEFAULT := "/tmp/pieces.png"
const SIZE := Vector2i(1600, 900)

func _init() -> void:
	var args := RunArgs.parse(OS.get_cmdline_user_args())
	var extra := _extra(OS.get_cmdline_user_args())
	var out: String = args.out if args.out != "" else OUT_DEFAULT
	var pkg := RunPackage.open(args.run)
	if pkg == null:
		push_error("preview: no run at %s" % args.run)
		quit(1)
		return

	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_position(Vector2i(0, 0))
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)

	var manifest: Dictionary = pkg.manifest
	var layout: Dictionary = pkg.layout
	var camp: Dictionary = layout.get("camp_position", {"x": 0.0, "z": 0.0})
	var target := Vector3(float(camp.get("x", 0.0)), 0.0, float(camp.get("z", 0.0)))
	var camera_spec: Dictionary = manifest.get("camera", {})
	var yaw := deg_to_rad(float(extra.get("yaw", camera_spec.get("yaw_degrees", 45.0))))
	var pitch := deg_to_rad(float(camera_spec.get("pitch_degrees", 55.0)))
	var distance := float(camera_spec.get("distance_meters", 18.0))
	var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance

	var viewport := SubViewport.new()
	viewport.size = SIZE
	viewport.own_world_3d = true
	viewport.transparent_bg = false
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)

	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.16, 0.17, 0.15)
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	var world_environment := WorldEnvironment.new()
	world_environment.environment = environment
	viewport.add_child(world_environment)

	var camera := Camera3D.new()
	camera.fov = float(camera_spec.get("fov_degrees", 35.0))
	camera.near = 0.5
	camera.far = 300.0
	viewport.add_child(camera)
	camera.transform = Transform3D(Basis(), target + offset).looking_at(target, Vector3.UP)

	# The stand-in plate: the ground module's job, drawn here only so the pieces
	# are not floating in the void.
	var plate := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(260.0, 260.0)
	plate.mesh = plane
	var plate_material := StandardMaterial3D.new()
	plate_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	plate_material.albedo_color = Color(0.19, 0.20, 0.15)
	plate.material_override = plate_material
	viewport.add_child(plate)

	var fu := FrameUniforms.from_manifest(manifest, Vector2(SIZE))
	var world := _world_stub(pkg, yaw, String(extra.get("look", "")))

	var pieces := Pieces.new()
	viewport.add_child(pieces)
	pieces.setup(pkg, world, fu)

	var night := float(extra.get("night", 0.0))
	fu.write_frame({
		"u_time": 0.0,
		"u_night": night,
		"u_light_intensity": 1.0 if night > 0.0 else 0.0,
		"u_light_pos": target,
		"u_light_radius": 6.0,
		"u_pool_pos": target,
		"u_rain": 0.0,
		"u_snow": 1.0 if String(extra.get("look", "")) != "" else 0.0,
		"u_flash": 0.0,
	})

	var cam := {
		"yaw": yaw,
		"basis": camera.transform.basis,
		"position": camera.transform.origin,
		"target": target,
		"changed": true,
		"pixel_ratio": 1.0,
		"resolution": Vector2(SIZE),
	}
	pieces.update(world, 1.0 / 60.0, cam)
	world["time"] = 0.6
	pieces.update(world, 0.6, cam)

	for i in 2:
		await process_frame
	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
	for i in 3:
		RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	var error := image.save_png(out)
	print("preview: %s %dx%d (%s), forage %d" % [
		out, image.get_width(), image.get_height(),
		"ok" if error == OK else "save failed", pieces.forage.count])
	print("preview: centre pixel %s" % image.get_pixel(SIZE.x / 2, SIZE.y / 2))
	quit(0 if error == OK else 1)

## The camera yaw, the look, and the forage flags: everything these modules read.
func _world_stub(pkg, yaw: float, look: String) -> Dictionary:
	var entities: Array = []
	var cells: Array = pkg.manifest.get("ground", {}).get("forage", {}).get("cells", [])
	var forage: Array = pkg.layout.get("forage", [])
	for index in forage.size():
		var cell: Dictionary = cells[int(forage[index].get("cell", 0)) % maxi(1, cells.size())]
		if String(cell.get("item_id", "")) == "":
			continue
		entities.append({"kind": "forage", "index": index, "picked": false, "hidden": false})
	return {
		"camera_yaw": yaw, "look": look, "time": 0.0,
		"manifest": pkg.manifest, "entities": entities,
	}

## The two knobs `RunArgs` does not carry, so the preview stays a builder's tool.
func _extra(argv: PackedStringArray) -> Dictionary:
	var extra: Dictionary = {}
	for index in argv.size():
		var token := argv[index]
		var value := ""
		var equals := token.find("=")
		if equals > 0:
			value = token.substr(equals + 1)
			token = token.substr(0, equals)
		elif index + 1 < argv.size():
			value = argv[index + 1]
		match token:
			"--yaw":
				extra["yaw"] = float(value)
			"--night":
				extra["night"] = float(value)
			"--look":
				extra["look"] = value
	return extra
