class_name Shadows
extends Node3D

## The contact shadows: one flat ellipse under every card that the package says
## needs one.
##
## A port of `shadowProfile` / `shadowTexture` (viewer :297, :2788),
## `buildShadows` / `shadowPool` (:3742, :3755) and `syncShadows` (:5035).
##
## Three stacked ellipses are baked once into a single 128² radial ALPHA map, so
## five hundred entities cost five hundred quads and not fifteen hundred; the
## stack reaches zero exactly at the quad's edge, because a spread past the edge
## left a visible step that read as a stain with a rim (viewer :290-291).
##
## Two pools, one strength each. The props' pool follows the package's seam
## policy (`manifest.ground_contact`): a skirt or a painted base already carries
## part of the seam, so the ellipse steps back. Actors get their own pool at
## full strength — a thing that moves can be handed no skirt laid at layout time
## and no patch painted into its cutout, so the shadow is its whole seam, and
## `actors.<id>.ground_contact` says so.
##
## This module reads only the manifest, the world and `Cards`'s static layout
## maths, so it needs no handle on the card module.

## The stack, and how much of the seam each authored contact wants (viewer
## :292-296).
const SHADOW_SPREAD := [1.0, 0.6, 0.22]
const SHADOW_ALPHA := [0.20, 0.30, 0.42]
const SHADOW_STRENGTH := {"shadow": 1.0, "skirt_decal": 0.6, "painted_base": 0.3, "none": 0.0}
## Just clear of the ground plate (viewer :167).
const SHADOW_Y := 0.006
## Under the cards, over the decals: the viewer's `ORDER.shadow` (:187).
const SHADOW_PRIORITY := 2
const TEXTURE_SIZE := 128
const SHADOW_SHADER := "res://view/shaders/shadow.gdshader"

var package: Variant = null
var manifest: Dictionary = {}

var _props_pool: MultiMeshInstance3D = null
var _actors_pool: MultiMeshInstance3D = null
var _look: String = ""
## prop_id -> state -> the ellipse half-width in metres, for the look now
## drawn. Dropped when the look turns.
var _prop_half: Dictionary = {}
## The (x, z, half) each pool instance was last laid with, three floats an
## index, so a standing prop is never rewritten.
var _laid_props := PackedFloat32Array()
var _laid_actors := PackedFloat32Array()
## `"<item_id>"` -> the ellipse half-width in metres.
var _item_half: Dictionary = {}
## `blend.shadow_scale` and `blend.shadow_strength` (run: 1.4 and 0.7).
var _scale: float = 1.0


func setup(pkg, world, _fu) -> void:
	package = pkg
	manifest = pkg.manifest
	_look = String(Cards.field(world, "look", ""))
	var blend: Dictionary = manifest.get("ground", {}).get("splat", {}).get("blend", {})
	_scale = float(blend.get("shadow_scale", 1.0)) if blend.get("shadow_scale") != null else 1.0
	var strength := float(blend.get("shadow_strength", 1.0)) if blend.get("shadow_strength") != null else 1.0
	var texture := ImageTexture.create_from_image(shadow_image(TEXTURE_SIZE))

	# One ellipse per placed entity, plus room for drops and built fires: a pool
	# sized to a fixed number silently stopped at the 2049th prop (viewer :3074).
	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else manifest.get("layout", {})
	var placed: int = (layout.get("entities", []) as Array).size()
	_props_pool = _pool(maxi(512, placed + 512), String(manifest.get("ground_contact", "shadow")), strength, texture)
	var actor_seam := "shadow"
	var actors: Dictionary = manifest.get("actors", {})
	if not actors.is_empty():
		actor_seam = String((actors[actors.keys()[0]] as Dictionary).get("ground_contact", "shadow"))
	_actors_pool = _pool(64, actor_seam, strength, texture)
	# NAN never equals itself, so the first lay writes every instance.
	_laid_props.resize(_props_pool.multimesh.instance_count * 3)
	_laid_props.fill(NAN)
	_laid_actors.resize(_actors_pool.multimesh.instance_count * 3)
	_laid_actors.fill(NAN)


func update(world, _delta: float, _cam: Dictionary) -> void:
	var look := String(Cards.field(world, "look", ""))
	if look != _look:
		set_look(look)
	sync(world)


func set_look(look: String) -> void:
	if look == _look:
		return
	_look = look
	# The half-width table is per look, and a snow cap changes a card's width.
	_prop_half.clear()


func set_mode(mode: String) -> void:
	visible = mode != "gallery"


# --- the baked ellipse ------------------------------------------------------

## The three-ellipse stack at a normalised radius (viewer `shadowProfile`, :297).
static func shadow_profile(t: float) -> float:
	var alpha := 0.0
	for i in SHADOW_SPREAD.size():
		var edge: float = SHADOW_SPREAD[i]
		if t < edge:
			alpha += float(SHADOW_ALPHA[i]) * (1.0 - t / edge)
	return minf(1.0, alpha)


## The stack baked into a radial alpha map. Black with a profile in alpha, the
## way the viewer's canvas texture was (viewer :2788).
static func shadow_image(size: int = TEXTURE_SIZE) -> Image:
	var image := Image.create_empty(size, size, false, Image.FORMAT_RGBA8)
	var centre := float(size - 1) * 0.5
	for y in size:
		for x in size:
			var dx := float(x) - centre
			var dy := float(y) - centre
			var alpha := shadow_profile(sqrt(dx * dx + dy * dy) / centre)
			# The viewer rounds the profile into a byte before it ever reaches
			# the GPU; matching that keeps the two frames byte-comparable.
			image.set_pixel(x, y, Color(0.0, 0.0, 0.0, round(alpha * 255.0) / 255.0))
	return image


func _pool(capacity: int, ground_contact: String, strength: float, texture: Texture2D) -> MultiMeshInstance3D:
	var seam := float(SHADOW_STRENGTH.get(ground_contact, 1.0))
	var material := ShaderMaterial.new()
	material.shader = load(SHADOW_SHADER)
	material.set_shader_parameter("u_map", texture)
	material.set_shader_parameter("u_opacity", seam * strength)
	material.render_priority = SHADOW_PRIORITY
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE
	quad.surface_set_material(0, material)
	var multi := MultiMesh.new()
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.mesh = quad
	multi.instance_count = capacity
	multi.visible_instance_count = 0
	var node := MultiMeshInstance3D.new()
	node.multimesh = multi
	# The pool is one plane turned -90 degrees about X, so its local +y runs
	# along world -z and its local +z is up: exactly the viewer's pool node.
	node.transform = Transform3D(Basis(Vector3(1.0, 0.0, 0.0), -PI / 2.0), Vector3(0.0, SHADOW_Y, 0.0))
	# Godot sizes a MultiMesh's AABB from the mesh alone; without a custom one
	# covering the scattered instances the whole pool is culled as one object.
	var extent := float(manifest.get("ground", {}).get("size_meters", 256.0))
	node.custom_aabb = AABB(Vector3(-extent, -extent, -4.0), Vector3(extent * 2.0, extent * 2.0, 8.0))
	add_child(node)
	return node


# --- the per-frame lay ------------------------------------------------------

## Re-lay both pools from the world (viewer `syncShadows`, :5036).
## This runs once per entity per frame, so everything on the path is written
## flat: the fields are read straight off the Dictionary rather than through
## `Cards.field`, the kind is compared as a Variant rather than built into a
## String, and `_lay` writes a transform only when the instance's own (x, z,
## half) actually moved. A world of standing props therefore costs the walk and
## nothing else, and the drops and the mobs are the only transforms written.
func sync(world) -> void:
	var props := 0
	var actors := 0
	var props_mesh := _props_pool.multimesh
	var actors_mesh := _actors_pool.multimesh
	var props_cap := props_mesh.instance_count
	var actors_cap := actors_mesh.instance_count
	for entity: Variant in Cards.field(world, "entities", []):
		if not (entity is Dictionary):
			continue
		var e: Dictionary = entity
		var kind: Variant = e.get("kind", "")
		if kind == "prop":
			var half := _prop_half_width(e.get("prop_id", ""), e.get("state", ""))
			if half > 0.0 and props < props_cap:
				_lay(props_mesh, _laid_props, props, float(e.get("x", 0.0)), float(e.get("z", 0.0)), half)
				props += 1
		elif kind == "item":
			# The shadow stays on the ground and shrinks as the pickup rises.
			var half := _item_half_width(String(e.get("item_id", "")))
			half = half / (1.0 + float(e.get("y", 0.0)) * 2.0)
			if half > 0.0 and props < props_cap:
				_lay(props_mesh, _laid_props, props, float(e.get("x", 0.0)), float(e.get("z", 0.0)), half)
				props += 1
		elif kind == "forage":
			# Its contact is painted into the sheet cell, like the litter's.
			continue
		elif kind == "mob":
			if actors < actors_cap:
				_lay(
					actors_mesh, _laid_actors, actors,
					float(e.get("x", 0.0)), float(e.get("z", 0.0)),
					_actor_half_width(String(e.get("actor_id", ""))),
				)
				actors += 1
	var player: Variant = Cards.field(world, "player")
	var player_id := String(Cards.field(world, "player_id", ""))
	if player != null and player_id != "" and actors < actors_cap:
		_lay(
			actors_mesh, _laid_actors, actors,
			float(Cards.field(player, "x", 0.0)), float(Cards.field(player, "z", 0.0)),
			_actor_half_width(player_id),
		)
		actors += 1
	props_mesh.visible_instance_count = props
	actors_mesh.visible_instance_count = actors


## A flat ellipse, wider than deep, because a fifty-five degree view foreshortens
## the ground axis that runs away from the camera. The pool's local +y is world
## -z, so the z goes in negated — written as (x, z) every shadow landed mirrored
## across the x axis (viewer :5044-5049).
## `laid` holds the (x, z, half) each instance was last written with, three
## floats an index, so an instance that has not moved costs a comparison instead
## of a `set_instance_transform` and the `Basis` and `Transform3D` behind it.
func _lay(multi: MultiMesh, laid: PackedFloat32Array, index: int, x: float, z: float, half_width: float) -> void:
	var slot := index * 3
	if slot + 2 < laid.size():
		if laid[slot] == x and laid[slot + 1] == z and laid[slot + 2] == half_width:
			return
		laid[slot] = x
		laid[slot + 1] = z
		laid[slot + 2] = half_width
	var basis := Basis(
		Vector3(half_width * 2.4 * _scale, 0.0, 0.0),
		Vector3(0.0, half_width * 1.2 * _scale, 0.0),
		Vector3(0.0, 0.0, 1.0),
	)
	multi.set_instance_transform(index, Transform3D(basis, Vector3(x, -z, 0.0)))


## Two Dictionary hops rather than one formatted `"<prop>/<state>/<look>"` key:
## the string was built for every prop in the world, every frame. The table is
## per look and is dropped when the look turns.
func _prop_half_width(prop_id: Variant, state: Variant) -> float:
	var states: Variant = _prop_half.get(prop_id)
	if states is Dictionary:
		var cached: Variant = (states as Dictionary).get(state)
		if cached != null:
			return float(cached)
	else:
		states = {}
		_prop_half[prop_id] = states
	var half := 0.0
	var props: Dictionary = manifest.get("props", {})
	var prop: Variant = props.get(String(prop_id))
	if prop is Dictionary:
		var spec := Cards.state_spec(prop, String(state), _look)
		if not spec.is_empty():
			var authored := float((prop as Dictionary).get("shadow_width_meters", 0.0))
			half = 0.5 * (authored if authored != 0.0 else float(Cards.card_layout(spec)["width"]) * 0.5)
	(states as Dictionary)[state] = half
	return half


func _item_half_width(item_id: String) -> float:
	if _item_half.has(item_id):
		return _item_half[item_id]
	var half := 0.0
	var items: Dictionary = manifest.get("items", {})
	var spec: Variant = items.get(item_id)
	if spec is Dictionary:
		# `record.shadow = template.width * 0.9`, halved on the way in (:4999).
		half = float(Cards.card_layout(spec)["width"]) * 0.9 * 0.5
	_item_half[item_id] = half
	return half


func _actor_half_width(actor_id: String) -> float:
	var actors: Dictionary = manifest.get("actors", {})
	var actor: Variant = actors.get(actor_id)
	var width := 0.6
	if actor is Dictionary and float((actor as Dictionary).get("shadow_width_meters", 0.0)) != 0.0:
		width = float((actor as Dictionary)["shadow_width_meters"])
	return width * 0.5


## The instance counts both pools are showing, for a capture harness's log.
func debug_counts() -> String:
	return "props %d/%d actors %d/%d" % [
		_props_pool.multimesh.visible_instance_count, _props_pool.multimesh.instance_count,
		_actors_pool.multimesh.visible_instance_count, _actors_pool.multimesh.instance_count,
	]
