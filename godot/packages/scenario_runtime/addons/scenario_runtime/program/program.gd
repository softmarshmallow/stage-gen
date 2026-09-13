extends RefCounted

## Closed v3 instruction admission. No game manifest, I/O or scene dependency.
const Catalog = preload("catalog.gd")
const Refusal = preload("../refusal.gd")
const KINDS := ["line", "choice", "branch", "set", "jump", "effect", "stop", "wait", "end"]
const CLOCKS := ["sequence", "presentation", "reading"]

static func parse(document: Variant, catalog: Dictionary) -> Dictionary:
	var failure := _strict_shape(document)
	if not failure.is_empty():
		return failure
	var program := from_v2_adapter(document, catalog)
	if Refusal.is_refusal(program):
		return program
	for capability: String in program["required_capabilities"]:
		if not catalog["types"].has(capability) or catalog["types"][capability]["version"] != program["required_capabilities"][capability]:
			return _error("required installed capability version is unavailable", "required_capabilities." + capability)
	failure = _flow(program)
	return failure if not failure.is_empty() else program


## The maintained v2 reader preserves its older admission policy and statement
## identities. It still uses all v3 type/reference normalization and one Session
## executor; downloaded v3 documents must use parse(), including flow admission.
static func from_v2_adapter(document: Variant, catalog: Dictionary) -> Dictionary:
	if not (document is Dictionary):
		return _error("program must be a record", "program")
	if not _name(document.get("kind")) or document["kind"] != "scenario-program-v3":
		return _error("expected scenario-program-v3", "kind")
	var version: Variant = document.get("schema_version")
	if not (version is int or version is float) or version != 3:
		return _error("expected schema_version 3", "schema_version")
	for key in ["scenario_id", "entry"]:
		if not _name(document.get(key)):
			return _error("program identity and entry must be nonempty", key)
	if not (document.get("nodes") is Array) or document["nodes"].is_empty():
		return _error("nodes must be a nonempty array", "nodes")
	var facts: Variant = document.get("facts", {})
	if not (facts is Dictionary):
		return _error("facts must be a record", "facts")
	for key: Variant in facts:
		if not _name(key) or not (facts[key] is Dictionary):
			return _error("fact must have a named declaration", "facts")
		var definition: Dictionary = facts[key]
		if not (definition.get("type") is String) or not ["boolean", "string"].has(definition["type"]):
			return _error("facts support boolean or finite string values", "facts." + key)
		if definition.has("external") and not (definition["external"] is bool):
			return _error("external must be boolean", "facts." + key)
		if definition["type"] == "string" and (not (definition.get("values") is Array) or definition["values"].is_empty()):
			return _error("string fact needs its finite values", "facts." + key)
		if not fact_value(definition.get("default", false if definition["type"] == "boolean" else null), definition):
			return _error("fact default must match its declaration", "facts." + key)
	var speakers := {}
	if not (document.get("speakers", []) is Array):
		return _error("speakers must be an array", "speakers")
	for speaker: Variant in document.get("speakers", []):
		if not (speaker is Dictionary) or not _name(speaker.get("id")) or speakers.has(speaker["id"]):
			return _error("speaker needs a unique id", "speakers")
		if not (speaker.get("display_name", speaker["id"]) is String):
			return _error("speaker display name must be text", "speakers")
		speakers[speaker["id"]] = {"id": speaker["id"], "display_name": speaker.get("display_name", speaker["id"])}
	var requirements: Variant = document.get("required_capabilities", {})
	if not (requirements is Dictionary):
		return _error("required_capabilities must be a record", "required_capabilities")
	requirements = requirements.duplicate(true)
	for key: Variant in requirements:
		if not _name(key) or not (requirements[key] is int or requirements[key] is float) or requirements[key] < 1 or requirements[key] != floor(float(requirements[key])):
			return _error("capability requirement needs a positive integer version", "required_capabilities")
	var nodes := {}
	var order: Array = []
	for raw: Variant in document["nodes"]:
		if not (raw is Dictionary) or not _name(raw.get("id")) or nodes.has(raw["id"]):
			return _error("node needs a unique stable id", "nodes")
		if not (raw.get("kind") is String) or not KINDS.has(raw["kind"]):
			return _error("unknown instruction kind", raw["id"])
		var node := _node(raw, catalog, facts, speakers)
		if Refusal.is_refusal(node):
			return node
		nodes[raw["id"]] = node
		order.append(raw["id"])
		var effects: Array = [node] if node["kind"] == "effect" else node.get("cues", [])
		for effect: Dictionary in effects:
			var capability: String = effect["effect"]["type"]
			var required: int = effect["effect"]["version"]
			if requirements.has(capability) and requirements[capability] != required:
				return _error("effect conflicts with required capability version", raw["id"])
			requirements[capability] = required
	if not nodes.has(document["entry"]):
		return _error("entry does not name a node", "entry")
	for id: String in order:
		var node: Dictionary = nodes[id]
		var targets: Array = []
		if node.has("next"):
			targets.append(node["next"])
		match node["kind"]:
			"jump": targets.append(node["target"])
			"choice":
				for option: Dictionary in node["options"]:
					targets.append(option["target"])
			"branch":
				targets.append(node["default"])
				for edge: Dictionary in node["edges"]:
					targets.append(edge["target"])
		for target: Variant in targets:
			if not nodes.has(target):
				return _error("target does not name a node", id + ".target")
	var program := {"scenario_id": document["scenario_id"], "entry": document["entry"], "nodes": nodes, "order": order, "speakers": speakers, "facts": facts.duplicate(true), "required_capabilities": requirements, "catalog_fingerprint": catalog["fingerprint"]}
	program["fingerprint"] = Catalog.digest(program)
	return program


static func _strict_shape(document: Variant) -> Dictionary:
	if not (document is Dictionary):
		return _error("program must be a record", "program")
	if Refusal.is_refusal(Catalog.validate_value(document, {"type": "json"}, "program")):
		return _error("program must contain portable JSON values", "program")
	var failure := _closed(document, ["kind", "schema_version", "scenario_id", "entry", "nodes", "speakers", "facts", "required_capabilities", "source_map", "metadata"], "program")
	if not failure.is_empty():
		return failure
	for field in ["scenario_id", "entry"]:
		if not _logical(document.get(field)):
			return _error("expected a stable logical identifier", field)
	if not (document.get("nodes") is Array) or document["nodes"].is_empty() or document["nodes"].size() > 10000:
		return _error("expected between 1 and 10000 nodes", "nodes")
	if document.get("facts", {}) is Dictionary:
		for key: Variant in document.get("facts", {}):
			var fact: Variant = document["facts"][key]
			if not _logical(key) or not (fact is Dictionary):
				return _error("fact declaration must be named", "facts")
			failure = _closed(fact, ["type", "default", "values", "external"], "facts." + key)
			if not failure.is_empty():
				return failure
			if not fact.has("default"):
				return _error("fact must declare its default", "facts." + key)
			if fact.has("values"):
				if not (fact.get("type") is String) or fact["type"] != "string" or not (fact["values"] is Array):
					return _error("values requires a finite string fact", "facts." + key)
				var known := {}
				for value: Variant in fact["values"]:
					if not (value is String) or known.has(value):
						return _error("fact values must be unique strings", "facts." + key)
					known[value] = true
	if document.get("speakers", []) is Array:
		for speaker: Variant in document.get("speakers", []):
			if not (speaker is Dictionary) or not _logical(speaker.get("id")):
				return _error("speaker must have a stable id", "speakers")
			failure = _closed(speaker, ["id", "display_name"], "speakers")
			if not failure.is_empty():
				return failure
			if speaker.has("display_name") and (not (speaker["display_name"] is String) or speaker["display_name"].strip_edges().is_empty()):
				return _error("display_name must contain text", "speakers")
	var fields := {
		"line": ["text", "text_key", "speaker", "expression", "presentation", "cues", "next", "gates", "advance_mode"],
		"choice": ["options", "text", "text_key", "speaker", "expression", "presentation", "cues", "gates"],
		"branch": ["edges", "default"], "set": ["values", "next"], "jump": ["target"],
		"effect": ["effect", "instance_id", "target", "scope", "duration", "clock", "next"],
		"stop": ["instance_id", "next"], "wait": ["duration", "clock", "operation", "event", "next"], "end": ["outcome"],
	}
	for node: Variant in document["nodes"]:
		if not (node is Dictionary) or not _logical(node.get("id")) or not (node.get("kind") is String) or not fields.has(node["kind"]):
			return _error("node requires a stable id and supported kind", "nodes")
		var id: String = node["id"]
		failure = _closed(node, ["id", "kind"] + fields[node["kind"]], id)
		if not failure.is_empty():
			return failure
		for field in ["next", "speaker", "expression", "target", "default", "instance_id", "operation", "event", "outcome"]:
			if node.has(field) and not _logical(node[field]):
				return _error("expected a stable logical identifier", id + "." + field)
		if node.has("expression") and not node.has("speaker"):
			return _error("expression requires a speaker", id)
		if node["kind"] == "line" or node.has("text") or node.has("text_key"):
			failure = _strict_text(node, id)
			if not failure.is_empty():
				return failure
		if node.has("gates") and node["gates"] is Array:
			for gate: Variant in node["gates"]:
				if not (gate is Dictionary) or not _logical(gate.get("event")):
					return _error("gate needs a named event", id)
				failure = _closed(gate, ["event", "finish_on_advance"], id + ".gates")
				if not failure.is_empty():
					return failure
		if node.get("advance_mode") is String and node["advance_mode"] == "on_gates":
			if not (node.get("gates") is Array) or node["gates"].is_empty():
				return _error("on_gates needs at least one explicit gate", id)
		if node.has("cues") and node["cues"] is Array:
			for cue: Variant in node["cues"]:
				if not (cue is Dictionary) or not _logical(cue.get("id")):
					return _error("cue needs a stable id", id)
				failure = _closed(cue, ["id", "at", "on", "after", "effect", "instance_id", "target", "scope", "duration", "clock"], id + ".cues")
				if not failure.is_empty():
					return failure
				for field in ["instance_id", "target", "on"]:
					if cue.has(field) and not _logical(cue[field]):
						return _error("cue reference needs a stable id", id + ".cues")
				if cue.has("at") and cue.has("after"):
					return _error("after is only supported on an event cue", id + ".cues")
				if cue.has("duration") and not _duration(cue["duration"]):
					return _error("duration must be finite and nonnegative", id + ".cues")
		if node["kind"] == "choice" and node.get("options") is Array:
			if node["options"].size() > 64:
				return _error("choice supports at most 64 options", id)
			for option: Variant in node["options"]:
				if not (option is Dictionary) or not _logical(option.get("id")) or not _logical(option.get("target")):
					return _error("choice needs stable option and target ids", id)
				failure = _closed(option, ["id", "text", "text_key", "target", "condition", "set"], id + ".options")
				if not failure.is_empty():
					return failure
				failure = _strict_text(option, id + ".options")
				if not failure.is_empty():
					return failure
		if node["kind"] == "branch":
			if not (node.get("edges") is Array) or node["edges"].is_empty():
				return _error("branch needs nonempty edges", id)
			for edge: Variant in node["edges"]:
				if not (edge is Dictionary) or not edge.has("condition") or not _logical(edge.get("target")):
					return _error("branch edge needs condition and target", id)
				failure = _closed(edge, ["condition", "target"], id + ".edges")
				if not failure.is_empty():
					return failure
		if node["kind"] == "set" and not node.has("values"):
			return _error("set requires explicit values", id)
		if node["kind"] == "wait" and node.has("clock") and not node.has("duration"):
			return _error("clock only applies to duration waits", id)
		if node.has("duration") and not _duration(node["duration"]):
			return _error("duration must be finite and nonnegative", id)
	return {}


static func _flow(program: Dictionary) -> Dictionary:
	var graph := {}
	var invisible := {}
	for node: Dictionary in program["nodes"].values():
		var targets: Array = []
		if node.has("next"): targets.append(node["next"])
		if node["kind"] == "jump": targets.append(node["target"])
		if node["kind"] == "branch":
			targets.append(node["default"])
			for edge: Dictionary in node["edges"]: targets.append(edge["target"])
		if node["kind"] == "choice":
			for option: Dictionary in node["options"]: targets.append(option["target"])
		graph[node["id"]] = targets
		if not ["line", "choice", "wait", "end"].has(node["kind"]) or (node["kind"] == "wait" and node.get("duration", -1.0) == 0.0):
			invisible[node["id"]] = 0
	var visited := {}
	var pending: Array = [program["entry"]]
	var has_ending := false
	while not pending.is_empty():
		var id: String = pending.pop_back()
		if visited.has(id): continue
		visited[id] = true
		has_ending = has_ending or program["nodes"][id]["kind"] == "end"
		pending.append_array(graph[id])
	if visited.size() != graph.size():
		return _error("program declares unreachable nodes", "nodes")
	if not has_ending:
		return _error("program has no reachable ending", "nodes")
	for id: String in invisible:
		for target: String in graph[id]:
			if invisible.has(target): invisible[target] += 1
	pending = []
	for id: String in invisible:
		if invisible[id] == 0: pending.append(id)
	while not pending.is_empty():
		var id: String = pending.pop_back()
		invisible.erase(id)
		for target: String in graph[id]:
			if invisible.has(target):
				invisible[target] -= 1
				if invisible[target] == 0: pending.append(target)
	if not invisible.is_empty():
		return _error("program has an invisible instruction cycle", "nodes")
	return {}


static func _closed(value: Dictionary, fields: Array, path: String) -> Dictionary:
	for key: Variant in value:
		if not fields.has(key):
			return _error("unknown instruction field", path + "." + str(key))
	return {}


static func _strict_text(value: Dictionary, path: String) -> Dictionary:
	if value.has("text") == value.has("text_key"):
		return _error("exactly one of text or text_key is required", path)
	var text: Variant = value.get("text", value.get("text_key"))
	return {} if text is String and not text.strip_edges().is_empty() else _error("text must be nonempty", path)


static func _logical(value: Variant) -> bool:
	if not (value is String) or value.is_empty() or value.length() > 128:
		return false
	var first := "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
	if not first.contains(value[0]):
		return false
	for glyph: String in value:
		if not (first + "_.:-").contains(glyph):
			return false
	return true


static func _node(raw: Dictionary, catalog: Dictionary, facts: Dictionary, speakers: Dictionary) -> Dictionary:
	var id: String = raw["id"]
	var kind: String = raw["kind"]
	var node := {"id": id, "kind": kind}
	if ["line", "set", "effect", "stop", "wait"].has(kind):
		if not _name(raw.get("next")):
			return _error("instruction needs next", id + ".next")
		node["next"] = raw["next"]
	match kind:
		"line", "choice":
			if not (raw.get("gates", []) is Array) or not ["manual", "on_gates"].has(raw.get("advance_mode", "manual")):
				return _error("presentation gates or advance mode are invalid", id)
			if kind == "choice" and raw.get("advance_mode", "manual") != "manual":
				return _error("a choice requires explicit selection", id)
			node["gates"] = []
			node["advance_mode"] = raw.get("advance_mode", "manual")
			var gate_names := {}
			for gate: Variant in raw.get("gates", []):
				if not (gate is Dictionary) or not _name(gate.get("event")) or gate_names.has(gate["event"]) or not (gate.get("finish_on_advance", false) is bool):
					return _error("gate needs a unique event and boolean finish policy", id)
				gate_names[gate["event"]] = true
				node["gates"].append({"event": gate["event"], "finish_on_advance": gate.get("finish_on_advance", false)})
			var presentation: Variant = raw.get("presentation", {})
			if not (presentation is Dictionary):
				return _error("presentation must be a record", id)
			var checked := Catalog.validate_value(presentation, {"type": "json"}, id + ".presentation")
			if Refusal.is_refusal(checked):
				return checked
			node["presentation"] = presentation.duplicate(true)
			for field in ["channel", "profile"]:
				if not _name(presentation.get(field, "dialogue" if field == "channel" else "bottom")):
					return _error("presentation selection must be named", id + ".presentation." + field)
				node["presentation"][field] = presentation.get(field, "dialogue" if field == "channel" else "bottom")
	if kind == "line" or kind == "choice":
		if kind == "line" or raw.has("text") or raw.has("text_key"):
			var text_failure := _text(raw, node, id)
			if not text_failure.is_empty():
				return text_failure
		for field in ["speaker", "expression"]:
			if raw.get(field) != null and not _name(raw[field]):
				return _error("speaker and expression must be names", id + "." + field)
			node[field] = raw.get(field)
		if node["speaker"] != null and not speakers.has(node["speaker"]):
			return _error("speaker is not declared", id + ".speaker")
		if not (raw.get("cues", []) is Array):
			return _error("cues must be an array", id)
		node["cues"] = []
		var cue_ids := {}
		for cue: Variant in raw.get("cues", []):
			if not (cue is Dictionary) or not _name(cue.get("id")) or cue_ids.has(cue["id"]):
				return _error("cue needs a unique id within its line", id + ".cues")
			cue_ids[cue["id"]] = true
			if cue.has("at") == cue.has("on"):
				return _error("cue needs exactly one at time or on event", id + ".cues." + cue["id"])
			var normalized := _effect(cue, catalog, id + ".cues." + cue["id"], "node")
			if Refusal.is_refusal(normalized):
				return normalized
			normalized["id"] = cue["id"]
			if cue.has("at"):
				if not _duration(cue["at"]):
					return _error("cue time must be finite and nonnegative", id)
				normalized["at"] = float(cue["at"])
			else:
				if not _name(cue["on"]) or not _duration(cue.get("after", 0.0)):
					return _error("cue event and delay are invalid", id)
				normalized["on"] = cue["on"]
				normalized["after"] = float(cue.get("after", 0.0))
			node["cues"].append(normalized)
	if kind == "choice":
		if not (raw.get("options") is Array) or raw["options"].is_empty():
			return _error("choice needs options", id)
		node["options"] = []
		var option_ids := {}
		for option: Variant in raw["options"]:
			if not (option is Dictionary) or not _name(option.get("id")) or option_ids.has(option["id"]) or not _name(option.get("target")):
				return _error("choice option needs unique id and target", id)
			option_ids[option["id"]] = true
			var normalized := {"id": option["id"], "target": option["target"]}
			var failure := _text(option, normalized, id + "." + option["id"])
			if not failure.is_empty():
				return failure
			for field in ["condition", "set"]:
				failure = _facts(option.get(field, {}), facts, field == "set", id + "." + option["id"] + "." + field)
				if not failure.is_empty():
					return failure
				normalized[field] = option.get(field, {}).duplicate(true)
			node["options"].append(normalized)
	elif kind == "branch":
		if not _name(raw.get("default")) or not (raw.get("edges", []) is Array):
			return _error("branch needs default and edges", id)
		node["default"] = raw["default"]
		node["edges"] = []
		for edge: Variant in raw.get("edges", []):
			if not (edge is Dictionary) or not _name(edge.get("target")):
				return _error("branch edge needs target", id)
			var failure := _facts(edge.get("condition", {}), facts, false, id + ".condition")
			if not failure.is_empty():
				return failure
			node["edges"].append({"target": edge["target"], "condition": edge.get("condition", {}).duplicate(true)})
	elif kind == "set":
		var failure := _facts(raw.get("values", {}), facts, true, id + ".values")
		if not failure.is_empty():
			return failure
		node["values"] = raw.get("values", {}).duplicate(true)
	elif kind == "jump":
		if not _name(raw.get("target")):
			return _error("jump needs target", id)
		node["target"] = raw["target"]
	elif kind == "effect":
		var effect := _effect(raw, catalog, id, "sequence")
		if Refusal.is_refusal(effect):
			return effect
		node.merge(effect)
	elif kind == "stop":
		if not _name(raw.get("instance_id")):
			return _error("stop needs instance_id", id)
		node["instance_id"] = raw["instance_id"]
	elif kind == "wait":
		var modes := 0
		for field in ["duration", "operation", "event"]:
			if raw.has(field):
				modes += 1
				if (field == "duration" and not _duration(raw[field])) or (field != "duration" and not _name(raw[field])):
					return _error("invalid wait target", id + "." + field)
				node[field] = float(raw[field]) if field == "duration" else raw[field]
		if modes != 1 or not CLOCKS.has(raw.get("clock", "sequence")):
			return _error("wait needs one mode and a supported clock", id)
		node["clock"] = raw.get("clock", "sequence")
	elif kind == "end":
		if not _name(raw.get("outcome")):
			return _error("end needs an outcome", id)
		node["outcome"] = raw["outcome"]
	return node


static func _effect(raw: Dictionary, catalog: Dictionary, path: String, default_scope: String) -> Dictionary:
	var effect := Catalog.resolve(raw.get("effect"), catalog, path + ".effect")
	if Refusal.is_refusal(effect):
		return effect
	if not _name(raw.get("instance_id")):
		return _error("effect needs instance_id", path)
	if raw.get("target") != null and not _name(raw["target"]):
		return _error("effect target must be a binding id", path)
	if not ["node", "sequence"].has(raw.get("scope", default_scope)) or not CLOCKS.has(raw.get("clock", "presentation")):
		return _error("unsupported effect scope or clock", path)
	if raw.get("duration") != null and not _duration(raw["duration"]):
		return _error("effect duration must be finite and nonnegative", path)
	return {"effect": effect, "instance_id": raw["instance_id"], "target": raw.get("target"), "scope": raw.get("scope", default_scope), "clock": raw.get("clock", "presentation"), "duration": raw.get("duration")}


static func _text(raw: Dictionary, target: Dictionary, path: String) -> Dictionary:
	if not raw.has("text") and not raw.has("text_key"):
		return _error("presentation needs text or text_key", path)
	for field in ["text", "text_key"]:
		if raw.has(field):
			if not (raw[field] is String) or (field == "text_key" and raw[field].is_empty()):
				return _error("text and text_key must be strings", path + "." + field)
			target[field] = raw[field]
	return {}


static func _facts(values: Variant, declarations: Dictionary, writable: bool, path: String) -> Dictionary:
	if not (values is Dictionary):
		return _error("facts must be a record", path)
	for key: Variant in values:
		if not (key is String) or not declarations.has(key) or not fact_value(values[key], declarations[key]):
			return _error("unknown fact or invalid value", path + "." + str(key))
		if writable and declarations[key].get("external", false):
			return _error("scenario cannot assign an external fact", path + "." + key)
	return {}


static func fact_value(value: Variant, declaration: Dictionary) -> bool:
	if declaration.get("type") == "boolean":
		return value is bool
	return value is String and declaration.get("values", []).has(value)


static func _duration(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= 0.0


static func _name(value: Variant) -> bool:
	return value is String and not value.is_empty()


static func _error(message: String, path: String) -> Dictionary:
	return Refusal.of("scenario/program", message, path)
