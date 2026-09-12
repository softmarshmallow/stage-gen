class_name HostCutInView
extends CanvasLayer

## A cut-in on screen: the torn plate, the striped interior behind the portrait,
## the banner, and the scrim under all of it.
##
## A port of `web/lib/families/screen-fx/cut-in-view.ts`. `FamilyCutIn` says
## where everything is at a given millisecond; this puts it there. Every object
## sits in screen space and is positioned from the frame's numbers each tick —
## no tween, no timer, so the same elapsed time always draws the same picture.
##
## Host-side rather than family-side because it is nodes: the family may not
## extend a scene class. It is under `hosts/common` rather than the runner's own
## view because the platformer plays the same moments from the same block.
##
## The interior is composed inside the plate's own silhouette. Godot clips
## children to a parent's drawn alpha, so the plate *is* the mask — no eraser
## texture, no inverse-alpha canvas, and no dynamic texture to keep in step with
## a resize. The plate is then drawn once more on top in multiply, so its ink rim
## stays over the face rather than under it — through `ink.gdshader`, because
## Godot's multiply and the browser's are not the same arithmetic and the
## difference blacked out the whole world behind the moment.
##
## Nothing drew this before. The moment ran on schedule — the world froze for its
## ninety-eight frames and then released — against a picture that was not there.

const BACKDROP_COLOR := Color(1.0, 0.290, 0.110)
const STRIPE_COLOR := Color(1.0, 0.471, 0.275)
const SHADOW_COLOR := Color(0.039, 0.031, 0.047)
const BANNER_FILL := Color(0.055, 0.047, 0.063)
const BANNER_WIDTH := 620.0
const BANNER_HEIGHT := 128.0
## Shadow offset under the rip, in group heights.
const SHADOW_OFFSET_FRACTION := 0.021
## Stripe period and width, in group heights, and the stripe's slant.
const STRIPE_PERIOD_FRACTION := 0.112
const STRIPE_WIDTH_FRACTION := 0.035
const STRIPE_SLANT := 0.55

var _view_width: float = 0.0
var _view_height: float = 0.0
var _group_width: float = 0.0
var _group_height: float = 0.0
var _bindings: Dictionary = {}
var _worn: String = ""

var _scrim: ColorRect = null
var _group: Node2D = null
var _shadow: Sprite2D = null
var _shadow_material: ShaderMaterial = null
var _clip: Sprite2D = null
var _interior: Node2D = null
var _backdrop: ColorRect = null
var _stripes: Node2D = null
var _portrait: Sprite2D = null
var _ink: Sprite2D = null
var _banner: Node2D = null
var _title: Label = null
var _subtitle: Label = null
var _stripe_phase: float = 0.0


## Build the view from a package's `fx` block, or null when it binds no moment.
static func of(
	package: HostRunDir, view_width: float, view_height: float, layer: int
) -> HostCutInView:
	var fx: Dictionary = package.manifest.get("fx", {})
	var cut_in: Dictionary = fx.get("cut_in", {})
	if cut_in.is_empty():
		return null
	var frame: Dictionary = cut_in.get("frame", {})
	var plate := package.texture(String(frame.get("asset", "")))
	if plate == null:
		push_error("cut-in view: the frame plate could not be read")
		return null
	var portraits := {}
	for entry: Variant in (cut_in.get("portraits", []) as Array):
		var portrait: Dictionary = entry
		portraits[String(portrait["portrait_id"])] = portrait
	var bindings := {}
	for entry: Variant in (fx.get("moments", []) as Array):
		var moment: Dictionary = entry
		if String(moment.get("effect", "")) != "cut_in":
			continue
		var portrait: Dictionary = portraits.get(String(moment.get("portrait_id", "")), {})
		if portrait.is_empty():
			push_error("cut-in view: moment %s names a portrait this run does not publish" % moment["moment"])
			continue
		var texture := package.texture(String(portrait["asset"]))
		if texture == null:
			continue
		var canvas: Dictionary = portrait.get("canvas", {})
		bindings[String(moment["moment"])] = {
			"texture": texture,
			"aspect": float(canvas.get("width", 1)) / maxf(1.0, float(canvas.get("height", 1))),
			"placement": portrait.get("placement", {}),
			"title": String(moment.get("title", "")),
			"subtitle": String(moment.get("subtitle", "")),
		}
	if bindings.is_empty():
		return null

	var view := HostCutInView.new()
	view.layer = layer
	view._view_width = view_width
	view._view_height = view_height
	view._bindings = bindings
	var canvas_frame: Dictionary = frame.get("canvas", {})
	# The group keeps the plate's own aspect, spanning the canvas across.
	view._group_width = _even(view_width)
	view._group_height = _even(
		view_width * float(canvas_frame.get("height", 1)) / maxf(1.0, float(canvas_frame.get("width", 1)))
	)
	view._build(plate)
	view.hide_moment()
	return view


func _build(plate: Texture2D) -> void:
	_scrim = ColorRect.new()
	_scrim.color = Color(0.0, 0.0, 0.0, 1.0)
	_scrim.size = Vector2(_view_width, _view_height)
	_scrim.modulate.a = 0.0
	add_child(_scrim)

	_group = Node2D.new()
	add_child(_group)

	_shadow = Sprite2D.new()
	_shadow.texture = plate
	_shadow.centered = true
	_shadow_material = ShaderMaterial.new()
	_shadow_material.shader = load("res://scenes/common/shaders/fill.gdshader")
	_shadow_material.set_shader_parameter("amount", 1.0)
	_shadow_material.set_shader_parameter("fill_color", SHADOW_COLOR)
	_shadow.material = _shadow_material
	_group.add_child(_shadow)

	# The plate draws itself and clips whatever is inside it to its own alpha,
	# which is the mask the browser had to build an inverse-alpha canvas for.
	_clip = Sprite2D.new()
	_clip.texture = plate
	_clip.centered = true
	_clip.clip_children = CanvasItem.CLIP_CHILDREN_AND_DRAW
	_group.add_child(_clip)

	# Children of the plate work in group coordinates with the origin top-left,
	# which is the space the published placement is authored in.
	_interior = Node2D.new()
	_interior.position = Vector2(-_group_width / 2.0, -_group_height / 2.0)
	_clip.add_child(_interior)
	_backdrop = ColorRect.new()
	_backdrop.color = BACKDROP_COLOR
	_backdrop.size = Vector2(_group_width, _group_height)
	_interior.add_child(_backdrop)
	_stripes = Node2D.new()
	_stripes.draw.connect(_draw_stripes)
	_interior.add_child(_stripes)
	_portrait = Sprite2D.new()
	_portrait.centered = true
	_interior.add_child(_portrait)

	_ink = Sprite2D.new()
	_ink.texture = plate
	_ink.centered = true
	var ink := ShaderMaterial.new()
	ink.shader = load("res://scenes/common/shaders/ink.gdshader")
	_ink.material = ink
	_group.add_child(_ink)

	_banner = Node2D.new()
	_banner.draw.connect(_draw_banner)
	add_child(_banner)
	_title = _label(40, Color(1.0, 1.0, 1.0))
	_subtitle = _label(28, Color(1.0, 0.863, 0.784))


## Apply one choreography frame for one moment.
##
## The signature `FamilyCutIn`'s system calls: `sync(frame, moment)`.
func sync(frame: Dictionary, moment: String) -> void:
	if frame.is_empty():
		return
	if not _wear(moment):
		return
	visible = true
	var group_scale := float(frame["ripScale"])
	var center := Vector2(
		_view_width / 2.0 + float(frame["ripX"]) * _view_width, _view_height / 2.0
	)
	_group.position = center
	_group.scale = Vector2(group_scale, group_scale)
	_scrim.modulate.a = float(frame["dim"])
	_shadow.position = Vector2.ONE * (SHADOW_OFFSET_FRACTION * _group_height)

	var binding: Dictionary = _bindings[_worn]
	var placement: Dictionary = binding["placement"]
	var portrait_height := (
		float(placement.get("scale", 0.6)) * _group_height * float(frame["bustScale"])
	)
	var portrait_width := portrait_height * float(binding["aspect"])
	var texture: Texture2D = binding["texture"]
	_portrait.position = Vector2(
		(float(placement.get("x", 0.5)) + float(frame["bustDx"])) * _group_width,
		float(placement.get("y", 0.5)) * _group_height
	)
	_portrait.scale = Vector2(
		portrait_width / maxf(1.0, float(texture.get_width())),
		portrait_height / maxf(1.0, float(texture.get_height()))
	)
	_stripe_phase = float(frame["stripePhase"])
	_stripes.queue_redraw()

	var banner_x := (
		_view_width - BANNER_WIDTH - 40.0 + float(frame["bannerX"]) * _view_width
	)
	var banner_y := _view_height - BANNER_HEIGHT - 36.0
	_banner.position = Vector2(banner_x, banner_y)
	_banner.queue_redraw()
	_title.position = Vector2(banner_x + 70.0, banner_y + 16.0)
	_subtitle.position = Vector2(banner_x + 70.0, banner_y + 70.0)


func hide_moment() -> void:
	visible = false


## Swap in the plate and the two lines this moment is announced with. False when
## the package binds nothing for it, which is said once rather than every frame.
func _wear(moment: String) -> bool:
	if moment == _worn:
		return true
	if not _bindings.has(moment):
		push_warning("cut-in view: no portrait bound for moment %s" % moment)
		return false
	_worn = moment
	var binding: Dictionary = _bindings[moment]
	_portrait.texture = binding["texture"]
	_title.text = String(binding["title"]).to_upper()
	_subtitle.text = String(binding["subtitle"]).to_upper()
	return true


func _draw_stripes() -> void:
	var period := STRIPE_PERIOD_FRACTION * _group_height
	var width := STRIPE_WIDTH_FRACTION * _group_height
	var offset := fposmod(_stripe_phase, 1.0)
	var slant := _group_height * STRIPE_SLANT
	var x := -_group_height - period
	while x < _group_width + period:
		var x0 := x + offset * period
		_stripes.draw_colored_polygon(
			PackedVector2Array(
				[
					Vector2(x0, _group_height),
					Vector2(x0 + slant, 0.0),
					Vector2(x0 + slant + width, 0.0),
					Vector2(x0 + width, _group_height),
				]
			),
			STRIPE_COLOR
		)
		x += period


func _draw_banner() -> void:
	var shape := PackedVector2Array(
		[
			Vector2(40.0, 0.0),
			Vector2(BANNER_WIDTH, 0.0),
			Vector2(BANNER_WIDTH - 40.0, BANNER_HEIGHT),
			Vector2(0.0, BANNER_HEIGHT),
		]
	)
	_banner.draw_colored_polygon(shape, BANNER_FILL)
	var rule := PackedVector2Array(
		[
			Vector2(46.0, 8.0),
			Vector2(BANNER_WIDTH - 8.0, 8.0),
			Vector2(BANNER_WIDTH - 46.0, BANNER_HEIGHT - 8.0),
			Vector2(8.0, BANNER_HEIGHT - 8.0),
			Vector2(46.0, 8.0),
		]
	)
	_banner.draw_polyline(rule, Color(1.0, 1.0, 1.0), 3.0, true)


func _label(size: int, color: Color) -> Label:
	var label := Label.new()
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	add_child(label)
	return label


## An odd side would leave the plate a pixel short of the interior it clips.
static func _even(value: float) -> float:
	var rounded := int(round(value))
	return float(rounded if rounded % 2 == 0 else rounded + 1)
