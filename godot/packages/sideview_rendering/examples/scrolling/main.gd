extends Node2D

const Parallax = preload("res://addons/sideview_rendering/parallax.gd")
const ImageBaker = preload("res://addons/sideview_rendering/image_baker.gd")
const Refusal = preload("res://addons/sideview_rendering/refusal.gd")
const WIDTH := 640
const HEIGHT := 360
var _bands: Array[Dictionary] = []
var _scroll := 0.0

func _ready() -> void:
	# Original synthetic repeating art keeps this example independent of media,
	# generation, run manifests and complete games.
	for index in 3:
		var source := Image.create(128, 72, false, Image.FORMAT_RGBA8)
		for x in 128:
			var horizon := 18 + index * 15 + int(sin(float(x) * TAU / 128.0) * 8.0)
			for y in 72:
				var color := Color(0.12 + index * 0.07, 0.22 + index * 0.1, 0.34 + index * 0.08, 1.0)
				if index == 0 and y < horizon:
					color = Color(0.035, 0.055, 0.10, 1.0)
				elif y < horizon:
					color.a = 0.0
				source.set_pixel(x, y, color)
		var factor := 0.15 + float(index) * 0.3
		var layout := Parallax.layer_layout("canvas_cover", 0.0, 72.0, 72.0, HEIGHT, HEIGHT, factor)
		if Refusal.is_refusal(layout):
			_fail(layout)
			return
		var presentation := {"contrast": 0.88, "saturation": 0.8} if index == 0 else {}
		var texture: Variant = ImageBaker.texture(source, presentation, WIDTH, HEIGHT)
		if Refusal.is_refusal(texture):
			_fail(texture)
			return
		var sprite := Sprite2D.new()
		sprite.texture = texture
		sprite.centered = false
		sprite.region_enabled = true
		sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
		sprite.region_rect = Rect2(0, 0, WIDTH * 2, HEIGHT)
		sprite.position.y = layout["top_y"]
		# Ordering is this example's choice, not a required package ladder.
		sprite.z_index = index
		add_child(sprite)
		_bands.append({"sprite": sprite, "parallax": factor})

func _process(delta: float) -> void:
	_scroll += delta * 55.0
	for band in _bands:
		var offset: Variant = Parallax.band_tile_position(_scroll, band["parallax"], 1.0)
		if Refusal.is_refusal(offset):
			_fail(offset)
			return
		band["sprite"].position.x = -fposmod(float(offset), float(WIDTH))

func _fail(failure: Dictionary) -> void:
	push_error(Refusal.line(failure))
	get_tree().quit(1)
