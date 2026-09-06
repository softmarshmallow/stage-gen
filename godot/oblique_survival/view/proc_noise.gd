extends RefCounted

## The one procedural input the ground and the water share: the viewer's
## `noiseTexture(256, 32)` (index.html:2751-2785), value noise from
## `mulberry32(1337)` on a wrapping 32x32 lattice, smoothstep-interpolated.
##
## Two port notes, both load-bearing:
##
## 1. The lattice is drawn in exactly the viewer's order (row by row, one
##    `rand()` per cell) so the field is the same field, not merely the same
##    kind of field. Every torn coast, every brush stroke and every wave in a
##    Godot frame therefore lands where the web viewer put it.
## 2. three uploads a `CanvasTexture` with `flipY = true`, so its `v` runs up
##    the image; Godot's runs down. The image is written flipped here (row `r`
##    holds the canvas row `size - 1 - r`) so a shader can sample it with the
##    viewer's own UV maths and get the viewer's own texel. Nothing downstream
##    needs a flip.

const SIZE := 256
const LATTICE := 32
const SEED := 1337

static var _cached: ImageTexture = null

## The shared noise texture (built once per process).
static func texture() -> ImageTexture:
	if _cached == null:
		_cached = ImageTexture.create_from_image(image())
	return _cached

static func image() -> Image:
	var grid := PackedFloat32Array()
	grid.resize(LATTICE * LATTICE)
	# `Array.from({length: lattice}, () => Array.from({length: lattice}, rand))`:
	# row 0 first, left to right, from the simulation's own generator so both
	# halves of the host draw from one PRNG.
	var rng := Mulberry32.new(SEED)
	for i in range(LATTICE * LATTICE):
		grid[i] = rng.next()
	var img := Image.create_empty(SIZE, SIZE, false, Image.FORMAT_RGBA8)
	for y in range(SIZE):
		var fy := (float(y) / float(SIZE)) * float(LATTICE)
		var y0 := int(floor(fy)) % LATTICE
		var y1 := (y0 + 1) % LATTICE
		var ty := _smooth(fy - floor(fy))
		for x in range(SIZE):
			var fx := (float(x) / float(SIZE)) * float(LATTICE)
			var x0 := int(floor(fx)) % LATTICE
			var x1 := (x0 + 1) % LATTICE
			var tx := _smooth(fx - floor(fx))
			var top: float = grid[y0 * LATTICE + x0] * (1.0 - tx) + grid[y0 * LATTICE + x1] * tx
			var bottom: float = grid[y1 * LATTICE + x0] * (1.0 - tx) + grid[y1 * LATTICE + x1] * tx
			var value := float(roundi((top * (1.0 - ty) + bottom * ty) * 255.0)) / 255.0
			# Flipped: the canvas row `y` becomes the image row `SIZE - 1 - y`.
			img.set_pixel(x, SIZE - 1 - y, Color(value, value, value, 1.0))
	img.generate_mipmaps()
	return img

static func _smooth(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)
