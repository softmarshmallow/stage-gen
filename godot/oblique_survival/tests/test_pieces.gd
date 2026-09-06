extends RefCounted

## `view/pieces.gd`, `view/plants.gd`, `view/leaves.gd` against the real run.
##
## What is worth asserting headlessly is the arithmetic the viewer does on the
## CPU: one instance per layout entry, the atlas window each entry resolves to,
## the metric size a plant's cell box gives it, the layer each sheet lies at,
## and the transform a piece is laid with. The look of it is a windowed
## capture's job, not this suite's.
##
## Godot's dummy renderer keeps nothing a `MultiMesh` is handed — under
## `--headless`, `get_instance_transform` reads back identity and
## `get_instance_custom_data` reads back opaque black — so the assertions call
## the modules' own `piece_transform` / `plant_transform` / `windows`, which are
## the exact values written into the MultiMesh a line later.

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
	var plants := Plants.new()
	plants.setup(pkg, world, fu)
	var leaves := Leaves.new()
	leaves.setup(pkg, world, fu)

	_check_counts(h, pieces, plants, leaves, layout)
	_check_windows(h, pieces, manifest, layout)
	_check_plant_size(h, plants, manifest, layout)
	_check_layers(h, pieces, plants, layout)
	_check_forage_visibility(h, pieces, world, layout)
	_check_forage_lift(h, pieces, world)
	_check_leaves(h, leaves, manifest)

	pieces.free()
	plants.free()
	leaves.free()

## One instance per layout entry, for all three sheets and the plant shadows.
func _check_counts(h: TestHarness, pieces, plants, leaves, layout: Dictionary) -> void:
	var clutter_entries: int = layout.get("clutter", []).size()
	var forage_entries: int = layout.get("forage", []).size()
	var plant_entries: int = layout.get("plants", []).size()
	h.assert_true(clutter_entries > 0 and forage_entries > 0 and plant_entries > 0,
		"the run lays clutter, forage and plants")
	h.assert_eq(pieces.clutter.count, clutter_entries, "clutter instances = layout.clutter")
	h.assert_eq(pieces.clutter.multimesh.instance_count, clutter_entries, "the clutter MultiMesh is that long")
	h.assert_eq(pieces.forage.count, forage_entries, "forage instances = layout.forage")
	h.assert_eq(pieces.forage.multimesh.instance_count, forage_entries, "the forage MultiMesh is that long")
	h.assert_eq(plants.count, plant_entries, "plant instances = layout.plants")
	h.assert_eq(plants.multimesh.instance_count, plant_entries, "the plant MultiMesh is that long")
	h.assert_eq(plants.shadow_multimesh.instance_count, plant_entries, "one contact ellipse per plant")
	h.assert_eq(plants.shadow_multimesh.visible_instance_count, plant_entries, "every ellipse is drawn")
	h.assert_eq(leaves.multimesh.instance_count, Leaves.CAPACITY, "the leaf pool is 96 slots")

## The window is the cell's pixels from the image's top-left, straight through:
## Godot does not flip textures, so the viewer's `1 - (y + h)/height` is gone.
func _check_windows(h: TestHarness, pieces, manifest: Dictionary, layout: Dictionary) -> void:
	var spec: Dictionary = manifest["ground"]["clutter"]
	var cells: Array = spec["cells"]
	var width := float(spec["width_px"])
	var height := float(spec["height_px"])
	var entry: Dictionary = layout["clutter"][0]
	var cell: Dictionary = cells[int(entry["cell"]) % cells.size()]
	var window: Color = pieces.clutter.windows[0]
	h.assert_near(window.r, float(cell["x"]) / width, 1e-6, "window x = cell.x / width")
	h.assert_near(window.g, float(cell["y"]) / height, 1e-6, "window y = cell.y / height (not flipped)")
	h.assert_near(window.b, float(cell["w"]) / width, 1e-6, "window w = cell.w / width")
	h.assert_near(window.a, float(cell["h"]) / height, 1e-6, "window h = cell.h / height")

## `plantWindows` (index.html :3588-3602):
## `metersPerPx = cell_meters / (width_px / columns)`, and the card is
## `cell.w * metersPerPx * entry.scale` by `cell.h * metersPerPx * entry.scale`.
func _check_plant_size(h: TestHarness, plants, manifest: Dictionary, layout: Dictionary) -> void:
	var spec: Dictionary = manifest["ground"]["plants"]
	var cells: Array = spec["cells"]
	var width := float(spec["width_px"])
	var columns := float(spec["columns"])
	var meters_per_px := float(spec["cell_meters"]) / maxf(1.0, width / columns)
	# The first entry that uses cell 0, so the assertion names a real cell box.
	var index := -1
	for i in layout["plants"].size():
		if int(layout["plants"][i].get("cell", -1)) % cells.size() == 0:
			index = i
			break
	if not h.assert_true(index >= 0, "some plant uses cell 0"):
		return
	var entry: Dictionary = layout["plants"][index]
	var cell: Dictionary = cells[0]
	var scale := float(entry.get("scale", 1.0))
	var expected_w := float(cell["w"]) * meters_per_px * scale
	var expected_h := float(cell["h"]) * meters_per_px * scale
	var basis: Basis = plants.plant_transform(index, _cam()["basis"]).basis
	h.assert_near(basis.x.length(), expected_w, 1e-4, "the plant card is cell.w metres wide")
	h.assert_near(basis.y.length(), expected_h, 1e-4, "the plant card is cell.h metres tall")
	h.note("cell 0 at scale %.3f is %.4f x %.4f m" % [scale, expected_w, expected_h])

	# Its foot is on the ground: the centre sits half the height up the card's
	# own axis, so the lowest point of the quad is y = 0.
	var transform: Transform3D = plants.plant_transform(index, _cam()["basis"])
	var foot: Vector3 = transform.origin - transform.basis.y * 0.5
	h.assert_near(foot.y, 0.0, 1e-4, "the plant's foot is on the ground plane")
	h.assert_near(foot.x, float(entry["x"]), 1e-4, "and stands at the entry's x")
	h.assert_near(foot.z, float(entry["z"]), 1e-4, "and at the entry's z")

## The Y stack, and the lay-flat transform `layPiece` builds.
func _check_layers(h: TestHarness, pieces, plants, layout: Dictionary) -> void:
	h.assert_near(pieces.clutter.y, 0.018, 1e-9, "clutter lies at 0.018")
	h.assert_near(pieces.forage.y, 0.021, 1e-9, "forage lies at 0.021")
	var entry: Dictionary = layout["clutter"][0]
	var transform: Transform3D = pieces.piece_transform(pieces.clutter, 0, NOON_YAW)
	h.assert_near(transform.origin.x, float(entry["x"]), 1e-4, "a piece stands at its entry's x")
	h.assert_near(transform.origin.y, 0.018, 1e-6, "at the clutter layer")
	h.assert_near(transform.origin.z, float(entry["z"]), 1e-4, "and its entry's z")
	# Laid flat: the quad's normal (its local +Z) points up.
	var normal: Vector3 = transform.basis.z.normalized()
	h.assert_near(normal.y, 1.0, 1e-5, "a laid piece faces up")
	# Square by cell_meters * entry.scale, never by the cell's aspect.
	var size := 0.42 * float(entry.get("scale", 1.0))
	h.assert_near(transform.basis.x.length(), size, 1e-5, "a piece is cell_meters * scale wide")
	h.assert_near(transform.basis.y.length(), size, 1e-5, "and as deep")
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

## The leaves are the litter sheet's `fallen` cells, and they fly.
func _check_leaves(h: TestHarness, leaves, manifest: Dictionary) -> void:
	var spec: Dictionary = manifest["ground"]["clutter"]
	var fallen := 0
	for cell in spec["cells"]:
		if String(cell.get("contact", "")) == "fallen":
			fallen += 1
	h.assert_eq(leaves._windows.size(), fallen, "one window per `fallen` cell")
	h.assert_near(leaves._size, float(spec["cell_meters"]) * Leaves.SIZE_SCALE, 1e-9,
		"a leaf is 0.55 of a litter cell")
	leaves.spawn_leaves(3.0, -2.0, 0.0, {"count": 5, "top": 4.0, "bottom": 2.0, "spread": 0.8})
	var live := 0
	var within := 0
	for leaf in leaves._live:
		if leaf == null:
			continue
		live += 1
		if leaf["y"] >= 2.0 and leaf["y"] <= 4.0 and leaf["landed"] < 0.0:
			within += 1
	h.assert_eq(live, 5, "five leaves left the crown")
	h.assert_eq(within, 5, "each between `bottom` and `top`, and airborne")
	var stub := {"time": 0.25, "camera_yaw": NOON_YAW, "manifest": manifest}
	leaves.update(stub, 0.25, _cam())
	var falling := 0
	for leaf in leaves._live:
		if leaf != null and leaf["landed"] < 0.0 and leaf["y"] > 0.01:
			falling += 1
	h.assert_eq(falling, 5, "and all five are still falling a quarter second later")
	# Six seconds after they land the pool is empty again.
	for step in 40:
		leaves.update({"time": 0.25 + float(step + 1) * 0.5, "camera_yaw": NOON_YAW}, 0.5, _cam())
	var left := 0
	for leaf in leaves._live:
		if leaf != null:
			left += 1
	h.assert_eq(left, 0, "and the pool takes every slot back")

func _cam() -> Dictionary:
	var pitch := deg_to_rad(55.0)
	var offset := Vector3(sin(NOON_YAW) * cos(pitch), sin(pitch), cos(NOON_YAW) * cos(pitch))
	var basis: Basis = Transform3D().looking_at(-offset, Vector3.UP).basis
	return {
		"yaw": NOON_YAW, "basis": basis, "position": offset * 18.0, "target": Vector3.ZERO,
		"changed": false, "pixel_ratio": 1.0, "resolution": Vector2(1600, 900),
	}

## Enough of a world for these modules: the camera yaw, the look, and the
## forage entities they read. Duck-typed, exactly as the modules are.
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
