extends RefCounted

func run(h: TestHarness) -> void:
	var options := RunnerOptions.parse(PackedStringArray(["--run", "/prepared/", "--seed=-9", "--season=winter"]))
	h.assert_eq(options.run, "/prepared", "run directory normalization")
	h.assert_eq(options.seed_value, -9, "runner seed override")
	h.assert_eq(Array(options.unknown), ["--season"], "survival season is not a runner option")
	h.done()
