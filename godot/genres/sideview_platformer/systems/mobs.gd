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
	var dt := float(frame_step["dt"]) / 1000.0
	for entry: Variant in world.mobs:
		PlatformerMob.wander(entry as Dictionary, map, dt)


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
	return int(HEALTH_BY_RANK.get(String(spec.get("rank", "")), DEFAULT_HEALTH))


static func _aggression(spec: Dictionary) -> String:
	var authored := String(spec.get("aggression", ""))
	if PlatformerCombat.PROFILES.has(authored):
		return authored
	return String(AGGRESSION_BY_RANK.get(String(spec.get("rank", "")), DEFAULT_AGGRESSION))
