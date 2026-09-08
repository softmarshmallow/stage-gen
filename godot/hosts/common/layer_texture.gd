class_name HostLayerTexture
extends RefCounted

## A scrolling band's texture, with the depth the producer authored baked in.
##
## `FamilyLayerPresentation` says what the transform is; this pays for it. The
## split is here rather than in the family because how many cores a machine has
## is not part of what a band looks like — the family stays a statement about
## pixels, and the host stays the only thing that knows it is running on a
## computer.
##
## Rows are independent in all three passes, so the image is cut into one strip
## per core and reassembled in order. Measured on this repository's own runner
## package, a 1536x1024 band costs 0.77 s to colour and 6.5 s to blur on one
## thread; that is a boot nobody would sit through, and it is the whole reason
## this file exists.

## More strips than this buys nothing and costs a task each: the passes are
## memory-bound long before the core count runs out.
const MAX_STRIPS := 16


## One band's texture at the size it will be drawn, presented.
##
## The resize comes first and the arithmetic runs at screen resolution, which is
## both cheaper and truer than the browser's order: `detail_blur_screen_pixels`
## is authored in *screen* pixels, so a kernel applied at screen scale is the
## number the producer wrote, with no conversion to be wrong about. The band is
## drawn at this size anyway — a texture carrying more pixels than the viewport
## can show is detail the sampler was going to throw away.
##
## Returns null when the image cannot be read; the caller reports the gap,
## because only it knows which band went missing.
static func band(
	package: HostRunDir, image_ref: String, presentation: Dictionary,
	render_width: int, render_height: int
) -> ImageTexture:
	var source := package.image(image_ref)
	if source == null:
		return null
	var working := Image.new()
	working.copy_from(source)
	if working.get_format() != Image.FORMAT_RGBA8:
		working.convert(Image.FORMAT_RGBA8)
	var width := maxi(1, render_width)
	var height := maxi(1, render_height)
	if working.get_width() != width or working.get_height() != height:
		working.resize(width, height, Image.INTERPOLATE_LANCZOS)

	if not FamilyLayerPresentation.is_neutral(presentation):
		var pixels := _colour(working.get_data(), width, height, presentation)
		# Screen resolution, so the authored screen-pixel sigma is the sigma.
		var sigma := FamilyLayerPresentation.blur_sigma(presentation, 1.0)
		if sigma >= FamilyLayerPresentation.MIN_SIGMA:
			var kernel := FamilyLayerPresentation.gaussian_kernel(sigma)
			pixels = _blur(pixels, width, height, kernel, true)
			pixels = _blur(pixels, width, height, kernel, false)
		working = Image.create_from_data(width, height, false, Image.FORMAT_RGBA8, pixels)

	working.generate_mipmaps()
	return ImageTexture.create_from_image(working)


static func _colour(
	pixels: PackedByteArray, width: int, height: int, presentation: Dictionary
) -> PackedByteArray:
	return _across_strips(
		height,
		func(from: int, to: int) -> PackedByteArray:
			return FamilyLayerPresentation.colour_rows(
				pixels, width, height, presentation, from, to
			)
	)


static func _blur(
	pixels: PackedByteArray, width: int, height: int,
	kernel: PackedFloat32Array, horizontal: bool
) -> PackedByteArray:
	return _across_strips(
		height,
		func(from: int, to: int) -> PackedByteArray:
			return FamilyLayerPresentation.blur_rows(
				pixels, width, height, kernel, horizontal, from, to
			)
	)


## Run `strip` over every row once, in parallel, and join the pieces in order.
##
## The results array is sized before any task starts and each task writes one
## slot of it, so the threads share a container without ever sharing a slot.
static func _across_strips(height: int, strip: Callable) -> PackedByteArray:
	var strips := clampi(OS.get_processor_count(), 1, MAX_STRIPS)
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
