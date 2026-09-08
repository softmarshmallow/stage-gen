class_name TestHarness
extends RefCounted

## Assertions and the shared run package. Every `tests/test_*.gd` defines
## `func run(h: TestHarness) -> void` and reports through this.

## The run every test reads when the command line names none. A real run, not a
## fixture: the port is only worth anything if it loads what the pipeline
## actually emits. `out/ember-hollow-v13` is the current run — manifest kind
## `oblique-survival-manifest-v3`, the forage the only sheet of ground pieces
## and every cell of it sized (decision 0060), and the game shell drawn; the
## counts pinned in these tests are that run's.
##
## Found from the project rather than from a path typed on one machine:
## `res://` globalises to the project directory, and the repository's `out/` is
## one level up from it.
const DEFAULT_RUN_REF := "../out/ember-hollow-v13"

## The run this suite is pointed at: the default above, or the directory after
## `-- --run` on the command line.
static var RUN_DIR: String = ""

## The scene tree the suite runs in, for a test that must stand a node in a
## viewport (a camera cannot unproject outside one). Set by the runner.
var tree: SceneTree = null

static func _static_init() -> void:
	var argv := OS.get_cmdline_user_args()
	for i in range(argv.size()):
		if argv[i] == "--run" and i + 1 < argv.size():
			RUN_DIR = argv[i + 1].rstrip("/")
			return
		if argv[i].begins_with("--run="):
			RUN_DIR = argv[i].substr(6).rstrip("/")
			return
	RUN_DIR = ProjectSettings.globalize_path("res://").path_join(DEFAULT_RUN_REF).simplify_path()

var failures: PackedStringArray = PackedStringArray()
var checks: int = 0

## Whether the file being run reached the end of its own `run`.
##
## A GDScript runtime error — a null where a String was expected, an index off
## the end of an array — aborts the function it happens in and returns to the
## caller with nothing to say. The suite printed `ok` for a file that had
## crashed halfway through, because every check it *had* reached still passed.
## So each file says when it is finished, and a file that never says so fails.
var finished: bool = false
## The test file currently running, for the failure lines.
var current: String = ""

static var _package: HostRunDir = null

## The shared run package, opened once for the whole suite.
func package() -> HostRunDir:
	if _package == null:
		_package = HostRunDir.open(RUN_DIR, Callable(SurvivalDocument, "check_manifest"), SurvivalDocument.LAYOUT_REF)
	return _package

func assert_true(condition: bool, message: String) -> bool:
	checks += 1
	if not condition:
		fail(message)
		return false
	return true

func assert_false(condition: bool, message: String) -> bool:
	return assert_true(not condition, message)

func assert_eq(actual: Variant, expected: Variant, message: String) -> bool:
	checks += 1
	if actual != expected:
		fail("%s (expected %s, got %s)" % [message, expected, actual])
		return false
	return true

func assert_near(actual: float, expected: float, eps: float, message: String) -> bool:
	checks += 1
	if not is_finite(actual) or absf(actual - expected) > eps:
		fail("%s (expected %.9f +/- %.9f, got %.9f)" % [message, expected, eps, actual])
		return false
	return true

## Called as the last statement of every `run`. The runner reads it, not the test.
func done() -> void:
	finished = true


func fail(message: String) -> void:
	failures.append("%s: %s" % [current, message])

func note(message: String) -> void:
	print("    note: %s" % message)
