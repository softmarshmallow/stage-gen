class_name FamilyBag
extends RefCounted

## What a body carries, counted.
##
## A port of `web/lib/families/inventory/bag.ts`. The bag is a Dictionary of
## item id to a positive count; an emptied stack **leaves** the bag rather than
## sitting at zero, so the item list is what is carried and not a history of
## what once was.
##
## Two rules that read as arbitrary until you see what they are for:
##
## A **grant is all or nothing** — a bag with room for two refuses three rather
## than taking two — because a grant is a promise made before the count is
## checked. A **spend is a floor at zero**, taking as many as are there, because
## spending is the half a caller has already checked: a throw asks whether a
## round is carried before it fires.
##
## Capacity of 0 means unbounded rather than a bag that holds nothing. A room's
## bag genuinely has no limit — the solvability proof searches a state space
## where carrying is unbounded — and a bag that refuses is a different bag from
## one that cannot.

const REFUSAL_QUANTITY := "quantity"
const REFUSAL_CAPACITY := "capacity"
const REFUSAL_ABSENT := "absent"
## A bag with no ceiling.
const UNLIMITED := 0


static func carried(bag: Dictionary, item_id: String) -> int:
	return int(bag.get(item_id, 0))


static func total_carried(bag: Dictionary) -> int:
	var total := 0
	for key: Variant in bag:
		total += int(bag[key])
	return total


## The item ids in a stable order.
##
## Sorted rather than in pickup order: both consumers draw a bag as a list, and
## a list whose order depends on the sequence things were picked up in is not
## reproducible across a replay that collects the same items another way round.
static func item_ids(bag: Dictionary) -> PackedStringArray:
	var keys := bag.keys()
	keys.sort()
	var made := PackedStringArray()
	for key: Variant in keys:
		made.append(String(key))
	return made


## A bag holding one of each name: a set, as a counted bag.
static func of_one(item_ids_in: PackedStringArray) -> Dictionary:
	var made := {}
	for item_id in item_ids_in:
		made[item_id] = 1
	return made


## Put units in. Returns `{bag, moved, refusal}`; `refusal` is "" when the whole
## request landed.
static func grant(
	bag: Dictionary, item_id: String, quantity: int, capacity: int = UNLIMITED
) -> Dictionary:
	if quantity <= 0:
		return {"bag": bag, "moved": 0, "refusal": REFUSAL_QUANTITY}
	if capacity > 0 and total_carried(bag) + quantity > capacity:
		return {"bag": bag, "moved": 0, "refusal": REFUSAL_CAPACITY}
	var next := bag.duplicate()
	next[item_id] = carried(bag, item_id) + quantity
	return {"bag": next, "moved": quantity, "refusal": ""}


## Spend units, taking as many as are there.
static func consume(bag: Dictionary, item_id: String, quantity: int) -> Dictionary:
	if quantity <= 0:
		return {"bag": bag, "moved": 0, "refusal": REFUSAL_QUANTITY}
	var held := carried(bag, item_id)
	var spent := mini(held, quantity)
	if spent <= 0:
		return {"bag": bag, "moved": 0, "refusal": REFUSAL_ABSENT}
	var next := bag.duplicate()
	if held - spent > 0:
		next[item_id] = held - spent
	else:
		next.erase(item_id)
	return {"bag": next, "moved": spent, "refusal": ""}
