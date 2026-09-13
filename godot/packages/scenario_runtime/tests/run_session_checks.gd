extends SceneTree

const Program = preload("res://addons/scenario_runtime/program/program.gd")
const Catalog = preload("res://addons/scenario_runtime/program/catalog.gd")
const Session = preload("res://addons/scenario_runtime/execution/session.gd")
const Refusal = preload("res://addons/scenario_runtime/refusal.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	_check(_catalog_checks(), "catalog checks completed")
	_check(_admission_checks(), "admission checks completed")
	_check(_progression_checks(), "progression checks completed")
	_check(_time_checks(), "clock checks completed")
	_check(_lifecycle_checks(), "lifecycle checks completed")
	_check(_transaction_checks(), "transaction checks completed")
	_check(_active_order_checks(), "active operation index checks completed")
	_check(_gate_checks(), "gate checks completed")
	_check(_restore_checks(), "restore checks completed")
	_check(_compiler_conformance(), "compiler conformance checks completed")
	if not failures.is_empty():
		for failure: String in failures:
			printerr(failure)
		quit(1)
		return
	print("scenario_session: %d checks passed" % checks)
	quit(0)

func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)

func _types() -> Dictionary:
	return {"pulse": {"version": 1, "reconstructable": true, "finishable": true, "parameters": {"strength": {"type": "number", "min": 0.0, "max": 1.0, "default": 0.5}, "color": {"type": "string", "enum": ["amber", "blue"], "default": "amber"}}}}

func _catalog_document() -> Dictionary:
	return {"kind": "scenario-catalog", "schema_version": 1, "catalog_id": "test_catalog", "revision": "r1", "definitions": {"soft_pulse": {"type": "pulse", "parameters": {}, "overrides": ["strength"]}}}

func _catalog() -> Dictionary:
	return Catalog.parse(_catalog_document(), _types())

func _policy() -> Dictionary:
	return {"session_id": "session_a", "capabilities": {"pulse": 1}, "channels": ["dialogue"], "bindings": ["actor"]}

func _document() -> Dictionary:
	return {"kind": "scenario-program-v3", "schema_version": 3, "scenario_id": "synthetic", "entry": "opening", "facts": {"agreed": {"type": "boolean", "default": false}, "world_ready": {"type": "boolean", "default": false, "external": true}}, "speakers": [{"id": "guide", "display_name": "Guide"}], "nodes": [
		{"id": "opening", "kind": "line", "speaker": "guide", "text": "The world keeps moving.", "next": "menu", "cues": [
			{"id": "pulse", "at": 0.25, "effect": {"preset": "soft_pulse"}, "instance_id": "glow", "target": "actor", "duration": 0.5, "scope": "sequence", "clock": "presentation"},
			{"id": "reaction", "on": "text_revealed", "after": 0.1, "effect": {"type": "pulse", "parameters": {"color": "blue"}}, "instance_id": "reaction", "duration": 0.2, "clock": "sequence"},
		]},
		{"id": "menu", "kind": "choice", "options": [{"id": "accept", "text": "Continue", "target": "pause", "set": {"agreed": true}}, {"id": "wait", "text": "Wait", "target": "opening", "condition": {"world_ready": true}}]},
		{"id": "pause", "kind": "wait", "duration": 0.5, "next": "branch"},
		{"id": "branch", "kind": "branch", "edges": [{"condition": {"agreed": true}, "target": "success"}], "default": "failure"},
		{"id": "success", "kind": "end", "outcome": "accepted"},
		{"id": "failure", "kind": "end", "outcome": "declined"},
	]}

func _session(document: Dictionary = {}) -> RefCounted:
	var catalog := _catalog()
	var program := Program.parse(_document() if document.is_empty() else document, catalog)
	_check(not Refusal.is_refusal(program), "test program admitted")
	var session := Session.new()
	var started := session.start(program, catalog, _policy())
	_check(not Refusal.is_refusal(started), "test session started")
	return session

func _catalog_checks() -> bool:
	var catalog := _catalog()
	_check(not Refusal.is_refusal(catalog), "typed catalog admitted")
	var roundtrip := Catalog.parse(JSON.parse_string(JSON.stringify(_catalog_document())), JSON.parse_string(JSON.stringify(_types())))
	_check(roundtrip["fingerprint"] == catalog["fingerprint"], "catalog identity survives integer-to-float JSON parsing")
	_check(Catalog.resolve({"preset": "soft_pulse"}, catalog) == Catalog.resolve({"type": "pulse", "parameters": {}}, catalog), "named and inline configurations normalize identically")
	_check(Catalog.resolve({"preset": "soft_pulse", "parameters": {"strength": 0.8}}, catalog)["parameters"]["strength"] == 0.8, "declared preset override accepted")
	for effect in [{"preset": "missing"}, {"type": "unknown"}, {"preset": "soft_pulse", "parameters": {"color": "blue"}}, {"type": "pulse", "parameters": {"strength": "fast"}}, {"type": "pulse", "parameters": {"strength": 2.0}}, {"type": "pulse", "parameters": {"unknown": 1}}]:
		_check(Refusal.is_refusal(Catalog.resolve(effect, catalog)), "invalid catalog use refused: " + str(effect))
	for change in [{"kind": []}, {"schema_version": {}}, {"revision": 1}, {"definitions": []}]:
		var raw := _catalog_document()
		raw.merge(change, true)
		_check(Refusal.is_refusal(Catalog.parse(raw, _types())), "malformed catalog refused")
	for declaration in [
		{"type": "unknown"}, {"type": "array", "items": {"type": "unknown"}},
		{"type": "object", "properties": {"nested": {"type": "unknown"}}},
		{"type": "number", "default": "wrong"}, {"type": "number", "min": INF},
		{"type": "number", "min": 4.0, "max": 1.0}, {"type": "string", "enum": "wrong"},
		{"type": "string", "required": "sometimes"}, {"type": "object", "additional_properties": "yes"},
		{"type": "number", "minimum": 1.0}]:
		var installed := _types()
		installed["unused"] = {"version": 1, "parameters": {"optional": declaration}}
		_check(Refusal.is_refusal(Catalog.parse(_catalog_document(), installed)), "unused optional schema is fully validated before registration")
	for flag in ["reconstructable", "finishable"]:
		var installed := _types()
		installed["pulse"][flag] = "yes"
		_check(Refusal.is_refusal(Catalog.parse(_catalog_document(), installed)), "installed lifecycle declarations must be boolean")
	return true


func _compiler_conformance() -> bool:
	var root := "res://conformance/authoring/"
	var catalog := Catalog.parse(JSON.parse_string(FileAccess.get_file_as_string(root + "catalog.json")), JSON.parse_string(FileAccess.get_file_as_string(root + "capabilities.json")))
	_check(not Refusal.is_refusal(catalog), "Python authoring catalog admitted")
	var program := Program.parse(JSON.parse_string(FileAccess.get_file_as_string(root + "bridge.program.json")), catalog)
	_check(not Refusal.is_refusal(program), "Python compiler output admitted by native player")
	if Refusal.is_refusal(program):
		printerr(Refusal.line(program))
		return false
	var session := Session.new()
	var report := session.start(program, catalog, {"session_id": "bridge", "capabilities": {"particle": 1}, "channels": ["dialogue"], "bindings": ["air", "guide"]})
	_check(not Refusal.is_refusal(report), "compiled source starts without producer dependency")
	session.submit({"kind": "host_event", "session_id": "bridge", "name": "text_revealed"})
	session.submit({"kind": "advance"})
	_check(session.view()["text_key"] == "question", "compiled choice retains its authored prompt")
	session.submit({"kind": "choose", "choice_id": "yes"})
	_check(session.view()["node_id"] == "agreed__settled", "compiled bounded call waits for its owned operation")
	session.tick(0.25)
	_check(session.view()["node_id"] == "accepted_line", "compiled operation duration resumes macro continuation")
	_check(session.view()["presentation"]["profile"] == "bubble", "compiled content selects a different dialogue surface")
	session.submit({"kind": "advance"})
	_check(session.view()["outcome"] == "accepted", "compiled branch and scope cleanup reach expected ending")
	return true

func _admission_checks() -> bool:
	var catalog := _catalog()
	var raw := _document()
	for change in [{"kind": []}, {"schema_version": {}}, {"entry": "absent"}, {"nodes": {}}, {"facts": []}, {"speakers": [false]}]:
		var invalid := raw.duplicate(true)
		invalid.merge(change, true)
		_check(Refusal.is_refusal(Program.parse(invalid, catalog)), "malformed program refused: " + str(change.keys()))
	var unknown := raw.duplicate(true)
	unknown["nodes"][0]["next"] = "absent"
	_check(Refusal.is_refusal(Program.parse(unknown, catalog)), "unknown next node refused")
	unknown = raw.duplicate(true)
	unknown["nodes"][1]["options"][0]["set"] = {"world_ready": true}
	_check(Refusal.is_refusal(Program.parse(unknown, catalog)), "content cannot assign external facts")
	for change in [{"timing": 1.0}, {"gates": false}, {"advance_mode": {}}, {"next": "missing"}, {"text_key": "also_text"}]:
		var invalid := raw.duplicate(true)
		invalid["nodes"][0].merge(change, true)
		_check(Refusal.is_refusal(Program.parse(invalid, catalog)), "invalid or unknown node behavior refused: " + str(change.keys()))
	unknown = raw.duplicate(true)
	unknown["nodes"].append({"id": "unreachable", "kind": "end", "outcome": "unused"})
	_check(Refusal.is_refusal(Program.parse(unknown, catalog)), "downloaded program cannot carry unreachable behavior")
	unknown = raw.duplicate(true)
	unknown["nodes"][4] = {"id": "success", "kind": "jump", "target": "success"}
	_check(Refusal.is_refusal(Program.parse(unknown, catalog)), "reachable silent trap refused even when another ending exists")
	unknown["nodes"][4] = {"id": "success", "kind": "wait", "duration": 0.0, "next": "success"}
	_check(Refusal.is_refusal(Program.parse(unknown, catalog)), "zero-duration wait does not disguise a silent cycle")
	for requirement in [{"absent": 1}, {"pulse": 2}]:
		unknown = raw.duplicate(true)
		unknown["required_capabilities"] = requirement
		_check(Refusal.is_refusal(Program.parse(unknown, catalog)), "explicit unavailable capability requirement refused at admission")
	var program := Program.parse(raw, catalog)
	for change in [{"capabilities": {}}, {"capabilities": {"pulse": 2}}, {"channels": []}, {"bindings": []}]:
		var policy := _policy()
		policy.merge(change, true)
		var session := Session.new()
		_check(Refusal.is_refusal(session.start(program, catalog, policy)), "missing policy grant refused")
		_check(session.drain_events().is_empty(), "admission failure emits no commands")
	return true

func _progression_checks() -> bool:
	var session := _session()
	_check(session.view()["text"] == "The world keeps moving.", "line view exposes authored text")
	session.submit({"kind": "advance"})
	_check(session.view()["options"].size() == 1, "choice filters current fact snapshot")
	session.submit({"kind": "external_facts", "session_id": "session_a", "values": {"world_ready": true}})
	_check(session.view()["options"].size() == 2, "explicit host fact update changes available choices")
	_check(not session.submit({"kind": "choose", "choice_id": "unknown"})["consumed"], "unknown stable choice id is unconsumed")
	session.submit({"kind": "choose", "choice_id": "accept"})
	_check(session.view()["node_id"] == "pause", "chosen option enters authored wait")
	_check(not session.submit({"kind": "advance"})["consumed"], "advance cannot bypass wait")
	_check(not session.submit({"kind": "host_event", "session_id": "session_a", "name": "combat_hit"})["consumed"], "unrelated gameplay event remains unconsumed")
	session.tick(0.5)
	_check(session.view()["outcome"] == "accepted", "time wait and fact branch reach ending")
	var events: Array = session.drain_events()
	var outcomes := 0
	for event: Dictionary in events:
		if event["type"] == "scenario/ended": outcomes += 1
	_check(outcomes == 1, "one outcome emitted per invocation")
	_check(session.tick(100.0)["events"].is_empty(), "terminal ticks do not repeat outcomes")
	return true

func _time_checks() -> bool:
	var large := _session()
	var small := _session()
	large.drain_events()
	small.drain_events()
	large.tick(1.0)
	for _step in 100:
		small.tick(0.01)
	var large_events: Array = large.drain_events()
	var small_events: Array = small.drain_events()
	_check(large_events.size() == 2 and small_events.size() == 2, "one timed start and finish independent of tick partition")
	for index in large_events.size():
		_check(large_events[index]["type"] == small_events[index]["type"] and large_events[index]["event_id"] == small_events[index]["event_id"], "stable occurrence identity across partitions")
		_check(is_equal_approx(large_events[index]["clocks"]["presentation"], small_events[index]["clocks"]["presentation"]), "same exact effect boundary across partitions")
	_check(is_equal_approx(large_events[0]["clocks"]["presentation"], 0.25), "effect starts at cue boundary within large tick")
	_check(is_equal_approx(large_events[1]["clocks"]["presentation"], 0.75), "effect completes at duration boundary within large tick")
	var split := _session()
	split.drain_events()
	split.tick({"sequence": 1.0})
	_check(split.drain_events().is_empty(), "paused presentation clock does not advance world effect cue")
	split.submit({"kind": "host_event", "session_id": "session_a", "name": "text_revealed"})
	split.tick({"sequence": 0.1})
	_check(split.drain_events()[0]["instance_id"] == "reaction", "event-relative cue follows its supplied clock")
	_check(Refusal.is_refusal(split.tick(-1.0)), "negative time refused")
	_check(Refusal.is_refusal(split.tick(INF)), "infinite time refused")
	return true

func _operation_document() -> Dictionary:
	return {"kind": "scenario-program-v3", "schema_version": 3, "scenario_id": "operation", "entry": "begin", "nodes": [
		{"id": "begin", "kind": "effect", "effect": {"preset": "soft_pulse"}, "instance_id": "interaction", "next": "wait"},
		{"id": "wait", "kind": "wait", "operation": "interaction", "next": "done"},
		{"id": "done", "kind": "end", "outcome": "complete"},
	]}

func _lifecycle_checks() -> bool:
	var session := _session(_operation_document())
	var operation: String = session.snapshot()["state"]["instances"]["interaction"]
	session.drain_events()
	_check(not session.submit({"kind": "operation_completed", "session_id": "another_session", "operation_id": operation})["consumed"], "cross-session completion ignored")
	_check(not session.submit({"kind": "operation_completed", "session_id": "session_a", "operation_id": "stale"})["consumed"], "unknown operation completion ignored")
	session.suspend()
	var frozen: Dictionary = session.snapshot()["state"]["clocks"]
	session.tick(20.0)
	_check(session.snapshot()["state"]["clocks"] == frozen, "suspension freezes only supplied invocation clocks")
	session.submit({"kind": "operation_completed", "session_id": "session_a", "operation_id": operation})
	_check(session.view()["status"] == "suspended", "completion queues while suspended")
	session.resume()
	_check(session.view()["outcome"] == "complete", "queued completion resumes authored sequence")
	_check(not session.submit({"kind": "operation_completed", "session_id": "session_a", "operation_id": operation})["consumed"], "duplicate completion cannot advance terminal sequence")
	var cancelled := _session(_operation_document())
	cancelled.drain_events()
	var report: Dictionary = cancelled.cancel("actor_lost")
	_check(report["events"][0]["type"] == "scenario/effect_cancelled", "cancel releases owned active operation first")
	_check(report["events"][1]["type"] == "scenario/cancelled", "cancel emits invocation result after release")
	_check(cancelled.cancel()["events"].is_empty(), "cancellation is idempotent")
	var loop := _operation_document()
	loop["entry"] = "loop"
	loop["nodes"].append({"id": "loop", "kind": "jump", "target": "loop"})
	var failed := Session.new()
	_check(Refusal.is_refusal(failed.start(Program.parse(loop, _catalog()), _catalog(), _policy())), "silent opening cycle refuses boundedly")
	_check(failed.drain_events().is_empty(), "failed opening publishes no partial effects")
	return true

func _gate_checks() -> bool:
	var raw := _document()
	raw["nodes"][0]["gates"] = [{"event": "cinematic_ready", "finish_on_advance": true}, {"event": "text_revealed", "finish_on_advance": true}]
	var session := _session(raw)
	session.drain_events()
	_check(session.submit({"kind": "advance"})["events"][0]["type"] == "scenario/finish_requested", "first advance requests cinematic completion")
	_check(session.view()["node_id"] == "opening", "finish request does not skip the utterance")
	session.submit({"kind": "host_event", "session_id": "session_a", "name": "cinematic_ready"})
	_check(session.submit({"kind": "advance"})["events"][0]["type"] == "scenario/reveal_requested", "next advance requests text reveal")
	session.submit({"kind": "host_event", "session_id": "session_a", "name": "text_revealed"})
	session.submit({"kind": "advance"})
	_check(session.view()["node_id"] == "menu", "only ready presentation advances")
	raw = _document()
	raw["nodes"][0]["advance_mode"] = "on_gates"
	raw["nodes"][0]["gates"] = [{"event": "operation_completed:feedback"}]
	raw["nodes"][0]["cues"] = [{"id": "feedback", "on": "contact_confirmed", "effect": {"preset": "soft_pulse"}, "instance_id": "feedback", "duration": 0.45}]
	session = _session(raw)
	_check(Refusal.is_refusal(session.submit({"kind": "host_event", "session_id": "session_a", "name": "operation_completed:feedback"})), "host event cannot impersonate an identified operation completion")
	session.submit({"kind": "advance"})
	_check(session.view()["node_id"] == "opening", "required contact cannot be skipped")
	session.submit({"kind": "host_event", "session_id": "session_a", "name": "contact_confirmed"})
	session.tick(0.44)
	_check(session.view()["node_id"] == "opening", "feedback remains authored work before completion")
	session.tick(0.01)
	_check(session.view()["node_id"] == "menu", "operation completion advances on_gates content without game timer")
	return true


func _transaction_checks() -> bool:
	var raw := {"kind": "scenario-program-v3", "schema_version": 3, "scenario_id": "failure_boundary", "entry": "line", "nodes": [
		{"id": "line", "kind": "line", "text": "Begin.", "next": "begin"},
		{"id": "begin", "kind": "effect", "effect": {"preset": "soft_pulse"}, "instance_id": "active", "next": "wait"},
		{"id": "wait", "kind": "wait", "duration": 0.1, "next": "bad_stop"},
		{"id": "bad_stop", "kind": "stop", "instance_id": "never_started", "next": "done"},
		{"id": "done", "kind": "end", "outcome": "complete"},
	]}
	var combined := _session(raw)
	combined.drain_events()
	var report: Dictionary = combined.tick(0.2, [{"kind": "advance"}])
	_check(report.has("failure") and report["state"]["status"] == "failed", "timer settlement failure terminates the invocation")
	var split := _session(raw)
	split.drain_events()
	var expected: Array = split.submit({"kind": "advance"})["events"]
	expected.append_array(split.tick(0.2)["events"])
	_check(report["events"] == expected, "accepted input occurrences survive a later tick failure with the same start and cleanup as separate calls")
	_check(report["events"][0]["type"] == "scenario/effect_started", "an accepted input cannot publish cancellation for a silently dropped start")
	return true


func _active_order_checks() -> bool:
	var raw := _document()
	raw["nodes"][0]["cues"] = []
	for index in 12:
		var cue := {"id": "cue_%d" % index, "at": 0.0, "effect": {"preset": "soft_pulse"}, "instance_id": "instance_%d" % index, "scope": "sequence"}
		if index < 9: cue["duration"] = 0.0
		raw["nodes"][0]["cues"].append(cue)
	var session := _session(raw)
	var saved: Dictionary = JSON.parse_string(JSON.stringify(session.snapshot(), "", true))
	_check(saved["state"]["operations"].size() == 12, "finished history remains in the portable snapshot")
	var restored := Session.new()
	var report := restored.restore(Program.parse(raw, _catalog()), _catalog(), _policy(), saved)
	var ids: Array = []
	for event: Dictionary in report["events"]: ids.append(event["operation_id"])
	_check(ids == ["session_a:operation:10", "session_a:operation:11", "session_a:operation:12"], "JSON restore derives only active operations in numeric occurrence order")
	restored.drain_events()
	report = restored.cancel()
	var cancelled: Array = []
	for event: Dictionary in report["events"]:
		if event["type"] == "scenario/effect_cancelled": cancelled.append(event["operation_id"])
	_check(cancelled == ids, "cleanup preserves active occurrence order without revisiting finished work")
	_check(restored.snapshot()["state"]["operations"].size() == 12, "active scheduling cleanup preserves complete persistence history")
	return true

func _restore_checks() -> bool:
	var catalog := _catalog()
	var program := Program.parse(_document(), catalog)
	var source := _session()
	source.tick(0.4)
	var saved: Dictionary = JSON.parse_string(JSON.stringify(source.snapshot()))
	var restored := Session.new()
	var report: Dictionary = restored.restore(program, catalog, _policy(), saved)
	_check(not Refusal.is_refusal(report), "active session restores from JSON")
	if Refusal.is_refusal(report):
		printerr(Refusal.line(report))
		return false
	_check(restored.view() == source.view(), "restore preserves current presentation and progression")
	_check(report["events"].size() == 1 and report["events"][0]["type"] == "scenario/effect_restored", "restore reconstructs active work without replaying start events")
	_check(is_equal_approx(report["events"][0]["elapsed"], 0.15), "restore provides active operation elapsed time")
	for change in [{"node_id": "branch"}, {"seen": ["ghost"]}, {"seen": ["opening", "opening"]}, {"clocks": {"sequence": -1, "presentation": 0, "reading": 0}}, {"outcome": "accepted"}, {"visit_id": "opening@99"}, {"operations": []}, {"entered": {}}, {"fired_cues": ["ghost@1:cue"]}, {"fired_cues": ["opening@1:pulse", "opening@1:pulse"]}, {"instances": {}}, {"operation_sequence": 0}, {"presentation": {}}, {"pending_cues": [false]}]:
		var invalid := saved.duplicate(true)
		invalid["state"].merge(change, true)
		_check(Refusal.is_refusal(Session.new().restore(program, catalog, _policy(), invalid)), "invalid session snapshot refused: " + str(change.keys()))
	var operation_id: String = saved["state"]["instances"]["glow"]
	for change in [{"start_time": -1.0}, {"visit_id": "opening@9"}, {"effect": {"type": "uninstalled"}}, {"target": {}}, {"duration": 0.1}, {"status": "invented"}]:
		var invalid := saved.duplicate(true)
		invalid["state"]["operations"][operation_id].merge(change, true)
		_check(Refusal.is_refusal(Session.new().restore(program, catalog, _policy(), invalid)), "invalid restored operation refused: " + str(change.keys()))
	var changed := _document()
	changed["nodes"][0]["text"] = "Edited content."
	_check(Refusal.is_refusal(Session.new().restore(Program.parse(changed, catalog), catalog, _policy(), saved)), "changed content cannot reuse an old snapshot")
	source.cancel()
	saved = source.snapshot()
	var ended := Session.new()
	_check(not Refusal.is_refusal(ended.restore(program, catalog, _policy(), saved)), "cancelled snapshot restores without active effects")
	_check(ended.drain_events().is_empty(), "terminal restore does not replay external outcomes")
	return true
