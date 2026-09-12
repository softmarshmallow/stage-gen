extends SceneTree

const Harness = preload("harness.gd")
const SUITES = [preload("test_pixels.gd"), preload("test_contract.gd")]

func _initialize() -> void:
	var count := 0
	var failures: Array[String] = []
	for suite in SUITES:
		var h := Harness.new()
		suite.new().run(h)
		if not h.finished or h.checks == 0:
			failures.append("suite did not complete: " + suite.resource_path)
		count += h.checks
		failures.append_array(h.failures)
	if not failures.is_empty():
		for failure in failures:
			printerr(failure)
		quit(1)
		return
	print("sideview_rendering: %d checks passed" % count)
	quit(0)
