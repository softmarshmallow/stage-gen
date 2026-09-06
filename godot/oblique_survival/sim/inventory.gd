class_name Inventory
extends RefCounted

## The pack. Slots hold stacks; an item's stack_max, use and tool come from
## items.toml through the manifest and nothing here knows an item by name.
## Every helper answers with what it could not do (the leftover) rather than
## throwing: a full pack leaves the thing on the ground and says so.
##
## Ported verbatim from viewer/index.html lines 597-690.


## manifest.items[item_id], or null.
static func item_spec(world: World, item_id: String) -> Variant:
	var items: Variant = world.manifest.get("items", null)
	if items == null:
		return null
	return (items as Dictionary).get(item_id, null)


## The authored display name, or the id with underscores opened out.
static func item_name(world: World, item_id: String) -> String:
	var spec: Variant = item_spec(world, item_id)
	if spec != null:
		var display: Variant = (spec as Dictionary).get("display_name", null)
		if display != null and str(display) != "":
			return str(display)
	return item_id.replace("_", " ")


## The base slots plus every carried pack's bonus.
static func slot_capacity(world: World) -> int:
	var extra := 0
	for slot in world.slots:
		if slot == null:
			continue
		var spec: Variant = item_spec(world, str((slot as Dictionary)["item"]))
		if spec == null:
			continue
		var use: Variant = (spec as Dictionary).get("use", null)
		if use != null and str((use as Dictionary).get("kind", "")) == "carry":
			extra += int((use as Dictionary).get("slots", 0)) * int((slot as Dictionary)["count"])
	return world.base_slots + extra


## Every worn thing's insulation, summed and capped: the cold's drain is
## scaled by what is left. Note the viewer does not multiply by slot.count.
static func insulation(world: World) -> float:
	var total := 0.0
	for slot in world.slots:
		if slot == null:
			continue
		var spec: Variant = item_spec(world, str((slot as Dictionary)["item"]))
		if spec == null:
			continue
		var use: Variant = (spec as Dictionary).get("use", null)
		if use != null and str((use as Dictionary).get("kind", "")) == "wear":
			total += float((use as Dictionary).get("insulation", 0.0))
	return minf(0.9, total)


## How many of an item the pack holds (the viewer's invCount).
static func count(world: World, item_id: String) -> int:
	var total := 0
	for slot in world.slots:
		if slot != null and str((slot as Dictionary)["item"]) == item_id:
			total += int((slot as Dictionary)["count"])
	return total


## Whether the pack holds at least ``n`` of an item.
static func has(world: World, item_id: String, n: int = 1) -> bool:
	return count(world, item_id) >= n


## Add up to ``amount``; returns how many did not fit. A tool keeps its wear.
static func inv_add(world: World, item_id: String, amount: int, uses: Variant = null) -> int:
	var spec: Variant = item_spec(world, item_id)
	var stack_max := 1
	if spec != null:
		var authored := int((spec as Dictionary).get("stack_max", 0))
		if authored != 0:
			stack_max = authored
	var capacity := slot_capacity(world)
	while world.slots.size() < capacity:
		world.slots.append(null)
	var left := amount
	# Pass 1: top up existing non-tool stacks, in slot order.
	for slot in world.slots:
		if left == 0:
			break
		if slot == null:
			continue
		var entry := slot as Dictionary
		if str(entry["item"]) == item_id and int(entry["count"]) < stack_max and entry["uses"] == null:
			var take: int = mini(stack_max - int(entry["count"]), left)
			entry["count"] = int(entry["count"]) + take
			left -= take
	# Pass 2: fill empty slots, in slot order.
	var i := 0
	while i < capacity and left > 0:
		if world.slots[i] == null:
			var take: int = mini(stack_max, left)
			var slot_uses: Variant = null
			if spec != null and (spec as Dictionary).get("tool", null) != null:
				if uses != null:
					slot_uses = uses
				else:
					slot_uses = int(((spec as Dictionary)["tool"] as Dictionary).get("uses", 0))
			world.slots[i] = {"item": item_id, "count": take, "uses": slot_uses}
			left -= take
		i += 1
	return left


## Take up to ``amount`` out of the pack, last stack first; returns how many
## came out.
static func inv_remove(world: World, item_id: String, amount: int) -> int:
	var left := amount
	var i := world.slots.size() - 1
	while i >= 0 and left > 0:
		var slot: Variant = world.slots[i]
		if slot != null and str((slot as Dictionary)["item"]) == item_id:
			var entry := slot as Dictionary
			var take: int = mini(int(entry["count"]), left)
			entry["count"] = int(entry["count"]) - take
			left -= take
			if int(entry["count"]) <= 0:
				world.slots[i] = null
		i -= 1
	return amount - left


## The first carried tool that serves a verb, or -1. Carried is enough;
## nothing is equipped, and wear is not considered.
static func inv_find_tool(world: World, verb: String) -> int:
	for i in world.slots.size():
		var slot: Variant = world.slots[i]
		if slot == null:
			continue
		var spec: Variant = item_spec(world, str((slot as Dictionary)["item"]))
		if spec == null:
			continue
		var tool_spec: Variant = (spec as Dictionary).get("tool", null)
		if tool_spec != null and str((tool_spec as Dictionary).get("verb", "")) == verb:
			return i
	return -1


## One completed interaction wears the tool by one; at zero it is gone.
static func wear_tool(world: World, index: int) -> void:
	if index < 0 or index >= world.slots.size():
		return
	var slot: Variant = world.slots[index]
	if slot == null:
		return
	var entry := slot as Dictionary
	if entry["uses"] == null:
		return
	entry["uses"] = int(entry["uses"]) - 1
	if int(entry["uses"]) <= 0:
		world.slots[index] = null
		Helpers.say(world, "The %s breaks." % item_name(world, str(entry["item"])))
