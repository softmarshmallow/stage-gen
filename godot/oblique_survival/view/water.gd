extends Node3D

## The water, three worlds wide so the square is never seen, sunk below the
## ground so the coast's discard reveals it — and the cliff face the slab
## stands on, which is the same plane's other branch.
##
## A port of the water half of `buildGround` (viewer/index.html:3396-3441) and
## `updateCliff` (:3451-3459). The shader is `view/shaders/water.gdshader`.

const Plates := preload("res://view/plates.gd")
const ProcNoise := preload("res://view/proc_noise.gd")

var material: ShaderMaterial = null
var mesh_instance: MeshInstance3D = null
## `ground.water.depth_meters` — the slab's thickness, and the plane's depth.
var water_depth: float = 0.45
var size_meters: float = 256.0

var _ice: float = 0.0

func setup(pkg, world, fu) -> void:
	var manifest: Dictionary = pkg.manifest
	var ground: Dictionary = manifest.get("ground", {})
	var splat: Dictionary = ground.get("splat", {}) if ground.get("splat") is Dictionary else {}
	var blend: Dictionary = splat.get("blend", {}) if splat.get("blend") is Dictionary else {}
	var level: Dictionary = blend.get("level", {}) if blend.get("level") is Dictionary else {}
	size_meters = float(ground.get("size_meters", 256.0))
	var water: Variant = ground.get("water")
	var water_block: Dictionary = water if water is Dictionary else {}
	var weather: Dictionary = manifest.get("weather", {}) if manifest.get("weather") is Dictionary else {}
	var ice: Variant = null
	if weather.get("snow") is Dictionary and (weather["snow"] as Dictionary).get("ice") is Dictionary:
		var block: Dictionary = (weather["snow"] as Dictionary)["ice"]
		if block.get("texture") != null:
			ice = block
	var ice_block: Dictionary = ice if ice is Dictionary else {}
	var noise := ProcNoise.texture()

	material = ShaderMaterial.new()
	material.shader = load("res://view/shaders/water.gdshader")
	var has_water: bool = water is Dictionary and water_block.get("texture") != null
	material.set_shader_parameter("u_water", pkg.texture(String(water_block["texture"])) if has_water else noise)
	material.set_shader_parameter("u_has_water", 1.0 if has_water else 0.0)
	material.set_shader_parameter("u_water_colour", _colour(water_block.get("colour"), Vector3(0.13, 0.2, 0.22)))
	material.set_shader_parameter("u_water_tile_meters", float(water_block.get("texel_meters", 1.0)) if water is Dictionary else 1.0)
	material.set_shader_parameter("u_water_level", Plates.level_gain(water, level))
	if splat.has("image"):
		material.set_shader_parameter("u_splat", pkg.texture(String(splat["image"]), false))
	material.set_shader_parameter("u_world_origin", Vector2(-size_meters * 0.5, -size_meters * 0.5))
	material.set_shader_parameter("u_world_extent", Vector2(size_meters, size_meters))
	material.set_shader_parameter("u_shore_shadow_meters", _number(blend, "shore_shadow_meters", 1.6))
	material.set_shader_parameter("u_noise", noise)
	material.set_shader_parameter("u_shore_noise_tile_meters", _number(blend, "shore_noise_tile_meters", 4.0))
	material.set_shader_parameter("u_shore_noise_strength", _number(blend, "shore_noise_strength", 0.5))
	material.set_shader_parameter("u_cliff_offset", Vector2.ZERO)
	material.set_shader_parameter("u_cliff_colour", _colour(water_block.get("cliff_colour"), Vector3(0.16, 0.12, 0.09)))
	material.set_shader_parameter("u_cliff_on", 1.0)
	material.set_shader_parameter("u_wave_ink", _number(blend, "wave_ink", 0.0))
	material.set_shader_parameter("u_wave_meters", _number(blend, "wave_meters", 1.6))
	var has_ice: bool = ice is Dictionary
	material.set_shader_parameter("u_ice_tex", pkg.texture(String(ice_block["texture"])) if has_ice else noise)
	material.set_shader_parameter("u_has_ice", 1.0 if has_ice else 0.0)
	material.set_shader_parameter("u_ice", 0.0)
	material.set_shader_parameter("u_ice_tile_meters", float(ice_block.get("texel_meters", 1.0)) if has_ice else 1.0)
	material.set_shader_parameter("u_ice_level", Plates.level_gain(ice, level))

	if fu != null:
		fu.register(material)

	water_depth = float(water_block.get("depth_meters", 0.45)) if water is Dictionary else 0.45
	var plane := PlaneMesh.new()
	plane.size = Vector2(size_meters * 3.0, size_meters * 3.0)
	plane.material = material
	mesh_instance = MeshInstance3D.new()
	mesh_instance.name = "WaterPlane"
	mesh_instance.mesh = plane
	mesh_instance.position.y = -water_depth
	mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mesh_instance)

func update(world, _delta: float, cam: Dictionary) -> void:
	if material == null:
		return
	update_cliff(cam)
	if world != null:
		var weather: Variant = world.get("weather")
		if weather is Dictionary:
			set_ice(float((weather as Dictionary).get("snow", 0.0)))

## The cliff walk: the ray's horizontal run over the slab's depth, toward the
## camera. Recomputed every frame because it follows the camera, not the world.
func update_cliff(cam: Dictionary) -> void:
	if material == null:
		return
	var target: Vector3 = cam.get("target", Vector3.ZERO)
	var position: Vector3 = cam.get("position", Vector3.ZERO)
	var dx := target.x - position.x
	var dz := target.z - position.z
	var dy := target.y - position.y
	var horizontal := sqrt(dx * dx + dz * dz)
	if horizontal == 0.0:
		horizontal = 1.0
	var pitch := atan2(-dy, horizontal)
	var span := water_depth / maxf(tan(pitch), 0.05)
	material.set_shader_parameter("u_cliff_offset", Vector2((-dx / horizontal) * span, (-dz / horizontal) * span))

## The freeze, `world.weather.snow` (index.html:5532).
func set_ice(value: float) -> void:
	if material == null or is_equal_approx(value, _ice):
		return
	_ice = value
	material.set_shader_parameter("u_ice", value)

func set_water_depth(depth: float) -> void:
	water_depth = maxf(0.05, depth)
	if mesh_instance != null:
		mesh_instance.position.y = -water_depth

func set_uniform(name: String, value: Variant) -> void:
	if material != null:
		material.set_shader_parameter(name, value)

static func _number(block: Dictionary, key: String, fallback: float) -> float:
	var value: Variant = block.get(key)
	if value is float or value is int:
		return float(value)
	return fallback

## `new THREE.Color(r, g, b)` takes its numbers as linear light, so these
## arrive as plain vectors and not as `source_color` uniforms.
static func _colour(value: Variant, fallback: Vector3) -> Vector3:
	if value is Array and (value as Array).size() >= 3:
		var list: Array = value
		return Vector3(float(list[0]), float(list[1]), float(list[2]))
	return fallback
