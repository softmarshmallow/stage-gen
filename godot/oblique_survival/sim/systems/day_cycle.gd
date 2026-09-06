class_name SysDayCycle
extends RefCounted

## The clock. Reads nothing, writes `clock` (index.html:1483-1499).

const DEFAULT_DAY_LENGTH := 180.0

static func update(world: World, dt: float) -> void:
	world.time += dt
	if world.time_frozen:
		return
	var rules: Dictionary = world.manifest.get("gameplay", {})
	var length := DEFAULT_DAY_LENGTH
	var authored: Variant = rules.get("day_length_seconds")
	if (authored is float or authored is int) and float(authored) != 0.0:
		length = float(authored)
	var before := world.day_phase
	world.day_phase = fmod(world.day_phase + dt / length, 1.0)
	if world.day_phase < before:
		world.day += 1
	# Last step's season: the calendar reads the clock, so its share of the day
	# is a frame behind, which no eye can see.
	world.night = Helpers.night_factor(world.day_phase, Helpers.night_share_of(world))
