class_name Fire
extends Node3D
## The flame over whatever is lit. One shared additive card, moved to the entity
## whose state is `lit` and cycled through the authored strip. Ported from
## `buildFire` (index.html :4204-4217) and the per-frame cycle (:5669-5692).
##
## There is no torch flame: a lit torch is a light on the player, never a card
## (the viewer draws none either — `world.torch` only feeds `world.light`).

const SHADER_PATH := "res://view/shaders/fx_card.gdshader"
## `ORDER.fx`.
const RENDER_PRIORITY := 4

var spec: Dictionary = {}
var _mesh: MeshInstance3D = null
var _material: ShaderMaterial = null
var _props: Dictionary = {}

func setup(pkg, world, fu) -> void:
	_props = pkg.manifest.get("props", {}) if pkg.manifest.get("props") is Dictionary else {}
	var fx: Dictionary = pkg.manifest.get("fx", {}) if pkg.manifest.get("fx") is Dictionary else {}
	var fire: Variant = fx.get("fire")
	if not (fire is Dictionary):
		return
	spec = fire
	var texture: Texture2D = pkg.texture(str(spec.get("strip", "")))
	if texture == null:
		spec = {}
		return
	_material = ShaderMaterial.new()
	_material.shader = load(SHADER_PATH)
	_material.render_priority = RENDER_PRIORITY
	_material.set_shader_parameter("u_map", texture)
	_material.set_shader_parameter("u_opacity", 1.0)
	_material.set_shader_parameter("u_frame_uv", _frame_uv(0))

	var size := float(spec.get("cell_px", 256)) / maxf(float(spec.get("px_per_meter", 1.0)), 0.0001)
	var base := 0.95
	var origin: Variant = spec.get("base_origin")
	if origin is Array and (origin as Array).size() >= 2:
		base = float((origin as Array)[1])
	var quad := QuadMesh.new()
	quad.size = Vector2(size, size)
	quad.center_offset = Vector3(0.0, size * (base - 0.5), 0.0)
	quad.material = _material
	_mesh = MeshInstance3D.new()
	_mesh.name = "FireCard"
	_mesh.mesh = quad
	_mesh.custom_aabb = AABB(Vector3(-size, -size, -size), Vector3(size * 2.0, size * 2.0, size * 2.0))
	_mesh.visible = false
	add_child(_mesh)

func update(world, _delta: float, _cam: Dictionary) -> void:
	if _mesh == null:
		return
	var lit: Variant = null
	for entity: Dictionary in world.entities:
		if entity.get("state", "") == "lit":
			lit = entity
			break
	_mesh.visible = lit != null
	if lit == null:
		return
	var entity: Dictionary = lit
	var prop: Dictionary = _props.get(str(entity.get("prop_id", "")), {})
	var states: Dictionary = prop.get("states", {}) if prop.get("states") is Dictionary else {}
	var state: Dictionary = states.get("lit", {}) if states.get("lit") is Dictionary else {}
	var card_height := 0.0
	if not state.is_empty():
		card_height = float(state.get("height_px", 0.0)) / maxf(float(state.get("px_per_meter", 1.0)), 0.0001)
	# With an anchor the flame sits where the reviewer put it; without one it
	# sits a little above the firepit's own measured height.
	var y := 0.3
	var anchor: Variant = state.get("anchor")
	if anchor is Array and (anchor as Array).size() >= 2:
		y = (float(state.get("ground_contact_y_normalized", 1.0)) - float((anchor as Array)[1])) * card_height
	elif not state.is_empty():
		y = float(state.get("height_meters", 0.545)) * 0.55
	_mesh.position = Vector3(float(entity.get("x", 0.0)), y, float(entity.get("z", 0.0)))
	# A Node3D's new transform reaches the RenderingServer only when the scene
	# tree flushes its transform-change list, which happens once per main-loop
	# iteration. A caller that drives whole frames by hand and then draws
	# (`advance()` / `frame()` followed by `RenderingServer.force_draw`, which is
	# what the capture harness does) never gets that flush, and the card is drawn
	# at the last transform the server saw — the identity it was created with, so
	# the flame lands on the world origin instead of on the fire. One node, once
	# a frame, is cheap enough to make this module true of its own accord.
	if _mesh.is_inside_tree():
		_mesh.force_update_transform()
	_material.set_shader_parameter("u_frame_uv", _frame_uv(_frame_index(float(world.time))))

## The strip's frame for this instant: `loop` or `ping_pong`, at the authored fps.
func _frame_index(time: float) -> int:
	var total: int = maxi(1, int(spec.get("frames", 1)))
	var tick := int(floor(time * float(spec.get("fps", 12.0))))
	if str(spec.get("mode", "loop")) == "ping_pong" and total > 1:
		var cycle := tick % (total * 2 - 2)
		return cycle if cycle < total else total * 2 - 2 - cycle
	return tick % total

## The window of one cell in reading order. Godot's UV origin is the image's
## top-left, so the row runs straight down: no `1 - (row + 1) / rows` flip.
func _frame_uv(index: int) -> Vector4:
	var columns: int = maxi(1, int(spec.get("columns", 1)))
	var rows: int = maxi(1, int(spec.get("rows", 1)))
	var column := index % columns
	@warning_ignore("integer_division")
	var row := index / columns
	return Vector4(
		float(column) / float(columns), float(row) / float(rows),
		1.0 / float(columns), 1.0 / float(rows))
