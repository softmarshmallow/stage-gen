class_name SysVitals
extends RefCounted

## Writes `player_vitals`. viewer/index.html 1427-1467, verbatim.
##
## The cold (gameplay.warmth, scaled by the season): the night adds to it, a
## worn thing takes from it, a lit torch scales it, a warm stone holds it off,
## and a lit fire within its heat radius gives warmth back. At zero the cold
## takes health.


static func update(world: World, dt: float) -> void:
	var player: PlayerState = world.player
	var rules: Dictionary = world.manifest["gameplay"]
	var hunger: Dictionary = rules.get("hunger", {})
	var health: Dictionary = rules.get("health", {})
	player.invulnerable = maxf(0.0, player.invulnerable - dt)
	var hunger_drain := float(hunger.get("drain_per_second", 0.0))
	if hunger_drain == 0.0:
		hunger_drain = 0.5
	player.hunger = maxf(0.0, player.hunger - hunger_drain * dt)
	if player.hunger <= 0.0:
		var starve := float(health.get("starve_damage_per_second", 0.0))
		if starve == 0.0:
			starve = 2.0
		player.health -= starve * dt
	var warmth: Dictionary = rules.get("warmth", {})
	var warmth_max := float(warmth.get("max", 0.0))
	if warmth_max == 0.0:
		warmth_max = 100.0
	var season_spec: Dictionary = world.season["spec"]
	var cold := float(season_spec.get("cold", 0.0))
	var warmth_drain := float(warmth.get("drain_per_second", 0.0))
	if warmth_drain == 0.0:
		warmth_drain = 0.5
	var night_scale := 0.6
	if warmth.get("night_scale", null) != null:
		night_scale = float(warmth["night_scale"])
	var drain := warmth_drain * cold * (1.0 + world.night * night_scale)
	drain *= 1.0 - Inventory.insulation(world)
	if float(world.torch["remaining"]) > 0.0:
		var heat_scale := 0.7
		var torch_rules: Variant = rules.get("torch", null)
		if torch_rules != null and (torch_rules as Dictionary).get("heat_scale", null) != null:
			heat_scale = float((torch_rules as Dictionary)["heat_scale"])
		drain *= heat_scale
	if float(world.warm["remaining"]) > 0.0:
		# A warm stone stops the cold dead.
		drain = 0.0
	var fire: Dictionary = rules.get("campfire", {})
	var heat := 0.0
	var heat_radius := float(fire.get("heat_radius_meters", 0.0))
	if heat_radius > 0.0:
		for entity in world.entities:
			# Variant compares: two `str()` calls an entity was the whole cost
			# of a scan that finds at most one lit fire.
			if entity.get("state", "") != "lit" or entity.get("kind", "") != "prop":
				continue
			var dx: float = float(entity["x"]) - player.x
			var dz: float = float(entity["z"]) - player.z
			if sqrt(dx * dx + dz * dz) <= heat_radius:
				heat = float(fire.get("heat_per_second", 0.0))
				break
	player.warmth = maxf(0.0, minf(warmth_max, player.warmth + (heat - drain) * dt))
	var freezing := cold > 0.0 and player.warmth <= 0.0 and heat <= 0.0
	if freezing:
		var freeze_damage := float(warmth.get("freeze_damage_per_second", 0.0))
		if freeze_damage == 0.0:
			freeze_damage = 2.0
		player.health -= freeze_damage * dt
		if not world.freezing:
			Helpers.say(world, "You are freezing. Find a fire.")
	world.freezing = freezing
	if player.health <= 0.0 and not world.dead:
		world.dead = true
		var cause := "hurt"
		if freezing:
			cause = "cold"
		elif player.hunger <= 0.0:
			cause = "hunger"
		Helpers.emit(world, {"type": "death", "cause": cause})
		# Deviation: the viewer writes the death line from the view's event
		# drain (index.html 5595-5598). With no view in the headless sim the
		# sim says it, so the message is a fact of the world.
		if cause == "cold":
			Helpers.say(world, "You froze. Press R to begin again.")
		elif cause == "hunger":
			Helpers.say(world, "You starved. Press R to begin again.")
		else:
			Helpers.say(world, "You did not last. Press R to begin again.")
