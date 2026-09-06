class_name Masks
extends RefCounted

## The two ground plates read back as data: where the player may walk, and what
## the surface under a point does to a sliding drop.
##
## Port of the viewer's `landMask` (index.html:2563) and `biomeMask` (2598).
## Both plates are data, not colour: no colour-space conversion, no mips, and
## row 0 is minimum z, which is exactly the PNG's own row order.

const DEFAULT_INSET_METERS := 0.7
const DEFAULT_FRICTION := 0.6

## World size in metres of the square the plates cover.
var size: float = 0.0

var _land: PackedByteArray = PackedByteArray()
var _land_cells: int = 0
var _land_rows: int = 0
var _inset: int = 1

var _biome: PackedByteArray = PackedByteArray()
var _biome_cells: int = 0
var _biome_rows: int = 0
## Channel key ("r", "g", "b", "base") -> biome id.
var _biome_ids: Dictionary = {}
## Channel key -> friction coefficient.
var _biome_friction: Dictionary = {}

## Build both masks from a run package. Always returns a Masks: a run with no
## plate gets the viewer's placeholders (everything is land, friction 0.6).
static func from_package(pkg: RunPackage, inset_meters: float = DEFAULT_INSET_METERS) -> Masks:
	var masks := Masks.new()
	if pkg == null:
		return masks
	var ground: Dictionary = pkg.manifest.get("ground", {})
	masks.size = float(ground.get("size_meters", 0.0))
	var splat: Dictionary = ground.get("splat", {}) if ground.get("splat") != null else {}
	if masks.size > 0.0 and splat.has("image"):
		var image := pkg.image(String(splat["image"]))
		if image != null:
			masks._land_cells = image.get_width()
			masks._land_rows = image.get_height()
			masks._land = _rgba8_bytes(image)
			masks._inset = maxi(1, int(round(inset_meters / masks.size * masks._land_cells)))
	var biome_splat: Variant = ground.get("biome_splat")
	var biomes: Variant = ground.get("biomes")
	if masks.size > 0.0 and biome_splat is Dictionary and biomes is Dictionary:
		for id: String in (biomes as Dictionary).keys():
			var biome: Dictionary = biomes[id]
			var channel: String = "base"
			if biome.get("weight_channel") != null:
				channel = String(biome["weight_channel"])
			masks._biome_ids[channel] = id
			var friction: Variant = biome.get("friction")
			var value := DEFAULT_FRICTION
			if friction is float or friction is int:
				value = float(friction)
			masks._biome_friction[channel] = value
		var ref: Variant = (biome_splat as Dictionary).get("image")
		if ref != null:
			var image := pkg.image(String(ref))
			if image != null:
				masks._biome_cells = image.get_width()
				masks._biome_rows = image.get_height()
				masks._biome = _rgba8_bytes(image)
	return masks

## Land only if this cell and its four neighbours `inset` cells away are land:
## a 0.7 m erosion that keeps the player inside the shader's torn edge.
func is_land(x: float, z: float) -> bool:
	if _land.is_empty():
		return true
	var column := floori((x + size * 0.5) / size * _land_cells)
	var row := floori((z + size * 0.5) / size * _land_cells)
	return (
		_land_at(column, row)
		and _land_at(column + _inset, row)
		and _land_at(column - _inset, row)
		and _land_at(column, row + _inset)
		and _land_at(column, row - _inset)
	)

## The friction coefficient of the ground under a point.
func friction_at(x: float, z: float) -> float:
	var channel := _channel_at(x, z)
	if channel == "":
		return DEFAULT_FRICTION
	return float(_biome_friction.get(channel, DEFAULT_FRICTION))

## Which biome is under a point, or "" when the run has no biome plate.
func biome_at(x: float, z: float) -> String:
	var channel := _channel_at(x, z)
	if channel == "":
		return ""
	return String(_biome_ids.get(channel, ""))

func _land_at(column: int, row: int) -> bool:
	if column < 0 or row < 0 or column >= _land_cells or row >= _land_rows:
		return false
	# The splat's alpha channel is the land (splat.channels.a === 'land').
	return _land[(row * _land_cells + column) * 4 + 3] > 127

## Channel precedence is r, then g, then b, then base: the first over 127 wins,
## not the largest.
func _channel_at(x: float, z: float) -> String:
	if _biome.is_empty():
		return ""
	var column := clampi(floori((x + size * 0.5) / size * _biome_cells), 0, _biome_cells - 1)
	var row := clampi(floori((z + size * 0.5) / size * _biome_cells), 0, _biome_rows - 1)
	var offset := (row * _biome_cells + column) * 4
	if _biome[offset] > 127:
		return "r"
	if _biome[offset + 1] > 127:
		return "g"
	if _biome[offset + 2] > 127:
		return "b"
	return "base"

static func _rgba8_bytes(image: Image) -> PackedByteArray:
	var copy := Image.new()
	copy.copy_from(image)
	if copy.get_format() != Image.FORMAT_RGBA8:
		copy.convert(Image.FORMAT_RGBA8)
	return copy.get_data()
