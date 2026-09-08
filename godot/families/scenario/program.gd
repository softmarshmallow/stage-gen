class_name FamilyScenarioProgram
extends RefCounted

## What a scenario program says, read once into the shape the runtime walks.
##
## A port of the runtime's half of `web/lib/scenario/program.ts`. The document is
## `lower_snake_case` on the wire and stays that way here: translating a
## persisted field name into a language-native one belongs at an explicit
## adapter, and the adapter for this genre is exactly this function.
##
## A scenario has no clock either, so like the room there is no roster and no
## sealed order — the whole runtime is a reducer over a finite graph.
##
## It is a **family** rather than a genre because two genres compose it: the
## dialogue scene plays one scenario, and a case plays several in order with a
## shared set of facts crossing between them. That is exactly the charter the
## host contract sets — a system with one consumer stays that genre's, and is
## promoted when the second genre asks for it.

const PROGRAM_KIND := "scenario-program-v2"
const PROGRAM_SCHEMA_VERSION := 2

## Where an actor may stand, left to right. Five, not three: the browser's
## `SCENARIO_SLOTS` publishes `far_left` and `far_right` too, and The Grain's
## scripts use both — `e1_statements` stands Robert at `far_left`. The constant
## was three when it was written and nothing referenced it, so nothing was
## refused and nothing was wrong; the moment a view laid the three out, half a
## cast would have been drawn in the middle of the stage.
const SLOTS := ["far_left", "left", "center", "right", "far_right"]

const STATEMENT_KINDS := [
	"line", "choice", "show", "hide", "stage", "audio", "set", "jump", "branch", "end"
]


## Read a program document, or refuse.
static func parse(document: Variant) -> Variant:
	if not (document is Dictionary):
		return KernelRefusal.of("scenario/program", "a scenario program must be a record")
	var doc: Dictionary = document
	if String(doc.get("kind", "")) != PROGRAM_KIND:
		return KernelRefusal.of(
			"scenario/program-kind",
			(
				"unsupported scenario program; regenerate this scenario with a current "
				+ "stage-gen (stage-gen scenario check)"
			),
			"kind"
		)
	if int(doc.get("schema_version", -1)) != PROGRAM_SCHEMA_VERSION:
		return KernelRefusal.of(
			"scenario/program-kind",
			(
				"unsupported scenario program; regenerate this scenario with a current "
				+ "stage-gen (stage-gen scenario check)"
			),
			"schema_version"
		)

	var cast: Array = []
	var cast_ids := {}
	for entry: Variant in _array(doc.get("cast")):
		var member: Dictionary = entry
		var actor_id := String(member.get("actor_id", ""))
		if actor_id.is_empty():
			return KernelRefusal.of("scenario/cast", "a cast member must name an actor_id", "cast")
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
			return KernelRefusal.of("scenario/blocks", "a block must name a label", "blocks")
		if labels.has(label):
			return KernelRefusal.of(
				"scenario/blocks", "blocks names %s twice" % label, "blocks"
			)
		labels[label] = true
		var statements: Array = []
		for raw: Variant in _array(block.get("statements")):
			var statement: Dictionary = raw
			var kind := String(statement.get("kind", ""))
			if not STATEMENT_KINDS.has(kind):
				return KernelRefusal.of(
					"scenario/blocks",
					"%s carries a statement of kind %s, which this build does not perform"
					% [label, kind],
					"blocks"
				)
			statements.append(_statement(statement, kind))
		blocks.append({"label": label, "statements": statements})

	var entry_label := String(doc.get("entry", ""))
	if not labels.has(entry_label):
		return KernelRefusal.of(
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
