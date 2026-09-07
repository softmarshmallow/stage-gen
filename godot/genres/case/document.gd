class_name CaseDocument
extends RefCounted

## A case: several leaves played in order, with facts crossing between them.
##
## A port of the runtime's half of `web/lib/narrative/case.ts`.
##
## The container is not a genre in the sense the other four are — it plays them.
## What it owns is the beat order, the edges between beats, and the fact
## vocabulary: **a fact is the only thing that crosses a leaf boundary**, because
## it is the only thing both a scenario and a room can say. No inventory, no seen
## set, no staging.

const DOCUMENT_KIND := "case-runtime-v1"
const DOCUMENT_SCHEMA_VERSION := 1

const BEAT_KINDS := ["scenario", "room"]
## What a solved room reports, so a room beat's edge can name an outcome.
const ROOM_WIN_OUTCOME := "win"


static func parse(document: Variant) -> Variant:
	if not (document is Dictionary):
		return KernelRefusal.of("case/document", "a case document must be a record")
	var doc: Dictionary = document
	if String(doc.get("kind", "")) != DOCUMENT_KIND:
		return KernelRefusal.of(
			"case/document-kind",
			(
				"unsupported case document; rebundle this case with a current stage-gen "
				+ "(stage-gen case bundle)"
			),
			"kind"
		)
	if int(doc.get("schema_version", -1)) != DOCUMENT_SCHEMA_VERSION:
		return KernelRefusal.of(
			"case/document-kind",
			(
				"unsupported case document; rebundle this case with a current stage-gen "
				+ "(stage-gen case bundle)"
			),
			"schema_version"
		)

	var facts := PackedStringArray()
	for entry: Variant in _array(doc.get("facts")):
		facts.append(String((entry as Dictionary).get("fact_id", "")))

	var beats: Array = []
	var seen := {}
	for entry: Variant in _array(doc.get("beats")):
		var beat: Dictionary = entry
		var beat_id := String(beat.get("beat_id", ""))
		if beat_id.is_empty():
			return KernelRefusal.of("case/beats", "a beat must name a beat_id", "beats")
		if seen.has(beat_id):
			return KernelRefusal.of("case/beats", "beats names %s twice" % beat_id, "beats")
		seen[beat_id] = true
		var kind := String(beat.get("kind", ""))
		if not BEAT_KINDS.has(kind):
			return KernelRefusal.of(
				"case/beats",
				"%s is a beat of kind %s, which this build does not play" % [beat_id, kind],
				"beats"
			)
		var edges: Array = []
		for raw: Variant in _array(beat.get("edges")):
			var edge: Dictionary = raw
			edges.append(
				{"outcome": String(edge.get("outcome", "")), "to": String(edge.get("to", ""))}
			)
		beats.append(
			{
				"beatId": beat_id,
				"kind": kind,
				"runTag": String(beat.get("run_tag", "")),
				"scenarioId": beat.get("scenario_id"),
				"writes": _strings(beat.get("writes")),
				"edges": edges,
			}
		)

	var entry_beat := String(doc.get("entry", ""))
	if not seen.has(entry_beat):
		return KernelRefusal.of(
			"case/entry",
			"the case enters at %s, which it does not publish" % entry_beat,
			"entry"
		)
	return {
		"caseId": String(doc.get("case_id", "")),
		"displayName": String(doc.get("display_name", "")),
		"entry": entry_beat,
		"facts": facts,
		"beats": beats,
	}


static func beat(document: Dictionary, beat_id: String) -> Dictionary:
	for entry: Variant in (document["beats"] as Array):
		var found: Dictionary = entry
		if String(found["beatId"]) == beat_id:
			return found
	return {}


## A beat with no outgoing edge ends the case.
static func beat_is_terminal(beat_record: Dictionary) -> bool:
	return (beat_record["edges"] as Array).is_empty()


static func initial_progress(document: Dictionary) -> Dictionary:
	return {"beatId": String(document["entry"]), "facts": PackedStringArray()}


## The facts a finished beat leaves behind, whether or not the case continues.
##
## Only names the case declared as facts survive: a leaf's own flag set is its
## own business, and a name it invents cannot become a fact by being exported.
static func merge_facts(
	document: Dictionary, carried: PackedStringArray, exported: PackedStringArray
) -> PackedStringArray:
	var declared := {}
	for fact in (document["facts"] as PackedStringArray):
		declared[fact] = true
	var merged := {}
	for fact in carried:
		if declared.has(fact):
			merged[fact] = true
	for fact in exported:
		if declared.has(fact):
			merged[fact] = true
	var keys := merged.keys()
	keys.sort()
	var made := PackedStringArray()
	for key: Variant in keys:
		made.append(String(key))
	return made


## Finish the current beat and take the edge its outcome names.
##
## Returns the progress at the next beat, or an empty dictionary when the case is
## over — either because the beat is terminal or because no edge matches the
## outcome. The second is the producer's proof failing rather than the player's
## problem: it ends the case rather than stranding them on a screen with nothing
## to press.
static func advance(
	document: Dictionary, progress: Dictionary, outcome: String, exported: PackedStringArray
) -> Dictionary:
	var current := beat(document, String(progress["beatId"]))
	if current.is_empty():
		return {}
	var carried := merge_facts(document, progress["facts"], exported)
	for entry: Variant in (current["edges"] as Array):
		var edge: Dictionary = entry
		if String(edge["outcome"]) == outcome:
			return {"beatId": String(edge["to"]), "facts": carried}
	return {}


## How far through the case a player is, for one line of chrome.
static func beat_number(document: Dictionary, beat_id: String) -> int:
	var beats: Array = document["beats"]
	for index in beats.size():
		if String((beats[index] as Dictionary)["beatId"]) == beat_id:
			return index + 1
	return 0


static func _array(value: Variant) -> Array:
	return value if value is Array else []


static func _strings(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in _array(value):
		made.append(String(entry))
	return made
