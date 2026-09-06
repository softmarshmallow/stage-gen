extends RefCounted

## Vitals: hunger, the cold, the fire's heat, freezing, and the one death.
##
## The formulas are exercised through `SysVitals.update` directly so that one
## condition is measured at a time; the clock and the calendar are held still
## rather than driven.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_vitals: could not open %s" % TestHarness.RUN_DIR)
		return
	_hunger(h, w)
	_a_day_of_hunger_starves(h, w)
	_winter_cold(h, w)
	_a_fire_gives_warmth_back(h, w)
	_freezing_takes_health(h, w)
	_death_fires_once(h, w)


func _reset(w: World, season_id: String) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.health = 100.0
	w.player.hunger = 100.0
	w.player.warmth = 100.0
	w.player.invulnerable = 0.0
	w.torch = {"remaining": 0.0, "radius": 0.0}
	w.warm = {"remaining": 0.0}
	w.night = 0.0
	w.freezing = false
	w.dead = false
	w.message = ""
	SimFixture.force_season(w, season_id)


func _run_seconds(w: World, seconds: float) -> void:
	var steps := int(round(seconds / SimFixture.STEP))
	for i in steps:
		SysVitals.update(w, SimFixture.STEP)


func _hunger(h: TestHarness, w: World) -> void:
	# gameplay.hunger.drain_per_second is 0.25, so ten seconds cost two and a
	# half; a full belly lasts 400 s of a 480 s day.
	_reset(w, "summer")
	var drain := float(((w.manifest["gameplay"] as Dictionary)["hunger"] as Dictionary)["drain_per_second"])
	h.assert_near(drain, 0.25, 1e-9, "the authored hunger drain")
	_run_seconds(w, 10.0)
	h.assert_near(w.player.hunger, 100.0 - drain * 10.0, 0.01, "hunger drains 0.25 a second")
	h.assert_near(w.player.health, 100.0, 1e-9, "a fed player takes no damage")
	h.assert_near(w.player.warmth, 100.0, 1e-9, "and summer costs no warmth")


func _a_day_of_hunger_starves(h: TestHarness, w: World) -> void:
	# 0.25 a second over a 480 s day is 120: one day empties a full belly with
	# 80 s to spare, and the rest is 2 health a second.
	_reset(w, "summer")
	var day_length := float((w.manifest["gameplay"] as Dictionary)["day_length_seconds"])
	h.assert_near(day_length, 480.0, 1e-9, "the day is 480 s")
	_run_seconds(w, day_length)
	h.assert_near(w.player.hunger, 0.0, 1e-9, "one day empties the belly")
	h.assert_near(w.player.health, 100.0 - 80.0 * 2.0, 0.3, "and the last 80 s cost 2 health a second")


func _winter_cold(h: TestHarness, w: World) -> void:
	# Winter's cold is 1.0 and the drain 0.5 a second by day; the night adds
	# night_scale (0.6) of itself; a worn cloak halves what is left.
	_reset(w, "winter")
	_run_seconds(w, 10.0)
	h.assert_near(w.player.warmth, 95.0, 0.01, "winter days cost 0.5 warmth a second")

	_reset(w, "winter")
	w.night = 1.0
	_run_seconds(w, 10.0)
	h.assert_near(w.player.warmth, 92.0, 0.01, "deep winter night costs 0.8 a second")

	_reset(w, "winter")
	Inventory.inv_add(w, "grass_cloak", 1)
	_run_seconds(w, 10.0)
	h.assert_near(w.player.warmth, 95.0, 0.01, "a cloak in the pack does nothing for the cold")
	_reset(w, "winter")
	Inventory.inv_add(w, "grass_cloak", 1)
	Inventory.equip(w, 0)
	_run_seconds(w, 10.0)
	h.assert_near(w.player.warmth, 97.5, 0.01, "a worn cloak halves the day drain")

	_reset(w, "winter")
	w.torch = {"remaining": 60.0, "radius": 3.5}
	_run_seconds(w, 10.0)
	h.assert_near(w.player.warmth, 96.5, 0.01, "a lit torch scales the drain by 0.7")

	_reset(w, "winter")
	w.warm = {"remaining": 120.0}
	_run_seconds(w, 10.0)
	h.assert_near(w.player.warmth, 100.0, 1e-9, "a warm stone stops the cold dead")

	_reset(w, "summer")
	_run_seconds(w, 10.0)
	h.assert_near(w.player.warmth, 100.0, 1e-9, "summer has no cold at all")


func _a_fire_gives_warmth_back(h: TestHarness, w: World) -> void:
	# campfire.heat_per_second is 8 within heat_radius_meters 3.5; the heat is
	# added, and the drain still applies.
	_reset(w, "winter")
	w.player.warmth = 50.0
	var fire := SimFixture.prop(w, "c1", "campfire", "unlit", 0.0, 2.0)
	fire["state"] = "lit"
	w.entities.append(fire)
	_run_seconds(w, 1.0)
	h.assert_near(w.player.warmth, 57.5, 0.02, "inside the heat radius warmth returns at 8 less the drain")

	# Step outside the radius and the fire stops counting.
	_reset(w, "winter")
	w.player.warmth = 50.0
	var far := SimFixture.prop(w, "c2", "campfire", "unlit", 0.0, 4.0)
	far["state"] = "lit"
	w.entities.append(far)
	_run_seconds(w, 1.0)
	h.assert_near(w.player.warmth, 49.5, 0.02, "4 m away is past the 3.5 m heat radius")


func _freezing_takes_health(h: TestHarness, w: World) -> void:
	_reset(w, "winter")
	w.player.warmth = 0.0
	_run_seconds(w, 5.0)
	h.assert_true(w.freezing, "an empty warmth in winter is freezing")
	h.assert_near(w.player.health, 90.0, 0.05, "the cold takes 2 health a second")
	h.assert_eq(w.message, "You are freezing. Find a fire.", "and the world says so once")


func _death_fires_once(h: TestHarness, w: World) -> void:
	_reset(w, "winter")
	w.player.warmth = 0.0
	w.player.health = 3.0
	_run_seconds(w, 10.0)
	h.assert_true(w.dead, "the cold finished the player")
	var deaths := SimFixture.events_of(w, "death")
	h.assert_eq(deaths.size(), 1, "death fires exactly once")
	h.assert_eq(str((deaths[0] as Dictionary)["cause"]), "cold", "and names the cold")
	h.assert_eq(w.message, "You froze. Press R to begin again.", "with the cold's line")
	_run_seconds(w, 10.0)
	h.assert_eq(SimFixture.events_of(w, "death").size(), 1, "and never again")
	# Starving names a different cause.
	_reset(w, "summer")
	w.player.hunger = 0.0
	w.player.health = 3.0
	_run_seconds(w, 10.0)
	h.assert_true(w.dead, "starvation finished the player")
	var starved := SimFixture.events_of(w, "death")
	h.assert_eq(str((starved[0] as Dictionary)["cause"]), "hunger", "and names the hunger")
	h.assert_eq(w.message, "You starved. Press R to begin again.", "with the hunger's line")
