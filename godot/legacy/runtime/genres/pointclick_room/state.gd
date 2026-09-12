class_name RoomState
extends RefCounted

## The room's whole gameplay as one pure reducer.
##
## A port of `web/lib/pointclick/state.ts`. This is deliberately the same state
## machine the Python solvability proof searches — flags, inventory, revealed,
## fired, with the same availability rules — so a room the proof admits is a
## room this runtime can finish. No timers, no physics, no hidden state: every
## transition is a click.
##
## Because there is no clock, there is no fixed step and no roster here. A room
## is not sealed into a frame order: it is a function from a state and a click to
## the next state and everything that happened inside it.

## Every operation a room may author, in the order an effect performs them.
##
## The authored form is one record with four optional fields rather than a
## tagged operation, and a record may carry several at once — so the effects
## family is reached through a *lowering* rather than by renaming a field. The
## order is kept exactly: an effect that grants an item and reveals the hotspot
## it is used on is not the same effect the other way round.
const EFFECT_OPERATIONS := ["set_flag", "grant_item", "remove_item", "reveal_hotspot"]

const MISS_LINE := "Nothing happens."
const MISS_WITH_ITEM_LINE := "That doesn't work here."


## Every flag this room can read or write, from its own interactions and its win.
##
## A room does not declare a flag list the way a scenario does, so the vocabulary
## is recovered from the document: it is exactly the set of names the reducer can
## ever compare against.
static func flag_vocabulary(manifest: Dictionary) -> Dictionary:
	var flags := {}
	for flag in (manifest["win"] as Dictionary)["requires"]:
		flags[String(flag)] = true
	for entry: Variant in (manifest["interactions"] as Array):
		var interaction: Dictionary = entry
		for flag in (interaction["requires"] as PackedStringArray):
			flags[String(flag)] = true
		for effect: Variant in (interaction["effects"] as Array):
			var authored: Dictionary = effect
			if authored.has("set_flag"):
				flags[String(authored["set_flag"])] = true
	return flags


## The room as the player finds it, optionally with facts an earlier beat set.
##
## `carried_flags` is a case's shared fact set. Only names this room actually
## uses are seeded: a fact it never mentions cannot change what it does, and
## putting it in the state would put a name in the machine the solvability proof
## never searched.
static func initial(manifest: Dictionary, carried_flags: PackedStringArray = PackedStringArray()) -> Dictionary:
	var vocabulary := flag_vocabulary(manifest)
	var seeded := {}
	for flag in carried_flags:
		if vocabulary.has(flag):
			seeded[flag] = true
	var flags := seeded.keys()
	flags.sort()
	var required: PackedStringArray = (manifest["win"] as Dictionary)["requires"]
	var solved := true
	for flag in required:
		if not seeded.has(flag):
			solved = false
			break
	return {
		"flags": flags,
		"inventory": {},
		"revealed": [],
		"fired": [],
		"selectedItem": null,
		"narration": String(manifest["displayName"]),
		"solved": solved,
	}


static func hotspot_visible(manifest: Dictionary, state: Dictionary, hotspot_id: String) -> bool:
	for entry: Variant in (manifest["hotspots"] as Array):
		var hotspot: Dictionary = entry
		if String(hotspot["id"]) != hotspot_id:
			continue
		return not bool(hotspot["hidden"]) or (state["revealed"] as Array).has(hotspot_id)
	return false


## One click, and everything that happened inside it.
##
## Returns `{state, events}`. A miss narrates rather than refusing: a player who
## tried something that does not work has not made an error, and the sentence
## they read is how the room says so.
static func interact_turn(
	manifest: Dictionary, state: Dictionary, verb: String, hotspot_id: String, item: Variant = null
) -> Dictionary:
	var events: Array = []
	var interactions: Array = manifest["interactions"]
	# No distance: this model has no space to measure, so the first available
	# interaction the author wrote wins.
	var index := FamilyAffordance.select(
		interactions.size(),
		func(at: int) -> bool:
			return _available(manifest, state, at, verb, hotspot_id, item)
	)
	if index >= 0:
		events.append(
			{
				"type": "interaction/outcome",
				"index": index,
				"verb": verb,
				"hotspot": hotspot_id,
				"item": item,
			}
		)
		# The effects run inside the application, so the outcome is announced
		# first and the operations it performed follow it, in authored order.
		return {"state": _apply(manifest, state, index, events), "events": events}
	events.append(
		{"type": "interaction/refused", "verb": verb, "hotspot": hotspot_id, "item": item}
	)
	var missed := state.duplicate(true)
	missed["selectedItem"] = null
	missed["narration"] = MISS_LINE if item == null else MISS_WITH_ITEM_LINE
	return {"state": missed, "events": events}


## Resolve one primary click the way a player expects: a held item tries
## use-with-item; otherwise an available bare `use` wins, else `inspect`.
static func click_hotspot_turn(
	manifest: Dictionary, state: Dictionary, hotspot_id: String
) -> Dictionary:
	if state["selectedItem"] != null:
		return interact_turn(manifest, state, "use", hotspot_id, state["selectedItem"])
	var interactions: Array = manifest["interactions"]
	for index in interactions.size():
		if _available(manifest, state, index, "use", hotspot_id, null):
			return interact_turn(manifest, state, "use", hotspot_id)
	return interact_turn(manifest, state, "inspect", hotspot_id)


## Pick up or put down a held item. Selecting what is already held clears it.
static func select_item(state: Dictionary, item_id: Variant) -> Dictionary:
	if item_id != null and FamilyBag.carried(state["inventory"], String(item_id)) < 1:
		return state
	var next := state.duplicate(true)
	next["selectedItem"] = null if state["selectedItem"] == item_id else item_id
	return next


static func _available(
	manifest: Dictionary,
	state: Dictionary,
	index: int,
	verb: String,
	hotspot_id: String,
	item: Variant
) -> bool:
	var interaction: Dictionary = (manifest["interactions"] as Array)[index]
	if String(interaction["verb"]) != verb or String(interaction["hotspot"]) != hotspot_id:
		return false
	if interaction["item"] != item:
		return false
	# An interaction with effects fires once. One with none never fires at all,
	# so looking twice is the same state and the same occurrence as looking once.
	if not (interaction["effects"] as Array).is_empty() and (state["fired"] as Array).has(index):
		return false
	for flag in (interaction["requires"] as PackedStringArray):
		if not (state["flags"] as Array).has(String(flag)):
			return false
	if item != null and FamilyBag.carried(state["inventory"], String(item)) < 1:
		return false
	return hotspot_visible(manifest, state, hotspot_id)


static func _apply(
	manifest: Dictionary, state: Dictionary, index: int, events: Array
) -> Dictionary:
	var interaction: Dictionary = (manifest["interactions"] as Array)[index]
	var flags := {}
	for flag: Variant in (state["flags"] as Array):
		flags[String(flag)] = true
	var revealed := {}
	for id: Variant in (state["revealed"] as Array):
		revealed[String(id)] = true
	# A single-element array so the handlers below can write to it: a Callable
	# closes over the binding, and the bag is replaced rather than mutated.
	var inventory: Array = [state["inventory"]]

	# The vocabulary, sealed against the handlers meant to answer it: an
	# operation this room may author and nothing implements is a refusal rather
	# than an effect that quietly does nothing.
	var vocabulary: Variant = FamilyEffects.seal(
		PackedStringArray(EFFECT_OPERATIONS),
		{
			"set_flag": func(payload: Variant) -> void:
				var flag := String(payload)
				events.append(
					{"type": "effects/applied", "operation": "set_flag", "payload": flag}
				)
				flags[flag] = true,
			# The unit grant, and the sentence that keeps this bag a set: a
			# room's item is carried or it is not, so a second grant for the
			# same name is the no-op it has always been rather than a second
			# unit.
			"grant_item": func(payload: Variant) -> void:
				var item_id := String(payload)
				events.append(
					{"type": "effects/applied", "operation": "grant_item", "payload": item_id}
				)
				if FamilyBag.carried(inventory[0], item_id) < 1:
					inventory[0] = FamilyBag.grant(inventory[0], item_id, 1)["bag"],
			# `remove_item` takes the stack, however deep it is.
			"remove_item": func(payload: Variant) -> void:
				var item_id := String(payload)
				events.append(
					{"type": "effects/applied", "operation": "remove_item", "payload": item_id}
				)
				inventory[0] = FamilyBag.consume(
					inventory[0], item_id, FamilyBag.carried(inventory[0], item_id)
				)["bag"],
			"reveal_hotspot": func(payload: Variant) -> void:
				var hotspot_id := String(payload)
				events.append(
					{
						"type": "effects/applied",
						"operation": "reveal_hotspot",
						"payload": hotspot_id,
					}
				)
				revealed[hotspot_id] = true,
		}
	)
	if KernelRefusal.is_refusal(vocabulary):
		push_error((vocabulary as KernelRefusal).line())
		return state
	for effect: Variant in (interaction["effects"] as Array):
		FamilyEffects.apply(vocabulary, _lowered(effect))

	var fired: Array = (state["fired"] as Array).duplicate()
	if not (interaction["effects"] as Array).is_empty():
		fired.append(index)
		fired.sort()
	var required: PackedStringArray = (manifest["win"] as Dictionary)["requires"]
	var solved := true
	for flag in required:
		if not flags.has(String(flag)):
			solved = false
			break
	var just_solved := solved and not bool(state["solved"])
	if just_solved:
		events.append({"type": "room/solved"})
	var narration := String(interaction["narration"])
	if just_solved:
		narration = "%s %s" % [narration, String((manifest["win"] as Dictionary)["narration"])]
	var flag_list := flags.keys()
	flag_list.sort()
	var revealed_list := revealed.keys()
	revealed_list.sort()
	return {
		"flags": flag_list,
		"inventory": inventory[0],
		"revealed": revealed_list,
		"fired": fired,
		"selectedItem": null,
		"narration": narration,
		"solved": solved,
	}


## One authored effect, as the operations it performs, in field order.
static func _lowered(effect: Variant) -> Array:
	var authored: Dictionary = effect
	var lowered: Array = []
	for operation in EFFECT_OPERATIONS:
		if authored.has(operation):
			lowered.append({"operation": operation, "payload": authored[operation]})
	return lowered
