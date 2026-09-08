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
	if String(weapon["delivery"]) != "projectile":
		return
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
		}
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
		var blow := PlatformerMob.take_hit(
			mob, map, float(weapon["damage"]), int(hit["dirSign"]), float(step["now"])
		)
		# The hold a blow puts on the frame: forty milliseconds, seventy on a
		# kill, and extended rather than restarted — three blows in one frame
		# hold once, and the longest of them wins, so a combo's kill is never
		# shortened by the blows before it.
		world.impact = {
			"disposed": false,
			"enabled": true,
			"hitstopUntilMs": maxf(
				float(world.impact["hitstopUntilMs"]),
				float(step["now"]) + (KILL_HITSTOP_MS if bool(blow["died"]) else HITSTOP_MS)
			),
			"reducedMotion": false,
		}
		if not bool(blow["died"]):
			continue
		PlatformerTranscript.record(
			world,
			"mob-defeated",
			int(step["frame"]),
			float(step["now"]),
			{"instanceId": mob["instanceId"]}
		)
