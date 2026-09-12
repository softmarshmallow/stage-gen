extends RefCounted

func run(h: TestHarness) -> void:
	var options := GrainOptions.parse(PackedStringArray([
		"--run=/case/", "--scenario", "arrival", "--beat=office", "--runs=/prepared", "--weather=rain"
	]))
	h.assert_eq(options.run, "/case", "run directory normalization")
	h.assert_eq(options.scenario, "arrival", "dialogue selection")
	h.assert_eq(options.beat, "office", "case beat option")
	h.assert_eq(options.runs, "/prepared", "case member root")
	h.assert_eq(Array(options.unknown), ["--weather"], "survival weather is not a case option")
	h.done()
