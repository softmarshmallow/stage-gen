class_name RunnerStage
extends Node2D

## Everything the runner draws: the parallax bands, the streamed ground, the
## avatar, the hazards and the pickups.
##
## A port of `web/lib/sideview-runner/parallax.ts`'s builder. It is a view in the
## strict sense — it reads slices and writes none, and it emits nothing. An
## interface control that wants to act writes through the input latch like a key.
##
## Everything is drawn in the browser's own 1280x720 design space and the whole
## canvas is scaled to the window, so every published rectangle lands where the
## manifest says it does and no part of the picture is scaled independently of
## another.

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
}

var _package: HostRunDir = null
var _config: Dictionary = {}
var _bands: Array = []
var _ground: Node2D = null
var _ground_tiles: Dictionary = {}
var _avatar: Sprite2D = null
var _avatar_frames: Dictionary = {}
var _avatar_motion: String = ""
var _avatar_frame: int = 0
var _avatar_clock: float = 0.0
var _hazards: Node2D = null
var _pickups: Node2D = null
var _prop_textures: Dictionary = {}
var _item_textures: Dictionary = {}
var _ground_signature: String = ""


func build(package: HostRunDir, config: Dictionary) -> void:
	_package = package
	_config = config
	var manifest := package.manifest
	_build_bands(manifest, "background")
	_ground = Node2D.new()
	_ground.z_index = DEPTHS["ground"]
	add_child(_ground)
	_pickups = Node2D.new()
	_pickups.z_index = DEPTHS["pickup"]
	add_child(_pickups)
	_hazards = Node2D.new()
	_hazards.z_index = DEPTHS["hazard"]
	add_child(_hazards)
	_build_avatar(manifest)
	_build_bands(manifest, "foreground")
	for entry: Variant in (manifest.get("props", []) as Array):
		var prop: Dictionary = entry
		_prop_textures[String(prop["prop_id"])] = package.texture(String(prop["image"]))
	for entry: Variant in (manifest.get("items", []) as Array):
		var item: Dictionary = entry
		_item_textures[String(item["item_id"])] = package.texture(String(item["image"]))


## Mirror one frame of the world. Reads only.
func sync(world: RunnerWorld) -> void:
	var scroll := float(world.camera["scrollX"])
	for entry: Variant in _bands:
		var band: Dictionary = entry
		var sprite := band["node"] as Sprite2D
		var offset := FamilyParallax.band_tile_position(
			scroll, float(band["parallax"]), float(band["scale"])
		)
		# A band repeats, so only the remainder of the scroll is drawn; without
		# the wrap a long run walks the texture off the screen.
		var width := float(band["width"])
		sprite.position.x = float(band["originX"]) - fposmod(offset * float(band["scale"]), width)
	_sync_ground(world, scroll)
	_sync_avatar(world, scroll)
	_sync_hazards(world, scroll)
	_sync_pickups(world, scroll)


func _build_bands(manifest: Dictionary, plane: String) -> void:
	var walk_surface_y := RunnerContract.ground_line_y(_config)
	for entry: Variant in (manifest.get("layers", []) as Array):
		var layer: Dictionary = entry
		if String(layer["plane"]) != plane:
			continue
		var texture := _package.texture(String(layer["image"]))
		if texture == null:
			# A band this run did not publish is a gap in the picture and is
			# said out loud, rather than drawn as a hole nobody can explain.
			push_error("runner stage: layer %s has no image at %s" % [layer["layer_id"], layer["image"]])
			continue
		var offset_raw: Variant = layer.get("vertical_offset")
		var layout := FamilyParallax.layer_layout(
			String(layer["vertical_anchor"]),
			0.0 if offset_raw == null else float(offset_raw),
			float(layer["height"]),
			float(layer["height"]),
			RunnerContract.VIEW_HEIGHT,
			walk_surface_y,
			float(layer["parallax"])
		)
		if layout.is_empty():
			push_error("runner stage: layer %s does not describe a band" % layer["layer_id"])
			continue
		var sprite := Sprite2D.new()
		sprite.texture = texture
		sprite.centered = false
		sprite.region_enabled = true
		# Three screens wide so a band never runs out mid-scroll.
		var scale_factor := float(layout["scale"])
		var tile_width := float(layer["width"]) * scale_factor
		sprite.region_rect = Rect2(
			0.0, 0.0, float(layer["width"]) * 3.0, float(layer["height"])
		)
		sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
		sprite.scale = Vector2(scale_factor, scale_factor)
		sprite.position = Vector2(-tile_width, float(layout["topY"]))
		sprite.z_index = (
			DEPTHS["background"] if plane == "background" else DEPTHS["foreground"]
		) + int(layer["order"])
		add_child(sprite)
		_bands.append(
			{
				"node": sprite,
				"parallax": float(layer["parallax"]),
				"scale": scale_factor,
				"width": tile_width,
				"originX": -tile_width,
			}
		)


func _build_avatar(manifest: Dictionary) -> void:
	var avatar: Dictionary = manifest.get("avatar", {})
	if avatar.is_empty():
		push_error("runner stage: this run publishes no avatar")
		return
	for entry: Variant in (avatar.get("motions", []) as Array):
		var motion: Dictionary = entry
		var texture := _package.texture(String(motion["atlas"]))
		if texture == null:
			push_error("runner stage: avatar motion %s has no atlas" % motion["state"])
			continue
		_avatar_frames[String(motion["state"])] = {
			"texture": texture,
			"columns": int(motion["columns"]),
			"fps": float(motion.get("frames_per_second", 12)),
			"loop": String(motion.get("playback_mode", "once")) == "loop",
			"frames": motion.get("canonical_frame_indices", [0]),
		}
	_avatar = Sprite2D.new()
	_avatar.centered = false
	_avatar.z_index = DEPTHS["avatar"]
	add_child(_avatar)


func _sync_avatar(world: RunnerWorld, _scroll: float) -> void:
	if _avatar == null:
		return
	var motion := String(world.avatar["motion"])
	var strip: Dictionary = _avatar_frames.get(motion, {})
	if strip.is_empty():
		# The manifest guarantees run, jump and death; anything else falls back
		# rather than vanishing, and says which state was missing.
		strip = _avatar_frames.get("run", {})
		if strip.is_empty():
			return
	if motion != _avatar_motion:
		_avatar_motion = motion
		_avatar_frame = 0
		_avatar_clock = 0.0
	var frames: Array = strip["frames"]
	_avatar_clock += get_process_delta_time() * float(strip["fps"])
	var advanced := int(_avatar_clock)
	if advanced > 0:
		_avatar_clock -= float(advanced)
		if bool(strip["loop"]):
			_avatar_frame = (_avatar_frame + advanced) % frames.size()
		else:
			_avatar_frame = mini(_avatar_frame + advanced, frames.size() - 1)
	var texture := strip["texture"] as Texture2D
	var columns := int(strip["columns"])
	var cell_width := float(texture.get_width()) / float(columns)
	var cell_height := float(texture.get_height())
	var index := int(frames[mini(_avatar_frame, frames.size() - 1)])
	_avatar.texture = texture
	_avatar.region_enabled = true
	_avatar.region_rect = Rect2(float(index) * cell_width, 0.0, cell_width, cell_height)
	# The body is sized by the manifest's own ruler rather than by the pixels
	# the atlas happens to carry: a redrawn strip at another resolution stands
	# exactly as tall.
	var height_px := float(_config["playerHeightTiles"]) * float(_config["tilePx"])
	var draw_scale := height_px / cell_height
	_avatar.scale = Vector2(draw_scale, draw_scale)
	var feet := RunnerContract.row_to_screen_y(float(world.avatar["y"]), _config)
	_avatar.position = Vector2(
		float(_config["avatarScreenX"]) - cell_width * draw_scale / 2.0,
		feet - cell_height * draw_scale
	)


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
	_ground_tiles.clear()
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


func _sync_hazards(world: RunnerWorld, scroll: float) -> void:
	_place(
		_hazards,
		RunnerSegments.streamed_hazards(world.segments),
		scroll,
		func(entry: Dictionary) -> Texture2D:
			return _prop_textures.get(String(entry["propId"])),
		func(entry: Dictionary) -> float:
			var surface := RunnerSegments.surface_row_at(
				world.segments, int(entry["worldColumn"])
			)
			if surface < 0:
				return -1.0
			var bottom := float(surface)
			if String(entry["anchor"]) == "overhead":
				bottom -= float(entry["clearanceRows"])
			return bottom,
		func(entry: Dictionary) -> float:
			var heights: Dictionary = _config["propHeightUnits"]
			return (
				float(heights.get(String(entry["propId"]), 1.0))
				* float(_config["playerHeightTiles"])
			)
	)


func _sync_pickups(world: RunnerWorld, scroll: float) -> void:
	var collected: Dictionary = world.obstacles["collected"]
	var remaining: Array = []
	for entry: Variant in RunnerSegments.streamed_pickups(world.segments):
		if not collected.has(RunnerObstaclesSystem.pickup_key(entry)):
			remaining.append(entry)
	_place(
		_pickups,
		remaining,
		scroll,
		func(entry: Dictionary) -> Texture2D:
			return _item_textures.get(String(entry["itemId"])),
		func(entry: Dictionary) -> float: return float(entry["row"]) + 1.0,
		func(_entry: Dictionary) -> float: return 1.0
	)


## Rebuild one layer of sprites from the streamed window.
##
## Rebuilt rather than pooled: the window holds a few dozen things at most, and
## a pool that has to be reconciled against a stream is where a stale sprite
## survives the chunk it belonged to.
func _place(
	parent: Node2D, entries: Array, scroll: float, texture_of: Callable,
	bottom_row_of: Callable, height_rows_of: Callable
) -> void:
	for child in parent.get_children():
		child.queue_free()
	var tile_px := float(_config["tilePx"])
	for entry: Variant in entries:
		var record: Dictionary = entry
		var texture: Texture2D = texture_of.call(record)
		if texture == null:
			continue
		var bottom_row: float = bottom_row_of.call(record)
		if bottom_row < 0.0:
			continue
		var height_rows: float = height_rows_of.call(record)
		var sprite := Sprite2D.new()
		sprite.texture = texture
		sprite.centered = false
		var height_px := height_rows * tile_px
		var draw_scale := height_px / float(texture.get_height())
		sprite.scale = Vector2(draw_scale, draw_scale)
		var width_px := float(texture.get_width()) * draw_scale
		sprite.position = Vector2(
			(float(record["worldColumn"]) + 0.5) * tile_px - scroll - width_px / 2.0,
			RunnerContract.row_to_screen_y(bottom_row, _config) - height_px
		)
		parent.add_child(sprite)
