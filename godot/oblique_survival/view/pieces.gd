class_name Pieces
extends Node3D

## The ground's small change: litter and forage.
##
## A port of the viewer's `buildPieces` / `layPiece` / `orientPieces` /
## `buildClutter` / `buildForage` / `setForageVisible` / `showAllForage`
## (index.html :3533-3567, :3655-3740). Two sheets, one `MultiMesh` each, over
## the same unit quad: `package/ground/clutter.png` with
## `manifest.ground.clutter.cells` at y 0.018, and `forage.png` with
## `manifest.ground.forage.cells` at y 0.021. Run full-v66 lays 6554 and 1049.
##
## Each piece is a flat quad laid on the ground, sized square by the sheet's
## `cell_meters` (never by the cell's aspect: the viewer scales `size, size`)
## times the layout's per-entry `scale`, and turned about the world's up axis so
## the image's bottom edge — which is where the artist drew the piece's own
## contact shadow — stays toward the camera. That is what
## `look.ground_pieces.orientation = "camera_facing"` asks for, so every piece
## is re-laid when the yaw moves, exactly as the cards are re-aimed.
##
## The per-instance atlas window rides in `INSTANCE_CUSTOM`; see
## `view/shaders/clutter_body.gdshaderinc`.

## `ALPHA_CUTOFF` (index.html :153).
const ALPHA_CUTOFF := 0.5
## `DECAL_Y` (index.html :180) and the two layers above it (:3538, :3552).
const DECAL_Y := 0.014
const CLUTTER_Y := DECAL_Y + 0.004
const FORAGE_Y := DECAL_Y + 0.007

const CLUTTER_SHADER := "res://view/shaders/clutter.gdshader"

## One instanced sheet: its node, its per-entry layout, and the hidden set.
class Sheet extends RefCounted:
	var node: MultiMeshInstance3D = null
	var multimesh: MultiMesh = null
	var material: ShaderMaterial = null
	var count: int = 0
	## The layer height this sheet lies at (the viewer's `mesh.userData.y`).
	var y: float = 0.0
	## The sheet's `cell_meters`: the viewer's `size0`.
	var size0: float = 1.0
	var px := PackedFloat32Array()
	var pz := PackedFloat32Array()
	## The layout's authored jitter, in radians.
	var spin := PackedFloat32Array()
	var scale := PackedFloat32Array()
	## 1 while the piece is not to be drawn (a zero-scale instance).
	var hidden := PackedByteArray()
	## The atlas window each instance was given, kept for a headless read: the
	## dummy renderer stores nothing a `MultiMesh` is handed.
	var windows: Array[Color] = []

var clutter: Sheet = null
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

	clutter = _build_sheet(ground.get("clutter"), layout.get("clutter", []), CLUTTER_Y, fu)
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
	sheet.size0 = float(sheet_spec.get("cell_meters", 1.0))
	sheet.px.resize(sheet.count)
	sheet.pz.resize(sheet.count)
	sheet.spin.resize(sheet.count)
	sheet.scale.resize(sheet.count)
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
		var window := cell_window(cell, width, height)
		sheet.windows.append(window)
		multimesh.set_instance_custom_data(index, window)

	sheet.material = make_material(_package, _manifest, sheet_spec.get("atlas", ""), CLUTTER_SHADER, fu)
	sheet.node = MultiMeshInstance3D.new()
	sheet.node.multimesh = multimesh
	sheet.node.material_override = sheet.material
	sheet.node.custom_aabb = world_aabb(_manifest)
	sheet.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(sheet.node)
	return sheet

# --- the frame -------------------------------------------------------------

func update(world, _delta: float, cam: Dictionary) -> void:
	var yaw := float(cam.get("yaw", 0.0))
	# The viewer re-lays every piece only when the yaw actually moved
	# (index.html :5465-5474); a settled camera costs nothing.
	if bool(cam.get("changed", false)) or not is_equal_approx(yaw, _laid_yaw):
		_orient_all(yaw)
	_sync_forage(world)

## `orientClutter` + `orientForage` (index.html :3714-3724, :3558-3560).
func _orient_all(yaw: float) -> void:
	_laid_yaw = yaw
	if clutter != null:
		_orient(clutter, yaw)
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
	var size := 0.0 if sheet.hidden[index] == 1 else sheet.size0 * sheet.scale[index]
	var spin := sheet.spin[index] + (yaw if _camera_facing else 0.0)
	var basis := Basis(Vector3(1.0, 0.0, 0.0), -PI * 0.5) * Basis(Vector3(0.0, 0.0, 1.0), spin)
	return Transform3D(basis.scaled_local(Vector3(size, size, 1.0)),
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

# --- shared with `Plants` and `Leaves` --------------------------------------

## The unit quad every piece, plant and leaf is drawn on: three's
## `PlaneGeometry(1, 1)`, centred, in the XY plane, facing +Z. The UVs are
## written out rather than taken from `QuadMesh` so the atlas window needs no
## assumption about Godot's own quad: UV (0,0) is the quad's top-left corner and
## therefore the cell's top-left pixel.
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

## A cell's window in atlas UV, as the four floats `INSTANCE_CUSTOM` carries.
## Pixels from the top-left, straight through: Godot does not flip textures, so
## the viewer's `1 - (y + h) / height` (its `flipY` compensation) is dropped.
static func cell_window(cell: Dictionary, width: float, height: float) -> Color:
	return Color(
		float(cell.get("x", 0.0)) / width,
		float(cell.get("y", 0.0)) / height,
		float(cell.get("w", width)) / width,
		float(cell.get("h", height)) / height)

## A clutter-family material: the sheet's atlas, the alpha cutoff, and the
## ground's own splat plate for the canopy darkening. The viewer shares the
## ground's uniform objects (index.html :3683-3685); here the plate and the two
## world numbers are read from the manifest, which is where the ground reads
## them too, so the value is the same either way.
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
