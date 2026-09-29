extends RefCounted

const Pixels = preload("res://addons/sideview_rendering/pixels.gd")

## Exercise this game's real manifest-to-layer adapter using an in-memory run
## image. Package mechanism tests separately pin browser-derived pixel values.
func run(h: TestHarness) -> void:
	var source := Image.create(16, 8, false, Image.FORMAT_RGBA8)
	for y in 8:
		for x in 16:
			source.set_pixel(x, y, Color(float(x) / 15.0, 1.0 - float(y) / 7.0, 0.2, 1.0))
	var package := HostRunDir.new()
	package._images["band.png"] = source
	var presentation := {"contrast": 0.88, "saturation": 0.86, "atmosphere_color": "#b8dcf0", "atmosphere_strength": 0.18}
	var stage := PlatformerStage.new()
	stage._package = package
	# Maps can omit these optional sheets. Absence never enters the content
	# loader, which correctly refuses an empty reference as invalid content.
	stage._build_portals(null, {})
	stage._build_climbables(null, {})
	h.assert_eq(package._configured_root, "", "absent optional map sheets do not configure content loading")
	stage._build_bands({"layers": [{
		"layer_id": "test", "plane": "background", "order": 2, "parallax": 0.25,
		"asset": {"path": "band.png", "width": 16, "height": 8},
		"placement": {"vertical_anchor": "screen_top", "source_height": 720, "trimmed_height": 8},
		"presentation": presentation,
	}]}, "background")
	h.assert_eq(stage._bands.size(), 1, "game adapter builds one selected band")
	if stage._bands.size() != 1:
		stage.free()
		h.done()
		return
	var sprite: Sprite2D = stage._bands[0]["node"]
	h.assert_eq(sprite.texture.get_image().get_data().slice(0, 16 * 8 * 4), Pixels.present_pixels(source.get_data(), 16, 8, presentation, 1.0), "game draws the presented pixels instead of the raw asset")
	h.assert_eq(sprite.z_index, stage.DEPTHS["background"] + 2, "game owns its plane and layer ordering")
	h.assert_eq(sprite.position.y, 0.0, "game adapts its authored vertical anchor")
	h.assert_true(sprite.region_rect.size.x >= 1280.0, "whole repeats cover the game viewport")
	h.assert_eq(sprite.texture_repeat, CanvasItem.TEXTURE_REPEAT_ENABLED, "game enables horizontal repetition")
	stage.free()
	_display_scale_and_speed(h, source, presentation)
	h.done()


## An authored display scale draws the band larger from its anchor, and a band
## moves at its parallax factor in screen pixels whatever size it is drawn at.
func _display_scale_and_speed(h: TestHarness, source: Image, presentation: Dictionary) -> void:
	var package := HostRunDir.new()
	package._images["band.png"] = source
	var stage := PlatformerStage.of(package, {})
	stage._build_bands({"layers": [{
		"layer_id": "grown", "plane": "background", "order": 1, "parallax": 0.25,
		"asset": {"path": "band.png", "width": 16, "height": 8},
		"placement": {"vertical_anchor": "screen_bottom", "vertical_offset": 0.0, "source_height": 16, "trimmed_height": 8, "display_scale": 1.5},
		"presentation": presentation,
	}]}, "background")
	var sprite: Sprite2D = stage._bands[0]["node"]
	# 720 / 16 is the fitted scale; 1.5 more makes each source pixel 67.5 screen pixels.
	h.assert_eq(sprite.texture.get_width(), 1080, "display scale widens the drawn tile")
	h.assert_eq(sprite.texture.get_height(), 540, "display scale heightens the drawn tile")
	h.assert_eq(sprite.position.y, 720.0 - 540.0, "a bottom-anchored band still meets the screen bottom")
	var world := PlatformerWorld.new()
	world.hold = true
	stage.sync(world, Vector2(400.0, 0.0))
	h.assert_eq(sprite.region_rect.position.x, 100.0, "a band moves at its parallax factor in screen pixels")
	stage.free()
