class_name FamilyContact
extends RefCounted

## What a body meets when it moves: the ground under a step, and the verdict on
## a fall.
##
## A port of `web/lib/families/sideview/traversal/contact.ts`. Rows increase
## downward, so "above" is numerically smaller and a rise absorbed by a step is
## a *decrease* in the foot's Y.
##
## Two entry rules, and the runner uses both in the same genre. `crossing` is
## the ordinary one: a body that ended the step below a surface it did not cross
## is **buried**, which the runner reads as a crush. `clamp` is the thrust
## locomotion's: a body pressed into the floor is simply put on it, because a
## boss fight's arena floor is a limit rather than a hazard. Handing the rule in
## rather than inferring it is what lets one function serve both without a flag
## nobody can see at the call site.

## Verdicts a step can return.
const SUPPORT_TERRAIN := "terrain"
const SUPPORT_PLATFORM := "platform"
## A body attached to a ladder or a rope. The runner has no such support and the
## platformer does, which is why the constant lives here rather than in either.
const SUPPORT_CLIMBABLE := "climbable"
const SUPPORT_AIR := "air"
const SUPPORT_BURIED := "buried"

const ENTRY_CLAMP := "clamp"
const ENTRY_CROSSING := "crossing"


## A grounded step onto a surface. Returns `{footY, support}`.
##
## The resolved `footY` is the surface when there is one: a rise is absorbed and
## the caller compares the two to decide whether that was a step up or a crush.
static func resolve_terrain_step(foot_y: float, surface_y: float, tolerance: float) -> Dictionary:
	if surface_y > foot_y + tolerance:
		return {"footY": foot_y, "support": SUPPORT_AIR}
	return {"footY": surface_y, "support": SUPPORT_TERRAIN}


## A vertical step through the world. Returns `{footY, vy, support}`.
##
## `decks` is the platformer's one-way platforms and is empty for the runner;
## it is here so the two genres share one function rather than two that drift.
static func resolve_vertical_landing(
	previous_foot_y: float,
	next_foot_y: float,
	vy: float,
	terrain_y: float,
	terrain_entry: String,
	x: float = 0.0,
	decks: Array = [],
	ignored_deck_id: String = ""
) -> Dictionary:
	if vy >= 0.0 and not decks.is_empty():
		var crossed: Array = []
		for deck: Variant in decks:
			var d: Dictionary = deck
			if String(d.get("id", "")) == ignored_deck_id:
				continue
			var deck_y := float(d.get("deckY", 0.0))
			if x < float(d.get("left", 0.0)) or x > float(d.get("right", 0.0)):
				continue
			if previous_foot_y <= deck_y and next_foot_y >= deck_y:
				crossed.append(d)
		if not crossed.is_empty():
			crossed.sort_custom(_by_deck)
			var first: Dictionary = crossed[0]
			return {
				"footY": float(first.get("deckY", 0.0)),
				"vy": 0.0,
				"support": SUPPORT_PLATFORM,
				"supportId": String(first.get("id", "")),
			}
	if terrain_entry == ENTRY_CLAMP:
		if vy >= 0.0 and next_foot_y >= terrain_y:
			return {"footY": terrain_y, "vy": 0.0, "support": SUPPORT_TERRAIN, "supportId": ""}
		return {"footY": next_foot_y, "vy": vy, "support": SUPPORT_AIR, "supportId": ""}
	if next_foot_y < terrain_y:
		return {"footY": next_foot_y, "vy": vy, "support": SUPPORT_AIR, "supportId": ""}
	if vy >= 0.0 and previous_foot_y <= terrain_y:
		return {"footY": terrain_y, "vy": 0.0, "support": SUPPORT_TERRAIN, "supportId": ""}
	return {"footY": next_foot_y, "vy": vy, "support": SUPPORT_BURIED, "supportId": ""}


## A horizontal step across a heightfield, stopped by any column face standing
## above the feet.
##
## Returns `{x, blocked, blockedColumn}`. `blockedColumn` is -1 when nothing
## stopped the walk.
##
## Descents are absorbed by default and rises are not: a column that steps down
## is a ledge the caller's gravity handles, and a column that steps up is a wall
## whose only way over is a jump. The platformer's heightfield steps in whole
## tiles, so in practice every rise is climbed rather than walked.
static func resolve_terrain_walk(
	previous_x: float,
	next_x: float,
	foot_y: float,
	tile_units: float,
	surface_at: Callable,
	tolerance: float,
	contact_gap: float,
	allow_descents: bool = true
) -> Dictionary:
	var unblocked := {"x": next_x, "blocked": false, "blockedColumn": -1}
	if tile_units <= 0.0:
		return unblocked
	var from_column := int(floor(previous_x / tile_units))
	var to_column := int(floor(next_x / tile_units))
	if from_column == to_column:
		return unblocked
	var step := 1 if to_column > from_column else -1
	var column := from_column + step
	while true:
		var surface_y := float(surface_at.call(column))
		var same_level := absf(surface_y - foot_y) <= tolerance
		if not (same_level or (allow_descents and surface_y > foot_y)):
			# The face of this column is above the feet. Stop just short of it,
			# on whichever side the body came from.
			var stopped := (
				float(column) * tile_units - contact_gap
				if step > 0
				else float(column + 1) * tile_units
			)
			return {"x": stopped, "blocked": true, "blockedColumn": column}
		if column == to_column:
			break
		column += step
	return unblocked


static func _by_deck(a: Variant, b: Variant) -> bool:
	var left: Dictionary = a
	var right: Dictionary = b
	var ly := float(left.get("deckY", 0.0))
	var ry := float(right.get("deckY", 0.0))
	if ly != ry:
		return ly < ry
	return String(left.get("id", "")) < String(right.get("id", ""))
