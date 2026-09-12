class_name CaseRuntime
extends RefCounted

## The episode above the leaves: which beat is playing, what the player has been
## shown, what a save holds, and what the case leaves behind.
##
## A port of `web/lib/narrative/runtime.ts`. The leaves have their own reducers
## and their own goldens; what lives here is the layer none of them can see —
## the beat order, the facts that cross between them, and the save that lets a
## player stop in the middle of one and come back to the same sentence.
##
## Like every turn-based surface in this project there is no clock, so `at` is
## handed in rather than read: a save's `updated_at` is the one field here that
## is not a function of the game.

const PHASE_READING_SAVE := "reading_save"
const PHASE_OFFERING_CONTINUE := "offering_continue"
const PHASE_PLAYING := "playing"
const PHASE_FINISHED := "finished"

## How many lines the backlog keeps. Old ones fall off the front.
const BACKLOG_LIMIT := 50


static func initial(document: Dictionary) -> Dictionary:
	return {
		"phase": PHASE_READING_SAVE,
		"progress": CaseDocument.initial_progress(document),
		"resume": null,
		"backlog": [],
		"pending": null,
		"ending": null,
		"carried": PackedStringArray(),
		"drawn": null,
		"lastLine": null,
	}


## What "the same line, again" means, per leaf kind.
##
## A scenario has statement identity and needs nothing else. A room has no such
## thing — it narrates in response to a click — so its line is identified by the
## beat, the interactions that have fired, and the words themselves, which is
## exactly enough to tell a redraw from a new click.
static func scenario_line_key(beat_id: String, statement_id: Variant) -> String:
	return "%s:%s" % [beat_id, "end" if statement_id == null else String(statement_id)]


static func room_line_key(beat_id: String, fired: Array, narration: String) -> String:
	var parts := PackedStringArray()
	for entry: Variant in fired:
		parts.append(str(int(entry)))
	return "%s:%s:%s" % [beat_id, ",".join(parts), narration]


## One transition of the episode.
##
## Returns `{state, events, write, clear, result}`: the next state, what
## happened, a save to write or null, whether the store should be cleared, and
## the episode's own output when it finished.
static func reduce(
	document: Dictionary, tag: String, state: Dictionary, action: Dictionary, at: String
) -> Dictionary:
	match String(action.get("kind", "")):
		"opened":
			var saved: Variant = action.get("saved")
			# A save whose beat this build no longer carries is not a save. The
			# player is offered a fresh episode rather than a Continue that goes
			# nowhere.
			if saved == null or CaseDocument.beat(document, String((saved as Dictionary)["beatId"])).is_empty():
				var fresh := state.duplicate(true)
				fresh["phase"] = PHASE_PLAYING
				return _still(fresh)
			var offered := state.duplicate(true)
			offered["phase"] = PHASE_OFFERING_CONTINUE
			offered["resume"] = saved
			offered["backlog"] = (saved as Dictionary)["backlog"]
			return _still(offered)

		"continue":
			var saved: Variant = state["resume"]
			if saved == null:
				return _still(state)
			var save: Dictionary = saved
			var resumed := state.duplicate(true)
			resumed["phase"] = PHASE_PLAYING
			resumed["progress"] = {"beatId": save["beatId"], "facts": save["facts"]}
			resumed["pending"] = null
			# The leaf redraws the moment it was saved at and reports it like any
			# other line, so without this a Continue would append the sentence the
			# player is looking at to a backlog that already ends with it.
			resumed["lastLine"] = (
				scenario_line_key(String(save["beatId"]), save["statementId"])
				if save["room"] == null
				else room_line_key(
					String(save["beatId"]),
					(save["room"] as Dictionary)["fired"],
					String((save["room"] as Dictionary)["narration"])
				)
			)
			return _still(resumed)

		"start-over":
			var fresh := initial(document)
			fresh["phase"] = PHASE_PLAYING
			var turn := _still(fresh)
			turn["clear"] = true
			return turn

		"presented":
			if String(state["phase"]) != PHASE_PLAYING:
				return _still(state)
			var beat_id := String((state["progress"] as Dictionary)["beatId"])
			var key := scenario_line_key(beat_id, action.get("statementId"))
			var remembered := _remember(state, key, action.get("line"))
			var next := state.duplicate(true)
			next["backlog"] = remembered["backlog"]
			next["lastLine"] = remembered["lastLine"]
			next["drawn"] = beat_id
			if action.get("outcome") != null:
				next["pending"] = {
					"beatId": beat_id,
					"outcome": action["outcome"],
					"flags": (action["scenario"] as Dictionary)["flags"],
				}
			return {
				"state": next,
				"events": [
					{
						"type": "line/presented",
						"beatId": beat_id,
						"statementId": action.get("statementId"),
					}
				],
				"write": CaseSave.of_scenario(
					tag,
					beat_id,
					(state["progress"] as Dictionary)["facts"],
					action["scenario"],
					remembered["backlog"],
					at
				),
				"clear": false,
				"result": null,
			}

		"room-changed":
			if String(state["phase"]) != PHASE_PLAYING:
				return _still(state)
			var beat_id := String((state["progress"] as Dictionary)["beatId"])
			var room: Dictionary = action["room"]
			var key := room_line_key(beat_id, room["fired"], String(room["narration"]))
			var remembered := _remember(
				state, key, {"speaker": null, "text": room["narration"]}
			)
			var next := state.duplicate(true)
			next["backlog"] = remembered["backlog"]
			next["lastLine"] = remembered["lastLine"]
			next["drawn"] = beat_id
			if bool(room["solved"]):
				next["pending"] = {
					"beatId": beat_id,
					"outcome": CaseDocument.ROOM_WIN_OUTCOME,
					"flags": room["flags"],
				}
			return {
				"state": next,
				"events": [{"type": "line/presented", "beatId": beat_id, "statementId": null}],
				"write": CaseSave.of_room(
					tag,
					beat_id,
					(state["progress"] as Dictionary)["facts"],
					room,
					remembered["backlog"],
					at
				),
				"clear": false,
				"result": null,
			}

		"finish":
			var progress: Dictionary = state["progress"]
			if String(progress["beatId"]) != String(action["beatId"]):
				return _still(state)
			var before := {}
			for fact in (progress["facts"] as PackedStringArray):
				before[fact] = true
			var flags: PackedStringArray = _strings(action.get("flags"))
			var merged := CaseDocument.merge_facts(document, progress["facts"], flags)
			var established := PackedStringArray()
			for fact in merged:
				if not before.has(fact):
					established.append(fact)
			var events: Array = []
			if not established.is_empty():
				events.append(
					{
						"type": "facts/established",
						"beatId": action["beatId"],
						"facts": established,
					}
				)
			var advanced := CaseDocument.advance(
				document, progress, String(action["outcome"]), flags
			)
			if advanced.is_empty():
				# Terminal, or an outcome the case declares no edge for. Either
				# way the episode is over here. The in-progress save goes — there
				# is nothing left to resume — but what the player finished
				# holding IS the episode's output, and the next case opens on it.
				events.append(
					{"type": "case/finished", "outcome": action["outcome"], "facts": merged}
				)
				var done := state.duplicate(true)
				done["phase"] = PHASE_FINISHED
				done["carried"] = merged
				done["ending"] = action["outcome"]
				done["pending"] = null
				return {
					"state": done,
					"events": events,
					"write": null,
					"clear": true,
					"result": {
						"runTag": tag,
						"outcome": action["outcome"],
						"facts": merged,
						"finishedAt": at,
					},
				}
			events.append(
				{"type": "beat/entered", "beatId": advanced["beatId"], "facts": advanced["facts"]}
			)
			var moved := state.duplicate(true)
			moved["progress"] = advanced
			moved["resume"] = null
			moved["pending"] = null
			moved["lastLine"] = null
			return {
				"state": moved,
				"events": events,
				# Written the moment a beat is entered, before it has drawn
				# anything: without it a player who reloads in the first second of
				# a beat would resume at the previous one and replay a scene they
				# finished.
				"write": CaseSave.of_beat(
					tag, String(advanced["beatId"]), advanced["facts"], state["backlog"], at
				),
				"clear": false,
				"result": null,
			}
	return _still(state)


## Remember a line unless it is the one already at the end of the backlog.
static func _remember(state: Dictionary, key: String, line: Variant) -> Dictionary:
	if line == null or String(state["lastLine"] if state["lastLine"] != null else "") == key:
		return {"backlog": state["backlog"], "lastLine": key}
	return {"backlog": CaseSave.append_backlog(state["backlog"], line), "lastLine": key}


static func _still(state: Dictionary) -> Dictionary:
	return {"state": state, "events": [], "write": null, "clear": false, "result": null}


static func _strings(value: Variant) -> PackedStringArray:
	if value is PackedStringArray:
		return value
	var made := PackedStringArray()
	if value is Array:
		for entry: Variant in (value as Array):
			made.append(String(entry))
	return made
