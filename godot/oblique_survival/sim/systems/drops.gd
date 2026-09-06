class_name SysDrops
extends RefCounted

## Reads `collision`, `entities`, `clock`; writes `items`.
## viewer/index.html 847-875 (spawnDrops, pickUp) and 1228-1293 (the system).

## Cartoon gravity for a dropped item, m/s^2 (deliberately not 9.8).
const DROP_GRAVITY := 26.0
## Bounce coefficient on a hard landing.
const DROP_RESTITUTION := 0.28
## The g used for sliding deceleration = friction * SLIDE_GRAVITY.
const SLIDE_GRAVITY := 9.81
## Speed, m/s, below which a sliding drop settles.
const DROP_SETTLE_SPEED := 0.06
## Magnet pickup reach, m (gameplay.pickup == "magnet" only).
const PICKUP_RADIUS := 1.0
## Magnet draw speed, m/s.
const PICKUP_SPEED := 7.0


static func update(world: World, dt: float) -> void:
	var player: PlayerState = world.player
	# Yields queued behind a falling trunk, released when the crown lands.
	var d := world.drops.size() - 1
	while d >= 0:
		var drop: Dictionary = world.drops[d]
		if world.time >= float(drop["at"]):
			world.drops.remove_at(d)
			spawn_drops(
				world, drop["yields"], float(drop["x"]), float(drop["z"]),
				float(drop["dir_x"]), float(drop["dir_z"]), float(drop["spread"])
			)
		d -= 1
	var pickup := str((world.manifest["gameplay"] as Dictionary).get("pickup", ""))
	if pickup == "":
		pickup = "manual"
	var i := world.entities.size() - 1
	while i >= 0:
		var item: Dictionary = world.entities[i]
		if item.get("kind", "") != "item":
			i -= 1
			continue
		item["age"] = float(item["age"]) + dt
		if not bool(item["settled"]):
			if not bool(item["grounded"]):
				item["vy"] = float(item["vy"]) - DROP_GRAVITY * dt
				item["x"] = float(item["x"]) + float(item["vx"]) * dt
				item["z"] = float(item["z"]) + float(item["vz"]) * dt
				item["y"] = float(item["y"]) + float(item["vy"]) * dt
				if float(item["y"]) <= 0.0:
					item["y"] = 0.0
					# A hard landing bounces once, short and damped; a soft
					# one is down for good and starts to slide.
					if float(item["vy"]) < -2.0:
						item["vy"] = float(item["vy"]) * -DROP_RESTITUTION
						item["vx"] = float(item["vx"]) * 0.55
						item["vz"] = float(item["vz"]) * 0.55
					else:
						item["vy"] = 0.0
						item["grounded"] = true
				i -= 1
				continue
			# On the ground: the surface decides how far it skids. Sliding
			# deceleration is the biome's friction times g, sampled under the
			# drop, so a stone runs on scree and stops dead in the bog.
			var vx := float(item["vx"])
			var vz := float(item["vz"])
			var speed := sqrt(vx * vx + vz * vz)
			var brake: float = float(world.friction_at.call(float(item["x"]), float(item["z"]))) * SLIDE_GRAVITY * dt
			if speed <= brake or speed <= DROP_SETTLE_SPEED:
				item["vx"] = 0.0
				item["vz"] = 0.0
				item["settled"] = true
				item["age"] = 0.0
			else:
				var scale := (speed - brake) / speed
				item["vx"] = vx * scale
				item["vz"] = vz * scale
				item["x"] = float(item["x"]) + float(item["vx"]) * dt
				item["z"] = float(item["z"]) + float(item["vz"]) * dt
			i -= 1
			continue
		# Settled. Under "manual" the drop waits for the player's key (the
		# interact system); under "magnet", after a beat, anything in reach
		# is drawn to the player.
		if pickup != "magnet":
			i -= 1
			continue
		if float(item["age"]) < 0.35:
			i -= 1
			continue
		var dx: float = player.x - float(item["x"])
		var dz: float = player.z - float(item["z"])
		var distance := sqrt(dx * dx + dz * dz)
		if bool(item.get("pulled", false)) or distance <= PICKUP_RADIUS:
			item["pulled"] = true
			if distance < 0.3:
				if pick_up(world, item):
					world.entities.remove_at(i)
				else:
					item["pulled"] = false
					item["age"] = 0.0
				i -= 1
				continue
			var step: float = minf(distance, PICKUP_SPEED * dt)
			item["x"] = float(item["x"]) + (dx / distance) * step
			item["z"] = float(item["z"]) + (dz / distance) * step
			item["y"] = maxf(0.0, float(item["y"]) + (0.5 - float(item["y"])) * minf(1.0, dt * 8.0))
		i -= 1


## A yield lands on the ground as pickups, scattered from (x, z) along a
## direction. Four PRNG draws per pickup, in this order: angle, speed, vy,
## seed -- a port must draw in the same order to keep a seed meaning the same
## thing. (maps/viewer-sim.md section 5.9 says three; index.html:659 draws a
## fourth for `vy`.)
static func spawn_drops(
	world: World, yields: Variant, x: float, z: float,
	dir_x: float, dir_z: float, spread: float, uses: Variant = null
) -> void:
	if yields == null:
		return
	for produced in (yields as Array):
		var block := produced as Dictionary
		var total := int(block.get("count", 0))
		if total == 0:
			total = 1
		for n in total:
			var angle: float = (float(world.rand.call()) - 0.5) * 1.6
			var c := cos(angle)
			var s := sin(angle)
			var ax := dir_x * c - dir_z * s
			var az := dir_x * s + dir_z * c
			var speed: float = 1.2 + float(world.rand.call()) * spread * 1.3
			var vy: float = 2.4 + float(world.rand.call()) * 1.0
			var seed_value := int(float(world.rand.call()) * 1e5)
			world.drop_count += 1
			world.entities.append({
				"id": "i%d" % world.drop_count, "kind": "item", "item_id": str(block["item_id"]),
				"x": x, "z": z, "y": 0.35, "vx": ax * speed, "vz": az * speed, "vy": vy,
				"settled": false, "grounded": false, "age": 0.0, "radius": 0.0,
				"seed": seed_value, "uses": uses, "taken": false, "pulled": false, "dirty": false,
			})


## Into the pack; true when it went, false when the pack is full and it stays.
static func pick_up(world: World, item: Dictionary) -> bool:
	var left := Inventory.inv_add(world, str(item["item_id"]), 1, item.get("uses", null))
	if left > 0:
		Helpers.say(world, "Hands full.")
		return false
	Helpers.emit(world, {
		"type": "pickup", "item": str(item["item_id"]), "x": world.player.x, "z": world.player.z,
	})
	return true
