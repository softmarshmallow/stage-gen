class_name Gallery
extends Node3D

## Gallery mode: the layout is ignored and every asset in the package stands in
## a row at true relative scale, beside a post as tall as the player.
##
## A port of `galleryRows` (viewer :392) and `buildGallery` (:5082). One row per
## actor (its concept first, then every state, and every facing of a four-way
## state), then one row per prop FAMILY (every state of every prop in it), then
## one row of items. Cells are laid left to right with a fixed 0.55 m gutter
## between card edges; rows are 5 m apart.
##
## The viewer's labels are DOM elements projected onto the canvas each frame
## (:5712-5720). Here they are `Label3D`s parented to what they name, which is
## the same information with no HUD dependency and no per-frame projection.

## The bone tone of the ruler post (viewer :5089).
const POST_COLOUR := Color(0xf0 / 255.0, 0xc8 / 255.0, 0x87 / 255.0)
const POST_WIDTH := 0.06
const POST_X := -1.8
const GUTTER := 0.55
const ROW_PITCH := 5.0
## Where gallery mode puts the camera target on entry (viewer :5138).
const CAMERA_TARGET := Vector3(5.0, 0.0, 5.0)

var package: Variant = null
var manifest: Dictionary = {}
var uniforms: Variant = null

var _cards: Cards = null
var _built: bool = false
var _mode: String = "play"
## The viewer's labels are DOM elements over the canvas; here they are `Label3D`s
## in the scene, so they land inside a captured frame where the viewer's never
## did. A capture that compares against a reference frame turns them off.
var _labels: bool = true


func setup(pkg, _world, fu) -> void:
	package = pkg
	manifest = pkg.manifest
	uniforms = fu
	# `Cards` owns the material and mesh maths; gallery mode only arranges what
	# it makes, so it borrows one instance rather than copying the builders.
	_cards = Cards.new()
	_cards.name = "GalleryCards"
	add_child(_cards)
	_cards.setup(pkg, null, fu)
	_cards.visible = false
	visible = false


func update(_world, _delta: float, _cam: Dictionary) -> void:
	pass


## Show or hide every label. The reference gallery frame is the WebGL canvas
## alone -- the viewer's labels were DOM elements over it -- so a capture that
## diffs against one calls this with `false` first.
func set_labels(on: bool) -> void:
	_labels = on
	for label: Label3D in find_children("*", "Label3D", true, false):
		label.visible = on


## `Main.set_overlays` reaches every module carrying something the viewer drew
## in the DOM rather than on the canvas; the gallery's labels are that one case,
## so the frame owner's overlay switch is what turns them off. Called before
## `set_mode` builds the rows, so the labels are born hidden.
func set_overlays(on: bool) -> void:
	set_labels(on)


func set_mode(mode: String) -> void:
	_mode = mode
	if mode == "gallery":
		if not _built:
			build()
		visible = true
	else:
		visible = false
		if _built:
			tear_down()


# --- the rows ---------------------------------------------------------------

## One row per family, every asset at true relative scale (viewer `galleryRows`).
static func rows(manifest: Dictionary) -> Array:
	var out: Array = []
	var actors: Dictionary = manifest.get("actors", {})
	for id: String in actors.keys():
		var actor: Dictionary = actors[id]
		var cells: Array = []
		if actor.get("still") is Dictionary:
			cells.append({"kind": "still", "actor": id, "label": "%s concept" % id})
		var states: Dictionary = actor.get("states", {})
		for state: String in states.keys():
			var spec: Dictionary = states[state]
			if spec.get("facings") is Dictionary:
				for facing: String in (spec["facings"] as Dictionary).keys():
					cells.append({
						"kind": "actor", "actor": id, "state": state, "facing": facing,
						"label": "%s %s %s" % [id, state, facing],
					})
			else:
				cells.append({"kind": "actor", "actor": id, "state": state, "label": "%s %s" % [id, state]})
		if not cells.is_empty():
			out.append({"title": "%s %sm" % [id, actor.get("height_meters", 0)], "cells": cells})
	var by_family: Dictionary = {}
	var order: Array = []
	var props: Dictionary = manifest.get("props", {})
	for id: String in props.keys():
		var prop: Dictionary = props[id]
		var family := String(prop.get("family", ""))
		if not by_family.has(family):
			by_family[family] = []
			order.append(family)
		for state: String in (prop.get("states", {}) as Dictionary).keys():
			(by_family[family] as Array).append({
				"kind": "prop", "prop": id, "state": state, "label": "%s %s" % [id, state],
			})
	for family: String in order:
		out.append({"title": family, "cells": by_family[family]})
	var items: Array = []
	for id: String in (manifest.get("items", {}) as Dictionary).keys():
		items.append({"kind": "item", "item": id, "label": id})
	if not items.is_empty():
		out.append({"title": "items", "cells": items})
	return out


func build() -> void:
	if _built:
		return
	_built = true
	var height := float(manifest.get("scale", {}).get("player_height_meters", 1.7))
	var z := 0.0
	for row: Dictionary in rows(manifest):
		_post(height, z, "%s  |  ruler %s m" % [row["title"], height])
		var x := 0.0
		for cell: Dictionary in row["cells"]:
			var found := _cell_spec(cell)
			if found.is_empty():
				continue
			var spec: Dictionary = found["spec"]
			var columns := int(found["columns"])
			var layout := Cards.card_layout(spec, columns)
			var material := _cards.card_material(
				package.texture(String(spec.get("atlas", spec.get("image", "")))),
				bool(found["soft"]),
			)
			if columns > 1:
				material.set_shader_parameter("u_frame_uv", Cards.frame_uv(0, columns, 1))
			var node := MeshInstance3D.new()
			var mesh := Cards.card_mesh(float(layout["width"]), float(layout["height"]), float(layout["foot"]))
			mesh.surface_set_material(0, material)
			node.mesh = mesh
			node.extra_cull_margin = maxf(float(layout["width"]), float(layout["height"]))
			x += float(layout["width"]) / 2.0 + GUTTER
			_label(node, String(cell["label"]))
			_stand(node, Vector3(x, 0.0, z))
			x += float(layout["width"]) / 2.0
		z += ROW_PITCH


func tear_down() -> void:
	if not _built:
		return
	_built = false
	for child in get_children():
		if child == _cards:
			continue
		remove_child(child)
		child.queue_free()


func _cell_spec(cell: Dictionary) -> Dictionary:
	var kind := String(cell["kind"])
	var spec: Variant = null
	var soft := false
	var columns := 1
	if kind == "prop":
		var prop: Dictionary = manifest["props"][cell["prop"]]
		spec = (prop.get("states", {}) as Dictionary).get(cell["state"])
		soft = String(prop.get("edge", "hard")) == "soft"
	elif kind == "actor":
		spec = (manifest["actors"][cell["actor"]]["states"] as Dictionary).get(cell["state"])
		if cell.has("facing") and spec is Dictionary and (spec as Dictionary).get("facings") is Dictionary:
			spec = ((spec as Dictionary)["facings"] as Dictionary).get(cell["facing"])
		if spec is Dictionary:
			columns = int((spec as Dictionary).get("columns", 1))
	elif kind == "still":
		spec = (manifest["actors"][cell["actor"]] as Dictionary).get("still")
	elif kind == "item":
		spec = (manifest["items"] as Dictionary).get(cell["item"])
	if not (spec is Dictionary):
		return {}
	return {"spec": spec, "soft": soft, "columns": columns}


## The ruler: a bone-coloured post exactly as tall as the player, so every card
## beside it is read at true scale.
func _post(height: float, z: float, title: String) -> void:
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = POST_COLOUR
	# `faceCamera(post)` (viewer :5093): the ruler stands square to the camera
	# like every card beside it, so it is read at the same scale. Without it the
	# post is a plane in the world's XZ frame and the fifty-five degree pitch
	# foreshortens it to four fifths of the height it is measuring.
	material.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	var mesh := Cards.card_mesh(POST_WIDTH, height, 1.0)
	mesh.surface_set_material(0, material)
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.extra_cull_margin = height
	_label(node, title)
	_stand(node, Vector3(POST_X, 0.0, z))


## Stand one gallery piece, label and all, and hand its transform to the
## rendering server: the row is built inside `set_mode`, which a capture calls
## between two engine frames, and the scene tree flushes transform
## notifications at the top of a frame -- so without this every card in the
## gallery draws at the world origin. Same rule as `Cards._attach`.
func _stand(node: Node3D, position: Vector3) -> void:
	node.position = position
	add_child(node)
	if not node.is_inside_tree():
		return
	node.force_update_transform()
	for child: Node3D in node.find_children("*", "Node3D", true, false):
		child.force_update_transform()


func _label(owner_node: Node3D, text: String) -> void:
	var label := Label3D.new()
	label.text = text
	label.visible = _labels
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.fixed_size = true
	label.pixel_size = 0.0003
	label.modulate = Color(0.92, 0.88, 0.80)
	label.outline_modulate = Color(0.09, 0.08, 0.07)
	label.outline_size = 8
	label.position = Vector3(0.0, -0.25, 0.0)
	owner_node.add_child(label)
