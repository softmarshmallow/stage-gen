extends RefCounted

## A scenario as a reducer: a state, an action, and everything that happened
## between them.
##
## Programs must come from Program.parse; states must come from this runtime
## or restore. They are read-only to callers. A transition has no clock.
##
## The one idea worth carrying across whole is the **settle**. `show`, `hide`,
## `stage`, `audio`, `set`, `jump` and `branch` are invisible: they change the
## world and hand control straight on. Only a line, a choice or an ending stops.
## Doing that walk inside the reducer rather than in the consumer is what keeps
## "what is drawn" a pure function of the state, instead of something a view has
## to re-derive by peeking at the next few statements.

const Program = preload("program.gd")
const Refusal = preload("refusal.gd")
const Compatibility = preload("compatibility/v2.gd")

const ACTION_ADVANCE := "advance"
const ACTION_CHOOSE := "choose"
const ACTION_RESTART := "restart"

const SNAPSHOT_KIND := "scenario-runtime-snapshot"
const SNAPSHOT_SCHEMA_VERSION := 1


## The opening, with everything the settle did on the way to the first moment.
static func initial_turn(program: Dictionary, carried: PackedStringArray = PackedStringArray()) -> Dictionary:
	return Compatibility.initial_turn(program, carried)


static func initial_state(program: Dictionary, carried: PackedStringArray = PackedStringArray()) -> Dictionary:
	var turn := initial_turn(program, carried)
	return turn if Refusal.is_refusal(turn) else turn["state"]


## One transition, and the occurrences inside it.
##
## A turn that moves nothing — a stray key at an ending, a choice that was not
## offered — reports no events, which is what makes "nothing happened" a
## checkable answer rather than an unchanged object a caller must notice by
## identity.
static func reduce_turn(program: Dictionary, state: Dictionary, action: Dictionary) -> Dictionary:
	if not (action.get("kind", "") is String):
		return Refusal.of("scenario/action", "action kind must be a string", "kind")
	var kind := String(action.get("kind", ""))
	if kind == ACTION_CHOOSE:
		var option: Variant = action.get("option", -1)
		if not (option is int or option is float) or not is_finite(float(option)) or float(option) != floor(float(option)):
			return Refusal.of("scenario/action", "choice option must be an integer", "option")
	if kind == ACTION_RESTART:
		return initial_turn(program)
	if state["outcome"] != null:
		return {"state": state, "events": []}
	var statement := _statement_at(program, state)
	if statement.is_empty():
		return {"state": state, "events": []}
	if String(statement["kind"]) == "choice":
		if kind != ACTION_CHOOSE:
			return {"state": state, "events": []}
		var available := _available_options(statement["options"], state["flags"])
		var option := int(action.get("option", -1))
		if option < 0 or option >= available.size():
			return {"state": state, "events": []}
		return Compatibility.reduce_turn(program, state, action)
	if kind != ACTION_ADVANCE:
		return {"state": state, "events": []}
	return Compatibility.reduce_turn(program, state, action)


static func reduce(program: Dictionary, state: Dictionary, action: Dictionary) -> Dictionary:
	var turn := reduce_turn(program, state, action)
	return turn if Refusal.is_refusal(turn) else turn["state"]


## What is on screen now: a line, a choice, or the end card.
static func view(program: Dictionary, state: Dictionary) -> Dictionary:
	if state["outcome"] != null:
		for entry: Variant in (program["endings"] as Array):
			var ending: Dictionary = entry
			if String(ending["outcomeId"]) == String(state["outcome"]):
				return {
					"kind": "end",
					"outcome": ending["outcomeId"],
					"label": ending["label"],
				}
		# An outcome with no published ending is labelled by its own id rather
		# than by nothing: a card with an empty heading tells a player less than
		# one naming the outcome the author wrote.
		return {"kind": "end", "outcome": state["outcome"], "label": state["outcome"]}
	var statement := _statement_at(program, state)
	if statement.is_empty():
		return {}
	if String(statement["kind"]) == "line":
		var speaker: Variant = statement["speaker"]
		return {
			"kind": "line",
			"speaker": speaker,
			"speakerLabel": (
				null if speaker == null else Program.speaker_label(program, String(speaker))
			),
			"text": statement["text"],
		}
	if String(statement["kind"]) == "choice":
		# The whole option, not only its text: a consumer that wants to show
		# where a choice leads, or why one is offered, reads the same record the
		# author wrote rather than asking the program again.
		return {
			"kind": "choice",
			"options": _available_options(statement["options"], state["flags"]),
		}
	return {}


## A statement's name within one program revision. Inserting statements changes
## these positions; persistent saves should use snapshot's program fingerprint.
static func statement_id(label: String, index: int) -> String:
	return "%s#%d" % [label, index]


static func is_finished(state: Dictionary) -> bool:
	return state["outcome"] != null


static func actor(state: Dictionary, actor_id: String) -> Dictionary:
	for entry: Variant in (state["actors"] as Array):
		var staged: Dictionary = entry
		if String(staged["actorId"]) == actor_id:
			return staged
	return {}


## Compatibility keeps v2 views and snapshots stable; all sequence progression
## runs through execution/session.gd via compatibility/v2.gd.
static func _statement_at(program: Dictionary, state: Dictionary) -> Dictionary:
	var block := Program.block_of(program, String(state["label"]))
	if block.is_empty():
		return {}
	var statements: Array = block["statements"]
	var index := int(state["index"])
	if index < 0 or index >= statements.size():
		return {}
	return statements[index]


static func _available_options(options: Array, flags: Array) -> Array:
	var made: Array = []
	for entry: Variant in options:
		var option: Dictionary = entry
		if _holds(option["condition"], flags):
			made.append(option)
	return made


## An empty condition is satisfied by every flag set, which is what an
## unconditional option or edge is.
static func _holds(condition: Variant, flags: Array) -> bool:
	if not (condition is Dictionary) or (condition as Dictionary).is_empty():
		return true
	var rule: Dictionary = condition
	for flag in (rule["requires"] as PackedStringArray):
		if not flags.has(String(flag)):
			return false
	for flag in (rule["forbids"] as PackedStringArray):
		if flags.has(String(flag)):
			return false
	return true


## How far through a scenario the player is, for one line of chrome.
##
## `total` counts the statements that *stop* — a line or a choice — because the
## invisible ones are not moments a player passes through. Not ported when the
## runtime was, and the readout that needs it is the one thing on the dialogue
## panel that is neither the words nor who said them.
static func progress(program: Dictionary, state: Dictionary) -> Dictionary:
	var total := 0
	for entry: Variant in (program["blocks"] as Array):
		for raw: Variant in ((entry as Dictionary)["statements"] as Array):
			var kind := String((raw as Dictionary)["kind"])
			if kind == "line" or kind == "choice":
				total += 1
	return {"seen": (state["seen"] as Array).size(), "total": total}


## A content-bound save envelope. State and program must be the unmodified values
## admitted by this package. Existing game save writers may keep their raw state
## representation; this explicit boundary adds identity without changing reducer
## state, events or their established replay representation.
static func snapshot(program: Dictionary, state: Dictionary) -> Dictionary:
	return {
		"kind": SNAPSHOT_KIND,
		"schema_version": SNAPSHOT_SCHEMA_VERSION,
		"program_fingerprint": Program.fingerprint(program),
		"state": state.duplicate(true),
	}


## A saved state, checked against the program it claims to be of, or null.
##
## New save writers can use snapshot() to refuse content edits even when the old
## label/index still exists. Raw pre-envelope states retain structural admission
## for supported game saves; their content revision cannot be verified. Neither
## form authenticates a save nor proves that its state was reached by playing.
## Incompatibility returns null so the host can offer a fresh invocation.
static func restore(program: Dictionary, saved_value: Variant) -> Variant:
	if not (saved_value is Dictionary):
		return null
	var saved: Dictionary = saved_value
	if saved.has("kind") or saved.has("program_fingerprint") or saved.has("state"):
		var version: Variant = saved.get("schema_version")
		if not (saved.get("kind") is String) or not (version is int or version is float):
			return null
		if saved["kind"] != SNAPSHOT_KIND or version != SNAPSHOT_SCHEMA_VERSION:
			return null
		if not (saved.get("program_fingerprint") is String) or not (saved.get("state") is Dictionary):
			return null
		if saved["program_fingerprint"] != Program.fingerprint(program):
			return null
		saved = saved["state"]
	if not _snapshot_shape(saved):
		return null
	var block := Program.block_of(program, String(saved.get("label", "")))
	if block.is_empty():
		return null
	var statements: Array = block["statements"]
	var index := int(saved.get("index", -1))
	if index < 0 or index >= statements.size():
		return null

	var statement: Dictionary = statements[index]
	var kind := String(statement["kind"])
	var outcome: Variant = saved.get("outcome")
	if kind == "end":
		if outcome != statement["outcome"]:
			return null
	elif (kind != "line" and kind != "choice") or outcome != null:
		return null

	var declared := {}
	for flag in (program["flags"] as PackedStringArray):
		declared[String(flag)] = true
	var flags: Array = []
	for flag: Variant in _array(saved.get("flags")):
		if not declared.has(String(flag)) or flags.has(String(flag)):
			return null
		flags.append(String(flag))
	flags.sort()
	if kind == "choice" and _available_options(statement["options"], flags).is_empty():
		return null

	var stage: Variant = saved.get("stage")
	if stage != null and not _names(program["stages"], String(stage)):
		return null
	var tracks: Array = []
	for track: Variant in _array(saved.get("tracks")):
		if not _names(program["tracks"], String(track)) or tracks.has(String(track)):
			return null
		tracks.append(String(track))

	var actors: Array = []
	var actor_ids := {}
	for entry: Variant in _array(saved.get("actors")):
		if not (entry is Dictionary):
			return null
		var staged: Dictionary = entry
		var actor_id := String(staged.get("actorId", staged.get("actor_id", "")))
		if actor_ids.has(actor_id):
			return null
		actor_ids[actor_id] = true
		var member := _cast_member(program, actor_id)
		if member.is_empty():
			return null
		var slot := String(staged.get("slot", ""))
		if not Program.SLOTS.has(slot):
			return null
		var expression: Variant = staged.get("expression")
		if expression != null and not (member["expressions"] as PackedStringArray).has(String(expression)):
			return null
		actors.append({"actorId": actor_id, "expression": expression, "slot": slot})

	var seen: Array = []
	var visible_ids := {}
	for entry: Variant in (program["blocks"] as Array):
		var visible_block: Dictionary = entry
		var visible_statements: Array = visible_block["statements"]
		for visible_index in visible_statements.size():
			var visible_kind := String(visible_statements[visible_index]["kind"])
			if visible_kind == "line" or visible_kind == "choice":
				visible_ids[statement_id(String(visible_block["label"]), visible_index)] = true
	for id: Variant in _array(saved.get("seen")):
		if not visible_ids.has(String(id)) or seen.has(String(id)):
			return null
		seen.append(String(id))
	if kind != "end" and not seen.has(statement_id(String(saved["label"]), index)):
		return null
	return {
		"label": String(saved["label"]),
		"index": index,
		"flags": flags,
		"seen": seen,
		"stage": stage,
		"actors": actors,
		"tracks": tracks,
		"outcome": outcome,
	}


static func _cast_member(program: Dictionary, actor_id: String) -> Dictionary:
	for entry: Variant in (program["cast"] as Array):
		var member: Dictionary = entry
		if String(member["actorId"]) == actor_id:
			return member
	return {}


static func _names(ids: PackedStringArray, wanted: String) -> bool:
	for id in ids:
		if String(id) == wanted:
			return true
	return false


static func _array(value: Variant) -> Array:
	return value if value is Array else []


## Snapshot admission protects the casts below; stale but well-shaped values
## still use the established null-on-incompatibility restore contract.
static func _snapshot_shape(saved: Dictionary) -> bool:
	if not (saved.get("label", "") is String):
		return false
	var index: Variant = saved.get("index", -1)
	if not (index is int or index is float) or not is_finite(float(index)) or float(index) != floor(float(index)):
		return false
	for key in ["outcome", "stage"]:
		if saved.get(key) != null and not (saved[key] is String):
			return false
	for key in ["flags", "tracks", "seen"]:
		if not (saved.get(key, []) is Array):
			return false
		for entry: Variant in saved.get(key, []):
			if not (entry is String):
				return false
	if not (saved.get("actors", []) is Array):
		return false
	for entry: Variant in saved.get("actors", []):
		if not (entry is Dictionary):
			return false
		if not (entry.get("actorId", entry.get("actor_id", "")) is String) or not (entry.get("slot", "") is String):
			return false
		if entry.get("expression") != null and not (entry["expression"] is String):
			return false
	return true
