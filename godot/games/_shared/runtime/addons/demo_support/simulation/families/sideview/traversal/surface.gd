class_name FamilySurface
extends RefCounted

## Where the ground is, read off an occupancy grid.
##
## A port of `web/lib/families/sideview/traversal/surface.ts`. Row 0 is the top,
## so a *smaller* row number is *higher* on the screen — the browser's
## convention, kept because every threshold in both genres is written in it and
## flipping it here would flip forty comparisons somewhere else.
##
## The one rule worth stating: a column's surface is the top of the run of
## filled cells that reaches the *bottom* of the grid. A floating platform is
## not a surface, because a runner that fell through the world would otherwise
## land on the roof of a cave.


## The top row of the bottom-contiguous stack, or -1 for a pit.
##
## The browser returns `null` here; GDScript has no nullable int, and -1 is not
## a row any grid has, so it is the pit and every caller tests for it by name.
static func bottom_contiguous_surface_row(rows: PackedStringArray, column: int) -> int:
	var height := rows.size()
	if height == 0:
		return -1
	if not _filled(rows, height - 1, column):
		return -1
	var surface := height - 1
	while surface > 0 and _filled(rows, surface - 1, column):
		surface -= 1
	return surface


## How many cells of that stack there are; zero for a pit.
static func bottom_contiguous_height(rows: PackedStringArray, column: int) -> int:
	var surface := bottom_contiguous_surface_row(rows, column)
	return 0 if surface < 0 else rows.size() - surface


## The heights of every column, left to right.
static func bottom_contiguous_heights(rows: PackedStringArray) -> PackedInt32Array:
	var made := PackedInt32Array()
	var width := 0 if rows.is_empty() else rows[0].length()
	for column in width:
		made.append(bottom_contiguous_height(rows, column))
	return made


## Does this row belong to a column's bottom stack?
static func belongs_to_bottom_stack(row: int, rows: int, height: int) -> bool:
	return row >= rows - height


## The world Y of a surface, for a caller that measures in pixels rather than
## rows. Neither genre's simulation uses it; the platformer's view does.
static func surface_datum(height: int, tile: float, baseline: float) -> float:
	return baseline - float(height) * tile


static func _filled(rows: PackedStringArray, row: int, column: int) -> bool:
	if row < 0 or row >= rows.size():
		return false
	var line := rows[row]
	if column < 0 or column >= line.length():
		return false
	return line[column] == "1"
