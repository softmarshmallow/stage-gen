class_name FamilyNavLanes
extends RefCounted

## Where a body may walk without leaving the ground.
##
## A port of `web/lib/families/navigation/lanes.ts`. A lane is a run of adjacent
## columns whose surfaces agree to within a tolerance, and it is precisely the
## run the controller walks without leaving the ground: `resolve_terrain_walk`
## refuses any column standing above the foot, so slopes do not exist here and a
## terrain of stepped tiles is a stack of level shelves, which is what it is.
##
## Adjacent connectivity is the form that subsumes both readings of the rule. At
## tolerance zero it is equality between neighbours, which chains to equality
## with any column in the run; at a nonzero tolerance it is the graph's own cut.
## Nothing here is in pixels or in rows — a surface is whatever the caller
## measures surfaces in.


## Every lane in the field, left to right. `endColumn` is exclusive.
##
## An empty array for a negative tolerance or a non-finite surface, which is a
## refusal rather than a guess: a field whose heights are not numbers describes
## no ground, and cutting it into shelves would invent them.
static func terrain_lanes(surfaces: PackedFloat64Array, tolerance: float) -> Array:
	if tolerance < 0.0:
		return []
	for surface: float in surfaces:
		if not is_finite(surface):
			return []
	var lanes: Array = []
	var start := 0
	var columns := surfaces.size()
	for column in range(1, columns + 1):
		if column < columns and absf(surfaces[column] - surfaces[column - 1]) <= tolerance:
			continue
		lanes.append(
			{"startColumn": start, "endColumn": column, "surface": surfaces[start]}
		)
		start = column
	return lanes
