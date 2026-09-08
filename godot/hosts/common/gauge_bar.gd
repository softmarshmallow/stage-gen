class_name HostGaugeBar
extends Node2D

## The drawn half of `FamilyGaugeBar`: a rounded-rectangle track with a gradient
## fill revealed by a crop, and a border on each of them.
##
## A crop, not a scale. Scaling would drag the whole spectrum along with the fill
## and paint a half-empty bar in the same green as a full one, which is the one
## thing the gradient exists to prevent. Cropping leaves each colour at the
## fraction it belongs to and squares off the leading edge, which is what a bar
## draining should look like anyway.
##
## Both textures are baked once per size and shared by every bar drawn at that
## size, exactly as the browser's were.

static var _baked: Dictionary = {}

var _style_width: float = 0.0
var _style_height: float = 0.0
var _track: Sprite2D = null
var _fill: Sprite2D = null


static func of(width: float, height: float) -> HostGaugeBar:
	var bar := HostGaugeBar.new()
	bar._style_width = width
	bar._style_height = height
	var textures := _textures(width, height)
	bar._track = Sprite2D.new()
	bar._track.texture = textures["track"]
	bar._track.centered = false
	bar.add_child(bar._track)
	bar._fill = Sprite2D.new()
	bar._fill.texture = textures["fill"]
	bar._fill.centered = false
	bar._fill.region_enabled = true
	bar.add_child(bar._fill)
	return bar


## Redraw from a gauge. `dimmed` is the immunity window: the bar fades with it,
## so the readout itself says a blow connected rather than only the body saying
## it.
func show_gauge(value: float, max_value: float, dimmed: bool) -> void:
	var width := FamilyGaugeBar.fill_width(value, max_value, _style_width, _style_height)
	_fill.visible = width > 0.0
	if _fill.visible:
		_fill.region_rect = Rect2(0.0, 0.0, width, _style_height)
	modulate.a = FamilyGaugeBar.DIMMED_ALPHA if dimmed else 1.0


## The track and fill for one size, baked once.
static func _textures(width: float, height: float) -> Dictionary:
	var key := "%dx%d" % [int(width), int(height)]
	if _baked.has(key):
		return _baked[key]
	var made := {
		"track": _bake(int(width), int(height), true),
		"fill": _bake(int(width), int(height), false),
	}
	_baked[key] = made
	return made


## One bar. The track is the dark box with the outline around it; the fill is
## the spectrum inside the same shape, with its own darker edge and a lift down
## its height.
##
## The rounding is measured rather than drawn with a style box, because the crop
## has to reveal the leading pixels of a *texture* — a style box would have no
## pixels to crop. Both borders come off one distance, so they can never drift
## apart or leave a seam between them.
static func _bake(width: int, height: int, is_track: bool) -> ImageTexture:
	var image := Image.create(maxi(1, width), maxi(1, height), false, Image.FORMAT_RGBA8)
	image.fill(Color(0.0, 0.0, 0.0, 0.0))
	var rim_ends_at := FamilyGaugeBar.OUTLINE_WIDTH + FamilyGaugeBar.INNER_RIM_WIDTH
	for y in height:
		for x in width:
			var depth := FamilyGaugeBar.inset_depth(
				float(x) + 0.5,
				float(y) + 0.5,
				float(width),
				float(height),
				FamilyGaugeBar.CORNER_RADIUS
			)
			if depth <= 0.0:
				continue
			var color: Color
			if is_track:
				color = (
					FamilyGaugeBar.OUTLINE_COLOR
					if depth <= FamilyGaugeBar.OUTLINE_WIDTH
					else FamilyGaugeBar.TRACK_FILL
				)
			else:
				# The fill stops short of the outline, so the track's border is
				# what the bar is edged with however full it is.
				if depth <= FamilyGaugeBar.OUTLINE_WIDTH:
					continue
				color = FamilyGaugeBar.color_at(float(x) / maxf(1.0, float(width - 1)))
				var shade := FamilyGaugeBar.depth_multiplier(
					(float(y) + 0.5) / maxf(1.0, float(height))
				)
				if depth <= rim_ends_at:
					shade *= FamilyGaugeBar.INNER_RIM_SHADE
				color = Color(
					minf(1.0, color.r * shade),
					minf(1.0, color.g * shade),
					minf(1.0, color.b * shade),
					color.a
				)
			# A pixel the shape only partly covers is only partly drawn, which is
			# what keeps a three-pixel corner a corner rather than a staircase.
			color.a *= minf(1.0, depth)
			image.set_pixel(x, y, color)
	return ImageTexture.create_from_image(image)
