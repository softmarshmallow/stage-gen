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
## The health a creature carries is its rank's, at the package's number scale, and
## its temperament is the package's word or its rank's default. Both are the scene's table rather than
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
		float(world.player["y"]),
		_occupied(world)
	)
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	for entry: Variant in issued:
		var reservation: Dictionary = entry
		var spec := _spec(world, int(reservation["mobSlot"]))
		if spec.is_empty():
			# The place is given back rather than kept: a reservation the caller
			# could not build into a body would otherwise hold that column for the
			# rest of the run and cost the route a creature.
			PlatformerPopulation.reject(
				world.population, String(reservation["reservationId"]), float(step["now"])
			)
			continue
		var instance := world.next_mob_instance
		world.next_mob_instance += 1
		var bot_id := "mob_%d" % world.next_mob_bot_id
		world.next_mob_bot_id += 1
		var instance_id := "%s/mob/%d" % [world.map_id, instance]
		var zone_id := String(reservation["zoneId"])
		world.mobs.append(
			PlatformerMob.create(
				instance,
				bot_id,
				instance_id,
				slot_of(world, String(spec.get("mob_id", ""))),
				aggression_of(spec),
				health_of(spec, PlatformerNumberScale.profile_of(world.package["combat"])),
				float(reservation["x"]),
				float(reservation["y"]),
				map,
				# The storey the director stood it up on. Passed through rather
				# than re-derived: the reservation is the only record of which of
				# the several places over one column was taken.
				str(reservation.get("deckId", ""))
			)
		)
		# The place it came from and the column it stands in, so the director can
		# be told when it is gone.
		(world.mobs[world.mobs.size() - 1] as Dictionary)["zoneId"] = zone_id
		(world.mobs[world.mobs.size() - 1] as Dictionary)["spawnColumn"] = int(reservation["column"])
		# And the held place becomes a creature, which is the only thing that moves
		# it out of the director's reservations and into its roster.
		PlatformerPopulation.confirm(
			world.population, String(reservation["reservationId"]), instance_id
		)
		PlatformerTranscript.record(
			world,
			"mob-spawned",
			int(step["frame"]),
			float(step["now"]),
			{"instanceId": instance_id, "column": int(reservation["column"])}
		)


## What else is in the way that the director does not manage.
##
## The creatures that are dead but still fading, which stand where they fell
## until they are gone: a route that spawned inside a corpse would put a new
## creature on top of the one the player just killed.
static func _occupied(world: PlatformerWorld) -> Array:
	var made: Array = []
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		if bool(mob["alive"]):
			continue
		made.append({"x": float(mob["x"]), "y": float(mob["y"])})
	return made


## Move everything standing.
static func step(world: PlatformerWorld, frame_step: Dictionary) -> void:
	if world.hold:
		return
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	var dt := world.simulation_dt / 1000.0
	var standing: Array = []
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		PlatformerMob.step(mob, map, dt, mob["observed"], float(frame_step["now"]))
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
	if world.hold:
		return
	var combat: Dictionary = world.package["combat"]
	var defeated := bool(world.player["defeated"])
	# A package with no combat, or with combat but no contact damage, still tells
	# its creatures where the body is *not*: an empty observation is the browser's
	# `observePlayer(null, null, …)`, and it is what makes them wander past a
	# player they cannot hurt.
	if not bool(world.package["combatEnabled"]) or not bool(combat.get("contact_damage", false)):
		for entry: Variant in world.mobs:
			(entry as Dictionary)["observed"] = {}
		return
	var seen := {
		"x": float(world.player["x"]), "y": float(world.player["y"]), "defeated": defeated
	}
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		if not bool(mob["alive"]):
			continue
		mob["observed"] = seen
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
				"died": bool(world.player["defeated"]),
				"dirSign": int(pending["dirSign"]),
				"seed": seed_value,
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
	# The slot is the *map's*, not a position in the zone that issued it: the
	# director numbers every kind any zone of the map can spawn, sorted once, so
	# two zones that both send moths name the same number. Rebuilding the table
	# out of one zone's own rows gave a second zone a different numbering for the
	# same creature.
	var ids: PackedStringArray = world.population.get("mobIdBySlot", PackedStringArray())
	if mob_slot < 0 or mob_slot >= ids.size():
		return {}
	var mob_id := ids[mob_slot]
	for entry: Variant in (world.package["mobs"] as Array):
		var spec: Dictionary = entry
		if String(spec.get("mob_id", "")) == mob_id:
			return spec
	return {}


## Where a creature sits in the package's own catalogue, which is the index the
## golden publishes as `ladderIndex`.
static func slot_of(world: PlatformerWorld, mob_id: String) -> int:
	var catalogue: Array = world.package["mobs"]
	for index in range(catalogue.size()):
		if String((catalogue[index] as Dictionary).get("mob_id", "")) == mob_id:
			return index
	return -1


static func health_of(spec: Dictionary, scale: Dictionary = {}) -> int:
	var base := int(HEALTH_BY_RANK.get(_rank(spec), DEFAULT_HEALTH))
	if scale.is_empty():
		return base
	return PlatformerNumberScale.mob_health(base, scale)


## The temperament a package named, or the one its rank implies.
##
## `str` rather than `String` throughout: a package may publish `aggression` as
## null rather than omitting it, and `String(null)` is not a cast in GDScript —
## it is a constructor that does not exist, and it takes the whole run down at
## the first creature. A rank read the same way for the same reason.
static func aggression_of(spec: Dictionary) -> String:
	var authored: Variant = spec.get("aggression")
	if authored is String and PlatformerCombat.PROFILES.has(authored):
		return authored
	return str(AGGRESSION_BY_RANK.get(_rank(spec), DEFAULT_AGGRESSION))


static func _rank(spec: Dictionary) -> String:
	var named: Variant = spec.get("rank")
	return named if named is String else ""
