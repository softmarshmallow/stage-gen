class_name TestHarness
extends RefCounted

## Assertions and the shared run package. Every `tests/test_*.gd` defines
## `func run(h: TestHarness) -> void` and reports through this.

## The run every test reads when the command line names none. A real run, not a
## fixture: the port is only worth anything if it loads what the pipeline
## actually emits. `out/ember-hollow-v1` is the promoted run — manifest kind
## `oblique-survival-manifest-v1` over a package byte-identical to the spike's
## `full-v66`, so every count in these tests is the same number.
const DEFAULT_RUN_DIR := "/Users/universe/Documents/shared/stage-gen/out/ember-hollow-v1"

## The run this suite is pointed at: `DEFAULT_RUN_DIR`, or the directory after
## `-- --run` on the command line.
static var RUN_DIR: String = DEFAULT_RUN_DIR

static func _static_init() -> void:
	var argv := OS.get_cmdline_user_args()
	for i in range(argv.size()):
		if argv[i] == "--run" and i + 1 < argv.size():
			RUN_DIR = argv[i + 1].rstrip("/")
			return
		if argv[i].begins_with("--run="):
			RUN_DIR = argv[i].substr(6).rstrip("/")
			return

var failures: PackedStringArray = PackedStringArray()
var checks: int = 0
## The test file currently running, for the failure lines.
var current: String = ""

static var _package: RunPackage = null

## The shared run package, opened once for the whole suite.
func package() -> RunPackage:
	if _package == null:
		_package = RunPackage.open(RUN_DIR)
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

func fail(message: String) -> void:
	failures.append("%s: %s" % [current, message])

func note(message: String) -> void:
	print("    note: %s" % message)
