class_name SurvivalFire
extends Node3D
## The flame over everything that is burning. One additive card per burning
## thing, cycled through the authored strip. Ported from `buildFire`
## (index.html :4204-4217) and the per-frame cycle (:5669-5692), which had one
## card because the viewer had one fireplace; a torch can set a wood alight, so
## the card became a pool.
##
## A card is as tall as the thing under it — a pine is a column of fire and a
## tuft is a flare — and never shorter than the strip's own drawn height, which
## is what the campfire had and still gets.
##
## There is no torch flame: a lit torch is a light on the player, never a card
## (the viewer draws none either — `world.torch` only feeds `world.light`).

const SHADER_PATH := "res://scenes/view/shaders/fx_card.gdshader"
## `ORDER.fx`.
const RENDER_PRIORITY := 4
## How many flames are drawn at once. A player with a torch can leave more than
## this behind; the nearest are the ones that matter, and the light is one
## anyway (`SurvivalFirelightSystem`).
const MAX_CARDS := 16

var spec: Dictionary = {}
var _cards: Array[MeshInstance3D] = []
var _quads: Array[QuadMesh] = []
var _natural := 0.0
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

	_natural = float(spec.get("cell_px", 256)) / maxf(float(spec.get("px_per_meter", 1.0)), 0.0001)

func update(world, _delta: float, _cam: Dictionary) -> void:
	if _material == null:
		return
	# The nearest burning things, because the pool is smaller than a wood a
	# torch can take.
	var burning: Array = []
	var px := float(world.player.x)
	var pz := float(world.player.z)
	for entity: Dictionary in world.entities:
		if float(entity.get("burn", 0.0)) <= 0.0 or entity.get("kind", "") != "prop":
			continue
		var dx := float(entity.get("x", 0.0)) - px
		var dz := float(entity.get("z", 0.0)) - pz
		burning.append({"entity": entity, "d": dx * dx + dz * dz})
	burning.sort_custom(func(a, b): return float(a["d"]) < float(b["d"]))
	if burning.size() > MAX_CARDS:
		burning.resize(MAX_CARDS)

	_material.set_shader_parameter("u_frame_uv", _frame_uv(_frame_index(float(world.time))))
	for i in burning.size():
		var entity: Dictionary = (burning[i] as Dictionary)["entity"]
		var prop: Dictionary = _props.get(str(entity.get("prop_id", "")), {})
		var states: Dictionary = prop.get("states", {}) if prop.get("states") is Dictionary else {}
		var look: Variant = states.get(str(entity.get("state", "")))
		var state: Dictionary = look if look is Dictionary else {}
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
		var size := maxf(_natural, float(state.get("height_meters", 0.0)))
		var card := _card(i)
		_size_card(i, size)
		card.visible = true
		card.position = Vector3(float(entity.get("x", 0.0)), y, float(entity.get("z", 0.0)))
		# A Node3D's new transform reaches the RenderingServer only when the scene
		# tree flushes its transform-change list, which happens once per main-loop
		# iteration. A caller that drives whole frames by hand and then draws
		# (`advance()` / `frame()` followed by `RenderingServer.force_draw`, which is
		# what the capture harness does) never gets that flush, and the card is drawn
		# at the last transform the server saw — the identity it was created with, so
		# the flame lands on the world origin instead of on the fire. One node, once
		# a frame, is cheap enough to make this module true of its own accord.
		if card.is_inside_tree():
			card.force_update_transform()
	for i in range(burning.size(), _cards.size()):
		_cards[i].visible = false


## The card at this index, made on first use: a run with one fireplace never
## builds the other fifteen.
func _card(index: int) -> MeshInstance3D:
	while _cards.size() <= index:
		var quad := QuadMesh.new()
		quad.material = _material
		var mesh := MeshInstance3D.new()
		mesh.name = "FireCard%d" % _cards.size()
		mesh.mesh = quad
		mesh.visible = false
		add_child(mesh)
		_quads.append(quad)
		_cards.append(mesh)
	return _cards[index]


## Size one card to the thing under it. The quad's origin sits at the flame's
## foot (`base_origin`), so the card grows upward from the ground.
func _size_card(index: int, size: float) -> void:
	var quad := _quads[index]
	if is_equal_approx(quad.size.x, size):
		return
	var base := 0.95
	var origin: Variant = spec.get("base_origin")
	if origin is Array and (origin as Array).size() >= 2:
		base = float((origin as Array)[1])
	quad.size = Vector2(size, size)
	quad.center_offset = Vector3(0.0, size * (base - 0.5), 0.0)
	_cards[index].custom_aabb = AABB(
		Vector3(-size, -size, -size), Vector3(size * 2.0, size * 2.0, size * 2.0))


## How many flames are on screen, and which node carries the nth. The cards are
## a pool, so the test that used to reach for the one card asks these instead.
func drawn() -> int:
	var n := 0
	for card: MeshInstance3D in _cards:
		if card.visible:
			n += 1
	return n


func card(index: int) -> MeshInstance3D:
	return _cards[index] if index < _cards.size() else null


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
