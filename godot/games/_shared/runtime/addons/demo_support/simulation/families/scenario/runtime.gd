class_name FamilyScenarioRuntime
extends RefCounted

## A scenario as a reducer: a state, an action, and everything that happened
## between them.
##
## A port of `web/lib/scenario/runtime.ts`. Like the room, a scenario has no
## clock — a transition is a keypress, not a step — so there is no roster and no
## sealed order here either.
##
## The one idea worth carrying across whole is the **settle**. `show`, `hide`,
## `stage`, `audio`, `set`, `jump` and `branch` are invisible: they change the
## world and hand control straight on. Only a line, a choice or an ending stops.
## Doing that walk inside the reducer rather than in the consumer is what keeps
## "what is drawn" a pure function of the state, instead of something a view has
## to re-derive by peeking at the next few statements.

const ACTION_ADVANCE := "advance"
const ACTION_CHOOSE := "choose"
const ACTION_RESTART := "restart"


## The opening, with everything the settle did on the way to the first moment.
static func initial_turn(program: Dictionary, carried: PackedStringArray = PackedStringArray()) -> Dictionary:
	var declared := {}
	for flag in (program["importedFlags"] as PackedStringArray):
		declared[flag] = true
	var seeded := {}
	for flag in carried:
		if declared.has(flag):
			seeded[flag] = true
	var flags := seeded.keys()
	flags.sort()
	var events: Array = []
	var state := _settle(
		program,
		{
			"label": String(program["entry"]),
			# Before the first statement of the entry block: the settle steps it
			# to zero, which is what makes entering a block and advancing inside
			# one the same walk.
			"index": -1,
			"flags": flags,
			"seen": [],
			"stage": null,
			"actors": [],
			"tracks": [],
			"outcome": null,
		},
		events
	)
	return {"state": state, "events": events}


static func initial_state(program: Dictionary, carried: PackedStringArray = PackedStringArray()) -> Dictionary:
	return initial_turn(program, carried)["state"]


## One transition, and the occurrences inside it.
##
## A turn that moves nothing — a stray key at an ending, a choice that was not
## offered — reports no events, which is what makes "nothing happened" a
## checkable answer rather than an unchanged object a caller must notice by
## identity.
static func reduce_turn(program: Dictionary, state: Dictionary, action: Dictionary) -> Dictionary:
	var kind := String(action.get("kind", ""))
	if kind == ACTION_RESTART:
		return initial_turn(program)
	var events: Array = []
	if state["outcome"] != null:
		return {"state": state, "events": events}
	var statement := _statement_at(program, state)
	if statement.is_empty():
		return {"state": state, "events": events}

	if String(statement["kind"]) == "choice":
		if kind != ACTION_CHOOSE:
			return {"state": state, "events": events}
		var available := _available_options(statement["options"], state["flags"])
		var option := int(action.get("option", -1))
		if option < 0 or option >= available.size():
			return {"state": state, "events": events}
		var chosen: Dictionary = available[option]
		events.append(
			{
				"type": "scenario/branched",
				"from": state["label"],
				"to": chosen["target"],
				"cause": "choice",
			}
		)
		var moved := state.duplicate(true)
		moved["label"] = chosen["target"]
		moved["index"] = -1
		return {"state": _settle(program, moved, events), "events": events}

	if kind != ACTION_ADVANCE:
		return {"state": state, "events": events}
	var next := state.duplicate(true)
	next["index"] = int(state["index"]) + 1
	return {"state": _settle(program, next, events), "events": events}


static func reduce(program: Dictionary, state: Dictionary, action: Dictionary) -> Dictionary:
	return reduce_turn(program, state, action)["state"]


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
				null if speaker == null else FamilyScenarioProgram.speaker_label(program, String(speaker))
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


## A statement's stable name: the block it is in and where in it.
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


## Run forward until something is on screen or the scenario ends.
static func _settle(program: Dictionary, start: Dictionary, events: Array) -> Dictionary:
	var state := start
	# The program is a finite graph whose every block terminates, and the
	# admission proof refused any that could not reach an `end`. A cycle of
	# invisible statements is still expressible, though, so the walk is bounded
	# rather than trusted.
	var limit := (
		FamilyScenarioProgram.total_statements(program) + (program["blocks"] as Array).size() + 1
	)
	for _step in limit + 1:
		var block := FamilyScenarioProgram.block_of(program, String(state["label"]))
		if block.is_empty():
			return state
		var statements: Array = block["statements"]
		var index := int(state["index"])
		if index < 0 or index >= statements.size():
			state = state.duplicate(true)
			state["index"] = 0
			continue
		var statement: Dictionary = statements[index]
		var kind := String(statement["kind"])
		if kind == "line" or kind == "choice":
			var settled := _mark_seen(_speak(state, statement, events))
			events.append(
				{
					"type": "scenario/presented",
					"statementId": statement_id(
						String(settled["label"]), int(settled["index"])
					),
					"kind": "choice" if kind == "choice" else "line",
				}
			)
			return settled
		state = _apply(state, statement, events)
		if state["outcome"] != null:
			events.append({"type": "scenario/ended", "outcome": state["outcome"]})
			return state
	push_error("scenario runtime exceeded its step bound; the program is not walkable")
	return state


static func _apply(state: Dictionary, statement: Dictionary, events: Array) -> Dictionary:
	var next := state.duplicate(true)
	match String(statement["kind"]):
		"show":
			var actor_id := String(statement["actor"])
			var previous := actor(state, actor_id)
			var expression: Variant = statement["expression"]
			if expression == null and not previous.is_empty():
				expression = previous["expression"]
			events.append(
				{
					"type": "scenario/actor-changed",
					"actorId": actor_id,
					"slot": statement["slot"],
					"expression": expression,
				}
			)
			# The actor is removed and re-appended, so the cast list is in the
			# order the author last staged them rather than first named them.
			var others: Array = []
			for entry: Variant in (state["actors"] as Array):
				if String((entry as Dictionary)["actorId"]) != actor_id:
					others.append(entry)
			others.append(
				{"actorId": actor_id, "expression": expression, "slot": statement["slot"]}
			)
			next["actors"] = others
			next["index"] = int(state["index"]) + 1
		"hide":
			var actor_id := String(statement["actor"])
			events.append(
				{
					"type": "scenario/actor-changed",
					"actorId": actor_id,
					"slot": null,
					"expression": null,
				}
			)
			var kept: Array = []
			for entry: Variant in (state["actors"] as Array):
				if String((entry as Dictionary)["actorId"]) != actor_id:
					kept.append(entry)
			next["actors"] = kept
			next["index"] = int(state["index"]) + 1
		"stage":
			events.append({"type": "scenario/staged", "stage": statement["stage"]})
			next["stage"] = statement["stage"]
			next["index"] = int(state["index"]) + 1
		"audio":
			var track := String(statement["track"])
			var action := String(statement["action"])
			events.append(
				{"type": "scenario/audio-changed", "track": track, "action": action}
			)
			var tracks: Array = []
			for entry: Variant in (state["tracks"] as Array):
				if String(entry) != track:
					tracks.append(entry)
			if action == "play":
				tracks.append(track)
			next["tracks"] = tracks
			next["index"] = int(state["index"]) + 1
		"set":
			var flag := String(statement["flag"])
			var value := bool(statement["value"])
			events.append({"type": "scenario/flag-changed", "flag": flag, "value": value})
			var flags: Array = []
			for entry: Variant in (state["flags"] as Array):
				if String(entry) != flag:
					flags.append(entry)
			if value:
				flags.append(flag)
				flags.sort()
			next["flags"] = flags
			next["index"] = int(state["index"]) + 1
		"jump":
			events.append(
				{
					"type": "scenario/branched",
					"from": state["label"],
					"to": statement["target"],
					"cause": "jump",
				}
			)
			next["label"] = statement["target"]
			next["index"] = 0
		"branch":
			# The first satisfied edge, exactly as the admission proof searched
			# it; the default is what an unsatisfied list falls to.
			var target := String(statement["default"])
			for entry: Variant in (statement["edges"] as Array):
				var edge: Dictionary = entry
				if _holds(edge["condition"], state["flags"]):
					target = String(edge["target"])
					break
			events.append(
				{
					"type": "scenario/branched",
					"from": state["label"],
					"to": target,
					"cause": "branch",
				}
			)
			next["label"] = target
			next["index"] = 0
		"end":
			next["outcome"] = statement["outcome"]
		_:
			next["index"] = int(state["index"]) + 1
	return next


## A line that names an expression re-dresses its speaker from here on, exactly
## as the script surface reads: `mara delighted "..."` means Mara is delighted
## for the rest of the scene, not only where `show` last put her. Staging stays
## `show`'s job — a line spoken from off stage changes nothing.
static func _speak(state: Dictionary, statement: Dictionary, events: Array) -> Dictionary:
	if String(statement["kind"]) != "line":
		return state
	if statement["speaker"] == null or statement["expression"] == null:
		return state
	var speaker := String(statement["speaker"])
	var staged := actor(state, speaker)
	if staged.is_empty() or staged["expression"] == statement["expression"]:
		return state
	events.append(
		{
			"type": "scenario/actor-changed",
			"actorId": speaker,
			"slot": staged["slot"],
			"expression": statement["expression"],
		}
	)
	var next := state.duplicate(true)
	var actors: Array = []
	for entry: Variant in (state["actors"] as Array):
		var member: Dictionary = (entry as Dictionary).duplicate()
		if String(member["actorId"]) == speaker:
			member["expression"] = statement["expression"]
		actors.append(member)
	next["actors"] = actors
	return next


static func _mark_seen(state: Dictionary) -> Dictionary:
	var id := statement_id(String(state["label"]), int(state["index"]))
	if (state["seen"] as Array).has(id):
		return state
	var next := state.duplicate(true)
	(next["seen"] as Array).append(id)
	return next


static func _statement_at(program: Dictionary, state: Dictionary) -> Dictionary:
	var block := FamilyScenarioProgram.block_of(program, String(state["label"]))
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


## A saved state, checked against the program it claims to be of, or null.
##
## A port of `restoreScenarioState`. The case shell writes a save on every
## statement and offers a Continue when it finds one; a regenerated scenario can
## have moved every block under it. Returning null rather than refusing is the
## point — the player is offered a fresh scene instead of a Continue that opens
## on an actor nobody declared, and a save that no longer fits is not an error
## anyone can act on.
static func restore(program: Dictionary, snapshot: Variant) -> Variant:
	if not (snapshot is Dictionary):
		return null
	var saved: Dictionary = snapshot
	var block := FamilyScenarioProgram.block_of(program, String(saved.get("label", "")))
	if block.is_empty():
		return null
	var statements: Array = block["statements"]
	var index := int(saved.get("index", -1))
	if index < 0 or index >= statements.size():
		return null

	var outcome: Variant = saved.get("outcome")
	if outcome != null:
		var published := false
		for entry: Variant in (program["endings"] as Array):
			if String((entry as Dictionary)["outcomeId"]) == String(outcome):
				published = true
				break
		if not published:
			return null

	var declared := {}
	for flag in (program["flags"] as PackedStringArray):
		declared[String(flag)] = true
	var flags: Array = []
	for flag: Variant in _array(saved.get("flags")):
		if not declared.has(String(flag)):
			return null
		flags.append(String(flag))
	flags.sort()

	var stage: Variant = saved.get("stage")
	if stage != null and not _names(program["stages"], String(stage)):
		return null
	var tracks: Array = []
	for track: Variant in _array(saved.get("tracks")):
		if not _names(program["tracks"], String(track)):
			return null
		tracks.append(String(track))

	var actors: Array = []
	for entry: Variant in _array(saved.get("actors")):
		if not (entry is Dictionary):
			return null
		var staged: Dictionary = entry
		var actor_id := String(staged.get("actorId", staged.get("actor_id", "")))
		var member := _cast_member(program, actor_id)
		if member.is_empty():
			return null
		var slot := String(staged.get("slot", ""))
		if not FamilyScenarioProgram.SLOTS.has(slot):
			return null
		var expression: Variant = staged.get("expression")
		if expression != null and not (member["expressions"] as PackedStringArray).has(String(expression)):
			return null
		actors.append({"actorId": actor_id, "expression": expression, "slot": slot})

	var seen: Array = []
	for id: Variant in _array(saved.get("seen")):
		seen.append(String(id))
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
