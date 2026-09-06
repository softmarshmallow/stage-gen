class_name SysTimers
extends RefCounted

## The clocks on things: the torch, the warm stone, regrowth and the fire's
## burn. Reads `entities`, `torch`, `warm`, `built` and `season`, writes
## `entities_state` (index.html:1330-1364).

static func update(world: World, dt: float) -> void:
	if float(world.torch["remaining"]) > 0.0:
		world.torch["remaining"] = float(world.torch["remaining"]) - dt
		if float(world.torch["remaining"]) <= 0.0:
			world.torch["remaining"] = 0.0
			world.say("The torch burns out.")
	if float(world.warm["remaining"]) > 0.0:
		world.warm["remaining"] = float(world.warm["remaining"]) - dt
		if float(world.warm["remaining"]) <= 0.0:
			world.warm["remaining"] = 0.0
			world.say("The stone has gone cold.")
	# Growth runs at the season's pace; in winter, not at all.
	var spec: Dictionary = world.season["spec"]
	var scale := 1.0
	var authored: Variant = spec.get("regrow_scale")
	if authored is float or authored is int:
		scale = float(authored)
	var grow := dt * scale
	for entity: Dictionary in world.entities:
		var kind: String = entity["kind"]
		if kind == "forage":
			if entity["picked"] and float(entity["regrow"]) > 0.0:
				entity["regrow"] = float(entity["regrow"]) - grow
				if float(entity["regrow"]) <= 0.0:
					entity["picked"] = false
					entity["taken"] = false
					entity["regrow"] = 0.0
					entity["dirty"] = true
			continue
		if kind != "prop":
			continue
		if float(entity["regrow"]) > 0.0:
			entity["regrow"] = float(entity["regrow"]) - grow
			if float(entity["regrow"]) <= 0.0:
				# The prop returns to the look it was placed with, not the
				# family baseline: a pine placed as `old` regrows to `old`.
				var baseline := String(entity.get("baseline", ""))
				if baseline == "":
					baseline = String(world.prop_spec(entity).get("baseline_state", ""))
				entity["state"] = baseline
				entity["hits"] = 0
				entity["dirty"] = true
		if float(entity["burn"]) > 0.0:
			# The fire's burn is not season-scaled.
			entity["burn"] = float(entity["burn"]) - dt
			if float(entity["burn"]) <= 0.0 and entity["state"] == "lit":
				entity["state"] = "unlit"
				entity["dirty"] = true
