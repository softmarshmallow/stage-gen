extends RefCounted

## Bounded v2 document/state/event adapter over the one current Session executor.
## These projection rules preserve established consumers, not a second scheduler.
const Source = preload("../program.gd")
const Program = preload("../program/program.gd")
const Catalog = preload("../program/catalog.gd")
const Session = preload("../execution/session.gd")
const Refusal = preload("../refusal.gd")
static var _cache: Dictionary = {}


static func initial_turn(source: Dictionary, carried: PackedStringArray) -> Dictionary:
	var compiled := _compiled(source)
	if Refusal.is_refusal(compiled):
		return compiled
	var facts := {}
	for flag: String in source["importedFlags"]:
		facts[flag] = carried.has(flag)
	var session := Session.new()
	var report := session.start(compiled["program"], compiled["catalog"], _policy(), facts)
	if Refusal.is_refusal(report):
		return _failure(report, source, compiled)
	return _project(source, compiled, {"label": source["entry"], "index": -1, "flags": [], "seen": [], "stage": null, "actors": [], "tracks": [], "outcome": null}, report)


static func reduce_turn(source: Dictionary, state: Dictionary, action: Dictionary) -> Dictionary:
	var compiled := _compiled(source)
	if Refusal.is_refusal(compiled):
		return compiled
	var normalized: Dictionary = compiled["program"]
	var id := "%s#%d" % [state["label"], int(state["index"])]
	var facts := {}
	for flag: String in normalized["facts"]:
		facts[flag] = state["flags"].has(flag)
	var visits := {}
	for seen_id: String in state["seen"]:
		visits[seen_id] = 1
	visits[id] = 1
	var core_state := {"session_id": "v2", "status": "running", "node_id": id, "entered": true, "visit_counts": visits, "visit_id": id + "@1", "facts": facts, "clocks": {"sequence": 0.0, "presentation": 0.0, "reading": 0.0}, "seen": state["seen"].duplicate(), "presentation": normalized["nodes"][id].duplicate(true), "gate_events": [], "pending_cues": [], "fired_cues": [], "operations": {}, "instances": {}, "wait": {}, "event_sequence": 0, "operation_sequence": 0, "outcome": null, "deferred_actions": []}
	var session := Session.new()
	var restored := session.restore(normalized, compiled["catalog"], _policy(), {"kind": "scenario-session-snapshot", "schema_version": 1, "program_fingerprint": normalized["fingerprint"], "catalog_fingerprint": compiled["catalog"]["fingerprint"], "state": core_state})
	if Refusal.is_refusal(restored):
		return _failure(restored, source, compiled)
	var translated := {"kind": action["kind"]}
	if action["kind"] == "choose":
		var options: Array = session.view()["options"]
		translated["choice_id"] = options[int(action["option"])]["id"]
	var report := session.submit(translated)
	if Refusal.is_refusal(report):
		return _failure(report, source, compiled)
	if report.has("failure"):
		return _failure({"error": report["failure"]}, source, compiled)
	return _project(source, compiled, state, report)


static func _compiled(source: Dictionary) -> Dictionary:
	var key := Source.fingerprint(source)
	if _cache.has(key):
		return _cache[key]
	var catalog := Catalog.parse({"kind": "scenario-catalog", "schema_version": 1, "catalog_id": "scenario_v2_compatibility", "revision": "1", "definitions": {}}, {"v2_state": {"version": 1, "parameters": {"statement": {"type": "json", "required": true}}}})
	var facts := {}
	for flag: String in source["flags"]:
		facts[flag] = {"type": "boolean", "default": false}
	var impossible := "__v2_never"
	while facts.has(impossible):
		impossible += "_"
	facts[impossible] = {"type": "boolean", "default": false}
	var nodes: Array = []
	var locations := {}
	var statements := {}
	var fallthroughs := {}
	for block: Dictionary in source["blocks"]:
		var label: String = block["label"]
		var block_statements: Array = block["statements"]
		var fallthrough := label + "#fallthrough"
		fallthroughs[fallthrough] = "%s#%d" % [label, block_statements.size()]
		nodes.append({"id": fallthrough, "kind": "jump", "target": fallthrough})
		for index in block_statements.size():
			var id := "%s#%d" % [label, index]
			var next := "%s#%d" % [label, index + 1] if index + 1 < block_statements.size() else fallthrough
			var statement: Dictionary = block_statements[index]
			locations[id] = {"label": label, "index": index}
			statements[id] = statement
			var kind: String = statement["kind"]
			var node := {"id": id, "kind": kind}
			match kind:
				"line":
					node.merge({"text": statement["text"], "speaker": statement["speaker"], "expression": statement["expression"], "next": next})
				"choice":
					var options: Array = []
					for option_index in statement["options"].size():
						var option: Dictionary = statement["options"][option_index]
						options.append({"id": str(option_index), "text": option["text"], "target": option["target"] + "#0", "condition": _condition(option["condition"], impossible)})
					node["options"] = options
				"set": node.merge({"values": {statement["flag"]: statement["value"]}, "next": next})
				"jump": node["target"] = statement["target"] + "#0"
				"branch":
					node["default"] = statement["default"] + "#0"
					node["edges"] = []
					for edge: Dictionary in statement["edges"]:
						node["edges"].append({"target": edge["target"] + "#0", "condition": _condition(edge["condition"], impossible)})
				"end": node["outcome"] = statement["outcome"]
				_:
					node.merge({"kind": "effect", "effect": {"type": "v2_state", "parameters": {"statement": statement}}, "instance_id": "v2:" + id, "scope": "node", "next": next}, true)
			nodes.append(node)
	var speakers: Array = []
	for member: Dictionary in source["cast"]:
		speakers.append({"id": member["actorId"], "display_name": member["displayName"]})
	var program := Program.from_v2_adapter({"kind": "scenario-program-v3", "schema_version": 3, "scenario_id": source["scenarioId"] if not source["scenarioId"].is_empty() else "scenario_v2", "entry": source["entry"] + "#0", "nodes": nodes, "speakers": speakers, "facts": facts}, catalog)
	if Refusal.is_refusal(program):
		return program
	var result := {"program": program, "catalog": catalog, "locations": locations, "statements": statements, "fallthroughs": fallthroughs}
	if _cache.size() >= 16:
		_cache.erase(_cache.keys()[0])
	_cache[key] = result
	return result


static func _condition(condition: Dictionary, impossible: String) -> Dictionary:
	var result := {}
	for flag: String in condition.get("requires", PackedStringArray()):
		result[flag] = true
	for flag: String in condition.get("forbids", PackedStringArray()):
		if result.has(flag):
			return {impossible: true}
		result[flag] = false
	return result


static func _project(source: Dictionary, compiled: Dictionary, previous: Dictionary, report: Dictionary) -> Dictionary:
	var state := previous.duplicate(true)
	var events: Array = []
	for event: Dictionary in report["events"]:
		match event["type"]:
			"scenario/effect_started": _state_effect(state, event["effect"]["parameters"]["statement"], events)
			"scenario/facts_changed":
				for flag: String in event["values"]:
					events.append({"type": "scenario/flag-changed", "flag": flag, "value": event["values"][flag]})
			"scenario/branched", "scenario/chosen":
				var from: Dictionary = compiled["locations"][event["node_id"]]
				var to: Dictionary = compiled["locations"][event["target"]]
				events.append({"type": "scenario/branched", "from": from["label"], "to": to["label"], "cause": "choice" if event["type"] == "scenario/chosen" else event["cause"]})
			"scenario/presented":
				var statement: Dictionary = compiled["statements"][event["node_id"]]
				if statement["kind"] == "line":
					_speak(state, statement, events)
				events.append({"type": "scenario/presented", "statementId": event["node_id"], "kind": statement["kind"]})
			"scenario/ended": events.append({"type": "scenario/ended", "outcome": event["outcome"]})
	var current: Dictionary = report["state"]
	var location: Dictionary = compiled["locations"][current["node_id"]]
	state["label"] = location["label"]
	state["index"] = location["index"]
	state["seen"] = current["seen"].duplicate()
	state["outcome"] = current["outcome"]
	state["flags"] = []
	for flag: String in source["flags"]:
		if current["facts"][flag]:
			state["flags"].append(flag)
	state["flags"].sort()
	return {"state": state, "events": events}


static func _state_effect(state: Dictionary, statement: Dictionary, events: Array) -> void:
	match statement["kind"]:
		"show":
			var actor_id: String = statement["actor"]
			var expression: Variant = statement["expression"]
			var actors: Array = []
			for actor: Dictionary in state["actors"]:
				if actor["actorId"] != actor_id:
					actors.append(actor)
				elif expression == null:
					expression = actor["expression"]
			actors.append({"actorId": actor_id, "slot": statement["slot"], "expression": expression})
			state["actors"] = actors
			events.append({"type": "scenario/actor-changed", "actorId": actor_id, "slot": statement["slot"], "expression": expression})
		"hide":
			var actors: Array = []
			for actor: Dictionary in state["actors"]:
				if actor["actorId"] != statement["actor"]:
					actors.append(actor)
			state["actors"] = actors
			events.append({"type": "scenario/actor-changed", "actorId": statement["actor"], "slot": null, "expression": null})
		"stage":
			state["stage"] = statement["stage"]
			events.append({"type": "scenario/staged", "stage": statement["stage"]})
		"audio":
			var tracks: Array = []
			for track: String in state["tracks"]:
				if track != statement["track"]:
					tracks.append(track)
			if statement["action"] == "play":
				tracks.append(statement["track"])
			state["tracks"] = tracks
			events.append({"type": "scenario/audio-changed", "track": statement["track"], "action": statement["action"]})


static func _speak(state: Dictionary, statement: Dictionary, events: Array) -> void:
	if statement["speaker"] == null or statement["expression"] == null:
		return
	for actor: Dictionary in state["actors"]:
		if actor["actorId"] == statement["speaker"] and actor["expression"] != statement["expression"]:
			actor["expression"] = statement["expression"]
			events.append({"type": "scenario/actor-changed", "actorId": actor["actorId"], "slot": actor["slot"], "expression": actor["expression"]})


static func _failure(failure: Dictionary, _source: Dictionary, compiled: Dictionary) -> Dictionary:
	var message: String = failure["error"]["message"]
	var path: String = failure["error"]["path"]
	if compiled["fallthroughs"].has(path):
		path = compiled["fallthroughs"][path]
	return Refusal.of("scenario/no-options" if message.contains("no available option") else "scenario/nonsettling", message, path)


static func _policy() -> Dictionary:
	return {"session_id": "v2", "capabilities": {"v2_state": 1}, "channels": ["dialogue"], "bindings": []}
