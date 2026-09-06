extends SceneTree
## A windowed capture of the weather and fx modules alone, over a plain tiled
## ground, so they can be looked at before the rest of the view exists.
##
##   Godot --path godot/oblique_survival --rendering-driver metal \
##     --resolution 160x100 --position 0,0 --quit-after 240 \
##     -s res://tools/weather_probe.gd -- --run <run dir> --out <png>
##
## It forces the verdict framing (camp, yaw 45, pitch 55, fov 35, 18 m) under a
## storm at noon: rain 1, wet 1, the campfire lit, a bolt a third of a second
## old, and a few bursts of dust. Scaffolding for a builder, not the host: the
## real frame owner is `main.gd`.

const RUN_DEFAULT := "/Users/universe/Documents/shared/stage-gen/out/ember-hollow-v1"
const SIZE := Vector2i(1600, 900)
const FRAMES := 150
const STEP := 1.0 / 60.0

var _modules: Array = []

func _init() -> void:
	var args := _args()
	var run_dir := str(args.get("run", RUN_DEFAULT))
	var out_path := str(args.get("out", "/tmp/weather.png"))
	var pkg: RunPackage = RunPackage.open(run_dir)
	if pkg == null:
		push_error("weather probe: could not open %s" % run_dir)
		quit(1)
		return

	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_size(Vector2i(160, 100))
		DisplayServer.window_set_position(Vector2i(0, 0))
		DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)

	var viewport := SubViewport.new()
	viewport.size = SIZE
	viewport.own_world_3d = true
	viewport.transparent_bg = false
	viewport.msaa_3d = Viewport.MSAA_4X
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)

	var environment := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.42, 0.47, 0.52)
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	environment.environment = env
	viewport.add_child(environment)

	# The verdict camera: manifest.camera against the camp.
	var manifest: Dictionary = pkg.manifest
	var camera_spec: Dictionary = manifest.get("camera", {})
	var camp: Dictionary = pkg.layout.get("camp_position", {"x": 0.0, "z": 0.0})
	var target := Vector3(float(camp.get("x", 0.0)), 0.0, float(camp.get("z", 0.0)))
	var yaw := deg_to_rad(float(camera_spec.get("yaw_degrees", 45.0)))
	var pitch := deg_to_rad(float(camera_spec.get("pitch_degrees", 55.0)))
	var distance := float(camera_spec.get("distance_meters", 18.0))
	var position := target + Vector3(
		sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	var camera := Camera3D.new()
	camera.fov = float(camera_spec.get("fov_degrees", 35.0))
	camera.near = 0.5
	camera.far = 300.0
	# Built by hand: nothing added in `_init` is inside the tree yet, so
	# `look_at` cannot be used. Columns are camera right / up / back.
	var back := (position - target).normalized()
	var right := Vector3.UP.cross(back).normalized()
	var basis := Basis(right, back.cross(right), back)
	camera.transform = Transform3D(basis, position)
	viewport.add_child(camera)

	var world: World = World.create(pkg, int(pkg.layout.get("seed", 7)), {
		"time": "noon", "weather": "storm", "season": "auto",
	})
	if world == null:
		push_error("weather probe: the world would not build")
		quit(1)
		return
	# A storm at noon (or a snowfall with `--weather snow`), held: the systems
	# are not stepped here, so the weather is written straight in and the fire
	# lit the way verdict mode does.
	var snowing := str(args.get("weather", "storm")) == "snow"
	world.night = 0.0
	world.weather["rain"] = 0.0 if snowing else 1.0
	world.weather["target"] = world.weather["rain"]
	world.weather["wet"] = 0.0 if snowing else 1.0
	world.weather["snow"] = 1.0 if snowing else 0.0
	world.light["on"] = true
	for entity: Dictionary in world.entities:
		if str(entity.get("prop_id", "")) == "campfire":
			entity["state"] = "lit"
			world.light["x"] = float(entity["x"])
			world.light["z"] = float(entity["z"])
			break

	var fu: FrameUniforms = FrameUniforms.from_manifest(manifest, Vector2(SIZE))
	viewport.add_child(_ground(pkg, fu))
	var host := Node3D.new()
	host.name = "Weather"
	viewport.add_child(host)
	var weather := WeatherView.new()
	var splashes := Splashes.new()
	var strikes := Strikes.new()
	var fire := Fire.new()
	var puffs := Puffs.new()
	_modules = [weather, splashes, strikes, fire, puffs]
	for module: Node3D in _modules:
		host.add_child(module)
		module.setup(pkg, world, fu)

	var cam := {
		"yaw": yaw, "basis": basis, "position": position, "target": target,
		"changed": true, "pixel_ratio": 1.0, "resolution": Vector2(SIZE),
	}
	for frame in range(FRAMES):
		world.time += STEP
		fu.write_frame({
			"u_time": world.time,
			"u_night": world.night,
			"u_light_intensity": 1.0 if world.light["on"] else 0.0,
			"u_light_pos": Vector3(float(world.light["x"]), 0.0, float(world.light["z"])),
			"u_light_radius": float(world.light["radius"]),
			"u_pool_pos": Vector3(world.player.x, 0.0, world.player.z),
			"u_rain": float(world.weather["rain"]),
			"u_snow": float(world.weather["snow"]),
			"u_flash": weather.flash(world) * WeatherView.FLASH_GAIN,
		})
		for module: Node3D in _modules:
			module.update(world, STEP, cam)
		cam["changed"] = false
		# A blow every third of a second, so the dust reads; a bolt near the end,
		# still on its envelope when the shutter opens.
		if frame % 20 == 10:
			_offer({
				"type": "hit", "kind": "chips", "x": target.x + 1.2, "z": target.z - 0.6,
				"away_x": 0.7, "away_z": 0.7, "verb": "chop",
			})
		if frame == FRAMES - 18 and not snowing:
			_offer({"type": "strike", "x": target.x - 2.0, "z": target.z + 5.0, "cell": 1, "distance": 6.0})

	for _i in range(2):
		await process_frame
	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
	for _i in range(3):
		RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	var error := image.save_png(out_path)
	print("weather probe: %s (%dx%d, err %d)" % [out_path, image.get_width(), image.get_height(), error])
	quit(0 if error == OK else 1)

func _offer(event: Dictionary) -> void:
	for module: Node3D in _modules:
		if module.has_method("handle_event"):
			module.handle_event(event)

## A plain tiled ground, levelled the way the ground shader levels its base
## plate, purely so the weather has something to fall on.
func _ground(pkg, fu) -> MeshInstance3D:
	var ground: Dictionary = pkg.manifest.get("ground", {})
	var biomes: Dictionary = ground.get("biomes", {})
	var base: Dictionary = biomes.get(str(ground.get("base_biome", "")), {})
	var shader := Shader.new()
	shader.code = """
shader_type spatial;
render_mode unshaded, cull_back, depth_draw_never, shadows_disabled, fog_disabled;
#include "res://view/shaders/night.gdshaderinc"
uniform sampler2D plate : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float tile = 4.0;
uniform float level = 1.0;
varying vec3 v_world;
void vertex() { v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() {
	vec3 colour = texture(plate, v_world.xz / tile).rgb * level;
	ALBEDO = apply_night(colour, v_world, FRAGCOORD.xy);
}
"""
	var material := ShaderMaterial.new()
	material.shader = shader
	material.set_shader_parameter("plate", pkg.texture(str(base.get("texture", ""))))
	material.set_shader_parameter("tile", float(base.get("texel_meters", 4.0)))
	material.set_shader_parameter("level", WeatherView._decal_gain(pkg.manifest) / 0.62)
	fu.register(material)
	var plane := PlaneMesh.new()
	plane.size = Vector2(160.0, 160.0)
	plane.material = material
	var mesh := MeshInstance3D.new()
	mesh.name = "ProbeGround"
	mesh.mesh = plane
	return mesh

func _args() -> Dictionary:
	var out: Dictionary = {}
	var argv := OS.get_cmdline_user_args()
	var index := 0
	while index < argv.size():
		var token := str(argv[index])
		if token.begins_with("--") and index + 1 < argv.size():
			out[token.substr(2)] = argv[index + 1]
			index += 2
		else:
			index += 1
	return out
