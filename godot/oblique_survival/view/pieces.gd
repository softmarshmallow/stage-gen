class_name Pieces
extends Node3D

## The ground's small change: the forage, every piece of it a thing to take.
##
## One sheet, one `MultiMesh`, over one unit quad: `package/ground/forage.png`
## with `manifest.ground.forage.cells` at y 0.021. The litter sheet that once
## lay beside it at 0.018 is gone with decision 0060 — the world places nothing
## the player cannot act on — so what lies on the ground is what the hand can
## reach, and a stone on the turf is always a stone to pick up.
##
## Each piece is a flat quad laid on the ground and sized from its cell's own
## calibration: the manifest publishes, per cell, the painted `box` inside the
## cut and the `px_per_meter` that box measures against the cell's authored
## `size_units`, so the quad is `box.w / px_per_meter` by `box.h / px_per_meter`
## metres — the piece's own extent at its authored size — times the layout's
## per-entry `scale` jitter. The quad's window is the box, not the cell, so
## the piece is centred on its entry and no transparent margin rides along.
## Before this every piece was a square of the sheet's one `cell_meters`
## whatever it held, and a flint chip and a bundle of branches lay the same
## size. It is turned about the world's up axis so the image's bottom edge —
## where the artist drew the piece's own contact shadow — stays toward the
## camera. That is what `look.ground_pieces.orientation = "camera_facing"`
## asks for, so every piece is re-laid when the yaw moves, exactly as the
## cards are re-aimed.
##
## The per-instance atlas window rides in `INSTANCE_CUSTOM`; see
## `view/shaders/pieces_body.gdshaderinc`.

## `ALPHA_CUTOFF` (index.html :153).
const ALPHA_CUTOFF := 0.5
## `DECAL_Y` (index.html :180) and the forage layer above it (:3552).
const DECAL_Y := 0.014
const FORAGE_Y := DECAL_Y + 0.007

const PIECES_SHADER := "res://view/shaders/pieces.gdshader"

## One instanced sheet: its node, its per-entry layout, and the hidden set.
class Sheet extends RefCounted:
	var node: MultiMeshInstance3D = null
	var multimesh: MultiMesh = null
	var material: ShaderMaterial = null
	var count: int = 0
	## The layer height this sheet lies at.
	var y: float = 0.0
	## The sheet's `cell_meters`: the lattice's drawing scale, kept for the record.
	var cell_meters: float = 1.0
	var px := PackedFloat32Array()
	var pz := PackedFloat32Array()
	## The layout's authored jitter, in radians.
	var spin := PackedFloat32Array()
	var scale := PackedFloat32Array()
	## Per instance, in metres: the piece's width and depth on the ground, from
	## its cell's painted box over its cell's ruler.
	var size_w := PackedFloat32Array()
	var size_h := PackedFloat32Array()
	## 1 while the piece is not to be drawn (a zero-scale instance).
	var hidden := PackedByteArray()
	## The atlas window each instance was given, kept for a headless read: the
	## dummy renderer stores nothing a `MultiMesh` is handed.
	var windows: Array[Color] = []

var forage: Sheet = null

var _package = null
var _manifest: Dictionary = {}
## `look.ground_pieces.orientation`: only `camera_facing` adds the camera yaw.
var _camera_facing: bool = true
var _laid_yaw: float = NAN
## The visibility each forage instance was last laid with, so the sync costs a
## comparison and not a transform write.
var _forage_shown := PackedByteArray()
## The forage entities, in the world's own order, kept against the entity array
## they were read from. Forage is placed when the world is built and is neither
## spawned nor removed after — only its `picked` and `hidden` flags move — while
## drops come and go, so walking every entity in the world to find the forage
## among them was this module's whole per-frame cost. The list is rebuilt when
## the array itself is replaced, and when it has grown shorter than it was
## (which is what a `clear()` or a removal looks like from here).
var _forage_entities: Array = []
var _forage_source: Variant = null
var _forage_source_size: int = -1

# --- build -----------------------------------------------------------------

func setup(pkg, world, fu) -> void:
	_package = pkg
	_manifest = pkg.manifest
	var ground: Dictionary = _manifest.get("ground", {})
	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else _manifest.get("layout", {})
	var pieces_look: Dictionary = _manifest.get("look", {}).get("ground_pieces", {})
	_camera_facing = String(pieces_look.get("orientation", "camera_facing")) == "camera_facing"

	forage = _build_sheet(ground.get("forage"), layout.get("forage", []), FORAGE_Y, fu)
	if forage != null:
		_forage_shown.resize(forage.count)
		_forage_shown.fill(1)
	# The first lay: the camera has not moved yet, so `update` would skip it.
	_orient_all(_yaw_of(world))

## One sheet, or null when the run has no such spec or no entries for it.
func _build_sheet(spec: Variant, entries: Array, y: float, fu) -> Sheet:
	if not (spec is Dictionary) or entries.is_empty():
		return null
	var sheet_spec: Dictionary = spec
	var cells: Array = sheet_spec.get("cells", [])
	if cells.is_empty():
		return null
	var width := float(sheet_spec.get("width_px", 1024))
	var height := float(sheet_spec.get("height_px", 1024))

	var sheet := Sheet.new()
	sheet.count = entries.size()
	sheet.y = y
	sheet.cell_meters = float(sheet_spec.get("cell_meters", 1.0))
	sheet.px.resize(sheet.count)
	sheet.pz.resize(sheet.count)
	sheet.spin.resize(sheet.count)
	sheet.scale.resize(sheet.count)
	sheet.size_w.resize(sheet.count)
	sheet.size_h.resize(sheet.count)
	sheet.hidden.resize(sheet.count)

	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_custom_data = true
	multimesh.mesh = quad_mesh()
	multimesh.instance_count = sheet.count
	sheet.multimesh = multimesh

	for index in sheet.count:
		var entry: Dictionary = entries[index]
		sheet.px[index] = float(entry.get("x", 0.0))
		sheet.pz[index] = float(entry.get("z", 0.0))
		sheet.spin[index] = deg_to_rad(float(entry.get("rotation_degrees", 0.0)))
		sheet.scale[index] = float(entry.get("scale", 1.0)) if entry.get("scale") else 1.0
		var cell: Dictionary = cells[int(entry.get("cell", 0)) % cells.size()]
		var box := piece_box(cell)
		var window := cell_window(box, width, height)
		sheet.windows.append(window)
		multimesh.set_instance_custom_data(index, window)
		var size := piece_size(cell)
		sheet.size_w[index] = size.x * sheet.scale[index]
		sheet.size_h[index] = size.y * sheet.scale[index]

	sheet.material = make_material(_package, _manifest, sheet_spec.get("atlas", ""), PIECES_SHADER, fu)
	sheet.node = MultiMeshInstance3D.new()
	sheet.node.multimesh = multimesh
	sheet.node.material_override = sheet.material
	sheet.node.custom_aabb = world_aabb(_manifest)
	sheet.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(sheet.node)
	return sheet

## The window a cell is drawn through: its painted `box`, which the manifest
## publishes for every cell (`RunPackage.check_manifest` refuses one without).
static func piece_box(cell: Dictionary) -> Dictionary:
	return cell["box"]

## A piece's extent on the ground, in metres, before the layout's jitter: the
## box's pixels over the cell's own ruler (`px_per_meter`, the painted extent
## against the authored `size_units`).
static func piece_size(cell: Dictionary) -> Vector2:
	var box := piece_box(cell)
	var per_meter := float(cell["px_per_meter"])
	return Vector2(float(box["w"]) / per_meter, float(box["h"]) / per_meter)

# --- the frame -------------------------------------------------------------

func update(world, _delta: float, cam: Dictionary) -> void:
	var yaw := float(cam.get("yaw", 0.0))
	# Every piece is re-laid only when the yaw actually moved
	# (index.html :5465-5474); a settled camera costs nothing.
	if bool(cam.get("changed", false)) or not is_equal_approx(yaw, _laid_yaw):
		_orient_all(yaw)
	_sync_forage(world)

func _orient_all(yaw: float) -> void:
	_laid_yaw = yaw
	if forage != null:
		_orient(forage, yaw)

func _orient(sheet: Sheet, yaw: float) -> void:
	for index in sheet.count:
		_lay(sheet, index, yaw)

## `layPiece` (index.html :3726-3740). Lay flat, then turn about the world's up
## axis so the image's bottom faces the camera, plus the authored jitter. Three
## composes the Euler as `Rx * Ry * Rz`, so the spin happens in the quad's own
## plane before it is laid flat; the product below is that, term for term.
func _lay(sheet: Sheet, index: int, yaw: float) -> void:
	sheet.multimesh.set_instance_transform(index, piece_transform(sheet, index, yaw))

## The transform `_lay` writes, as a value. Godot's dummy renderer keeps nothing
## a `MultiMesh` is handed, so this is also the only way a headless test can see
## what a piece was laid with.
func piece_transform(sheet: Sheet, index: int, yaw: float) -> Transform3D:
	var hidden := sheet.hidden[index] == 1
	var w := 0.0 if hidden else sheet.size_w[index]
	var h := 0.0 if hidden else sheet.size_h[index]
	var spin := sheet.spin[index] + (yaw if _camera_facing else 0.0)
	var basis := Basis(Vector3(1.0, 0.0, 0.0), -PI * 0.5) * Basis(Vector3(0.0, 0.0, 1.0), spin)
	return Transform3D(basis.scaled_local(Vector3(w, h, 1.0)),
		Vector3(sheet.px[index], sheet.y, sheet.pz[index]))

## A forage piece is drawn while it is neither picked nor hidden by the season
## (index.html :4987-4991). The viewer drives this from `entity.dirty`; here the
## flags are compared against what was last laid, so the module is idempotent
## and does not race whichever other module also clears `dirty`.
func _sync_forage(world) -> void:
	if forage == null or world == null:
		return
	var entities: Variant = field(world, "entities", [])
	if not (entities is Array):
		return
	var list: Array = entities
	if not is_same(list, _forage_source) or list.size() < _forage_source_size:
		_forage_source = list
		_forage_source_size = list.size()
		_forage_entities.clear()
		for entity in list:
			if entity is Dictionary and (entity as Dictionary).get("kind", "") == "forage":
				_forage_entities.append(entity)
	elif list.size() > _forage_source_size:
		_forage_source_size = list.size()
	for entity in _forage_entities:
		# Read straight off the Dictionary: this is a thousand entries a frame
		# and `field` is a static call an entry.
		var e: Dictionary = entity
		var index := int(e.get("index", -1))
		if index < 0 or index >= forage.count:
			continue
		var shown := 1 if not (bool(e.get("picked", false)) or bool(e.get("hidden", false))) else 0
		if _forage_shown[index] == shown:
			continue
		_forage_shown[index] = shown
		forage.hidden[index] = 0 if shown == 1 else 1
		_lay(forage, index, _laid_yaw)

## `setForageVisible` (index.html :3655-3661), for a caller that has the index.
func set_forage_visible(index: int, visible: bool) -> void:
	if forage == null or index < 0 or index >= forage.count:
		return
	forage.hidden[index] = 0 if visible else 1
	_forage_shown[index] = 1 if visible else 0
	_lay(forage, index, _laid_yaw)

## `showAllForage` (index.html :3663-3667): every piece back, after a reset.
func show_all_forage() -> void:
	if forage == null:
		return
	forage.hidden.fill(0)
	_forage_shown.fill(1)
	_orient(forage, _laid_yaw)

# --- the pointer's lift ------------------------------------------------------

## The forage instance under the pointer and the one in reach, by MultiMesh
## index, -1 for none. A card is one node and is lifted by swapping its
## material (`Cards.set_highlight`); a forage piece is one instance among a
## thousand in a single draw, so the sheet's material is handed the two indices
## and the shader lifts the instance whose id matches (`u_lift_a`, `u_lift_b`
## in `pieces_body.gdshaderinc`). Before this a stone that lay in the meadow
## since the world was laid answered the hand with its label alone, while the
## same stone knocked loose by a pick — a dropped item, with a card — lifted.
var _lift_hover: int = -1
var _lift_focus: int = -1

## Lift the piece standing for `entity` (the thing under the pointer). Anything
## that is not a forage entity — null, "", a tree — lifts nothing here, so the
## caller hands over whatever the pick returned and need not sort by kind.
func set_highlight(entity: Variant) -> void:
	var index := forage_index(entity)
	if index == _lift_hover:
		return
	_lift_hover = index
	_apply_lift()

## Lift the piece in reach (the focus), the same way.
func set_focus(entity: Variant) -> void:
	var index := forage_index(entity)
	if index == _lift_focus:
		return
	_lift_focus = index
	_apply_lift()

## The two lifted instance indices, hover then focus, -1 for none.
func lifted() -> Array[int]:
	return [_lift_hover, _lift_focus]

func _apply_lift() -> void:
	if forage == null or forage.material == null:
		return
	forage.material.set_shader_parameter("u_lift_a", _lift_hover)
	forage.material.set_shader_parameter("u_lift_b", _lift_focus)

## A forage entity's instance index on the sheet, -1 for anything else.
func forage_index(entity: Variant) -> int:
	if not (entity is Dictionary):
		return -1
	var e: Dictionary = entity
	if e.get("kind", "") != "forage":
		return -1
	var index := int(e.get("index", -1))
	if forage == null or index < 0 or index >= forage.count:
		return -1
	return index

# --- the quad and the material ----------------------------------------------

## The unit quad every piece is drawn on: three's `PlaneGeometry(1, 1)`,
## centred, in the XY plane, facing +Z. The UVs are written out rather than
## taken from `QuadMesh` so the atlas window needs no assumption about Godot's
## own quad: UV (0,0) is the quad's top-left corner and therefore the window's
## top-left pixel.
static func quad_mesh() -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([
		Vector3(-0.5, -0.5, 0.0), Vector3(0.5, -0.5, 0.0),
		Vector3(0.5, 0.5, 0.0), Vector3(-0.5, 0.5, 0.0),
	])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([
		Vector2(0.0, 1.0), Vector2(1.0, 1.0), Vector2(1.0, 0.0), Vector2(0.0, 0.0),
	])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([
		Vector3(0.0, 0.0, 1.0), Vector3(0.0, 0.0, 1.0),
		Vector3(0.0, 0.0, 1.0), Vector3(0.0, 0.0, 1.0),
	])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0, 1, 2, 0, 2, 3])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh

## A window in atlas UV, as the four floats `INSTANCE_CUSTOM` carries: a cell
## or a cell's painted box, in pixels from the image's top-left, straight
## through. Godot does not flip textures, so the viewer's `1 - (y + h) / height`
## (its `flipY` compensation) is dropped.
static func cell_window(cell: Dictionary, width: float, height: float) -> Color:
	return Color(
		float(cell.get("x", 0.0)) / width,
		float(cell.get("y", 0.0)) / height,
		float(cell.get("w", width)) / width,
		float(cell.get("h", height)) / height)

## The sheet's material: its atlas, the alpha cutoff, and the ground's own
## splat plate for the canopy darkening. The viewer shares the ground's
## uniform objects (index.html :3683-3685); here the plate and the two world
## numbers are read from the manifest, which is where the ground reads them
## too, so the value is the same either way.
static func make_material(pkg, manifest: Dictionary, atlas: String, shader_path: String, fu) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = load(shader_path)
	material.set_shader_parameter("u_map", pkg.texture(atlas))
	material.set_shader_parameter("u_alpha_cutoff", ALPHA_CUTOFF)
	var ground: Dictionary = manifest.get("ground", {})
	var splat: Dictionary = ground.get("splat", {})
	var image_ref := String(splat.get("image", ""))
	if image_ref != "":
		# A data plate: linear, no mipmaps (index.html :2548-2554).
		material.set_shader_parameter("u_splat", pkg.texture(image_ref, false))
	var size := float(ground.get("size_meters", 256.0))
	material.set_shader_parameter("u_world_origin", Vector2(-size * 0.5, -size * 0.5))
	material.set_shader_parameter("u_world_extent", Vector2(size, size))
	if fu != null:
		fu.register(material)
	return material

## Godot builds a MultiMesh's bounds from the mesh alone, so a sheet of
## scattered instances is culled as one object and vanishes. This is the box.
static func world_aabb(manifest: Dictionary) -> AABB:
	var size := float(manifest.get("ground", {}).get("size_meters", 256.0)) * 1.1
	return AABB(Vector3(-size * 0.5, -8.0, -size * 0.5), Vector3(size, 24.0, size))

## A field of a Dictionary or of an Object, whichever the simulation hands over.
static func field(holder, name: String, fallback = null):
	if holder is Dictionary:
		return holder.get(name, fallback)
	if holder is Object:
		var value = holder.get(name)
		return fallback if value == null else value
	return fallback

static func _yaw_of(world) -> float:
	var yaw = field(world, "camera_yaw", 0.0)
	return float(yaw) if yaw != null else 0.0
