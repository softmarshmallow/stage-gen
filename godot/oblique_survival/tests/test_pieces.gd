extends RefCounted

## `view/pieces.gd` against the real run.
##
## What is worth asserting headlessly is the arithmetic the view does on the
## CPU: one instance per layout entry, the atlas window each entry resolves to
## (the cell's painted box, not the cell), the metric size that box and the
## cell's ruler give a piece, the layer the sheet lies at, and the transform a
## piece is laid with. The look of it is a windowed capture's job, not this
## suite's.
##
## Godot's dummy renderer keeps nothing a `MultiMesh` is handed — under
## `--headless`, `get_instance_transform` reads back identity and
## `get_instance_custom_data` reads back opaque black — so the assertions call
## the module's own `piece_transform` / `windows`, which are the exact values
## written into the MultiMesh a line later.

const NOON_YAW := PI / 4.0

func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "the run package opened"):
		return
	var layout: Dictionary = pkg.layout
	var manifest: Dictionary = pkg.manifest
	var fu := FrameUniforms.from_manifest(manifest, Vector2(1600, 900))
	var world := _world_stub(pkg)

	var pieces := Pieces.new()
	pieces.setup(pkg, world, fu)

	_check_only_forage(h, pieces, manifest, layout)
	_check_windows(h, pieces, manifest, layout)
	_check_size(h, pieces, manifest, layout)
	_check_layer(h, pieces, layout)
	_check_forage_visibility(h, pieces, world, layout)
	_check_forage_lift(h, pieces, world)

	pieces.free()

## One sheet of ground pieces, the forage, one instance per layout entry; no
## litter and no standing plants anywhere in the run (decision 0060).
func _check_only_forage(h: TestHarness, pieces, manifest: Dictionary, layout: Dictionary) -> void:
	var forage_entries: int = layout.get("forage", []).size()
	h.assert_true(forage_entries > 0, "the run lays forage")
	h.assert_true(not layout.has("clutter") and not layout.has("plants"), "the layout lays no litter and no plants")
	var ground: Dictionary = manifest["ground"]
	h.assert_true(not ground.has("clutter") and not ground.has("plants"), "the manifest carries no litter and no plant sheet")
	h.assert_eq(pieces.forage.count, forage_entries, "forage instances = layout.forage")
	h.assert_eq(pieces.forage.multimesh.instance_count, forage_entries, "the forage MultiMesh is that long")
	# Every cell is calibrated: a box, a ruler, an authored size, and the
	# drawing's own opinion beside it.
	for cell in ground["forage"]["cells"]:
		var c: Dictionary = cell
		h.assert_true(c.get("box") is Dictionary and float(c.get("px_per_meter", 0.0)) > 0.0
			and float(c.get("size_meters", 0.0)) > 0.0 and c.has("drawn_size_meters"),
			"forage cell %s is calibrated" % c.get("index"))
	# The floor: every piece is authored no smaller than the package minimum.
	var floor_units := float(manifest["scale"]["minimum_height_units"])
	for cell in ground["forage"]["cells"]:
		h.assert_true(float(cell["size_units"]) >= floor_units - 1e-9,
			"forage cell %s keeps the size floor" % cell["index"])

## The window is the cell's painted box in pixels from the image's top-left,
## straight through: Godot does not flip textures, so the viewer's
## `1 - (y + h)/height` is gone, and the box is inside its cell.
func _check_windows(h: TestHarness, pieces, manifest: Dictionary, layout: Dictionary) -> void:
	var spec: Dictionary = manifest["ground"]["forage"]
	var cells: Array = spec["cells"]
	var width := float(spec["width_px"])
	var height := float(spec["height_px"])
	var entry: Dictionary = layout["forage"][0]
	var cell: Dictionary = cells[int(entry["cell"]) % cells.size()]
	var box: Dictionary = cell["box"]
	var window: Color = pieces.forage.windows[0]
	h.assert_near(window.r, float(box["x"]) / width, 1e-6, "window x = box.x / width")
	h.assert_near(window.g, float(box["y"]) / height, 1e-6, "window y = box.y / height (not flipped)")
	h.assert_near(window.b, float(box["w"]) / width, 1e-6, "window w = box.w / width")
	h.assert_near(window.a, float(box["h"]) / height, 1e-6, "window h = box.h / height")
	h.assert_true(float(box["x"]) >= float(cell["x"]) and float(box["y"]) >= float(cell["y"])
		and float(box["x"]) + float(box["w"]) <= float(cell["x"]) + float(cell["w"])
		and float(box["y"]) + float(box["h"]) <= float(cell["y"]) + float(cell["h"]),
		"the box lies inside its cell")

## A piece is `box / px_per_meter` metres a side, times the entry's jitter, and
## its longest side at jitter 1 is the cell's authored size (within the two
## pixels of padding the box carries).
func _check_size(h: TestHarness, pieces, manifest: Dictionary, layout: Dictionary) -> void:
	var spec: Dictionary = manifest["ground"]["forage"]
	var cells: Array = spec["cells"]
	var entry: Dictionary = layout["forage"][0]
	var cell: Dictionary = cells[int(entry["cell"]) % cells.size()]
	var box: Dictionary = cell["box"]
	var per_meter := float(cell["px_per_meter"])
	var scale := float(entry.get("scale", 1.0))
	var expected_w := float(box["w"]) / per_meter * scale
	var expected_h := float(box["h"]) / per_meter * scale
	var transform: Transform3D = pieces.piece_transform(pieces.forage, 0, NOON_YAW)
	h.assert_near(transform.basis.x.length(), expected_w, 1e-5, "a piece is box.w / px_per_meter * scale wide")
	h.assert_near(transform.basis.y.length(), expected_h, 1e-5, "and box.h / px_per_meter * scale deep")
	var longest := maxf(float(box["w"]), float(box["h"])) / per_meter
	var pad := 2.0 * 2.0 / per_meter
	h.assert_true(absf(longest - float(cell["size_meters"])) <= pad + 1e-6,
		"the longest side at jitter 1 is the authored size (%.3f vs %.3f m)" % [longest, float(cell["size_meters"])])
	h.note("cell %d (%s) at scale %.3f is %.3f x %.3f m, authored %.3f, drawn %.3f" % [
		int(cell["index"]), String(cell.get("item_id", "")), scale, expected_w, expected_h,
		float(cell["size_meters"]), float(cell["drawn_size_meters"])])

## The layer, and the lay-flat transform `layPiece` builds.
func _check_layer(h: TestHarness, pieces, layout: Dictionary) -> void:
	h.assert_near(pieces.forage.y, 0.021, 1e-9, "forage lies at 0.021")
	var entry: Dictionary = layout["forage"][0]
	var transform: Transform3D = pieces.piece_transform(pieces.forage, 0, NOON_YAW)
	h.assert_near(transform.origin.x, float(entry["x"]), 1e-4, "a piece stands at its entry's x")
	h.assert_near(transform.origin.y, 0.021, 1e-6, "at the forage layer")
	h.assert_near(transform.origin.z, float(entry["z"]), 1e-4, "and its entry's z")
	# Laid flat: the quad's normal (its local +Z) points up.
	var normal: Vector3 = transform.basis.z.normalized()
	h.assert_near(normal.y, 1.0, 1e-5, "a laid piece faces up")
	# The image's bottom edge lands at (sin spin, 0, cos spin) — toward the
	# camera at this yaw, which is the whole reason the pieces re-orient.
	var spin: float = NOON_YAW + deg_to_rad(float(entry.get("rotation_degrees", 0.0)))
	var down: Vector3 = (transform.basis * Vector3(0.0, -1.0, 0.0)).normalized()
	h.assert_near(down.x, sin(spin), 1e-5, "the piece's lower edge points at sin(spin)")
	h.assert_near(down.z, cos(spin), 1e-5, "and cos(spin)")

## A picked or season-hidden forage piece is a zero-scale instance.
func _check_forage_visibility(h: TestHarness, pieces, world: Dictionary, layout: Dictionary) -> void:
	var entities: Array = world["entities"]
	if not h.assert_true(entities.size() > 0, "the stub world carries forage entities"):
		return
	var entity: Dictionary = entities[0]
	var index := int(entity["index"])
	var before: Transform3D = pieces.piece_transform(pieces.forage, index, NOON_YAW)
	h.assert_true(before.basis.x.length() > 0.0, "an unpicked forage piece is drawn")
	entity["picked"] = true
	pieces.update(world, 1.0 / 60.0, _cam())
	var after: Transform3D = pieces.piece_transform(pieces.forage, index, NOON_YAW)
	h.assert_near(after.basis.x.length(), 0.0, 1e-9, "a picked piece is a zero-scale instance")
	entity["picked"] = false
	pieces.update(world, 1.0 / 60.0, _cam())
	var back: Transform3D = pieces.piece_transform(pieces.forage, index, NOON_YAW)
	h.assert_near(back.basis.x.length(), before.basis.x.length(), 1e-9, "and comes back when it regrows")
	# `showAllForage` after a reset.
	entity["hidden"] = true
	pieces.update(world, 1.0 / 60.0, _cam())
	h.assert_near(pieces.piece_transform(pieces.forage, index, NOON_YAW).basis.x.length(), 0.0, 1e-9,
		"a season-hidden piece is hidden too")
	pieces.show_all_forage()
	h.assert_near(pieces.piece_transform(pieces.forage, index, NOON_YAW).basis.x.length(),
		before.basis.x.length(), 1e-9, "show_all_forage brings every piece back")
	entity["hidden"] = false
	h.assert_eq(layout["forage"].size(), pieces.forage.count, "and the sheet is still that long")

## The pointer's lift on the sheet: the hovered and the in-reach forage piece
## are handed to the material by instance index, and anything that is not a
## forage entity lifts nothing there. The sheet's material keeps its uniforms
## on the CPU side, so the dummy renderer reads them back.
func _check_forage_lift(h: TestHarness, pieces, world: Dictionary) -> void:
	var entities: Array = world["entities"]
	if not h.assert_true(entities.size() > 1, "the stub world carries two forage pieces to lift"):
		return
	var material: ShaderMaterial = pieces.forage.material
	# A uniform never set reads back null and means the shader's own -1.
	var lifts := func() -> Array:
		var a: Variant = material.get_shader_parameter("u_lift_a")
		var b: Variant = material.get_shader_parameter("u_lift_b")
		return [-1 if a == null else int(a), -1 if b == null else int(b)]
	h.assert_eq(pieces.lifted(), [-1, -1], "nothing is lifted before the pointer moves")
	h.assert_eq(lifts.call(), [-1, -1], "and the material says so")
	var first: Dictionary = entities[0]
	var second: Dictionary = entities[1]
	pieces.set_highlight(first)
	h.assert_eq(lifts.call(), [int(first["index"]), -1], "the hovered piece is lifted by its instance index")
	pieces.set_focus(second)
	h.assert_eq(lifts.call(), [int(first["index"]), int(second["index"])], "the piece in reach is lifted beside it")
	pieces.set_focus(first)
	h.assert_eq(lifts.call(), [int(first["index"]), int(first["index"])],
		"hover and focus on one piece is one lift twice, not a fight")
	pieces.set_highlight({"id": "pine-1", "kind": "prop", "x": 0.0, "z": 0.0})
	h.assert_eq(lifts.call(), [-1, int(first["index"])], "a tree under the pointer lifts nothing on the sheet")
	pieces.set_highlight({"id": "ghost", "kind": "forage", "index": 999999})
	h.assert_eq(pieces.forage_index({"kind": "forage", "index": 999999}), -1, "an index off the sheet is no piece")
	pieces.set_focus(null)
	pieces.set_highlight("")
	h.assert_eq(lifts.call(), [-1, -1], "and both let down")

func _cam() -> Dictionary:
	var pitch := deg_to_rad(55.0)
	var offset := Vector3(sin(NOON_YAW) * cos(pitch), sin(pitch), cos(NOON_YAW) * cos(pitch))
	var basis: Basis = Transform3D().looking_at(-offset, Vector3.UP).basis
	return {
		"yaw": NOON_YAW, "basis": basis, "position": offset * 18.0, "target": Vector3.ZERO,
		"changed": false, "pixel_ratio": 1.0, "resolution": Vector2(1600, 900),
	}

## The camera yaw and the forage flags: everything the module reads of a world.
func _world_stub(pkg) -> Dictionary:
	var entities: Array = []
	var cells: Array = pkg.manifest["ground"]["forage"]["cells"]
	var forage: Array = pkg.layout.get("forage", [])
	for index in forage.size():
		var cell: Dictionary = cells[int(forage[index].get("cell", 0)) % cells.size()]
		if String(cell.get("item_id", "")) == "":
			continue
		entities.append({
			"id": "f%d" % index, "kind": "forage", "index": index,
			"picked": false, "hidden": false, "dirty": false,
		})
	return {
		"camera_yaw": NOON_YAW, "look": "", "time": 0.0,
		"manifest": pkg.manifest, "entities": entities,
	}
