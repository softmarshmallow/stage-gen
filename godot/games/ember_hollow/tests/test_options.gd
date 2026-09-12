extends RefCounted

func run(h: TestHarness) -> void:
	var options := EmberOptions.parse(PackedStringArray([
		"--run=/world/", "--weather=storm", "--time=night", "--season=winter", "--seed=17",
		"--fullscreen=false", "--night-floor=2", "--scenario=arrival"
	]))
	h.assert_eq(options.world_options(), {"mode": "play", "time": "night", "season": "winter", "weather": "storm"}, "Ember owns world option composition")
	h.assert_eq(options.run, "/world", "run directory normalization")
	h.assert_eq(options.seed_value, 17, "world seed override")
	h.assert_false(options.fullscreen, "explicit fullscreen false")
	h.assert_near(options.night_floor, 1.0, 0.00001, "night-floor clamping")
	h.assert_eq(Array(options.unknown), ["--scenario"], "dialogue selection is not a survival option")
	h.done()
