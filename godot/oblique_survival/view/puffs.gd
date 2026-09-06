class_name Puffs
extends Node3D
## Dust puffs: the ring buffer of 480 particles the viewer drew as a
## `THREE.Points` cloud (`buildParticles` / `spawnPuff`, index.html :3781-3853),
## here as one MultiMesh of camera-facing quads on `view/shaders/points.gdshader`.
##
## The pool node must stay at the origin: the shader reads the spawn point and
## the velocity out of MODEL_MATRIX, which carries this node's own transform.
##
## A burst is spawned by an event (a blow, a hurt, a strike) or by another view
## module: `spawn_puff` is public because the falling-trunk animation, which
## belongs to the card module, throws two of these when the trunk lands
## (index.html :5633-5665).

const CAPACITY := 480
const SHADER_PATH := "res://view/shaders/points.gdshader"
## The dust points sit in the viewer's `ORDER.particle` slot.
const RENDER_PRIORITY := 5

var _instance: MultiMeshInstance3D = null
var _multimesh: MultiMesh = null
var _material: ShaderMaterial = null
var _cursor: int = 0
## The atlas's kinds in cell order (`dust`, `leaves`, `chips`, `sparkle`), which
## is how `spawn_puff` turns a kind name into a cell index.
var _kinds: PackedStringArray = PackedStringArray()
var _world = null
var _rng := RandomNumberGenerator.new()

func setup(pkg, world, fu) -> void:
	_world = world
	# The viewer draws a procedural placeholder when the scope paid for no dust
	# sheet; a run without one simply shows no dust here (deviation, recorded).
	var fx: Dictionary = pkg.manifest.get("fx", {}) if pkg.manifest.get("fx") is Dictionary else {}
	var dust: Variant = fx.get("dust")
	if not (dust is Dictionary):
		return
	var spec: Dictionary = dust
	var atlas := str(spec.get("atlas", ""))
	var texture: Texture2D = pkg.texture(atlas)
	if texture == null:
		return
	_rng.seed = int(pkg.layout.get("seed", 0)) * 977 + 13

	_material = ShaderMaterial.new()
	_material.shader = load(SHADER_PATH)
	_material.render_priority = RENDER_PRIORITY
	_material.set_shader_parameter("u_map", texture)
	_material.set_shader_parameter("u_time", 0.0)
	var width := float(spec.get("width_px", 1024))
	var height := float(spec.get("height_px", 1024))
	var cells: Array = spec.get("cells", []) if spec.get("cells") is Array else []
	for index in range(4):
		var window := Vector4(0.0, 0.0, 1.0, 1.0)
		if index < cells.size():
			var cell: Dictionary = cells[index]
			# Top-left pixels straight to UV: Godot does not flip textures, so
			# the viewer's `1 - (y + h) / height` is not ported.
			window = Vector4(
				float(cell.get("x", 0)) / width, float(cell.get("y", 0)) / height,
				float(cell.get("w", width)) / width, float(cell.get("h", height)) / height)
		_material.set_shader_parameter("u_cell_%d" % index, window)
	for cell: Dictionary in cells:
		_kinds.append(str(cell.get("kind", "")))

	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	quad.material = _material
	_multimesh = MultiMesh.new()
	_multimesh.transform_format = MultiMesh.TRANSFORM_3D
	_multimesh.use_custom_data = true
	_multimesh.mesh = quad
	_multimesh.instance_count = CAPACITY
	for slot in range(CAPACITY):
		_multimesh.set_instance_transform(slot, Transform3D.IDENTITY)
		# Born long ago, so an unspawned slot is invisible from the first frame.
		_multimesh.set_instance_custom_data(slot, Color(-999.0, 1.0, 0.0, 0.0))
	_instance = MultiMeshInstance3D.new()
	_instance.name = "Puffs"
	_instance.multimesh = _multimesh
	# Positions live in the shader, so the pool must never be culled by its mesh.
	_instance.custom_aabb = AABB(Vector3(-4096.0, -4096.0, -4096.0), Vector3(8192.0, 8192.0, 8192.0))
	add_child(_instance)

func update(world, _delta: float, _cam: Dictionary) -> void:
	_world = world
	if _material != null:
		_material.set_shader_parameter("u_time", float(world.time))

## The event loop's puffs, verbatim from index.html :5551-5601.
func handle_event(event: Dictionary) -> void:
	if _material == null:
		return
	var time := float(_world.time) if _world != null else 0.0
	var kind := str(event.get("type", ""))
	var x := float(event.get("x", 0.0))
	var z := float(event.get("z", 0.0))
	if kind == "hit":
		var fx_kind := str(event.get("kind", ""))
		if fx_kind == "":
			fx_kind = "dust"
		# The blow throws its kind of debris along the blow, and kicks the ground.
		spawn_puff(fx_kind, x, z, time, {
			"count": 7, "y": 0.5, "speed": 1.4, "size": 0.22,
			"dir_x": float(event.get("away_x", 0.0)), "dir_z": float(event.get("away_z", 0.0)),
		})
		spawn_puff("dust", x, z, time, {"count": 5, "y": 0.1, "speed": 0.9, "size": 0.4, "rise": 0.5})
	elif kind == "puff":
		spawn_puff(str(event.get("kind", "")), x, z, time, {})
	elif kind == "hurt":
		spawn_puff("dust", x, z, time, {})
	elif kind == "strike":
		spawn_puff("sparkle", x, z, time, {"count": 12, "y": 0.2, "speed": 2.2, "size": 0.3, "rise": 1.6})

## A burst of puffs at (x, z). `count`, `speed`, `size` scale it; `dir_x`,
## `dir_z` bias the scatter along the blow, so chips fly away from the axe.
func spawn_puff(kind: String, x: float, z: float, time: float, options: Dictionary = {}) -> void:
	if _multimesh == null:
		return
	var count := int(options.get("count", 8))
	var y := float(options.get("y", 0.16))
	var speed0 := float(options.get("speed", 1.0))
	var size0 := float(options.get("size", 0.35))
	var life0 := float(options.get("life", 0.6))
	var dir_x := float(options.get("dir_x", 0.0))
	var dir_z := float(options.get("dir_z", 0.0))
	var rise := float(options.get("rise", 1.1))
	var index: int = maxi(0, _kinds.find(kind))
	for _i in range(count):
		var slot := _cursor % CAPACITY
		_cursor += 1
		var angle := _rng.randf() * TAU
		var speed := speed0 * (0.7 + _rng.randf() * 0.9)
		var velocity := Vector3(
			cos(angle) * speed + dir_x * speed0 * 0.8,
			rise * (0.8 + _rng.randf() * 0.7),
			sin(angle) * speed + dir_z * speed0 * 0.8)
		# The velocity rides in the first basis column and the spawn point in
		# the origin: the shader reads MODEL_MATRIX[0] and MODEL_MATRIX[3].
		var transform := Transform3D(
			Basis(velocity, Vector3.ZERO, Vector3.ZERO), Vector3(x, y, z))
		_multimesh.set_instance_transform(slot, transform)
		_multimesh.set_instance_custom_data(slot, Color(
			time, life0 * (0.8 + _rng.randf() * 0.5), size0 * (0.8 + _rng.randf() * 0.6),
			float(index)))
