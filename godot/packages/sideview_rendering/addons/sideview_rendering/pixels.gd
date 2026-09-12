extends RefCounted

## RGBA8 presentation arithmetic. Call present_pixels with explicit dimensions.
## Row/kernel helpers are internal and require validated input from that boundary.

const Refusal = preload("refusal.gd")

## Straight RGBA8, four bytes to a pixel, the layout `Image.FORMAT_RGBA8` gives.
const CHANNELS := 4

## Below this the blur is a copy: a kernel narrower than a pixel moves nothing,
## and building one wastes the boot it would cost.
const MIN_SIGMA := 0.05


## Does this band ask for anything at all?
##
## The neutral case is common — a foreground rail is usually authored at full
## strength — and skipping it is the difference between a boot that reads three
## bands and one that rewrites them.
static func _is_neutral(presentation: Dictionary) -> bool:
	return (
		is_equal_approx(float(presentation.get("contrast", 1.0)), 1.0)
		and is_equal_approx(float(presentation.get("saturation", 1.0)), 1.0)
		and is_equal_approx(float(presentation.get("atmosphere_strength", 0.0)), 0.0)
		and is_equal_approx(float(presentation.get("detail_blur_screen_pixels", 0.0)), 0.0)
	)


## `#rrggbb` as three bytes. An unreadable colour is black, which is what
## `Number.parseInt` of a bad slice gave the browser once `atmosphere_strength`
## multiplied it — and at strength zero no colour is read at all.
static func _parse_hex_color(value: String) -> PackedInt32Array:
	var text := value.strip_edges()
	if text.begins_with("#"):
		text = text.substr(1)
	if text.length() < 6:
		return PackedInt32Array([0, 0, 0])
	return PackedInt32Array(
		[
			text.substr(0, 2).hex_to_int(),
			text.substr(2, 2).hex_to_int(),
			text.substr(4, 2).hex_to_int(),
		]
	)


## Apply one band's presentation to its pixels.
##
## `source_pixels_per_screen_pixel` converts the authored blur — which is stated
## in *screen* pixels, because that is where a viewer sees it — into the source
## raster's own scale. A band painted at 1024 and drawn at 720 blurs by 1.4
## screen pixels only if its own kernel is 1.4 × 1024/720 wide.
##
## Returns a copied pixel buffer or a structured refusal. No input mutation.
static func present_pixels(
	source: PackedByteArray,
	width: int,
	height: int,
	presentation: Dictionary,
	source_pixels_per_screen_pixel: float
) -> Variant:
	if width <= 0 or height <= 0 or width > source.size() / CHANNELS or height > source.size() / (width * CHANNELS) or source.size() != width * height * CHANNELS:
		return Refusal.of("sideview/dimensions", "RGBA8 bytes must match positive dimensions", "source")
	var failure := validate_presentation(presentation, source_pixels_per_screen_pixel)
	if not failure.is_empty():
		return failure
	if _is_neutral(presentation):
		return source.duplicate()

	var output := _colour_rows(source, width, height, presentation, 0, height)
	var sigma := _blur_sigma(presentation, source_pixels_per_screen_pixel)
	if sigma < MIN_SIGMA:
		return output
	var kernel := _gaussian_kernel(sigma)
	var horizontal := _blur_rows(output, width, height, kernel, true, 0, height)
	return _blur_rows(horizontal, width, height, kernel, false, 0, height)


## The kernel width this band asks for, in its own source pixels.
##
## The authored number is in *screen* pixels, because that is where a viewer
## sees the softening; a band painted at 1024 and drawn at 720 needs a wider
## kernel of its own to land there.
static func _blur_sigma(presentation: Dictionary, source_pixels_per_screen_pixel: float) -> float:
	return (
		float(presentation.get("detail_blur_screen_pixels", 0.0))
		* source_pixels_per_screen_pixel
	)


## Contrast, saturation and atmosphere over the rows `[y_from, y_to)`.
##
## Returns those rows alone, so a caller splitting the image gets a piece it can
## place; `_colour_rows(source, w, h, p, 0, h)` is the whole image.
static func _colour_rows(
	source: PackedByteArray, width: int, height: int, presentation: Dictionary,
	y_from: int, y_to: int
) -> PackedByteArray:
	var first := clampi(y_from, 0, height)
	var last := clampi(y_to, first, height)
	var output := source.slice(first * width * CHANNELS, last * width * CHANNELS)
	var contrast := float(presentation.get("contrast", 1.0))
	var saturation := float(presentation.get("saturation", 1.0))
	var strength := float(presentation.get("atmosphere_strength", 0.0))
	var atmosphere := _parse_hex_color(String(presentation.get("atmosphere_color", "#000000")))
	var keep := 1.0 - strength
	var haze_r := float(atmosphere[0]) * strength
	var haze_g := float(atmosphere[1]) * strength
	var haze_b := float(atmosphere[2]) * strength

	var index := 0
	var end := output.size()
	while index < end:
		# A fully transparent pixel carries no colour to correct, and correcting
		# one would drag its arbitrary RGB into the blur that follows.
		if output[index + 3] == 0:
			index += CHANNELS
			continue
		var red := ((float(output[index]) / 255.0 - 0.5) * contrast + 0.5) * 255.0
		var green := ((float(output[index + 1]) / 255.0 - 0.5) * contrast + 0.5) * 255.0
		var blue := ((float(output[index + 2]) / 255.0 - 0.5) * contrast + 0.5) * 255.0
		# Rec. 709 luminance, which is the browser's and the one the authored
		# saturation numbers were chosen against.
		var luminance := red * 0.2126 + green * 0.7152 + blue * 0.0722
		red = luminance + (red - luminance) * saturation
		green = luminance + (green - luminance) * saturation
		blue = luminance + (blue - luminance) * saturation
		output[index] = _clamp_byte(red * keep + haze_r)
		output[index + 1] = _clamp_byte(green * keep + haze_g)
		output[index + 2] = _clamp_byte(blue * keep + haze_b)
		index += CHANNELS
	return output


## A normalised gaussian, two and a half sigma to each side.
static func _gaussian_kernel(sigma: float) -> PackedFloat32Array:
	var radius := maxi(1, int(ceil(sigma * 2.5)))
	var values := PackedFloat32Array()
	var total := 0.0
	for offset in range(-radius, radius + 1):
		var weight := exp(-float(offset * offset) / (2.0 * sigma * sigma))
		values.append(weight)
		total += weight
	for i in values.size():
		values[i] = values[i] / total
	return values


## One separable pass over the rows `[y_from, y_to)`, weighted by alpha.
##
## X wraps because every band is one admitted repeat period, so the pixel past
## the right edge really is the pixel at the left one. Y clamps because a band
## does not repeat vertically.
##
## The source alpha is carried through untouched: depth blur softens painted
## detail, it does not spread the silhouette the producer admitted or move the
## horizontal seam the repeat depends on.
##
## The whole image is read and only the asked-for rows are written, which is
## what makes a split safe: the vertical pass of one row reaches `radius` rows
## either side of it, and those rows are the *input*, which nobody is writing.
static func _blur_rows(
	source: PackedByteArray, width: int, height: int, kernel: PackedFloat32Array,
	horizontal: bool, y_from: int, y_to: int
) -> PackedByteArray:
	var first := clampi(y_from, 0, height)
	var last := clampi(y_to, first, height)
	var output := source.slice(first * width * CHANNELS, last * width * CHANNELS)
	var radius := kernel.size() / 2
	for y in range(first, last):
		var row := (y - first) * width
		for x in width:
			var red := 0.0
			var green := 0.0
			var blue := 0.0
			var contributing := 0.0
			for k in kernel.size():
				var offset := k - radius
				var sample_x := x
				var sample_y := y
				if horizontal:
					sample_x = posmod(x + offset, width)
				else:
					sample_y = clampi(y + offset, 0, height - 1)
				var at := (sample_y * width + sample_x) * CHANNELS
				var weight := (float(source[at + 3]) / 255.0) * kernel[k]
				red += float(source[at]) * weight
				green += float(source[at + 1]) * weight
				blue += float(source[at + 2]) * weight
				contributing += weight
			if contributing <= 0.0:
				continue
			var target := (row + x) * CHANNELS
			output[target] = _clamp_byte(red / contributing)
			output[target + 1] = _clamp_byte(green / contributing)
			output[target + 2] = _clamp_byte(blue / contributing)
	return output


static func _clamp_byte(value: float) -> int:
	return int(round(clampf(value, 0.0, 255.0)))


## Admission for the settings consumed by this transform. Unknown metadata is
## ignored. Helpers prefixed with an underscore require this admission first.
static func validate_presentation(presentation: Dictionary, source_pixels_per_screen_pixel: float = 1.0) -> Dictionary:
	if not is_finite(source_pixels_per_screen_pixel) or source_pixels_per_screen_pixel <= 0.0:
		return Refusal.of("sideview/scale", "source pixels per screen pixel must be finite and positive", "source_pixels_per_screen_pixel")
	for field in ["contrast", "saturation", "atmosphere_strength", "detail_blur_screen_pixels"]:
		var value: Variant = presentation.get(field, 1.0 if field in ["contrast", "saturation"] else 0.0)
		if not (value is int or value is float) or not is_finite(float(value)) or float(value) < 0.0:
			return Refusal.of("sideview/presentation", "setting must be a finite nonnegative number", field)
	if float(presentation.get("atmosphere_strength", 0.0)) > 1.0:
		return Refusal.of("sideview/presentation", "atmosphere strength must be at most one", "atmosphere_strength")
	var raw: Variant = presentation.get("atmosphere_color", "#000000")
	if not (raw is String):
		return Refusal.of("sideview/presentation", "atmosphere color must be a hex string", "atmosphere_color")
	var color: String = raw.strip_edges().trim_prefix("#")
	var valid_color := color.length() == 6
	for character in color.to_lower():
		valid_color = valid_color and "0123456789abcdef".contains(character)
	if not valid_color:
		return Refusal.of("sideview/presentation", "atmosphere color must have six hexadecimal digits", "atmosphere_color")
	var sigma := _blur_sigma(presentation, source_pixels_per_screen_pixel)
	# Packed array lengths are signed 32-bit. Refuse a kernel that cannot be
	# represented before conversion/allocation. Callers still own memory budgets.
	if not is_finite(sigma) or sigma * 5.0 + 3.0 > 2147483647.0:
		return Refusal.of("sideview/presentation", "blur kernel exceeds its representable range", "detail_blur_screen_pixels")
	var contrast := float(presentation.get("contrast", 1.0))
	var saturation := float(presentation.get("saturation", 1.0))
	if not is_finite(255.0 * contrast * maxf(1.0, saturation)):
		return Refusal.of("sideview/presentation", "color arithmetic exceeds its finite range", "contrast")
	return {}
