class_name SurvivalFirelightSystem
extends RefCounted

## The one light in the frame. A lit torch is it and it walks with the player;
## otherwise the burning thing whose pool the player stands deepest inside,
## whatever the distance — and how far a fire reaches is its own size. Reads `clock`,
## `entities_state` and `torch`, writes `light` (index.html:1589-1611).

const DEFAULT_TORCH_RADIUS := 3.0
const DEFAULT_FIRE_RADIUS := 6.0

static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "survival/firelight",
		"contract_version": "survival-firelight-system-v1",
		"reads": ["clock", "entities_state", "torch"],
		"writes": ["light"],
	})

static func update(world: SurvivalWorld, _dt: float) -> void:
	var player := world.player
	if float(world.torch["remaining"]) > 0.0:
		world.light["on"] = true
		world.light["x"] = player.x
		world.light["z"] = player.z
		var radius := float(world.torch["radius"])
		world.light["radius"] = radius if radius != 0.0 else DEFAULT_TORCH_RADIUS
		return
	var best: Variant = null
	var best_depth := INF
	var best_radius := DEFAULT_FIRE_RADIUS
	for entity: Dictionary in world.entities:
		# What makes a light is the burning, not the look: a lit fireplace and
		# a burning tree are one thing here.
		if entity["kind"] != "prop" or float(entity.get("burn", 0.0)) <= 0.0:
			continue
		var distance := sqrt(
			pow(float(entity["x"]) - player.x, 2.0) + pow(float(entity["z"]) - player.z, 2.0)
		)
		var radius := SurvivalHelpers.fire_radius(
			world.manifest,
			SurvivalHelpers.look_height(world.prop_spec(entity), str(entity.get("state", "")))
		)
		# The one the player stands deepest inside, not the one nearest: a
		# burning pine four metres off throws further than the fireplace at
		# your feet, and the frame should be lit by the pine.
		var depth := distance - radius
		if depth < best_depth:
			best_depth = depth
			best_radius = radius
			best = entity
	world.light["on"] = best != null
	if best != null:
		world.light["x"] = (best as Dictionary)["x"]
		world.light["z"] = (best as Dictionary)["z"]
	# The radius is written even when nothing is lit: the last line of the
	# viewer's system runs unconditionally, and the fireplace's is the answer.
	world.light["radius"] = best_radius
