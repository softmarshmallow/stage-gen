extends RefCounted

## The clock, the calendar and the weather's slew: the four systems that run on
## time alone (day_cycle, season, weather, firelight).

func run(h: TestHarness) -> void:
	_night_curve(h)
	_calendar(h)
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	_season_turn(h, pkg)
	_snow_onset_and_decay(h, pkg)

## `nightFactor`: 0 at midday, 1 in the deep of the night. A longer night is an
## earlier dusk, because dawn always ends at the day's turn.
func _night_curve(h: TestHarness) -> void:
	# Summer (night_share 0.38): dusk at 0.50, full night from 0.62 to 0.88.
	h.assert_near(Helpers.night_factor(0.12, 0.38), 0.0, 1e-9, "summer noon")
	h.assert_near(Helpers.night_factor(0.50, 0.38), 0.0, 1e-9, "summer dusk begins")
	h.assert_near(Helpers.night_factor(0.56, 0.38), 0.5, 1e-9, "summer half way into dusk")
	h.assert_near(Helpers.night_factor(0.62, 0.38), 1.0, 1e-9, "summer full night")
	h.assert_near(Helpers.night_factor(0.72, 0.38), 1.0, 1e-9, "summer deep night")
	h.assert_near(Helpers.night_factor(0.88, 0.38), 1.0, 1e-9, "summer dawn begins")
	h.assert_near(Helpers.night_factor(0.94, 0.38), 0.5, 1e-9, "summer half way through dawn")
	h.assert_near(Helpers.night_factor(0.9999, 0.38), 0.0008333333, 1e-7, "summer day's turn")

	# Winter (night_share 0.55): dusk at 0.33.
	h.assert_near(Helpers.night_factor(0.32, 0.55), 0.0, 1e-9, "winter before dusk")
	h.assert_near(Helpers.night_factor(0.39, 0.55), 0.5, 1e-9, "winter half way into dusk")
	h.assert_near(Helpers.night_factor(0.45, 0.55), 1.0, 1e-9, "winter full night")
	# The same phase is night in winter and day in summer: the share matters.
	h.assert_near(Helpers.night_factor(0.40, 0.38), 0.0, 1e-9, "phase 0.40 is day in summer")
	h.assert_true(Helpers.night_factor(0.40, 0.55) > 0.5, "phase 0.40 is not night in winter")

	# The dusk is clamped into [0.2, 0.76] however long the night is authored.
	h.assert_near(Helpers.night_factor(0.19, 0.9), 0.0, 1e-9, "a very long night still starts at 0.2")
	h.assert_near(Helpers.night_factor(0.26, 0.9), 0.5, 1e-9, "a very long night's dusk ramp")
	h.assert_near(Helpers.night_factor(0.75, 0.0), 0.0, 1e-9, "a run with no night")
	h.assert_near(Helpers.night_factor(0.82, 0.0), 0.5, 1e-9, "the shortest night's dusk ramp")

	# The phase wraps.
	h.assert_near(Helpers.night_factor(1.72, 0.38), 1.0, 1e-9, "phase 1.72 wraps to 0.72")
	h.assert_near(Helpers.night_factor(-0.28, 0.38), 1.0, 1e-9, "phase -0.28 wraps to 0.72")

## full-v66's calendar: four days a season, summer then winter.
func _calendar(h: TestHarness) -> void:
	var season := {
		"calendar": {"days_per_season": 4, "order": ["summer", "winter"]},
		"specs": {"summer": {"season_id": "summer"}, "winter": {"season_id": "winter"}},
		"force": "auto",
	}
	var expected := ["summer", "summer", "summer", "summer", "winter", "winter", "winter", "winter", "summer"]
	for index in expected.size():
		var day := index + 1
		var now := Helpers.season_for(season, day)
		h.assert_eq(now["id"], expected[index], "day %d is not %s" % [day, expected[index]])
	h.assert_eq(Helpers.season_for(season, 5)["day_in_season"], 1, "day 5 is the first of winter")
	h.assert_eq(Helpers.season_for(season, 8)["day_in_season"], 4, "day 8 is the fourth of winter")
	h.assert_eq(Helpers.season_for(season, 9)["index"], 0, "day 9 wraps the order")

	# A forced season overrides the id but not the index the calendar reached.
	season["force"] = "winter"
	h.assert_eq(Helpers.season_for(season, 1)["id"], "winter", "a forced season did not take")
	h.assert_eq(Helpers.season_for(season, 1)["index"], 0, "a forced season moved the index")

	# A run with no calendar has no season at all.
	h.assert_eq(Helpers.season_for({"calendar": null, "specs": {}, "force": "auto"}, 3)["id"], "", "no calendar")

## The live turn: a summer day rolls into day 5 and winter arrives, hiding the
## forage the season covers.
func _season_turn(h: TestHarness, pkg: RunPackage) -> void:
	var world := World.create(pkg, 7, {"masks": Masks.new()})
	Sim.step(world, Sim.FIXED_STEP)
	h.assert_eq(world.season["id"], "summer", "the first tick is not summer")
	h.assert_eq(int(world.season["turns"]), 1, "the first tick did not count a turn")
	h.assert_eq(world.message, "", "the first automatic season announced itself")
	h.assert_near(float(world.season["spec"]["night_share"]), 0.38, 1e-9, "summer night share")

	# Stand at the end of day 4 and let the clock roll over.
	world.day = 4
	world.day_phase = 0.999
	Sim.advance(world, 0.5)
	h.assert_eq(world.day, 5, "the day did not roll over")
	h.assert_eq(world.season["id"], "winter", "day 5 is not winter")
	h.assert_eq(int(world.season["day_in_season"]), 1, "day 5 is not the first of winter")
	h.assert_eq(world.message, "Winter comes.", "the turn was not announced")
	h.assert_near(float(world.season["spec"]["cold"]), 1.0, 1e-9, "winter is not cold")
	h.assert_near(float(world.season["spec"]["regrow_scale"]), 0.0, 1e-9, "winter still grows")

	# The season hid the forage it covers, and only that.
	var hidden := 0
	var visible := 0
	for entity: Dictionary in world.entities:
		if entity["kind"] != "forage":
			continue
		if entity["item_id"] == "mushroom" or entity["item_id"] == "moss":
			if entity["hidden"]:
				hidden += 1
		elif entity["hidden"]:
			visible += 1
	h.assert_true(hidden > 0, "winter hid no mushrooms or moss")
	h.assert_eq(visible, 0, "winter hid forage it does not cover")

	# The clock now reads the winter share: phase 0.40 is night in winter.
	world.day_phase = 0.40
	Sim.step(world, Sim.FIXED_STEP)
	h.assert_true(world.night > 0.5, "the clock is still using the summer night share")

## Snow is the season's, not a spell: it arrives over the authored onset (60 s)
## and leaves over the decay (120 s).
func _snow_onset_and_decay(h: TestHarness, pkg: RunPackage) -> void:
	var world := World.create(pkg, 7, {"masks": Masks.new()})
	# The onset and the decay do not read the entity list; dropping it keeps
	# 190 s of simulation (11 400 fixed steps) inside a test run.
	world.entities = []
	world.season["force"] = "winter"
	Sim.step(world, Sim.FIXED_STEP)
	h.assert_eq(world.season["id"], "winter", "the forced season did not take")
	# One step of onset has already run (1/60 s of a 60 s onset).
	h.assert_true(float(world.weather["snow"]) < 0.01, "snow started above zero")
	h.assert_eq(world.look, "", "the winter look came before the snow")

	Sim.advance(world, 55.0)
	var partway := float(world.weather["snow"])
	h.assert_true(partway > 0.8 and partway < 1.0, "snow at 55 s is %f, not part way" % partway)
	h.assert_eq(world.look, "winter", "the look did not swap at snow 0.5")

	Sim.advance(world, 10.0)
	h.assert_near(float(world.weather["snow"]), 1.0, 1e-6, "snow did not reach 1 within 65 s")
	h.assert_near(float(world.weather["rain"]), 0.0, 1e-6, "it rained under a snowy season")

	world.season["force"] = "summer"
	Sim.step(world, Sim.FIXED_STEP)
	h.assert_eq(world.season["id"], "summer", "the forced summer did not take")
	Sim.advance(world, 110.0)
	h.assert_true(float(world.weather["snow"]) > 0.0, "snow decayed faster than the authored 120 s")
	Sim.advance(world, 15.0)
	h.assert_near(float(world.weather["snow"]), 0.0, 1e-6, "snow did not clear within 125 s")
	h.assert_eq(world.look, "", "the look did not swap back")
