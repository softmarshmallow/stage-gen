class_name SurvivalTimersSystem
extends RefCounted

## The clocks on things: the torch, the warm stone, regrowth and the fire's
## burn. Reads `entities`, `torch`, `warm`, `built` and `season`, writes
## `entities_state` (index.html:1330-1364).

static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "survival/timers",
		"contract_version": "survival-timers-system-v1",
		"reads": ["entities", "torch", "warm", "built", "season"],
		"writes": ["entities_state"],
	})

static func update(world: SurvivalWorld, dt: float) -> void:
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
			if float(entity["burn"]) <= 0.0:
				_fire_out(world, entity)


## The flame dies. What it leaves is the `burn` interaction's `next_state` —
## the stump under a tree, the picked look under a bush — read from the thing's
## own contract rather than remembered on the entity, because the look it is
## burning in is the look that interaction applies from. A prop with no such
## interaction is the fireplace, and it goes back to unlit the way it always
## did.
static func _fire_out(world: SurvivalWorld, entity: Dictionary) -> void:
	entity["burn"] = 0.0
	entity["dirty"] = true
	var spec: Variant = world.prop_spec(entity)
	var state := str(entity.get("state", ""))
	if spec != null:
		var rows: Variant = (spec as Dictionary).get("interactions", null)
		if rows is Array:
			for block: Dictionary in (rows as Array):
				if str(block.get("verb", "")) != "burn":
					continue
				var from: Variant = block.get("from", null)
				if from == null or not (from as Array).has(state):
					continue
				entity["state"] = block["next_state"]
				entity["hits"] = 0
				var regrow: Variant = block.get("regrow_seconds", null)
				entity["regrow"] = float(regrow) if regrow != null else 0.0
				return
	if state == "lit":
		entity["state"] = "unlit"
