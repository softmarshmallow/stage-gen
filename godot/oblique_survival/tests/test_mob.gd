extends RefCounted

## The grub hound: aggro, the approach, the blow at the end of the swing, and
## the wander when nothing is near.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_mob: could not open %s" % TestHarness.RUN_DIR)
		return
	_approaches_and_hits(h, w)
	_invulnerability_spaces_the_blows(h, w)
	_out_of_aggro_it_wanders(h, w)


func _stage(w: World, x: float, z: float) -> Dictionary:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	w.player.health = 100.0
	w.player.hunger = 100.0
	w.player.warmth = 100.0
	w.player.invulnerable = 0.0
	w.player.busy = null
	w.player.approach = null
	w.dead = false
	SimFixture.force_season(w, "summer")
	var hound := SimFixture.mob(w, "m1", "grub_hound", x, z)
	w.entities.append(hound)
	return hound


func _approaches_and_hits(h: TestHarness, w: World) -> void:
	# aggro_radius_meters 6, speed 2.6, attack_range 1 plus both footprints
	# (0.34 + 0.476) = 1.816 m, attack strip 4 frames at 12 fps = 0.3333 s.
	var hound := _stage(w, 3.0, 0.0)
	var rules: Dictionary = (w.manifest["gameplay"] as Dictionary)["mob"]
	h.assert_near(float(rules["aggro_radius_meters"]), 6.0, 1e-9, "the hound notices at 6 m")
	h.assert_near(float(rules["attack_damage"]), 10.0, 1e-9, "and bites for 10")
	var start := float(hound["x"])
	for i in 12:
		Sim.step(w, SimFixture.STEP)
	h.assert_true(float(hound["x"]) < start - 0.3, "a hound inside the aggro radius closes on the player")
	h.assert_eq(str(hound["state"]), "walk", "walking while it comes")
	# It closes in about 0.46 s and swings for 0.33 s; the blow resolves at
	# the end of the swing.
	var bit := false
	for i in 78:
		Sim.step(w, SimFixture.STEP)
		if w.player.health < 100.0 and not bit:
			bit = true
			h.assert_near(w.player.health, 90.0, 1e-9, "the bite costs exactly the authored damage")
			h.assert_near(w.player.invulnerable, 0.7 - SimFixture.STEP, 1e-6,
				"and opens the i-frames")
			h.assert_eq(str(hound["state"]), "idle", "the hound drops out of its swing")
	h.assert_true(bit, "the hound landed a bite inside 1.5 s")
	# The 1.5 s cooldown holds the second bite off until about 1.95 s.
	var hurt := SimFixture.events_of(w, "hurt")
	h.assert_eq(hurt.size(), 1, "one hurt event was raised")
	h.assert_near(w.player.health, 90.0, 1e-9, "and only one")
	h.assert_true(float(hound["cooldown"]) > 0.0, "the hound is on its cooldown")


func _invulnerability_spaces_the_blows(h: TestHarness, w: World) -> void:
	# The blow resolves at the end of the swing, and only when the i-frames
	# have run out; a second bite inside 0.7 s is wasted.
	var hound := _stage(w, 1.5, 0.0)
	w.player.invulnerable = 5.0
	for i in 60:
		Sim.step(w, SimFixture.STEP)
	h.assert_near(w.player.health, 100.0, 1e-9, "a bite inside the i-frames does nothing")
	h.assert_eq(SimFixture.events_of(w, "hurt").size(), 0, "and raises nothing")
	h.assert_true(str(hound["state"]) != "", "the hound still has a state")


func _out_of_aggro_it_wanders(h: TestHarness, w: World) -> void:
	# Past the aggro radius the hound orbits home at 0.35 of its speed.
	var hound := _stage(w, 20.0, 20.0)
	for i in 60:
		Sim.step(w, SimFixture.STEP)
	h.assert_near(w.player.health, 100.0, 1e-9, "a distant hound does nothing to the player")
	h.assert_true(str(hound["state"]) == "walk" or str(hound["state"]) == "idle",
		"it walks or stands, but never attacks")
	var dx := float(hound["x"]) - float(hound["home_x"])
	var dz := float(hound["z"]) - float(hound["home_z"])
	h.assert_true(sqrt(dx * dx + dz * dz) <= 4.0 + 1e-6,
		"and it stays inside its wander radius of home")
