class_name Plants
extends Node3D

## The mid-scale layer: the plant sheet's cells stood up as camera-facing cards.
##
## A port of the viewer's `buildPlants` / `plantWindows` / `orientPlants` /
## `layPlantShadows` / `setPlantsLook` (index.html :3568-3653). The same
## instanced sheet the litter uses, but upright: at true size from the cell's own
## bounding box, its foot on the ground at any pitch, writing depth so it sorts
## against the prop cards, with a small contact ellipse under it. Run full-v66
## stands 4588 of them.
##
## A season look swaps the atlas and the cell windows together — a snow cap
## grows a plant's box, so the size has to be recomputed with the window — and a
## run whose sheet has no such look keeps summer.

## `SHADOW_Y` (index.html :167).
const SHADOW_Y := 0.006
## `SHADOW_SPREAD` / `SHADOW_ALPHA` (index.html :292-293): the stack reaches zero
## at the quad's edge, so the ellipse ends without a rim.
const SHADOW_SPREAD := [1.0, 0.6, 0.22]
const SHADOW_ALPHA := [0.20, 0.30, 0.42]
## `SHADOW_STRENGTH.shadow` (index.html :296): a plant carries no skirt, so its
## seam is the whole ellipse.
const SHADOW_SEAM := 1.0
## `this.plantShadows.material.opacity *= 0.55` (index.html :3580).
const PLANT_SHADOW_SCALE := 0.55
## `layPlantShadows` (index.html :3623-3637).
const SHADOW_WIDTH_SCALE := 0.7
const SHADOW_DEPTH_RATIO := 0.45
const SHADOW_TEXTURE_PX := 128
## `ORDER.shadow` (index.html :187), as a priority inside the transparent pass.
const SHADOW_PRIORITY := 2

const PLANTS_SHADER := "res://view/shaders/plants.gdshader"

var node: MultiMeshInstance3D = null
var multimesh: MultiMesh = null
var material: ShaderMaterial = null
var shadow_node: MultiMeshInstance3D = null
var shadow_multimesh: MultiMesh = null

## The look currently drawn: "" is summer.
var look: String = ""
var count: int = 0

var _package = null
var _manifest: Dictionary = {}
var _spec: Dictionary = {}
var _entries: Array = []
var _px := PackedFloat32Array()
var _pz := PackedFloat32Array()
var _scale := PackedFloat32Array()
## Per instance, in metres: the card's width and height (the viewer's
## `plantSizes`, two floats an entry).
var _size_w := PackedFloat32Array()
var _size_h := PackedFloat32Array()
## The atlas window each instance was given, kept for a headless read.
var _windows: Array[Color] = []
var _laid_basis := Basis()
var _has_laid := false

# --- build -----------------------------------------------------------------

func setup(pkg, world, fu) -> void:
	_package = pkg
	_manifest = pkg.manifest
	var ground: Dictionary = _manifest.get("ground", {})
	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else _manifest.get("layout", {})
	var spec: Variant = ground.get("plants")
	_entries = layout.get("plants", [])
	if not (spec is Dictionary) or _entries.is_empty() or (spec as Dictionary).get("cells", []).is_empty():
		return
	_spec = spec
	count = _entries.size()

	_px.resize(count)
	_pz.resize(count)
	_scale.resize(count)
	_size_w.resize(count)
	_size_h.resize(count)
	for index in count:
		var entry: Dictionary = _entries[index]
		_px[index] = float(entry.get("x", 0.0))
		_pz[index] = float(entry.get("z", 0.0))
		_scale[index] = float(entry.get("scale", 1.0)) if entry.get("scale") else 1.0

	multimesh = MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_custom_data = true
	multimesh.mesh = Pieces.quad_mesh()
	multimesh.instance_count = count

	material = Pieces.make_material(pkg, _manifest, _spec.get("atlas", ""), PLANTS_SHADER, fu)
	node = MultiMeshInstance3D.new()
	node.multimesh = multimesh
	node.material_override = material
	node.custom_aabb = Pieces.world_aabb(_manifest)
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)

	_build_shadow_pool()
	_plant_windows(_spec)
	_orient(_basis_of(world))
	_lay_shadows()

## The contact pool, a `shadowPool(entries.length, 'shadow')` whose opacity is
## then taken to 55 % (index.html :3579-3580, :3755-3778). It lies in its own
## frame: the node is turned flat, so an instance's local (x, y) is world
## (x, -z) — the viewer's own convention, carried over so the maths reads the
## same as `layPlantShadows`.
func _build_shadow_pool() -> void:
	var blend: Dictionary = _manifest.get("ground", {}).get("splat", {}).get("blend", {})
	var strength := float(blend.get("shadow_strength", 1.0)) if blend.get("shadow_strength") != null else 1.0
	var opacity := SHADOW_SEAM * strength * PLANT_SHADOW_SCALE

	var pool_material := StandardMaterial3D.new()
	pool_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	pool_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	pool_material.albedo_texture = shadow_texture()
	pool_material.albedo_color = Color(0.0, 0.0, 0.0, opacity)
	pool_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	# Depth tested, never written: a contact ellipse belongs under the card, and
	# its far half lands on that card's own feet.
	pool_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	pool_material.disable_receive_shadows = true
	pool_material.render_priority = SHADOW_PRIORITY

	shadow_multimesh = MultiMesh.new()
	shadow_multimesh.transform_format = MultiMesh.TRANSFORM_3D
	shadow_multimesh.mesh = Pieces.quad_mesh()
	shadow_multimesh.instance_count = count

	shadow_node = MultiMeshInstance3D.new()
	shadow_node.multimesh = shadow_multimesh
	shadow_node.material_override = pool_material
	shadow_node.rotation = Vector3(-PI * 0.5, 0.0, 0.0)
	shadow_node.position = Vector3(0.0, SHADOW_Y, 0.0)
	shadow_node.custom_aabb = Pieces.world_aabb(_manifest)
	shadow_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(shadow_node)

## `plantWindows` (index.html :3588-3602): per instance, the cell's window in the
## atlas and its size in metres, from the cell's own bounding box — a knee-high
## plant is not a waist-high one.
func _plant_windows(sheet: Dictionary) -> void:
	var cells: Array = sheet.get("cells", [])
	var width := float(sheet.get("width_px", 1024))
	var height := float(sheet.get("height_px", 1024))
	var columns := float(sheet.get("columns", 4))
	var meters_per_px := float(sheet.get("cell_meters", 1.0)) / maxf(1.0, width / columns)
	_windows.resize(count)
	for index in count:
		var entry: Dictionary = _entries[index]
		var cell: Dictionary = cells[int(entry.get("cell", 0)) % cells.size()]
		_windows[index] = Pieces.cell_window(cell, width, height)
		multimesh.set_instance_custom_data(index, _windows[index])
		_size_w[index] = float(cell.get("w", width)) * meters_per_px * _scale[index]
		_size_h[index] = float(cell.get("h", height)) * meters_per_px * _scale[index]

# --- the frame -------------------------------------------------------------

func update(world, _delta: float, cam: Dictionary) -> void:
	if node == null:
		return
	# The viewer reads `world.look` here (index.html :5533-5534); `set_look` is
	# also part of the module contract, and either route is idempotent.
	var wanted = Pieces.field(world, "look", "")
	if wanted is String:
		set_look(wanted)
	var basis: Basis = cam.get("basis", Basis())
	if bool(cam.get("changed", false)) or not _same_basis(basis):
		_orient(basis)

## `orientPlants` (index.html :3604-3621). The card takes the camera's own
## rotation, and its centre sits half its height up its own (camera-tilted)
## axis, so its foot lands on the ground whatever the pitch. Never mirrored: a
## flipped card is the same card and the eye knows it, and the look contract
## forbids it.
func _orient(basis: Basis) -> void:
	_laid_basis = basis
	_has_laid = true
	for index in count:
		multimesh.set_instance_transform(index, plant_transform(index, basis))

## The transform `_orient` writes, as a value (see `Pieces.piece_transform`).
func plant_transform(index: int, basis: Basis) -> Transform3D:
	var h := _size_h[index]
	var up := basis.y
	return Transform3D(
		basis.scaled_local(Vector3(_size_w[index], h, 1.0)),
		Vector3(_px[index] + up.x * h * 0.5, up.y * h * 0.5, _pz[index] + up.z * h * 0.5))

## The contact ellipse's transform, in the flat pool's own frame.
func shadow_transform(index: int) -> Transform3D:
	var w := _size_w[index] * SHADOW_WIDTH_SCALE
	return Transform3D(Basis.IDENTITY.scaled_local(Vector3(w, w * SHADOW_DEPTH_RATIO, 1.0)),
		Vector3(_px[index], -_pz[index], 0.0))

## `layPlantShadows` (index.html :3623-3637). The ellipse does not turn with the
## camera, so it is laid once — and again when a look changes a plant's width.
func _lay_shadows() -> void:
	if shadow_multimesh == null:
		return
	for index in count:
		shadow_multimesh.set_instance_transform(index, shadow_transform(index))
	shadow_multimesh.visible_instance_count = count

## `setPlantsLook` (index.html :3640-3653): the look's atlas and windows, or
## summer's. A run whose sheet has no such look keeps summer.
func set_look(next_look: String) -> void:
	if node == null:
		return
	var looks: Dictionary = _spec.get("looks", {}) if _spec.get("looks") is Dictionary else {}
	var seasonal: Variant = looks.get(next_look) if next_look != "" else null
	var resolved := next_look if seasonal is Dictionary else ""
	if resolved == look:
		return
	look = resolved
	var sheet := _spec.duplicate()
	if seasonal is Dictionary:
		sheet["atlas"] = (seasonal as Dictionary).get("atlas", sheet.get("atlas", ""))
		sheet["cells"] = (seasonal as Dictionary).get("cells", sheet.get("cells", []))
	material.set_shader_parameter("u_map", _package.texture(sheet.get("atlas", "")))
	_plant_windows(sheet)
	if _has_laid:
		_orient(_laid_basis)
	# The viewer leaves the ellipses where they were; a look that changes a
	# plant's box changes its contact width too, so they are re-laid here.
	_lay_shadows()

func _same_basis(basis: Basis) -> bool:
	if not _has_laid:
		return false
	return _laid_basis.x.is_equal_approx(basis.x) \
		and _laid_basis.y.is_equal_approx(basis.y) \
		and _laid_basis.z.is_equal_approx(basis.z)

static func _basis_of(world) -> Basis:
	# Before the first frame the camera has not published a basis; the yaw the
	# world carries plus the manifest's pitch is the same rig.
	var yaw := float(Pieces.field(world, "camera_yaw", 0.0))
	var pitch := 0.9599310886
	var manifest = Pieces.field(world, "manifest", null)
	if manifest is Dictionary:
		var camera: Dictionary = (manifest as Dictionary).get("camera", {})
		pitch = deg_to_rad(float(camera.get("pitch_degrees", 55.0)))
	var offset := Vector3(sin(yaw) * cos(pitch), sin(pitch), cos(yaw) * cos(pitch))
	return Transform3D().looking_at(-offset, Vector3.UP).basis

## The contact ellipse, drawn here: three stacked linear falloffs whose sum
## reaches zero exactly at the quad's edge (`shadowTexture`, index.html
## :2788-2807). Colour is black; only the alpha is the shape.
static func shadow_texture(size: int = SHADOW_TEXTURE_PX) -> ImageTexture:
	var image := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var centre := float(size - 1) * 0.5
	for y in size:
		for x in size:
			var t := Vector2(float(x) - centre, float(y) - centre).length() / centre
			image.set_pixel(x, y, Color(0.0, 0.0, 0.0, shadow_profile(t)))
	return ImageTexture.create_from_image(image)

static func shadow_profile(t: float) -> float:
	var alpha := 0.0
	for i in SHADOW_SPREAD.size():
		var edge: float = SHADOW_SPREAD[i]
		if t < edge:
			alpha += float(SHADOW_ALPHA[i]) * (1.0 - t / edge)
	return minf(1.0, alpha)
