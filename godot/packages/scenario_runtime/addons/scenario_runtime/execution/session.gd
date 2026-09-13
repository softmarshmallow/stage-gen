extends RefCounted

## An invocation has supplied clocks and emits commands; it owns no Godot nodes,
## inputs, audio devices, wall time, world state or application lifecycle.
const Program = preload("../program/program.gd")
const Catalog = preload("../program/catalog.gd")
const Refusal = preload("../refusal.gd")
const WORK_LIMIT := 4096
const EPSILON := 0.000000001

var _program: Dictionary = {}
var _catalog: Dictionary = {}
var _policy: Dictionary = {}
var _state: Dictionary = {}
var _events: Array = []
# Derived scheduling index only; persisted operation history remains complete.
var _active_operation_ids: Array[String] = []


func start(program: Dictionary, catalog: Dictionary, policy: Dictionary, initial_facts: Dictionary = {}) -> Dictionary:
	if not _state.is_empty():
		return _error("an invocation cannot be started twice", "session")
	var failure := _admit(program, catalog, policy)
	if not failure.is_empty():
		return failure
	var facts := {}
	for key: String in program["facts"]:
		var declaration: Dictionary = program["facts"][key]
		facts[key] = declaration.get("default", false)
	for key: Variant in initial_facts:
		if not (key is String) or not program["facts"].has(key) or not Program.fact_value(initial_facts[key], program["facts"][key]):
			return _error("initial fact is not declared with this value", "initial_facts." + str(key))
		facts[key] = initial_facts[key]
	_program = program
	_catalog = catalog
	_policy = policy.duplicate(true)
	_active_operation_ids.clear()
	_state = {"session_id": policy["session_id"], "status": "running", "node_id": program["entry"], "entered": false, "visit_counts": {}, "visit_id": "", "facts": facts, "clocks": {"sequence": 0.0, "presentation": 0.0, "reading": 0.0}, "seen": [], "presentation": {}, "gate_events": [], "pending_cues": [], "fired_cues": [], "operations": {}, "instances": {}, "wait": {}, "event_sequence": 0, "operation_sequence": 0, "outcome": null, "deferred_actions": []}
	failure = _settle()
	if failure.is_empty():
		failure = _due()
	if not failure.is_empty():
		_state = {}
		_events.clear()
		_active_operation_ids.clear()
		return failure
	return _report(0, true)


func tick(delta: Variant, input_events: Array = []) -> Dictionary:
	var deltas := _deltas(delta)
	if Refusal.is_refusal(deltas):
		return deltas
	if _state.is_empty():
		return _error("start or restore an invocation first", "session")
	var first := _events.size()
	for action: Variant in input_events:
		if not (action is Dictionary):
			return _error("input events must be action records", "input_events")
	# Validate every action before any externally visible progress.
	for action: Dictionary in input_events:
		var invalid := _validate_action(action)
		if not invalid.is_empty():
			return invalid
	for action: Dictionary in input_events:
		var result := submit(action)
		if Refusal.is_refusal(result):
			return result
	if _state["status"] != "running":
		return _report(first, false)
	var before := _state.duplicate(true)
	# Input submissions are completed transactions. A later clock failure rolls
	# back only clock progress, retaining those accepted occurrence batches.
	var clock_first := _events.size()
	var remaining := deltas.duplicate()
	for _iteration in WORK_LIMIT:
		var failure := _due()
		if not failure.is_empty():
			return _execution_failure(before, first, failure, clock_first)
		if _state["status"] != "running" or _zero(remaining):
			return _report(first, true)
		var fraction := _boundary_fraction(remaining)
		for clock: String in Program.CLOCKS:
			_state["clocks"][clock] = float(_state["clocks"][clock]) + float(remaining[clock]) * fraction
			remaining[clock] = float(remaining[clock]) * (1.0 - fraction)
	return _execution_failure(before, first, _error("tick exceeded its bounded work budget", "tick"), clock_first)


func submit(action: Dictionary) -> Dictionary:
	if _state.is_empty():
		return _error("start or restore an invocation first", "session")
	var invalid := _validate_action(action)
	if not invalid.is_empty():
		return invalid
	var first := _events.size()
	if not ["running", "suspended"].has(_state["status"]):
		return _report(first, false)
	var kind: String = action["kind"]
	if action.has("session_id") and action["session_id"] != _state["session_id"]:
		return _report(first, false)
	if _state["status"] == "suspended":
		if ["operation_completed", "operation_failed", "host_event", "external_facts"].has(kind):
			_state["deferred_actions"].append(action.duplicate(true))
		return _report(first, false)
	var before := _state.duplicate(true)
	var node: Dictionary = _program["nodes"][_state["node_id"]]
	var consumed := false
	if kind == "advance" or kind == "choose":
		if not ["line", "choice"].has(node["kind"]):
			return _report(first, false)
		var pending := _pending_gate(node)
		if not pending.is_empty():
			if pending["finish_on_advance"]:
				_emit("scenario/reveal_requested" if pending["event"] == "text_revealed" else "scenario/finish_requested", {"gate_event": pending["event"]})
			return _report(first, true)
		if kind == "advance" and node["kind"] == "line":
			_goto(node["next"])
			consumed = true
		elif kind == "choose" and node["kind"] == "choice":
			for option: Dictionary in node["options"]:
				if option["id"] == action["choice_id"] and _holds(option["condition"]):
					_assign(option["set"])
					_emit("scenario/chosen", {"choice_id": option["id"], "target": option["target"]})
					_goto(option["target"])
					consumed = true
					break
	elif kind == "host_event":
		if action.has("node_id") and action["node_id"] != _state["node_id"]:
			return _report(first, false)
		if action.has("visit_id") and action["visit_id"] != _state["visit_id"]:
			return _report(first, false)
		var name: String = action["name"]
		if not _uses_event(node, name):
			return _report(first, false)
		_record_event(name)
		if node["kind"] == "wait" and node.get("event", "") == name:
			_goto(node["next"])
		elif node["kind"] == "line" and node["advance_mode"] == "on_gates" and _pending_gate(node).is_empty():
			_goto(node["next"])
		consumed = true
	elif kind == "operation_completed" or kind == "operation_failed":
		var operation_id: String = action["operation_id"]
		if not _state["operations"].has(operation_id) or _state["operations"][operation_id]["status"] != "running":
			return _report(first, false)
		if kind == "operation_failed":
			return _execution_failure(before, first, _error("host operation failed", operation_id))
		_finish(operation_id, "finished", "host", action.get("result"))
		consumed = true
	elif kind == "external_facts":
		for key: String in action["values"]:
			_state["facts"][key] = action["values"][key]
		consumed = true
	var failure := _settle()
	if failure.is_empty():
		failure = _due()
	if not failure.is_empty():
		return _execution_failure(before, first, failure)
	return _report(first, consumed)


func suspend() -> Dictionary:
	if _state.is_empty():
		return _error("start an invocation first", "session")
	var first := _events.size()
	if _state["status"] == "running":
		_state["status"] = "suspended"
		_emit("scenario/suspended")
	return _report(first, true)


func resume() -> Dictionary:
	if _state.is_empty():
		return _error("start an invocation first", "session")
	var first := _events.size()
	if _state["status"] == "suspended":
		_state["status"] = "running"
		_emit("scenario/resumed")
		var deferred: Array = _state["deferred_actions"].duplicate(true)
		_state["deferred_actions"].clear()
		for action: Dictionary in deferred:
			var result := submit(action)
			if Refusal.is_refusal(result):
				return result
	return _report(first, true)


func cancel(reason: String = "host") -> Dictionary:
	if _state.is_empty():
		return _error("start an invocation first", "session")
	var first := _events.size()
	if ["running", "suspended"].has(_state["status"]):
		_terminate("cancelled", reason)
	return _report(first, true)


func view() -> Dictionary:
	if _state.is_empty():
		return {}
	var shown: Dictionary = _state["presentation"].duplicate(true)
	shown.merge({"status": _state["status"], "node_id": _state["node_id"], "visit_id": _state["visit_id"], "outcome": _state["outcome"], "wait": _state["wait"].duplicate(true)}, true)
	var node: Dictionary = _program["nodes"][_state["node_id"]]
	shown["pending_gate"] = _pending_gate(node) if node.has("gates") else {}
	if node["kind"] == "choice":
		shown["options"] = _options(node)
	return shown


func drain_events() -> Array:
	var events := _events.duplicate(true)
	_events.clear()
	return events


func snapshot() -> Dictionary:
	if _state.is_empty():
		return _error("start an invocation first", "session")
	return {"kind": "scenario-session-snapshot", "schema_version": 1, "program_fingerprint": _program["fingerprint"], "catalog_fingerprint": _catalog["fingerprint"], "state": _state.duplicate(true)}


func restore(program: Dictionary, catalog: Dictionary, policy: Dictionary, saved: Variant) -> Dictionary:
	if not _state.is_empty():
		return _error("restore requires a fresh invocation", "session")
	var failure := _admit(program, catalog, policy)
	if not failure.is_empty():
		return failure
	if not (saved is Dictionary) or not (saved.get("kind") is String) or saved["kind"] != "scenario-session-snapshot":
		return _error("expected a session snapshot", "snapshot")
	var version: Variant = saved.get("schema_version")
	if not (version is int or version is float) or version != 1:
		return _error("unsupported snapshot version", "snapshot.schema_version")
	for field in ["program_fingerprint", "catalog_fingerprint"]:
		if not (saved.get(field) is String):
			return _error("snapshot fingerprint must be a string", "snapshot." + field)
	if saved["program_fingerprint"] != program["fingerprint"] or saved["catalog_fingerprint"] != catalog["fingerprint"]:
		return _error("snapshot content revision differs", "snapshot")
	_program = program
	_catalog = catalog
	_policy = policy.duplicate(true)
	failure = _validate_saved(saved.get("state"))
	if not failure.is_empty():
		return failure
	_state = saved["state"].duplicate(true)
	_rebuild_active_operations()
	if not _state["presentation"].is_empty():
		_state["presentation"] = _program["nodes"][_state["presentation"]["id"]].duplicate(true)
	# Reconstruct only currently owned work; never replay historical starts or an
	# already delivered outcome. The game restores its world separately.
	for operation_id: String in _operation_ids():
		var operation: Dictionary = _state["operations"][operation_id]
		if operation["status"] == "running":
			var payload := operation.duplicate(true)
			payload["elapsed"] = float(_state["clocks"][operation["clock"]]) - float(operation["start_time"])
			_emit("scenario/effect_restored", payload)
	return _report(0, true)


func _settle() -> Dictionary:
	for _step in WORK_LIMIT:
		if _state["status"] != "running":
			return {}
		var node: Dictionary = _program["nodes"][_state["node_id"]]
		if not _state["entered"]:
			_state["entered"] = true
			var visit := int(_state["visit_counts"].get(node["id"], 0)) + 1
			_state["visit_counts"][node["id"]] = visit
			_state["visit_id"] = "%s@%d" % [node["id"], visit]
			_state["gate_events"] = []
			match node["kind"]:
				"line", "choice":
					if node["kind"] == "choice" and _options(node).is_empty():
						return _error("choice has no available option", node["id"])
					if not _state["seen"].has(node["id"]):
						_state["seen"].append(node["id"])
					_state["presentation"] = node.duplicate(true)
					_emit("scenario/presented", {"presentation": node.duplicate(true)})
					for definition: Dictionary in node.get("cues", []):
						var cue := definition.duplicate(true)
						cue["node_id"] = node["id"]
						cue["visit_id"] = _state["visit_id"]
						cue["cue_id"] = _state["visit_id"] + ":" + cue["id"]
						cue["deadline"] = float(_state["clocks"][cue["clock"]]) + float(cue["at"]) if cue.has("at") else null
						_state["pending_cues"].append(cue)
				"wait":
					_state["wait"] = {"node_id": node["id"], "clock": node["clock"]}
					if node.has("duration"):
						_state["wait"]["deadline"] = float(_state["clocks"][node["clock"]]) + float(node["duration"])
					elif node.has("operation"):
						if not _state["instances"].has(node["operation"]):
							return _error("wait names an operation that has not started", node["id"])
						_state["wait"]["operation_id"] = _state["instances"][node["operation"]]
					else:
						_state["wait"]["event"] = node["event"]
					_emit("scenario/waiting", {"wait": _state["wait"].duplicate(true)})
		match node["kind"]:
			"line", "choice":
				if node["kind"] == "line" and node["advance_mode"] == "on_gates" and _pending_gate(node).is_empty():
					_goto(node["next"])
				else:
					return {}
			"wait":
				var wait: Dictionary = _state["wait"]
				if wait.has("deadline") and float(_state["clocks"][wait["clock"]]) + EPSILON >= float(wait["deadline"]):
					_goto(node["next"])
				elif wait.has("operation_id") and _state["operations"][wait["operation_id"]]["status"] == "finished":
					_goto(node["next"])
				else:
					return {}
			"set":
				_assign(node["values"])
				_goto(node["next"])
			"jump":
				_emit("scenario/branched", {"target": node["target"], "cause": "jump"})
				_goto(node["target"])
			"branch":
				var target: String = node["default"]
				for edge: Dictionary in node["edges"]:
					if _holds(edge["condition"]):
						target = edge["target"]
						break
				_emit("scenario/branched", {"target": target, "cause": "branch"})
				_goto(target)
			"effect":
				var failure := _begin_effect(node, node["id"], _state["visit_id"])
				if not failure.is_empty():
					return failure
				_goto(node["next"])
			"stop":
				if not _state["instances"].has(node["instance_id"]):
					return _error("stop names an operation that has not started", node["id"])
				_finish(_state["instances"][node["instance_id"]], "cancelled", "stop")
				_goto(node["next"])
			"end":
				_state["outcome"] = node["outcome"]
				_terminate("ended", "completed")
	return _error("sequence exceeded its invisible-instruction budget", _state["node_id"])


func _due() -> Dictionary:
	for _iteration in WORK_LIMIT:
		if _state["status"] != "running":
			return {}
		var changed := false
		# Finish existing operations first at a shared timestamp, then fire authored
		# cues in source order. This makes reusing an instance at that boundary safe.
		for operation_id: String in _operation_ids():
			var operation: Dictionary = _state["operations"][operation_id]
			if operation["status"] == "running" and operation["duration"] != null and float(_state["clocks"][operation["clock"]]) + EPSILON >= float(operation["start_time"]) + float(operation["duration"]):
				_finish(operation_id, "finished", "duration")
				changed = true
		var kept: Array = []
		var ready: Array = []
		for cue: Dictionary in _state["pending_cues"]:
			if cue["deadline"] != null and float(_state["clocks"][cue["clock"]]) + EPSILON >= float(cue["deadline"]):
				ready.append(cue)
			else:
				kept.append(cue)
		_state["pending_cues"] = kept
		for cue: Dictionary in ready:
			_state["fired_cues"].append(cue["cue_id"])
			var failure := _begin_effect(cue, cue["node_id"], cue["visit_id"])
			if not failure.is_empty():
				return failure
			changed = true
		var before_node: String = _state["visit_id"]
		var failure := _settle()
		if not failure.is_empty():
			return failure
		if not changed and before_node == _state["visit_id"]:
			return {}
	return _error("due work exceeded its bounded work budget", _state["node_id"])


func _begin_effect(definition: Dictionary, node_id: String, visit_id: String) -> Dictionary:
	var instance: String = definition["instance_id"]
	if _state["instances"].has(instance) and _state["operations"][_state["instances"][instance]]["status"] == "running":
		return _error("effect instance already has active work", instance)
	_state["operation_sequence"] = int(_state["operation_sequence"]) + 1
	var operation_id := "%s:operation:%d" % [_state["session_id"], _state["operation_sequence"]]
	var operation := {"operation_id": operation_id, "instance_id": instance, "effect": definition["effect"].duplicate(true), "target": definition["target"], "scope": definition["scope"], "clock": definition["clock"], "duration": definition["duration"], "start_time": float(_state["clocks"][definition["clock"]]), "node_id": node_id, "visit_id": visit_id, "status": "running", "result": null}
	_state["operations"][operation_id] = operation
	_state["instances"][instance] = operation_id
	_active_operation_ids.append(operation_id)
	_emit("scenario/effect_started", operation.duplicate(true))
	return {}


func _finish(operation_id: String, status: String, reason: String, result: Variant = null) -> void:
	var operation: Dictionary = _state["operations"][operation_id]
	if operation["status"] != "running":
		return
	operation["status"] = status
	operation["result"] = result
	_active_operation_ids.erase(operation_id)
	_emit("scenario/effect_finished" if status == "finished" else "scenario/effect_cancelled", {"operation_id": operation_id, "instance_id": operation["instance_id"], "reason": reason, "result": result})
	if status == "finished":
		_record_event("operation_completed:" + operation["instance_id"])


func _record_event(name: String) -> void:
	if not _state["gate_events"].has(name):
		_state["gate_events"].append(name)
	for cue: Dictionary in _state["pending_cues"]:
		if cue["visit_id"] == _state["visit_id"] and cue.get("on", "") == name and cue["deadline"] == null:
			cue["deadline"] = float(_state["clocks"][cue["clock"]]) + float(cue["after"])


func _goto(target: String) -> void:
	var leaving: String = _state["visit_id"]
	for operation_id: String in _operation_ids():
		var operation: Dictionary = _state["operations"][operation_id]
		if operation["scope"] == "node" and operation["visit_id"] == leaving:
			_finish(operation_id, "cancelled", "node_exit")
	var kept: Array = []
	for cue: Dictionary in _state["pending_cues"]:
		if cue["scope"] != "node" or cue["visit_id"] != leaving:
			kept.append(cue)
	_state["pending_cues"] = kept
	_state["node_id"] = target
	_state["entered"] = false
	_state["wait"] = {}


func _terminate(status: String, reason: String) -> void:
	for operation_id: String in _operation_ids():
		_finish(operation_id, "cancelled", reason)
	_state["pending_cues"].clear()
	_state["deferred_actions"].clear()
	_state["wait"] = {}
	_state["status"] = status
	_emit("scenario/" + status, {"reason": reason, "outcome": _state["outcome"]})
	_emit("scenario/released", {"channels": _policy.get("channels", []).duplicate()})


func _execution_failure(before: Dictionary, first: int, failure: Dictionary, rollback_first: int = -1) -> Dictionary:
	_state = before
	_rebuild_active_operations()
	_events.resize(first if rollback_first < 0 else rollback_first)
	_terminate("failed", failure["error"]["message"])
	var report := _report(first, true)
	report["failure"] = failure["error"]
	return report


func _emit(type: String, payload: Dictionary = {}) -> void:
	_state["event_sequence"] = int(_state["event_sequence"]) + 1
	var event := payload.duplicate(true)
	event.merge({"type": type, "event_id": "%s:event:%d" % [_state["session_id"], _state["event_sequence"]], "session_id": _state["session_id"], "node_id": payload.get("node_id", _state["node_id"]), "visit_id": payload.get("visit_id", _state["visit_id"]), "clocks": _state["clocks"].duplicate()}, true)
	_events.append(event)


func _report(first: int, consumed: bool) -> Dictionary:
	return {"state": _state.duplicate(true), "events": _events.slice(first).duplicate(true), "consumed": consumed}


func _holds(condition: Dictionary) -> bool:
	for key: String in condition:
		if _state["facts"][key] != condition[key]:
			return false
	return true


func _operation_ids() -> Array:
	# A stable copy permits completion/cancellation to mutate the live index.
	return _active_operation_ids.duplicate()


func _rebuild_active_operations() -> void:
	_active_operation_ids.clear()
	for id: String in _state["operations"]:
		if _state["operations"][id]["status"] == "running":
			_active_operation_ids.append(id)
	var prefix: String = _state["session_id"] + ":operation:"
	_active_operation_ids.sort_custom(func(left: String, right: String) -> bool: return int(left.trim_prefix(prefix)) < int(right.trim_prefix(prefix)))


func _uses_event(node: Dictionary, name: String) -> bool:
	if node["kind"] == "wait" and node.get("event", "") == name:
		return true
	for gate: Dictionary in node.get("gates", []):
		if gate["event"] == name:
			return true
	for cue: Dictionary in _state["pending_cues"]:
		if cue["visit_id"] == _state["visit_id"] and cue.get("on", "") == name:
			return true
	return false


func _assign(values: Dictionary) -> void:
	for key: String in values:
		_state["facts"][key] = values[key]
	if not values.is_empty():
		_emit("scenario/facts_changed", {"values": values.duplicate(true)})


func _options(node: Dictionary) -> Array:
	var options: Array = []
	for option: Dictionary in node["options"]:
		if _holds(option["condition"]):
			options.append(option.duplicate(true))
	return options


func _pending_gate(node: Dictionary) -> Dictionary:
	for gate: Dictionary in node.get("gates", []):
		if not _state["gate_events"].has(gate["event"]):
			return gate.duplicate()
	return {}


func _boundary_fraction(delta: Dictionary) -> float:
	var fraction := 1.0
	var deadlines: Array = []
	for id: String in _active_operation_ids:
		var operation: Dictionary = _state["operations"][id]
		if operation["duration"] != null:
			deadlines.append({"clock": operation["clock"], "at": float(operation["start_time"]) + float(operation["duration"])})
	for cue: Dictionary in _state["pending_cues"]:
		if cue["deadline"] != null:
			deadlines.append({"clock": cue["clock"], "at": cue["deadline"]})
	if _state["wait"].has("deadline"):
		deadlines.append({"clock": _state["wait"]["clock"], "at": _state["wait"]["deadline"]})
	for deadline: Dictionary in deadlines:
		var clock: String = deadline["clock"]
		if float(delta[clock]) > 0.0:
			fraction = minf(fraction, maxf(0.0, (float(deadline["at"]) - float(_state["clocks"][clock])) / float(delta[clock])))
	return fraction


static func _deltas(delta: Variant) -> Dictionary:
	var result := {"sequence": 0.0, "presentation": 0.0, "reading": 0.0}
	if delta is int or delta is float:
		if not is_finite(float(delta)) or float(delta) < 0.0:
			return _error("delta must be finite and nonnegative", "delta")
		for clock: String in Program.CLOCKS:
			result[clock] = float(delta)
	elif delta is Dictionary:
		for clock: Variant in delta:
			if not Program.CLOCKS.has(clock) or not (delta[clock] is int or delta[clock] is float) or not is_finite(float(delta[clock])) or float(delta[clock]) < 0.0:
				return _error("clock delta must be finite and nonnegative", "delta." + str(clock))
			result[clock] = float(delta[clock])
	else:
		return _error("delta must be a number or supplied clock record", "delta")
	return result


static func _zero(values: Dictionary) -> bool:
	for value: float in values.values():
		if value > 0.0:
			return false
	return true


func _validate_action(action: Dictionary) -> Dictionary:
	if not (action.get("kind") is String):
		return _error("action needs a kind", "action")
	var kind: String = action["kind"]
	if not ["advance", "choose", "host_event", "operation_completed", "operation_failed", "external_facts"].has(kind):
		return _error("unknown action", "action.kind")
	if action.has("session_id") and not _name(action["session_id"]):
		return _error("action session identity must be a name", "action.session_id")
	if kind == "choose" and not _name(action.get("choice_id")):
		return _error("choice action needs a stable choice_id", "action.choice_id")
	if ["host_event", "operation_completed", "operation_failed", "external_facts"].has(kind) and not _name(action.get("session_id")):
		return _error("host result needs session identity", "action.session_id")
	if kind == "host_event" and not _name(action.get("name")):
		return _error("host event needs a name", "action.name")
	if kind == "host_event" and action["name"].begins_with("operation_completed:"):
		return _error("operation completion events require an identified operation result", "action.name")
	for field in ["node_id", "visit_id"]:
		if action.has(field) and not _name(action[field]):
			return _error("event scope must be named", "action." + field)
	if ["operation_completed", "operation_failed"].has(kind):
		if not _name(action.get("operation_id")):
			return _error("operation result needs identity", "action.operation_id")
		var checked := Catalog.validate_value(action.get("result"), {"type": "json"}, "action.result")
		if Refusal.is_refusal(checked):
			return checked
	if kind == "external_facts":
		if not (action.get("values") is Dictionary):
			return _error("fact update needs values", "action.values")
		for key: Variant in action["values"]:
			if not (key is String) or not _program["facts"].has(key) or not _program["facts"][key].get("external", false) or not Program.fact_value(action["values"][key], _program["facts"][key]):
				return _error("host update needs a declared external fact value", "action.values." + str(key))
	return {}


static func _admit(program: Dictionary, catalog: Dictionary, policy: Dictionary) -> Dictionary:
	if not program.has("fingerprint") or not catalog.has("fingerprint") or program.get("catalog_fingerprint") != catalog["fingerprint"]:
		return _error("use an admitted program and its catalog", "program")
	if not _name(policy.get("session_id")) or not (policy.get("capabilities", {}) is Dictionary):
		return _error("policy needs session identity and capability grants", "policy")
	for list_name in ["channels", "bindings"]:
		if not (policy.get(list_name, []) is Array):
			return _error("policy grants must be arrays", "policy." + list_name)
		for value: Variant in policy.get(list_name, []):
			if not _name(value):
				return _error("policy grants must be names", "policy." + list_name)
	for capability: String in program["required_capabilities"]:
		var grant: Variant = policy.get("capabilities", {}).get(capability)
		if not (grant is int or grant is float) or grant != program["required_capabilities"][capability]:
			return _error("required capability version is not granted", "policy.capabilities." + capability)
	for node: Dictionary in program["nodes"].values():
		if node.has("presentation") and not policy.get("channels", []).has(node["presentation"]["channel"]):
			return _error("presentation channel is not granted", node["id"])
		var effects: Array = [node] if node["kind"] == "effect" else node.get("cues", [])
		for effect: Dictionary in effects:
			if effect["target"] != null and not policy.get("bindings", []).has(effect["target"]):
				return _error("effect target is not bound", node["id"])
	return {}


func _validate_saved(value: Variant) -> Dictionary:
	if not (value is Dictionary):
		return _error("snapshot state must be a record", "snapshot.state")
	if Refusal.is_refusal(Catalog.validate_value(value, {"type": "json"}, "snapshot.state")):
		return _error("snapshot state must contain only JSON values", "snapshot.state")
	var state: Dictionary = value
	if not state.has("outcome"):
		return _error("snapshot outcome field is absent", "snapshot.outcome")
	for field in ["session_id", "status", "node_id", "visit_id"]:
		if not _name(state.get(field)):
			return _error("snapshot identity is malformed", "snapshot." + field)
	if state["session_id"] != _policy["session_id"] or not ["running", "suspended", "ended", "cancelled", "failed"].has(state["status"]) or not _program["nodes"].has(state["node_id"]):
		return _error("snapshot session, status or node is incompatible", "snapshot")
	for field in ["facts", "clocks", "visit_counts", "presentation", "operations", "instances", "wait"]:
		if not (state.get(field) is Dictionary):
			return _error("snapshot field must be a record", "snapshot." + field)
	for field in ["seen", "gate_events", "pending_cues", "fired_cues", "deferred_actions"]:
		if not (state.get(field) is Array):
			return _error("snapshot field must be an array", "snapshot." + field)
	for field in ["event_sequence", "operation_sequence"]:
		if not _integer(state.get(field)):
			return _error("snapshot counter must be a nonnegative integer", "snapshot." + field)
	if not (state.get("entered") is bool) or not state["entered"]:
		return _error("snapshot must be at a settled instruction", "snapshot.entered")
	var node: Dictionary = _program["nodes"][state["node_id"]]
	if not state["presentation"].is_empty():
		var presentation_id: Variant = state["presentation"].get("id")
		if not _name(presentation_id) or not _program["nodes"].has(presentation_id) or not ["line", "choice"].has(_program["nodes"][presentation_id]["kind"]) or not Catalog.equivalent(state["presentation"], _program["nodes"][presentation_id]):
			return _error("snapshot presentation differs from authored content", "snapshot.presentation")
	if ["line", "choice"].has(node["kind"]) and not Catalog.equivalent(state["presentation"], node):
		return _error("snapshot current presentation is inconsistent", "snapshot.presentation")
	if node["kind"] == "choice":
		var available := false
		for option: Dictionary in node["options"]:
			var holds := true
			for key: String in option["condition"]:
				if not state["facts"].has(key) or not Catalog.equivalent(state["facts"][key], option["condition"][key]):
					holds = false
			available = available or holds
		if not available:
			return _error("snapshot choice has no available option", "snapshot.facts")
	if ["running", "suspended"].has(state["status"]) and not ["line", "choice", "wait"].has(node["kind"]):
		return _error("snapshot cannot resume an invisible instruction", "snapshot.node_id")
	if state["status"] == "ended":
		if node["kind"] != "end" or not (state.get("outcome") is String) or state["outcome"] != node["outcome"]:
			return _error("snapshot ending is inconsistent", "snapshot.outcome")
	elif state.get("outcome") != null:
		return _error("nonterminal snapshot cannot have an outcome", "snapshot.outcome")
	if state["facts"].size() != _program["facts"].size():
		return _error("snapshot fact declarations differ", "snapshot.facts")
	for key: Variant in state["facts"]:
		if not _program["facts"].has(key) or not Program.fact_value(state["facts"][key], _program["facts"][key]):
			return _error("snapshot fact value is invalid", "snapshot.facts")
	if state["clocks"].size() != Program.CLOCKS.size() or Refusal.is_refusal(_deltas(state["clocks"])):
		return _error("snapshot clocks are invalid", "snapshot.clocks")
	var known_seen := {}
	for id: Variant in state["seen"]:
		if not _name(id) or not _program["nodes"].has(id) or known_seen.has(id) or not ["line", "choice"].has(_program["nodes"][id]["kind"]):
			return _error("snapshot visible history is invalid", "snapshot.seen")
		known_seen[id] = true
	if ["line", "choice"].has(node["kind"]) and not known_seen.has(node["id"]):
		return _error("current presentation must be in visible history", "snapshot.seen")
	for id: Variant in state["visit_counts"]:
		if not _program["nodes"].has(id) or not _integer(state["visit_counts"][id]) or state["visit_counts"][id] < 1:
			return _error("snapshot visit identity is invalid", "snapshot.visit_counts")
	if not state["visit_counts"].has(node["id"]) or state["visit_id"] != "%s@%d" % [node["id"], int(state["visit_counts"][node["id"]])]:
		return _error("snapshot current visit is inconsistent", "snapshot.visit_id")
	var gate_names := {}
	for name: Variant in state["gate_events"]:
		if not _name(name) or gate_names.has(name):
			return _error("snapshot event history is invalid", "snapshot.gate_events")
		gate_names[name] = true
	for operation_id: Variant in state["operations"]:
		var operation: Variant = state["operations"][operation_id]
		if not _name(operation_id) or not (operation is Dictionary):
			return _error("snapshot operation is malformed", "snapshot.operations")
		for field in ["duration", "target", "result"]:
			if not operation.has(field):
				return _error("snapshot operation field is absent", "snapshot.operations." + field)
		for field in ["operation_id", "instance_id", "clock", "scope", "node_id", "visit_id", "status"]:
			if not _name(operation.get(field)):
				return _error("snapshot operation identity is malformed", "snapshot.operations")
		if operation["operation_id"] != operation_id or not operation_id.begins_with(state["session_id"] + ":operation:") or not Program.CLOCKS.has(operation["clock"]) or not ["node", "sequence"].has(operation["scope"]) or not ["running", "finished", "cancelled"].has(operation["status"]):
			return _error("snapshot operation identity is incompatible", "snapshot.operations")
		var sequence_text: String = operation_id.trim_prefix(state["session_id"] + ":operation:")
		if not sequence_text.is_valid_int() or int(sequence_text) < 1 or str(int(sequence_text)) != sequence_text or int(sequence_text) > int(state["operation_sequence"]):
			return _error("snapshot operation counter is inconsistent", "snapshot.operations")
		if not _duration(operation.get("start_time")) or float(operation["start_time"]) > float(state["clocks"][operation["clock"]]) or (operation.get("duration") != null and not _duration(operation["duration"])):
			return _error("snapshot operation timing is invalid", "snapshot.operations")
		if not _program["nodes"].has(operation["node_id"]) or not (operation.get("effect") is Dictionary):
			return _error("snapshot operation source is invalid", "snapshot.operations")
		if not _valid_visit(operation["visit_id"], operation["node_id"], state["visit_counts"]):
			return _error("snapshot operation visit is invalid", "snapshot.operations")
		var matched := false
		var origin: Dictionary = _program["nodes"][operation["node_id"]]
		var definitions: Array = [origin] if origin["kind"] == "effect" else origin.get("cues", [])
		for definition: Dictionary in definitions:
			if definition["instance_id"] == operation["instance_id"] and Catalog.equivalent(definition["effect"], operation["effect"]) and definition["clock"] == operation["clock"] and definition["scope"] == operation["scope"] and Catalog.equivalent(definition["target"], operation.get("target")) and Catalog.equivalent(definition["duration"], operation.get("duration")):
				matched = true
		if not matched:
			return _error("snapshot operation differs from authored content", "snapshot.operations")
		if operation["status"] == "running" and not _catalog["types"][operation["effect"]["type"]].get("reconstructable", false):
			return _error("active capability does not support reconstruction", "snapshot.operations")
		if operation["status"] == "running":
			if not ["running", "suspended"].has(state["status"]) or not state["instances"].has(operation["instance_id"]) or not Catalog.equivalent(state["instances"][operation["instance_id"]], operation_id):
				return _error("active snapshot operation has no current owner", "snapshot.operations")
			if operation["duration"] != null and float(operation["start_time"]) + float(operation["duration"]) <= float(state["clocks"][operation["clock"]]):
				return _error("active snapshot operation has already expired", "snapshot.operations")
			if operation["scope"] == "node" and operation["visit_id"] != state["visit_id"]:
				return _error("node-scoped operation survived its owning node", "snapshot.operations")
	if state["operations"].size() != int(state["operation_sequence"]):
		return _error("snapshot operation history is incomplete", "snapshot.operation_sequence")
	for instance: Variant in state["instances"]:
		if not _name(instance) or not (state["instances"][instance] is String) or not state["operations"].has(state["instances"][instance]) or state["operations"][state["instances"][instance]]["instance_id"] != instance:
			return _error("snapshot instance binding is invalid", "snapshot.instances")
	var cue_ids := {}
	for cue_id: Variant in state["fired_cues"]:
		if not _name(cue_id) or cue_ids.has(cue_id) or not _valid_cue_id(cue_id, state["visit_counts"]):
			return _error("snapshot fired cue history is invalid", "snapshot.fired_cues")
		cue_ids[cue_id] = true
	for cue: Variant in state["pending_cues"]:
		if not (cue is Dictionary) or not _name(cue.get("node_id")) or not _program["nodes"].has(cue["node_id"]) or not _name(cue.get("id")) or not _name(cue.get("cue_id")) or not _name(cue.get("visit_id")) or not Program.CLOCKS.has(cue.get("clock")):
			return _error("snapshot cue is malformed", "snapshot.pending_cues")
		if not cue.has("deadline") or cue_ids.has(cue["cue_id"]) or not _valid_visit(cue["visit_id"], cue["node_id"], state["visit_counts"]) or cue["cue_id"] != cue["visit_id"] + ":" + cue["id"]:
			return _error("snapshot cue identity is inconsistent", "snapshot.pending_cues")
		cue_ids[cue["cue_id"]] = true
		if cue.get("deadline") != null and not _duration(cue["deadline"]):
			return _error("snapshot cue deadline is invalid", "snapshot.pending_cues")
		var matched := false
		for definition: Dictionary in _program["nodes"][cue["node_id"]].get("cues", []):
			var candidate: Dictionary = cue.duplicate(true)
			for field in ["node_id", "visit_id", "cue_id", "deadline"]:
				candidate.erase(field)
			if Catalog.equivalent(candidate, definition):
				matched = true
		if not matched:
			return _error("snapshot cue differs from authored content", "snapshot.pending_cues")
		if cue["scope"] == "node" and cue["visit_id"] != state["visit_id"]:
			return _error("node-scoped cue survived its owning node", "snapshot.pending_cues")
		if cue["deadline"] != null and float(cue["deadline"]) <= float(state["clocks"][cue["clock"]]):
			return _error("snapshot contains a cue that is already due", "snapshot.pending_cues")
		if not ["running", "suspended"].has(state["status"]):
			return _error("terminal snapshot retains pending cues", "snapshot.pending_cues")
	for action: Variant in state["deferred_actions"]:
		if not (action is Dictionary) or not _validate_action(action).is_empty():
			return _error("snapshot deferred action is invalid", "snapshot.deferred_actions")
	if node["kind"] == "wait" and ["running", "suspended"].has(state["status"]):
		var wait: Dictionary = state["wait"]
		if not Catalog.equivalent(wait.get("node_id"), node["id"]) or not Catalog.equivalent(wait.get("clock"), node["clock"]):
			return _error("snapshot wait differs from current node", "snapshot.wait")
		if node.has("duration") and (not _duration(wait.get("deadline")) or float(wait["deadline"]) <= float(state["clocks"][node["clock"]])):
			return _error("snapshot time wait is not pending", "snapshot.wait")
		if node.has("operation") and (not (wait.get("operation_id") is String) or not state["operations"].has(wait["operation_id"]) or state["operations"][wait["operation_id"]]["instance_id"] != node["operation"] or state["operations"][wait["operation_id"]]["status"] != "running"):
			return _error("snapshot operation wait is not pending", "snapshot.wait")
		if node.has("event") and not Catalog.equivalent(wait.get("event"), node["event"]):
			return _error("snapshot host wait differs", "snapshot.wait")
	elif not state["wait"].is_empty():
		return _error("snapshot has a wait outside its instruction", "snapshot.wait")
	return {}


static func _valid_visit(visit_id: String, node_id: String, visits: Dictionary) -> bool:
	if not visits.has(node_id) or not visit_id.begins_with(node_id + "@"):
		return false
	var suffix := visit_id.trim_prefix(node_id + "@")
	return suffix.is_valid_int() and int(suffix) >= 1 and str(int(suffix)) == suffix and int(suffix) <= int(visits[node_id])


func _valid_cue_id(cue_id: String, visits: Dictionary) -> bool:
	for node: Dictionary in _program["nodes"].values():
		for cue: Dictionary in node.get("cues", []):
			var suffix: String = ":" + cue["id"]
			if cue_id.ends_with(suffix) and _valid_visit(cue_id.trim_suffix(suffix), node["id"], visits):
				return true
	return false


static func _duration(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= 0.0


static func _integer(value: Variant) -> bool:
	return _duration(value) and float(value) == floor(float(value))


static func _name(value: Variant) -> bool:
	return value is String and not value.is_empty()


static func _error(message: String, path: String) -> Dictionary:
	return Refusal.of("scenario/session", message, path)
