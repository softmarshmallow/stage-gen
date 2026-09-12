class_name FamilyTerrainAtlas
extends RefCounted

## Which cell of a terrain sheet one filled square is drawn with.
##
## A port of `web/lib/sideview/terrain-atlas.ts`. A square's cell is decided by
## its eight neighbours, so a run of ground draws as a run of ground rather than
## as a grid of identical blocks: the top edge gets a top edge, an inside corner
## gets an inside corner, and a lone block gets the one cell that is all edge.
##
## The mask is nine characters — `nw n ne w center e sw s se`, in that order,
## `1` for filled — and the centre is always `1` because an empty square is not
## drawn at all. A diagonal only counts when both of its sides do: a corner that
## peers past a gap would draw ground where the player can walk through.
##
## The table itself is read by the host, because reading a file is a host's job
## and a family may not name a path. What is here is the arithmetic: the mask, and
## what a mask means once somebody has handed over the table.

const LOOKUP_KIND := "terrain-atlas-3x3-minimal-lookup-v1"
const MASK_ORDER := "nw,n,ne,w,center,e,sw,s,se"
const MASK_COUNT := 47

## The sheet's own grid, and the cell size every published sheet is cut to.
const COLUMNS := 12
const ROWS := 4
const CELL_PX := 120.0

## How far below a cell's top edge the walkable surface actually sits. The art
## overhangs its own footing, so a body standing on a square stands this far
## into it rather than on its very top.
const WALK_SURFACE_INSET_PX := 10.0

## The cell drawn for a mask the table does not carry, as `[column, row]`.
## Nothing should reach it; drawing something is better than drawing nothing,
## and it is visibly wrong.
const PLACEHOLDER := [10, 1]


## Check a lookup document and reduce it to `{mask: [column, row]}`, or refuse.
##
## The document is the host's to fetch; what it has to *be* is this family's,
## because a table read in another neighbour order would draw a plausible map
## out of the wrong cells and nothing would say so.
static func lookup(document: Variant) -> Variant:
	if not (document is Dictionary):
		return KernelRefusal.of("terrain/atlas", "the terrain lookup could not be read")
	var doc: Dictionary = document
	if String(doc.get("kind", "")) != LOOKUP_KIND:
		return KernelRefusal.of("terrain/atlas", "the terrain lookup is of another kind", "kind")
	if int(doc.get("terrain_mask_count", 0)) != MASK_COUNT:
		return KernelRefusal.of(
			"terrain/atlas", "the terrain lookup does not carry %d masks" % MASK_COUNT
		)
	var order := PackedStringArray()
	for entry: Variant in (doc.get("mask_order", []) as Array):
		order.append(String(entry))
	if ",".join(order) != MASK_ORDER:
		return KernelRefusal.of(
			"terrain/atlas", "the terrain lookup reads its neighbours in another order", "mask_order"
		)
	var made := {}
	for key: Variant in (doc.get("lookup", {}) as Dictionary):
		var cell: Array = (doc["lookup"] as Dictionary)[key]
		made[String(key)] = [int(cell[0]), int(cell[1])]
	return made


## The nine-character mask for one filled square.
##
## A diagonal counts only when both of its sides do, which is what stops a
## corner peering across a gap the player can walk through.
static func peering_mask(occupancy: PackedStringArray, column: int, row: int) -> String:
	var north := _filled(occupancy, column, row - 1)
	var east := _filled(occupancy, column + 1, row)
	var south := _filled(occupancy, column, row + 1)
	var west := _filled(occupancy, column - 1, row)
	var bits := [
		north and west and _filled(occupancy, column - 1, row - 1),
		north,
		north and east and _filled(occupancy, column + 1, row - 1),
		west,
		true,
		east,
		south and west and _filled(occupancy, column - 1, row + 1),
		south,
		south and east and _filled(occupancy, column + 1, row + 1),
	]
	var made := ""
	for bit: Variant in bits:
		made += "1" if bool(bit) else "0"
	return made


## Where in the sheet one mask's cell sits, as `[column, row]` in cells.
static func cell_for(table: Dictionary, mask: String) -> Array:
	return table.get(mask, PLACEHOLDER)


## How far into a drawn cell the walkable surface sits, at this cell size.
static func walk_surface_offset(rendered_cell_px: float) -> float:
	if rendered_cell_px <= 0.0:
		return 0.0
	return (WALK_SURFACE_INSET_PX / CELL_PX) * rendered_cell_px


static func _filled(occupancy: PackedStringArray, column: int, row: int) -> bool:
	if row < 0 or row >= occupancy.size():
		return false
	var line := occupancy[row]
	if column < 0 or column >= line.length():
		return false
	return line[column] == "1"


## The squares to draw, including the ones just off the map.
##
## Returns `[{column, row, mask}]` over an occupancy padded by one column at each
## side and one row at the bottom, each copying the edge it extends. Columns are
## reported in the *map's* numbering, so the two extra ones are -1 and the width.
##
## Without the padding a map ends in mid-air: the leftmost filled square peers
## into nothing, takes an edge cell, and the ground stops with a drawn lip a
## finger's width from the screen edge. The padding is what makes ground read as
## continuing past the picture rather than as a platform floating in it.
static func overscan_plan(occupancy: PackedStringArray) -> Array:
	if occupancy.is_empty():
		return []
	var padded := PackedStringArray()
	for line in occupancy:
		if line.is_empty():
			continue
		padded.append(line[0] + line + line[line.length() - 1])
	if padded.is_empty():
		return []
	padded.append(padded[padded.size() - 1])
	var made: Array = []
	for row in range(padded.size()):
		var line := padded[row]
		for column in range(line.length()):
			if line[column] != "1":
				continue
			made.append(
				{
					"column": column - 1,
					"row": row,
					"mask": peering_mask(padded, column, row),
				}
			)
	return made
