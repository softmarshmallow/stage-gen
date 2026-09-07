class_name RunnerSessionSystem
extends RefCounted

## A run starts, ends, and the player asks for another.
##
## A port of `web/lib/sideview-runner/session.ts`. The seed of the next run is
## drawn from *this* run's generator, so a chain of runs is as reproducible as a
## single one and "the third run of seed N" can be replayed.
##
## The restart does not happen here. This system emits `run-restarted` and stops;
## the composition sees that event in its reset list at the frame boundary and
## resets every system in sealed order. A system that reset the world mid-frame
## would leave the systems after it reading a world that no longer matches the
## events they are about to consume.

## The seed asked for but not yet spent, held outside the world because between
## the ask and the reset there is no run to hold it.
static var pending_seed: int = -1


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "session/run",
		"contract_version": "session-system-v1",
		"reads": ["intent"],
		"owns": ["run"],
		"emits": ["run-restarted"],
		"consumes": ["run-ended", "fx-released"],
		"after": ["score/run"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	var run := world.run
	match String(run["phase"]):
		"intro":
			for entry: Variant in world.events.of_type("fx-released"):
				if String((entry as Dictionary).get("moment", "")) == "stage_start":
					run["phase"] = "running"
					return
		"running":
			var ended: Array[Dictionary] = world.events.of_type("run-ended")
			if not ended.is_empty():
				run["phase"] = "dead"
				run["endedBy"] = (ended[0] as Dictionary)["source"]
		_:
			# Either key restarts: a player looking at a death card is asking to
			# play, whichever one they reach for.
			if not (bool(world.intent["action"]) or bool(world.intent["jump"])):
				return
			var seed_value := FamilySession.next_session_seed(world.rng)
			world.events.emit({"type": "run-restarted", "seed": seed_value})
			pending_seed = seed_value


static func reset(world: RunnerWorld, scope: String) -> void:
	var seed_value := pending_seed
	if seed_value < 0:
		seed_value = FamilySession.next_session_seed(world.rng)
	pending_seed = -1
	var run_index := 0 if scope == FamilySession.SCOPE_SESSION else int(world.run["runIndex"]) + 1
	world.reset(seed_value, scope == FamilySession.SCOPE_SESSION, world.encounter_binding)
	world.run["seed"] = seed_value
	world.run["runIndex"] = run_index
	world.run["endedBy"] = null
