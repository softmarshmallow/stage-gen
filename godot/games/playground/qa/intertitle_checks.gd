extends SceneTree

## Offline contract checks; host rendering and input routing need integration QA.
const CONTROLLER_PATH := "res://addons/game_presentation/text/intertitle.gd"
var _controller_script: Script
var _errors: Array[String] = []
var _observations: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_controller_script = load(CONTROLLER_PATH)
	if _controller_script == null or not _controller_script.can_instantiate():
		printerr("FAIL Intertitle: controller must load and instantiate.")
		quit(1)
		return
	_reveal_and_explicit_continuation()
	_frame_partitioning_and_clock_ownership()
	_snapshots_and_isolation()
	_rejected_inputs_are_atomic()
	_unicode_and_bounds()
	if _errors.is_empty():
		for observation: String in _observations:
			print("PASS Intertitle: " + observation)
	else:
		for issue: String in _errors:
			printerr("FAIL Intertitle: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _make() -> RefCounted:
	return _controller_script.new()


func _start(controller: RefCounted, text: String, settings: Dictionary = {}) -> void:
	var errors: Array = controller.call("start", text, settings)
	_expect(errors.is_empty(), "Valid cue must start: " + str(errors))


func _frame(controller: RefCounted) -> Dictionary:
	return controller.call("sample")


func _reveal_and_explicit_continuation() -> void:
	var controller := _make()
	_expect(_frame(controller) == {"text": "", "visible_characters": 0, "phase": "idle"}, "A new controller must begin empty and idle.")
	_expect(not controller.call("is_active") and not controller.call("request_advance"), "Idle input must not complete an absent cue.")
	_start(controller, "I am here.", {"chars_per_second": 4.0})
	_expect(_frame(controller).visible_characters == 0 and _frame(controller).phase == "revealing", "New text must start hidden.")
	controller.call("advance", 0.75)
	_expect(_frame(controller).visible_characters == 3, "Three codepoints must reveal after 0.75 seconds at four per second.")
	_expect(not controller.call("request_advance"), "Input during reveal must reveal without continuing.")
	_expect(_frame(controller).visible_characters == 10 and _frame(controller).phase == "holding", "The reveal action must expose the complete cue and hold it.")
	var held: Dictionary = controller.call("get_state")
	controller.call("advance", 10000000.0)
	_expect(held == controller.call("get_state") and controller.call("is_active"), "A held cue must remain active indefinitely without auto continuation.")
	_expect(controller.call("request_advance"), "A subsequent action must explicitly finish the held cue.")
	_expect(not controller.call("is_active") and _frame(controller).phase == "finished", "Finished cues must become inactive while preserving visible text.")
	_expect(not controller.call("request_advance"), "Completion must be emitted only once.")
	_start(controller, "Hi", {"chars_per_second": 2.0})
	controller.call("advance", 1.0)
	_expect(_frame(controller).phase == "holding" and controller.call("is_active"), "Natural reveal completion must also hold until an explicit action.")
	_expect(controller.call("request_advance"), "Already fully revealed text must finish on the first subsequent action.")
	controller.call("clear")
	_expect(_frame(controller) == {"text": "", "visible_characters": 0, "phase": "idle"}, "Clear must return to the empty identity.")
	_observations.append("typewriter timing, reveal-before-continue input, indefinite hold, one-shot completion, and reset")


func _frame_partitioning_and_clock_ownership() -> void:
	var text := "A scene waits until its reader chooses to continue."
	for rate: float in [0.1, 3.0, 32.0, 240.0]:
		for target: float in [0.0, 0.03125, 0.25, 1.0, 2.125, 20.0, 1000.0]:
			var whole := _make()
			var split := _make()
			_start(whole, text, {"chars_per_second": rate})
			_start(split, text, {"chars_per_second": rate})
			whole.call("advance", target)
			for index in 300:
				split.call("advance", target / 300.0)
			_expect(_frame(whole) == _frame(split), "Equivalent time must reveal the same text independent of frame partition at rate " + str(rate) + " and elapsed " + str(target))
	var controller := _make()
	_start(controller, text)
	controller.call("advance", 0.125)
	var saved: Dictionary = controller.call("get_state")
	for index in 100:
		controller.call("sample")
		controller.call("is_active")
		controller.call("get_state")
	for invalid_delta: float in [-1.0, 0.0, NAN, INF, -INF]:
		controller.call("advance", invalid_delta)
	_expect(saved == controller.call("get_state"), "Sampling and invalid deltas must not consume time.")
	controller.call("advance", 1.7976931348623157e308)
	_expect(_frame(controller).phase == "holding" and _frame(controller).visible_characters == text.length(), "A large finite delta must reveal the text without overflow or dismissal.")
	_observations.append("frame partition independence, side-effect-free sampling, invalid-delta no-ops, and bounded large deltas")


func _snapshots_and_isolation() -> void:
	for phase: String in ["idle", "revealing", "holding", "finished"]:
		var original := _make()
		if phase != "idle":
			_start(original, "The same moment returns after a detour.", {"chars_per_second": 17.3})
			original.call("advance", 0.271)
			if phase in ["holding", "finished"]:
				original.call("request_advance")
			if phase == "finished":
				original.call("request_advance")
		var saved: Dictionary = original.call("get_state")
		var restored := _make()
		var round_trip: Variant = JSON.parse_string(JSON.stringify(saved))
		var restore_errors: Array = restored.call("restore", round_trip)
		_expect(restore_errors.is_empty(), "Every phase must restore after JSON round trip: " + phase + "; " + str(restore_errors))
		_expect(_frame(original) == _frame(restored), "Restore must reproduce the exact visible cue for " + phase)
		var continuation_matches := true
		for index in 180:
			original.call("advance", 0.016)
			restored.call("advance", 0.016)
			continuation_matches = continuation_matches and _frame(original) == _frame(restored)
		_expect(continuation_matches, "Restored fractional progress must continue identically for " + phase)
		_expect(original.call("request_advance") == restored.call("request_advance"), "Restored phase must consume input identically for " + phase)
		saved["text"] = "External mutation"
		_expect(_frame(restored).text != "External mutation", "Snapshot input must not alias controller state.")
	var first := _make()
	var second := _make()
	var settings := {"chars_per_second": 4.0}
	_start(first, "Old", settings)
	settings["chars_per_second"] = 80.0
	first.call("advance", 0.25)
	_expect(_frame(first).visible_characters == 1 and _frame(second).phase == "idle", "Settings mutation and other instances must not affect an active cue.")
	_start(first, "Replacement")
	_expect(_frame(first) == {"text": "Replacement", "visible_characters": 0, "phase": "revealing"}, "A valid start must replace prior text and timing.")
	first.call("advance", 0.03125)
	_expect(_frame(first).visible_characters == 1, "Omitted settings must use the default rate again.")
	first.call("clear")
	_expect(first.call("get_state") == second.call("get_state"), "Clear must reset all saved state.")
	_observations.append("JSON snapshots in every phase, fractional-time resume, cue replacement, and isolated state")


func _rejected_inputs_are_atomic() -> void:
	var controller := _make()
	_start(controller, "A running cue must survive bad input.", {"chars_per_second": 20.0})
	controller.call("advance", 0.125)
	var unchanged: Dictionary = controller.call("get_state")
	for invalid_settings: Dictionary in [
		{"speed": 30.0}, {"chars_per_second": 0}, {"chars_per_second": -2},
		{"chars_per_second": 0.099}, {"chars_per_second": 240.01},
		{"chars_per_second": NAN}, {"chars_per_second": INF},
		{"chars_per_second": "32"}, {"chars_per_second": true}, {"chars_per_second": null},
	]:
		_expect(not (controller.call("start", "Replacement", invalid_settings) as Array).is_empty(), "Malformed settings must be refused: " + str(invalid_settings))
		_expect(unchanged == controller.call("get_state"), "Refused settings must preserve the existing cue.")
	for invalid_text: String in ["", "x".repeat(16385)]:
		_expect(not (controller.call("start", invalid_text) as Array).is_empty(), "Empty or oversized cues must be refused.")
		_expect(unchanged == controller.call("get_state"), "Refused text must preserve the existing cue.")
	var invalid_states: Array[Dictionary] = [{}]
	for key: String in unchanged:
		var missing := unchanged.duplicate()
		missing.erase(key)
		invalid_states.append(missing)
	for patch: Dictionary in [
		{"unknown": 1}, {"version": 2}, {"version": true},
		{"text": null}, {"text": ""}, {"text": "x".repeat(16385)},
		{"chars_per_second": 0.0}, {"chars_per_second": INF},
		{"elapsed": NAN}, {"elapsed": true}, {"elapsed": -1.0}, {"elapsed": 100000.0},
		{"phase": "invalid"}, {"phase": "idle"}, {"phase": "holding"}, {"phase": "finished"},
	]:
		var invalid := unchanged.duplicate()
		invalid.merge(patch, true)
		invalid_states.append(invalid)
	var complete := _make()
	_start(complete, "Complete")
	complete.call("request_advance")
	var inconsistent: Dictionary = complete.call("get_state")
	inconsistent["phase"] = "revealing"
	invalid_states.append(inconsistent)
	for invalid: Dictionary in invalid_states:
		_expect(not (controller.call("restore", invalid) as Array).is_empty(), "Malformed or inconsistent snapshots must be refused.")
		_expect(unchanged == controller.call("get_state"), "Rejected restore must be atomic.")
	_observations.append("atomic refusal for malformed settings/text and incomplete, nonfinite, or inconsistent snapshots")


func _unicode_and_bounds() -> void:
	var controller := _make()
	var text := "Aé🙂e\u0301\n中"
	_expect(text.length() == 7, "Unicode fixture must include one non-BMP emoji and a separate combining codepoint.")
	_start(controller, text, {"chars_per_second": 1.0})
	for count in range(1, 8):
		controller.call("advance", 1.0)
		_expect(_frame(controller).visible_characters == count, "Reveal must count Unicode codepoints, including newline and combining marks.")
	_expect(_frame(controller).phase == "holding", "Unicode text must stop at its exact codepoint length.")
	_start(controller, "x".repeat(16384), {"chars_per_second": 240.0})
	controller.call("advance", 1000.0)
	_expect(_frame(controller).visible_characters == 16384 and _frame(controller).phase == "holding", "Maximum text length and speed must remain valid and bounded.")
	_observations.append("explicit Unicode codepoint semantics and supported text/rate boundaries")
