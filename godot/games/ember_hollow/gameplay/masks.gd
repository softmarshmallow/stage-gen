class_name SurvivalMasks
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
## The walkable inset, in metres: a point is land only if the four points this
## far from it are land too. Never quantised to cells, so a coarser plate keeps
## the same erosion.
var _inset_meters: float = DEFAULT_INSET_METERS
## Metres per plate cell, as the manifest publishes it.
var _cell_meters: float = 0.0

var _biome: PackedByteArray = PackedByteArray()
var _biome_cells: int = 0
var _biome_rows: int = 0
## Channel key ("r", "g", "b", "base") -> biome id.
var _biome_ids: Dictionary = {}
## Channel key -> friction coefficient.
var _biome_friction: Dictionary = {}

## Construct sampling state from already decoded game-owned plates.
## The caller supplies admitted RGBA8 buffers and matching dimensions.
static func from_data(world_size: float, land: Dictionary, biome: Dictionary,
		inset_meters: float = DEFAULT_INSET_METERS) -> SurvivalMasks:
	var masks := SurvivalMasks.new()
	masks.size = world_size
	masks._land = land.get("pixels", PackedByteArray()).duplicate()
	masks._land_cells = int(land.get("width", 0))
	masks._land_rows = int(land.get("height", 0))
	masks._cell_meters = float(land.get("cell_meters", 0.0))
	masks._inset_meters = inset_meters
	masks._biome = biome.get("pixels", PackedByteArray()).duplicate()
	masks._biome_cells = int(biome.get("width", 0))
	masks._biome_rows = int(biome.get("height", 0))
	masks._biome_ids = biome.get("ids", {}).duplicate()
	masks._biome_friction = biome.get("friction", {}).duplicate()
	return masks

## Land only if this point and the four points `_inset_meters` away are land:
## a 0.7 m erosion that keeps the player inside the shader's torn edge, the
## same 0.7 m whatever the plate's cell size.
func is_land(x: float, z: float) -> bool:
	if _land.is_empty():
		return true
	var m := _inset_meters
	return (
		_land_at_point(x, z)
		and _land_at_point(x + m, z)
		and _land_at_point(x - m, z)
		and _land_at_point(x, z + m)
		and _land_at_point(x, z - m)
	)

func _land_at_point(x: float, z: float) -> bool:
	var column := floori((x + size * 0.5) / size * _land_cells)
	var row := floori((z + size * 0.5) / size * _land_rows)
	return _land_at(column, row)

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
	var row := clampi(floori((z + size * 0.5) / size * _biome_rows), 0, _biome_rows - 1)
	var offset := (row * _biome_cells + column) * 4
	if _biome[offset] > 127:
		return "r"
	if _biome[offset + 1] > 127:
		return "g"
	if _biome[offset + 2] > 127:
		return "b"
	return "base"
