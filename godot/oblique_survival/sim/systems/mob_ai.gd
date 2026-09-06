class_name SysMobAi
extends RefCounted

## Reads `collision`, writes `mobs`. viewer/index.html 1367-1425.
##
## There is no mob health, no damage taken, no death and no respawn: mobs
## cannot be attacked and the player has no attack verb. Mobs do not collide
## with props (only the player does) and nothing pushes them apart.


static func update(world: World, dt: float) -> void:
	var gameplay: Dictionary = world.manifest["gameplay"]
	var rules: Dictionary = gameplay.get("mob", {})
	var player: PlayerState = world.player
	var attack_range := _rule(rules, "attack_range_meters", 1.0)
	var aggro := _rule(rules, "aggro_radius_meters", 6.0)
	var speed := _rule(rules, "speed_meters_per_second", 2.4)
	var wander := _rule(rules, "wander_radius_meters", 4.0)
	for mob in world.entities:
		# Compared as a Variant: `str()` here allocated a String for every
		# entity in the world just to reject it.
		if mob.get("kind", "") != "mob":
			continue
		mob["elapsed"] = float(mob["elapsed"]) + dt
		var states: Dictionary = _states(world, str(mob.get("actor_id", "")))
		if str(mob["state"]) == "attack":
			# The blow resolves at the end of the animation, not at its start.
			if float(mob["elapsed"]) < Targeting.state_duration(states.get("attack", null)):
				continue
			mob["state"] = "idle"
			mob["elapsed"] = 0.0
			var reach_dx: float = player.x - float(mob["x"])
			var reach_dz: float = player.z - float(mob["z"])
			var reach_distance := sqrt(reach_dx * reach_dx + reach_dz * reach_dz)
			if reach_distance <= attack_range + player.radius + float(mob["radius"]) \
					and player.invulnerable <= 0.0:
				player.health -= _rule(rules, "attack_damage", 10.0)
				player.invulnerable = 0.7
				# An attack interrupts a harvest.
				player.busy = null
				# Verbatim quirk: `states` here is the MOB's state block, so a
				# mob with no `hurt` strip (grub_hound) leaves the player's
				# state alone. index.html:1382.
				if states.has("hurt"):
					player.state = "hurt"
				player.elapsed = 0.0
				Helpers.emit(world, {"type": "hurt", "x": player.x, "z": player.z})
			continue
		mob["cooldown"] = maxf(0.0, float(mob["cooldown"]) - dt)
		var dx: float = player.x - float(mob["x"])
		var dz: float = player.z - float(mob["z"])
		var distance := sqrt(dx * dx + dz * dz)
		if distance == 0.0:
			distance = 1e-5
		if distance <= attack_range + player.radius + float(mob["radius"]) and float(mob["cooldown"]) <= 0.0:
			mob["state"] = "attack"
			mob["elapsed"] = 0.0
			mob["cooldown"] = _rule(rules, "attack_cooldown_seconds", 1.5)
			mob["vx"] = 0.0
			mob["vz"] = 0.0
			mob["facing"] = Targeting.facing_for(dx, dz, world.camera_yaw, str(mob["facing"]))
		elif distance < aggro:
			mob["vx"] = (dx / distance) * speed
			mob["vz"] = (dz / distance) * speed
			mob["state"] = "walk"
		else:
			# A Lissajous orbit of home, phased by the layout's per-mob seed.
			var t := world.time * 0.25 + float(mob["seed"])
			var wx: float = float(mob["home_x"]) + cos(t) * wander - float(mob["x"])
			var wz: float = float(mob["home_z"]) + sin(t * 0.8) * wander - float(mob["z"])
			var wd := sqrt(wx * wx + wz * wz)
			if wd == 0.0:
				wd = 1.0
			mob["vx"] = (wx / wd) * speed * 0.35
			mob["vz"] = (wz / wd) * speed * 0.35
			mob["state"] = "walk" if wd > 0.5 else "idle"
		var next_x: float = float(mob["x"]) + float(mob["vx"]) * dt
		var next_z: float = float(mob["z"]) + float(mob["vz"]) * dt
		if bool(world.is_land.call(next_x, next_z)):
			mob["x"] = next_x
			mob["z"] = next_z
		else:
			# Off the shore: turn around, and stand still this tick.
			mob["vx"] = -float(mob["vx"])
			mob["vz"] = -float(mob["vz"])
		mob["facing"] = Targeting.facing_for(float(mob["vx"]), float(mob["vz"]), world.camera_yaw, str(mob["facing"]))


static func _rule(rules: Dictionary, key: String, fallback: float) -> float:
	var authored := float(rules.get(key, 0.0))
	return authored if authored != 0.0 else fallback


static func _states(world: World, actor_id: String) -> Dictionary:
	var actors: Variant = world.manifest.get("actors", null)
	if actors == null:
		return {}
	var actor: Variant = (actors as Dictionary).get(actor_id, null)
	if actor == null:
		return {}
	var states: Variant = (actor as Dictionary).get("states", null)
	return (states as Dictionary) if states != null else {}
