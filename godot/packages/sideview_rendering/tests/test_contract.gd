extends RefCounted

const Parallax = preload("res://addons/sideview_rendering/parallax.gd")
const Pixels = preload("res://addons/sideview_rendering/pixels.gd")
const ImageBaker = preload("res://addons/sideview_rendering/image_baker.gd")
const Refusal = preload("res://addons/sideview_rendering/refusal.gd")

func run(h) -> void:
	_layout(h)
	_admission(h)
	_images(h)
	h.done()

func _layout(h) -> void:
	var expected := {"canvas_cover": 0.0, "screen_center": 342.0, "screen_top": 72.0, "screen_bottom": 612.0, "walk_surface": 392.0}
	for anchor: String in expected:
		var layout := Parallax.layer_layout(anchor, 0.4, 1200.0, 300.0, 720.0, 500.0, 0.25)
		h.assert_false(Refusal.is_refusal(layout), "supported anchor: " + anchor)
		h.assert_near(layout["scale"], 0.6, 1e-12, "reference frame determines scale")
		h.assert_near(layout["rendered_height"], 180.0, 1e-12, "trimmed height sets visible height")
		h.assert_near(layout["top_y"], expected[anchor], 1e-12, "anchor places top: " + anchor)
		h.assert_eq(layout["space"], "world" if anchor == "walk_surface" else "screen", "anchor chooses coordinate space")
		h.assert_eq(layout["vertical_scroll_factor"], 1.0 if anchor == "walk_surface" else 0.25, "world anchored layers follow vertical camera fully")
	h.assert_eq(Parallax.band_tile_position(360.0, 0.25, 0.6), 150.0, "scroll converts into texture space")
	h.assert_eq(Parallax.band_tile_position(-360.0, 0.25, 0.6), -150.0, "negative scroll is valid")

func _admission(h) -> void:
	for anchor in ["", "unknown", "screen-center"]:
		h.assert_true(Refusal.is_refusal(Parallax.layer_layout(anchor, 0.0, 100.0, 50.0, 720.0, 500.0, 0.5)), "unknown anchors refused")
	for index in range(1, 7):
		for value in [NAN, INF, -INF]:
			var args := ["screen_center", 0.0, 100.0, 50.0, 720.0, 500.0, 0.5]
			args[index] = value
			h.assert_true(Refusal.is_refusal(Parallax.layer_layout.callv(args)), "nonfinite layout input refused")
	for index in [2, 3, 4]:
		var args := ["screen_center", 0.0, 100.0, 50.0, 720.0, 500.0, 0.5]
		args[index] = 0.0
		h.assert_true(Refusal.is_refusal(Parallax.layer_layout.callv(args)), "zero dimensions refused")
	h.assert_true(Refusal.is_refusal(Parallax.layer_layout("screen_center", 0.0, 1e-300, 50.0, 1e300, 500.0, 0.5)), "layout overflow refused")
	for args in [[NAN, 1.0, 1.0], [0.0, INF, 1.0], [0.0, 1.0, 0.0], [1.0, -1.0, 1.0], [1e300, 1e300, 1.0]]:
		h.assert_true(Refusal.is_refusal(Parallax.band_tile_position.callv(args)), "invalid scroll refused")
	for field in ["contrast", "saturation", "atmosphere_strength", "detail_blur_screen_pixels"]:
		for value in [NAN, INF, -1.0, {}, "bad"]:
			h.assert_true(Refusal.is_refusal(Pixels.validate_presentation({field: value})), "invalid presentation number refused")
	for color in ["#123", "#gg0000", "#0x1234", "#12345678", []]:
		h.assert_true(Refusal.is_refusal(Pixels.validate_presentation({"atmosphere_color": color})), "invalid atmosphere color refused")
	h.assert_true(Refusal.is_refusal(Pixels.validate_presentation({"atmosphere_strength": 1.1})), "strength outside blend range refused")
	h.assert_true(Refusal.is_refusal(Pixels.validate_presentation({"detail_blur_screen_pixels": 1e300})), "unrepresentable blur kernel refused")
	h.assert_true(Refusal.is_refusal(Pixels.present_pixels(PackedByteArray([1, 2, 3, 4]), 9223372036854775807, 4, {}, 1.0)), "dimension product cannot overflow before byte admission")

func _images(h) -> void:
	var source := Image.create(16, 8, false, Image.FORMAT_RGBA8)
	for y in 8:
		for x in 16:
			source.set_pixel(x, y, Color(float(x) / 15.0, 1.0 - float(y) / 7.0, 0.2, float((x + y) % 5) / 4.0))
	var original := source.get_data()
	var settings := {"contrast": 0.88, "saturation": 0.86, "atmosphere_color": "#b8dcf0", "atmosphere_strength": 0.18, "detail_blur_screen_pixels": 1.4}
	# Recorded from the pre-extraction image loader/baker, including mip levels.
	# These hashes are independent of the new package implementation.
	var expected := ["6d9cab918bf5170112fc785b2c70c8bb558f5a54b9a3eaeec0a9a3684dcd1725", "31476ae58cd76e63c32bc820f1b4c2a1ad87a53e980ef3287f739122cd391455", "59df421058ea38baf51cd0b0a36998683f74880b6f28b169ac96d6d44c84627e", "9bbfe371f858d00d178b7f4ddc00aeab73d7727d4ff3f7d285c530a7463cd4dd", "d4e497ca4a4c909d42c5f0b17bf0cb5f5d346d8b038ef564904d22c0b092c580", "b15179d8f05b74068eb26d73be1d7713fedff4358de05799945ea4b59874f54e", "af173dd7eadd93e4fc5cdb0670669626677bf58f344166e9a9ff662e0e1de9da", "76b429d1c84608055c302dc6c8332dcd8b5e2ec660b472fceaf52bafaf73cec3", "4aa1828518e553ca9381ef916901b1a49460d107f801588ba8e44c8ff182c8b1"]
	var case_index := 0
	for size in [Vector2i(16, 8), Vector2i(32, 16), Vector2i(7, 5)]:
		for presentation in [{}, {"contrast": 0.88, "saturation": 0.86, "atmosphere_color": "#b8dcf0", "atmosphere_strength": 0.18}, settings]:
			var image: Image = ImageBaker.image(source, presentation, size.x, size.y)
			var hash := HashingContext.new()
			hash.start(HashingContext.HASH_SHA256)
			hash.update(image.get_data())
			h.assert_eq(hash.finish().hex_encode(), expected[case_index], "complete image/mips retain pre-extraction pixels")
			case_index += 1
	var serial: Image = ImageBaker.image(source, settings, 32, 16, 1)
	for strips in [0, 2, 3, 8, 16]:
		var parallel: Image = ImageBaker.image(source, settings, 32, 16, strips)
		h.assert_eq(parallel.get_data(), serial.get_data(), "strip count preserves every base and mip pixel")
	h.assert_eq(source.get_data(), original, "source image is immutable")
	h.assert_true(serial.has_mipmaps(), "baked image includes mipmaps")
	var neutral: Image = ImageBaker.image(source, {}, 16, 8)
	h.assert_eq(neutral.get_data().slice(0, original.size()), original, "neutral base level unchanged")
	var texture: ImageTexture = ImageBaker.texture(source, settings, 32, 16, 1)
	h.assert_eq(texture.get_image().get_data(), serial.get_data(), "texture upload preserves the complete image")
	for args in [[null, {}, 2, 2], [Image.new(), {}, 2, 2], [source, {}, 0, 8], [source, {}, 16, -1], [source, {"saturation": NAN}, 16, 8]]:
		h.assert_true(Refusal.is_refusal(ImageBaker.image.callv(args)), "invalid image request refused")
	h.assert_true(Refusal.is_refusal(ImageBaker.image(source, {}, 16, 8, 17)), "unsupported strip count refused")
	# A kernel wider than a repeat period still wraps positively. Each row is
	# constant, so horizontal blur must preserve it even at a one-pixel period.
	for width in [1, 2, 3]:
		var tiny := Image.create(width, 1, false, Image.FORMAT_RGBA8)
		tiny.fill(Color(0.2, 0.4, 0.8, 1.0))
		var blurred: Variant = Pixels.present_pixels(tiny.get_data(), width, 1, {"detail_blur_screen_pixels": 2.0}, 1.0)
		h.assert_eq(blurred, tiny.get_data(), "wide kernels wrap narrow repeat periods")
