class_name FamilyNavGraph
extends RefCounted

## How a body gets from where it stands to where it wants to be.
##
## A port of `web/lib/families/navigation/graph.ts`. One graph, derived from the
## traversal core, for every character that moves under its own steam.
##
## A jump link is a promise, and it is kept only because the admission and the
## physics read one integrator: `FamilyJump.simulate_jump_arc` is the traversal
## family's, the same fixed-step semi-implicit Euler the controller steps. That
## is why this family sits on top of `sideview/traversal` rather than beside it.
##
## Deliberately the layer that knows nothing about *why* a destination was
## chosen. A behaviour picks a target; navigation answers two questions about it:
## can I reach it, and what do I press this frame to get closer. Keeping those
## apart is what lets a repertoire grow without rewriting a decision — teaching a
## body to double jump, to climb, or to drop through a floor changes the graph
## and the steering, and everything that merely wanted to reach something
## inherits the new ability for free.
##
## The repertoire itself is data. A capability set states what this character can
## physically do, and a link is admitted only when the character that owns those
## capabilities can traverse it. A body with no air jump is therefore not a body
## that tries and fails to reach the high ledge: it is a body for which the high
## ledge does not exist, and which walks around instead.

const MOVE_WALK := "walk"
const MOVE_STEP_DOWN := "step_down"
const MOVE_JUMP := "jump"
const MOVE_DOUBLE_JUMP := "double_jump"
const MOVE_CLIMB := "climb"
const MOVE_DROP_THROUGH := "drop_through"

const KIND_TERRAIN := "terrain"
const KIND_PLATFORM := "platform"

## Penalties, in seconds, for moves that cost more than the ground they cover.
##
## A jump is not merely the time it takes; it commits the character to an arc it
## cannot steer out of, so an equally long walk is worth preferring. A drop
## through a floor is cheap but irreversible from below, and a double jump is the
## most committing move there is.
const MOVE_PENALTY_SECONDS := {
	MOVE_WALK: 0.0,
	MOVE_STEP_DOWN: 0.1,
	MOVE_JUMP: 0.35,
	MOVE_DOUBLE_JUMP: 0.7,
	MOVE_CLIMB: 0.3,
	MOVE_DROP_THROUGH: 0.25,
}

## Half a tile, which is how far past an edge a landing point sits so a ledge is
## actually cleared.
const LEDGE_MARGIN_FRACTION := 0.5

## How many fixed steps an arc is integrated for before it is called unreachable.
const JUMP_PROOF_MAX_STEPS := 120

## A body with no second jump. GDScript has no nullable float, so the absence is
## a value outside every real impulse — the same convention `resolve_jump_request`
## uses for a coyote window that is not open.
const NO_AIR_JUMP := -1.0


static func empty_graph() -> Dictionary:
	return {"nodes": [], "links": []}


## Close a capability set, refusing one that cannot describe a body.
##
## The defaults are the caller's, not the family's: a genre binds its own
## controller constants so that the model a navigator has of itself is the model
## its physics uses, and a navigator that is deliberately weaker overrides a
## field rather than forking the graph. An empty dictionary is the refusal.
static func movement_capabilities(base: Dictionary, overrides: Dictionary = {}) -> Dictionary:
	var merged: Dictionary = {}
	for key: Variant in base:
		merged[key] = base[key]
	for key: Variant in overrides:
		merged[key] = overrides[key]
	for field: String in [
		"walkSpeed", "runSpeed", "jumpVelocity", "gravity", "stepSeconds", "stepUpTolerance"
	]:
		var value := float(merged.get(field, 0.0))
		if not is_finite(value) or value <= 0.0:
			return {}
	var air := float(merged.get("airJumpVelocity", NO_AIR_JUMP))
	if air > 0.0 and not is_finite(air):
		return {}
	return merged


static func _horizontal_gap(from: Dictionary, to: Dictionary) -> float:
	if float(to["left"]) > float(from["right"]):
		return float(to["left"]) - float(from["right"])
	if float(from["left"]) > float(to["right"]):
		return float(from["left"]) - float(to["right"])
	return 0.0


## The span two nodes share, or an empty dictionary when they merely touch or
## miss entirely.
static func _overlap_span(a: Dictionary, b: Dictionary) -> Dictionary:
	var left := maxf(float(a["left"]), float(b["left"]))
	var right := minf(float(a["right"]), float(b["right"]))
	return {"left": left, "right": right} if right > left else {}


## A point on `node` at `x`, pulled inside its edges.
##
## Landing points have to sit inside the shelf they name rather than on its lip:
## steering walks toward the landing point, and one exactly on the edge is a
## point the character oscillates around as it crosses back and forth over it.
static func _point_inside(node: Dictionary, x: float, margin: float) -> float:
	var left := float(node["left"])
	var right := float(node["right"])
	var inset := minf(margin, (right - left) / 2.0)
	return minf(right - inset, maxf(left + inset, x))


## Whether a rise-and-gap is jumpable, and with which of the body's two jumps.
##
## Both answers come from the traversal family's integration, the same one the
## controller steps, so the graph cannot promise an arc the character falls short
## of. The single jump is tried first: a route that does not need the air jump
## should not spend it. An empty string is "neither".
static func _jump_move_for(rise: float, gap: float, capabilities: Dictionary) -> String:
	var use_rise := maxf(0.0, rise)
	var use_gap := maxf(0.0, gap)
	var speed := float(capabilities["runSpeed"])
	var jump_velocity := float(capabilities["jumpVelocity"])
	var gravity := float(capabilities["gravity"])
	var step_seconds := float(capabilities["stepSeconds"])
	var single := FamilyJump.simulate_jump_arc(
		use_rise, use_gap, speed, jump_velocity, NO_AIR_JUMP, gravity, step_seconds,
		JUMP_PROOF_MAX_STEPS
	)
	if bool(single.get("reachable", false)):
		return MOVE_JUMP
	var air_jump := float(capabilities.get("airJumpVelocity", NO_AIR_JUMP))
	if air_jump <= 0.0:
		return ""
	var double := FamilyJump.simulate_jump_arc(
		use_rise, use_gap, speed, jump_velocity, air_jump, gravity, step_seconds,
		JUMP_PROOF_MAX_STEPS
	)
	return MOVE_DOUBLE_JUMP if bool(double.get("reachable", false)) else ""


static func _link_cost(move: String, from_x: float, to_x: float, capabilities: Dictionary) -> float:
	return absf(to_x - from_x) / float(capabilities["runSpeed"]) + float(MOVE_PENALTY_SECONDS[move])


## One traversal. `climbableId` is `""` for every move that is not a climb.
static func _make_link(
	from: Dictionary,
	to: Dictionary,
	move: String,
	from_x: float,
	to_x: float,
	gap: float,
	climbable_id: String,
	capabilities: Dictionary
) -> Dictionary:
	return {
		"id": "%s>%s:%s" % [from["id"], to["id"], move],
		"from": String(from["id"]),
		"to": String(to["id"]),
		"move": move,
		"fromX": from_x,
		"toX": to_x,
		# Positive upward, so a climb and a jump report a rise and a fall reports
		# a negative one.
		"rise": float(from["surfaceY"]) - float(to["surfaceY"]),
		"gap": gap,
		"climbableId": climbable_id,
		"cost": _link_cost(move, from_x, to_x, capabilities),
	}


## Cut the terrain into level lanes, as nodes.
static func _lane_nodes(
	column_surface_y: PackedFloat64Array, tile_units: float, tolerance: float
) -> Array:
	var made: Array = []
	var lanes := FamilyNavLanes.terrain_lanes(column_surface_y, tolerance)
	for index in range(lanes.size()):
		var span: Dictionary = lanes[index]
		made.append(
			{
				"id": "terrain:%d" % index,
				"kind": KIND_TERRAIN,
				"left": float(span["startColumn"]) * tile_units,
				"right": float(span["endColumn"]) * tile_units,
				"surfaceY": float(span["surface"]),
			}
		)
	return made


## Links between two shelves that share a boundary.
##
## Terrain lanes tile the map end to end, so "shares a boundary" and "is the next
## lane along" are the same statement, and two lanes with a third between them are
## deliberately not linked: clearing an intervening shelf is not a move this model
## describes, and pretending otherwise would hand the steering an arc the
## character flies into the side of. An empty dictionary is "no link".
static func _neighbour_link(
	from: Dictionary,
	to: Dictionary,
	boundary: float,
	toward_sign: float,
	tile_units: float,
	capabilities: Dictionary
) -> Dictionary:
	var margin := tile_units * LEDGE_MARGIN_FRACTION
	var from_x := _point_inside(from, boundary, 1.0)
	var to_x := _point_inside(to, boundary + toward_sign * margin, 1.0)
	var climb := float(from["surfaceY"]) - float(to["surfaceY"])
	if absf(climb) <= float(capabilities["stepUpTolerance"]):
		return _make_link(from, to, MOVE_WALK, from_x, to_x, 0.0, "", capabilities)
	if climb < 0.0:
		return _make_link(from, to, MOVE_STEP_DOWN, from_x, to_x, 0.0, "", capabilities)
	var move := _jump_move_for(climb, 0.0, capabilities)
	if move.is_empty():
		return {}
	return _make_link(from, to, move, from_x, to_x, 0.0, "", capabilities)


## Links between a deck and anything else within reach of it.
##
## Decks are the one geometry that can sit over, beside, or under another, so
## their rules are stated per relationship rather than per neighbour: a shelf
## above is jumped to, a shelf that runs out past the deck's edge is stepped off
## onto, and a shelf directly underneath is dropped through when the character
## has that move at all. A deck a shelf neither overlaps nor reaches is not
## linked, and is simply somewhere the navigator does not go.
static func _deck_links(
	from: Dictionary, to: Dictionary, tile_units: float, capabilities: Dictionary
) -> Array:
	var margin := tile_units * LEDGE_MARGIN_FRACTION
	var gap := _horizontal_gap(from, to)
	if gap > tile_units * 4.0:
		return []
	var overlap := _overlap_span(from, to)
	var climb := float(from["surfaceY"]) - float(to["surfaceY"])
	var links: Array = []
	if absf(climb) <= float(capabilities["stepUpTolerance"]):
		if gap > tile_units * 0.5:
			return []
		var rightward := float(to["left"]) >= float(from["right"])
		var boundary: float = float(from["right"]) if rightward else float(from["left"])
		var toward_sign := 1.0 if rightward else -1.0
		return [
			_make_link(
				from,
				to,
				MOVE_WALK,
				_point_inside(from, boundary, 1.0),
				_point_inside(to, boundary + toward_sign * margin, 1.0),
				gap,
				"",
				capabilities
			)
		]
	if climb > 0.0:
		# `to` stands above `from`, so the only way onto it is an arc the physics
		# agrees with.
		var move := _jump_move_for(climb, gap, capabilities)
		if move.is_empty():
			return []
		var launch_x := 0.0
		if overlap.is_empty():
			var edge: float = (
				float(from["right"])
				if float(to["left"]) >= float(from["right"])
				else float(from["left"])
			)
			launch_x = _point_inside(from, edge, 1.0)
		else:
			launch_x = _point_inside(
				from, (float(overlap["left"]) + float(overlap["right"])) / 2.0, 1.0
			)
		var land_x := _point_inside(
			to, launch_x, minf(margin, (float(to["right"]) - float(to["left"])) / 2.0)
		)
		return [_make_link(from, to, move, launch_x, land_x, gap, "", capabilities)]
	# `to` lies below. Walking off an edge works only where `to` actually
	# continues past it.
	var side := 0.0
	if float(to["left"]) < float(from["left"]):
		side = -1.0
	elif float(to["right"]) > float(from["right"]):
		side = 1.0
	if not is_zero_approx(side):
		var edge_x: float = float(from["left"]) if side < 0.0 else float(from["right"])
		links.append(
			_make_link(
				from,
				to,
				MOVE_STEP_DOWN,
				_point_inside(from, edge_x, 1.0),
				_point_inside(to, edge_x + side * margin, 1.0),
				gap,
				"",
				capabilities
			)
		)
	var wide_enough := (
		not overlap.is_empty()
		and float(overlap["right"]) - float(overlap["left"]) >= tile_units * 0.25
	)
	if bool(capabilities["canDropThrough"]) and String(from["kind"]) == KIND_PLATFORM and wide_enough:
		var through_x := (float(overlap["left"]) + float(overlap["right"])) / 2.0
		links.append(
			_make_link(
				from, to, MOVE_DROP_THROUGH, through_x, through_x, 0.0, "", capabilities
			)
		)
	return links


## The node a climbable's end stands on, or an empty dictionary when neither end
## lands on one.
static func _node_at(nodes: Array, surface_y: float, center_x: float, tolerance: float) -> Dictionary:
	for entry: Variant in nodes:
		var node: Dictionary = entry
		if absf(float(node["surfaceY"]) - surface_y) > tolerance:
			continue
		if float(node["left"]) <= center_x and center_x <= float(node["right"]):
			return node
	return {}


## Derive the traversal graph for one map.
##
## `input` is `{columnSurfaceY, tileUnits, platforms, climbables, capabilities}`.
## Every link is admitted by a rule that names a real mechanic — walking a level
## shelf, stepping off a ledge, jumping a rise the physics proves reachable,
## climbing a declared zone, dropping through a one-way deck — and no link is
## admitted that the supplied capabilities cannot perform. The result is a graph
## specific to *this* character in *this* world, which is why it is rebuilt on map
## entry against the capabilities of whoever is about to walk it.
##
## An empty graph is the refusal, for a tile size that is not positive or a
## surface that is not a number: both describe ground that is not there.
static func build(input: Dictionary) -> Dictionary:
	var tile_units := float(input["tileUnits"])
	if not is_finite(tile_units) or tile_units <= 0.0:
		return empty_graph()
	var column_surface_y: PackedFloat64Array = input["columnSurfaceY"]
	for surface: float in column_surface_y:
		if not is_finite(surface):
			return empty_graph()
	var capabilities: Dictionary = input["capabilities"]
	var lanes := _lane_nodes(column_surface_y, tile_units, float(capabilities["stepUpTolerance"]))
	var nodes: Array = lanes.duplicate()
	for entry: Variant in (input["platforms"] as Array):
		var platform: Dictionary = entry
		nodes.append(
			{
				"id": "platform:%s" % platform["id"],
				"kind": KIND_PLATFORM,
				"left": float(platform["left"]),
				"right": float(platform["right"]),
				"surfaceY": float(platform["deckY"]),
			}
		)
	var links: Array = []

	for index in range(lanes.size() - 1):
		var left: Dictionary = lanes[index]
		var right: Dictionary = lanes[index + 1]
		var boundary := float(left["right"])
		for pair: Array in [[left, right, 1.0], [right, left, -1.0]]:
			var link := _neighbour_link(
				pair[0], pair[1], boundary, pair[2], tile_units, capabilities
			)
			if not link.is_empty():
				links.append(link)

	for from_entry: Variant in nodes:
		var from: Dictionary = from_entry
		for to_entry: Variant in nodes:
			var to: Dictionary = to_entry
			if String(from["id"]) == String(to["id"]):
				continue
			if String(from["kind"]) == KIND_TERRAIN and String(to["kind"]) == KIND_TERRAIN:
				continue
			links.append_array(_deck_links(from, to, tile_units, capabilities))

	if bool(capabilities["canClimb"]):
		var tolerance := float(capabilities["stepUpTolerance"])
		for entry: Variant in (input["climbables"] as Array):
			var climbable: Dictionary = entry
			var center_x := float(climbable["centerX"])
			var upper := _node_at(nodes, float(climbable["upperDeckY"]), center_x, tolerance)
			var lower := _node_at(nodes, float(climbable["lowerSurfaceY"]), center_x, tolerance)
			if upper.is_empty() or lower.is_empty() or String(upper["id"]) == String(lower["id"]):
				continue
			for pair: Array in [[lower, upper], [upper, lower]]:
				links.append(
					_make_link(
						pair[0],
						pair[1],
						MOVE_CLIMB,
						center_x,
						center_x,
						0.0,
						String(climbable["id"]),
						capabilities
					)
				)

	links.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return String(a["id"]) < String(b["id"]))
	return {"nodes": nodes, "links": links}


## Cost and opening move to every node reachable from `from_node_id`.
##
## One search per frame answers every "can I get there, and how do I start"
## question a behaviour has, which is why a navigator carries no path in memory:
## re-deriving is cheaper than invalidating, and a plan recomputed from the world
## each frame cannot go stale behind a moving target. Ties break on node id so two
## equal routes always resolve the same way, on every replay.
##
## Each entry is `{nodeId, cost, firstLink}`, where `firstLink` is an empty
## dictionary for the node already occupied.
static func reach(graph: Dictionary, from_node_id: String) -> Array:
	var nodes: Array = graph["nodes"]
	var known := false
	for entry: Variant in nodes:
		if String((entry as Dictionary)["id"]) == from_node_id:
			known = true
			break
	if not known:
		return []
	var links: Array = graph["links"]
	var settled: Dictionary = {}
	var best := {from_node_id: 0.0}
	var opening := {from_node_id: {}}
	var pending := {from_node_id: true}
	while not pending.is_empty():
		var current_id := ""
		var current_cost := INF
		for candidate: Variant in pending:
			var name := String(candidate)
			var cost := float(best.get(name, INF))
			if cost < current_cost or (cost == current_cost and (current_id.is_empty() or name < current_id)):
				current_id = name
				current_cost = cost
		if current_id.is_empty():
			break
		pending.erase(current_id)
		settled[current_id] = {
			"nodeId": current_id,
			"cost": current_cost,
			"firstLink": opening.get(current_id, {}),
		}
		for entry: Variant in links:
			var link: Dictionary = entry
			if String(link["from"]) != current_id or settled.has(String(link["to"])):
				continue
			var to_id := String(link["to"])
			var cost := current_cost + float(link["cost"])
			if best.has(to_id) and float(best[to_id]) <= cost:
				continue
			best[to_id] = cost
			var carried: Dictionary = opening.get(current_id, {})
			opening[to_id] = link if current_id == from_node_id or carried.is_empty() else carried
			pending[to_id] = true
	var made: Array = settled.values()
	made.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		return String(a["nodeId"]) < String(b["nodeId"]))
	return made


## The reach entry for one node, or an empty dictionary when it is unreachable.
static func reach_of(entries: Array, node_id: String) -> Dictionary:
	for entry: Variant in entries:
		var found: Dictionary = entry
		if String(found["nodeId"]) == node_id:
			return found
	return {}


## Which node a point stands on.
##
## Never empty for a non-empty graph, and that is deliberate: a character mid-jump
## is over some shelf even when it is on none of them, and a navigator that lost
## itself between two nodes would stop dead exactly when it most needs to keep
## steering. The nearest surface under the foot wins, falling back to the nearest
## surface at all.
static func locate(graph: Dictionary, x: float, foot_y: float) -> Dictionary:
	var nodes: Array = graph["nodes"]
	if nodes.is_empty():
		return {}
	var best: Dictionary = nodes[0]
	var best_score := _locate_score(best, x, foot_y)
	for index in range(1, nodes.size()):
		var node: Dictionary = nodes[index]
		var score := _locate_score(node, x, foot_y)
		if _closer(score, best_score, String(node["id"]), String(best["id"])):
			best = node
			best_score = score
	return best


## Horizontal distance first, then whether the surface is under the foot at all,
## then how far under it, and finally the node id — so two shelves that score
## identically always resolve the same way, on every replay.
static func _closer(
	score: PackedFloat64Array, best: PackedFloat64Array, node_id: String, best_id: String
) -> bool:
	for index in range(score.size()):
		if score[index] != best[index]:
			return score[index] < best[index]
	return node_id < best_id


static func _locate_score(node: Dictionary, x: float, foot_y: float) -> PackedFloat64Array:
	var left := float(node["left"])
	var right := float(node["right"])
	var horizontal := 0.0
	if x < left or x > right:
		horizontal = minf(absf(left - x), absf(right - x))
	var below := 0.0 if float(node["surfaceY"]) >= foot_y - 1.0 else 1.0
	return PackedFloat64Array([horizontal, below, absf(float(node["surfaceY"]) - foot_y)])
