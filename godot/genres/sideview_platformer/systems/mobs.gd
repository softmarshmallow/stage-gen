class_name PlatformerMobsSystem
extends RefCounted

## The creatures on the route: how many stand up, and what each does per frame.
##
## Two systems in the browser's roster and two here. `mobs/population` asks the
## director whether anything is owed and stands up whatever it says; `mobs/step`
## moves what is standing. They are separate because the director reads where
## every creature *is* before deciding where the next one may go, and a step
## folded into the same system would have it reading half-moved bodies.
##
## The health a creature carries is its rank's, and its temperament is the
## package's word or its rank's default. Both are the scene's table rather than
## the package's, which is the same division the population policy keeps: the
## package names species and populations, and what those words are worth is the
## consumer's.

## What a rank is worth, in health.
const HEALTH_BY_RANK := {"boss": 12, "elite": 6, "uncommon": 3}
const DEFAULT_HEALTH := 2

## What a rank means when a package names no temperament.
const AGGRESSION_BY_RANK := {
	"boss": "relentless", "elite": "hunting", "uncommon": "territorial"
}
const DEFAULT_AGGRESSION := "passive"

## How far past its own reach a creature's committed blow still connects. A body
## running through a swing is given the margin rather than dodging on a pixel.
const STRIKE_RANGE_MARGIN := 1.35


static func population_declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "mobs/population",
			"contract_version": "mob-population-system-v1",
			"reads": ["hold", "player", "camera"],
			"writes": ["mobs"],
			"emits": ["mob-spawned"],
		}
	)


static func step_declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "mobs/step",
			"contract_version": "mob-step-system-v1",
			"reads": ["hold"],
			"writes": ["mobs"],
		}
	)


## Stand up whatever the director says is owed.
static func populate(world: PlatformerWorld, step: Dictionary) -> void:
	if world.hold or world.population.is_empty():
		return
	PlatformerPopulation.update_positions(world.population, world.mobs)
	var issued := PlatformerPopulation.update(
		world.population,
		# Whole milliseconds, which is the clock the director's intervals are
		# measured against.
		float(int(float(step["now"]))),
		float(world.player["x"]),
		float(world.player["y"])
	)
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	for entry: Variant in issued:
		var reservation: Dictionary = entry
		var spec := _spec(world, int(reservation["mobSlot"]))
		if spec.is_empty():
			continue
		var instance := world.next_mob_instance
		world.next_mob_instance += 1
		var instance_id := "%s/mob/%d" % [world.map_id, instance]
		var zone_id := String(reservation["zoneId"])
		world.mobs.append(
			PlatformerMob.create(
				instance,
				"mob_%d" % instance,
				instance_id,
				_slot_of(world, String(spec.get("mob_id", ""))),
				_aggression(spec),
				_health(spec),
				float(reservation["x"]),
				float(reservation["y"]),
				map
			)
		)
		# The place it came from and the column it stands in, so the director can
		# be told when it is gone.
		(world.mobs[world.mobs.size() - 1] as Dictionary)["zoneId"] = zone_id
		(world.mobs[world.mobs.size() - 1] as Dictionary)["spawnColumn"] = int(reservation["column"])
		PlatformerTranscript.record(
			world,
			"mob-spawned",
			int(step["frame"]),
			float(step["now"]),
			{"instanceId": instance_id, "column": int(reservation["column"])}
		)


## Move everything standing.
static func step(world: PlatformerWorld, frame_step: Dictionary) -> void:
	if world.hold:
		return
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	var dt := world.simulation_dt / 1000.0
	# Every creature is told where the body is before any of them moves, which is
	# what the browser's `observePlayer` pass does — a creature that read a
	# half-moved roster would hunt a player nobody else could see.
	var player := {"x": float(world.player["x"]), "y": float(world.player["y"])}
	var standing: Array = []
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		PlatformerMob.step(mob, map, dt, player, float(frame_step["now"]))
		if not PlatformerMob.faded(mob, float(frame_step["now"])):
			standing.append(mob)
	world.mobs = standing


## The blows the creatures landed on the body this frame.
##
## Resolved after they have moved, and re-checked for range: a creature commits
## to its swing when it starts, so backing out of reach dodges the damage even
## though the animation played out. Distance is measured with a third again of
## the profile's reach, which is the margin a body running past a swing is given.
static func strike(world: PlatformerWorld, step: Dictionary) -> void:
	if world.hold or not bool(world.package["combatEnabled"]):
		return
	var combat: Dictionary = world.package["combat"]
	if not bool(combat.get("contact_damage", false)):
		return
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		if not bool(mob["alive"]):
			continue
		var pending := PlatformerMob.consume_strike(mob)
		if pending.is_empty() or float(pending["damage"]) <= 0.0:
			continue
		var profile := PlatformerCombat.profile(String(mob["aggression"]))
		if (
			absf(float(mob["x"]) - float(world.player["x"]))
			> float(profile["strikeRangePx"]) * STRIKE_RANGE_MARGIN
		):
			continue
		if (
			absf(float(mob["y"]) - float(world.player["y"]))
			> PlatformerMaps.TILE_PX * PlatformerMob.VERTICAL_REACH_TILES
		):
			continue
		world.blow_sequence += 1
		var seed_value := PlatformerCombat.blow_seed(
			world.blow_sequence, float(mob["x"]), int(mob["ladderIndex"])
		)
		var blow := PlatformerCombat.critical_damage(
			float(pending["damage"]), String(combat.get("critical_profile", "none")), seed_value
		)
		if not PlatformerPlayer.take_damage(
			world.player, float(blow["amount"]), float(step["now"])
		):
			continue
		PlatformerPlayer.knock_back(world.player, int(pending["dirSign"]), float(step["now"]))
		world.blows.append(
			{
				"amount": int(blow["amount"]),
				"critical": bool(blow["critical"]),
				"incoming": true,
				"x": float(world.player["x"]),
				"y": float(world.player["y"]),
			}
		)
		PlatformerTranscript.record(
			world,
			"player-damaged",
			int(step["frame"]),
			float(step["now"]),
			{
				"applied": int(blow["amount"]),
				"hp": int(world.player["hp"]),
				"critical": bool(blow["critical"]),
			}
		)


## The published list, in the order the creatures stood up.
static func snapshots(world: PlatformerWorld) -> Array:
	var made: Array = []
	for entry: Variant in world.mobs:
		made.append(PlatformerMob.snapshot(entry as Dictionary))
	return made


## The catalogue entry a population slot names.
##
## The director's slots are the zone's own spawn table, sorted by mob id; the
## catalogue's are the order the package published them. They are not the same
## numbering and one is translated into the other here rather than assumed equal.
static func _spec(world: PlatformerWorld, mob_slot: int) -> Dictionary:
	var ids := _population_ids(world)
	if mob_slot < 0 or mob_slot >= ids.size():
		return {}
	var mob_id := ids[mob_slot]
	for entry: Variant in (world.package["mobs"] as Array):
		var spec: Dictionary = entry
		if String(spec.get("mob_id", "")) == mob_id:
			return spec
	return {}


## Every mob id this map's zones can spawn, sorted, which is the director's slot
## order.
static func _population_ids(world: PlatformerWorld) -> PackedStringArray:
	var seen := {}
	for entry: Variant in (world.population.get("zones", []) as Array):
		var zone: Dictionary = entry
		for row: Variant in (zone["spawnTable"] as Array):
			seen[String((row as Dictionary).get("mob_id", ""))] = true
	var made := PackedStringArray()
	for key: Variant in seen:
		made.append(String(key))
	made.sort()
	return made


## Where a creature sits in the package's own catalogue, which is the index the
## golden publishes as `ladderIndex`.
static func _slot_of(world: PlatformerWorld, mob_id: String) -> int:
	var catalogue: Array = world.package["mobs"]
	for index in range(catalogue.size()):
		if String((catalogue[index] as Dictionary).get("mob_id", "")) == mob_id:
			return index
	return -1


static func _health(spec: Dictionary) -> int:
	return int(HEALTH_BY_RANK.get(_rank(spec), DEFAULT_HEALTH))


## The temperament a package named, or the one its rank implies.
##
## `str` rather than `String` throughout: a package may publish `aggression` as
## null rather than omitting it, and `String(null)` is not a cast in GDScript —
## it is a constructor that does not exist, and it takes the whole run down at
## the first creature. A rank read the same way for the same reason.
static func _aggression(spec: Dictionary) -> String:
	var authored: Variant = spec.get("aggression")
	if authored is String and PlatformerCombat.PROFILES.has(authored):
		return authored
	return str(AGGRESSION_BY_RANK.get(_rank(spec), DEFAULT_AGGRESSION))


static func _rank(spec: Dictionary) -> String:
	var named: Variant = spec.get("rank")
	return named if named is String else ""
