class_name CaseSave
extends RefCounted

const ScenarioRuntime = preload("res://addons/scenario_runtime/runtime.gd")

## What a stopped episode holds, and what it leaves behind when it finishes.
##
## A port of the save-shaping half of `web/lib/narrative/case-save.ts`. The
## storage itself is the host's: this decides what a save *is*.
##
## `facts` is the only slice that belongs to the case rather than to the leaf
## being played, because a fact is the only thing that crosses a beat boundary.
## `statementId` is derivable from the scenario slice and is written anyway, so a
## Continue card can name the line without loading the program the line belongs
## to.

const BACKLOG_LIMIT := 50


## One line the player has already been shown.
static func append_backlog(backlog: Array, line: Variant) -> Array:
	var entry: Dictionary = line
	var next := backlog.duplicate()
	next.append({"speaker": entry.get("speaker"), "text": String(entry.get("text", ""))})
	if next.size() > BACKLOG_LIMIT:
		next = next.slice(next.size() - BACKLOG_LIMIT)
	return next


static func of_scenario(
	run_tag: String,
	beat_id: String,
	facts: PackedStringArray,
	scenario: Dictionary,
	backlog: Array,
	updated_at: String
) -> Dictionary:
	return {
		"runTag": run_tag,
		"beatId": beat_id,
		"facts": facts,
		"statementId": ScenarioRuntime.statement_id(
			String(scenario["label"]), int(scenario["index"])
		),
		"scenario": scenario,
		"room": null,
		"backlog": backlog,
		"updatedAt": updated_at,
	}


static func of_room(
	run_tag: String,
	beat_id: String,
	facts: PackedStringArray,
	room: Dictionary,
	backlog: Array,
	updated_at: String
) -> Dictionary:
	return {
		"runTag": run_tag,
		"beatId": beat_id,
		"facts": facts,
		# A room has no statement identity: it narrates in response to a click.
		"statementId": null,
		"scenario": null,
		"room": room,
		"backlog": backlog,
		"updatedAt": updated_at,
	}


## The save written the moment a beat is entered, before it has drawn anything.
static func of_beat(
	run_tag: String,
	beat_id: String,
	facts: PackedStringArray,
	backlog: Array,
	updated_at: String
) -> Dictionary:
	return {
		"runTag": run_tag,
		"beatId": beat_id,
		"facts": facts,
		"statementId": null,
		"scenario": null,
		"room": null,
		"backlog": backlog,
		"updatedAt": updated_at,
	}
