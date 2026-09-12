class_name RunnerWorld
extends RefCounted

## Everything one run of the runner is, slice by slice.
##
## A port of `web/lib/sideview-runner/world.ts`. Fourteen slices, each with one
## owning system, plus the frozen config and the event queue.
##
## Every number here is a plain float and every collection a plain Array or
## Dictionary. Nothing holds an engine vector: `Vector2` is single precision in
## the default build, and a world that stores one cannot be compared against
## another implementation of itself — which is the whole basis of the parity
## this port is proved by.
##
## The unit is the **column** across and the **row** down, never a pixel. Rows
## increase downward, so a smaller `y` is higher up.

var clock: Dictionary = {}
var intent: Dictionary = {}
var difficulty: Dictionary = {}
var avatar: Dictionary = {}
var segments: Dictionary = {}
var obstacles: Dictionary = {}
var vitals: Dictionary = {}
var run: Dictionary = {}
var score: Dictionary = {}
var camera: Dictionary = {}
## The moment in flight, or empty for none.
var fx: Dictionary = {}
var locomotion: String = "run"
## The fight in flight, or empty when this package declares no encounter.
var encounter: Dictionary = {}

var events: KernelEventQueue = null
var config: Dictionary = {}
## The fight's authored fields plus the two numbers only a loaded boss atlas can
## supply. Empty when this run plays without fights. It lives here rather than on
## the roster because it is this run's configuration, and because a system that
## reached back to the roster for it would make the roster and its own systems
## name each other — a cycle GDScript will not resolve.
var encounter_binding: Dictionary = {}

## The run's generator. Drawn from by exactly two places — the segment stream
## and the session's next seed — so "how many times has this run drawn" is a
## meaningful divergence signal.
var rng: KernelRng = null


## Build a world from a parsed config. `encounter_binding` carries the two
## numbers only a loaded boss atlas can supply; an empty binding means this run
## plays without fights, which is what a headless replay does.
static func create(
	config: Dictionary, seed_value: int, intro: bool, encounter_binding: Dictionary
) -> RunnerWorld:
	var world := RunnerWorld.new()
	world.config = config
	world.encounter_binding = encounter_binding
	world.events = KernelEventQueue.new()
	world.clock = FamilyClock.create()
	world.score = FamilyScore.create()
	world.reset(seed_value, intro, encounter_binding)
	return world


## Put the world back to the start of a run.
##
## The clock and the score are deliberately **not** rebuilt here: the clock's
## integral is the session's and a refractory window stamped against it must not
## be reopened by a restart, and the score is the score system's to reset in
## sealed order. Everything else is built fresh.
func reset(seed_value: int, intro: bool, binding: Dictionary) -> void:
	var run_index := int(run.get("runIndex", 0))
	rng = KernelRng.new(seed_value)
	intent = neutral_intent()
	difficulty = {
		"ceiling": 1,
		"floor": 1,
		"speedMultiplier": 1.0,
		"speedColumnsPerSecond": float(
			(config["arithmetic"] as Dictionary)["baseSpeedColumnsPerSecond"]
		),
	}
	avatar = {
		"distanceColumns": 2.0,
		"y": float(config["walkSurfaceRow"]),
		"vy": 0.0,
		"grounded": true,
		"airJumpsUsed": 0,
		"sliding": false,
		"jumpImpulses": 0,
		"motion": "run",
	}
	segments = RunnerSegments.create(int(config["rows"]), int(config["walkSurfaceRow"]))
	obstacles = {
		"collected": {},
		"missed": {},
		"hazardContact": false,
		"struck": {},
		"cleared": {},
		"collectedThisFrame": [],
		"missedThisFrame": 0,
	}
	vitals = FamilyVitals.create(int(config["maxVitalPoints"]))
	run = {
		"phase": "intro" if intro else "running",
		"seed": seed_value,
		"runIndex": run_index,
		"endedBy": null,
	}
	fx = {}
	locomotion = "run"
	encounter = {}
	encounter_binding = binding
	if not binding.is_empty():
		encounter = RunnerEncounterState.create(binding)
	camera = {"scrollX": camera_scroll_x(float(avatar["distanceColumns"]), config)}
	# The first window is primed with no rest cadence and no arena: a run opens
	# on whatever the catalogue rolls, and the director has not asked for a
	# fight before the first step.
	RunnerSegments.stream_ahead(
		segments,
		config["chunks"],
		{"ceiling": 1, "floor": 1},
		rng,
		int(ceil(float(avatar["distanceColumns"]))) + int(config["streamAheadColumns"])
	)
	if intro and not (config["introMoment"] as Dictionary).is_empty():
		var moment: Dictionary = config["introMoment"]
		fx = {
			"moment": String(moment["moment"]),
			"choreography": String(moment["choreography"]),
			"startedAt": null,
			"released": false,
		}


## Nothing asked for.
static func neutral_intent() -> Dictionary:
	return {"jump": false, "duck": false, "thrust": false, "action": false}


## Where the view sits so the avatar stands on its anchor.
static func camera_scroll_x(distance_columns: float, config: Dictionary) -> float:
	return FamilyCamera.anchored_scroll(
		distance_columns * float(config["tilePx"]), float(config["avatarScreenX"])
	)
