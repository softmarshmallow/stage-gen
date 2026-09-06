extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T12, T13, the two halves of T24 that
## `test_mob` leaves open, and T27.
##
## The exact second the belly empties, the freezing message's edge latch, the
## hound's wander pace and its refusal to walk into the sea, and the footstep
## cadence.

const STEP := 1.0 / 60.0
## `100 / 0.6`: how long a full belly lasts at the authored drain.
const SECONDS_TO_STARVE := 166.66666666666666
## `pi / 9.5`: one foot planted per half turn of the walk cycle.
const STEP_SECONDS := PI / 9.5


func run(h: TestHarness) -> void:
	var world := SimFixture.world()
	if world == null:
		h.fail("could not open %s" % TestHarness.RUN_DIR)
		return
	_t12_hunger(h, world)
	_t13_freezing_latch(h, world)
	_t24_wander_pace(h, world)
	_t24_the_blow_lands_at_the_end(h, world)
	_t24_the_sea_turns_it_back(h, world)
	_t27_footsteps(h)


func _reset(world: World, season_id: String) -> void:
	SimFixture.bare(world)
	world.player.x = 0.0
	world.player.z = 0.0
	world.player.health = 100.0
	world.player.hunger = 100.0
	world.player.warmth = 100.0
	world.player.invulnerable = 0.0
	world.player.busy = null
	world.player.approach = null
	world.torch = {"remaining": 0.0, "radius": 0.0}
	world.warm = {"remaining": 0.0}
	world.night = 0.0
	world.freezing = false
	world.dead = false
	world.message = ""
	world.events.clear()
	# The wander orbit is phased by `world.time`, so it is pinned too.
	world.time = 0.0
	SimFixture.force_season(world, season_id)


func _vitals(world: World, seconds: float) -> void:
	for _i in int(round(seconds / STEP)):
		SysVitals.update(world, STEP)


# ---------------------------------------------------------------------------
# T12. The belly, and what follows it.
# ---------------------------------------------------------------------------

## 0.6 a second from 100 is 166.667 s; from there the shortfall is 2 health a
## second, and the death it ends in names the hunger.
func _t12_hunger(h: TestHarness, world: World) -> void:
	var hunger: Dictionary = (world.manifest["gameplay"] as Dictionary)["hunger"]
	var health: Dictionary = (world.manifest["gameplay"] as Dictionary)["health"]
	h.assert_near(float(hunger["drain_per_second"]), 0.6, 1e-9, "the authored hunger drain")
	h.assert_near(float(health["starve_damage_per_second"]), 2.0, 1e-9, "the authored starve damage")
	h.assert_near(SECONDS_TO_STARVE, 100.0 / 0.6, 1e-9, "100 at 0.6 a second is 166.667 s")

	# A quarter of a second short of the line the belly still holds something.
	_reset(world, "summer")
	_vitals(world, SECONDS_TO_STARVE - 0.25)
	h.assert_true(world.player.hunger > 0.0,
		"the belly emptied early (%.6f left)" % world.player.hunger)
	h.assert_near(world.player.health, 100.0, 1e-9, "and nothing has been taken from health")

	# Over it, the belly is empty and health starts to go.
	_reset(world, "summer")
	_vitals(world, SECONDS_TO_STARVE + 0.25)
	h.assert_near(world.player.hunger, 0.0, 1e-9, "the belly did not empty on time")
	h.assert_true(world.player.health < 100.0, "an empty belly did not start on health")
	h.assert_true(world.player.health > 99.0, "and it took more than the first steps' worth")

	# Ten more seconds is twenty health.
	var before := world.player.health
	_vitals(world, 10.0)
	h.assert_near(world.player.health, before - 20.0, 0.05, "starving costs 2 health a second")

	# The death it ends in is the hunger's, and it fires once.
	_reset(world, "summer")
	world.player.hunger = 0.0
	world.player.health = 5.0
	_vitals(world, 10.0)
	h.assert_eq(world.dead, true, "starvation did not finish the player")
	var deaths := SimFixture.events_of(world, "death")
	h.assert_eq(deaths.size(), 1, "death fired %d times" % deaths.size())
	h.assert_eq(str((deaths[0] as Dictionary)["cause"]), "hunger", "the cause is the hunger")


# ---------------------------------------------------------------------------
# T13. Freezing, and the latch on its message.
# ---------------------------------------------------------------------------

## `cold > 0 && warmth <= 0 && heat <= 0` takes 2 health a second, and the line
## is said on the edge into that state and not once more until it is left.
func _t13_freezing_latch(h: TestHarness, world: World) -> void:
	var warmth: Dictionary = (world.manifest["gameplay"] as Dictionary)["warmth"]
	h.assert_near(float(warmth["freeze_damage_per_second"]), 2.0, 1e-9, "the authored freeze damage")

	_reset(world, "winter")
	world.player.warmth = 0.0
	SysVitals.update(world, STEP)
	h.assert_eq(world.freezing, true, "an empty warmth in winter is not freezing")
	h.assert_eq(world.message, "You are freezing. Find a fire.", "the line was not said")
	h.assert_near(world.player.health, 100.0 - 2.0 * STEP, 1e-9, "and the cold took its first bite")

	# Held in the same state, the line is not said again.
	world.message = ""
	_vitals(world, 20.0)
	h.assert_eq(world.message, "", "the freezing line repeated while the state held")
	h.assert_near(world.player.health, 100.0 - 2.0 * (20.0 + STEP), 0.05,
		"the cold kept taking 2 health a second")

	# A fire clears the latch, and losing it sets the line again: this is an
	# edge, not a level.
	var fire := SimFixture.prop(world, "c1", "campfire", "unlit", 0.0, 2.0)
	fire["state"] = "lit"
	world.entities.append(fire)
	SysVitals.update(world, STEP)
	h.assert_eq(world.freezing, false, "a lit fire in reach is still freezing")
	world.entities.clear()
	world.message = ""
	world.player.warmth = 0.0
	SysVitals.update(world, STEP)
	h.assert_eq(world.freezing, true, "walking away from the fire is not freezing again")
	h.assert_eq(world.message, "You are freezing. Find a fire.", "and the line is said again")

	# Summer has no cold, so an empty warmth is not freezing at all.
	_reset(world, "summer")
	world.player.warmth = 0.0
	world.message = ""
	_vitals(world, 5.0)
	h.assert_eq(world.freezing, false, "a summer with no cold froze the player")
	h.assert_eq(world.message, "", "and said something about it")
	h.assert_near(world.player.health, 100.0, 1e-9, "and took health for it")


# ---------------------------------------------------------------------------
# T24. The two halves `test_mob` leaves.
# ---------------------------------------------------------------------------

## Out of aggro the hound orbits home at 0.35 of its speed: 2.6 * 0.35 = 0.91.
func _t24_wander_pace(h: TestHarness, world: World) -> void:
	var rules: Dictionary = ((world.manifest["gameplay"] as Dictionary)["mob"] as Dictionary)
	h.assert_near(float(rules["speed_meters_per_second"]), 2.6, 1e-9, "the hound's speed")
	h.assert_near(float(rules["attack_range_meters"]), 1.0, 1e-9, "its attack range")
	h.assert_near(float(rules["attack_cooldown_seconds"]), 1.5, 1e-9, "its cooldown")
	# The blow lands inside `range + both footprints`.
	h.assert_near(1.0 + world.player.radius + 0.476, 1.816, 1e-6, "the reach a bite needs")

	_reset(world, "summer")
	world.player.x = 60.0
	world.player.z = 60.0
	var hound := SimFixture.mob(world, "m1", "grub_hound", 0.0, 0.0)
	# Off its home mark, so the orbit has somewhere to pull it.
	hound["x"] = 2.0
	hound["z"] = 0.0
	world.entities.append(hound)
	SysMobAi.update(world, STEP)
	var pace := sqrt(pow(float(hound["vx"]), 2.0) + pow(float(hound["vz"]), 2.0))
	h.assert_near(pace, 2.6 * 0.35, 1e-6, "the wander pace is not 0.35 of the walk")
	h.assert_eq(str(hound["state"]), "walk", "a wandering hound walks")

	# Inside the aggro radius it comes on at the full walk instead.
	_reset(world, "summer")
	world.player.x = 0.0
	world.player.z = 0.0
	var chaser := SimFixture.mob(world, "m2", "grub_hound", 4.0, 0.0)
	world.entities.append(chaser)
	SysMobAi.update(world, STEP)
	var chase := sqrt(pow(float(chaser["vx"]), 2.0) + pow(float(chaser["vz"]), 2.0))
	h.assert_near(chase, 2.6, 1e-6, "a hound on the scent runs at its whole speed")


## A step that would land in the water is not taken: the hound reverses both
## velocity components and stands still for the tick.
func _t24_the_sea_turns_it_back(h: TestHarness, world: World) -> void:
	var speed := 2.6
	var reach := speed * STEP
	var shore := _shore_point(world, reach)
	if not h.assert_true(not is_inf(float(shore["x"])), "no shoreline was found on the run's plate"):
		return

	_reset(world, "summer")
	var x := float(shore["x"])
	var z := float(shore["z"])
	# The player stands out in the water, three metres east: inside the aggro
	# radius, outside the bite, so the hound walks straight at the sea.
	world.player.x = x + 3.0
	world.player.z = z
	var hound := SimFixture.mob(world, "m1", "grub_hound", x, z)
	world.entities.append(hound)
	SysMobAi.update(world, STEP)
	h.assert_eq(str(hound["state"]), "walk", "the hound did not set off")
	h.assert_near(float(hound["x"]), x, 1e-12, "the hound stepped into the water")
	h.assert_near(float(hound["z"]), z, 1e-12, "on the other axis too")
	h.assert_near(float(hound["vx"]), -speed, 1e-6, "the refused step did not reverse vx")
	h.assert_near(float(hound["vz"]), 0.0, 1e-6, "nor vz")


## The hound's swing is four frames at 12 fps, and the 10 damage lands on the
## step that finishes it — not when it starts.
func _t24_the_blow_lands_at_the_end(h: TestHarness, world: World) -> void:
	var states: Dictionary = ((world.manifest["actors"] as Dictionary)["grub_hound"] as Dictionary)["states"]
	var swing := Targeting.state_duration(states["attack"])
	h.assert_near(swing, 4.0 / 12.0, 1e-9, "the swing is four frames at 12 fps")
	h.assert_near(swing, 0.33333333, 1e-7, "which is 0.3333 s")

	_reset(world, "summer")
	world.player.x = 0.0
	world.player.z = 0.0
	var hound := SimFixture.mob(world, "m1", "grub_hound", 1.5, 0.0)
	world.entities.append(hound)
	SysMobAi.update(world, STEP)
	h.assert_eq(str(hound["state"]), "attack", "1.5 m is inside the bite's reach")
	h.assert_near(float(hound["elapsed"]), 0.0, 1e-12, "the swing starts from zero")
	h.assert_near(float(hound["cooldown"]), 1.5, 1e-9, "and the cooldown is set on the swing")

	var landed := -1
	for i in 40:
		SysMobAi.update(world, STEP)
		if world.player.health < 100.0:
			landed = i + 1
			break
	# 0.3333 s at 1/60 is twenty steps; the repeated addition may need one more.
	h.assert_true(landed == 20 or landed == 21,
		"the blow landed on step %d of the swing, not at its end" % landed)
	h.assert_near(world.player.health, 90.0, 1e-9, "the bite costs the authored 10")
	h.assert_near(world.player.invulnerable, 0.7, 1e-9, "and opens 0.7 s of i-frames")
	h.assert_eq(str(hound["state"]), "idle", "the hound drops out of the swing")


## A point that is land, whose step of `reach` toward +x is not.
##
## A hound's step is 2.6 / 60 = 0.043 m and the plate's cells are 0.25 m, so
## such a point is a thin band just inside a shoreline: found by walking the
## row at cell width for a land-to-water edge, then bisecting for the edge
## itself and standing back half a step from it.
func _shore_point(world: World, reach: float) -> Dictionary:
	var z := -110.0
	while z <= 110.0:
		var x := -110.0
		while x < 110.0:
			var here := world.is_land(x, z)
			var there := world.is_land(x + 0.25, z)
			if here and not there:
				var low := x
				var high := x + 0.25
				for _i in 30:
					var middle := (low + high) * 0.5
					if world.is_land(middle, z):
						low = middle
					else:
						high = middle
				var point := low - reach * 0.5
				if world.is_land(point, z) and not world.is_land(point + reach, z):
					return {"x": point, "z": z}
			x += 0.25
		z += 1.0
	return {"x": INF, "z": INF}


# ---------------------------------------------------------------------------
# T27. Footsteps.
# ---------------------------------------------------------------------------

## Records what `Sfx.footsteps` would have played, so the cadence can be read
## without an audio device or the run's clips.
class StepSpy extends Sfx:
	var calls: Array = []

	func play(cue: String, scale: float = 1.0) -> bool:
		calls.append({"cue": cue, "scale": scale})
		return true


## One step per `pi / 9.5` of the player's own `elapsed`; the first frame of a
## walk is silent, because the counter has nothing to compare against yet.
func _t27_footsteps(h: TestHarness) -> void:
	h.assert_near(Sfx.WALK_RATE, 9.5, 1e-9, "the walk rate")
	h.assert_near(STEP_SECONDS, 0.33069396, 1e-7, "one step is pi / 9.5 seconds")

	var spy := StepSpy.new()
	# The cues the package would have decoded; the spy never touches them.
	spy._streams = {"footstep": null, "footstep_snow": null}
	spy._sounds = {"footstep": {}, "footstep_snow": {}}

	var player := {"state": "walk", "busy": null, "elapsed": 0.0}
	spy.footsteps(player, 0.0)
	h.assert_eq(spy.calls.size(), 0, "the first frame of a walk was not silent")

	# Walk for three whole cadences and count what was planted.
	var elapsed := 0.0
	while elapsed < STEP_SECONDS * 3.0 - 1e-6:
		elapsed += STEP
		player["elapsed"] = elapsed
		spy.footsteps(player, 0.0)
	h.assert_eq(spy.calls.size(), 3, "three cadences did not plant three feet")
	var sides: Array = []
	var cues: Array = []
	for call: Dictionary in spy.calls:
		sides.append(float(call["scale"]))
		cues.append(str(call["cue"]))
	h.assert_eq(sides, [0.85, 1.0, 0.85], "the feet did not alternate at 0.85 and 1.0")
	h.assert_eq(cues, ["footstep", "footstep", "footstep"], "a dry walk played something else")

	# Standing still resets the counter, so the next walk is silent for a frame.
	spy.calls.clear()
	player["state"] = "idle"
	spy.footsteps(player, 0.0)
	h.assert_eq(spy.calls.size(), 0, "an idle player planted a foot")
	player["state"] = "walk"
	player["elapsed"] = 0.0
	spy.footsteps(player, 0.0)
	h.assert_eq(spy.calls.size(), 0, "the first frame of the next walk was not silent")

	# A busy player is not walking, whatever the state says.
	spy.calls.clear()
	player["busy"] = {"state": "gather"}
	player["elapsed"] = STEP_SECONDS * 3.0
	spy.footsteps(player, 0.0)
	h.assert_eq(spy.calls.size(), 0, "a harvesting player planted a foot")
	player["busy"] = null

	# Under half a cover of snow the walk crunches instead.
	spy.calls.clear()
	spy._step_count = -1
	player["elapsed"] = 0.0
	spy.footsteps(player, 0.49)
	player["elapsed"] = STEP_SECONDS * 1.1
	spy.footsteps(player, 0.49)
	h.assert_eq(str((spy.calls[0] as Dictionary)["cue"]), "footstep",
		"under half a cover the walk is still dry")
	spy.calls.clear()
	player["elapsed"] = STEP_SECONDS * 2.1
	spy.footsteps(player, 0.5)
	h.assert_eq(str((spy.calls[0] as Dictionary)["cue"]), "footstep_snow",
		"at half a cover the walk did not crunch")

	# With no snow cue in the package the dry one is played whatever the cover.
	spy.calls.clear()
	spy._streams = {"footstep": null}
	player["elapsed"] = STEP_SECONDS * 3.1
	spy.footsteps(player, 1.0)
	h.assert_eq(str((spy.calls[0] as Dictionary)["cue"]), "footstep",
		"a package with no snow cue played one anyway")
	spy.free()
