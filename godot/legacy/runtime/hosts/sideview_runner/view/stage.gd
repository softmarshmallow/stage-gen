class_name RunnerStage
extends Node2D

## Everything the runner draws: the parallax bands, the streamed ground, the
## avatar and its shadow, the hazards and the pickups, and the fight.
##
## A port of the browser host's `buildParallaxStage` and `buildActorsView`. It is
## a view in the strict sense — it reads slices and writes none, and it emits
## nothing. An interface control that wants to act writes through the input latch
## like a key.
##
## Everything is drawn in the browser's own 1280x720 design space and the whole
## canvas is scaled to the window, so every published rectangle lands where the
## manifest says it does and no part of the picture is scaled independently of
## another.
##
## The clock is the caller's `dt`, accumulated here. Nothing reads a wall clock,
## so a capture handing this fixed steps draws the same picture every time —
## which is what makes a picture of this game comparable with another picture of
## it, and is a property the first port did not have.

## Back to front. A genre may skip a rung of the family's ladder; it may never
## invert two, and `FamilyParallax.seal_depth_ladder` refuses one that does.
const DEPTHS := {
	"background": 0,
	"ground": 20,
	"shadow": 24,
	"dust": 25,
	"pickup": 26,
	"hazard": 27,
	"boss": 29,
	"avatar": 30,
	"shot": 32,
	"foreground": 40,
	"boss_bar": 50,
}

## The cell a collectible is fitted into, as a fraction of a tile. A coin drawn
## to its own calibration is a speck at this scale; the browser fitted pickups
## up into a readable cell and this is that cell.
const PICKUP_READABLE_CELL_TILES := 0.72

const HAZARD_GROUND_SHADOW_ALPHA := 0.24
const HAZARD_GROUND_SHADOW_HEIGHT_TILES := 0.16
const HAZARD_CUE_COLOR := Color(1.0, 0.819, 0.4)
const PICKUP_HALO_FILL := Color(1.0, 0.902, 0.604)
const PICKUP_HALO_RIM := Color(1.0, 0.941, 0.678)

var _package: HostRunDir = null
var _config: Dictionary = {}
var _bands: Array = []
var _ground: Node2D = null
var _ground_signature: String = ""
var _avatar: HostActor = null
var _shadow: RunnerEllipses = null
var _hazards: Node2D = null
var _hazard_shapes: RunnerEllipses = null
var _hazard_views: Dictionary = {}
var _pickups: Node2D = null
var _pickup_shapes: RunnerEllipses = null
var _pickup_views: Dictionary = {}
var _boss: RunnerBossView = null
var _prop_draw: Dictionary = {}
var _item_draw: Dictionary = {}
var _flash_shader: Shader = null
## The frame clock, in milliseconds. A cut-in stops the world; a coin already
## turning keeps turning, because it is a picture of a thing rather than a rule.
var _now_ms: float = 0.0
## The seed the mirrored instances belong to. A restart replays the same world
## columns with different chunks, so a sprite cached by (column, id) would alias
## stale geometry across it.
var _worn_seed: int = -1
## When the run ended on the frame clock, and the row the body was at. Negative
## while a run is still being played.
var _death_at_ms: float = -1.0
var _death_row: float = 0.0
## The gravity a body falls under once the run is over: the arc's own, so a
## death reads as the game letting go rather than as a second set of physics.
var _fall_gravity: float = 0.0


func build(package: HostRunDir, config: Dictionary) -> void:
	_package = package
	_config = config
	var manifest := package.manifest
	_flash_shader = load("res://hosts/common/shaders/fill.gdshader")
	_fall_gravity = float(RunnerAvatarSystem.jump_arc(config)["gravityPerSecondSquared"])
	_build_bands(manifest, "background")
	_ground = Node2D.new()
	_ground.z_index = DEPTHS["ground"]
	add_child(_ground)
	_shadow = RunnerEllipses.new()
	_shadow.z_index = DEPTHS["shadow"]
	add_child(_shadow)
	_pickups = Node2D.new()
	_pickups.z_index = DEPTHS["pickup"]
	add_child(_pickups)
	_pickup_shapes = RunnerEllipses.new()
	_pickups.add_child(_pickup_shapes)
	_hazards = Node2D.new()
	_hazards.z_index = DEPTHS["hazard"]
	add_child(_hazards)
	_hazard_shapes = RunnerEllipses.new()
	_hazards.add_child(_hazard_shapes)
	_build_avatar(manifest)
	_boss = RunnerBossView.of(
		package, config, DEPTHS["boss"], DEPTHS["shot"], DEPTHS["boss_bar"], _flash_shader
	)
	if _boss != null:
		add_child(_boss)
	_build_bands(manifest, "foreground")
	_measure_catalog(manifest)


## Mirror one frame of the world. Reads only.
func sync(world: RunnerWorld, dt: float) -> void:
	_now_ms += dt * 1000.0
	if int(world.run["seed"]) != _worn_seed:
		_worn_seed = int(world.run["seed"])
		_forget_instances()
	var scroll := float(world.camera["scrollX"])
	for entry: Variant in _bands:
		var band: Dictionary = entry
		var sprite := band["node"] as Sprite2D
		# The band's texture was built at the size it is drawn, so texture space
		# and screen space are the same space and the family's conversion is by
		# one. A band repeats, so only the remainder of the scroll is drawn;
		# without the wrap a long run walks the texture off the screen.
		var offset := FamilyParallax.band_tile_position(scroll, float(band["parallax"]), 1.0)
		sprite.position.x = float(band["originX"]) - fposmod(offset, float(band["width"]))
	_sync_ground(world, scroll)
	_sync_avatar(world, dt)
	_sync_hazards(world, scroll)
	_sync_pickups(world, scroll)
	if _boss != null:
		_boss.sync(world, dt)


func _build_bands(manifest: Dictionary, plane: String) -> void:
	var walk_surface_y := RunnerContract.ground_line_y(_config)
	var layers: Array = manifest.get("layers", [])
	for entry: Variant in layers:
		var layer: Dictionary = entry
		if String(layer["plane"]) != plane:
			continue
		var offset_raw: Variant = layer.get("vertical_offset")
		var layout := FamilyParallax.layer_layout(
			String(layer["vertical_anchor"]),
			0.0 if offset_raw == null else float(offset_raw),
			# The frame the band was painted against, which for a trimmed band
			# is not its own height. See `RunnerContract.layer_frame_height`.
			RunnerContract.layer_frame_height(layer, layers),
			float(layer["height"]),
			RunnerContract.VIEW_HEIGHT,
			walk_surface_y,
			float(layer["parallax"])
		)
		if layout.is_empty():
			push_error("runner stage: layer %s does not describe a band" % layer["layer_id"])
			continue
		var scale_factor := float(layout["scale"])
		var tile_width := maxi(1, int(round(float(layer["width"]) * scale_factor)))
		var tile_height := maxi(1, int(round(float(layer["height"]) * scale_factor)))
		var texture := HostLayerTexture.band(
			_package,
			String(layer["image"]),
			layer.get("presentation", {}),
			tile_width,
			tile_height
		)
		if texture == null:
			# A band this run did not publish is a gap in the picture and is
			# said out loud, rather than drawn as a hole nobody can explain.
			push_error(
				"runner stage: layer %s has no image at %s" % [layer["layer_id"], layer["image"]]
			)
			continue
		var sprite := Sprite2D.new()
		sprite.texture = texture
		sprite.centered = false
		sprite.region_enabled = true
		# Enough whole repeats to cover the viewport from wherever the wrap has
		# put the left edge, which is anywhere within one tile to the left of the
		# origin. Counting *screens* instead of tiles is what left a bare strip
		# down the right of the picture whenever a tile was narrower than the
		# canvas — and at this design width, the cover band is.
		var repeats := 1 + int(ceil(RunnerContract.VIEW_WIDTH / float(tile_width)))
		sprite.region_rect = Rect2(
			0.0, 0.0, float(tile_width * repeats), float(tile_height)
		)
		sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
		sprite.position = Vector2(0.0, float(layout["topY"]))
		sprite.z_index = (
			DEPTHS["background"] if plane == "background" else DEPTHS["foreground"]
		) + int(layer["order"])
		add_child(sprite)
		_bands.append(
			{
				"node": sprite,
				"parallax": float(layer["parallax"]),
				"scale": scale_factor,
				"width": float(tile_width),
				"originX": 0.0,
			}
		)


func _build_avatar(manifest: Dictionary) -> void:
	var avatar: Dictionary = manifest.get("avatar", {})
	if avatar.is_empty():
		push_error("runner stage: this run publishes no avatar")
		return
	_avatar = HostActor.of(
		_package,
		avatar.get("motions", []),
		avatar.get("calibration", {}),
		_config,
		_flash_shader
	)
	if _avatar == null:
		return
	_avatar.z_index = DEPTHS["avatar"]
	add_child(_avatar)


## Measure the catalogue once: how big each prop and item is drawn.
##
## Both are sized by the producer's own ruler — how many source pixels one unit
## of height was drawn as — never by the pixels the raster happens to carry, so
## a redrawn asset at another resolution stands exactly as tall.
func _measure_catalog(manifest: Dictionary) -> void:
	var design_height := float(_config["playerHeightTiles"]) * float(_config["tilePx"])
	var tile_px := float(_config["tilePx"])
	var arithmetic: Dictionary = _config["arithmetic"]
	var collision_width := tile_px * (1.0 - float(arithmetic["hazardColumnInset"]) * 2.0)
	for entry: Variant in (manifest.get("props", []) as Array):
		var prop: Dictionary = entry
		# Trimmed: the calibration is measured against the subject, not the
		# canvas it floats in, and a prop placed by its bottom edge must stand
		# on its own feet rather than on its padding.
		var texture := _package.trimmed_texture(String(prop["image"]))
		if texture == null:
			push_error("runner stage: prop %s has no image" % prop["prop_id"])
			continue
		var per_unit := float((prop.get("calibration", {}) as Dictionary).get(
			"source_px_per_unit", 0.0
		))
		var calibrated := design_height / per_unit if per_unit > 0.0 else 1.0
		var fitted := RunnerPresentation.hazard_visual_scale(
			calibrated, float(texture.get_width()), collision_width
		)
		if fitted.is_empty():
			push_error("runner stage: prop %s cannot be sized" % prop["prop_id"])
			continue
		_prop_draw[String(prop["prop_id"])] = {
			"texture": texture,
			"scaleX": float(fitted["scaleX"]),
			"scaleY": float(fitted["scaleY"]),
		}
	var readable := tile_px * PICKUP_READABLE_CELL_TILES
	for entry: Variant in (manifest.get("items", []) as Array):
		var item: Dictionary = entry
		var texture := _package.trimmed_texture(String(item["image"]))
		if texture == null:
			push_error("runner stage: item %s has no image" % item["item_id"])
			continue
		var per_unit := float((item.get("calibration", {}) as Dictionary).get(
			"source_px_per_unit", 0.0
		))
		var calibrated := design_height / per_unit if per_unit > 0.0 else 1.0
		_item_draw[String(item["item_id"])] = {
			"texture": texture,
			"scale": minf(
				calibrated,
				minf(
					readable / maxf(1.0, float(texture.get_width())),
					readable / maxf(1.0, float(texture.get_height()))
				)
			),
		}


func _sync_avatar(world: RunnerWorld, dt: float) -> void:
	if _avatar == null:
		return
	_avatar.show_motion(String(world.avatar["motion"]), int(world.avatar["jumpImpulses"]))
	_avatar.advance(dt)
	var feet := RunnerContract.row_to_screen_y(_body_row(world), _config)
	_avatar.place(float(_config["avatarScreenX"]), feet)
	# The contracted hurt representation: while the gauge is refusing contact the
	# body blinks, and the phase is arithmetic on the gauge's own clock rather
	# than a tween, so a fixed-step replay draws the same alpha on the same
	# frame. Re-applied every frame because it is a function of time.
	_avatar.modulate.a = FamilyVitals.body_blink_alpha(
		world.vitals, FamilyVitals.CONTACT_BLINK_INTERVAL_MS, FamilyVitals.CONTACT_BLINK_ALPHA
	)
	_sync_shadow(world)


## The row the body is drawn at.
##
## While the run is being played that is simply the row the simulation says. Once
## it has ended the simulation stops moving the body at all, so a player shot out
## of a climb played a death animation in mid-air over the arena; here it falls
## the rest of the way under the arc's own gravity and stays where it lands.
func _body_row(world: RunnerWorld) -> float:
	var row := float(world.avatar["y"])
	if String(world.run["phase"]) != "dead":
		_death_at_ms = -1.0
		return row
	if _death_at_ms < 0.0:
		_death_at_ms = _now_ms
		_death_row = row
	var support := RunnerSegments.surface_row_at(
		world.segments, int(floor(float(world.avatar["distanceColumns"])))
	)
	# No surface under the body is a pit, and a body that died over one goes on
	# down it rather than stopping at the lip.
	var floor_row := INF
	if support >= 0:
		floor_row = float(support)
	return RunnerPresentation.death_fall_row(
		_now_ms - _death_at_ms, _death_row, floor_row, _fall_gravity, float(_config["rows"])
	)


## The contact shadow on the support under the body, thinning with air.
##
## Published as `presentation.contact_shadows` and never read until now, so the
## avatar stood on nothing: at runner speed a body with no shadow reads as
## floating slightly above its own floor.
func _sync_shadow(world: RunnerWorld) -> void:
	_shadow.begin()
	var shadows: Dictionary = (
		_package.manifest.get("presentation", {}) as Dictionary
	).get("contact_shadows", {})
	if bool(shadows.get("enabled", false)) and String(world.run["phase"]) == "running":
		var support := RunnerSegments.surface_row_at(
			world.segments, int(floor(float(world.avatar["distanceColumns"])))
		)
		if support >= 0:
			var air_rows := maxf(0.0, float(support) - float(world.avatar["y"]))
			var spread := maxf(0.45, 1.0 - air_rows / 6.0)
			var tile_px := float(_config["tilePx"])
			_shadow.add_fill(
				float(_config["avatarScreenX"]),
				RunnerContract.row_to_screen_y(float(support), _config),
				tile_px * 0.95 * spread / 2.0,
				tile_px * 0.28 * spread / 2.0,
				Color(0.0, 0.0, 0.0, float(shadows.get("opacity", 0.16)) * spread)
			)
	_shadow.commit()


func _sync_ground(world: RunnerWorld, scroll: float) -> void:
	var chunks: Array = world.segments["chunks"]
	var signature := "%d:%d" % [
		int((chunks[0] as Dictionary)["startColumn"]) if not chunks.is_empty() else 0,
		int(world.segments["nextColumn"]),
	]
	if signature != _ground_signature:
		_ground_signature = signature
		_rebuild_ground(chunks)
	_ground.position.x = -scroll


func _rebuild_ground(chunks: Array) -> void:
	for child in _ground.get_children():
		child.queue_free()
	var ground: Dictionary = _package.manifest.get("ground", {})
	var by_segment := {}
	for entry: Variant in (ground.get("chunks", []) as Array):
		var record: Dictionary = entry
		by_segment[String(record["segment_id"])] = record
	var tile_px := float(_config["tilePx"])
	for entry: Variant in chunks:
		var chunk: Dictionary = entry
		var record: Dictionary = by_segment.get(String(chunk["segmentId"]), {})
		if record.is_empty():
			continue
		var texture := _package.texture(String(record["image"]))
		if texture == null:
			continue
		var sprite := Sprite2D.new()
		sprite.texture = texture
		sprite.centered = false
		var rows := float(record["rows"])
		var columns := float(record["columns"])
		var draw_scale := (columns * tile_px) / float(texture.get_width())
		sprite.scale = Vector2(draw_scale, draw_scale)
		sprite.position = Vector2(
			float(chunk["startColumn"]) * tile_px,
			RunnerContract.VIEW_HEIGHT - rows * tile_px
		)
		_ground.add_child(sprite)


## Mirror the streamed hazards, keyed by instance.
##
## Kept rather than rebuilt: the window holds a few dozen things, and destroying
## and recreating every sprite sixty times a second is churn nobody asked for.
## The shapes around them are refilled each frame, because their alphas move.
func _sync_hazards(world: RunnerWorld, scroll: float) -> void:
	_hazards.position.x = -scroll
	_hazard_shapes.begin()
	var tile_px := float(_config["tilePx"])
	var arithmetic: Dictionary = _config["arithmetic"]
	var collision_width := tile_px * (1.0 - float(arithmetic["hazardColumnInset"]) * 2.0)
	var heights: Dictionary = _config["propHeightUnits"]
	var wanted := {}
	for entry: Variant in RunnerSegments.streamed_hazards(world.segments):
		var hazard: Dictionary = entry
		var prop_id := String(hazard["propId"])
		var key := "%d:%s" % [int(hazard["worldColumn"]), prop_id]
		var drawn: Dictionary = _prop_draw.get(prop_id, {})
		if drawn.is_empty():
			continue
		var support := RunnerSegments.surface_row_at(
			world.segments, int(hazard["worldColumn"])
		)
		if support < 0:
			continue
		wanted[key] = true
		# An overhead hazard hangs with its underside at the clearance line; a
		# surface one stands on its ground.
		var base_row := float(support)
		if String(hazard["anchor"]) == "overhead":
			base_row -= float(hazard["clearanceRows"])
		var center_x := (float(hazard["worldColumn"]) + 0.5) * tile_px
		var base_y := RunnerContract.row_to_screen_y(base_row, _config)
		if not _hazard_views.has(key):
			var texture: Texture2D = drawn["texture"]
			var sprite := Sprite2D.new()
			sprite.texture = texture
			sprite.centered = false
			sprite.scale = Vector2(float(drawn["scaleX"]), float(drawn["scaleY"]))
			sprite.position = Vector2(
				center_x - float(texture.get_width()) * float(drawn["scaleX"]) / 2.0,
				base_y - float(texture.get_height()) * float(drawn["scaleY"])
			)
			_hazards.add_child(sprite)
			_hazard_views[key] = sprite
		# A quiet grounding shadow, so the prop sits on the floor rather than
		# in front of it. An overhead hazard touches nothing and casts none.
		if String(hazard["anchor"]) == "surface":
			_hazard_shapes.add_fill(
				center_x, base_y, collision_width / 2.0,
				tile_px * HAZARD_GROUND_SHADOW_HEIGHT_TILES / 2.0,
				Color(0.0, 0.0, 0.0, HAZARD_GROUND_SHADOW_ALPHA)
			)
		# The approach rim: a restrained warning that agrees exactly with the
		# published collision column and never alters it.
		var height_rows := (
			float(heights.get(prop_id, 1.0)) * float(_config["playerHeightTiles"])
		)
		var alpha := RunnerPresentation.hazard_cue_alpha(
			float(hazard["worldColumn"]) - float(world.avatar["distanceColumns"]), _now_ms
		)
		if alpha > 0.0:
			var cue := HAZARD_CUE_COLOR
			cue.a = alpha
			_hazard_shapes.add_stroke(
				center_x, base_y - height_rows * tile_px / 2.0,
				collision_width * 1.08 / 2.0, height_rows * tile_px * 1.04 / 2.0, cue, 2.0
			)
	_hazard_shapes.commit()
	_forget_missing(_hazard_views, wanted)


func _sync_pickups(world: RunnerWorld, scroll: float) -> void:
	_pickups.position.x = -scroll
	_pickup_shapes.begin()
	var tile_px := float(_config["tilePx"])
	var collected: Dictionary = world.obstacles["collected"]
	var wanted := {}
	for entry: Variant in RunnerSegments.streamed_pickups(world.segments):
		var pickup: Dictionary = entry
		var item_id := String(pickup["itemId"])
		var drawn: Dictionary = _item_draw.get(item_id, {})
		if drawn.is_empty():
			continue
		var key := RunnerObstaclesSystem.pickup_key(pickup)
		wanted[key] = true
		var texture: Texture2D = drawn["texture"]
		var base_scale := float(drawn["scale"])
		var center_x := (float(pickup["worldColumn"]) + 0.5) * tile_px
		var base_y := RunnerContract.row_to_screen_y(float(pickup["row"]) + 0.5, _config)
		var sprite: Sprite2D = _pickup_views.get(key)
		if sprite == null:
			sprite = Sprite2D.new()
			sprite.texture = texture
			sprite.centered = true
			_pickups.add_child(sprite)
			_pickup_views[key] = sprite
		# Collected is not the same as gone: the instance stays in the streamed
		# window until its chunk falls behind, and a sprite that kept drawing
		# would be a coin the player already has.
		var visible_now := not collected.has(key)
		sprite.visible = visible_now
		# The flip is a function of the frame clock and a phase derived from the
		# instance key, so a trail of coins ripples instead of turning as one
		# slab, and two runs of one seed draw the same face on the same frame.
		var motion := RunnerPresentation.collectible(_now_ms, RunnerPresentation.phase_for(key))
		if motion.is_empty():
			continue
		var y := base_y + float(motion["bobRows"]) * tile_px
		sprite.position = Vector2(center_x, y)
		sprite.scale = Vector2(
			base_scale * float(motion["scaleXMultiplier"]),
			base_scale * float(motion["scaleYMultiplier"])
		)
		if not visible_now:
			continue
		var halo := PICKUP_HALO_FILL
		halo.a = 0.06
		var radius := tile_px * PICKUP_READABLE_CELL_TILES * float(motion["haloScale"]) / 2.0
		_pickup_shapes.add_fill(center_x, y, radius, radius, halo)
		var rim := PICKUP_HALO_RIM
		rim.a = float(motion["haloAlpha"])
		_pickup_shapes.add_stroke(center_x, y, radius, radius, rim, 2.0)
	_pickup_shapes.commit()
	_forget_missing(_pickup_views, wanted)


## Drop the mirrors of instances the streamed window no longer holds.
static func _forget_missing(views: Dictionary, wanted: Dictionary) -> void:
	for key: Variant in views.keys():
		if wanted.has(key):
			continue
		(views[key] as Node).queue_free()
		views.erase(key)


## A restart replays the same world columns with different chunks, so every
## mirror keyed by (column, id) has to go with the seed that made it.
func _forget_instances() -> void:
	_forget_missing(_hazard_views, {})
	_forget_missing(_pickup_views, {})
	_ground_signature = ""
	if _boss != null:
		_boss.clear_shots()
