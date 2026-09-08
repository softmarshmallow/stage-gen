class_name RunnerDustSystem
extends RefCounted

## The dust a stride, a slide, a take-off and a landing throw.
##
## The one system on the **frame** clock rather than the simulation's, and
## deliberately: a cut-in stops the world, but dust already in the air keeps
## settling, because it is a picture of something that already happened. Every
## other system in this genre reads `clock.simulationNow`; this one reads
## `step.now`, and that asymmetry is load-bearing.
##
## The puffs are seeded from the run's seed and the frame number, so two runs of
## one seed throw the same dust and a picture comparison means something.
##
## What lays a puff is what the world said happened. A takeoff, a landing and the
## first frame of a slide are the avatar's own occurrences; the two trails are
## cadences over levels the avatar publishes, which is a read and not a copy.
##
## The ring, the cap and the noise are the `particles` family's; what a puff
## looks like is this genre's and lives in `RunnerDust`. Only the *drawing* is
## the host's — and until now the whole of this was the host's, which is to say
## it did not exist: the view was never built, so nothing was ever thrown.

static var view: Object = null

## The live records, oldest first. Static because the system is, which is this
## genre's established shape — `RunnerIntentSystem.latch` is the same.
static var _live: Array = []
static var _stride_tick: int = -1
static var _slide_tick: int = -1
## The first frame of a new run lays nothing; see `reset`.
static var _resumed: bool = false


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/dust",
		"contract_version": "dust-system-v2",
		"reads": ["avatar", "run", "camera", "difficulty"],
		"consumes": ["jumped", "landed", "slid"],
		"after": ["runner/parallax", "runner/audio"],
	})


static func update(world: RunnerWorld, step: Dictionary) -> void:
	var now_ms := FamilyVitals.vitals_clock_ms(float(step["now"]))
	var avatar := world.avatar
	var config := world.config
	var scroll_x := float(world.camera["scrollX"])
	var arithmetic: Dictionary = config["arithmetic"]
	var ramp := maxf(1e-9, float(arithmetic["maxSpeedMultiplier"]) - 1.0)
	var intensity := FamilyParticles.unit_progress(
		(float(world.difficulty["speedMultiplier"]) - 1.0) / ramp
	)

	var quiet := _resumed
	_resumed = false
	if String(world.run["phase"]) == "running" and not quiet:
		# A ground takeoff kicks dust; an air jump has no ground to kick, and
		# the occurrence says which it was rather than the reader guessing from
		# a copy of last frame's `grounded`.
		for entry: Variant in world.events.of_type("jumped"):
			if not bool((entry as Dictionary).get("airJump", false)):
				_born(world, "takeoff", RunnerDust.TAKEOFF_PUFFS, now_ms, scroll_x, intensity, step)
		for _entry: Variant in world.events.of_type("landed"):
			_born(world, "land", RunnerDust.LAND_PUFFS, now_ms, scroll_x, intensity, step)
		if bool(avatar["grounded"]) and bool(avatar["sliding"]):
			var tick := int(floor(now_ms / RunnerDust.SLIDE_INTERVAL_MS))
			# The first frame of a slide lays its own puff rather than waiting
			# for the cadence, and that first frame is an occurrence.
			if not world.events.of_type("slid").is_empty() or tick != _slide_tick:
				_slide_tick = tick
				_born(world, "slide", 1, now_ms, scroll_x, intensity, step)
		else:
			_slide_tick = -1
		if bool(avatar["grounded"]) and not bool(avatar["sliding"]):
			var tick := int(floor(now_ms / RunnerDust.STRIDE_INTERVAL_MS))
			if tick != _stride_tick:
				_stride_tick = tick
				_born(world, "stride", 1, now_ms, scroll_x, intensity, step)
		else:
			_stride_tick = -1

	FamilyParticles.ring_prune(
		_live, func(entry: Variant) -> bool: return RunnerDust.record_spent(entry, now_ms)
	)
	if view == null:
		return
	view.call("begin")
	for entry: Variant in _live:
		var puff := RunnerDust.sample_puff(entry, now_ms, scroll_x)
		if not puff.is_empty():
			view.call("puff", puff)
	view.call("commit")


static func _born(
	world: RunnerWorld, kind: String, count: int, now_ms: float, scroll_x: float,
	intensity: float, step: Dictionary
) -> void:
	var config := world.config
	var feet_y := RunnerContract.row_to_screen_y(float(world.avatar["y"]), config)
	for index in count:
		FamilyParticles.ring_remember(
			_live,
			RunnerDust.record(
				kind, index, int(world.run["seed"]), int(step["frame"]), now_ms,
				float(config["avatarScreenX"]), feet_y, scroll_x, float(config["tilePx"]),
				intensity
			),
			RunnerDust.DEFAULT_ACTIVE_CAP
		)


## A new run lays no dust from the old one.
##
## And the first frame of the new run lays nothing either, which is what the
## browser's version did: it spent that frame resynchronising its four shadow
## copies of the avatar and laid no puff. Kept exactly, because a run's first
## frame laying a stride puff is a change somebody should make deliberately,
## with its own evidence.
static func reset(_world: RunnerWorld, _scope: String) -> void:
	_live.clear()
	_stride_tick = -1
	_slide_tick = -1
	_resumed = true
	if view != null and view.has_method("clear_puffs"):
		view.call("clear_puffs")
