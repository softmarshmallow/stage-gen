extends RefCounted

func run(h: TestHarness) -> void:
	var options := BellweatherOptions.parse(PackedStringArray(["--run=/prepared/", "--weather=storm"]))
	h.assert_eq(options.run, "/prepared", "run directory normalization")
	h.assert_eq(Array(options.unknown), ["--weather"], "survival weather is not a platformer option")
	h.done()
