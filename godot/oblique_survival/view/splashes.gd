class_name Splashes
extends Node3D
## Drops landing: flat ground quads spawned across the visible ground patch at
## the authored rate times the rain, each living out its whole life in the
## shader. Ported from `buildSplashes` / `updateSplashes` (index.html
## :4075-4162) with `view/shaders/splash.gdshader`.

const CAPACITY := 720
const SHADER_PATH := "res://view/shaders/splash.gdshader"
## `DECAL_Y + 0.01` — the top of the ground stack (index.html :180, :4152).
const SPLASH_Y := 0.024
## `ORDER.fx`, above the decals and the cards.
const RENDER_PRIORITY := 4
## Rings most often, a bead least: the author's four looks, weighted here.
const WEIGHTS: Array[float] = [0.5, 0.25, 0.15, 0.1]
## The viewer never spawns more than sixty in one frame.
const MAX_PER_FRAME := 60

var spec: Dictionary = {}
var _instance: MultiMeshInstance3D = null
var _multimesh: MultiMesh = null
var _material: ShaderMaterial = null
var _cells: Array = []
var _cursor: int = 0
var _carry: float = 0.0
var _size: float = 0.5
var _fov: float = 35.0
var _rng := RandomNumberGenerator.new()

func setup(pkg, world, fu) -> void:
	var weather: Dictionary = pkg.manifest.get("weather", {}) if pkg.manifest.get("weather") is Dictionary else {}
	var rain: Variant = weather.get("rain")
	if not (rain is Dictionary):
		return
	var ground: Variant = (rain as Dictionary).get("ground")
	if not (ground is Dictionary):
		return
	spec = ground
	_cells = spec.get("cells", []) if spec.get("cells") is Array else []
	if _cells.is_empty():
		spec = {}
		return
	var texture: Texture2D = pkg.texture(str(spec.get("atlas", "")))
	if texture == null:
		spec = {}
		return
	var camera: Dictionary = pkg.manifest.get("camera", {}) if pkg.manifest.get("camera") is Dictionary else {}
	_fov = float(camera.get("fov_degrees", 35.0))
	_size = float(spec.get("height_meters", 0.27)) * 1.8
	_rng.seed = int(pkg.layout.get("seed", 0)) * 6151 + 29

	_material = ShaderMaterial.new()
	_material.shader = load(SHADER_PATH)
	_material.render_priority = RENDER_PRIORITY
	_material.set_shader_parameter("u_map", texture)
	var width := float(spec.get("width_px", 1024))
	var height := float(spec.get("height_px", 1024))
	for index in range(4):
		var window := Vector4(0.0, 0.0, 1.0, 1.0)
		if index < _cells.size():
			var cell: Dictionary = _cells[index]
			window = Vector4(
				float(cell.get("x", 0)) / width, float(cell.get("y", 0)) / height,
				float(cell.get("w", width)) / width, float(cell.get("h", height)) / height)
		_material.set_shader_parameter("u_cell_%d" % index, window)
	if fu != null:
		fu.register(_material)

	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	quad.material = _material
	_multimesh = MultiMesh.new()
	_multimesh.transform_format = MultiMesh.TRANSFORM_3D
	_multimesh.use_custom_data = true
	_multimesh.mesh = quad
	_multimesh.instance_count = CAPACITY
	for slot in range(CAPACITY):
		_multimesh.set_instance_transform(slot, Transform3D(Basis().scaled(Vector3.ZERO), Vector3.ZERO))
		_multimesh.set_instance_custom_data(slot, Color(-999.0, 1.0, 0.0, 0.0))
	_instance = MultiMeshInstance3D.new()
	_instance.name = "Splashes"
	_instance.multimesh = _multimesh
	_instance.custom_aabb = AABB(Vector3(-4096.0, -4096.0, -4096.0), Vector3(8192.0, 8192.0, 8192.0))
	add_child(_instance)

func update(world, delta: float, cam: Dictionary) -> void:
	update_splashes(world, delta, cam)

## Drops land across the visible ground at the authored rate times the rain.
func update_splashes(world, dt: float, cam: Dictionary) -> void:
	if _multimesh == null:
		return
	var weather: Dictionary = world.weather
	var rain := float(weather.get("rain", 0.0))
	if rain <= 0.01:
		return
	var target: Vector3 = cam.get("target", Vector3.ZERO)
	var position: Vector3 = cam.get("position", Vector3.ZERO)
	var resolution: Vector2 = cam.get("resolution", Vector2(1600.0, 900.0))
	var aspect := resolution.x / maxf(resolution.y, 1.0)
	var v_fov := deg_to_rad(_fov)
	var distance := position.distance_to(target)
	if distance <= 0.0:
		distance = 18.0
	var width := 2.0 * tan(v_fov / 2.0) * distance * aspect * 1.15
	var depth := (width / maxf(aspect, 0.0001)) * 1.35
	if not is_finite(width * depth) or not is_finite(_carry):
		_carry = 0.0
		return
	_carry += float(spec.get("rate_per_100_sqm_per_second", 0.0)) * rain * ((width * depth) / 100.0) * dt
	var count := int(floor(_carry))
	_carry -= float(count)
	if count <= 0:
		return
	var yaw := float(cam.get("yaw", 0.0))
	# The world direction along the screen's right edge, and the one that runs
	# up the screen (the camera's own offset, laid flat and reversed).
	var right := Vector3(cos(yaw), 0.0, -sin(yaw))
	var offset := position - target
	var up_length := sqrt(offset.x * offset.x + offset.z * offset.z)
	if up_length <= 0.0:
		up_length = 1.0
	var up := Vector3(-offset.x / up_length, 0.0, -offset.z / up_length)
	var width_px := float(spec.get("width_px", 1024))
	var height_px := float(spec.get("height_px", 1024))
	for _n in range(mini(count, MAX_PER_FRAME)):
		var slot := _cursor % CAPACITY
		_cursor += 1
		var u := _rng.randf() - 0.5
		var v := _rng.randf() - 0.5
		var x := target.x + right.x * u * width + up.x * v * depth
		var z := target.z + right.z * u * width + up.z * v * depth
		var pick := _rng.randf()
		var index := 0
		while index < _cells.size() - 1 and index < WEIGHTS.size() and pick > WEIGHTS[index]:
			pick -= WEIGHTS[index]
			index += 1
		var life := 0.35 + _rng.randf() * 0.3
		var size := _size * (0.7 + _rng.randf() * 0.6)
		# A ground piece: flat, its lower edge to the camera, like the litter.
		var basis := Basis(Vector3.RIGHT, -PI / 2.0) \
			* Basis(Vector3.BACK, yaw + (_rng.randf() - 0.5) * 0.4) \
			* Basis.IDENTITY.scaled(Vector3(size, size, 1.0))
		_multimesh.set_instance_transform(slot, Transform3D(basis, Vector3(x, SPLASH_Y, z)))
		_multimesh.set_instance_custom_data(slot, Color(float(world.time), life, float(index), 0.0))
