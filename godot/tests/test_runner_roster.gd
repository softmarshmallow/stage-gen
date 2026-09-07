extends RefCounted

## The runner genre: the order its declarations derive, and the arithmetic that
## order carries.
##
## The order below is the browser's, asserted in `game.test.ts:44-73` and copied
## here verbatim. It is not the order the roster registers in — the moment system
## is registered third and runs fifth, the difficulty system is registered fourth
## and runs third — and that is the point of asserting it: a declaration edit
## that reorders a frame is a visible diff in this file rather than a replay that
## drifts three commits later.

## The frame, as `KernelSealer` derives it from sixteen declarations.
const SEALED_ORDER: Array[String] = [
	"clock/step",
	"runner/intent",
	"runner/difficulty",
	"runner/avatar",
	"fx/moment",
	"runner/encounter",
	"runner/segments",
	"runner/obstacles",
	"runner/vitals",
	"score/run",
	"session/run",
	"runner/camera",
	"runner/parallax",
	"runner/hud",
	"runner/audio",
	"runner/dust",
]


func run(h: TestHarness) -> void:
	_order(h)
	_manifest(h)
	_arithmetic(h)


func _order(h: TestHarness) -> void:
	var sealed: Variant = RunnerRoster.seal()
	h.assert_true(not KernelRefusal.is_refusal(sealed), "the runner's roster seals")
	if KernelRefusal.is_refusal(sealed):
		return
	var order := (sealed as KernelSealed).order
	h.assert_eq(order.size(), SEALED_ORDER.size(), "sixteen systems seal into sixteen")
	for index in mini(order.size(), SEALED_ORDER.size()):
		h.assert_eq(
			order[index],
			SEALED_ORDER[index],
			"the derived frame runs %s at %d" % [SEALED_ORDER[index], index]
		)


func _manifest(h: TestHarness) -> void:
	var manifest: Variant = _fixture()
	var config: Variant = RunnerContract.parse(manifest)
	h.assert_true(not KernelRefusal.is_refusal(config), "the fixture manifest parses")
	if KernelRefusal.is_refusal(config):
		return
	var parsed: Dictionary = config
	h.assert_eq(int(parsed["rows"]), 8, "the fixture is eight rows deep")
	h.assert_eq(int(parsed["walkSurfaceRow"]), 5, "and walks on row five")
	# 1280 / 64 = 20 columns on screen, plus the eight-column margin.
	h.assert_eq(int(parsed["viewportColumns"]), 20, "twenty columns fit the view")
	h.assert_eq(int(parsed["streamAheadColumns"]), 28, "and eight more are built ahead")
	h.assert_eq(float(parsed["avatarScreenX"]), 320.0, "the avatar stands a quarter in")

	# A document of another kind is refused by name rather than half-read.
	var wrong: Dictionary = (manifest as Dictionary).duplicate(true)
	wrong["kind"] = "sideview-platformer-runtime-v1"
	h.assert_true(
		KernelRefusal.is_refusal(RunnerContract.parse(wrong)),
		"a manifest of another kind is refused"
	)
	var old: Dictionary = (manifest as Dictionary).duplicate(true)
	old["schema_version"] = 12
	h.assert_true(
		KernelRefusal.is_refusal(RunnerContract.parse(old)),
		"and so is one at another schema version"
	)
	# A block at a version this build does not read is the other identity, and
	# it is refused even though the document's kind is right.
	var stale: Dictionary = (manifest as Dictionary).duplicate(true)
	(stale["blocks"] as Dictionary)["segments"] = "runner-segments-block-v0"
	var refusal: Variant = RunnerContract.parse(stale)
	h.assert_true(KernelRefusal.is_refusal(refusal), "a stale block is refused")
	if KernelRefusal.is_refusal(refusal):
		h.assert_eq(
			(refusal as KernelRefusal).path, "segments", "and the refusal names the block"
		)


func _arithmetic(h: TestHarness) -> void:
	var config: Variant = RunnerContract.parse(_fixture())
	if KernelRefusal.is_refusal(config):
		return
	var parsed: Dictionary = config
	var arc := RunnerAvatarSystem.jump_arc(parsed)
	# Derived from the admission, never authored: the level that was drawn and
	# the physics that flies it read the same two numbers.
	h.assert_true(float(arc["initialSpeedPerSecond"]) > 0.0, "the arc has a launch speed")
	h.assert_true(float(arc["gravityPerSecondSquared"]) > 0.0, "and a gravity")

	# The boss hovers centred in the slack between its height and the floor.
	h.assert_near(
		RunnerEncounterState.hover_feet_row(2.0, 5.0), 3.5, 1e-12, "a short boss hovers high"
	)
	h.assert_near(
		RunnerEncounterState.hover_feet_row(5.0, 5.0), 5.0, 1e-12, "a boss its full height stands"
	)
	# Thrust: one acceleration, two asymmetric caps.
	var thrust := {
		"maxClimbRowsPerSecond": 9.0,
		"maxFallRowsPerSecond": 10.0,
		"climbAccelerationRowsPerSecondSquared": 24.0,
	}
	h.assert_near(
		RunnerAvatarSystem.thrust_velocity(0.0, true, 1.0, thrust),
		-9.0,
		1e-12,
		"a held climb caps at nine"
	)
	h.assert_near(
		RunnerAvatarSystem.thrust_velocity(0.0, false, 1.0, thrust),
		10.0,
		1e-12,
		"and a release falls to ten"
	)

	# A hazard's box is inset from its cell, so a body brushing the column edge
	# does not collide with something drawn well inside it.
	var hazard := {"worldColumn": 6, "anchor": "surface", "clearanceRows": null}
	var box := RunnerObstaclesSystem.hazard_box(hazard, 5, 1.0, parsed)
	h.assert_near(float(box["bottom"]), 5.0, 1e-12, "a surface hazard sits on the floor")
	h.assert_true(float(box["left"]) > 6.0, "and is inset from its own column")

	var overhead := {"worldColumn": 6, "anchor": "overhead", "clearanceRows": 2.0}
	var hanging := RunnerObstaclesSystem.hazard_box(overhead, 5, 1.0, parsed)
	h.assert_near(
		float(hanging["bottom"]), 3.0, 1e-12, "an overhead hazard hangs its clearance up"
	)

	h.assert_eq(
		RunnerObstaclesSystem.pickup_key({"worldColumn": 6, "row": 2, "itemId": "sunleaf_token"}),
		"6:2:sunleaf_token",
		"a pickup's key is its place and its name"
	)


func _fixture() -> Variant:
	var path := "res://tests/fixtures/sideview_runner/manifest.json"
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return null
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed
