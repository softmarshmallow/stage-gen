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


static func _by_deck(a: Variant, b: Variant) -> bool:
	var left: Dictionary = a
	var right: Dictionary = b
	var ly := float(left.get("deckY", 0.0))
	var ry := float(right.get("deckY", 0.0))
	if ly != ry:
		return ly < ry
	return String(left.get("id", "")) < String(right.get("id", ""))
