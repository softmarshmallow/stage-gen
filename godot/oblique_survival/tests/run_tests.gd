extends SceneTree

## The headless suite:
##
##   Godot --headless --path godot/oblique_survival -s res://tests/run_tests.gd
##
## Every `tests/test_*.gd` is instantiated and its `run(h)` called. Exit code 1
## on any failure.

const TESTS_DIR := "res://tests"

## The suite runs on the first frame, not in `_init` or `_initialize`: a test
## that stands a camera under the root to unproject a point needs the root
## window live in the tree, and it is not until the loop's first iteration
## (under `_initialize` the root is still outside the tree at 100 by 100).
var _ran := false

func _process(_delta: float) -> bool:
	if _ran:
		return false
	_ran = true
	_run_all()
	return false

func _run_all() -> void:
	var harness := TestHarness.new()
	harness.tree = self
	var files := _test_files()
	if files.is_empty():
		push_error("no tests found under %s" % TESTS_DIR)
		quit(1)
		return
	var started := Time.get_ticks_msec()
	for file in files:
		harness.current = file.get_file()
		var script: Variant = load(file)
		# A script that failed to parse still loads, but cannot be instanced.
		if not (script is GDScript) or not (script as GDScript).can_instantiate():
			print("%s\n  FAILED (did not compile)" % harness.current)
			harness.fail("the test script did not compile")
			continue
		var test: Variant = (script as GDScript).new()
		if test == null or not test.has_method("run"):
			print("%s\n  FAILED (no run(h))" % harness.current)
			harness.fail("no run(h) in the test script")
			continue
		harness.current = file.get_file()
		var before := harness.failures.size()
		var checks := harness.checks
		var at := Time.get_ticks_msec()
		print("%s" % harness.current)
		test.run(harness)
		# A script that failed to compile can still be instanced and called,
		# doing nothing at all; a file that asserts nothing has not run.
		if harness.checks == checks:
			harness.fail("ran no checks (did the script compile?)")
		var passed := harness.failures.size() == before
		print("  %s (%d ms)" % ["ok" if passed else "FAILED", Time.get_ticks_msec() - at])
	var seconds := float(Time.get_ticks_msec() - started) / 1000.0
	print("")
	if harness.failures.is_empty():
		print("%d checks in %d files passed (%.1f s)" % [harness.checks, files.size(), seconds])
		quit(0)
		return
	print("%d of %d checks failed (%.1f s):" % [harness.failures.size(), harness.checks, seconds])
	for failure in harness.failures:
		print("  %s" % failure)
	quit(1)

func _test_files() -> PackedStringArray:
	var found := PackedStringArray()
	var dir := DirAccess.open(TESTS_DIR)
	if dir == null:
		return found
	for name in dir.get_files():
		# Godot hands out `.remap` names in an exported build.
		var script_name := name.trim_suffix(".remap")
		if script_name.begins_with("test_") and script_name.ends_with(".gd"):
			found.append("%s/%s" % [TESTS_DIR, script_name])
	found.sort()
	return found
