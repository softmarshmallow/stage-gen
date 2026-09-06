class_name Inventory
extends RefCounted

## The pack. Slots hold stacks; an item's stack_max, use and tool come from
## items.toml through the manifest and nothing here knows an item by name.
## Every helper answers with what it could not do (the leftover) rather than
## throwing: a full pack leaves the thing on the ground and says so.
##
## Ported from viewer/index.html lines 597-690, then given the equipment the
## viewer did not have (`World.equipment`): a tool is worn in the `hand`, a
## `wear` item on the `body`, a `carry` pack on the `back`. Only the worn
## thing counts — the body's insulation, the back's slots — where the viewer
## counted anything in the pack; a tool still serves from the pack when no
## hand tool does, so a carried axe is enough to chop, and the hand only says
## which axe wears first.

## The three equipment kinds, in the order the HUD shows them.
const EQUIPMENT_KINDS := ["hand", "body", "back"]
## The `tool_slot` a target carries when the tool in hand serves it (a pack
## slot is 0 and up, -1 is none).
const HAND_SLOT := -2


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


## The base slots plus the pack on the back. A pack in a slot carries nothing
## until it is worn.
static func slot_capacity(world: World) -> int:
	var back: Variant = world.equipment.get("back", null)
	if back == null:
		return world.base_slots
	var spec: Variant = item_spec(world, str((back as Dictionary)["item"]))
	if spec == null:
		return world.base_slots
	var use: Variant = (spec as Dictionary).get("use", null)
	if use != null and str((use as Dictionary).get("kind", "")) == "carry":
		return world.base_slots + int((use as Dictionary).get("slots", 0))
	return world.base_slots


## The worn thing's insulation, capped: the cold's drain is scaled by what is
## left. A cloak in the pack warms nothing.
static func insulation(world: World) -> float:
	var body: Variant = world.equipment.get("body", null)
	if body == null:
		return 0.0
	var spec: Variant = item_spec(world, str((body as Dictionary)["item"]))
	if spec == null:
		return 0.0
	var use: Variant = (spec as Dictionary).get("use", null)
	if use != null and str((use as Dictionary).get("kind", "")) == "wear":
		return minf(0.9, float((use as Dictionary).get("insulation", 0.0)))
	return 0.0


## Which equipment kind an item is worn in: `hand` for a tool, `body` for a
## `wear` use, `back` for a `carry` use, "" for everything else.
static func equip_kind(world: World, item_id: String) -> String:
	var spec: Variant = item_spec(world, item_id)
	if spec == null:
		return ""
	if (spec as Dictionary).get("tool", null) != null:
		return "hand"
	var use: Variant = (spec as Dictionary).get("use", null)
	if use is Dictionary:
		match str((use as Dictionary).get("kind", "")):
			"wear":
				return "body"
			"carry":
				return "back"
	return ""


## Wear one of the item in a pack slot. What was worn there goes back into the
## pack (into the slot just emptied, so the two swap); a thing with no place
## to be worn is refused in words. True when it went on.
static func equip(world: World, index: int) -> bool:
	if index < 0 or index >= world.slots.size() or world.slots[index] == null:
		Helpers.say(world, "Nothing selected.")
		return false
	var entry := world.slots[index] as Dictionary
	var item_id := str(entry["item"])
	var kind := equip_kind(world, item_id)
	if kind == "":
		Helpers.say(world, "The %s is not worn." % item_name(world, item_id))
		return false
	var worn: Variant = world.equipment.get(kind, null)
	# One of the stack goes on; a single thing leaves its slot empty for what
	# comes off.
	var taken := {"item": item_id, "count": 1, "uses": entry["uses"]}
	entry["count"] = int(entry["count"]) - 1
	if int(entry["count"]) <= 0:
		world.slots[index] = null
	world.equipment[kind] = taken
	if worn != null:
		var previous := worn as Dictionary
		var left := inv_add(world, str(previous["item"]), int(previous["count"]), previous["uses"])
		if left > 0:
			# No room for what came off: undo the swap and say so.
			world.equipment[kind] = previous
			if world.slots[index] == null:
				world.slots[index] = taken
			else:
				(world.slots[index] as Dictionary)["count"] = int((world.slots[index] as Dictionary)["count"]) + 1
			Helpers.say(world, "Hands full.")
			return false
	# A pack worn grows the slots on the spot, not on the next thing added.
	while world.slots.size() < slot_capacity(world):
		world.slots.append(null)
	Helpers.say(world, "%s: %s." % [kind, item_name(world, item_id)])
	return true


## Take a worn thing off, back into the pack. The pack on the back comes off
## only once its own slots are empty; a pack with no room refuses. True when
## it came off.
static func unequip(world: World, kind: String) -> bool:
	var worn: Variant = world.equipment.get(kind, null)
	if worn == null:
		return false
	var entry := worn as Dictionary
	if kind == "back":
		var after := world.base_slots
		for i in world.slots.size():
			if world.slots[i] != null and i >= after:
				Helpers.say(world, "Empty the pack's own slots first.")
				return false
	world.equipment[kind] = null
	var left := inv_add(world, str(entry["item"]), int(entry["count"]), entry["uses"])
	if left > 0:
		world.equipment[kind] = entry
		Helpers.say(world, "Hands full.")
		return false
	if kind == "back":
		# The bonus slots are gone with the pack; they were empty.
		while world.slots.size() > slot_capacity(world):
			world.slots.pop_back()
	Helpers.say(world, "%s off." % item_name(world, str(entry["item"])))
	return true


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


## The tool in hand when it serves the verb (`HAND_SLOT`), else the first
## carried tool that does, else -1. Carried is enough to work; the hand only
## says which tool wears first.
static func inv_find_tool(world: World, verb: String) -> int:
	var hand: Variant = world.equipment.get("hand", null)
	if hand != null:
		var hand_spec: Variant = item_spec(world, str((hand as Dictionary)["item"]))
		if hand_spec != null:
			var hand_tool: Variant = (hand_spec as Dictionary).get("tool", null)
			if hand_tool != null and str((hand_tool as Dictionary).get("verb", "")) == verb:
				return HAND_SLOT
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


## One completed interaction wears the tool by one; at zero it is gone. The
## tool is the pack slot at `index`, or the one in hand at `HAND_SLOT`.
static func wear_tool(world: World, index: int) -> void:
	var slot: Variant = null
	if index == HAND_SLOT:
		slot = world.equipment.get("hand", null)
	elif index >= 0 and index < world.slots.size():
		slot = world.slots[index]
	if slot == null:
		return
	var entry := slot as Dictionary
	if entry["uses"] == null:
		return
	entry["uses"] = int(entry["uses"]) - 1
	if int(entry["uses"]) <= 0:
		if index == HAND_SLOT:
			world.equipment["hand"] = null
		else:
			world.slots[index] = null
		Helpers.say(world, "The %s breaks." % item_name(world, str(entry["item"])))
