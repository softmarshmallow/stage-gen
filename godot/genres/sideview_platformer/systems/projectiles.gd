class_name PlatformerProjectilesSystem
extends RefCounted

## The rounds in the air, stepped and paid out.
##
## Runs after the creatures have moved this frame and before drops are
## collected, so a kill lands in the same frame's loot pass rather than a frame
## later. The pool never holds a creature: it is handed this frame's boxes and
## returns indices into them, which is what keeps combat resolving against
## geometry rather than against object identity.

## How long a blow stops the frame.
const HITSTOP_MS := 40.0
const KILL_HITSTOP_MS := 70.0


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "projectiles/step",
			"contract_version": "projectile-system-v1",
			"reads": ["hold", "mobs"],
			"owns": ["projectiles"],
			"emits": ["mob-defeated"],
		}
	)


## Put a round in the air, on the frame the weapon releases one.
##
## The round is spent only once one is actually in the air — the inverse of
## drinking, where the bag opens only if the heal connected.
static func throw_one(world: PlatformerWorld, step: Dictionary) -> void:
	if world.hold:
		return
	var weapon := PlatformerWeapon.profile(world.weapon_class)
	var tick := PlatformerWeapon.next_hit_tick(
		weapon,
		{
			"attackActive": bool(world.player["attackActive"]),
			"attackStarted": float(world.player["attackStarted"]),
		},
		float(step["now"]),
		int(world.player["attackTicksFired"])
	)
	if tick < 0:
		return
	world.player["attackTicksFired"] = tick + 1
	var direction := -1 if String(world.player["facing"]) == PlatformerPlayer.FACING_LEFT else 1
	if String(weapon["delivery"]) == "instant":
		_swing(world, step, weapon, direction)
		return
	var shot := PlatformerProjectiles.launch(
		world.projectiles,
		world.next_shot_id,
		float(world.player["x"]),
		float(world.player["y"]),
		direction
	)
	if shot.is_empty():
		return
	world.next_shot_id += 1
	PlatformerTranscript.record(
		world,
		"projectile-thrown",
		int(step["frame"]),
		float(step["now"]),
		{"x": int(round(float(world.player["x"]))), "dirSign": direction}
	)


## Everything one landed blow is worth: the critical it rolls, the hold it puts
## on the frame, and — if it killed — the record, the loot, the place it frees,
## the experience it banks and the tremor it puts in the view.
##
## Shared by the swing and the throw, because the two differ only in how the
## blow reached the creature. `seed_x` is where the blow came from: the hand for
## a swing, the point of release for a throw.
static func _pay_out(
	world: PlatformerWorld,
	step: Dictionary,
	weapon: Dictionary,
	mob: Dictionary,
	seed_x: float,
	direction: int
) -> Dictionary:
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	world.blow_sequence += 1
	var seed_value := PlatformerCombat.blow_seed(
		world.blow_sequence, seed_x, int(mob["ladderIndex"])
	)
	var struck := PlatformerCombat.critical_damage(
		float(weapon["damage"]),
		PlatformerProgression.named(world.package["combat"], "critical_profile", "none"),
		seed_value
	)
	var blow := PlatformerMob.take_hit(
		mob, map, float(struck["amount"]), direction, float(step["now"])
	)
	# The hold a blow puts on the frame: forty milliseconds, seventy on a kill,
	# and extended rather than restarted — three blows in one frame hold once,
	# and the longest of them wins, so a combo's kill is never shortened by the
	# blows before it.
	world.impact = {
		"disposed": false,
		"enabled": true,
		"hitstopUntilMs": maxf(
			float(world.impact["hitstopUntilMs"]),
			float(step["now"]) + _hold_for(bool(blow["died"]), bool(struck["critical"]))
		),
		"reducedMotion": false,
	}
	world.blows.append(
		{
			"amount": int(struck["amount"]),
			"critical": bool(struck["critical"]),
			"incoming": false,
			"x": float(mob["x"]),
			"y": float(mob["y"]),
		}
	)
	if not bool(blow["died"]):
		return {"blow": blow, "struck": struck, "seed": seed_value}
	PlatformerTranscript.record(
		world,
		"mob-defeated",
		int(step["frame"]),
		float(step["now"]),
		{"ladderIndex": int(mob["ladderIndex"]), "x": int(round(float(mob["x"])))}
	)
	PlatformerItemsSystem.drop_loot(world, mob, direction)
	# The director forgets a creature the moment it dies, and the world says so:
	# an instance id is the director's name for something it is still managing.
	mob["instanceId"] = null
	PlatformerPopulation.record_death(
		world.population,
		str(mob.get("zoneId", "")),
		int(mob.get("spawnColumn", -1)),
		float(step["now"])
	)
	_award(world, mob)
	world.shakes.append(
		{
			"seed": seed_value,
			"startedMs": float(step["now"]),
			"dirSign": direction,
			"scale": FamilyShake.CRITICAL_SCALE if bool(struck["critical"]) else 1.0,
		}
	)
	return {"blow": blow, "struck": struck, "seed": seed_value}


## How long one blow holds the frame. A critical holds a quarter longer, which
## is what makes a big number feel like one.
static func _hold_for(died: bool, critical: bool) -> float:
	var base := KILL_HITSTOP_MS if died else HITSTOP_MS
	return round(base * (1.25 if critical else 1.0))


## Bank what this kill was worth, and grow the pool if it bought a rank.
static func _award(world: PlatformerWorld, mob: Dictionary) -> void:
	var catalogue: Array = world.package["mobs"]
	var index := int(mob["ladderIndex"])
	if index < 0 or index >= catalogue.size():
		return
	var rank := String((catalogue[index] as Dictionary).get("rank", ""))
	var granted := PlatformerProgression.grant(
		world.progression,
		PlatformerProgression.award_for_rank(rank),
		world.package["progression"],
		int(world.package["startingHealth"])
	)
	if int(granted["awarded"]) <= 0:
		return
	world.progression = granted["state"]
	if int(granted["levelsGained"]) <= 0:
		return
	world.player["maxHp"] = int(world.progression["maximumHealth"])


## The shape the package's round is drawn as, which decides how it carries
## itself in the air.
static func _silhouette(world: PlatformerWorld) -> String:
	var wanted := PlatformerProgression.named(world.package["combat"], "projectile_id", "")
	for entry: Variant in (world.package["projectiles"] as Array):
		var spec: Dictionary = entry
		if PlatformerProgression.named(spec, "projectile_id", "") != wanted:
			continue
		return PlatformerProgression.named(
			spec, "silhouette", PlatformerProjectiles.DEFAULT_ORIENTATION
		)
	return PlatformerProjectiles.DEFAULT_ORIENTATION


## One blow of a swing, resolved against every creature standing in the band.
##
## Re-resolved on every blow of an action rather than once per action, so a
## creature killed by the second frees its slot for the third, and one that
## wandered into the band mid-swing is struck by the blows that remain.
static func _swing(
	world: PlatformerWorld, step: Dictionary, weapon: Dictionary, direction: int
) -> void:
	var living: Array = []
	var boxes: Array = []
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		if not bool(mob["alive"]):
			continue
		living.append(mob)
		boxes.append({"x": float(mob["x"]), "footY": float(mob["y"])})
	for index: Variant in PlatformerWeapon.instant_targets(
		weapon,
		float(world.player["x"]),
		float(world.player["y"]),
		direction,
		boxes
	):
		_pay_out(world, step, weapon, living[int(index)], float(world.player["x"]), direction)


## Step every round and pay out what it hit.
static func update(world: PlatformerWorld, step: Dictionary) -> void:
	if world.hold or world.projectiles.is_empty():
		return
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	var living: Array = []
	var boxes: Array = []
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		if not bool(mob["alive"]):
			continue
		living.append(mob)
		boxes.append(PlatformerMob.bounds(mob))
	var hits := PlatformerProjectiles.update(
		world.projectiles,
		boxes,
		world.simulation_dt,
		{
			"minX": 0.0,
			"maxX": float(map["worldWidthPx"]),
			"surfaceAt": func(x: float) -> float: return PlatformerMaps.surface_at_x(map, x),
		},
		_silhouette(world)
	)
	var weapon := PlatformerWeapon.profile(world.weapon_class)
	for entry: Variant in hits:
		var hit: Dictionary = entry
		var index := int(hit["targetIndex"])
		if index < 0 or index >= living.size():
			continue
		var mob: Dictionary = living[index]
		if not bool(mob["alive"]):
			continue
		_pay_out(world, step, weapon, mob, float(hit["spawnX"]), int(hit["dirSign"]))