class_name WorldMap
extends CanvasLayer

## The M overlay: the splat plates recoloured, north up, with the camp and the
## player on top. Ported from `buildMap` / `drawMap`
## (viewer/index.html:2638-2748) and the `#map` CSS at :84-90.
##
## The base picture is built once, on the first open, at the splat's own
## resolution; the vectors are redrawn every frame the panel is up.

const CANVAS := 768.0
## `#map canvas { width: min(72vh, 72vw) }`.
const VIEW_SHARE := 0.72
const WEDGE_RADIUS := 46.0
const WEDGE_HALF_ANGLE := 0.55
const PLAYER_RADIUS := 4.5

const WATER := Color8(27, 43, 49)
const ROAD := Color8(201, 162, 107)
const BIOME_COLOURS := {
	"forest_floor": Color8(60, 90, 49),
	"dry_meadow": Color8(168, 147, 76),
	"mossy_bog": Color8(91, 120, 87),
	"grey_scree": Color8(140, 138, 132),
}
## A biome the palette has never heard of takes its channel's colour.
const CHANNEL_COLOURS := {
	"base": Color8(70, 96, 58),
	"r": Color8(160, 130, 80),
	"g": Color8(90, 118, 100),
	"b": Color8(130, 128, 122),
}

var package: Variant = null
## Whether this layer answers the M key itself. A frame owner that binds the
## map (none does today) should set it false.
var owns_keys: bool = true
var open: bool = false
var size_meters: float = 256.0

var _root: Control = null
var _panel: PanelContainer = null
var _view: MapView = null
var _legend: HBoxContainer = null
var _font: Font = null
var _built: bool = false


func setup(pkg, world, _fu) -> void:
	package = pkg
	layer = 31
	visible = false
	size_meters = float((world.manifest as Dictionary).get("ground", {}).get("size_meters", 256.0))
	_font = SystemFont.new()
	(_font as SystemFont).font_names = PackedStringArray(["ui-monospace", "SF Mono", "Menlo",
		"Monaco", "DejaVu Sans Mono", "monospace"])
	_root = Control.new()
	# Sized by `set_ui_scale`, not by anchors: a full-rect anchor would follow
	# the viewport's pixels and ignore the layer's scale.
	_root.set_anchors_preset(Control.PRESET_TOP_LEFT)
	_root.size = Vector2(1600.0, 900.0)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var theme := Theme.new()
	theme.default_font = _font
	theme.default_font_size = 13
	theme.set_color("font_color", "Label", Color("#e8e4dc"))
	_root.theme = theme
	add_child(_root)
	_build(world)


func _unhandled_key_input(event: InputEvent) -> void:
	if not owns_keys:
		return
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo and key.physical_keycode == KEY_M:
		toggle()


func set_mode(_mode: String) -> void:
	pass


func set_look(_look: String) -> void:
	pass


func handle_event(_event: Dictionary) -> void:
	pass


## The HUD's scale (the window's height over 900, times `--ui-scale`): the
## layer is scaled as a whole and its root shrunk to match, so the panel's own
## arithmetic stays in 1600x900 units.
func set_ui_scale(scale_factor: float) -> void:
	var s := maxf(0.25, scale_factor)
	transform = Transform2D(0.0, Vector2.ZERO).scaled(Vector2(s, s))
	if _root != null:
		var viewport := get_viewport()
		if viewport != null:
			_root.size = viewport.get_visible_rect().size / s


func set_open(value: bool) -> void:
	open = value
	visible = value
	if value and not _built:
		_build_base(_view)


func toggle() -> void:
	set_open(not open)


func status() -> Dictionary:
	return {"map": "open" if open else "closed"}


func update(world, _delta: float, cam: Dictionary) -> void:
	if not open or _view == null:
		return
	var player: Variant = world.player
	_view.player = Vector2(_num(player, "x", 0.0), _num(player, "z", 0.0))
	_view.yaw = float(cam.get("yaw", world.camera_yaw))
	_view.queue_redraw()
	_layout()


# ===========================================================================
# Building
# ===========================================================================

func _build(world) -> void:
	_panel = PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(12.0 / 255.0, 13.0 / 255.0, 16.0 / 255.0, 0.82)
	style.border_color = Color("#2c2f36")
	style.set_border_width_all(1)
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	style.content_margin_left = 10.0
	style.content_margin_right = 10.0
	style.content_margin_top = 10.0
	style.content_margin_bottom = 10.0
	_panel.add_theme_stylebox_override("panel", style)
	_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.add_child(_panel)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 7)
	_panel.add_child(column)

	var frame := Control.new()
	frame.name = "frame"
	frame.clip_contents = true
	column.add_child(frame)

	_view = MapView.new()
	_view.size = Vector2(CANVAS, CANVAS)
	_view.font = _font
	_view.size_meters = size_meters
	var camp: Dictionary = (world.manifest as Dictionary).get("layout", {}).get("camp_position",
		{"x": 0.0, "z": 0.0})
	_view.camp = Vector2(float(camp.get("x", 0.0)), float(camp.get("z", 0.0)))
	# The other set pieces the generator sited; the camp is the triangle.
	var pieces: Array[Vector2] = []
	for piece: Dictionary in (world.manifest as Dictionary).get("layout", {}).get("set_pieces", []):
		if String(piece.get("set_piece", "")) == "camp":
			continue
		pieces.append(Vector2(float(piece.get("x", 0.0)), float(piece.get("z", 0.0))))
	_view.set_pieces = pieces
	frame.add_child(_view)

	_legend = HBoxContainer.new()
	_legend.add_theme_constant_override("separation", 12)
	column.add_child(_legend)
	_build_base(_view)
	_build_legend(world)


## `buildMap` (:2652-2703): one flat colour per splat cell.
func _build_base(view: MapView) -> void:
	if _built or package == null or view == null:
		return
	var ground: Dictionary = _ground()
	var splat_ref := str(ground.get("splat", {}).get("image", ""))
	var biome_ref := str(ground.get("biome_splat", {}).get("image", ""))
	if splat_ref == "" or biome_ref == "":
		return
	var structure: Image = package.image(splat_ref)
	var weights: Image = package.image(biome_ref)
	if structure == null or weights == null:
		return
	_built = true
	var cells := structure.get_width()
	var structure_bytes := _rgba8(structure)
	var weight_bytes := _rgba8(weights, cells)
	var by_channel := _channels()
	var out := PackedByteArray()
	out.resize(cells * cells * 4)
	for index: int in cells * cells:
		var o := index * 4
		var colour: Color = by_channel["base"]
		if structure_bytes[o + 3] <= 127:
			colour = WATER
		elif structure_bytes[o] > 127:
			colour = ROAD
		elif weight_bytes[o] > 127:
			colour = by_channel["r"]
		elif weight_bytes[o + 1] > 127:
			colour = by_channel["g"]
		elif weight_bytes[o + 2] > 127:
			colour = by_channel["b"]
		out[o] = int(colour.r8)
		out[o + 1] = int(colour.g8)
		out[o + 2] = int(colour.b8)
		out[o + 3] = 255
	var image := Image.create_from_data(cells, cells, false, Image.FORMAT_RGBA8, out)
	view.base = ImageTexture.create_from_image(image)


func _build_legend(_world) -> void:
	var by_channel := _channels()
	var ids := _channel_ids()
	for channel: String in ["base", "r", "g", "b"]:
		if str(ids.get(channel, "")) == "":
			continue
		_legend.add_child(_legend_entry(str(ids[channel]).replace("_", " "), by_channel[channel]))
	_legend.add_child(_legend_entry("road", ROAD))
	_legend.add_child(_legend_entry("water", WATER))


func _legend_entry(label: String, colour: Color) -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	var swatch := ColorRect.new()
	swatch.color = colour
	swatch.custom_minimum_size = Vector2(10.0, 10.0)
	swatch.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(swatch)
	var text := Label.new()
	text.text = label
	text.add_theme_font_size_override("font_size", 11)
	text.modulate.a = 0.85
	row.add_child(text)
	return row


func _layout() -> void:
	var view_size: Vector2 = _root.size
	var side := minf(view_size.y * VIEW_SHARE, view_size.x * VIEW_SHARE)
	var frame: Control = _panel.get_child(0).get_node("frame")
	frame.custom_minimum_size = Vector2(side, side)
	_view.scale = Vector2(side / CANVAS, side / CANVAS)
	_panel.size = _panel.get_combined_minimum_size()
	_panel.position = (view_size - _panel.size) * 0.5


func _ground() -> Dictionary:
	if package == null:
		return {}
	return (package.manifest as Dictionary).get("ground", {})


## Which biome sits on each splat channel, and the colour the map paints it.
func _channels() -> Dictionary:
	var ids := _channel_ids()
	var out := {}
	for channel: String in ["base", "r", "g", "b"]:
		var id := str(ids.get(channel, ""))
		if id != "" and BIOME_COLOURS.has(id):
			out[channel] = BIOME_COLOURS[id]
		else:
			out[channel] = CHANNEL_COLOURS[channel]
	return out


func _channel_ids() -> Dictionary:
	var ids := {}
	var biomes: Dictionary = _ground().get("biomes", {})
	for id: String in biomes.keys():
		var block: Dictionary = biomes[id]
		ids[str(block.get("weight_channel", "base"))] = id
	return ids


func _rgba8(image: Image, cells: int = 0) -> PackedByteArray:
	var copy := Image.new()
	copy.copy_from(image)
	if copy.get_format() != Image.FORMAT_RGBA8:
		copy.convert(Image.FORMAT_RGBA8)
	# The viewer draws both plates into a canvas the splat's size, so a biome
	# plate at another resolution is stretched to match.
	if cells > 0 and copy.get_width() != cells:
		copy.resize(cells, cells, Image.INTERPOLATE_NEAREST)
	return copy.get_data()


func _num(object: Variant, key: String, fallback: float) -> float:
	if object is Dictionary:
		return float((object as Dictionary).get(key, fallback))
	if object is Object and key in object:
		return float(object.get(key))
	return fallback


## The 768-pixel canvas: the recoloured plate, the camp, the player.
class MapView:
	extends Control

	var base: Texture2D = null
	var font: Font = null
	var size_meters: float = 256.0
	var camp := Vector2.ZERO
	var set_pieces: Array[Vector2] = []
	var player := Vector2.ZERO
	var yaw: float = 0.0

	func _to_map(point: Vector2) -> Vector2:
		return Vector2(
			((point.x + size_meters * 0.5) / size_meters) * WorldMap.CANVAS,
			((point.y + size_meters * 0.5) / size_meters) * WorldMap.CANVAS)

	func _draw() -> void:
		var box := Rect2(0.0, 0.0, WorldMap.CANVAS, WorldMap.CANVAS)
		if base != null:
			draw_texture_rect(base, box, false)
		else:
			draw_rect(box, WorldMap.WATER)
		draw_rect(box, Color("#3a3d44"), false, 1.0)

		# The camp: a tent-shaped triangle where the layout put it.
		var c := _to_map(camp)
		var triangle := PackedVector2Array([
			Vector2(c.x, c.y - 8.0), Vector2(c.x + 7.0, c.y + 5.0), Vector2(c.x - 7.0, c.y + 5.0),
		])
		draw_colored_polygon(triangle, Color("#f2b04a"))
		var outline := triangle.duplicate()
		outline.append(triangle[0])
		draw_polyline(outline, Color("#1a1208"), 1.5)

		# The player, with the camera's heading as a wedge: the rig sits at
		# (sin yaw, cos yaw) behind the target, so it looks along (-sin, -cos).
		var p := _to_map(player)
		var heading := atan2(-cos(yaw), -sin(yaw))
		var wedge := PackedVector2Array([p])
		var steps := 16
		for i: int in steps + 1:
			var angle := heading - WorldMap.WEDGE_HALF_ANGLE \
				+ (2.0 * WorldMap.WEDGE_HALF_ANGLE) * (float(i) / float(steps))
			wedge.append(p + Vector2(cos(angle), sin(angle)) * WorldMap.WEDGE_RADIUS)
		draw_colored_polygon(wedge, Color(1.0, 1.0, 1.0, 0.38))
		draw_circle(p, WorldMap.PLAYER_RADIUS, Color.WHITE)
		draw_arc(p, WorldMap.PLAYER_RADIUS, 0.0, TAU, 24, Color("#111111"), 1.5)

		# The other set pieces: a ring where the layout sited each one.
		for piece: Vector2 in set_pieces:
			var s := _to_map(piece)
			draw_arc(s, 6.0, 0.0, TAU, 20, Color("#f2b04a"), 2.0)

		# A scale bar, so the map says how far things are.
		var meters := 100.0 if size_meters >= 400.0 else 50.0 if size_meters >= 200.0 else 10.0
		var bar := (meters / size_meters) * WorldMap.CANVAS
		draw_rect(Rect2(10.0, WorldMap.CANVAS - 30.0, bar + 12.0, 20.0), Color(0.0, 0.0, 0.0, 0.45))
		draw_rect(Rect2(16.0, WorldMap.CANVAS - 17.0, bar, 3.0), Color.WHITE)
		if font != null:
			draw_string(font, Vector2(16.0, WorldMap.CANVAS - 21.0), "%d m" % int(meters),
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color.WHITE)
