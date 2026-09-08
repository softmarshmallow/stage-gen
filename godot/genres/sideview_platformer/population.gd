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
	var tile := PlatformerMaps.TILE_PX
	var wander := roundi(tile * WANDER_RADIUS_TILES)

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
		var candidates: Array = []
		for column in range(left, right):
			if heights[column] <= 0:
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
				"spawnTable": zone.get("spawn_table", []),
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
		"updateIntervalMs": float(authored.get("update_interval_ms", 250)),
		"maxBatch": int(authored.get("max_spawn_batch_per_update", 1)),
		"lastUpdateAtMs": -1.0,
	}


## One director tick. Returns the reservations it issued, each `{zoneId,
## mobSlot, column, x, y}`, and nothing when the interval has not elapsed.
static func update(state: Dictionary, now_ms: float, player_x: float, player_y: float) -> Array:
	if state.is_empty():
		return []
	var last := float(state["lastUpdateAtMs"])
	if last >= 0.0 and now_ms - last < float(state["updateIntervalMs"]):
		return []
	state["lastUpdateAtMs"] = now_ms

	var issued: Array = []
	var capacity := int(state["maxBatch"])
	for entry: Variant in (state["zones"] as Array):
		var zone: Dictionary = entry
		var tickets: Array = zone["tickets"]
		if not bool(zone["initialized"]):
			zone["initialized"] = true
			for _i in range(int(zone["initialPopulation"])):
				tickets.append(now_ms)
		else:
			# A zone below its headcount with nothing already owed asks for the
			# difference now. A death has already put its own ticket in, due
			# when the route is meant to feel dangerous again.
			var owed := (
				int(zone["targetPopulation"]) - (zone["alive"] as Array).size() - tickets.size()
			)
			for _i in range(owed):
				tickets.append(now_ms)
		var wanted := 0
		for due: Variant in tickets:
			if float(due) <= now_ms:
				wanted += 1
		while wanted > 0 and capacity > 0:
			if (zone["alive"] as Array).size() >= int(zone["populationCap"]):
				break
			var made := _reserve(zone, player_x, player_y)
			if made.is_empty():
				break
			issued.append(made)
			(zone["alive"] as Array).append(made)
			_spend_ticket(tickets, now_ms)
			wanted -= 1
			capacity -= 1
	return issued


## One creature: which kind, then where. Two to four draws, always in that order.
static func _reserve(zone: Dictionary, player_x: float, player_y: float) -> Dictionary:
	var rng: KernelRng = zone["rng"]
	var slot := _select_slot(zone, rng)
	if slot < 0:
		return {}
	var eligible := _eligible(zone, player_x, player_y)
	if eligible.is_empty():
		return {}
	var chosen := _choose(zone, eligible, rng)
	return {
		"zoneId": zone["zoneId"],
		"mobSlot": slot,
		"column": chosen["column"],
		"x": chosen["x"],
		"y": chosen["y"],
	}


## Which creature, by weight. A single-entry table still draws, because the draw
## is the contract even when its answer is not in doubt.
static func _select_slot(zone: Dictionary, rng: KernelRng) -> int:
	var table: Array = zone["spawnTable"]
	if table.is_empty():
		return -1
	var total := 0.0
	for entry: Variant in table:
		total += float((entry as Dictionary).get("weight", 0))
	var selection := rng.next() * total
	for index in range(table.size()):
		selection -= float((table[index] as Dictionary).get("weight", 0))
		if selection < 0.0:
			return index
	return table.size() - 1


## Where a creature may stand: far enough from the player, and not on top of
## something already standing.
static func _eligible(zone: Dictionary, player_x: float, player_y: float) -> Array:
	var separation := roundf(PlatformerMaps.TILE_PX * SEPARATION_TILES)
	var player_distance := roundf(PlatformerMaps.TILE_PX * PLAYER_DISTANCE_TILES)
	var made: Array = []
	for entry: Variant in (zone["candidates"] as Array):
		var candidate: Dictionary = entry
		if _squared(candidate, player_x, player_y) < player_distance * player_distance:
			continue
		var blocked := false
		for other: Variant in (zone["alive"] as Array):
			var standing: Dictionary = other
			if int(standing["column"]) == int(candidate["column"]):
				blocked = true
				break
			if _squared(candidate, float(standing["x"]), float(standing["y"])) < separation * separation:
				blocked = true
				break
		if not blocked:
			made.append(candidate)
	return made


## Which of them. A group already standing usually pulls the next one towards
## it, which is what makes a route feel hunted rather than sprinkled.
static func _choose(zone: Dictionary, eligible: Array, rng: KernelRng) -> Dictionary:
	var standing: Array = zone["alive"]
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
		(zone["tickets"] as Array).append(now_ms + float(zone["respawnDelayMs"]))
		return


## Take the oldest ticket that is due, which is the one that has waited longest.
static func _spend_ticket(tickets: Array, now_ms: float) -> void:
	var oldest := -1
	for index in range(tickets.size()):
		if float(tickets[index]) > now_ms:
			continue
		if oldest < 0 or float(tickets[index]) < float(tickets[oldest]):
			oldest = index
	if oldest >= 0:
		tickets.remove_at(oldest)
