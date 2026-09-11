class_name RunnerSegmentsSystem
extends RefCounted

## Build the world ahead, forget the world behind.

static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/segments",
		"contract_version": "segments-system-v4",
		"reads": ["difficulty", "avatar", "encounter"],
		"owns": ["segments"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	var config := world.config
	var profile := RunnerSegments.ramp_profile(String(config["rampProfile"]))
	var ahead := (
		int(ceil(float(world.avatar["distanceColumns"]))) + int(config["streamAheadColumns"])
	)
	var selection := {
		"ceiling": world.difficulty["ceiling"],
		"floor": world.difficulty["floor"],
		"restEveryAppends": profile["restEveryAppends"],
	}
	# The arena is placed only while a fight is actually being staged, so the
	# catalogue between fights never rolls it.
	if RunnerEncounterState.wants_arena(world.encounter):
		selection["arena"] = config["arenaChunk"]
	RunnerSegments.stream_ahead(world.segments, config["chunks"], selection, world.rng, ahead)
	RunnerSegments.drop_behind(
		world.segments,
		int(floor(float(world.avatar["distanceColumns"]))) - int(config["keepBehindColumns"])
	)
