class_name Leaves
extends Node3D

## Leaves shaken out of a crown, and the litter they become.
##
## A port of the viewer's `buildLeaves` / `spawnLeaves` / `updateLeaves`
## (index.html :3117-3225). The litter sheet's `fallen` cells are the leaves —
## already drawn, already in the style, and what ends up on the ground under a
## tree anyway — in a ring-buffer pool of 96 over the same instanced quad the
## other pieces use.
##
## Airborne, a leaf flutters across the screen's right axis and tumbles about
## its own card axis; when it lands it becomes flat litter with its lower edge
## to the camera, and after six seconds the slot is taken back.

## `buildLeaves(capacity = 96)` (index.html :3117).
const CAPACITY := 96
## `size: clutter.cell_meters * 0.55` (index.html :3155).
const SIZE_SCALE := 0.55
## Landed litter sits at `DECAL_Y + 0.006` (index.html :3216).
const LANDED_Y := Pieces.DECAL_Y + 0.006
## `FALL_SECONDS` (index.html :156): when a felled trunk's crown meets the ground.
const FALL_SECONDS := 1.1

const LEAVES_SHADER := "res://view/shaders/leaves.gdshader"

var node: MultiMeshInstance3D = null
var multimesh: MultiMesh = null
var material: ShaderMaterial = null

## Whether this module spawns the burst a felled trunk throws when its crown
## lands. The viewer does it from inside the faller animation (index.html
## :5644-5650), which a props module owns; if that module calls `spawn_leaves`
## itself it must clear this, or the burst is thrown twice.
var fell_leaves_owned: bool = true

var _package = null
var _manifest: Dictionary = {}
## The world this module was set up with, for the clock an event does not carry.
var _world = null
## The `fallen` cells of the litter sheet, as ready-made atlas windows.
var _windows: Array[Color] = []
var _size: float = 0.0
var _cursor: int = 0
## One entry per slot: a Dictionary while the leaf lives, null when the slot is
## free. Ninety-six of them, so the shape costs nothing.
var _live: Array = []
## Felled trunks whose crown has not landed yet: `{at, x, z, sign, height}`.
var _pending: Array = []
var _rng := RandomNumberGenerator.new()
var _yaw: float = 0.0
var _basis := Basis()

# --- build -----------------------------------------------------------------

func setup(pkg, world, fu) -> void:
	_package = pkg
	_manifest = pkg.manifest
	_world = world
	var clutter: Variant = _manifest.get("ground", {}).get("clutter")
	if not (clutter is Dictionary):
		return
	var spec: Dictionary = clutter
	var cells: Array = spec.get("cells", [])
	var width := float(spec.get("width_px", 1024))
	var height := float(spec.get("height_px", 1024))
	for cell in cells:
		if cell is Dictionary and String((cell as Dictionary).get("contact", "")) == "fallen":
			_windows.append(Pieces.cell_window(cell, width, height))
	if _windows.is_empty():
		return
	_size = float(spec.get("cell_meters", 1.0)) * SIZE_SCALE

	# The viewer's leaves draw from `Math.random`. Seeding from the layout keeps
	# a capture repeatable without touching the simulation's own generator.
	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else _manifest.get("layout", {})
	_rng.seed = int(layout.get("seed", 1)) ^ 0x1eaf

	_live.resize(CAPACITY)
	multimesh = MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_custom_data = true
	multimesh.mesh = Pieces.quad_mesh()
	multimesh.instance_count = CAPACITY
	for index in CAPACITY:
		multimesh.set_instance_transform(index, Transform3D(Basis().scaled(Vector3.ZERO), Vector3.ZERO))

	material = Pieces.make_material(pkg, _manifest, spec.get("atlas", ""), LEAVES_SHADER, fu)
	node = MultiMeshInstance3D.new()
	node.multimesh = multimesh
	node.material_override = material
	node.custom_aabb = Pieces.world_aabb(_manifest)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)
	_yaw = float(Pieces.field(world, "camera_yaw", 0.0))
	_basis = Plants._basis_of(world)

# --- the frame -------------------------------------------------------------

func update(world, delta: float, cam: Dictionary) -> void:
	if node == null:
		return
	_world = world
	_yaw = float(cam.get("yaw", _yaw))
	_basis = cam.get("basis", _basis)
	var time := float(Pieces.field(world, "time", 0.0))
	_release_pending(time)
	_update_leaves(time, delta)

## The blow that sheds them: a `hit` on a tree (index.html :5570-5575), and the
## `fell` whose crown throws another handful when it lands (:5644-5650).
func handle_event(event: Dictionary) -> void:
	if node == null:
		return
	var type := String(event.get("type", ""))
	if type == "hit":
		var prop: Dictionary = _manifest.get("props", {}).get(String(event.get("prop_id", "")), {})
		if String(prop.get("family", "")) != "tree":
			return
		var state: Dictionary = prop.get("states", {}).get(String(event.get("state", "")), {})
		var height := float(state.get("height_meters", 0.0))
		if height <= 0.0:
			height = 3.0
		spawn_leaves(float(event.get("x", 0.0)), float(event.get("z", 0.0)), _time_now(event), {
			"count": 10 if bool(event.get("last", false)) else 5,
			"top": height * 0.9,
			"bottom": height * 0.45,
			"spread": height * 0.18,
		})
	elif type == "fell" and fell_leaves_owned:
		_pending.append({
			"at": _time_now(event) + FALL_SECONDS,
			"x": float(event.get("x", 0.0)),
			"z": float(event.get("z", 0.0)),
			"sign": float(event.get("sign", 1.0)),
			"height": float(event.get("height", 3.0)),
		})

## `spawnLeaves(x, z, time, options)` (index.html :3162-3187). Options:
## `count`, `top`, `bottom`, `spread`, `drift_x`, `drift_z`.
func spawn_leaves(x: float, z: float, time: float, options: Dictionary = {}) -> void:
	if node == null:
		return
	var count := int(options.get("count", 6))
	var top := float(options.get("top", 3.0))
	var bottom := float(options.get("bottom", 1.5))
	var spread := float(options.get("spread", 0.6))
	var drift_x := float(options.get("drift_x", 0.0))
	var drift_z := float(options.get("drift_z", 0.0))
	var right := screen_right(_yaw)
	for i in count:
		var slot := _cursor % CAPACITY
		_cursor += 1
		multimesh.set_instance_custom_data(slot, _windows[_rng.randi() % _windows.size()])
		var side := (_rng.randf() - 0.5) * 2.0 * spread
		_live[slot] = {
			"x": x + right.x * side,
			"z": z + right.y * side,
			"y": bottom + _rng.randf() * (top - bottom),
			"vx": drift_x * 0.5 + (_rng.randf() - 0.5) * 0.4,
			"vz": drift_z * 0.5 + (_rng.randf() - 0.5) * 0.4,
			"vy": -(0.7 + _rng.randf() * 0.6),
			"phase": _rng.randf() * 6.28,
			"spin": (_rng.randf() - 0.5) * 6.0,
			"born": time,
			"landed": -1.0,
			"jitter": (_rng.randf() - 0.5) * 0.5,
			"scale": 0.8 + _rng.randf() * 0.5,
		}

## `updateLeaves(time, dt)` (index.html :3189-3225).
func _update_leaves(time: float, dt: float) -> void:
	var right := screen_right(_yaw)
	for index in CAPACITY:
		var leaf = _live[index]
		if leaf == null:
			continue
		var age: float = time - leaf["born"]
		var scale: float = _size * leaf["scale"]
		var basis: Basis
		var origin: Vector3
		if leaf["landed"] < 0.0:
			# Airborne: a flutter across the screen's right axis, a slow tumble,
			# and a fall the flutter keeps from being a plumb line.
			var sway: float = sin(age * 5.0 + leaf["phase"]) * 0.55
			leaf["x"] += (leaf["vx"] + right.x * sway) * dt
			leaf["z"] += (leaf["vz"] + right.y * sway) * dt
			leaf["y"] += leaf["vy"] * dt
			if leaf["y"] <= 0.01:
				leaf["y"] = 0.01
				leaf["landed"] = time
			origin = Vector3(leaf["x"], leaf["y"], leaf["z"])
			basis = _basis * Basis(Vector3(0.0, 0.0, 1.0), leaf["spin"] * age)
		else:
			# On the ground it is litter: flat, its lower edge to the camera,
			# then taken back into the ground so the pool never fills.
			var down: float = time - leaf["landed"]
			if down > 6.0:
				_live[index] = null
				scale = 0.0
			elif down > 5.0:
				scale *= 1.0 - (down - 5.0)
			origin = Vector3(leaf["x"], LANDED_Y, leaf["z"])
			basis = Basis(Vector3(1.0, 0.0, 0.0), -PI * 0.5) \
				* Basis(Vector3(0.0, 0.0, 1.0), _yaw + leaf["jitter"])
		multimesh.set_instance_transform(
			index, Transform3D(basis.scaled_local(Vector3(scale, scale, 1.0)), origin))

## The crown meets the ground: the burst lands where it fell, along the screen's
## right axis at the yaw of that moment (index.html :5644-5650).
func _release_pending(time: float) -> void:
	if _pending.is_empty():
		return
	var still: Array = []
	for entry in _pending:
		if time < entry["at"]:
			still.append(entry)
			continue
		var right := screen_right(_yaw)
		var height: float = entry["height"]
		var sign_: float = entry["sign"]
		spawn_leaves(
			entry["x"] + right.x * sign_ * height * 0.7,
			entry["z"] + right.y * sign_ * height * 0.7,
			time,
			{"count": 8, "top": 1.2, "bottom": 0.3, "spread": height * 0.25})
	_pending = still

## Every leaf gone, for a reset.
func clear() -> void:
	if node == null:
		return
	_pending.clear()
	for index in CAPACITY:
		_live[index] = null
		multimesh.set_instance_transform(index, Transform3D(Basis().scaled(Vector3.ZERO), Vector3.ZERO))

## `screenRight(yaw)` (index.html :2932-2934): the world direction along the
## screen's right edge, as (x, z).
static func screen_right(yaw: float) -> Vector2:
	return Vector2(cos(yaw), -sin(yaw))

## An event carries no clock of its own, so the world's is read straight from
## the world this module was set up with. The event drain (viewer step 6) runs
## before `update` (step 7), so reading a cached frame time would be a frame old.
func _time_now(event: Dictionary) -> float:
	if event.has("time"):
		return float(event["time"])
	return float(Pieces.field(_world, "time", 0.0))
