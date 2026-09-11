extends SceneTree

## Offline public-contract checks for first-person eye transitions.
## Run: Godot --headless --path presentation-playground --script res://qa/eye_transition_checks.gd
const CONTROLLER_PATH := "res://addons/game_presentation/transitions/eye_transition.gd"
const EPSILON := 0.00001
const SETTINGS := {"opening_seconds": 2.2, "closing_seconds": 0.4, "closed_hold_seconds": 0.18}
var _controller_script: Script
var _errors: Array[String] = []
var _observations: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_controller_script = load(CONTROLLER_PATH)
	if _controller_script == null or not _controller_script.can_instantiate():
		printerr("FAIL Eye Transition: controller must load and instantiate.")
		quit(1)
		return
	_endpoints_and_motion()
	_blink_and_elapsed_time()
	_waking_opening()
	_legacy_snapshots()
	_lifecycle_and_isolation()
	_snapshot_continuation()
	_rejected_input_is_atomic()
	if _errors.is_empty():
		for observation: String in _observations:
			print("PASS Eye Transition: " + observation)
	else:
		for issue: String in _errors:
			printerr("FAIL Eye Transition: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _make(settings: Dictionary = {}) -> RefCounted:
	var controller: RefCounted = _controller_script.new()
	var errors: Array = controller.call("configure", settings)
	_expect(errors.is_empty(), "Valid settings must configure: " + str(settings) + "; " + str(errors))
	return controller


func _start(controller: RefCounted, mode: String, settings: Dictionary = {}) -> void:
	_expect((controller.call("start", mode, settings) as Array).is_empty(), "A valid " + mode + " request must start.")


func _sample_equal(first: Dictionary, second: Dictionary) -> bool:
	for key: String in ["openness", "progress", "elapsed", "total_seconds"]:
		if not first.has(key) or not second.has(key) or absf(float(first[key]) - float(second[key])) > EPSILON:
			return false
	for key: String in ["phase", "active", "reached_closed"]:
		if first.get(key) != second.get(key):
			return false
	return true


func _bounded(sample: Dictionary) -> bool:
	for key: String in ["openness", "progress", "elapsed", "total_seconds"]:
		if not (sample.get(key) is int or sample.get(key) is float) or not is_finite(float(sample[key])):
			return false
	return float(sample["openness"]) >= 0.0 and float(sample["openness"]) <= 1.0 and float(sample["progress"]) >= 0.0 and float(sample["progress"]) <= 1.0 and float(sample["elapsed"]) >= 0.0 and float(sample["elapsed"]) <= float(sample["total_seconds"]) and sample.get("active") is bool and sample.get("reached_closed") is bool


func _endpoints_and_motion() -> void:
	for mode: String in ["eye_opening", "eye_closing"]:
		var controller := _make()
		_start(controller, mode)
		var opening := mode == "eye_opening"
		var duration: float = SETTINGS["opening_seconds" if opening else "closing_seconds"]
		var beginning: Dictionary = controller.call("sample")
		_expect(is_equal_approx(float(beginning["openness"]), 0.0 if opening else 1.0), mode + " must start at the appropriate mask endpoint.")
		_expect(bool(beginning["active"]) and bool(controller.call("is_active")) and is_zero_approx(float(beginning["progress"])), mode + " must begin active at zero progress.")
		var previous: float = beginning["openness"]
		var monotonic := true
		var bounded := true
		for index in 400:
			controller.call("advance", duration / 400.0)
			var sample: Dictionary = controller.call("sample")
			bounded = bounded and _bounded(sample)
			var current: float = sample["openness"]
			monotonic = monotonic and (current >= previous - EPSILON if opening else current <= previous + EPSILON)
			previous = current
		controller.call("advance", EPSILON)
		var endpoint: Dictionary = controller.call("sample")
		_expect(monotonic and bounded, mode + " must remain finite, bounded, and monotonic throughout its motion.")
		_expect(is_equal_approx(float(endpoint["openness"]), 1.0 if opening else 0.0), mode + " must reach its exact visible endpoint.")
		_expect(not bool(endpoint["active"]) and not bool(controller.call("is_active")) and is_equal_approx(float(endpoint["progress"]), 1.0), mode + " must finish at full progress.")
		_expect(endpoint["phase"] == ("open" if opening else "closed") and bool(endpoint["reached_closed"]), mode + " must report its held phase and closure history.")
		controller.call("advance", 99999.0)
		_expect(_sample_equal(endpoint, controller.call("sample")), mode + " must hold its endpoint without time or mask drift.")
		_start(controller, mode)
		controller.call("advance", duration * 0.001)
		var near_start: float = (controller.call("sample") as Dictionary)["openness"]
		controller.call("advance", duration * 0.998)
		var near_end: float = (controller.call("sample") as Dictionary)["openness"]
		_expect(absf(near_start - float(beginning["openness"])) < 0.0001 and absf(near_end - float(endpoint["openness"])) < 0.0001, mode + " must ease gently into and out of the motion.")
	_observations.append("opening and closing ease monotonically between exact held endpoints")


func _blink_and_elapsed_time() -> void:
	var controller := _make()
	_start(controller, "blink")
	_expect(not bool((controller.call("sample") as Dictionary)["reached_closed"]), "A blink must not report closure before it has occurred.")
	controller.call("advance", 0.4)
	var closed: Dictionary = controller.call("sample")
	_expect(closed["phase"] == "closed" and is_zero_approx(float(closed["openness"])) and bool(closed["active"]) and bool(closed["reached_closed"]), "Blink must fully close before its hold and reopening.")
	controller.call("advance", 0.09)
	_expect(is_zero_approx(float((controller.call("sample") as Dictionary)["openness"])) and (controller.call("sample") as Dictionary)["phase"] == "closed", "The authored closed hold must remain completely masked.")
	controller.call("advance", 0.10)
	var reopening: Dictionary = controller.call("sample")
	_expect(reopening["phase"] == "opening" and float(reopening["openness"]) > 0.0 and bool(reopening["reached_closed"]), "Blink must reopen after its full closed hold and preserve closure history.")
	controller.call("advance", 1000000.0)
	var completed: Dictionary = controller.call("sample")
	_expect(completed["phase"] == "open" and is_equal_approx(float(completed["openness"]), 1.0) and not bool(completed["active"]), "Blink must end fully open.")
	var leap := _make()
	_start(leap, "blink")
	leap.call("advance", 1000000.0)
	_expect(_sample_equal(completed, leap.call("sample")) and bool((leap.call("sample") as Dictionary)["reached_closed"]), "A frame crossing the entire blink must still report that full closure occurred.")
	for hold: float in [0.0, 2.0]:
		for mode: String in ["eye_opening", "eye_closing", "blink"]:
			var whole := _make({"closed_hold_seconds": hold})
			var split := _make({"closed_hold_seconds": hold})
			_start(whole, mode)
			_start(split, mode)
			whole.call("advance", 0.75)
			for index in 48:
				split.call("advance", 0.015625)
			_expect(_sample_equal(whole.call("sample"), split.call("sample")), "Equivalent elapsed time must produce the same " + mode + " frame with hold " + str(hold) + ".")
			var snapshot: Dictionary = whole.call("get_state")
			for index in 100:
				whole.call("sample")
			_expect(snapshot == whole.call("get_state"), "Sampling must not consume closure history or advance time.")
	for opening: float in [0.1, 8.0]:
		for closing: float in [0.1, 4.0]:
			for hold: float in [0.0, 2.0]:
				var extremes := _make({"opening_seconds": opening, "closing_seconds": closing, "closed_hold_seconds": hold})
				_start(extremes, "blink")
				var valid := true
				for index in 401:
					valid = valid and _bounded(extremes.call("sample"))
					extremes.call("advance", (opening + closing + hold) / 400.0)
				_expect(valid, "Blink must stay finite and bounded for every combination of timing limits.")
	_observations.append("blink closure, closed hold, reopening, frame partitioning, and large-delta closure history")


func _lifecycle_and_isolation() -> void:
	var controller := _make()
	var companion := _make()
	var idle: Dictionary = companion.call("sample")
	var defaults: Dictionary = controller.call("get_settings")
	_start(controller, "eye_opening", {"opening_seconds": 4.0})
	controller.call("advance", 0.75)
	_expect(_sample_equal(idle, companion.call("sample")), "One transition must not affect another instance.")
	_expect(defaults == controller.call("get_settings"), "Per-cue overrides must not change configured defaults.")
	var active: Dictionary = controller.call("sample")
	_expect((controller.call("configure", {"opening_seconds": 0.5}) as Array).is_empty(), "Defaults may be configured for the next cue while another is active.")
	_expect(_sample_equal(active, controller.call("sample")), "Next-cue configuration must not alter the active transition.")
	controller.call("skip")
	_expect(is_equal_approx(float((controller.call("sample") as Dictionary)["total_seconds"]), 4.0), "Skip must use the active cue's own timing snapshot.")
	for mode: String in ["eye_opening", "eye_closing", "blink"]:
		_start(controller, mode)
		controller.call("advance", 0.05)
		controller.call("skip")
		var skipped: Dictionary = controller.call("sample")
		_expect(not bool(skipped["active"]) and is_equal_approx(float(skipped["openness"]), 0.0 if mode == "eye_closing" else 1.0), "Skipping " + mode + " must hold its appropriate final mask.")
		controller.call("skip")
		_expect(_sample_equal(skipped, controller.call("sample")), "Repeated skip must preserve the held endpoint.")
		_start(controller, mode)
		_expect(is_zero_approx(float((controller.call("sample") as Dictionary)["elapsed"])), "Replay must restart timing cleanly.")
	_start(controller, "eye_opening")
	_expect(is_equal_approx(float((controller.call("sample") as Dictionary)["total_seconds"]), 0.5), "New cues must use the updated default settings.")
	controller.call("clear")
	_expect(_sample_equal(idle, controller.call("sample")), "Clear must return to an unmasked idle state.")
	controller.call("skip")
	_expect(_sample_equal(idle, controller.call("sample")), "Skipping idle must not create a transition.")
	var exposed: Dictionary = controller.call("get_settings")
	exposed["opening_seconds"] = 8.0
	_expect(is_equal_approx(float((controller.call("get_settings") as Dictionary)["opening_seconds"]), 0.5), "Returned settings must not alias controller state.")
	_observations.append("isolated cues, stable active settings, skip, replay, reset, and immutable settings exposure")


func _snapshot_continuation() -> void:
	for elapsed: float in [0.0, 0.25, 0.45, 0.70, 5.0]:
		var original := _make({"opening_seconds": 1.7})
		_start(original, "blink", {"opening_seconds": 2.8})
		original.call("advance", elapsed)
		original.call("configure", {"opening_seconds": 0.7})
		var saved: Dictionary = original.call("get_state")
		var serialized: Variant = JSON.parse_string(JSON.stringify(saved))
		_expect(serialized is Dictionary, "Snapshots must survive JSON serialization.")
		var restored := _make()
		_expect((restored.call("restore", serialized) as Array).is_empty(), "Idle, closing, held, reopening, and completed snapshots must restore.")
		_expect(_sample_equal(original.call("sample"), restored.call("sample")), "Restore must reproduce the saved mask and closure history.")
		var matches := true
		for index in 80:
			original.call("advance", 0.0625)
			restored.call("advance", 0.0625)
			matches = matches and _sample_equal(original.call("sample"), restored.call("sample"))
		_expect(matches, "Restored transitions must continue identically through completion.")
		_start(restored, "eye_opening")
		_expect(is_equal_approx(float((restored.call("sample") as Dictionary)["total_seconds"]), 0.7), "Snapshots must preserve defaults separately from active cue overrides.")
		var exposed: Dictionary = original.call("get_state")
		var original_state: Dictionary = original.call("get_state")
		(exposed["defaults"] as Dictionary)["opening_seconds"] = 8.0
		(exposed["active_settings"] as Dictionary)["opening_seconds"] = 0.1
		_expect(original_state == original.call("get_state"), "Returned snapshots must not expose mutable internal dictionaries.")
		var received: Dictionary = original.call("get_state")
		_expect((restored.call("restore", received) as Array).is_empty(), "Valid caller-owned state must restore.")
		var received_state: Dictionary = restored.call("get_state")
		(received["defaults"] as Dictionary)["opening_seconds"] = 8.0
		(received["active_settings"] as Dictionary)["opening_seconds"] = 0.1
		_expect(received_state == restored.call("get_state"), "Restore must not retain aliases to its caller's state.")
	var cleared := _make()
	var idle_copy := _make()
	_expect((idle_copy.call("restore", JSON.parse_string(JSON.stringify(cleared.call("get_state")))) as Array).is_empty(), "A cleared controller must also provide a valid portable snapshot.")
	_expect(_sample_equal(cleared.call("sample"), idle_copy.call("sample")), "Cleared state must remain unmasked and inactive when restored.")
	_observations.append("JSON snapshot continuation across all blink phases and independent state ownership")


func _rejected_input_is_atomic() -> void:
	var controller := _make()
	_start(controller, "blink")
	controller.call("advance", 0.25)
	var before: Dictionary = controller.call("get_state")
	var invalid_settings: Array[Dictionary] = [
		{"opening_seconds": 0.09}, {"opening_seconds": 8.1}, {"opening_seconds": NAN},
		{"closing_seconds": 0.09}, {"closing_seconds": 4.1}, {"closing_seconds": INF},
		{"closed_hold_seconds": -0.1}, {"closed_hold_seconds": 2.1}, {"closed_hold_seconds": true},
		{"opening_seconds": "2.2"}, {"openingSeconds": 2.2},
		{"opening_seconds": 4.0, "closing_seconds": -1.0},
	]
	for settings: Dictionary in invalid_settings:
		_expect(not (controller.call("configure", settings) as Array).is_empty(), "Invalid configuration must be rejected: " + str(settings))
		_expect(before == controller.call("get_state"), "Rejected configuration must preserve defaults and active state.")
		_expect(not (controller.call("start", "eye_opening", settings) as Array).is_empty(), "Invalid cue overrides must be rejected: " + str(settings))
		_expect(before == controller.call("get_state"), "Rejected cue overrides must not restart a valid transition.")
	for mode: String in ["", "eyeOpening", "unknown", "character_blink"]:
		_expect(not (controller.call("start", mode) as Array).is_empty(), "Unsupported transition modes must be rejected.")
		_expect(before == controller.call("get_state"), "Rejected modes must preserve active state.")
	for delta: float in [-1.0, NAN, INF, -INF, 0.0]:
		controller.call("advance", delta)
		_expect(before == controller.call("get_state"), "Invalid and zero deltas must not advance or corrupt a transition.")
	var invalid_states: Array[Dictionary] = []
	for mutation: Dictionary in [
		{"version": 3}, {"version": true}, {"mode": "unknown"}, {"mode": ""},
		{"elapsed": -1.0}, {"elapsed": 999.0}, {"elapsed": INF}, {"elapsed": "0.25"},
		{"defaults": {"opening_seconds": 2.2}}, {"active_settings": {"opening_seconds": 2.2}},
		{"unexpected": 1},
	]:
		var malformed: Dictionary = before.duplicate(true)
		malformed.merge(mutation, true)
		invalid_states.append(malformed)
	for field: String in before:
		var missing: Dictionary = before.duplicate(true)
		missing.erase(field)
		invalid_states.append(missing)
	for state: Dictionary in invalid_states:
		_expect(not (controller.call("restore", state) as Array).is_empty(), "Malformed or inconsistent snapshots must be rejected: " + str(state))
		_expect(before == controller.call("get_state"), "Rejected snapshots must not partially mutate a valid running transition.")
	_observations.append("atomic rejection of invalid timing, cue modes, deltas, and portable snapshots")


func _waking_opening() -> void:
	var settings := {"peek_seconds": 0.22, "peek_openness": 0.42, "closing_seconds": 0.14, "closed_hold_seconds": 0.08, "opening_seconds": 2.2}
	var controller := _make(settings)
	_start(controller, "waking_opening")
	var first: Dictionary = controller.call("sample")
	_expect(first["phase"] == "peeking" and is_zero_approx(float(first["openness"])) and bool(first["active"]) and bool(first["reached_closed"]), "Waking starts fully closed and begins its partial peek.")
	_expect(is_equal_approx(float(first["total_seconds"]), 2.64), "Waking duration must add peek, closing, closed hold, and the independently authored final opening.")
	controller.call("advance", 0.11)
	var peek: Dictionary = controller.call("sample")
	_expect(float(peek["openness"]) > 0.0 and float(peek["openness"]) < 0.42, "The first peek must gradually reveal only its partial aperture.")
	controller.call("advance", 0.11)
	var peak: Dictionary = controller.call("sample")
	_expect(peak["phase"] == "closing" and is_equal_approx(float(peak["openness"]), 0.42), "Peek duration must reach the configured depth before reversing into closure.")
	controller.call("advance", 0.14)
	var closed: Dictionary = controller.call("sample")
	_expect(closed["phase"] == "closed" and is_zero_approx(float(closed["openness"])) and bool(closed["active"]), "Waking must close completely after its first peek.")
	controller.call("advance", 0.04)
	_expect((controller.call("sample") as Dictionary)["phase"] == "closed" and is_zero_approx(float((controller.call("sample") as Dictionary)["openness"])), "The waking closed hold must remain completely masked.")
	controller.call("advance", 0.04 + EPSILON)
	var reopening: Dictionary = controller.call("sample")
	_expect(reopening["phase"] == "opening" and float(reopening["openness"]) < 0.0001, "Final opening must begin anew from closed after the hold.")
	controller.call("advance", 1.1 - EPSILON)
	_expect(is_equal_approx(float((controller.call("sample") as Dictionary)["openness"]), 0.5), "The complete final opening duration must be preserved independently of the preliminary peek.")
	var paused: Dictionary = controller.call("get_state")
	for frame in 100:
		controller.call("sample")
	_expect(paused == controller.call("get_state"), "A host pause that withholds clock advancement must preserve the waking frame.")
	_expect((controller.call("configure", {"peek_seconds": 0.5, "opening_seconds": 4.0}) as Array).is_empty(), "Future waking defaults can be configured while a cue is held.")
	_expect(is_equal_approx(float((controller.call("sample") as Dictionary)["total_seconds"]), 2.64), "New defaults must not retime the active waking cue.")
	controller.call("skip")
	_expect((controller.call("sample") as Dictionary)["phase"] == "open" and is_equal_approx(float((controller.call("sample") as Dictionary)["openness"]), 1.0), "Skipping waking must end fully open.")
	_start(controller, "waking_opening")
	_expect(is_zero_approx(float((controller.call("sample") as Dictionary)["elapsed"])) and is_zero_approx(float((controller.call("sample") as Dictionary)["openness"])), "Waking replay must restart fully closed with no carried-over motion.")
	_expect(is_equal_approx(float((controller.call("sample") as Dictionary)["total_seconds"]), 4.72), "Replay must use the newly configured peek and final-opening times.")
	for elapsed: float in [0.11, 0.29, 0.4, 1.54, 20.0]:
		var source := _make(settings)
		_start(source, "waking_opening")
		source.call("advance", elapsed)
		var receiver := _make()
		var state: Dictionary = JSON.parse_string(JSON.stringify(source.call("get_state")))
		_expect(int(state["version"]) == 2 and (receiver.call("restore", state) as Array).is_empty(), "Every waking phase must restore from a complete version-two JSON snapshot.")
		_expect(_sample_equal(source.call("sample"), receiver.call("sample")), "Waking snapshot restoration must reproduce the exact saved phase and aperture.")
		var identical := true
		for frame in 60:
			source.call("advance", 0.0625)
			receiver.call("advance", 0.0625)
			identical = identical and _sample_equal(source.call("sample"), receiver.call("sample"))
		_expect(identical, "Restored waking transitions must continue identically through final opening.")
	var whole := _make(settings)
	var split := _make(settings)
	_start(whole, "waking_opening")
	_start(split, "waking_opening")
	whole.call("advance", 0.75)
	for frame in 48:
		split.call("advance", 0.015625)
	_expect(_sample_equal(whole.call("sample"), split.call("sample")), "Frame partitioning across the complete preliminary blink must preserve waking timing.")
	whole.call("advance", 10000.0)
	_expect(not bool(whole.call("is_active")) and (whole.call("sample") as Dictionary)["phase"] == "open", "One large frame must complete every waking phase without getting stuck.")
	for peek_seconds: float in [0.05, 2.0]:
		for peek_openness: float in [0.05, 1.0]:
			for hold: float in [0.0, 2.0]:
				var edge := _make({"peek_seconds": peek_seconds, "peek_openness": peek_openness, "closed_hold_seconds": hold})
				_start(edge, "waking_opening")
				var total: float = (edge.call("sample") as Dictionary)["total_seconds"]
				var bounded := true
				for frame in 501:
					bounded = bounded and _bounded(edge.call("sample"))
					edge.call("advance", total / 500.0)
				_expect(bounded, "Waking output must remain finite and bounded at all peek and hold limits.")
	var before: Dictionary = controller.call("get_state")
	for invalid: Dictionary in [{"peek_seconds": 0.049}, {"peek_seconds": 2.01}, {"peek_seconds": INF}, {"peek_seconds": true}, {"peek_openness": 0.049}, {"peek_openness": 1.01}, {"peek_openness": NAN}, {"peek_openness": "0.42"}, {"peek_seconds": 0.5, "peek_openness": -1.0}]:
		_expect(not (controller.call("configure", invalid) as Array).is_empty() and before == controller.call("get_state"), "Invalid peek configuration must be refused atomically.")
		_expect(not (controller.call("start", "waking_opening", invalid) as Array).is_empty() and before == controller.call("get_state"), "Invalid waking overrides must preserve the current cue.")
	for field: String in ["defaults", "active_settings"]:
		var missing := before.duplicate(true)
		(missing[field] as Dictionary).erase("peek_seconds")
		_expect(not (controller.call("restore", missing) as Array).is_empty() and before == controller.call("get_state"), "Version-two snapshots must require every peek field and reject incomplete state atomically.")
	_observations.append("waking partial peek, reclosure, held darkness, independent final opening, replay, portable continuation, and valid limits")


func _legacy_snapshots() -> void:
	for mode: String in ["", "eye_opening", "eye_closing", "blink"]:
		var current := _make()
		if not mode.is_empty():
			_start(current, mode)
			current.call("advance", 0.2)
		var old := {"version": 1, "mode": mode, "defaults": SETTINGS.duplicate(), "active_settings": SETTINGS.duplicate(), "elapsed": 0.0 if mode.is_empty() else 0.2}
		var imported := _make()
		_expect((imported.call("restore", JSON.parse_string(JSON.stringify(old))) as Array).is_empty(), "Original three-setting version-one snapshots must remain readable for " + mode + ".")
		_expect(_sample_equal(current.call("sample"), imported.call("sample")), "Legacy import must preserve old modes' exact appearance and timing.")
		var upgraded: Dictionary = imported.call("get_state")
		_expect(int(upgraded["version"]) == 2 and is_equal_approx(float(upgraded["defaults"]["peek_seconds"]), 0.22) and is_equal_approx(float(upgraded["active_settings"]["peek_openness"]), 0.42), "Legacy import must explicitly upgrade to complete version-two settings with the new peek defaults.")
		var before := upgraded.duplicate(true)
		old["mode"] = "waking_opening"
		_expect(not (imported.call("restore", old) as Array).is_empty() and before == imported.call("get_state"), "The waking mode must not be smuggled into an incomplete legacy snapshot.")
	_observations.append("explicit migration of original three-setting snapshots without changing existing modes")
