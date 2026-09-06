extends SceneTree

## A one-shot windowed capture of the CARD modules alone, against a real run.
##
##   Godot --path godot/oblique_survival --rendering-driver metal \
##       --resolution 160x100 --position 0,0 --audio-driver Dummy \
##       -s res://tools/capture_cards.gd -- --run <run dir> --out <png>
##
## It stands the props, the mobs and the player of the camp at the run's own
## camera framing, with the skirt decals under them and a contact shadow under
## each, and writes one PNG. Nothing here is a module: the world is a plain
## Dictionary standing in for `sim/world.gd` (the modules read it through
## `Cards.field`, which takes a Dictionary or an Object), and the ground is a
## flat plate so the cards have something to stand on. The real ground, water,
## pieces, weather and HUD belong to other builders.
##
## Capture path per maps/godot-capabilities.md section 3d: `--headless` can
## never produce a picture (`frame_post_draw` never emits and `get_image()`
## returns null), so this needs a real display server; the window is made tiny
## and moved to the corner, and `force_draw` after two idle frames is what
## actually renders.

const DEFAULT_RUN := "/Users/universe/Documents/shared/stage-gen/out/ember-hollow-v1"
const SIZE := Vector2i(1600, 900)
## How far from the camp an entity has to be to be left out of the shot.
const CAMP_RADIUS := 16.0
## Where gallery mode puts the camera target on entry (viewer :5138).
const CAMERA_TARGET := Vector3(5.0, 0.0, 5.0)


func _init() -> void:
	var args := RunArgs.from_command_line()
	var run_dir := args.run if args.run != "" else DEFAULT_RUN
	var out := args.out if args.out != "" else "/tmp/cards.png"
	var pkg := RunPackage.open(run_dir)
	if pkg == null:
		push_error("capture_cards: could not open %s" % run_dir)
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
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	# Soft-edged cards are alpha-to-coverage: without MSAA the edge collapses to
	# a hard cut at 0.5, which is the speckle the viewer went out of its way to
	# avoid. The frame owner must set this on the real viewport too.
	viewport.msaa_3d = Viewport.MSAA_4X
	root.add_child(viewport)

	var env := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.16, 0.18, 0.15)
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	env.environment = environment
	viewport.add_child(env)

	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else pkg.manifest.get("layout", {})
	var camp: Dictionary = layout.get("camp_position", {"x": 0.0, "z": 0.0})
	var target := Vector3(float(camp.get("x", 0.0)), 0.0, float(camp.get("z", 0.0)))
	var cam_spec: Dictionary = pkg.manifest.get("camera", {})
	var yaw := deg_to_rad(float(cam_spec.get("yaw_degrees", 45.0)))
	var pitch := deg_to_rad(float(cam_spec.get("pitch_degrees", 55.0)))
	var distance := float(cam_spec.get("distance_meters", 18.0))

	var camera := Camera3D.new()
	camera.fov = float(cam_spec.get("fov_degrees", 35.0))
	camera.near = 0.1
	camera.far = 600.0
	camera.position = target + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * distance
	camera.look_at_from_position(camera.position, target, Vector3.UP)
	camera.current = true
	viewport.add_child(camera)

	_ground(viewport, pkg)

	var fu := FrameUniforms.from_manifest(pkg.manifest, Vector2(SIZE))
	var world := _world(pkg, layout, target, yaw)

	# `--capture <parts>` narrows the shot to one module, which is how a layer
	# that is there but invisible is told apart from one that is not there.
	var parts := args.capture if args.capture != "" else "all"
	# `cards` / `shadows` / `decals` show that one layer alone; `none` shows the
	# bare plate; everything else shows all three.
	var solo := ["cards", "shadows", "decals"].has(parts)

	var decals := Decals.new()
	decals.visible = parts != "none" and (not solo or parts == "decals")
	viewport.add_child(decals)
	decals.setup(pkg, world, fu)

	var shadows := Shadows.new()
	shadows.visible = parts != "none" and (not solo or parts == "shadows")
	viewport.add_child(shadows)
	shadows.setup(pkg, world, fu)

	var cards := Cards.new()
	cards.visible = parts != "none" and (not solo or parts == "cards")
	viewport.add_child(cards)
	cards.setup(pkg, world, fu)

	if parts == "gallery":
		# Gallery mode: the layout is ignored and the package's own assets stand
		# in rows beside a player-height ruler.
		var gallery := Gallery.new()
		viewport.add_child(gallery)
		gallery.setup(pkg, world, fu)
		gallery.set_mode("gallery")
		for module: Node3D in [decals, shadows, cards]:
			module.set_mode("gallery")
		camera.position = CAMERA_TARGET + Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch)) * 26.0
		camera.look_at_from_position(camera.position, CAMERA_TARGET, Vector3.UP)
	if parts == "winter":
		# The season turn, without a simulation: the world says `winter` and
		# every prop state that drew one swaps to its winter picture.
		world["look"] = "winter"
	if parts == "reactions":
		# One blow to a pine and one felled tree beside it, so the shake's damped
		# rock and the trunk's toppling arc are both in the shot.
		_reactions(world, cards)

	var cam := {
		"yaw": yaw, "basis": camera.transform.basis, "position": camera.position,
		"target": target, "changed": true, "pixel_ratio": 1.0, "resolution": Vector2(SIZE),
	}
	# The frame owner's loop, in miniature: advance the clock, write the shared
	# uniforms, then update every module in the order of viewer-render.md
	# section 10 (decals, shadows and cards all sit inside step 7).
	var steps: int = args.frames if args.frames > 0 else 1
	for step in steps:
		var delta := 1.0 / 60.0
		world["time"] = float(world["time"]) + delta
		var player: Dictionary = world["player"]
		player["elapsed"] = float(player["elapsed"]) + delta
		fu.write_frame({
			"u_time": float(world["time"]), "u_night": 0.0, "u_light_intensity": 0.0,
			"u_light_pos": Vector3.ZERO, "u_light_radius": 6.0,
			"u_pool_pos": Vector3(player["x"], 0.0, player["z"]),
			"u_rain": 0.0, "u_snow": 0.0, "u_flash": 0.0,
		})
		decals.update(world, delta, cam)
		shadows.update(world, delta, cam)
		cards.update(world, delta, cam)
		cam["changed"] = false

	# Nodes added outside the main loop are not registered with the rendering
	# scenario until it has iterated; without these two, force_draw is black.
	for _i in range(3):
		await process_frame
	if DisplayServer.get_name() != "headless":
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)
	for _i in range(4):
		RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	if image == null:
		push_error("capture_cards: no image (a display server is required)")
		quit(1)
		return
	var error := image.save_png(out)
	print("[cards] %d cards, %d decal groups over %d decals, shadows %s -> %s (%s)" % [
		cards.record_count(), decals.group_count(), decals.instance_count(),
		shadows.debug_counts(), out, "ok" if error == OK else "save failed",
	])
	quit(0 if error == OK else 1)


## A blow and a felling, offered to the card module the way the frame owner
## offers a drained `world.events` entry.
func _reactions(world: Dictionary, cards: Cards) -> void:
	var struck: Dictionary = {}
	var felled: Dictionary = {}
	for entity: Dictionary in world["entities"]:
		if String(entity.get("prop_id", "")) != "pine" or String(entity.get("state", "")) != "grown":
			continue
		if struck.is_empty():
			struck = entity
		elif felled.is_empty():
			felled = entity
	if not struck.is_empty():
		cards.handle_event({
			"type": "hit", "id": struck["id"], "prop_id": "pine", "state": struck["state"],
			"verb": "chop", "kind": "chips", "x": struck["x"], "z": struck["z"],
			"away_x": 1.0, "away_z": 0.0, "last": false,
		})
	if not felled.is_empty():
		cards.handle_event({
			"type": "fell", "id": felled["id"], "prop_id": "pine", "state": felled["state"],
			"x": felled["x"], "z": felled["z"], "sign": 1.0,
		})
		# The entity underneath already shows its stump.
		felled["state"] = "stump"
		felled["dirty"] = true


## The camp's entities, in the shape `sim/world.gd` builds them, as a plain
## Dictionary world the modules can read through `Cards.field`.
func _world(pkg: RunPackage, layout: Dictionary, target: Vector3, yaw: float) -> Dictionary:
	var props: Dictionary = pkg.manifest.get("props", {})
	var actors: Dictionary = pkg.manifest.get("actors", {})
	var entities: Array = []
	for raw: Dictionary in layout.get("entities", []):
		var x := float(raw.get("x", 0.0))
		var z := float(raw.get("z", 0.0))
		if Vector2(x - target.x, z - target.z).length() > CAMP_RADIUS:
			continue
		var kind := String(raw.get("kind", ""))
		if kind == "prop":
			var prop_id := String(raw.get("prop", ""))
			if not props.has(prop_id):
				continue
			var prop: Dictionary = props[prop_id]
			var state := String(raw.get("state", ""))
			if not (prop.get("states", {}) as Dictionary).has(state):
				state = String(prop.get("baseline_state", ""))
			entities.append({
				"id": String(raw.get("id", "")), "kind": "prop", "prop_id": prop_id,
				"state": state, "baseline": state, "x": x, "z": z,
				"seed": int(raw.get("seed", 0)), "dirty": false,
			})
		elif kind == "mob":
			var actor_id := String(raw.get("actor", ""))
			if not actors.has(actor_id):
				continue
			entities.append({
				"id": String(raw.get("id", "")), "kind": "mob", "actor_id": actor_id,
				"state": "idle", "x": x, "z": z, "facing": "right", "elapsed": 0.0, "dirty": false,
			})
	# One dropped log beside the fire, so the item card and its shrinking
	# contact shadow are in the shot too.
	if (pkg.manifest.get("items", {}) as Dictionary).has("log"):
		entities.append({
			"id": "i1", "kind": "item", "item_id": "log",
			"x": target.x + 1.6, "y": 0.0, "z": target.z + 2.4, "dirty": false,
		})
	var player_id := ""
	for id: String in actors.keys():
		if String((actors[id] as Dictionary).get("role", "")) == "player":
			player_id = id
			break
	return {
		"time": 0.0, "night": 0.0, "look": "", "camera_yaw": yaw,
		"player_id": player_id,
		"player": {
			"x": target.x, "z": target.z + 1.8, "state": "idle", "elapsed": 0.0, "facing": "front",
		},
		"entities": entities,
		"weather": {"rain": 0.0, "snow": 0.0, "wet": 0.0},
		"events": [],
	}


## A flat plate under the cards. Not the ground module: one tiled plate at the
## base biome's own level, only so the shot has a floor and the skirt decals
## have something to sit on.
func _ground(viewport: SubViewport, pkg: RunPackage) -> void:
	var ground: Dictionary = pkg.manifest.get("ground", {})
	var biomes: Dictionary = ground.get("biomes", {})
	var base: Variant = biomes.get(String(ground.get("base_biome", "")))
	if not (base is Dictionary):
		return
	var shader := Shader.new()
	shader.code = """
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque;
uniform sampler2D plate : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float texel_meters = 4.0;
uniform float level = 1.0;
varying vec3 world_pos;
void vertex() { world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() { ALBEDO = texture(plate, world_pos.xz / texel_meters).rgb * level; }
"""
	var material := ShaderMaterial.new()
	material.shader = shader
	material.set_shader_parameter("plate", pkg.texture(String((base as Dictionary).get("texture", ""))))
	material.set_shader_parameter("texel_meters", float((base as Dictionary).get("texel_meters", 4.0)))
	material.set_shader_parameter("level", Decals.ground_level(pkg.manifest))
	var plane := PlaneMesh.new()
	plane.size = Vector2(120.0, 120.0)
	plane.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.mesh = plane
	viewport.add_child(node)
