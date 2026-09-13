extends SceneTree

const TRANSPORT = preload("res://addons/scenario_runtime/execution/transport.gd")
var _errors: Array[String] = []


func _initialize() -> void:
	var transport = TRANSPORT.new()
	_expect(transport.configure({}).is_empty(), "Default policy initializes.")
	transport.enter("opening")
	_expect(transport.tick(20.0, "", false, true).is_empty(), "Disabled transport never advances.")
	transport.set_enabled(true)
	_expect(transport.tick(20.0, "", false, false).is_empty(), "A readiness-completing frame does not count as reading.")
	_expect(transport.tick(2.0, "", false, true).is_empty(), "Reading delay remains required.")
	var saved: Dictionary = transport.snapshot()
	_expect(transport.tick(20.0, "paused", false, true).is_empty() and transport.snapshot() == saved, "Pause preserves reading time.")
	_expect(transport.tick(1.0, "", false, true) == {"kind": "advance"}, "Ready reading requests one advance.")
	transport.tick(2.0, "", false, true)
	transport.manual_action()
	_expect(transport.tick(1.0, "", false, true).is_empty(), "Manual input resets the reading delay.")
	_expect(transport.tick(9.0, "voice", false, true).is_empty() and transport.state()["elapsed_seconds"] == 0.0, "Active voice blocks and resets reading time.")
	_expect(transport.enter("choice", {"default_choice": "accept"}, ["accept", "decline"]).is_empty(), "An authored choice default initializes.")
	_expect(transport.tick(4.0, "", true, true).is_empty(), "Choice uses its own delay.")
	_expect(transport.tick(1.0, "", true, true) == {"kind": "choose", "choice_id": "accept"}, "Choice request uses the stable option ID.")
	transport.enter("contact", {"require_input": true})
	_expect(transport.tick(60.0, "", false, true).is_empty(), "Required interaction cannot be completed by autoplay.")
	transport.enter("return")
	transport.tick(2.0, "", false, true)
	saved = transport.snapshot()
	var resumed = TRANSPORT.new()
	resumed.configure({})
	resumed.enter("return")
	_expect(resumed.restore(saved).is_empty() and resumed.snapshot() == saved, "Same-node reading state restores.")
	saved["node_id"] = "other"
	_expect(not resumed.restore(saved).is_empty(), "A different node refuses the saved clock.")
	_expect(not transport.configure({"delay_seconds": NAN}).is_empty(), "Nonfinite policy refuses.")
	transport.tick(1.0, "ended", false, true)
	_expect(not transport.state()["enabled"], "The ending disables autoplay.")
	for issue: String in _errors: printerr("FAIL transport: " + issue)
	if _errors.is_empty(): print("PASS transport: explicit time/readiness, manual reset, pause, voice, choices, required input and restore")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
