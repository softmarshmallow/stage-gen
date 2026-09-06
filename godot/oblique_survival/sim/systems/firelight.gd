class_name SysFirelight
extends RefCounted

## The one light in the frame. A lit torch is it and it walks with the player;
## otherwise the nearest lit prop, whatever the distance. Reads `clock`,
## `entities_state` and `torch`, writes `light` (index.html:1589-1611).

const DEFAULT_TORCH_RADIUS := 3.0
const DEFAULT_FIRE_RADIUS := 6.0

static func update(world: World, _dt: float) -> void:
	var player := world.player
	if float(world.torch["remaining"]) > 0.0:
		world.light["on"] = true
		world.light["x"] = player.x
		world.light["z"] = player.z
		var radius := float(world.torch["radius"])
		world.light["radius"] = radius if radius != 0.0 else DEFAULT_TORCH_RADIUS
		return
	var best: Variant = null
	var best_distance := INF
	for entity: Dictionary in world.entities:
		if entity["kind"] != "prop" or entity["state"] != "lit":
			continue
		var distance := sqrt(
			pow(float(entity["x"]) - player.x, 2.0) + pow(float(entity["z"]) - player.z, 2.0)
		)
		if distance < best_distance:
			best_distance = distance
			best = entity
	world.light["on"] = best != null
	if best != null:
		world.light["x"] = (best as Dictionary)["x"]
		world.light["z"] = (best as Dictionary)["z"]
	# The fire's radius is written even when no fire is lit: the last line of
	# the viewer's system runs unconditionally.
	var campfire: Variant = world.manifest.get("gameplay", {}).get("campfire")
	var fire_radius := DEFAULT_FIRE_RADIUS
	if campfire is Dictionary:
		var authored: Variant = (campfire as Dictionary).get("light_radius_meters")
		if (authored is float or authored is int) and float(authored) != 0.0:
			fire_radius = float(authored)
	world.light["radius"] = fire_radius
