class_name RunnerDifficultySystem
extends RefCounted

## How hard the level gets, and how fast the world moves.
##
## A port of `web/lib/sideview-runner/difficulty.ts`. Both ramps are a function
## of distance alone: nothing here reads how well the player is doing, because a
## runner that eases off when you are struggling is a runner whose replay is not
## a function of its seed.
##
## The read of the avatar's distance is a **feedback read** — last frame's
## value — and is not declared, because declaring it would put this system after
## the avatar and the avatar reads the speed this system sets. `after` carries
## the ordering instead and says so out loud.

static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/difficulty",
		"contract_version": "difficulty-system-v4",
		"owns": ["difficulty"],
		"after": ["runner/intent"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	var config := world.config
	var arithmetic: Dictionary = config["arithmetic"]
	var profile := RunnerSegments.ramp_profile(String(config["rampProfile"]))
	var distance := maxf(0.0, float(world.avatar["distanceColumns"]))
	var ceiling := mini(
		int(config["maxAuthoredDifficulty"]),
		mini(
			int(profile["maxCeiling"]),
			1 + int(floor(distance / float(profile["columnsPerCeilingStep"])))
		)
	)
	world.difficulty["ceiling"] = ceiling
	world.difficulty["floor"] = maxi(1, ceiling - int(profile["minCeilingLag"]))
	var multiplier := minf(
		float(arithmetic["maxSpeedMultiplier"]),
		(
			1.0
			+ float(profile["maxSpeedBonus"])
			* minf(1.0, distance / float(profile["speedRampColumns"]))
		)
	)
	world.difficulty["speedMultiplier"] = multiplier
	world.difficulty["speedColumnsPerSecond"] = (
		float(arithmetic["baseSpeedColumnsPerSecond"]) * multiplier
	)
