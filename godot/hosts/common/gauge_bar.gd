class_name HostGaugeBar
extends Node2D

## The drawn half of `FamilyGaugeBar`: a capsule track with a gradient fill
## revealed by a crop.
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


## One capsule. The track is a dark rounded box with a rim; the fill is the
## spectrum across the same shape.
##
## The rounding is measured rather than drawn with a style box, because the crop
## has to reveal the leading pixels of a *texture* — a style box would have no
## pixels to crop.
static func _bake(width: int, height: int, is_track: bool) -> ImageTexture:
	var image := Image.create(maxi(1, width), maxi(1, height), false, Image.FORMAT_RGBA8)
	image.fill(Color(0.0, 0.0, 0.0, 0.0))
	var radius := float(height) / 2.0
	for y in height:
		for x in width:
			# Distance to the capsule's spine: the segment between the two
			# centres the rounded ends turn about.
			var point := Vector2(float(x) + 0.5, float(y) + 0.5)
			var spine_x := clampf(point.x, radius, float(width) - radius)
			var distance := point.distance_to(Vector2(spine_x, radius))
			if distance > radius:
				continue
			var color: Color
			if is_track:
				color = (
					FamilyGaugeBar.TRACK_RIM
					if distance > radius - FamilyGaugeBar.RIM_WIDTH
					else FamilyGaugeBar.TRACK_FILL
				)
			else:
				color = FamilyGaugeBar.color_at(float(x) / maxf(1.0, float(width - 1)))
			image.set_pixel(x, y, color)
	return ImageTexture.create_from_image(image)
