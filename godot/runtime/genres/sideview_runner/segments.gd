class_name RunnerSegments
extends RefCounted

## The level, streamed a window at a time.
##
## A port of `web/lib/sideview-runner/segments.ts`. A runner has no authored
## level: it has a catalogue of chunks and a rule for picking the next one, and
## the world ahead of the avatar is built as it is needed and dropped once it is
## behind.
##
## **Every draw from the run's generator happens here or in the session's next
## seed, and nowhere else.** `select_chunk_index` and `select_rest_index` each
## spend exactly one draw; placing an arena spends none. That is what makes "how
## many times has this run drawn" a divergence signal a parity harness can use.


## The rest cadence and speed ramp of each profile.
static func ramp_profile(name: String) -> Dictionary:
	var brisk := name == "brisk_ramp_v1"
	return {
		"columnsPerCeilingStep": 60.0,
		"maxCeiling": 10,
		"minCeilingLag": 3,
		"restEveryAppends": 6,
		"maxSpeedBonus": 0.5,
		"speedRampColumns": 720.0 if brisk else 1800.0,
	}


static func create(rows: int, walk_surface_row: int) -> Dictionary:
	return {
		"rows": rows,
		"walkSurfaceRow": walk_surface_row,
		"chunks": [],
		"nextColumn": 0,
		"lastChunkIndex": -1,
		"appendsSinceRest": 0,
	}


## Append chunks until the stream reaches `through_column`.
##
## `selection` carries `ceiling`, `floor`, and optionally `restEveryAppends` and
## `arena`. An arena is placed verbatim and touches neither the rest counter nor
## the generator, because a fight is the director's decision rather than a roll.
static func stream_ahead(
	stream: Dictionary,
	catalog: Array,
	selection: Dictionary,
	rng: KernelRng,
	through_column: int
) -> void:
	var rest_every := int(selection.get("restEveryAppends", 0))
	var arena: Dictionary = selection.get("arena", {})
	while int(stream["nextColumn"]) <= through_column:
		if not arena.is_empty():
			_push(stream, arena, int(stream["nextColumn"]))
			stream["nextColumn"] = int(stream["nextColumn"]) + int(arena["width"])
			continue
		var resting := rest_every > 0 and int(stream["appendsSinceRest"]) + 1 >= rest_every
		var index := (
			select_rest_index(catalog, rng, int(stream["lastChunkIndex"]))
			if resting
			else select_chunk_index(catalog, selection, rng, int(stream["lastChunkIndex"]))
		)
		var chunk: Dictionary = catalog[index]
		_push(stream, chunk, int(stream["nextColumn"]))
		stream["nextColumn"] = int(stream["nextColumn"]) + int(chunk["width"])
		stream["lastChunkIndex"] = index
		stream["appendsSinceRest"] = 0 if resting else int(stream["appendsSinceRest"]) + 1


## Which chunk comes next. Exactly one draw.
##
## The pool is everything inside the difficulty band; failing that, everything
## under the ceiling; failing that, the easiest chunks there are — so a band
## that admits nothing still yields a level rather than a refusal mid-run. The
## previous chunk is dropped from the pool when something else is available,
## which is the only variety rule.
static func select_chunk_index(
	chunks: Array, selection: Dictionary, rng: KernelRng, previous_index: int
) -> int:
	var floor_value := int(selection.get("floor", 1))
	var ceiling := int(selection.get("ceiling", 1))
	var banded: Array = []
	var under_ceiling: Array = []
	for index in chunks.size():
		var difficulty := int((chunks[index] as Dictionary)["difficulty"])
		if difficulty <= ceiling:
			under_ceiling.append(index)
			if difficulty >= floor_value:
				banded.append(index)
	var pool: Array = banded if not banded.is_empty() else under_ceiling
	if pool.is_empty():
		var easiest := 0x7FFFFFFF
		for entry: Variant in chunks:
			easiest = mini(easiest, int((entry as Dictionary)["difficulty"]))
		for index in chunks.size():
			if int((chunks[index] as Dictionary)["difficulty"]) == easiest:
				pool.append(index)
	if previous_index >= 0 and pool.size() > 1:
		var varied: Array = []
		for index: Variant in pool:
			if int(index) != previous_index:
				varied.append(index)
		if not varied.is_empty():
			pool = varied
	return int(pool[mini(pool.size() - 1, int(floor(rng.next() * float(pool.size()))))])


## The easiest chunk there is, drawn the same way. Also exactly one draw.
static func select_rest_index(chunks: Array, rng: KernelRng, previous_index: int) -> int:
	var easiest := 0x7FFFFFFF
	for entry: Variant in chunks:
		easiest = mini(easiest, int((entry as Dictionary)["difficulty"]))
	return select_chunk_index(chunks, {"ceiling": easiest, "floor": easiest}, rng, previous_index)


## Forget the chunks entirely behind the avatar.
static func drop_behind(stream: Dictionary, before_column: int) -> void:
	var chunks: Array = stream["chunks"]
	while not chunks.is_empty():
		var first: Dictionary = chunks[0]
		if int(first["startColumn"]) + int(first["width"]) >= before_column:
			break
		chunks.remove_at(0)


## The chunk a world column falls in, or an empty dictionary past the window.
static func chunk_at(stream: Dictionary, world_column: int) -> Dictionary:
	for entry: Variant in (stream["chunks"] as Array):
		var chunk: Dictionary = entry
		var start := int(chunk["startColumn"])
		if world_column >= start and world_column < start + int(chunk["width"]):
			return chunk
	return {}


## The surface row at a world column: -1 for a pit, and a refusal past the
## window.
##
## The browser threw here, and the throw was load-bearing: a column outside the
## streamed window means the avatar has outrun the stream, which is a defect in
## the streaming rather than a hole in the floor. GDScript has no exceptions, so
## the two are told apart by value — -1 is a pit the body falls through, and
## `OUTSIDE` is a bug that must not be read as one.
const OUTSIDE := -2

static func surface_row_at(stream: Dictionary, world_column: int) -> int:
	var chunk := chunk_at(stream, world_column)
	if chunk.is_empty():
		return OUTSIDE
	return FamilySurface.bottom_contiguous_surface_row(
		chunk["occupancy"], world_column - int(chunk["startColumn"])
	)


## Every hazard in the retained window, in chunk order then authored order.
static func streamed_hazards(stream: Dictionary) -> Array:
	var made: Array = []
	for entry: Variant in (stream["chunks"] as Array):
		var chunk: Dictionary = entry
		for hazard: Variant in (chunk["hazards"] as Array):
			made.append(hazard)
	return made


## Every pickup in the retained window, in the same order.
static func streamed_pickups(stream: Dictionary) -> Array:
	var made: Array = []
	for entry: Variant in (stream["chunks"] as Array):
		var chunk: Dictionary = entry
		for pickup: Variant in (chunk["pickups"] as Array):
			made.append(pickup)
	return made


static func _push(stream: Dictionary, chunk: Dictionary, start_column: int) -> void:
	var hazards: Array = []
	for entry: Variant in (chunk["hazards"] as Array):
		var hazard: Dictionary = entry
		hazards.append(
			{
				"propId": hazard["propId"],
				"worldColumn": start_column + int(hazard["column"]),
				"anchor": hazard["anchor"],
				"clearanceRows": hazard["clearanceRows"],
			}
		)
	var pickups: Array = []
	for entry: Variant in (chunk["pickups"] as Array):
		var pickup: Dictionary = entry
		pickups.append(
			{
				"itemId": pickup["itemId"],
				"worldColumn": start_column + int(pickup["column"]),
				"row": pickup["row"],
			}
		)
	(stream["chunks"] as Array).append(
		{
			"segmentId": chunk["segmentId"],
			"difficulty": chunk["difficulty"],
			"role": chunk["role"],
			"startColumn": start_column,
			"width": chunk["width"],
			"occupancy": chunk["occupancy"],
			"hazards": hazards,
			"pickups": pickups,
		}
	)
