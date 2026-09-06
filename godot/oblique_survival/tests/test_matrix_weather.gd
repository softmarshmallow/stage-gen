extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T7, T8, T9, T10.
##
## The slew, the season's snow, the rain the snow suppresses, and the strike
## clock. `SysWeather.update` is driven directly wherever the assertion is
## about the slew alone, so a step is exactly one authored increment and the
## count of them is the measurement; the strike run goes through `Sim.step`
## because the strike clock reads `world.time`, which only `day_cycle` moves.

const STEP := 1.0 / 60.0
## The authored onsets and decays of full-v66 (`weather.rain`, `weather.snow`).
const RAIN_ONSET := 14.0
const RAIN_DECAY := 26.0
const SNOW_ONSET := 60.0
const STRIKE_ABOVE := 0.72
const STRIKE_INTERVAL := [7.0, 24.0]


func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	_authored(h, pkg)
	_t7_rain_slew(h, pkg)
	_t8_snow_is_a_season(h, pkg)
	_t9_no_rain_under_snow(h, pkg)
	_t10_strike_now(h, pkg)
	_t10_strikes_in_a_storm(h, pkg)


## The constants above are the run's, not this file's opinion.
func _authored(h: TestHarness, pkg: RunPackage) -> void:
	var rain: Dictionary = (pkg.manifest["weather"] as Dictionary)["rain"]
	var snow: Dictionary = (pkg.manifest["weather"] as Dictionary)["snow"]
	h.assert_near(float(rain["onset_seconds"]), RAIN_ONSET, 1e-9, "the rain onset")
	h.assert_near(float(rain["decay_seconds"]), RAIN_DECAY, 1e-9, "the rain decay")
	h.assert_near(float(snow["onset_seconds"]), SNOW_ONSET, 1e-9, "the snow onset")
	var strike: Dictionary = rain["strike"]
	h.assert_near(float(strike["above"]), STRIKE_ABOVE, 1e-9, "the strike threshold")
	h.assert_eq(strike["interval_seconds"], STRIKE_INTERVAL, "the strike interval")


# ---------------------------------------------------------------------------
# T7. The slew: one onset up, one decay down.
# ---------------------------------------------------------------------------

func _t7_rain_slew(h: TestHarness, pkg: RunPackage) -> void:
	var world := _bare(pkg)
	world.weather["mode"] = "storm"
	var up := _slew_steps(world, func() -> bool: return float(world.weather["rain"]) >= 1.0)
	h.assert_true(up > 0, "the storm never reached full rain")
	# "one onset, plus or minus a step": the ramp is a repeated addition, so
	# the last increment may or may not carry it over the line.
	h.assert_near(float(up) * STEP, RAIN_ONSET, STEP * 1.5,
		"a forced storm reaches full rain in one onset")
	h.assert_near(float(world.weather["rain"]), 1.0, 1e-9, "and stops at 1")
	h.assert_near(float(world.weather["target"]), 1.0, 1e-9, "storm targets 1.0")

	# Half way up, the ramp is linear in the onset.
	var halfway := _bare(pkg)
	halfway.weather["mode"] = "storm"
	for _i in int(round(RAIN_ONSET * 0.5 / STEP)):
		SysWeather.update(halfway, STEP)
	h.assert_near(float(halfway.weather["rain"]), 0.5, 1e-6, "half an onset is half the rain")

	world.weather["mode"] = "clear"
	var down := _slew_steps(world, func() -> bool: return float(world.weather["rain"]) <= 0.0)
	h.assert_true(down > 0, "the rain never cleared")
	h.assert_near(float(down) * STEP, RAIN_DECAY, STEP * 1.5,
		"released to clear, the rain leaves over one decay")
	h.assert_near(float(world.weather["rain"]), 0.0, 1e-9, "and stops at 0")

	# `rain` is the mode's target; `hold` reads the dev slider instead.
	var held := _bare(pkg)
	held.weather["mode"] = "hold"
	held.weather["hold"] = 0.33
	SysWeather.update(held, STEP)
	h.assert_near(float(held.weather["target"]), 0.33, 1e-9, "hold takes the slider's value")
	held.weather["mode"] = "rain"
	SysWeather.update(held, STEP)
	h.assert_near(float(held.weather["target"]), 0.4, 1e-9, "the rain mode targets 0.4")


## Steps `SysWeather` until `done` answers true, or gives up after two minutes
## of simulated time. Returns the number of steps taken, or -1.
func _slew_steps(world: World, done: Callable) -> int:
	for i in int(round(120.0 / STEP)):
		SysWeather.update(world, STEP)
		if bool(done.call()):
			return i + 1
	return -1


# ---------------------------------------------------------------------------
# T8. Snow is a season, not a spell.
# ---------------------------------------------------------------------------

## In `auto`, winter's own `snow` factor is the target: it arrives over the
## authored onset, and the world's look flips the instant the cover passes a
## half — every prop dirtied on that one step, and nothing else touched.
func _t8_snow_is_a_season(h: TestHarness, pkg: RunPackage) -> void:
	var world := _bare(pkg)
	SimFixture.force_season(world, "winter")
	# A handful of things to watch the look swap reach.
	var pine := SimFixture.prop(world, "p1", "pine", "grown", 2.0, 0.0)
	var rock := SimFixture.prop(world, "r1", "moss_boulder", "whole", -2.0, 0.0)
	var moss := SimFixture.forage(world, "f1", 11, 0.0, 1.0)
	var hound := SimFixture.mob(world, "m1", "grub_hound", 8.0, 8.0)
	world.entities.append_array([pine, rock, moss, hound])

	# Walk the whole onset, noting the step the look swapped on and the cover
	# either side of it.
	var flip_step := -1
	var cover_before := -1.0
	var cover_at := -1.0
	var dirty_at_flip := {}
	var full_step := -1
	for i in int(round(SNOW_ONSET * 1.5 / STEP)):
		var before := float(world.weather["snow"])
		world.time += STEP
		SysWeather.update(world, STEP)
		if flip_step < 0 and world.look != "":
			flip_step = i + 1
			cover_before = before
			cover_at = float(world.weather["snow"])
			dirty_at_flip = {
				"pine": bool(pine["dirty"]), "rock": bool(rock["dirty"]),
				"moss": bool(moss["dirty"]), "hound": bool(hound["dirty"]),
			}
			pine["dirty"] = false
			rock["dirty"] = false
		if full_step < 0 and float(world.weather["snow"]) >= 1.0:
			full_step = i + 1

	if not h.assert_true(flip_step > 0, "the look never swapped over a whole onset"):
		return
	h.assert_eq(world.look, "winter", "the look is the season's")
	h.assert_true(cover_before < 0.5, "the look swapped while the cover was under a half")
	h.assert_true(cover_at >= 0.5, "the look swapped before the cover reached a half")
	# Half the onset is 30 s, which is step 1800 of a 60 s onset at 1/60 s.
	h.assert_true(absi(flip_step - 1800) <= 1,
		"the swap landed on step %d, not the halfway 1800" % flip_step)
	h.assert_eq(dirty_at_flip.get("pine"), true, "the pine was not rebuilt on the swap")
	h.assert_eq(dirty_at_flip.get("rock"), true, "the boulder was not rebuilt on the swap")
	h.assert_eq(dirty_at_flip.get("moss"), false, "the swap dirtied a forage piece")
	h.assert_eq(dirty_at_flip.get("hound"), false, "the swap dirtied a mob")
	# It flips once, not every step: nothing was dirtied again after the swap.
	h.assert_eq(bool(pine["dirty"]), false, "the look kept re-dirtying every step")
	h.assert_true(full_step > 0 and absi(full_step - 3600) <= 1,
		"the cover reached 1 at step %d, not at the end of the 60 s onset" % full_step)
	h.assert_near(float(world.weather["snow"]), 1.0, 1e-9, "and it stops at 1")


# ---------------------------------------------------------------------------
# T9. No rain under the snow.
# ---------------------------------------------------------------------------

## `target = peak * (1 - season.snow)`: in a season whose snow is 1 the spell
## still runs and still draws its peak, but nothing falls as rain.
func _t9_no_rain_under_snow(h: TestHarness, pkg: RunPackage) -> void:
	var world := _bare(pkg)
	SimFixture.force_season(world, "winter")
	world.weather["mode"] = "auto"
	# Due now, so this step starts a wet spell and rolls its peak.
	world.weather["spell_ends_at"] = -1.0
	SysWeather.update(world, STEP)
	h.assert_eq(bool(world.weather["wet_spell"]), true, "the spell did not start")
	h.assert_true(float(world.weather["peak"]) >= 0.45, "the wet spell rolled no peak")
	h.assert_near(float(world.weather["target"]), 0.0, 1e-12, "winter's snow did not suppress the rain")
	h.assert_near(float(world.weather["rain"]), 0.0, 1e-12, "it rained under the snow")

	# The same spell in summer does fall.
	var summer := _bare(pkg)
	SimFixture.force_season(summer, "summer")
	summer.weather["mode"] = "auto"
	summer.weather["spell_ends_at"] = -1.0
	SysWeather.update(summer, STEP)
	h.assert_eq(bool(summer.weather["wet_spell"]), true, "the summer spell did not start")
	h.assert_near(float(summer.weather["target"]), float(summer.weather["peak"]), 1e-12,
		"a summer spell targets its whole peak")
	h.assert_true(float(summer.weather["rain"]) > 0.0, "the summer spell brought no rain")


# ---------------------------------------------------------------------------
# T10. Strikes.
# ---------------------------------------------------------------------------

## `strikeNow` (index.html:451-471): the bolt lands 5-21 m off, the thunder is
## queued at `t + 0.2 + distance * 0.05`, and the next strike is armed one
## authored interval out.
func _t10_strike_now(h: TestHarness, pkg: RunPackage) -> void:
	var world := _bare(pkg)
	var strike: Dictionary = ((pkg.manifest["weather"] as Dictionary)["rain"] as Dictionary)["strike"]
	world.time = 100.0
	var low_distance := INF
	var high_distance := -INF
	var low_gap := INF
	var high_gap := -INF
	var thunder_ok := true
	var cell_ok := true
	for _i in 64:
		world.weather["pending"] = []
		world.events.clear()
		SysWeather.strike_now(world, strike)
		var events := SimFixture.events_of(world, "strike")
		if events.size() != 1:
			thunder_ok = false
			break
		var event: Dictionary = events[0]
		var distance := float(event["distance"])
		low_distance = minf(low_distance, distance)
		high_distance = maxf(high_distance, distance)
		var cell := int(event["cell"])
		if cell < 0 or cell > 3:
			cell_ok = false
		var pending: Array = world.weather["pending"]
		if pending.size() != 1 \
				or absf(float((pending[0] as Dictionary)["at"]) - (100.0 + 0.2 + distance * 0.05)) > 1e-9 \
				or absf(float((pending[0] as Dictionary)["distance"]) - distance) > 1e-9:
			thunder_ok = false
		var gap := float(world.weather["next_strike_at"]) - 100.0
		low_gap = minf(low_gap, gap)
		high_gap = maxf(high_gap, gap)
	h.assert_true(thunder_ok, "the thunder was not queued at t + 0.2 + distance * 0.05")
	h.assert_true(cell_ok, "a strike drew a bolt cell outside 0..3")
	h.assert_true(low_distance >= 5.0 and high_distance <= 21.0,
		"a strike landed outside 5-21 m (%.3f .. %.3f)" % [low_distance, high_distance])
	h.assert_true(low_distance < 7.0 and high_distance > 19.0,
		"the strike distance does not span its range (%.3f .. %.3f)" % [low_distance, high_distance])
	h.assert_true(low_gap >= STRIKE_INTERVAL[0] - 1e-9 and high_gap <= STRIKE_INTERVAL[1] + 1e-9,
		"the next strike was armed outside [7, 24] (%.3f .. %.3f)" % [low_gap, high_gap])
	h.assert_eq(int(world.weather["strikes"]), 64, "every strike was counted")
	var last: Dictionary = world.weather["last_strike"]
	h.assert_near(float(last["at"]), 100.0, 1e-9, "the last strike remembers its time")
	h.assert_near(float(world.weather["flash_at"]), 100.0, 1e-9, "and the flash is stamped")


## A run of the storm: the bolt fires once the rain is over the threshold, the
## thunder arrives behind it, and the strikes are spaced by the interval.
func _t10_strikes_in_a_storm(h: TestHarness, pkg: RunPackage) -> void:
	var world := _bare(pkg)
	world.weather["mode"] = "storm"
	var strikes: Array = []
	var thunder: Array = []
	var above_at := -1.0
	for _i in int(round(60.0 / STEP)):
		Sim.step(world, STEP)
		if above_at < 0.0 and float(world.weather["rain"]) >= STRIKE_ABOVE:
			above_at = world.time
		for event: Dictionary in world.events:
			match str(event.get("type", "")):
				"strike":
					strikes.append({"at": world.time, "distance": float(event["distance"])})
				"thunder":
					thunder.append({"at": world.time, "distance": float(event["distance"])})
		world.events.clear()
	h.assert_near(above_at, STRIKE_ABOVE * RAIN_ONSET, STEP + 1e-6,
		"the rain crossed the strike threshold at the wrong time")
	if not h.assert_true(strikes.size() >= 2, "a minute of storm raised %d strikes" % strikes.size()):
		return
	# The clock is armed at `interval[0] * (0.3 + rand * 0.7)` the first time,
	# so the first bolt is inside one whole low interval of the crossing.
	h.assert_true(float((strikes[0] as Dictionary)["at"]) <= above_at + STRIKE_INTERVAL[0] + STEP,
		"the first bolt was later than one low interval after the threshold")
	var low_gap := INF
	var high_gap := -INF
	for i in range(1, strikes.size()):
		var gap: float = float((strikes[i] as Dictionary)["at"]) - float((strikes[i - 1] as Dictionary)["at"])
		low_gap = minf(low_gap, gap)
		high_gap = maxf(high_gap, gap)
	h.assert_true(low_gap >= STRIKE_INTERVAL[0] - STEP and high_gap <= STRIKE_INTERVAL[1] + STEP,
		"two bolts were spaced outside [7, 24] s (%.3f .. %.3f)" % [low_gap, high_gap])

	# Every bolt's thunder followed it, at the speed of feel.
	h.assert_true(thunder.size() >= strikes.size() - 1,
		"%d bolts raised only %d thunders" % [strikes.size(), thunder.size()])
	var lag_ok := true
	for i in thunder.size():
		var heard: Dictionary = thunder[i]
		var bolt: Dictionary = strikes[i]
		var expected: float = float(bolt["at"]) + 0.2 + float(bolt["distance"]) * 0.05
		if absf(float(heard["at"]) - expected) > STEP + 1e-6:
			lag_ok = false
	h.assert_true(lag_ok, "a thunder did not arrive 0.2 s + distance * 0.05 after its bolt")

	# Below the threshold the clock disarms rather than keeping its appointment.
	# Full rain takes (1 - 0.72) * 26 = 7.3 s of decay to fall under it.
	world.weather["mode"] = "clear"
	Sim.advance(world, 10.0)
	h.assert_true(float(world.weather["rain"]) < STRIKE_ABOVE, "the rain is still over the threshold")
	h.assert_true(not is_finite(float(world.weather["next_strike_at"])),
		"the strike clock stayed armed under the threshold")


## A world with the run's masks and nothing standing in it: the weather does
## not read the entity list, and 3520 entities would cost 90 s of test time.
func _bare(pkg: RunPackage) -> World:
	var world := World.create(pkg, 7, {"masks": Masks.from_package(pkg)})
	world.entities.clear()
	return world
