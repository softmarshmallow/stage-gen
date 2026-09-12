class_name FamilyLoot
extends RefCounted

## What the body picked up, and what it walked past.
##
## A port of `web/lib/families/loot/collect.ts`. The ledger is two sets of keys
## the caller owns; this decides, per candidate and **in the caller's order**,
## which of three things happened. The order is load-bearing: it is the order
## the awards are paid in and so the order the digest records.
##
## A candidate is tested against `passed` before `reached`, so a pickup the body
## is both past and touching is a miss. That is deliberate — the alternative
## lets a fast body harvest things behind it.


## Returns `{taken: Array, missed: Array}`.
static func collect_drops(
	candidates: Array,
	key_of: Callable,
	collected: Dictionary,
	missed_keys: Dictionary,
	passed: Callable,
	reached: Callable
) -> Dictionary:
	var taken: Array = []
	var missed: Array = []
	for drop: Variant in candidates:
		var key := String(key_of.call(drop))
		if collected.has(key):
			continue
		if bool(passed.call(drop)):
			if not missed_keys.has(key):
				missed_keys[key] = true
				missed.append(drop)
			continue
		if not bool(reached.call(drop)):
			continue
		collected[key] = true
		taken.append(drop)
	return {"taken": taken, "missed": missed}
