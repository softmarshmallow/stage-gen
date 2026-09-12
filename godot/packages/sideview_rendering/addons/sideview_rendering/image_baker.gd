extends RefCounted

## Render-resolution image baking. Content resolution remains consumer-owned.

const Pixels = preload("pixels.gd")
const Refusal = preload("refusal.gd")

## More strips than this buys nothing and costs a task each: the passes are
## memory-bound long before the core count runs out.
const MAX_STRIPS := 16


## Copy an image, resize with Lanczos, apply presentation and generate mipmaps.
## Returns an Image or a structured refusal. No file IO and no source mutation.
static func image(
	source: Image, presentation: Dictionary, render_width: int, render_height: int,
	strip_count: int = 0
) -> Variant:
	if source == null or source.is_empty() or source.is_compressed():
		return Refusal.of("sideview/image", "source must be a nonempty decompressed image", "source")
	if render_width <= 0 or render_height <= 0:
		return Refusal.of("sideview/dimensions", "render dimensions must be positive", "render_size")
	if strip_count < 0 or strip_count > MAX_STRIPS:
		return Refusal.of("sideview/strips", "strip count must be 0 (automatic) or 1 through 16", "strip_count")
	var failure := Pixels.validate_presentation(presentation, 1.0)
	if not failure.is_empty():
		return failure
	var working := Image.new()
	working.copy_from(source)
	if working.get_format() != Image.FORMAT_RGBA8:
		working.convert(Image.FORMAT_RGBA8)
	var width := render_width
	var height := render_height
	if working.get_width() != width or working.get_height() != height:
		working.resize(width, height, Image.INTERPOLATE_LANCZOS)
	if working.get_width() != width or working.get_height() != height:
		return Refusal.of("sideview/dimensions", "image resize did not produce the requested dimensions", "render_size")

	if not Pixels._is_neutral(presentation):
		var pixels := _colour(working.get_data(), width, height, presentation, strip_count)
		# Screen resolution, so the authored screen-pixel sigma is the sigma.
		var sigma := Pixels._blur_sigma(presentation, 1.0)
		if sigma >= Pixels.MIN_SIGMA:
			var kernel := Pixels._gaussian_kernel(sigma)
			pixels = _blur(pixels, width, height, kernel, true, strip_count)
			pixels = _blur(pixels, width, height, kernel, false, strip_count)
		working = Image.create_from_data(width, height, false, Image.FORMAT_RGBA8, pixels)

	working.generate_mipmaps()
	return working


## The same baked image, uploaded as a texture when the caller needs one.
static func texture(source: Image, presentation: Dictionary, render_width: int, render_height: int, strip_count: int = 0) -> Variant:
	var baked: Variant = image(source, presentation, render_width, render_height, strip_count)
	if Refusal.is_refusal(baked):
		return baked
	return ImageTexture.create_from_image(baked)


static func _colour(
	pixels: PackedByteArray, width: int, height: int, presentation: Dictionary, strip_count: int
) -> PackedByteArray:
	return _across_strips(
		height,
		func(from: int, to: int) -> PackedByteArray:
			return Pixels._colour_rows(
				pixels, width, height, presentation, from, to
			),
		strip_count
	)


static func _blur(
	pixels: PackedByteArray, width: int, height: int,
	kernel: PackedFloat32Array, horizontal: bool, strip_count: int
) -> PackedByteArray:
	return _across_strips(
		height,
		func(from: int, to: int) -> PackedByteArray:
			return Pixels._blur_rows(
				pixels, width, height, kernel, horizontal, from, to
			),
		strip_count
	)


## Run `strip` over every row once, in parallel, and join the pieces in order.
##
## The results array is sized before any task starts and each task writes one
## slot of it, so the threads share a container without ever sharing a slot.
static func _across_strips(height: int, strip: Callable, strip_count: int) -> PackedByteArray:
	var strips := clampi(OS.get_processor_count(), 1, MAX_STRIPS) if strip_count == 0 else strip_count
	strips = mini(strips, maxi(1, height))
	if strips == 1:
		return strip.call(0, height)
	var rows := int(ceil(float(height) / float(strips)))
	var results: Array = []
	results.resize(strips)
	var group := WorkerThreadPool.add_group_task(
		func(index: int) -> void:
			results[index] = strip.call(
				index * rows, mini((index + 1) * rows, height)
			),
		strips
	)
	WorkerThreadPool.wait_for_group_task_completion(group)
	var joined := PackedByteArray()
	for piece: Variant in results:
		joined.append_array(piece)
	return joined
