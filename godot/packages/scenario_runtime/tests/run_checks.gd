extends SceneTree

const Program = preload("res://addons/scenario_runtime/program.gd")
const Runtime = preload("res://addons/scenario_runtime/runtime.gd")
const Refusal = preload("res://addons/scenario_runtime/refusal.gd")
const Example = preload("res://examples/minimal/program.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
	var parsed: Variant = Program.parse(Example.document())
	_check(not Refusal.is_refusal(parsed), "example is admitted")
	if Refusal.is_refusal(parsed):
		printerr(Refusal.line(parsed))
		quit(1)
		return
	_check(_behavior(parsed), "behavior section completed")
	_check(_admission(), "admission section completed")
	_check(_failure_atomicity(), "failure section completed")
	_check(_staging(), "staging section completed")
	_check(_malformed_shapes(), "malformed section completed")
	_check(_restore_invariants(), "restore invariants section completed")
	_check(_snapshot_identity(), "snapshot identity section completed")
	if not failures.is_empty():
		for failure in failures:
			printerr(failure)
		quit(1)
		return
	print("scenario_runtime: %d checks passed" % checks)
	quit(0)

func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)

func _behavior(program: Dictionary) -> bool:
	var opening := Runtime.initial_turn(program)
	_check(opening["events"] == [{"type": "scenario/presented", "statementId": "start#0", "kind": "line"}], "opening event identity")
	_check(Runtime.view(program, opening["state"])["text"] == "A distant signal arrives.", "line view")
	_check(Runtime.reduce_turn(program, opening["state"], {"kind": "choose", "option": 0})["events"].is_empty(), "stray choice is a no-op")
	var choice := Runtime.reduce_turn(program, opening["state"], {"kind": "advance"})
	_check(Runtime.view(program, choice["state"])["kind"] == "choice", "advance reaches choice")
	var ended := Runtime.reduce_turn(program, choice["state"], {"kind": "choose", "option": 0})
	_check(ended["state"]["flags"] == ["heard"], "choice applies flag")
	_check(ended["events"] == [{"type": "scenario/branched", "from": "start", "to": "reply", "cause": "choice"}, {"type": "scenario/flag-changed", "flag": "heard", "value": true}, {"type": "scenario/ended", "outcome": "received"}], "turn event order and payload")
	_check(Runtime.is_finished(ended["state"]), "ending reached")
	_check(Runtime.view(program, ended["state"])["label"] == "Signal received", "ending label")
	_check(Runtime.progress(program, ended["state"]) == {"seen": 2, "total": 2}, "progress identity")
	_check(Runtime.restore(program, ended["state"]) == ended["state"], "valid state restores without shape changes")
	_check(Runtime.reduce(program, ended["state"], {"kind": "restart"}) == opening["state"], "restart restores opening")
	_check(opening["state"]["flags"].is_empty(), "previous state remains unchanged")
	return true

func _admission() -> bool:
	for collection in ["cast", "stages", "tracks", "flags", "endings", "blocks"]:
		var malformed := Example.document()
		malformed[collection] = [17]
		_refused(Program.parse(malformed), "scenario/malformed", collection + "[0]")
	var malformed := Example.document()
	malformed["blocks"][0]["statements"] = [17]
	_refused(Program.parse(malformed), "scenario/malformed", "blocks[0].statements[0]")
	malformed = Example.document()
	malformed["blocks"][0]["statements"][1]["options"] = [17]
	_refused(Program.parse(malformed), "scenario/malformed", "blocks[0].statements[1].options[0]")
	malformed = Example.document()
	malformed["blocks"][0]["statements"][1]["options"][0]["target"] = "absent"
	_refused(Program.parse(malformed), "scenario/unresolved", "blocks[0].statements[1].options[0].target")
	malformed = Example.document()
	malformed["blocks"][1]["statements"][0]["flag"] = "absent"
	_refused(Program.parse(malformed), "scenario/unresolved", "blocks[1].statements[0].flag")
	malformed = Example.document()
	malformed["blocks"][0]["statements"][1]["options"][0]["condition"] = {"requires": [false]}
	_refused(Program.parse(malformed), "scenario/malformed", "blocks[0].statements[1].options[0].condition.requires[0]")
	malformed = Example.document()
	malformed["blocks"][0]["statements"][1]["options"][0]["condition"] = {"requires": ["absent"]}
	_refused(Program.parse(malformed), "scenario/unresolved", "blocks[0].statements[1].options[0].condition.requires")
	_refused(Program.parse(null), "scenario/malformed", "")
	malformed = Example.document()
	malformed["entry"] = "absent"
	_refused(Program.parse(malformed), "scenario/entry", "entry")
	malformed = Example.document()
	malformed["schema_version"] = []
	_refused(Program.parse(malformed), "scenario/program-kind", "schema_version")
	return true

func _failure_atomicity() -> bool:
	var raw := Example.document()
	raw["blocks"][1]["statements"] = [{"kind": "set", "flag": "heard"}, {"kind": "jump", "target": "reply"}]
	var program: Dictionary = Program.parse(raw)
	var opening := Runtime.initial_state(program)
	var choice := Runtime.reduce(program, opening, {"kind": "advance"})
	var before := choice.duplicate(true)
	var failure := Runtime.reduce_turn(program, choice, {"kind": "choose", "option": 0})
	_check(Refusal.is_refusal(failure) and failure["error"]["code"] == "scenario/nonsettling", "invisible cycle fails structurally")
	_check(not failure.has("state") and not failure.has("events"), "failure publishes no partial result")
	_check(choice == before, "failed turn leaves previous state unchanged")
	raw["entry"] = "reply"
	program = Program.parse(raw)
	_check(Refusal.is_refusal(Runtime.initial_turn(program)), "nonsettling opening is refused")
	_check(Refusal.is_refusal(Runtime.initial_state(program)), "state convenience method propagates refusal")
	raw = Example.document()
	raw["blocks"][0]["statements"][1]["options"][0]["condition"] = {"requires": ["heard"]}
	program = Program.parse(raw)
	opening = Runtime.initial_state(program)
	failure = Runtime.reduce_turn(program, opening, {"kind": "advance"})
	_check(Refusal.is_refusal(failure) and failure["error"]["code"] == "scenario/no-options", "unavailable choice fails without an unplayable view")
	_refused(Runtime.reduce_turn(program, opening, {"kind": "choose", "option": {}}), "scenario/action", "option")
	return true

func _refused(value: Variant, code: String, path: String) -> void:
	_check(Refusal.is_refusal(value), "refusal at " + path)
	if Refusal.is_refusal(value):
		_check(value["error"]["code"] == code, "refusal code at " + path)
		_check(value["error"]["path"] == path, "refusal path at " + path)

func _staging() -> bool:
	var raw := {
		"kind": "scenario-program-v2", "schema_version": 2, "entry": "start",
		"cast": [{"actor_id": "operator", "expressions": ["neutral", "curious"]}],
		"stages": [{"stage_id": "station"}], "tracks": [{"track_id": "hum"}],
		"flags": [{"flag_id": "permit", "origin": "imported"}, {"flag_id": "local"}],
		"endings": [{"outcome_id": "done"}],
		"blocks": [
			{"label": "start", "statements": [
				{"kind": "stage", "stage": "station"},
				{"kind": "audio", "track": "hum"},
				{"kind": "show", "actor": "operator", "slot": "far_left", "expression": "neutral"},
				{"kind": "line", "speaker": "operator", "expression": "curious", "text": "A signal?"},
				{"kind": "branch", "edges": [{"target": "finish", "condition": {"requires": ["permit"], "forbids": ["local"]}}], "default": "repeat"},
			]},
			{"label": "repeat", "statements": [{"kind": "jump", "target": "start"}]},
			{"label": "finish", "statements": [
				{"kind": "hide", "actor": "operator"},
				{"kind": "audio", "action": "stop", "track": "hum"},
				{"kind": "set", "flag": "permit", "value": false},
				{"kind": "end", "outcome": "done"},
			]},
		],
	}
	var program: Dictionary = Program.parse(raw)
	_check(not Refusal.is_refusal(program), "staging program admitted")
	var opening := Runtime.initial_turn(program, PackedStringArray(["permit", "local", "unknown", "permit"]))
	_check(opening["state"]["flags"] == ["permit"], "only imported declared carried flags survive, without duplicates")
	_check(opening["state"]["stage"] == "station" and opening["state"]["tracks"] == ["hum"], "stage and audio settle before line")
	_check(Runtime.actor(opening["state"], "operator") == {"actorId": "operator", "slot": "far_left", "expression": "curious"}, "speech expression changes staged actor")
	_check(opening["events"] == [
		{"type": "scenario/staged", "stage": "station"},
		{"type": "scenario/audio-changed", "track": "hum", "action": "play"},
		{"type": "scenario/actor-changed", "actorId": "operator", "slot": "far_left", "expression": "neutral"},
		{"type": "scenario/actor-changed", "actorId": "operator", "slot": "far_left", "expression": "curious"},
		{"type": "scenario/presented", "statementId": "start#3", "kind": "line"},
	], "invisible staging and speech events retain order")
	_check(Runtime.restore(program, opening["state"]) == opening["state"], "staged snapshot restores exactly")
	var ended := Runtime.reduce_turn(program, opening["state"], {"kind": "advance"})
	_check(Runtime.is_finished(ended["state"]), "conditional branch reaches ending")
	_check(ended["state"]["actors"].is_empty() and ended["state"]["tracks"].is_empty() and ended["state"]["flags"].is_empty(), "hide, stop and clearing flags apply")
	var loop := Runtime.initial_state(program)
	var repeated := Runtime.reduce_turn(program, loop, {"kind": "advance"})
	_check(not Refusal.is_refusal(repeated) and repeated["state"] == loop, "visible loops remain valid")
	_check(repeated["events"][0]["cause"] == "branch" and repeated["events"][1]["cause"] == "jump", "default branch and jump events")
	for slot in Program.SLOTS:
		var candidate := raw.duplicate(true)
		candidate["blocks"][0]["statements"][2]["slot"] = slot
		_check(not Refusal.is_refusal(Program.parse(candidate)), "supported slot: " + slot)
	for change in [{"index": {}}, {"flags": {}}, {"actors": [false]}, {"stage": {}}, {"tracks": [false]}, {"seen": [{}]}, {"outcome": {}}, {"label": {}}]:
		var snapshot: Dictionary = opening["state"].duplicate(true)
		snapshot.merge(change, true)
		_check(Runtime.restore(program, snapshot) == null, "malformed snapshot returns null: " + str(change.keys()))
	var saved: Dictionary = opening["state"].duplicate(true)
	saved["actors"][0]["expression"] = "unknown"
	_check(Runtime.restore(program, saved) == null, "unresolved saved expression returns null")
	saved = opening["state"].duplicate(true)
	saved["actors"].append(saved["actors"][0].duplicate(true))
	_check(Runtime.restore(program, saved) == null, "duplicate saved actor refused")
	saved = opening["state"].duplicate(true)
	saved["tracks"].append("hum")
	_check(Runtime.restore(program, saved) == null, "duplicate saved track refused")
	return true

func _malformed_shapes() -> bool:
	for change in [{"blocks": {}}, {"cast": null}, {"entry": {}}, {"scenario_id": 7}, {"display_name": []}, {"flags": [{"flag_id": "heard", "origin": []}]}, {"cast": [{"actor_id": "speaker", "expressions": [{}]}]}]:
		var raw := Example.document()
		raw.merge(change, true)
		_check(Refusal.is_refusal(Program.parse(raw)), "malformed consumed field: " + str(change.keys()))
	for statement in [
		{"kind": "line", "speaker": {}}, {"kind": "line", "text": []},
		{"kind": "line", "expression": {}}, {"kind": "show", "actor": "absent", "slot": "center"},
		{"kind": "hide", "actor": "absent"}, {"kind": "stage", "stage": "absent"},
		{"kind": "audio", "track": "absent"}, {"kind": "audio", "track": "absent", "action": "pause"},
		{"kind": "set", "flag": "heard", "value": 1}, {"kind": "jump", "target": "absent"},
		{"kind": "end", "outcome": "absent"}, {"kind": "branch", "edges": [false], "default": "reply"},
		{"kind": "branch", "edges": [], "default": "absent"}, {"kind": "choice", "options": []},
		{"kind": "choice", "options": [{"target": "reply", "condition": []}]},
	]:
		var raw := Example.document()
		raw["blocks"][0]["statements"][0] = statement
		_check(Refusal.is_refusal(Program.parse(raw)), "malformed or unresolved statement: " + str(statement))
	var raw := Example.document()
	raw["blocks"].append(raw["blocks"][0].duplicate(true))
	_check(Refusal.is_refusal(Program.parse(raw)), "duplicate block refused")
	raw = Example.document()
	raw["blocks"][0]["statements"] = []
	_check(Refusal.is_refusal(Program.parse(raw)), "empty block refused")
	raw = Example.document()
	raw["blocks"][0]["statements"] = [{"kind": "line", "text": "No transfer follows."}]
	var program: Dictionary = Program.parse(raw)
	var opening := Runtime.initial_state(program)
	var failure := Runtime.reduce_turn(program, opening, {"kind": "advance"})
	_check(Refusal.is_refusal(failure) and failure["error"]["code"] == "scenario/nonsettling", "fallthrough fails instead of wrapping to the same line")
	return true


func _restore_invariants() -> bool:
	var program: Dictionary = Program.parse(Example.document())
	var opening := Runtime.initial_state(program)
	var choice := Runtime.reduce(program, opening, {"kind": "advance"})
	var ended := Runtime.reduce(program, choice, {"kind": "choose", "option": 0})
	for state in [opening, choice, ended]:
		_check(Runtime.restore(program, JSON.parse_string(JSON.stringify(state))) == state, "JSON save round trip preserves a settled state")
	for change in [
		{"label": "reply", "index": 0},
		{"outcome": "received"},
		{"seen": ["ghost#0"]},
		{"seen": ["start#0", "start#0"]},
		{"seen": ["start#0", "reply#0"]},
		{"seen": ["start#0", "reply#1"]},
		{"seen": []},
		{"flags": ["heard", "heard"]},
	]:
		var saved: Dictionary = opening.duplicate(true)
		saved.merge(change, true)
		_check(Runtime.restore(program, saved) == null, "inconsistent restored state refused: " + str(change))
	var missing_outcome := ended.duplicate(true)
	missing_outcome["outcome"] = null
	_check(Runtime.restore(program, missing_outcome) == null, "end statement requires its outcome")
	var raw := Example.document()
	raw["endings"].append({"outcome_id": "other", "label": "Another ending"})
	program = Program.parse(raw)
	var wrong_outcome := ended.duplicate(true)
	wrong_outcome["outcome"] = "other"
	_check(Runtime.restore(program, wrong_outcome) == null, "declared outcome must match the current end statement")
	raw["blocks"][0]["statements"][1]["options"][0]["condition"] = {"requires": ["heard"]}
	program = Program.parse(raw)
	_check(Runtime.restore(program, choice) == null, "a restored choice needs at least one available option")
	_check(opening["seen"] == ["start#0"], "snapshot admission does not mutate the caller state")
	return true


func _snapshot_identity() -> bool:
	var raw := Example.document()
	var program: Dictionary = Program.parse(raw)
	var opening := Runtime.initial_state(program)
	var saved := Runtime.snapshot(program, opening)
	_check(saved["kind"] == "scenario-runtime-snapshot" and saved["schema_version"] == 1, "content-bound envelope has its own version")
	_check(Runtime.restore(program, saved) == opening, "content-bound snapshot restores current program")
	_check(Runtime.restore(program, JSON.parse_string(JSON.stringify(saved))) == opening, "content-bound snapshot survives JSON serialization")
	var edited := raw.duplicate(true)
	edited["blocks"][0]["statements"].insert(0, {"kind": "line", "text": "New opening before the saved position."})
	var changed: Dictionary = Program.parse(edited)
	_check(Runtime.restore(changed, saved) == null, "inserting text refuses stale position even when label and index still exist")
	_check(Runtime.restore(changed, opening) != null, "raw historical states keep structural compatibility without claiming revision verification")
	edited = raw.duplicate(true)
	edited["blocks"][0]["statements"][0]["text"] = "Changed text at the same position."
	_check(Runtime.restore(Program.parse(edited), saved) == null, "editing existing text invalidates content identity")
	edited = raw.duplicate(true)
	edited["blocks"][1]["statements"][0]["value"] = false
	_check(Runtime.restore(Program.parse(edited), saved) == null, "editing an invisible effect invalidates content identity")
	edited = raw.duplicate(true)
	edited["producer_metadata"] = {"revision": "not interpreted"}
	_check(Runtime.restore(Program.parse(edited), saved) == opening, "unconsumed producer metadata does not invalidate interpreter identity")
	var reordered := {}
	var keys: Array = raw.keys()
	keys.reverse()
	for key: Variant in keys:
		reordered[key] = raw[key]
	_check(Runtime.restore(Program.parse(reordered), saved) == opening, "dictionary insertion order does not invalidate identity")
	for change in [
		{"kind": "unknown"}, {"kind": {}}, {"schema_version": 2}, {"schema_version": []}, {"schema_version": true},
		{"program_fingerprint": "sha256:stale"}, {"program_fingerprint": {}},
		{"state": false},
	]:
		var malformed := saved.duplicate(true)
		malformed.merge(change, true)
		_check(Runtime.restore(program, malformed) == null, "malformed envelope refused: " + str(change.keys()))
	var missing_identity := saved.duplicate(true)
	missing_identity.erase("program_fingerprint")
	_check(Runtime.restore(program, missing_identity) == null, "partial envelope does not fall back to legacy admission")
	var invalid_state := saved.duplicate(true)
	invalid_state["state"]["index"] = 200
	_check(Runtime.restore(program, invalid_state) == null, "matching fingerprint does not bypass state validation")
	saved["state"]["seen"].append("ghost#0")
	_check(opening["seen"] == ["start#0"], "snapshot creation detaches state from the caller")
	_check(Runtime.restore(program, saved) == null, "matching fingerprint does not authenticate modified save state")
	return true
