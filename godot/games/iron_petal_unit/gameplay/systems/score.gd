class_name RunnerScoreSystem
extends RefCounted

## What the run is worth.
##
## A port of `web/lib/sideview-runner/score.ts`. Only pickups chain; a boss pays
## flat, and one miss breaks the chain.

const PICKUP_SCORE := 10
const BOSS_DEFEAT_SCORE := 500
const CHAIN_STEPS := [5, 15, 30]


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "score/run",
		"contract_version": "score-system-v1",
		"reads": ["obstacles"],
		"owns": ["score"],
		"consumes": ["boss-defeated"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	# Last frame's phase. The session is sealed after this system, so the frame
	# a run ends on is still scored — the pickup that killed you still counts.
	if String(world.run["phase"]) != "running":
		return
	FamilyScore.apply(
		world.score,
		{"collected": PICKUP_SCORE, "boss-defeated": BOSS_DEFEAT_SCORE},
		PackedInt32Array(CHAIN_STEPS),
		PackedStringArray(["collected"]),
		{
			"collected": (world.obstacles["collectedThisFrame"] as Array).size(),
			"boss-defeated": world.events.of_type("boss-defeated").size(),
		},
		int(world.obstacles["missedThisFrame"]) > 0,
		true
	)


static func reset(world: RunnerWorld, _scope: String) -> void:
	FamilyScore.reset(world.score)
