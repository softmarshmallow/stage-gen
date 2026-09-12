extends RefCounted

## Admission and normalization of scenario-program-v2 documents.
## No game manifest, media loader, scene, clock or producer dependency.

const Refusal = preload("refusal.gd")

const PROGRAM_KIND := "scenario-program-v2"
const PROGRAM_SCHEMA_VERSION := 2

## The five supported stage slots. Rendering their positions is consumer-owned.
const SLOTS := ["far_left", "left", "center", "right", "far_right"]

const STATEMENT_KINDS := [
	"line", "choice", "show", "hide", "stage", "audio", "set", "jump", "branch", "end"
]


## Read a program document, or refuse.
static func parse(document: Variant) -> Variant:
	var failure := _validate_document(document)
	if not failure.is_empty():
		return failure
	var doc: Dictionary = document

	var cast: Array = []
	var cast_ids := {}
	for entry: Variant in _array(doc.get("cast")):
		var member: Dictionary = entry
		var actor_id := String(member.get("actor_id", ""))
		if actor_id.is_empty():
			return Refusal.of("scenario/cast", "a cast member must name an actor_id", "cast")
		cast_ids[actor_id] = true
		cast.append(
			{
				"actorId": actor_id,
				# An actor with no display name is spoken of by its id, which is
				# what a nameless player character wants.
				"displayName": String(member.get("display_name", actor_id)),
				"expressions": _strings(member.get("expressions")),
			}
		)

	var blocks: Array = []
	var labels := {}
	for entry: Variant in _array(doc.get("blocks")):
		var block: Dictionary = entry
		var label := String(block.get("label", ""))
		if label.is_empty():
			return Refusal.of("scenario/blocks", "a block must name a label", "blocks")
		if labels.has(label):
			return Refusal.of(
				"scenario/blocks", "blocks names %s twice" % label, "blocks"
			)
		labels[label] = true
		var statements: Array = []
		for raw: Variant in _array(block.get("statements")):
			var statement: Dictionary = raw
			var kind := String(statement.get("kind", ""))
			if not STATEMENT_KINDS.has(kind):
				return Refusal.of(
					"scenario/blocks",
					"%s carries a statement of kind %s, which this build does not perform"
					% [label, kind],
					"blocks"
				)
			if kind == "show" and not SLOTS.has(String(statement.get("slot", ""))):
				return Refusal.of(
					"scenario/blocks",
					(
						"%s stages an actor at %s, which is not one of the five slots "
						+ "this build publishes"
					) % [label, statement.get("slot", "(none)")],
					"blocks"
				)
			statements.append(_statement(statement, kind))
		blocks.append({"label": label, "statements": statements})

	var entry_label := String(doc.get("entry", ""))
	if not labels.has(entry_label):
		return Refusal.of(
			"scenario/entry",
			"the scenario enters at %s, which it does not publish" % entry_label,
			"entry"
		)

	return {
		"scenarioId": String(doc.get("scenario_id", "")),
		"displayName": String(doc.get("display_name", "")),
		"entry": entry_label,
		"cast": cast,
		"blocks": blocks,
		"stages": _ids(doc.get("stages"), "stage_id"),
		"tracks": _ids(doc.get("tracks"), "track_id"),
		"flags": _ids(doc.get("flags"), "flag_id"),
		"endings": _endings(doc.get("endings")),
		# A scenario played inside a case may be handed facts an earlier beat
		# set; a scenario played alone imports none. Which flags those are is a
		# property of each flag's own declaration — `origin = "imported"` — rather
		# than a second list, so a flag cannot be importable in one place and not
		# in another.
		"importedFlags": _imported(doc.get("flags")),
	}


static func block_of(program: Dictionary, label: String) -> Dictionary:
	for entry: Variant in (program["blocks"] as Array):
		var block: Dictionary = entry
		if String(block["label"]) == label:
			return block
	return {}


static func total_statements(program: Dictionary) -> int:
	var total := 0
	for entry: Variant in (program["blocks"] as Array):
		total += ((entry as Dictionary)["statements"] as Array).size()
	return total


static func speaker_label(program: Dictionary, actor_id: String) -> String:
	for entry: Variant in (program["cast"] as Array):
		var member: Dictionary = entry
		if String(member["actorId"]) == actor_id:
			return String(member["displayName"])
	return actor_id


static func _statement(statement: Dictionary, kind: String) -> Dictionary:
	var made := {"kind": kind}
	match kind:
		"line":
			made["text"] = String(statement.get("text", ""))
			made["speaker"] = statement.get("speaker")
			made["expression"] = statement.get("expression")
		"choice":
			var options: Array = []
			for raw: Variant in _array(statement.get("options")):
				var option: Dictionary = raw
				options.append(
					{
						"text": String(option.get("text", "")),
						"target": String(option.get("target", "")),
						"condition": _condition(option.get("condition")),
					}
				)
			made["options"] = options
		"show":
			made["actor"] = String(statement.get("actor", ""))
			made["slot"] = String(statement.get("slot", "center"))
			made["expression"] = statement.get("expression")
		"hide":
			made["actor"] = String(statement.get("actor", ""))
		"stage":
			made["stage"] = String(statement.get("stage", ""))
		"audio":
			made["track"] = String(statement.get("track", ""))
			made["action"] = String(statement.get("action", "play"))
		"set":
			made["flag"] = String(statement.get("flag", ""))
			made["value"] = bool(statement.get("value", true))
		"jump":
			made["target"] = String(statement.get("target", ""))
		"branch":
			var edges: Array = []
			for raw: Variant in _array(statement.get("edges")):
				var edge: Dictionary = raw
				edges.append(
					{
						"target": String(edge.get("target", "")),
						"condition": _condition(edge.get("condition")),
					}
				)
			made["edges"] = edges
			made["default"] = String(statement.get("default", ""))
		"end":
			made["outcome"] = String(statement.get("outcome", ""))
	return made


## A condition, or an empty one — which every flag satisfies.
static func _condition(value: Variant) -> Dictionary:
	if not (value is Dictionary):
		return {}
	var condition: Dictionary = value
	return {
		"requires": _strings(condition.get("requires")),
		"forbids": _strings(condition.get("forbids")),
	}


static func _endings(value: Variant) -> Array:
	var made: Array = []
	for entry: Variant in _array(value):
		var ending: Dictionary = entry
		made.append(
			{
				"outcomeId": String(ending.get("outcome_id", "")),
				"label": String(ending.get("label", "")),
			}
		)
	return made


## The flags this scenario opens holding, when a case hands them to it.
static func _imported(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in _array(value):
		var flag: Dictionary = entry
		if String(flag.get("origin", "local")) == "imported":
			made.append(String(flag.get("flag_id", "")))
	return made


static func _ids(value: Variant, key: String) -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in _array(value):
		made.append(String((entry as Dictionary).get(key, "")))
	return made


static func _array(value: Variant) -> Array:
	return value if value is Array else []


static func _strings(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in _array(value):
		made.append(String(entry))
	return made


## Validate only the vocabulary this interpreter consumes. Unknown metadata is
## ignored; this is not the producer's asset, provenance or complete JSON schema.
static func _validate_document(document: Variant) -> Dictionary:
	if not (document is Dictionary):
		return _malformed("a scenario program must be a record", "")
	var doc: Dictionary = document
	if doc.get("kind") != PROGRAM_KIND:
		return Refusal.of("scenario/program-kind", "expected scenario-program-v2", "kind")
	var version: Variant = doc.get("schema_version")
	if not (version is int or version is float) or version != PROGRAM_SCHEMA_VERSION:
		return Refusal.of("scenario/program-kind", "expected schema_version 2", "schema_version")
	for key in ["scenario_id", "display_name", "entry"]:
		var failure := _text(doc, key, "", key == "entry")
		if not failure.is_empty():
			return failure
	var registries := {}
	var fields := {"cast": "actor_id", "stages": "stage_id", "tracks": "track_id", "flags": "flag_id", "endings": "outcome_id", "blocks": "label"}
	for collection: String in fields:
		var values: Variant = doc.get(collection, [])
		if not (values is Array):
			return _malformed("expected an array", collection)
		var registry := {}
		for i in values.size():
			var path := "%s[%d]" % [collection, i]
			if not (values[i] is Dictionary):
				return _malformed("expected a record", path)
			var entry: Dictionary = values[i]
			var field: String = fields[collection]
			var failure := _text(entry, field, path, true)
			if not failure.is_empty():
				return failure
			var id: String = entry[field]
			if registry.has(id):
				return _malformed("duplicate identifier %s" % id, path + "." + field)
			registry[id] = entry
			for text_field in ["display_name", "label", "origin"]:
				failure = _text(entry, text_field, path)
				if not failure.is_empty():
					return failure
			if collection == "cast":
				failure = _string_list(entry.get("expressions", []), path + ".expressions")
				if not failure.is_empty():
					return failure
			if collection == "flags" and not ["local", "imported"].has(entry.get("origin", "local")):
				return _malformed("flag origin must be local or imported", path + ".origin")
		registries[collection] = registry
	if not registries["blocks"].has(doc["entry"]):
		return Refusal.of("scenario/entry", "entry must name a published block", "entry")
	for block_index in doc.get("blocks", []).size():
		var block: Dictionary = doc["blocks"][block_index]
		var path := "blocks[%d].statements" % block_index
		var statements: Variant = block.get("statements")
		if not (statements is Array) or statements.is_empty():
			return _malformed("a block needs a nonempty statements array", path)
		for i in statements.size():
			var failure := _validate_statement(statements[i], "%s[%d]" % [path, i], registries)
			if not failure.is_empty():
				return failure
	return {}


static func _validate_statement(value: Variant, path: String, registries: Dictionary) -> Dictionary:
	if not (value is Dictionary):
		return _malformed("expected a statement record", path)
	var statement: Dictionary = value
	var kind: Variant = statement.get("kind")
	if not STATEMENT_KINDS.has(kind):
		return _malformed("unsupported statement kind", path + ".kind")
	var references := {}
	match kind:
		"line":
			var failure := _text(statement, "text", path)
			if not failure.is_empty():
				return failure
			failure = _text(statement, "speaker", path, false, true)
			if not failure.is_empty():
				return failure
			if statement.get("speaker") != null:
				references["speaker"] = "cast"
		"show", "hide":
			references["actor"] = "cast"
			if kind == "show" and not SLOTS.has(statement.get("slot")):
				return _malformed("unsupported actor slot", path + ".slot")
		"stage":
			references["stage"] = "stages"
		"audio":
			references["track"] = "tracks"
			if not ["play", "stop"].has(statement.get("action", "play")):
				return _malformed("audio action must be play or stop", path + ".action")
		"set":
			references["flag"] = "flags"
			if not (statement.get("value", true) is bool):
				return _malformed("flag value must be boolean", path + ".value")
		"jump":
			references["target"] = "blocks"
		"end":
			references["outcome"] = "endings"
		"choice", "branch":
			var field := "options" if kind == "choice" else "edges"
			var edges: Variant = statement.get(field)
			if not (edges is Array):
				return _malformed("expected an array", path + "." + field)
			if kind == "choice" and edges.is_empty():
				return _malformed("a choice needs at least one option", path + ".options")
			for i in edges.size():
				var edge_path := "%s.%s[%d]" % [path, field, i]
				if not (edges[i] is Dictionary):
					return _malformed("expected a branch record", edge_path)
				var edge: Dictionary = edges[i]
				var failure := _reference(edge, "target", edge_path, registries["blocks"])
				if not failure.is_empty():
					return failure
				failure = _text(edge, "text", edge_path)
				if not failure.is_empty():
					return failure
				failure = _validate_condition(edge.get("condition"), edge_path + ".condition", registries["flags"])
				if not failure.is_empty():
					return failure
			if kind == "branch":
				references["default"] = "blocks"
	for field: String in references:
		var failure := _reference(statement, field, path, registries[references[field]])
		if not failure.is_empty():
			return failure
	if kind == "line" or kind == "show":
		var failure := _text(statement, "expression", path, false, true)
		if not failure.is_empty():
			return failure
		if statement.get("expression") != null:
			var actor_id: Variant = statement.get("speaker") if kind == "line" else statement.get("actor")
			if actor_id == null or not registries["cast"][actor_id].get("expressions", []).has(statement["expression"]):
				return Refusal.of("scenario/unresolved", "expression must be declared by its actor", path + ".expression")
	return {}


static func _validate_condition(value: Variant, path: String, flags: Dictionary) -> Dictionary:
	if value == null:
		return {}
	if not (value is Dictionary):
		return _malformed("expected a condition record or null", path)
	for field in ["requires", "forbids"]:
		var values: Variant = value.get(field, [])
		var failure := _string_list(values, path + "." + field)
		if not failure.is_empty():
			return failure
		for flag: String in values:
			if not flags.has(flag):
				return Refusal.of("scenario/unresolved", "condition flag is not declared", path + "." + field)
	return {}


static func _reference(record: Dictionary, field: String, path: String, registry: Dictionary) -> Dictionary:
	var failure := _text(record, field, path, true)
	if not failure.is_empty():
		return failure
	if not registry.has(record[field]):
		return Refusal.of("scenario/unresolved", "reference is not declared: %s" % record[field], path + "." + field)
	return {}


static func _text(record: Dictionary, field: String, path: String, required: bool = false, nullable: bool = false) -> Dictionary:
	var value: Variant = record.get(field)
	if (not record.has(field) and not required) or (nullable and value == null):
		return {}
	if not (value is String) or (required and value.is_empty()):
		return _malformed("expected %sstring" % ("a nonempty " if required else "a "), path + ("." if path != "" else "") + field)
	return {}


static func _string_list(value: Variant, path: String) -> Dictionary:
	if not (value is Array):
		return _malformed("expected an array of strings", path)
	for i in value.size():
		if not (value[i] is String):
			return _malformed("expected a string", "%s[%d]" % [path, i])
	return {}


static func _malformed(message: String, path: String) -> Dictionary:
	return Refusal.of("scenario/malformed", message, path)
