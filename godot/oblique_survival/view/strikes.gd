class_name Strikes
extends Node3D
## Lightning: a bolt stood in the world at the strike point, held for the flash
## and gone, plus the sparkle that lands with it. Ported from `strike` /
## `updateStrikes` (index.html :4173-4202) and the event loop's twelve-particle
## burst (:5586).
##
## The twelve-particle sparkle that lands with the bolt is spawned by `Puffs`,
## which is offered the same `strike` event by the frame owner: this module
## draws the bolt only, so the burst is never thrown twice.

const SHADER_PATH := "res://view/shaders/fx_card.gdshader"
## `ORDER.particle`.
const RENDER_PRIORITY := 5

var spec: Dictionary = {}
var _texture: Texture2D = null
var _shader: Shader = null
var _bolts: Array = []
## The world clock, carried from `update` so `handle_event` can date a bolt.
var _time: float = 0.0

func setup(pkg, world, fu) -> void:
	var weather: Dictionary = pkg.manifest.get("weather", {}) if pkg.manifest.get("weather") is Dictionary else {}
	var rain: Variant = weather.get("rain")
	if not (rain is Dictionary):
		return
	var strike: Variant = (rain as Dictionary).get("strike")
	if not (strike is Dictionary):
		return
	spec = strike
	_texture = pkg.texture(str(spec.get("atlas", "")))
	if _texture == null:
		spec = {}
		return
	_shader = load(SHADER_PATH)

func update(world, _delta: float, _cam: Dictionary) -> void:
	_time = float(world.time)
	update_strikes(_time)

func handle_event(event: Dictionary) -> void:
	if str(event.get("type", "")) != "strike":
		return
	strike(event, _time)

## A bolt stood in the world at the strike point, held for the flash and gone.
func strike(event: Dictionary, time: float) -> void:
	if spec.is_empty():
		return
	var material := ShaderMaterial.new()
	material.shader = _shader
	material.render_priority = RENDER_PRIORITY
	material.set_shader_parameter("u_map", _texture)
	# Full on its birth frame, as `flashEnvelope(0)` is: the frame owner drains
	# events after `update_strikes`, so the first envelope write is next frame.
	material.set_shader_parameter("u_opacity", 1.0)
	var cells: Array = spec.get("cells", []) if spec.get("cells") is Array else []
	if not cells.is_empty():
		var index: int = clampi(int(event.get("cell", 0)), 0, cells.size() - 1)
		var cell: Dictionary = cells[index]
		var width := float(spec.get("width_px", 1024))
		var height := float(spec.get("height_px", 1024))
		material.set_shader_parameter("u_frame_uv", Vector4(
			float(cell.get("x", 0)) / width, float(cell.get("y", 0)) / height,
			float(cell.get("w", width)) / width, float(cell.get("h", height)) / height))
	var side := float(spec.get("height_meters", 13.6))
	var quad := QuadMesh.new()
	quad.size = Vector2(side, side)
	# `cardGeometry(side, side, 0.97)`: the foot row sits at the node's origin.
	quad.center_offset = Vector3(0.0, side * (0.97 - 0.5), 0.0)
	quad.material = material
	var mesh := MeshInstance3D.new()
	mesh.mesh = quad
	mesh.position = Vector3(float(event.get("x", 0.0)), 0.0, float(event.get("z", 0.0)))
	# The card is billboarded in the shader, so its own AABB never turns.
	mesh.custom_aabb = AABB(Vector3(-side, -side, -side), Vector3(side * 2.0, side * 2.0, side * 2.0))
	add_child(mesh)
	# The bolt is born and drawn inside one hand-driven frame, and a Node3D's
	# transform reaches the RenderingServer only when the scene tree flushes its
	# transform-change list — once per main-loop iteration, which a caller
	# stepping the world itself never reaches. Without this the bolt is drawn at
	# the world origin on every frame of its half-second life.
	if mesh.is_inside_tree():
		mesh.force_update_transform()
	_bolts.append({
		"mesh": mesh, "material": material, "start": time,
		"seconds": float(spec.get("flash_seconds", 0.5)),
	})

func update_strikes(time: float) -> void:
	var alive: Array = []
	for bolt: Dictionary in _bolts:
		var age := time - float(bolt["start"])
		var seconds := float(bolt["seconds"])
		(bolt["material"] as ShaderMaterial).set_shader_parameter(
			"u_opacity", flash_envelope(age, seconds))
		if age > seconds:
			(bolt["mesh"] as Node).queue_free()
		else:
			alive.append(bolt)
	_bolts = alive

## The flash: two pulses and a tail, the way a real strike reads. Feel, not
## contract (index.html :442-448). Shared with WeatherView, which drives the
## frame's `u_flash` from the same curve.
static func flash_envelope(age: float, seconds: float) -> float:
	if age < 0.0 or age > seconds:
		return 0.0
	if age < 0.05:
		return 1.0
	if age < 0.09:
		return 0.3
	if age < 0.16:
		return 0.9
	return maxf(0.0, 0.9 * (1.0 - (age - 0.16) / maxf(0.01, seconds - 0.16)))
