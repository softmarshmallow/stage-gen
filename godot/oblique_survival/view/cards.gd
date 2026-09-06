class_name Cards
extends Node3D

## Every standing picture in the world: props, mobs, the player, dropped items,
## the trunk that is falling and the card that is still rocking from a blow.
##
## A port of the viewer's card half — `cardGeometry` / `cardLayout` (:2886,
## :264), `propTemplate` (:3860), `actorRecord` / `setActorFrame` (:3889),
## `itemTemplate` (:3228), `syncEntities` (:4972), `shake` (:3089), `fell`
## (:3098) and the per-frame settle and fall at :5626-5665.
##
## Two conventions differ from three.js and are handled once, here:
##
##   * Godot does not flip textures. An atlas window given in pixels from the
##     image's top-left is `(x/W, y/H, w/W, h/H)`; the viewer's flipY
##     compensation `1 - (row + 1)/rows` is NOT carried over. See `frame_uv`.
##   * A `QuadMesh` has UV.y = 0 at the top, where three's `PlaneGeometry` had
##     v = 0 at the foot. The shader's sway term compensates; the geometry does
##     not need to (the foot offset is the same number either way).
##
## The card geometry, the layout maths and the playback rules are static, so
## `Shadows`, `Decals` and `Gallery` read them from here rather than keeping a
## second copy.

## Hard-edged art is alpha-tested here and then forced opaque (viewer :153).
const ALPHA_CUTOFF := 0.5
## Shared with the simulation: the yield lands when the crown does (viewer :165).
const FALL_SECONDS := 1.1
## `{ none: 0, sway_top: 1, bob: 2, flicker: 3 }` (viewer :2894).
const SWAY_MODES := {"none": 0.0, "sway_top": 1.0, "bob": 2.0, "flicker": 3.0}

const CARD_SHADER := "res://view/shaders/card.gdshader"
const CARD_SOFT_SHADER := "res://view/shaders/card_soft.gdshader"
const CARD_BLEND_SHADER := "res://view/shaders/card_blend.gdshader"

## Where a fading card sits in the transparent pass. Decals are 1 and the
## contact shadows 2, mirroring the viewer's `ORDER` (:187); a faller is a card,
## so it draws after both.
const FALLER_PRIORITY := 3

## Emitted when a falling trunk's crown reaches the ground, with the point the
## impact happened at. The dust, the leaves and the camera's kick are the FX and
## camera modules' business (viewer :5641-5651), and only this module knows the
## card's height and when the fall ends.
signal faller_landed(x: float, z: float, height: float)

var package: Variant = null
var manifest: Dictionary = {}
var uniforms: Variant = null

## `"<prop_id>/<state>/<look or empty>"` -> a template Dictionary.
var _prop_templates: Dictionary = {}
## `"<item_id>"` -> a template Dictionary.
var _item_templates: Dictionary = {}
## entity id -> a record Dictionary.
var _records: Dictionary = {}
var _player_record: Variant = null
var _player_id: String = ""
## entity id -> `{start, sign, strength}`.
var _shakes: Dictionary = {}
## `[entity, record]` for every record that is not a prop — the mobs and the
## dropped items, the only cards whose transform is rewritten every frame.
var _movers: Array = []
## Set whenever a record is created or dropped; `_movers` is rebuilt on the
## next frame that needs it.
var _movers_stale: bool = true
var _fallers: Array = []
var _look: String = ""
var _mode: String = "play"
## The entity id the pointer is over, whose card is lifted (`u_highlight`), or
## "". Re-applied every frame, because a card that was rebuilt (a state change,
## a season) comes back without its override.
var _highlight_id: String = ""
## Template material instance id -> its lifted twin, made once per template
## the pointer has ever rested on and registered for the frame uniforms.
var _lifted: Dictionary = {}
## Texture instance id -> a small copy of its picture, for the pick's alpha
## test. Read back from the GPU once per texture the pointer has crossed.
var _pick_images: Dictionary = {}
## The camera yaw as of the last `update`; an event arriving before the first
## frame is signed with it.
var _yaw: float = 0.0
var _time: float = 0.0


# --- the module contract ---------------------------------------------------

func setup(pkg, world, fu) -> void:
	package = pkg
	manifest = pkg.manifest
	uniforms = fu
	_look = String(field(world, "look", ""))
	_player_id = String(field(world, "player_id", ""))
	sync_entities(world)


func update(world, delta: float, cam: Dictionary) -> void:
	_yaw = float(cam.get("yaw", _yaw))
	_time = float(field(world, "time", _time))
	if _mode == "gallery":
		return
	var look := String(field(world, "look", ""))
	if look != _look:
		set_look(look)
	sync_entities(world)
	_update_player(world)
	_update_entities(world)
	_update_shakes()
	_update_fallers(delta)
	_apply_highlight()


## The frame owner offers every drained event to every module. Only two land
## here: a blow rocks the card it struck, and a felled tree detaches its trunk.
func handle_event(event: Dictionary) -> void:
	var type := String(event.get("type", ""))
	if type == "hit":
		_on_hit(event)
	elif type == "fell":
		_on_fell(event)


## The season turned: every prop card swaps to `looks.<look>` where the state
## has one, and keeps its summer picture where it does not.
func set_look(look: String) -> void:
	if look == _look:
		return
	_look = look
	for id: String in _records.keys():
		var record: Dictionary = _records[id]
		if record.get("kind", "") == "prop":
			record["stale"] = true


func set_mode(mode: String) -> void:
	_mode = mode
	visible = mode != "gallery"


# --- pure helpers, shared with Shadows, Decals and Gallery ------------------

## Read a field from a simulation entity (a Dictionary) or the player (an
## Object), so this module does not care which the simulation chose.
static func field(holder: Variant, key: String, fallback: Variant = null) -> Variant:
	if holder is Dictionary:
		return (holder as Dictionary).get(key, fallback)
	if holder is Object:
		var value: Variant = (holder as Object).get(key)
		return fallback if value == null else value
	return fallback


## Card size in metres and where the foot row sits inside the image
## (viewer `cardLayout`, :264). Size is pixels / `px_per_meter`; the foot is
## `bottom_gutter_px` for an actor strip, `ground_contact_y_normalized` for a
## prop or an item, and the image's bottom row when the package says neither.
static func card_layout(spec: Dictionary, columns: int = 1) -> Dictionary:
	var cell_width: float = float(spec["cell_width"]) if spec.get("cell_width") != null else float(spec.get("width_px", 0))
	var cell_height: float = float(spec["cell_height"]) if spec.get("cell_height") != null else float(spec.get("height_px", 0))
	var per_meter := float(spec.get("px_per_meter", 1.0))
	if per_meter == 0.0:
		per_meter = 1.0
	var foot := 1.0
	if spec.get("bottom_gutter_px") != null and cell_height != 0.0:
		foot = 1.0 - float(spec["bottom_gutter_px"]) / cell_height
	elif spec.get("ground_contact_y_normalized") != null:
		foot = float(spec["ground_contact_y_normalized"])
	return {
		"width": cell_width / per_meter,
		"height": cell_height / per_meter,
		"foot": foot,
		"columns": columns,
	}


## The UV window of one cell, in reading order, in GODOT's convention: the
## origin is the image's top-left and V grows downward, so a cell's row index
## is its row directly. The viewer's `1 - (row + 1)/rows` (:279) is three's
## flipY compensation and must not be copied.
static func frame_uv(index: int, columns: int, rows: int) -> Vector4:
	var cols := maxi(1, columns)
	var num_rows := maxi(1, rows)
	var column := index % cols
	@warning_ignore("integer_division")
	var row := int(index / cols)
	return Vector4(float(column) / float(cols), float(row) / float(num_rows), 1.0 / float(cols), 1.0 / float(num_rows))


## Which frame of a strip is showing (viewer `motionFrame`, :247). Pure.
## Returns `{frame: int, done: bool}`.
static func motion_frame(playback: Dictionary, elapsed_seconds: float, progress: float = 0.0) -> Dictionary:
	var indices: Array = playback.get("canonical_frame_indices", [0])
	if indices.is_empty():
		indices = [0]
	var n := indices.size()
	var mode := String(playback.get("mode", "loop"))
	if mode == "hold" or n == 1:
		return {"frame": int(indices[0]), "done": true}
	if mode == "gameplay_driven":
		var step := mini(n - 1, maxi(0, int(floor(progress * float(n)))))
		return {"frame": int(indices[step]), "done": progress >= 1.0}
	var fps := float(playback.get("fps", 8.0))
	if fps == 0.0:
		fps = 8.0
	var advanced := elapsed_seconds * fps
	if mode == "once":
		var step := mini(n - 1, int(floor(maxf(0.0, advanced))))
		return {"frame": int(indices[step]), "done": advanced >= float(n)}
	var wrapped := int(floor(maxf(0.0, advanced))) % n
	return {"frame": int(indices[wrapped]), "done": false}


## The world direction that runs along the screen's right edge (viewer :2932).
static func screen_right(yaw: float) -> Vector2:
	return Vector2(cos(yaw), -sin(yaw))


## How far right of screen centre a world direction points (viewer :1020).
static func screen_right_component(x: float, z: float, yaw: float) -> float:
	return x * cos(yaw) - z * sin(yaw)


## How far toward the camera a world direction points (viewer :1022).
static func toward_camera_component(x: float, z: float, yaw: float) -> float:
	return x * sin(yaw) + z * cos(yaw)


## Which facing a heading reads as on screen (viewer `facingFor`, :1025).
## The side wins on a perfect diagonal, which is what the `>=` is for.
static func facing_for(x: float, z: float, yaw: float, current: String = "") -> String:
	var sx := screen_right_component(x, z, yaw)
	var sy := toward_camera_component(x, z, yaw)
	if sqrt(sx * sx + sy * sy) < 0.05:
		return current if current != "" else "front"
	if absf(sx) >= absf(sy) - 1e-6:
		return "left" if sx < 0.0 else "right"
	return "front" if sy > 0.0 else "back"


## The state spec a prop card is drawn from: the summer state, overlaid by
## `looks.<look>` when this run drew one (viewer `propTemplate`, :3864-3870).
## The look overrides the picture and its measurements; every other field of the
## summer spec survives.
static func state_spec(prop: Dictionary, state: String, look: String) -> Dictionary:
	var states: Dictionary = prop.get("states", {})
	var summer: Variant = states.get(state)
	if not (summer is Dictionary):
		return {}
	var spec: Dictionary = (summer as Dictionary).duplicate()
	if look != "":
		var looks: Variant = spec.get("looks")
		if looks is Dictionary and (looks as Dictionary).get(look) is Dictionary:
			spec.merge((looks as Dictionary)[look], true)
	return spec


## True when this state has a picture for that look, i.e. the template key
## carries the look rather than falling back to summer.
static func has_look(prop: Dictionary, state: String, look: String) -> bool:
	if look == "":
		return false
	var states: Dictionary = prop.get("states", {})
	var summer: Variant = states.get(state)
	if not (summer is Dictionary):
		return false
	var looks: Variant = (summer as Dictionary).get("looks")
	return looks is Dictionary and (looks as Dictionary).get(look) is Dictionary


## A plane whose foot row sits at local y = 0, so it stands on the ground
## (viewer `cardGeometry`, :2886: `PlaneGeometry` translated by
## `height * (foot - 0.5)`).
static func card_mesh(width: float, height: float, foot: float) -> QuadMesh:
	var quad := QuadMesh.new()
	quad.size = Vector2(width, height)
	quad.center_offset = Vector3(0.0, height * (foot - 0.5), 0.0)
	return quad


# --- materials and templates -----------------------------------------------

## `cardMaterial` (viewer :2892). `kind` picks the render state, which is a
## compile-time render_mode in Godot and so a separate shader file:
## `"opaque"` hard-edged (alpha test, writes depth), `"soft"` soft-edged
## (alpha-to-coverage, writes depth), `"blend"` faded or flat (no depth write).
func card_material(texture: Texture2D, soft: bool, hint: String = "none", sway_meters: float = 0.0, kind: String = "") -> ShaderMaterial:
	var chosen := kind
	if chosen == "":
		chosen = "soft" if soft else "opaque"
	var path := CARD_SHADER
	if chosen == "soft":
		path = CARD_SOFT_SHADER
	elif chosen == "blend":
		path = CARD_BLEND_SHADER
	var material := ShaderMaterial.new()
	material.shader = load(path)
	material.set_shader_parameter("u_map", texture)
	material.set_shader_parameter("u_frame_uv", Vector4(0.0, 0.0, 1.0, 1.0))
	material.set_shader_parameter("u_flip", 0.0)
	material.set_shader_parameter("u_alpha_cutoff", ALPHA_CUTOFF)
	material.set_shader_parameter("u_soft", 1.0 if soft else 0.0)
	material.set_shader_parameter("u_opacity", 1.0)
	material.set_shader_parameter("u_tint", Vector3.ONE)
	material.set_shader_parameter("u_sway_mode", float(SWAY_MODES.get(hint, 0.0)))
	material.set_shader_parameter("u_sway_amplitude", sway_meters)
	material.set_shader_parameter("u_billboard", 1.0)
	if uniforms != null:
		uniforms.register(material)
	return material


## One shared mesh + material per `(prop_id, state, look)`; every instance is a
## plain node with its own transform, and the shader derives the sway phase from
## that transform, so five hundred pines cost ten materials (viewer :3860).
func prop_template(prop_id: String, state: String, look: String = "") -> Variant:
	var props: Dictionary = manifest.get("props", {})
	var prop: Variant = props.get(prop_id)
	if not (prop is Dictionary):
		return null
	var seasonal := has_look(prop, state, look)
	var key := "%s/%s/%s" % [prop_id, state, look if seasonal else ""]
	if _prop_templates.has(key):
		return _prop_templates[key]
	var spec := state_spec(prop, state, look)
	if spec.is_empty():
		_prop_templates[key] = null
		return null
	var layout := card_layout(spec)
	var soft := String((prop as Dictionary).get("edge", "hard")) == "soft"
	var material := card_material(
		package.texture(String(spec.get("image", ""))),
		soft,
		String((prop as Dictionary).get("motion_hint", "none")),
		float(layout["width"]) * 0.05,
	)
	var mesh := card_mesh(float(layout["width"]), float(layout["height"]), float(layout["foot"]))
	mesh.surface_set_material(0, material)
	var shadow := float((prop as Dictionary).get("shadow_width_meters", 0.0))
	if shadow == 0.0:
		shadow = float(layout["width"]) * 0.5
	var template := {
		"mesh": mesh,
		"material": material,
		"layout": layout,
		"shadow": shadow,
		"prop": prop,
		"spec": spec,
		"soft": soft,
	}
	_prop_templates[key] = template
	return template


## A dropped pickup's card (viewer `itemTemplate`, :3228). The run's items carry
## no `ground_contact_y_normalized`, so `card_layout` falls back to foot = 1 and
## the image's bottom row is the ground line.
func item_template(item_id: String) -> Variant:
	if _item_templates.has(item_id):
		return _item_templates[item_id]
	var items: Dictionary = manifest.get("items", {})
	var spec: Variant = items.get(item_id)
	if not (spec is Dictionary):
		_item_templates[item_id] = null
		return null
	var layout := card_layout(spec)
	var material := card_material(package.texture(String((spec as Dictionary).get("image", ""))), false)
	var mesh := card_mesh(float(layout["width"]), float(layout["height"]), float(layout["foot"]))
	mesh.surface_set_material(0, material)
	var template := {
		"mesh": mesh,
		"material": material,
		"layout": layout,
		"width": float(layout["width"]),
	}
	_item_templates[item_id] = template
	return template


## An actor gets its own mesh and material: only actors need a per-card flip and
## a per-card frame (viewer `actorRecord`, :3889). The card is placed before it
## is added to the tree, because a node's transform reaches the rendering server
## on entry and afterwards only when the scene tree flushes its transform
## notifications -- see `_place`.
func actor_record(actor_id: String, position: Vector3 = Vector3.ZERO) -> Variant:
	var actors: Dictionary = manifest.get("actors", {})
	var actor: Variant = actors.get(actor_id)
	if not (actor is Dictionary):
		return null
	var states: Dictionary = (actor as Dictionary).get("states", {})
	var first_state := ""
	var spec: Variant = (actor as Dictionary).get("still")
	if not states.is_empty():
		first_state = String(states.keys()[0])
		spec = states[first_state]
	if not (spec is Dictionary):
		return null
	var columns := int((spec as Dictionary).get("columns", 1))
	var layout := card_layout(spec, columns)
	var atlas := String((spec as Dictionary).get("atlas", (spec as Dictionary).get("image", "")))
	var material := card_material(package.texture(atlas), false)
	var node := MeshInstance3D.new()
	node.mesh = card_mesh(float(layout["width"]), float(layout["height"]), float(layout["foot"]))
	node.material_override = material
	node.extra_cull_margin = maxf(float(layout["width"]), float(layout["height"]))
	_attach(node, position)
	return {
		"kind": "actor",
		"node": node,
		"material": material,
		"actor": actor,
		"actor_id": actor_id,
		"state": first_state,
		"meshes": {},
	}


## Point an actor card at one frame of one state (viewer `setActorFrame`,
## :3910). A four-way actor has a strip per facing and is never mirrored; a
## single_mirrored actor uses the state strip and flips for `left`.
func set_actor_frame(record: Dictionary, state: String, elapsed: float, facing: String) -> void:
	var actor: Dictionary = record["actor"]
	var states: Dictionary = actor.get("states", {})
	var state_block: Variant = states.get(state)
	if not (state_block is Dictionary):
		return
	var facings: Variant = (state_block as Dictionary).get("facings")
	var spec: Dictionary = state_block
	var has_facings := facings is Dictionary
	if has_facings:
		var table: Dictionary = facings
		if table.get(facing) is Dictionary:
			spec = table[facing]
		elif table.get("front") is Dictionary:
			spec = table["front"]
	var key := ("%s/%s" % [state, facing]) if has_facings else state
	if String(record.get("state", "")) != key:
		var meshes: Dictionary = record["meshes"]
		if not meshes.has(key):
			var layout := card_layout(spec, int(spec.get("columns", 1)))
			meshes[key] = card_mesh(float(layout["width"]), float(layout["height"]), float(layout["foot"]))
		var node: MeshInstance3D = record["node"]
		node.mesh = meshes[key]
		record["material"].set_shader_parameter("u_map", package.texture(String(spec.get("atlas", spec.get("image", "")))))
		record["state"] = key
	var frame: Dictionary = motion_frame(spec, elapsed)
	record["material"].set_shader_parameter(
		"u_frame_uv",
		frame_uv(int(frame["frame"]), int(spec.get("columns", 1)), int(spec.get("rows", 1))),
	)
	record["material"].set_shader_parameter("u_flip", 1.0 if (not has_facings and facing == "left") else 0.0)


# --- the per-frame sync ----------------------------------------------------

## Create, rebuild and remove one card per world entity (viewer `syncEntities`,
## :4972). Forage is drawn by the instanced sheet, not here.
func sync_entities(world) -> void:
	var entities: Array = field(world, "entities", [])
	# The removal pass costs a Dictionary of every id in the world and an array
	# of every record's key, every frame, to find the handful of entities that
	# vanished. Counting the records the walk below meets says the same thing
	# for nothing: when every record was met, nothing was removed. (An id is
	# never reused, so a record met is a record still standing.)
	var matched := 0
	for entity: Variant in entities:
		# The kind is read first and compared as a Variant: forage is drawn by
		# the instanced sheet and never has a record, and it is a third of the
		# world, so it leaves before an id String is built or the record table
		# is asked anything.
		var kind: Variant = field(entity, "kind", "")
		if kind == "forage":
			continue
		var id := String(field(entity, "id", ""))
		var existing: Variant = _records.get(id)
		if existing != null:
			matched += 1
		if kind == "mob":
			if existing == null:
				var record: Variant = actor_record(
					String(field(entity, "actor_id", "")),
					Vector3(float(field(entity, "x", 0.0)), 0.0, float(field(entity, "z", 0.0))),
				)
				if record != null:
					_records[id] = record
					_movers_stale = true
			continue
		if kind == "item":
			if existing == null:
				var template: Variant = item_template(String(field(entity, "item_id", "")))
				if template != null:
					var node := MeshInstance3D.new()
					node.mesh = template["mesh"]
					node.extra_cull_margin = float(template["width"])
					_attach(node, Vector3(
						float(field(entity, "x", 0.0)),
						float(field(entity, "y", 0.0)),
						float(field(entity, "z", 0.0)),
					))
					_records[id] = {
						"kind": "item",
						"node": node,
						"shadow": float(template["width"]) * 0.9,
					}
					_movers_stale = true
			continue
		if kind != "prop":
			continue
		var dirty := bool(field(entity, "dirty", false))
		var stale: bool = existing is Dictionary and bool((existing as Dictionary).get("stale", false))
		if existing != null and not dirty and not stale:
			continue
		if existing != null:
			# A state change rebuilds the card; the viewer keeps the shake on the
			# id, so the stump that just appeared goes on rocking (:5626-5631).
			_drop_record(id, false)
		if entity is Dictionary:
			(entity as Dictionary)["dirty"] = false
		var built: Variant = prop_template(
			String(field(entity, "prop_id", "")),
			String(field(entity, "state", "")),
			_look,
		)
		if built == null:
			continue
		var template: Dictionary = built
		var node := MeshInstance3D.new()
		node.mesh = template["mesh"]
		var layout: Dictionary = template["layout"]
		node.extra_cull_margin = maxf(float(layout["width"]), float(layout["height"]))
		_attach(node, Vector3(float(field(entity, "x", 0.0)), 0.0, float(field(entity, "z", 0.0))))
		_records[id] = {
			"kind": "prop",
			"node": node,
			"shadow": float(template["shadow"]),
			"stale": false,
		}
		_movers_stale = true
	if matched != _records.size():
		# Something the walk did not meet is still holding a card: build the
		# live id set and drop them. Rare — a drop taken, a mob gone — so the
		# two allocations are paid on those frames alone.
		var alive := {}
		for entity: Variant in entities:
			alive[String(field(entity, "id", ""))] = true
		for id: String in _records.keys():
			if not alive.has(id):
				_drop_record(id, true)


## Alpha under this much of the card's picture is not the thing: the pointer
## passes through a birch's empty corner to the pine behind it.
const PICK_ALPHA := 0.3
## The pick reads each card texture back once, shrunk to this many pixels a
## side; a card is metres wide, so the test is a hand's width coarse.
const PICK_IMAGE_SIZE := 128

## The thing under a screen point, for the pointer (not the viewer's: it had
## no mouse). Every card is a billboard perpendicular to the view axis, so its
## four corners project to an axis-aligned screen rectangle; a hit inside the
## rectangle is then tested against the card's own picture, so the empty
## corner of a card is not the card; the foot row's screen height orders the
## hits (the nearer card is drawn in front). Forage has no card — it is
## instanced from the sheet — so a piece is hit within a small circle round its
## foot. The player is never a hit. Returns the world's own entity Dictionary,
## or null.
func pick_entity(screen: Vector2, camera: Camera3D, world, forage_radius_px: float = 26.0) -> Variant:
	if camera == null or world == null:
		return null
	var entities: Array = field(world, "entities", [])
	var best: Variant = null
	var best_foot_y := -INF
	for entity: Variant in entities:
		var kind: Variant = field(entity, "kind", "")
		var foot := Vector3(float(field(entity, "x", 0.0)), float(field(entity, "y", 0.0)) if kind == "item" else 0.0, float(field(entity, "z", 0.0)))
		if camera.is_position_behind(foot):
			continue
		var foot_s := camera.unproject_position(foot)
		if kind == "forage":
			if bool(field(entity, "picked", false)) or bool(field(entity, "hidden", false)):
				continue
			if foot_s.distance_to(screen) > forage_radius_px:
				continue
			if foot_s.y > best_foot_y:
				best_foot_y = foot_s.y
				best = entity
			continue
		# Broad phase on the foot alone: a card's rectangle stands on its foot
		# and no card is wider than about 8 m, so a foot far to the side or far
		# below the point cannot own it.
		if absf(foot_s.x - screen.x) > 600.0 or foot_s.y < screen.y - 40.0 or foot_s.y > screen.y + 1400.0:
			continue
		var record: Variant = _records.get(String(field(entity, "id", "")))
		if not (record is Dictionary):
			continue
		var node: Node3D = (record as Dictionary).get("node")
		if node == null or not (node is MeshInstance3D) or (node as MeshInstance3D).mesh == null:
			continue
		var quad := (node as MeshInstance3D).mesh as QuadMesh
		if quad == null:
			continue
		var half_w := quad.size.x * 0.5
		var top := quad.center_offset.y + quad.size.y * 0.5
		var bottom := quad.center_offset.y - quad.size.y * 0.5
		var basis := node.global_transform.basis
		var origin := node.global_transform.origin
		var rect := Rect2(foot_s, Vector2.ZERO)
		var first := true
		for corner: Vector3 in [
			origin + basis.x * -half_w + basis.y * bottom,
			origin + basis.x * half_w + basis.y * bottom,
			origin + basis.x * -half_w + basis.y * top,
			origin + basis.x * half_w + basis.y * top,
		]:
			var p := camera.unproject_position(corner)
			if first:
				rect = Rect2(p, Vector2.ZERO)
				first = false
			else:
				rect = rect.expand(p)
		if not rect.has_point(screen):
			continue
		if foot_s.y <= best_foot_y:
			continue
		# Inside the rectangle: is there picture here? The rectangle is the
		# card's quad, so the point's place in it is the quad's UV (the card
		# reads its window top-down, as the quad does). A dropped item is its
		# whole small card: its picture floats mid-card, and a hand aiming at
		# a log on the ground should not have to hit the drawn log.
		if kind != "item":
			var uv := (screen - rect.position) / rect.size
			if _alpha_at(record as Dictionary, uv) < PICK_ALPHA:
				continue
		best_foot_y = foot_s.y
		best = entity
	return best


## The alpha of a card's picture at a quad UV, through the material's window
## and flip. 1 when the picture cannot be read (the card is then its whole
## rectangle, as before).
func _alpha_at(record: Dictionary, uv: Vector2) -> float:
	var node: Variant = record.get("node")
	if not (node is MeshInstance3D):
		return 1.0
	var material: Variant = (node as MeshInstance3D).material_override
	if material == null and (node as MeshInstance3D).mesh != null:
		material = (node as MeshInstance3D).mesh.surface_get_material(0)
	if not (material is ShaderMaterial):
		return 1.0
	var shader_material := material as ShaderMaterial
	var texture: Variant = shader_material.get_shader_parameter("u_map")
	if not (texture is Texture2D):
		return 1.0
	var image := _pick_image(texture as Texture2D)
	if image == null:
		return 1.0
	var window: Variant = shader_material.get_shader_parameter("u_frame_uv")
	var frame: Vector4 = window if window is Vector4 else Vector4(0.0, 0.0, 1.0, 1.0)
	var flipped := float(shader_material.get_shader_parameter("u_flip")) > 0.5
	var u := (1.0 - uv.x) if flipped else uv.x
	var x := int(clampf(frame.x + u * frame.z, 0.0, 0.9999) * image.get_width())
	var y := int(clampf(frame.y + uv.y * frame.w, 0.0, 0.9999) * image.get_height())
	return image.get_pixel(x, y).a


func _pick_image(texture: Texture2D) -> Image:
	var key := texture.get_instance_id()
	if _pick_images.has(key):
		return _pick_images[key]
	var image: Image = texture.get_image()
	if image != null:
		image = image.duplicate()
		if image.is_compressed():
			image.decompress()
		image.convert(Image.FORMAT_RGBA8)
		# Shrink along the longer side, so a wide strip keeps its cells.
		var longest := maxi(image.get_width(), image.get_height())
		if longest > PICK_IMAGE_SIZE:
			var scale := float(PICK_IMAGE_SIZE) / float(longest)
			image.resize(maxi(1, int(image.get_width() * scale)), maxi(1, int(image.get_height() * scale)), Image.INTERPOLATE_BILINEAR)
	_pick_images[key] = image
	return image


## Stand a card in the world and hand it to the rendering server.
##
## `force_update_transform` is not decoration. Setting `position` -- or entering
## the tree -- only marks a `Node3D` dirty; the transform reaches the rendering
## server when the scene tree flushes its transform notifications, at the top of
## an engine frame. The capture harness and the tests drive `Main.frame()` by
## hand and then draw with `RenderingServer.force_draw`, which flushes nothing,
## so a card created or moved between two flushes is drawn at the world origin.
## That is where the player's card stood in every captured frame: it is built on
## the first frame, long after the harness's last `await process_frame`.
func _attach(node: Node3D, position: Vector3) -> void:
	node.position = position
	add_child(node)
	if node.is_inside_tree():
		node.force_update_transform()


## Move a card that is already in the tree, and flush it for the same reason.
static func _place(node: Node3D, position: Vector3) -> void:
	node.position = position
	if node.is_inside_tree():
		node.force_update_transform()


## The same, for a card whose basis is turning too (a shake or a fall).
static func _place_basis(node: Node3D, basis: Basis) -> void:
	node.transform = Transform3D(basis, node.position)
	if node.is_inside_tree():
		node.force_update_transform()


func _drop_record(id: String, forget_shake: bool) -> void:
	var record: Variant = _records.get(id)
	if record is Dictionary:
		var node: Variant = (record as Dictionary).get("node")
		if node is Node:
			(node as Node).queue_free()
	_records.erase(id)
	_movers_stale = true
	if forget_shake:
		_shakes.erase(id)


func _update_player(world) -> void:
	var player_id := String(field(world, "player_id", ""))
	if player_id != _player_id:
		_player_id = player_id
		if _player_record is Dictionary:
			((_player_record as Dictionary)["node"] as Node).queue_free()
		_player_record = null
	if player_id == "":
		return
	var player: Variant = field(world, "player")
	if player == null:
		return
	if _player_record == null:
		_player_record = actor_record(player_id, Vector3(
			float(field(player, "x", 0.0)), 0.0, float(field(player, "z", 0.0)),
		))
		if _player_record == null:
			return
	var record: Dictionary = _player_record
	set_actor_frame(
		record,
		String(field(player, "state", "idle")),
		float(field(player, "elapsed", 0.0)),
		String(field(player, "facing", "front")),
	)
	_place(
		record["node"],
		Vector3(float(field(player, "x", 0.0)), 0.0, float(field(player, "z", 0.0))),
	)


func _update_entities(world) -> void:
	# Props are skipped here — a prop never moves, so its transform is written
	# when the card is built and only a shake or a settle touches it again. (The
	# viewer rewrote all 2459 of them every frame; the picture is identical.)
	# Walking every entity to find the mobs and the drops among them costs an
	# id and a lookup per entity, so the pairs that do move are kept and rebuilt
	# only when a record was created or dropped.
	if _movers_stale:
		_rebuild_movers(world)
	for pair: Array in _movers:
		var entity: Variant = pair[0]
		var block: Dictionary = pair[1]
		var kind := String(block.get("kind", ""))
		if kind == "actor":
			set_actor_frame(
				block,
				String(field(entity, "state", "idle")),
				float(field(entity, "elapsed", 0.0)),
				String(field(entity, "facing", "front")),
			)
		var y := float(field(entity, "y", 0.0)) if kind == "item" else 0.0
		_place(block["node"], Vector3(float(field(entity, "x", 0.0)), y, float(field(entity, "z", 0.0))))


## The `[entity, record]` pairs `_update_entities` walks: every record that is
## not a prop, in the world's own entity order.
func _rebuild_movers(world) -> void:
	_movers_stale = false
	_movers.clear()
	for entity: Variant in field(world, "entities", []):
		var record: Variant = _records.get(String(field(entity, "id", "")))
		if not (record is Dictionary):
			continue
		if String((record as Dictionary).get("kind", "")) == "prop":
			continue
		_movers.append([entity, record])


# --- reactions: the shake and the fall --------------------------------------

## A blow to a standing card: a damped rock about its foot, away from the axe
## (viewer :3089, fired at :5556-5564). Whether a card rocks at all is the
## author's word (`hit_reaction`); a trunk gives and a boulder does not.
func _on_hit(event: Dictionary) -> void:
	var id := String(event.get("id", ""))
	if not _records.has(id):
		return
	var props: Dictionary = manifest.get("props", {})
	var prop: Variant = props.get(String(event.get("prop_id", "")))
	if not (prop is Dictionary):
		return
	if String((prop as Dictionary).get("hit_reaction", "none")) != "shake":
		return
	var sign_value := -1.0 if screen_right_component(
		float(event.get("away_x", 0.0)), float(event.get("away_z", 0.0)), _yaw
	) < 0.0 else 1.0
	_shakes[id] = {
		"start": _time,
		"sign": sign_value,
		"strength": 1.0 if String((prop as Dictionary).get("family", "")) == "tree" else 0.6,
	}


## The standing card, detached from its entity, toppling in the screen plane
## about its foot while the entity underneath already shows its stump
## (viewer `fell`, :3098).
func _on_fell(event: Dictionary) -> void:
	var built: Variant = prop_template(
		String(event.get("prop_id", "")),
		String(event.get("state", "")),
		_look,
	)
	if built == null:
		return
	var template: Dictionary = built
	var layout: Dictionary = template["layout"]
	# Its own material, so `u_opacity` can take it away without fading the two
	# hundred pines that share the template's.
	var material := card_material(
		(template["material"] as ShaderMaterial).get_shader_parameter("u_map"),
		bool(template["soft"]),
		"none",
		0.0,
		"blend",
	)
	material.render_priority = FALLER_PRIORITY
	var node := MeshInstance3D.new()
	node.mesh = template["mesh"]
	node.material_override = material
	node.extra_cull_margin = float(layout["height"])
	_attach(node, Vector3(float(event.get("x", 0.0)), 0.0, float(event.get("z", 0.0))))
	_fallers.append({
		"node": node,
		"material": material,
		"start": _time,
		"sign": float(event.get("sign", 1.0)),
		"x": float(event.get("x", 0.0)),
		"z": float(event.get("z", 0.0)),
		# The foot-to-crown reach of the card, which is where the crown lands.
		"height": float(layout["height"]) * float(layout["foot"]),
		"landed": false,
	})


func _update_shakes() -> void:
	for id: String in _shakes.keys():
		var shake: Dictionary = _shakes[id]
		var record: Variant = _records.get(id)
		var t := _time - float(shake["start"])
		if not (record is Dictionary) or t > 0.9:
			_shakes.erase(id)
			if record is Dictionary:
				_tilt((record as Dictionary)["node"], 0.0)
			continue
		var angle := float(shake["sign"]) * float(shake["strength"]) * 0.11 \
			* sin(t * 2.0 * PI * 7.5) * exp(-t * 4.5)
		_tilt((record as Dictionary)["node"], angle)


func _update_fallers(_delta: float) -> void:
	for index in range(_fallers.size() - 1, -1, -1):
		var faller: Dictionary = _fallers[index]
		var t := (_time - float(faller["start"])) / FALL_SECONDS
		var angle := 0.0
		if t < 1.0:
			# Accelerating, like a thing given to gravity: the angle grows with
			# t squared.
			angle = float(faller["sign"]) * (PI / 2.0) * t * t
		else:
			if not bool(faller["landed"]):
				faller["landed"] = true
				var right := screen_right(_yaw)
				var reach := float(faller["sign"]) * float(faller["height"]) * 0.7
				faller_landed.emit(
					float(faller["x"]) + right.x * reach,
					float(faller["z"]) + right.y * reach,
					float(faller["height"]),
				)
			var after := t - 1.0
			# One short bounce, then the card fades and is gone.
			angle = float(faller["sign"]) * (PI / 2.0 - sin(minf(1.0, after / 0.3) * PI) * 0.12)
			faller["material"].set_shader_parameter(
				"u_opacity", maxf(0.0, 1.0 - maxf(0.0, after - 0.5) / 0.6)
			)
			if after > 1.2:
				(faller["node"] as Node).queue_free()
				_fallers.remove_at(index)
				continue
		_tilt(faller["node"], angle)


## A billboard turned in its own plane about its foot: a shake, or a fall.
## Positive leans the top toward the screen's right, which is why the shader's
## basis multiply takes a negative rotation about the card's own z (viewer
## `tiltCard`, :2927).
func _tilt(node: Node3D, radians: float) -> void:
	if radians == 0.0:
		_place_basis(node, Basis.IDENTITY)
		return
	_place_basis(node, Basis(Vector3(0.0, 0.0, 1.0), -radians))


# --- the pointer's hover -----------------------------------------------------

## Lift the card standing for `entity_id` (the thing under the pointer), and
## let the last one down. "" lifts nothing. A shared template card (a prop, a
## drop) wears a lifted twin of its material as an override; an actor's own
## material takes the uniform directly. A forage piece has no card of its own
## (it is instanced from the sheet), so hovering one lifts nothing and the
## label alone names it.
func set_highlight(entity_id: String) -> void:
	if entity_id == _highlight_id:
		return
	_let_down(_records.get(_highlight_id))
	_highlight_id = entity_id
	_apply_highlight()


func _let_down(record: Variant) -> void:
	if not (record is Dictionary):
		return
	var node: Variant = (record as Dictionary).get("node")
	if not (node is MeshInstance3D):
		return
	if String((record as Dictionary).get("kind", "")) == "actor":
		((record as Dictionary)["material"] as ShaderMaterial).set_shader_parameter("u_highlight", 0.0)
	else:
		(node as MeshInstance3D).material_override = null


func _apply_highlight() -> void:
	if _highlight_id == "":
		return
	var record: Variant = _records.get(_highlight_id)
	if not (record is Dictionary):
		return
	var node: Variant = (record as Dictionary).get("node")
	if not (node is MeshInstance3D):
		return
	var mesh_node := node as MeshInstance3D
	if String((record as Dictionary).get("kind", "")) == "actor":
		((record as Dictionary)["material"] as ShaderMaterial).set_shader_parameter("u_highlight", 1.0)
		return
	if mesh_node.material_override != null or mesh_node.mesh == null:
		return
	var base: Variant = mesh_node.mesh.surface_get_material(0)
	if not (base is ShaderMaterial):
		return
	var key := (base as ShaderMaterial).get_instance_id()
	if not _lifted.has(key):
		var lifted := (base as ShaderMaterial).duplicate() as ShaderMaterial
		lifted.set_shader_parameter("u_highlight", 1.0)
		if uniforms != null:
			uniforms.register(lifted)
		_lifted[key] = lifted
	mesh_node.material_override = _lifted[key]


func highlighted() -> String:
	return _highlight_id


## Where a label for an entity hangs in the world: the top of its card, a hand
## above its foot when it has no card (a forage piece), or a dropped item's
## own height. `up` is the card's own up — the camera basis's, since a card is
## a billboard in the camera plane — so the point projects straight above the
## foot on the screen; world up would splay outward from the screen's centre.
## The HUD projects it and stands the name there, so the name belongs to the
## thing rather than to the cursor.
func label_anchor(entity: Variant, up: Vector3 = Vector3.UP) -> Vector3:
	var x := float(field(entity, "x", 0.0))
	var z := float(field(entity, "z", 0.0))
	var kind := String(field(entity, "kind", ""))
	var y := float(field(entity, "y", 0.0)) if kind == "item" else 0.0
	var foot := Vector3(x, y, z)
	var record: Variant = _records.get(String(field(entity, "id", "")))
	if record is Dictionary:
		var node: Variant = (record as Dictionary).get("node")
		if node is MeshInstance3D and (node as MeshInstance3D).mesh is QuadMesh:
			var quad := (node as MeshInstance3D).mesh as QuadMesh
			var top := quad.center_offset.y + quad.size.y * 0.5
			# The drawn top, not the quad's: a card carries a transparent
			# margin above its picture, and a name floating over that margin
			# reads as belonging to nothing.
			top -= quad.size.y * _empty_top(record as Dictionary)
			return foot + up.normalized() * top
	return foot + up.normalized() * 0.45


## How much of a card's window, from the top, is empty (alpha under the pick
## threshold on every column), as a fraction of the window's height. Read off
## the pick's small copy of the picture; 0 when it cannot be read.
func _empty_top(record: Dictionary) -> float:
	var node: Variant = record.get("node")
	if not (node is MeshInstance3D):
		return 0.0
	var material: Variant = (node as MeshInstance3D).material_override
	if material == null and (node as MeshInstance3D).mesh != null:
		material = (node as MeshInstance3D).mesh.surface_get_material(0)
	if not (material is ShaderMaterial):
		return 0.0
	var texture: Variant = (material as ShaderMaterial).get_shader_parameter("u_map")
	if not (texture is Texture2D):
		return 0.0
	var image := _pick_image(texture as Texture2D)
	if image == null:
		return 0.0
	var window: Variant = (material as ShaderMaterial).get_shader_parameter("u_frame_uv")
	var frame: Vector4 = window if window is Vector4 else Vector4(0.0, 0.0, 1.0, 1.0)
	var x0 := int(frame.x * image.get_width())
	var x1 := maxi(x0 + 1, int((frame.x + frame.z) * image.get_width()))
	var y0 := int(frame.y * image.get_height())
	var y1 := maxi(y0 + 1, int((frame.y + frame.w) * image.get_height()))
	for y in range(y0, y1):
		for x in range(x0, x1):
			if image.get_pixel(x, y).a >= PICK_ALPHA:
				return float(y - y0) / float(y1 - y0)
	return 0.0


# --- read-only views, for the modules that need a card's numbers ------------

## The half-width the contact shadow under `entity_id` was sized from, or 0.
func shadow_half_width(entity_id: String) -> float:
	var record: Variant = _records.get(entity_id)
	if record is Dictionary:
		return float((record as Dictionary).get("shadow", 0.0)) * 0.5
	return 0.0


## The card standing for an entity, or null. For a test or a capture harness
## that has to read a card back; nothing in the module writes through it.
func card_node(entity_id: String) -> Node3D:
	var record: Variant = _records.get(entity_id)
	return (record as Dictionary)["node"] if record is Dictionary else null


## The player's card, or null before the first frame built it.
func player_node() -> Node3D:
	return (_player_record as Dictionary)["node"] if _player_record is Dictionary else null


func record_count() -> int:
	return _records.size()


func faller_count() -> int:
	return _fallers.size()
