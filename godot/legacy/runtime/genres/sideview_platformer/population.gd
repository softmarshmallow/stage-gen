class_name PlatformerPopulation
extends RefCounted

## How many creatures a route carries, and where each one stands up.
##
## A port of `prepared-population.ts` (the authored block projected into integer
## columns) and the paths of `spawn-director.ts` this genre actually walks. The
## authored vocabulary is fractional and per-map — a zone is a stretch of the
## route named by two fractions — and the director works in columns, so the
## projection is where "0.12 to 0.6 of the road" becomes "columns 5 to 23".
##
## **Every number below is drawn, and the draws are the contract.** One
## reservation costs one draw for which creature and one to three for where it
## stands, in that order, from a generator seeded off the map and zone names and
## the map's own salt. A port that drew the same numbers in a different order
## would populate a different route from the same package, so the order is as
## much a part of this as the arithmetic.
##
## **The policy is the consumer's, not the package's.** The package names
## populations and species; how those bodies are arranged is how the route feels,
## and the scene owns it: spawns may land in view, they stand half a tile apart
## rather than more than one, and they usually join a group already standing
## rather than spreading evenly. Those four overrides are `POLICY` below.
##
## What is not here yet: death tickets, the replacement policies, and the
## set-piece and wave readings of the same authored zones. The golden reaches
## none of them, and a system written against no evidence is a system nobody has
## checked.

## The hunting-ground policy, in tiles of the genre's own grid.
const SEPARATION_TILES := 0.5
const CLUSTER_RADIUS_TILES := 2.5
const PLAYER_DISTANCE_TILES := 2.5
const WANDER_RADIUS_TILES := 1.5

## How often a group already standing pulls the next one towards it.
const CLUSTER_JOIN_CHANCE := 0.7

## Columns nothing may stand up in.
##
## Six at each end of a map, and two either side of every gate. The first keeps
## creatures off the strip a body walks in on, where a spawn would be a fight
## nobody chose; the second keeps a doorway clear, so a route can always be left
## by the way it was entered.
##
## Not decoration: it narrows the candidate list, and the candidate list is what
## a placement draws against. Leaving it out moves every column a route ever
## spawns in.
const EDGE_MARGIN_COLUMNS := 6
const PORTAL_MARGIN_COLUMNS := 2

## The two surfaces a zone may be authored over. A zone on `terrain` stands its
## creatures on the ground only; one on `terrain_and_decks` populates every ledge
## over it as well.
const SURFACE_TERRAIN_AND_DECKS := "terrain_and_decks"


## The columns a map keeps clear, by index.
static func reserved_columns(world_columns: int, portal_fractions: PackedFloat32Array) -> Dictionary:
	var made := {}
	for column in range(mini(EDGE_MARGIN_COLUMNS, world_columns)):
		made[column] = true
	for column in range(maxi(0, world_columns - EDGE_MARGIN_COLUMNS), world_columns):
		made[column] = true
	for fraction in portal_fractions:
		var anchor := int(floor(fraction * float(world_columns)))
		for offset in range(-PORTAL_MARGIN_COLUMNS, PORTAL_MARGIN_COLUMNS + 1):
			var column := anchor + offset
			if column >= 0 and column < world_columns:
				made[column] = true
	return made


## The generator's substitute for a seed of zero, so a zero-seeded zone still
## draws rather than repeating one value.
const ZERO_SEED_SUBSTITUTE := 0x6D2B79F5


## Project one map's authored population into zones and their candidate columns.
##
## Returns `{zones: [...]}` or an empty dictionary when the map authors none.
static func project(package: Dictionary, map_id: String) -> Dictionary:
	var authored: Dictionary = _map_block(package, map_id)
	if authored.is_empty():
		return {}
	var map: Dictionary = (package["maps"] as Dictionary)[map_id]
	var heights: PackedInt32Array = map["heights"]
	var world_columns := heights.size()
	var gates := PackedFloat32Array()
	for entry: Variant in (map["endpoints"] as Array):
		gates.append(float((entry as Dictionary)["normalizedX"]))
	var reserved := reserved_columns(world_columns, gates)
	var tile := PlatformerMaps.TILE_PX
	var wander := roundi(tile * WANDER_RADIUS_TILES)

	# The slot table is the map's, not a zone's: every mob id any zone can spawn,
	# sorted, and a slot is an index into that. Two zones that both spawn moths
	# name the same slot, which is what lets one creature's kind be read off a
	# reservation without knowing which zone issued it.
	var slots := {}
	var ids := PackedStringArray()
	for entry: Variant in (authored.get("zones", []) as Array):
		for row: Variant in ((entry as Dictionary).get("spawn_table", []) as Array):
			var mob_id := String((row as Dictionary).get("mob_id", ""))
			if not ids.has(mob_id):
				ids.append(mob_id)
	ids.sort()
	for index in range(ids.size()):
		slots[ids[index]] = index

	var zones: Array = []
	for entry: Variant in (authored.get("zones", []) as Array):
		var zone: Dictionary = entry
		var left := clampi(
			int(ceil(float(zone.get("left_fraction", 0.0)) * world_columns - 0.5)),
			0,
			world_columns
		)
		var right := clampi(
			int(ceil(float(zone.get("right_fraction", 0.0)) * world_columns - 0.5)),
			0,
			world_columns
		)
		if right <= left:
			continue
		var left_px := float(left) * tile
		var right_px := float(right) * tile
		var on_decks := String(zone.get("surface", "terrain")) == SURFACE_TERRAIN_AND_DECKS
		var candidates: Array = []
		for column in range(left, right):
			if heights[column] <= 0 or reserved.has(column):
				continue
			var x := float(column) * tile + tile / 2.0
			# A body needs room to wander inside its own zone, so a column whose
			# wander circle leaves the zone is not a place to stand up.
			if x - wander < left_px or x + wander >= right_px:
				continue
			candidates.append(
				{
					"column": column,
					"x": x,
					"y": PlatformerVertical.terrain_surface_y(
						heights[column], tile, PlatformerMaps.BASELINE_Y
					),
					"deckId": "",
				}
			)
			if not on_decks:
				continue
			# A storey adds footings rather than replacing the one below it: the
			# ground under a deck stays a place to stand, so a hunting ground is
			# populated on the floor and on every ledge over it. The pair (column,
			# deck) is what makes two of them different places.
			for footing: Variant in (map["platforms"] as Array):
				var deck: Dictionary = footing
				if x < float(deck["left"]) or x >= float(deck["right"]):
					continue
				candidates.append(
					{
						"column": column,
						"x": x,
						"y": float(deck["deckY"]),
						"deckId": String(deck["id"]),
					}
				)
		if candidates.is_empty():
			continue
		zones.append(
			{
				"zoneId": _kebab(String(zone.get("zone_id", ""))),
				"initialPopulation": int(zone.get("initial_population", 0)),
				"targetPopulation": int(zone.get("target_population", 0)),
				"populationCap": int(zone.get("population_cap", 0)),
				# The table as the director reads it: a *map-wide* slot rather than
				# a position in this zone's list, and the headcounts a draw is
				# bounded by. The projection fills the last two, because the author
				# names a species and a weight and nothing else.
				"spawnTable": _spawn_table(zone, slots, int(zone.get("population_cap", 0))),
				# One batch is the smaller of the map's budget and what this zone
				# could hold, and a zone waits out its own interval between batches.
				"spawnBatchSize": mini(
					int(authored.get("max_spawn_batch_per_update", 1)),
					int(zone.get("population_cap", 0))
				),
				"spawnIntervalMs": float(authored.get("update_interval_ms", 250)),
				"retryDelayMs": float(authored.get("update_interval_ms", 250)),
				"lastSpawnBatchAtMs": -1.0,
				"reservations": [],
				"candidates": candidates,
				"rng": KernelRng.new(
					_zone_seed(
						int(package["revision"]),
						map_id,
						_kebab(String(zone.get("zone_id", ""))),
						int(authored.get("seed_salt", 0))
					)
				),
				"alive": [],
				"tickets": [],
				"respawnDelayMs": float(zone.get("respawn_delay_ms", 0)),
				"initialized": false,
			}
		)
	if zones.is_empty():
		return {}
	return {
		"mapId": map_id,
		"zones": zones,
		"mobIdBySlot": ids,
		"updateIntervalMs": float(authored.get("update_interval_ms", 250)),
		"maxBatch": int(authored.get("max_spawn_batch_per_update", 1)),
		"lastUpdateAtMs": -1.0,
		# Which zone this map's budget is offered to first. It advances by one an
		# update, so a scarce budget rotates through the map's zones instead of
		# always feeding the one the author happened to list first.
		"nextZoneIndex": 0,
		"nextReservationSequence": 1,
	}


## One zone's table, with the map-wide slot and the headcounts a draw is bounded
## by. `min_alive` is nought and `max_alive` the zone's own cap: the author names
## a species and a weight, and how many of each a zone may hold is the cap it
## already published.
static func _spawn_table(zone: Dictionary, slots: Dictionary, cap: int) -> Array:
	var made: Array = []
	for entry: Variant in (zone.get("spawn_table", []) as Array):
		var row: Dictionary = entry
		made.append(
			{
				"mobSlot": int(slots.get(String(row.get("mob_id", "")), -1)),
				"weight": float(row.get("weight", 0.0)),
				"minAlive": 0,
				"maxAlive": cap,
			}
		)
	return made


## One director tick. Returns the reservations it issued, and nothing when the
## interval has not elapsed.
##
## A reservation is not a creature: it is a place held for one, and the caller
## turns it into a body and then says whether it managed to. Until it does, the
## place is spoken for and nothing else may stand there.
##
## `occupied` is what else is in the way that the director does not manage — the
## props along a route, and the creatures that are dead but still fading.
static func update(
	state: Dictionary,
	now_ms: float,
	player_x: float,
	player_y: float,
	occupied: Array = []
) -> Array:
	if state.is_empty():
		return []
	var last := float(state["lastUpdateAtMs"])
	if last >= 0.0 and now_ms - last < float(state["updateIntervalMs"]):
		return []
	state["lastUpdateAtMs"] = now_ms

	var zones: Array = state["zones"]
	if zones.is_empty():
		return []
	for entry: Variant in zones:
		var zone: Dictionary = entry
		var tickets: Array = zone["tickets"]
		if not bool(zone["initialized"]):
			zone["initialized"] = true
			_add_tickets(state, zone, int(zone["initialPopulation"]), now_ms)
			continue
		# A zone below its headcount with nothing already owed asks for the
		# difference now. A death has already put its own ticket in, due when the
		# route is meant to feel dangerous again. A reservation counts: it is a
		# creature the zone is already getting.
		var owed := (
			int(zone["targetPopulation"])
			- (zone["alive"] as Array).size()
			- (zone["reservations"] as Array).size()
			- tickets.size()
		)
		_add_tickets(state, zone, owed, now_ms)

	var issued: Array = []
	var start_index := int(state["nextZoneIndex"]) % zones.size()
	var budget := int(state["maxBatch"])
	for offset in range(zones.size()):
		if budget <= 0:
			break
		var zone: Dictionary = zones[(start_index + offset) % zones.size()]
		var made := _issue_for_zone(
			state,
			zone,
			now_ms,
			player_x,
			player_y,
			occupied,
			mini(int(zone["spawnBatchSize"]), budget)
		)
		for reservation: Variant in made:
			issued.append(reservation)
		budget -= made.size()
	state["nextZoneIndex"] = (start_index + 1) % zones.size()
	return issued


## One zone's share of this update.
static func _issue_for_zone(
	state: Dictionary,
	zone: Dictionary,
	now_ms: float,
	player_x: float,
	player_y: float,
	occupied: Array,
	capacity: int
) -> Array:
	var since := float(zone["lastSpawnBatchAtMs"])
	if since >= 0.0 and now_ms - since < float(zone["spawnIntervalMs"]):
		return []
	var tickets: Array = zone["tickets"]
	# Oldest first, and ties broken by the order they were written: a ticket that
	# has waited longer is filled first, and two that came due together are filled
	# in the order the zone owed them.
	var due: Array = []
	for entry: Variant in tickets:
		if float((entry as Dictionary)["dueAtMs"]) <= now_ms:
			due.append(entry)
	due.sort_custom(_by_ticket)

	var issued: Array = []
	for entry: Variant in due:
		var ticket: Dictionary = entry
		if issued.size() >= capacity:
			break
		if (
			(zone["alive"] as Array).size() + (zone["reservations"] as Array).size()
			>= int(zone["populationCap"])
		):
			break
		var made := _reserve(state, zone, player_x, player_y, occupied)
		if made.is_empty():
			# A place it could not find is not the end of the zone's batch: this
			# ticket waits out the retry delay and the next due one is tried. It has
			# already spent a draw on which creature, and that draw is spent whether
			# or not somewhere was found to put it.
			ticket["dueAtMs"] = now_ms + float(zone["retryDelayMs"])
			ticket["attemptCount"] = int(ticket["attemptCount"]) + 1
			continue
		tickets.erase(ticket)
		(zone["reservations"] as Array).append(made)
		issued.append(made)
	if not issued.is_empty():
		zone["lastSpawnBatchAtMs"] = now_ms
	return issued


## Turn a held place into a creature. The caller says which body it built.
static func confirm(state: Dictionary, reservation_id: String, instance_id: String) -> void:
	var found := _take_reservation(state, reservation_id)
	if found.is_empty():
		return
	var reservation: Dictionary = found["reservation"]
	reservation["instanceId"] = instance_id
	((found["zone"] as Dictionary)["alive"] as Array).append(reservation)


## Give a held place back. The ticket returns to the queue with a fresh deadline
## and the column is free again — which is what stops a body the caller could not
## build from costing the route a creature for the rest of the run.
static func reject(state: Dictionary, reservation_id: String, now_ms: float) -> void:
	var found := _take_reservation(state, reservation_id)
	if found.is_empty():
		return
	var zone: Dictionary = found["zone"]
	(zone["tickets"] as Array).append(
		{
			"dueAtMs": now_ms + float(zone["retryDelayMs"]),
			"sequence": _next_sequence(state),
			"attemptCount": 1,
		}
	)


static func _take_reservation(state: Dictionary, reservation_id: String) -> Dictionary:
	for entry: Variant in (state["zones"] as Array):
		var zone: Dictionary = entry
		var held: Array = zone["reservations"]
		for index in range(held.size()):
			if String((held[index] as Dictionary)["reservationId"]) != reservation_id:
				continue
			var reservation: Dictionary = held[index]
			held.remove_at(index)
			return {"zone": zone, "reservation": reservation}
	return {}


static func _add_tickets(state: Dictionary, zone: Dictionary, count: int, now_ms: float) -> void:
	for _index in range(maxi(0, count)):
		(zone["tickets"] as Array).append(
			{"dueAtMs": now_ms, "sequence": _next_sequence(state), "attemptCount": 0}
		)


static func _next_sequence(state: Dictionary) -> int:
	var sequence := int(state["nextReservationSequence"])
	state["nextReservationSequence"] = sequence + 1
	return sequence


static func _by_ticket(left: Dictionary, right: Dictionary) -> bool:
	if not is_equal_approx(float(left["dueAtMs"]), float(right["dueAtMs"])):
		return float(left["dueAtMs"]) < float(right["dueAtMs"])
	return int(left["sequence"]) < int(right["sequence"])


## One creature: which kind, then where. Two to four draws, always in that order.
static func _reserve(
	state: Dictionary,
	zone: Dictionary,
	player_x: float,
	player_y: float,
	occupied: Array
) -> Dictionary:
	var rng: KernelRng = zone["rng"]
	var slot := _select_slot(zone, rng)
	if slot < 0:
		return {}
	var eligible := _eligible(state, zone, player_x, player_y, occupied)
	if eligible.is_empty():
		return {}
	var chosen := _choose(zone, eligible, rng)
	return {
		"reservationId": "%s/%s/reservation/%d"
		% [String(state["mapId"]), String(zone["zoneId"]), _next_sequence(state)],
		"zoneId": zone["zoneId"],
		"mobSlot": slot,
		"surface": "terrain" if String(chosen["deckId"]).is_empty() else "deck",
		"deckId": chosen["deckId"],
		"column": chosen["column"],
		"x": chosen["x"],
		"y": chosen["y"],
	}


## Which creature, by weight. A single-entry table still draws, because the draw
## is the contract even when its answer is not in doubt.
static func _select_slot(zone: Dictionary, rng: KernelRng) -> int:
	# What this zone is already getting, counted by kind: the creatures standing
	# and the places held for ones that are not yet built.
	var counts := {}
	for group: Variant in [zone["alive"], zone["reservations"]]:
		for entry: Variant in (group as Array):
			var slot := int((entry as Dictionary)["mobSlot"])
			counts[slot] = int(counts.get(slot, 0)) + 1
	return admissible_slot(zone["spawnTable"], counts, rng.next())


## Which kind, out of the ones the zone may still have.
##
## The draw runs over the admissible pool and not over the whole table. A kind
## below its floor is the only one that may be drawn while any kind is below its
## floor; failing that, a kind already at its ceiling is not in the bag at all.
## Summing the weights over the whole table instead would draw a kind the zone
## cannot have and lose the ticket to it.
##
## `roll` is one number in [0, 1) and is always spent, because the draw is the
## contract even when its answer is not in doubt. Public because it is a rule,
## and because the projection this genre ships gives every kind the zone's own
## cap as its ceiling — which puts the ceiling and the cap in the same place and
## leaves the rule with no way to show itself through a whole update.
static func admissible_slot(table: Array, counts: Dictionary, roll: float) -> int:
	if table.is_empty():
		return -1
	var below: Array = []
	var under_cap: Array = []
	for entry: Variant in table:
		var row: Dictionary = entry
		var held := int(counts.get(int(row["mobSlot"]), 0))
		if held < int(row["minAlive"]):
			below.append(row)
		if held < int(row["maxAlive"]):
			under_cap.append(row)
	var pool: Array = below if not below.is_empty() else under_cap
	if pool.is_empty():
		return -1
	var total := 0.0
	for entry: Variant in pool:
		total += float((entry as Dictionary)["weight"])
	var selection := roll * total
	for entry: Variant in pool:
		var row: Dictionary = entry
		selection -= float(row["weight"])
		if selection < 0.0:
			return int(row["mobSlot"])
	return int((pool[pool.size() - 1] as Dictionary)["mobSlot"])


## Where a creature may stand: far enough from the player, and not on top of
## anything already there.
##
## "Anything" is three things and not one: what the caller says is in the way —
## props, and creatures that are dead but still fading — every creature *every*
## zone of this map is managing, and every place held for one that is not built
## yet. A zone that only looked at its own would stand its creatures inside the
## next zone's.
static func _eligible(
	state: Dictionary,
	zone: Dictionary,
	player_x: float,
	player_y: float,
	occupied: Array
) -> Array:
	var separation := roundf(PlatformerMaps.TILE_PX * SEPARATION_TILES)
	var player_distance := roundf(PlatformerMaps.TILE_PX * PLAYER_DISTANCE_TILES)
	var taken: Array = []
	for entry: Variant in occupied:
		var point: Dictionary = entry
		taken.append({"x": float(point["x"]), "y": float(point["y"]), "zoneId": "", "column": -1, "deckId": "", "moved": true})
	for entry: Variant in (state["zones"] as Array):
		var other_zone: Dictionary = entry
		for group: Variant in [other_zone["alive"], other_zone["reservations"]]:
			for standing: Variant in (group as Array):
				var place: Dictionary = standing
				taken.append(
					{
						"x": float(place["x"]),
						"y": float(place["y"]),
						"zoneId": String(other_zone["zoneId"]),
						"column": int(place["column"]),
						"deckId": String(place.get("deckId", "")),
						"moved": bool(place.get("moved", false)),
					}
				)
	var made: Array = []
	for entry: Variant in (zone["candidates"] as Array):
		var candidate: Dictionary = entry
		if _squared(candidate, player_x, player_y) < player_distance * player_distance:
			continue
		var blocked := false
		for other: Variant in taken:
			var place: Dictionary = other
			# The place a creature stood up in is forgotten the moment it moves.
			# `update_positions` clears the mark, so the place-is-taken rule only
			# ever fires for one that has not been positioned yet — which is to say,
			# for a reservation made earlier in this same frame. The footing is the
			# pair: a column and the storey it stands on, because the ground under a
			# deck and the deck over it are two places.
			if (
				not bool(place["moved"])
				and String(place["zoneId"]) == String(zone["zoneId"])
				and int(place["column"]) == int(candidate["column"])
				and String(place["deckId"]) == String(candidate["deckId"])
			):
				blocked = true
				break
			if _squared(candidate, float(place["x"]), float(place["y"])) < separation * separation:
				blocked = true
				break
		if not blocked:
			made.append(candidate)
	return made


## Which of them. A group already standing usually pulls the next one towards
## it, which is what makes a route feel hunted rather than sprinkled.
static func _choose(zone: Dictionary, eligible: Array, rng: KernelRng) -> Dictionary:
	# The creatures standing *and* the places held for ones not built yet: a
	# reservation made a moment ago is as much a group to join as a body.
	var standing: Array = []
	for group: Variant in [zone["alive"], zone["reservations"]]:
		for entry: Variant in (group as Array):
			standing.append(entry)
	if not standing.is_empty() and rng.next() < CLUSTER_JOIN_CHANCE:
		var nucleus: Dictionary = standing[int(rng.next() * float(standing.size()))]
		var radius := roundf(PlatformerMaps.TILE_PX * CLUSTER_RADIUS_TILES)
		var near: Array = []
		for entry: Variant in eligible:
			var candidate: Dictionary = entry
			if _squared(candidate, float(nucleus["x"]), float(nucleus["y"])) <= radius * radius:
				near.append(candidate)
		if not near.is_empty():
			return near[int(rng.next() * float(near.size()))]
	return eligible[int(rng.next() * float(eligible.size()))]


static func _squared(candidate: Dictionary, x: float, y: float) -> float:
	var dx := float(candidate["x"]) - x
	var dy := float(candidate["y"]) - y
	return dx * dx + dy * dy


## The zone's own generator seed: the run's revision folded through the map and
## zone names and the map's authored salt, so two zones of one map draw
## differently and one zone draws the same on every run of the package.
static func _zone_seed(revision: int, map_id: String, zone_id: String, salt: int) -> int:
	var mixed := revision & KernelHash.MASK
	mixed = (mixed ^ KernelHash.fnv1a32(map_id)) & KernelHash.MASK
	mixed = KernelHash.imul(mixed ^ (mixed >> 16), 0x45D9F3B)
	mixed = (mixed ^ KernelHash.fnv1a32(zone_id)) & KernelHash.MASK
	mixed = KernelHash.imul(mixed ^ (mixed >> 16), 0x45D9F3B)
	mixed = (mixed ^ (salt & KernelHash.MASK)) & KernelHash.MASK
	mixed = (mixed ^ (mixed >> 16)) & KernelHash.MASK
	return ZERO_SEED_SUBSTITUTE if mixed == 0 else mixed


## The authored population block for one map, or an empty dictionary.
static func _map_block(package: Dictionary, map_id: String) -> Dictionary:
	var population: Dictionary = package["mobPopulation"]
	for entry: Variant in (population.get("maps", []) as Array):
		var map: Dictionary = entry
		if String(map.get("map_id", "")) == map_id:
			var made := map.duplicate()
			made["update_interval_ms"] = population.get("update_interval_ms", 250)
			made["max_spawn_batch_per_update"] = population.get("max_spawn_batch_per_update", 1)
			return made
	return {}


## The director works in kebab-case ids; a package may author either.
static func _kebab(source_id: String) -> String:
	return source_id.replace("_", "-")


## Where every creature it is managing now stands.
##
## Told rather than remembered, and told *before* it decides: a director that
## placed against the positions creatures stood up in would keep putting new ones
## on top of a group that has since walked away, and the clustered placement
## would cluster around a memory.
static func update_positions(state: Dictionary, mobs: Array) -> void:
	if state.is_empty():
		return
	var standing := {}
	for entry: Variant in mobs:
		var mob: Dictionary = entry
		if not bool(mob["alive"]):
			continue
		standing[
			"%s/%d" % [String(mob.get("zoneId", "")), int(mob.get("spawnColumn", -1))]
		] = mob
	for entry: Variant in (state["zones"] as Array):
		var zone: Dictionary = entry
		for other: Variant in (zone["alive"] as Array):
			var place: Dictionary = other
			var key := "%s/%d" % [String(zone["zoneId"]), int(place["column"])]
			if not standing.has(key):
				continue
			var mob: Dictionary = standing[key]
			place["x"] = float(mob["x"])
			place["y"] = float(mob["y"])
			place["moved"] = true


## A creature the route has lost. Frees the place it stood and owes another one,
## due when the zone's own delay has run.
##
## The director is told rather than asked, because only the caller knows a
## creature died: a population that polled for corpses would replace one the
## moment it stopped moving rather than the moment it was gone.
static func record_death(state: Dictionary, zone_id: String, column: int, now_ms: float) -> void:
	if state.is_empty():
		return
	for entry: Variant in (state["zones"] as Array):
		var zone: Dictionary = entry
		if String(zone["zoneId"]) != zone_id:
			continue
		var standing: Array = []
		var removed := false
		for other: Variant in (zone["alive"] as Array):
			if not removed and int((other as Dictionary)["column"]) == column:
				removed = true
				continue
			standing.append(other)
		if not removed:
			return
		zone["alive"] = standing
		(zone["tickets"] as Array).append(
			{
				"dueAtMs": now_ms + float(zone["respawnDelayMs"]),
				"sequence": _next_sequence(state),
				"attemptCount": 0,
			}
		)
		return
