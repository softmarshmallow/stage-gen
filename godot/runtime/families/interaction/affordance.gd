class_name FamilyAffordance
extends RefCounted

## Which of several things a verb acts on.
##
## A port of `web/lib/families/interaction/affordance.ts`. Two genres select an
## affordance and they measure differently: the platformer picks the nearest
## available candidate, and the room has no space to measure at all — so the
## first available one the author wrote wins.
##
## That second shape is a real one rather than a degenerate proximity. Two
## interactions on the same verb and hotspot are a general case and a special
## one, and the author put them in that order on purpose.


## The index of the winning candidate, or -1 for none.
##
## `available` answers whether a candidate can fire. `distance` is optional: an
## invalid Callable means "no space", and the first available candidate wins.
static func select(count: int, available: Callable, distance: Callable = Callable()) -> int:
	var best := -1
	var best_distance := INF
	for index in count:
		if not bool(available.call(index)):
			continue
		if not distance.is_valid():
			return index
		var measured := float(distance.call(index))
		if measured < best_distance:
			best = index
			best_distance = measured
	return best
