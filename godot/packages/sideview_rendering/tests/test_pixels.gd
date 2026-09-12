extends RefCounted

const Pixels = preload("res://addons/sideview_rendering/pixels.gd")
const ImageBaker = preload("res://addons/sideview_rendering/image_baker.gd")
const Refusal = preload("res://addons/sideview_rendering/refusal.gd")

## What depth does to a scrolling band.
##
## Every expected byte below came out of `web/lib/sideview/prepared-layer-
## presentation.ts` — the module the platformer still calls and the browser
## runner called before it was retired — run over the same four-by-three patch.
## Not read off this port and written down: a port checked against itself proves
## only that it is self-consistent, and this transform was shipped unchecked
## once already, which is why the runner's background drew at full strength.
##
## The patch is small and deliberately awkward: a fully saturated red, a green,
## a blue, two greys, a black, a white, a half-transparent pixel, and a fully
## transparent one whose colour must survive untouched.

const WIDTH := 4
const HEIGHT := 3

const SOURCE := [
	255, 0, 0, 255,     0, 255, 0, 255,     0, 0, 255, 255,     128, 128, 128, 255,
	10, 20, 30, 255,    200, 180, 160, 128, 0, 0, 0, 255,       255, 255, 255, 255,
	77, 88, 99, 0,      240, 12, 200, 255,  30, 200, 90, 64,    111, 111, 111, 255,
]

## The browser's answer with the runner's own far-band presentation and no blur.
const COLOURED := [
	209, 58, 61, 255,   64, 229, 74, 255,   48, 54, 216, 255,   138, 145, 148, 255,
	54, 66, 76, 255,    188, 182, 174, 128, 46, 52, 56, 255,    230, 236, 240, 255,
	77, 88, 99, 0,      202, 67, 187, 255,  80, 192, 127, 64,   126, 132, 136, 255,
]

## The same, with the 1.4 screen-pixel kernel this package's far band asks for.
const BLURRED := [
	122, 124, 122, 255, 119, 122, 128, 255, 113, 122, 132, 255, 124, 120, 133, 255,
	122, 125, 124, 255, 133, 116, 139, 128, 119, 122, 134, 255, 131, 121, 140, 255,
	122, 126, 127, 0,   148, 110, 151, 255, 128, 120, 139, 64,  139, 119, 146, 255,
]

const PRESENTATION := {
	"contrast": 0.88,
	"saturation": 0.86,
	"atmosphere_color": "#b8dcf0",
	"atmosphere_strength": 0.18,
	"detail_blur_screen_pixels": 0.0,
}


func run(h) -> void:
	_neutral(h)
	_colour(h)
	_blur(h)
	_rows_are_the_whole(h)
	_refusals(h)
	_host_path(h)
	h.done()


func _neutral(h) -> void:
	h.assert_true(
		Pixels._is_neutral(
			{
				"contrast": 1.0,
				"saturation": 1.0,
				"atmosphere_color": "#000000",
				"atmosphere_strength": 0.0,
				"detail_blur_screen_pixels": 0.0,
			}
		),
		"a band asking for nothing is neutral"
	)
	h.assert_false(
		Pixels._is_neutral(PRESENTATION),
		"the runner's far band is not neutral"
	)
	# The canopy asks only for a touch of contrast, and that alone is enough to
	# make it a band that must be presented rather than passed through.
	h.assert_false(
		Pixels._is_neutral(
			{
				"contrast": 1.04,
				"saturation": 1.02,
				"atmosphere_color": "#b8dcf0",
				"atmosphere_strength": 0.0,
				"detail_blur_screen_pixels": 0.0,
			}
		),
		"contrast alone is not neutral"
	)
	h.assert_eq(
		Array(Pixels._parse_hex_color("#b8dcf0")),
		[184, 220, 240],
		"an atmosphere colour parses to three bytes"
	)


func _colour(h) -> void:
	var got: Variant = Pixels.present_pixels(
		_source(), WIDTH, HEIGHT, PRESENTATION, 1.0
	)
	h.assert_eq(Array(got), COLOURED, "contrast, saturation and atmosphere match the browser")
	# The one property the arithmetic must never break: a pixel nobody can see
	# carries no colour to correct, and correcting it would drag arbitrary RGB
	# into the blur that follows.
	h.assert_eq(
		[got[32], got[33], got[34], got[35]],
		[77, 88, 99, 0],
		"a fully transparent pixel is left exactly as it was"
	)


func _blur(h) -> void:
	var asked := PRESENTATION.duplicate()
	asked["detail_blur_screen_pixels"] = 1.4
	var got: Variant = Pixels.present_pixels(_source(), WIDTH, HEIGHT, asked, 1.0)
	h.assert_eq(Array(got), BLURRED, "the alpha-weighted blur matches the browser")
	h.assert_eq(got[35], 0, "the blur carries source alpha through untouched")
	# Two and a half sigma each side, normalised.
	var kernel := Pixels._gaussian_kernel(1.4)
	h.assert_eq(kernel.size(), 9, "a 1.4 sigma kernel is nine taps wide")
	var total := 0.0
	for weight in kernel:
		total += weight
	h.assert_near(total, 1.0, 1e-6, "a kernel sums to one")
	# Below the floor the transform is a copy, not a convolution nobody can see.
	var barely := PRESENTATION.duplicate()
	barely["detail_blur_screen_pixels"] = 0.01
	h.assert_eq(
		Array(Pixels.present_pixels(_source(), WIDTH, HEIGHT, barely, 1.0)),
		COLOURED,
		"a kernel narrower than a pixel is skipped"
	)


## The row form and the whole-image form are the same transform.
##
## This is what lets the host split a band across cores without the picture
## depending on how many it found: every split of the rows must reassemble into
## the answer one thread would have given.
func _rows_are_the_whole(h) -> void:
	var asked := PRESENTATION.duplicate()
	asked["detail_blur_screen_pixels"] = 1.4
	var whole: Variant = Pixels.present_pixels(_source(), WIDTH, HEIGHT, asked, 1.0)
	for split in [1, 2, 3]:
		var coloured := PackedByteArray()
		for y in range(0, HEIGHT, split):
			coloured.append_array(
				Pixels._colour_rows(
					_source(), WIDTH, HEIGHT, asked, y, mini(y + split, HEIGHT)
				)
			)
		var kernel := Pixels._gaussian_kernel(1.4)
		var horizontal := _in_strips(coloured, kernel, true, split)
		var vertical := _in_strips(horizontal, kernel, false, split)
		h.assert_eq(
			Array(vertical), Array(whole), "rows in strips of %d rebuild the whole band" % split
		)


func _in_strips(
	pixels: PackedByteArray, kernel: PackedFloat32Array, horizontal: bool, split: int
) -> PackedByteArray:
	var made := PackedByteArray()
	for y in range(0, HEIGHT, split):
		made.append_array(
			Pixels._blur_rows(
				pixels, WIDTH, HEIGHT, kernel, horizontal, y, mini(y + split, HEIGHT)
			)
		)
	return made


## Malformed inputs return named failures, not partially transformed pixels.
func _refusals(h) -> void:
	for args in [[_source(), WIDTH, HEIGHT + 1, PRESENTATION, 1.0], [_source(), 0, HEIGHT, PRESENTATION, 1.0], [_source(), WIDTH, HEIGHT, PRESENTATION, 0.0]]:
		h.assert_true(Refusal.is_refusal(Pixels.present_pixels.callv(args)), "invalid pixel dimensions/scale are refused")


func _source() -> PackedByteArray:
	var made := PackedByteArray()
	for value: Variant in SOURCE:
		made.append(int(value))
	return made


## The image-to-texture path is independent of a package directory or loader.
func _host_path(h) -> void:
	var source := Image.create(16, 8, false, Image.FORMAT_RGBA8)
	for y in 8:
		for x in 16:
			# A saturated ramp, so a loss of saturation is unmistakable.
			source.set_pixel(x, y, Color(float(x) / 15.0, 1.0 - float(y) / 7.0, 0.2, 1.0))
	var texture: Variant = ImageBaker.texture(source, PRESENTATION, 16, 8)
	if not h.assert_true(not Refusal.is_refusal(texture), "an image presents to a texture"):
		return
	# Byte for byte the family's answer, which is what makes the host a carrier
	# of the transform rather than a second opinion about it. The base level
	# only: a band texture carries a mip chain, and the levels below the first
	# are the renderer's arithmetic rather than this one's.
	h.assert_eq(
		Array(_base_level(texture, 16, 8)),
		Array(
			Pixels.present_pixels(source.get_data(), 16, 8, PRESENTATION, 1.0)
		),
		"the drawn texture is the family's transform, byte for byte"
	)
	# And in the direction a reader cares about: further back reads quieter.
	var graded := Image.create_from_data(
		16, 8, false, Image.FORMAT_RGBA8, _base_level(texture, 16, 8)
	)
	h.assert_true(
		_mean_saturation(graded) < _mean_saturation(source),
		"a graded band is less saturated than the band it was made from"
	)
	# A band asking for nothing is carried through untouched.
	var neutral := {
		"contrast": 1.0,
		"saturation": 1.0,
		"atmosphere_color": "#000000",
		"atmosphere_strength": 0.0,
		"detail_blur_screen_pixels": 0.0,
	}
	h.assert_eq(
		Array(_base_level(ImageBaker.texture(source, neutral, 16, 8), 16, 8)),
		Array(source.get_data()),
		"and a neutral band is the band"
	)


## The first mip level of a band texture, which is the picture it was made from.
static func _base_level(texture: ImageTexture, width: int, height: int) -> PackedByteArray:
	return texture.get_image().get_data().slice(0, width * height * 4)


static func _mean_saturation(image: Image) -> float:
	var total := 0.0
	for y in image.get_height():
		for x in image.get_width():
			var pixel := image.get_pixel(x, y)
			var high := maxf(pixel.r, maxf(pixel.g, pixel.b))
			var low := minf(pixel.r, minf(pixel.g, pixel.b))
			total += 0.0 if high <= 0.0 else (high - low) / high
	return total / float(image.get_width() * image.get_height())
