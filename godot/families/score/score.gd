class_name FamilyScore
extends RefCounted

## A total, a chain, and the multiplier the chain earns.
##
## A port of `web/lib/families/score/score.ts`. The slice is `{total, chain,
## multiplier}`.
##
## The order inside `apply` is load-bearing and is the whole design: **a break
## is applied before this frame's occurrences extend the chain**, and the
## multiplier is recomputed before anything is paid. So a frame that both misses
## one pickup and takes another starts the new chain at one, and this frame's
## collections are paid at the multiplier they themselves just earned.


static func create() -> Dictionary:
	return {"total": 0.0, "chain": 0, "multiplier": 1}


## In place, because the slice is owned and the reset is not a new object.
static func reset(state: Dictionary) -> void:
	state["total"] = 0.0
	state["chain"] = 0
	state["multiplier"] = 1


## One more for each step the chain has passed. Steps are ascending; the ladder
## is the genre's and the cap is however many rungs it lists.
static func chain_multiplier(chain: int, steps: PackedInt32Array) -> int:
	var multiplier := 1
	for step in steps:
		if chain >= step:
			multiplier += 1
	return multiplier


## Pay for this frame. `counts` maps an award kind to how many happened;
## `awards` maps a kind to what one is worth; `extended_by` are the kinds that
## feed the chain and are the only ones the multiplier applies to.
##
## Returns `{delta, broken}`.
static func apply(
	state: Dictionary,
	awards: Dictionary,
	steps: PackedInt32Array,
	extended_by: PackedStringArray,
	counts: Dictionary,
	broken: bool,
	chained_at_all: bool
) -> Dictionary:
	if broken and chained_at_all:
		state["chain"] = 0
	if chained_at_all:
		var extended := 0
		for kind in extended_by:
			extended += int(counts.get(kind, 0))
		state["chain"] = int(state["chain"]) + extended
		state["multiplier"] = chain_multiplier(int(state["chain"]), steps)
	var delta := 0.0
	for kind: Variant in counts:
		var paid := int(counts[kind])
		if paid <= 0:
			continue
		var award := float(awards.get(kind, 0))
		var chained := chained_at_all and extended_by.has(String(kind))
		var multiplier := float(state["multiplier"]) if chained else 1.0
		delta += float(paid) * award * multiplier
	state["total"] = float(state["total"]) + delta
	return {"delta": delta, "broken": broken and chained_at_all}
