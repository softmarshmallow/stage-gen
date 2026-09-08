class_name PlatformerVertical
extends RefCounted

## The platformer's world above the ground line: one-way decks, ladders, and the
## heightfield they stand on.
##
## A port of the geometry half of `web/lib/sideview-platformer/vertical.ts` and
## `prepared-terrain.ts`. Everything here is derived from the map's authored
## occupancy grid rather than authored directly, which is what keeps the level a
## producer drew and the level this plays the same level.
##
## Every number is a whole world pixel. The unit is not a tile: the platformer
## measures in pixels because its terrain steps in tiles and its bodies do not.

## How thick a one-way deck is, below its walking surface.
const UPPER_PLATFORM_THICKNESS := 32.0

## How tall a climbable is, in tiles. Exactly one rise and not a range: the
## artwork is drawn to it and the reachability proof admitted routes at it.
const CLIMBABLE_RISE_TILES := 4.0
const CLIMBABLE_ACTIVATION_HALF_WIDTH := 30.0
const CLIMBABLE_ENDPOINT_TOLERANCE := 12.0
const CLIMBABLE_VISUAL_OVERSHOOT := 32.0
const CLIMBABLE_VISUAL_WIDTH := 64.0
const CLIMBABLE_SPEED := 180.0
const CLIMBABLE_JUMP_VELOCITY := -350.0
const CLIMBABLE_JUMP_HORIZONTAL_SPEED := 200.0

const WALK_SPEED := 200.0
const RUN_SPEED := 540.0
const CROUCH_SPEED := 80.0
const JUMP_VELOCITY := 520.0
## Deliberately weaker than the grounded launch, so the second jump extends a
## route rather than doubling it: 520 clears 90px on its own and the 440
## follow-up adds another 64. A two-tile rise is therefore unreachable from the
## ground and reachable with the air jump, which is what makes the mechanic
## load-bearing in the platform graph instead of decorative.
const AIR_JUMP_VELOCITY := 440.0
const AIR_JUMPS_MAX := 1
## Grace after leaving a support during which a jump still counts as grounded.
## Terrain step-downs are real falls here, so without this every jump pressed at
## a ledge silently spends the air jump instead of the ground one.
const COYOTE_MS := 90.0
const GRAVITY := 1500.0
const FIXED_STEP_SECONDS := 1.0 / 30.0

## How much downward terrain change a walking foot absorbs without leaving the
## surface, and how much upward. Past either is a wall or a fall, not a snap.
const STEP_DOWN_TOLERANCE := 1.0
const STEP_UP_TOLERANCE := 1.0
## The gap kept between a blocked foot and the column face it stopped against.
const WALL_CONTACT_GAP := 1.0

const DROP_THROUGH_MS := 180.0
const DROP_CLEARANCE := 16.0
const DROP_SETTLE_FRAMES := 7


## Where a column's walking surface sits, in world pixels.
static func terrain_surface_y(height: int, tile_px: float, baseline_y: float) -> float:
	return baseline_y - float(height) * tile_px


## The one-way decks a map's occupancy grid describes.
##
## A deck is a run of filled cells that is **not** part of a column's ground
## stack and has nothing filled directly above it — an exposed floating surface.
## The run ends where any of those three stops being true, which is what turns a
## painted shelf into one platform rather than a platform per cell.
static func floating_platforms(
	occupancy: PackedStringArray, heights: PackedInt32Array, tile_px: float, baseline_y: float
) -> Array:
	var rows: int = occupancy.size()
	if rows == 0:
		return []
	var columns: int = occupancy[0].length()
	var platforms: Array = []
	for row in rows:
		var column := 0
		while column < columns:
			if not _exposed(occupancy, heights, rows, row, column):
				column += 1
				continue
			var start: int = column
			column += 1
			while column < columns and _exposed_run(occupancy, heights, rows, row, column):
				column += 1
			var end: int = column
			var deck_y: float = baseline_y - float(rows - row) * tile_px
			platforms.append(
				{
					"id": "terrain-platform-r%d-c%d" % [row, start],
					"left": float(start) * tile_px,
					"right": float(end) * tile_px,
					"deckY": deck_y,
					"tier": maxi(1, int(round((baseline_y - deck_y) / tile_px))),
					"thickness": UPPER_PLATFORM_THICKNESS,
					"sourceColumns": {"start": start, "end": end},
				}
			)
	# Left to right, then lowest deck, then by id: a stable order, because the
	# order platforms are searched in is the order a landing picks between two
	# that overlap.
	platforms.sort_custom(_by_platform)
	return platforms


## Everything wrong with a set of derived decks, or an empty string.
##
## The derivation and the check are separate on purpose: the grid walk above
## produces geometry and this decides whether that geometry is a world. A deck
## outside the map, one whose pixels do not agree with the columns it was read
## from, or two whose *solid bodies* intersect are all package defects, and a
## package defect that plays is worse than one that refuses — the first is
## discovered by a player.
##
## The overlap test is two-dimensional and pairwise rather than a neighbour
## check, because decks may share columns as long as they occupy different
## bands: that is what lets one route run above another.
static func deck_refusal(
	platforms: Array,
	columns: int,
	tile_px: float,
	baseline_y: float,
	top_y: float,
	world_width: float
) -> String:
	var seen := {}
	for entry: Variant in platforms:
		var deck: Dictionary = entry
		var id := String(deck["id"])
		if seen.has(id):
			return "two decks are both named %s" % id
		seen[id] = true
		var source: Dictionary = deck["sourceColumns"]
		if (
			float(deck["left"]) < 0.0
			or float(deck["right"]) > world_width
			or float(deck["left"]) >= float(deck["right"])
			or float(deck["deckY"]) < top_y
			or float(deck["deckY"]) + UPPER_PLATFORM_THICKNESS > baseline_y
			or int(deck["tier"]) < 1
			or int(source["start"]) < 0
			or int(source["end"]) > columns
			or int(source["start"]) >= int(source["end"])
			or not is_equal_approx(float(deck["left"]), float(source["start"]) * tile_px)
			or not is_equal_approx(float(deck["right"]), float(source["end"]) * tile_px)
		):
			return "deck %s lies outside its world or the columns it was read from" % id
	for index in range(platforms.size()):
		var a: Dictionary = platforms[index]
		for other in range(index + 1, platforms.size()):
			var b: Dictionary = platforms[other]
			if float(b["left"]) >= float(a["right"]) or float(a["left"]) >= float(b["right"]):
				continue
			if (
				float(b["deckY"]) >= float(a["deckY"]) + UPPER_PLATFORM_THICKNESS
				or float(a["deckY"]) >= float(b["deckY"]) + UPPER_PLATFORM_THICKNESS
			):
				continue
			return "decks %s and %s occupy the same solid space" % [a["id"], b["id"]]
	return ""


## The ladders and ropes a map places, resolved against the decks they hang from.
##
## Returns the zones, or a `KernelRefusal` naming the placement that does not
## attach: a ladder to nowhere is a route the solvability proof admitted and this
## build cannot walk, which is a refusal rather than a ladder nobody can climb.
static func climbable_zones(
	placements: Array,
	variants: Dictionary,
	platforms: Array,
	heights: PackedInt32Array,
	tile_px: float,
	baseline_y: float,
	world_width: float
) -> Variant:
	var zones: Array = []
	for entry: Variant in placements:
		var placement: Dictionary = entry
		var climbable_id: String = String(placement.get("climbable_id", ""))
		var center_x: float = round(float(placement.get("normalized_x", 0.0)) * world_width)
		var column: int = int(floor(center_x / tile_px))
		# A placement outside the heightfield has no lower endpoint; it is caught
		# below as a climbable that attaches to nothing rather than guessed at.
		var lower_height := 0
		if column >= 0 and column < heights.size():
			lower_height = int(heights[column])
		var lower_surface_y: float = terrain_surface_y(lower_height, tile_px, baseline_y)
		var upper_deck_y: float = lower_surface_y - float(placement.get("rise_tiles", 0)) * tile_px
		# The rise is not the author's to choose: a climbable is one four-tile
		# span, because that is the height the artwork is drawn to and the height
		# the reachability proof admitted the route at. A ladder authored five
		# tiles long would be drawn stretched and would put a body through a deck.
		if not is_equal_approx(lower_surface_y - upper_deck_y, tile_px * CLIMBABLE_RISE_TILES):
			return KernelRefusal.of(
				"platformer/climbable",
				(
					"climbable %s spans %d tiles; a climbable is one %d-tile rise"
					% [climbable_id, int(placement.get("rise_tiles", 0)), int(CLIMBABLE_RISE_TILES)]
				),
				climbable_id
			)
		# And its foot has to be on real, flat ground with something to its right:
		# a body steps *off* a ladder sideways, and a foot placed over the edge of
		# a shelf steps into air.
		if column < 0 or column + 1 >= heights.size():
			return KernelRefusal.of(
				"platformer/climbable",
				"climbable %s stands at the edge of the map with no ground to its right"
				% climbable_id,
				climbable_id
			)
		if not is_equal_approx(
			lower_surface_y, terrain_surface_y(int(heights[column + 1]), tile_px, baseline_y)
		):
			return KernelRefusal.of(
				"platformer/climbable",
				"climbable %s stands on a step rather than on flat ground" % climbable_id,
				climbable_id
			)
		var deck := {}
		for candidate: Variant in platforms:
			var platform: Dictionary = candidate
			if (
				is_equal_approx(float(platform["deckY"]), upper_deck_y)
				and center_x >= float(platform["left"])
				and center_x < float(platform["right"])
			):
				deck = platform
				break
		if deck.is_empty():
			return KernelRefusal.of(
				"platformer/climbable",
				(
					"climbable %s does not attach to an exposed platform at the rise it declares"
					% climbable_id
				),
				climbable_id
			)
		var variant: Dictionary = variants.get(String(placement.get("variant_id", "")), {})
		if variant.is_empty():
			return KernelRefusal.of(
				"platformer/climbable",
				"climbable %s names a variant this map does not declare" % climbable_id,
				climbable_id
			)
		# The drawn width follows the atlas cell's own aspect rather than a
		# constant: a rope painted narrow and a ladder painted wide are drawn as
		# they were painted, over the rise they actually span.
		var visual_height: float = lower_surface_y - upper_deck_y + CLIMBABLE_VISUAL_OVERSHOOT * 2.0
		var cell: Dictionary = variant.get("cell", {})
		var visual_width: float = climbable_visual_width(
			float(cell.get("width", 1.0)), float(cell.get("height", 1.0)), visual_height
		)
		if visual_width <= 0.0 or visual_width > tile_px * CLIMBABLE_RISE_TILES:
			return KernelRefusal.of(
				"platformer/climbable",
				(
					"climbable %s is drawn %d px wide, which is not a width within four tiles"
					% [climbable_id, int(visual_width)]
				),
				climbable_id
			)
		zones.append(
			{
				"id": climbable_id,
				"platformId": deck["id"],
				"variantId": String(placement.get("variant_id", "")),
				"role": String(variant.get("role", "ladder")),
				"centerX": center_x,
				"upperDeckY": upper_deck_y,
				"lowerSurfaceY": lower_surface_y,
				"activationHalfWidth": CLIMBABLE_ACTIVATION_HALF_WIDTH,
				"visualWidth": visual_width,
				"visualTopOvershoot": CLIMBABLE_VISUAL_OVERSHOOT,
				"visualBottomOvershoot": CLIMBABLE_VISUAL_OVERSHOOT,
			}
		)
	# Left to right, then by id. The order is not cosmetic: an entry takes the
	# *first* zone whose activation band contains the body, so two climbables
	# close enough to overlap are decided by this and not by which the author
	# happened to list first.
	zones.sort_custom(_by_climbable)
	return zones


static func _by_climbable(left: Dictionary, right: Dictionary) -> bool:
	if not is_equal_approx(float(left["centerX"]), float(right["centerX"])):
		return float(left["centerX"]) < float(right["centerX"])
	return String(left["id"]) < String(right["id"])


## How wide a climbable is drawn: its atlas cell's aspect, over the rise it spans.
static func climbable_visual_width(
	cell_width: float, cell_height: float, visual_height: float
) -> float:
	if cell_width <= 0.0 or cell_height <= 0.0 or visual_height <= 0.0:
		return CLIMBABLE_VISUAL_WIDTH
	return maxf(1.0, round((visual_height * cell_width) / cell_height))


## The deck a given x stands over at a given deck height, or an empty dictionary.
static func platform_by_id(platforms: Array, platform_id: Variant) -> Dictionary:
	if platform_id == null:
		return {}
	for entry: Variant in platforms:
		var platform: Dictionary = entry
		if String(platform["id"]) == String(platform_id):
			return platform
	return {}


## The climb geometry the traversal family asks for, out of one zone.
static func climb_geometry(zone: Dictionary) -> Dictionary:
	return {
		"centerX": zone["centerX"],
		"activationHalfWidth": zone["activationHalfWidth"],
		"upperY": zone["upperDeckY"],
		"lowerY": zone["lowerSurfaceY"],
		"deckId": zone["platformId"],
	}


static func _exposed(
	occupancy: PackedStringArray, heights: PackedInt32Array, rows: int, row: int, column: int
) -> bool:
	if not _filled(occupancy, row, column):
		return false
	if FamilySurface.belongs_to_bottom_stack(row, rows, heights[column]):
		return false
	return row == 0 or not _filled(occupancy, row - 1, column)


static func _exposed_run(
	occupancy: PackedStringArray, heights: PackedInt32Array, rows: int, row: int, column: int
) -> bool:
	if not _filled(occupancy, row, column):
		return false
	if FamilySurface.belongs_to_bottom_stack(row, rows, heights[column]):
		return false
	return not (row > 0 and _filled(occupancy, row - 1, column))


static func _filled(occupancy: PackedStringArray, row: int, column: int) -> bool:
	if row < 0 or row >= occupancy.size():
		return false
	var line: String = occupancy[row]
	if column < 0 or column >= line.length():
		return false
	return line[column] == "1"


static func _by_platform(a: Variant, b: Variant) -> bool:
	var left: Dictionary = a
	var right: Dictionary = b
	if not is_equal_approx(float(left["left"]), float(right["left"])):
		return float(left["left"]) < float(right["left"])
	if not is_equal_approx(float(left["deckY"]), float(right["deckY"])):
		return float(left["deckY"]) < float(right["deckY"])
	return String(left["id"]) < String(right["id"])
