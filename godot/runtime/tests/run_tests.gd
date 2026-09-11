extends SceneTree

## The headless suite:
##
##   Godot --headless --path godot/runtime -s res://tests/run_tests.gd -- [--only <file>]
##
## Every `tests/test_*.gd` is instantiated and its `run(h)` called. Exit code 1
## on any failure.
##
## `--only` runs one file and nothing else. That is what makes a *supervisor*
## possible: `tools/run_suite.py` spawns one of these per file with a timeout, so
## a file that hangs is named and killed rather than taking the whole suite down
## with it, and a file that dies hard costs its own results and no one else's.
## Without `--only` this behaves exactly as it always has.

const TESTS_DIR := "res://tests"

## One file's name (`test_room.gd`) when a supervisor is running them one at a
## time, empty for the whole directory.
static var ONLY: String = ""

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

func _initialize() -> void:
	var argv := OS.get_cmdline_user_args()
	for index in argv.size():
		if argv[index] == "--only" and index + 1 < argv.size():
			ONLY = argv[index + 1].get_file()
		elif String(argv[index]).begins_with("--only="):
			ONLY = String(argv[index]).substr(7).get_file()


func _run_all() -> void:
	var harness := TestHarness.new()
	harness.tree = self
	var files := _test_files()
	if files.is_empty():
		# A supervisor that names a file this build does not carry is a
		# supervisor out of step with the tree, and saying nothing would let it
		# report a green suite that ran nothing.
		push_error(
			"no tests found under %s" % TESTS_DIR
			if ONLY.is_empty()
			else "no test named %s under %s" % [ONLY, TESTS_DIR]
		)
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
		harness.finished = false
		test.run(harness)
		# A runtime error inside a test aborts its `run` and returns here with
		# nothing to say, so every check it reached still passed and the file
		# printed `ok`. The last line of a `run` is the only thing that can prove
		# it got there.
		if not harness.finished:
			harness.fail("stopped before the end of run() — look for a SCRIPT ERROR above")
		# A script that failed to compile can still be instanced and called,
		# doing nothing at all; a file that asserts nothing has not run.
		if harness.checks == checks:
			harness.fail("ran no checks (did the script compile?)")
		var passed := harness.failures.size() == before
		print("  %s (%d ms)" % ["ok" if passed else "FAILED", Time.get_ticks_msec() - at])
	var seconds := float(Time.get_ticks_msec() - started) / 1000.0
	print("")
	# What the run this suite was pointed at could not be asked. Named rather
	# than counted: a tier that silently empties reads as a green gate.
	if not TestHarness.SKIPPED.is_empty():
		print("%d pinned to a real run, not read here:" % TestHarness.SKIPPED.size())
		for entry in TestHarness.SKIPPED:
			print("  %s" % entry)
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
		if not (script_name.begins_with("test_") and script_name.ends_with(".gd")):
			continue
		if not ONLY.is_empty() and script_name != ONLY:
			continue
		found.append("%s/%s" % [TESTS_DIR, script_name])
	found.sort()
	return found
