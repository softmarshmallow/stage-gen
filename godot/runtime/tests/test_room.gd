extends RefCounted

## The point-and-click room: its contract, and the reducer that is its whole
## gameplay.
##
## The room has no clock and so no roster and no sealed order — it is a function
## from a state and a click to the next state and everything that happened
## inside it. What that buys is a test that can assert a whole run in a few
## lines, which is what this does.
##
## The scripted run itself is proved elsewhere and harder: `tools/room_parity.gd`
## replays the browser's own fourteen clicks and the digests are identical.

func run(h: TestHarness) -> void:
	var manifest: Variant = RoomContract.parse(_fixture())
	h.assert_true(not KernelRefusal.is_refusal(manifest), "the fixture room parses")
	if KernelRefusal.is_refusal(manifest):
		return
	var room: Dictionary = manifest
	_contract(h, room)
	_bag(h)
	_reducer(h, room)
	h.done()


func _contract(h: TestHarness, room: Dictionary) -> void:
	h.assert_eq((room["hotspots"] as Array).size(), 3, "the fixture room has three hotspots")
	h.assert_eq(String(room["roomId"]), "test_room", "and names itself")
	var raw: Dictionary = (_fixture() as Dictionary)
	var wrong := raw.duplicate(true)
	wrong["kind"] = "dialogue-scene-bundle-v8"
	h.assert_true(
		KernelRefusal.is_refusal(RoomContract.parse(wrong)),
		"a document of another kind is refused rather than half-read"
	)
	var stale := raw.duplicate(true)
	stale["schema_version"] = 2
	h.assert_true(
		KernelRefusal.is_refusal(RoomContract.parse(stale)),
		"and so is one at another schema version"
	)
	# An interaction that acts on a hotspot the room does not publish is a
	# closure the package validator should have caught; the runtime refuses it
	# rather than silently never firing it.
	var dangling := raw.duplicate(true)
	((dangling["interactions"] as Array)[0] as Dictionary)["on"] = {
		"verb": "inspect", "hotspot": "nowhere", "item": null
	}
	h.assert_true(
		KernelRefusal.is_refusal(RoomContract.parse(dangling)),
		"an interaction on an unpublished hotspot is refused"
	)


func _bag(h: TestHarness) -> void:
	var bag := {}
	var granted := FamilyBag.grant(bag, "key", 1)
	h.assert_eq(int(granted["moved"]), 1, "a grant moves what it promised")
	h.assert_eq(FamilyBag.carried(granted["bag"], "key"), 1, "and the bag holds it")
	# A grant is all or nothing against a capacity; a spend is a floor at zero.
	var full := FamilyBag.grant({"key": 2}, "key", 3, 4)
	h.assert_eq(String(full["refusal"]), "capacity", "a grant past the ceiling is refused whole")
	h.assert_eq(int(full["moved"]), 0, "and moves nothing")
	var partial := FamilyBag.consume({"key": 2}, "key", 5)
	h.assert_eq(int(partial["moved"]), 2, "a spend takes as many as are there")
	h.assert_true(
		not (partial["bag"] as Dictionary).has("key"),
		"and an emptied stack leaves the bag rather than sitting at zero"
	)
	h.assert_eq(
		String(FamilyBag.consume({}, "key", 1)["refusal"]),
		"absent",
		"spending what is not carried says so"
	)
	var ids := FamilyBag.item_ids({"rope": 1, "key": 1})
	h.assert_eq(ids[0], "key", "the item list is sorted, not in pickup order")


func _reducer(h: TestHarness, room: Dictionary) -> void:
	var state := RoomState.initial(room)
	h.assert_true(not bool(state["solved"]), "a room does not begin solved")
	h.assert_eq(String(state["narration"]), String(room["displayName"]), "and names itself")

	# Looking has no effects, so it never fires and looking twice is the same
	# state and the same occurrence as looking once.
	var first := RoomState.interact_turn(room, state, "inspect", "bench")
	h.assert_eq(
		String(((first["events"] as Array)[0] as Dictionary)["type"]),
		"interaction/outcome",
		"a look that lands is an outcome"
	)
	var second := RoomState.interact_turn(room, first["state"], "inspect", "bench")
	h.assert_eq(
		String(((second["events"] as Array)[0] as Dictionary)["type"]),
		"interaction/outcome",
		"and looking again lands again, because nothing fired"
	)

	# The chest before the key: a hidden hotspot and an unmet item, both refused.
	var early := RoomState.interact_turn(room, state, "use", "prize")
	h.assert_eq(
		String(((early["events"] as Array)[0] as Dictionary)["type"]),
		"interaction/refused",
		"a hidden hotspot refuses"
	)
	h.assert_eq(
		String((early["state"] as Dictionary)["narration"]),
		RoomState.MISS_LINE,
		"and narrates rather than throwing"
	)

	var keyed := RoomState.interact_turn(room, state, "use", "bench")
	var with_key: Dictionary = keyed["state"]
	h.assert_eq(FamilyBag.carried(with_key["inventory"], "key"), 1, "the bench yields a key")
	# The room's bag is a set: a second grant of the same name is a no-op.
	var again := RoomState.interact_turn(room, with_key, "use", "bench")
	h.assert_eq(
		FamilyBag.carried((again["state"] as Dictionary)["inventory"], "key"),
		1,
		"and a second grant of one name is the no-op it has always been"
	)
	# An interaction with effects fires once, so the second click misses.
	h.assert_eq(
		String(((again["events"] as Array)[0] as Dictionary)["type"]),
		"interaction/refused",
		"an interaction with effects fires exactly once"
	)

	var held := RoomState.select_item(with_key, "key")
	h.assert_eq(String((held as Dictionary)["selectedItem"]), "key", "an item can be held")
	h.assert_true(
		RoomState.select_item(held, "key")["selectedItem"] == null,
		"and selecting it again puts it down"
	)
	h.assert_true(
		RoomState.select_item(with_key, "rope")["selectedItem"] == null,
		"an item that is not carried cannot be held"
	)

	var opened := RoomState.interact_turn(room, with_key, "use", "chest", "key")
	var after: Dictionary = opened["state"]
	h.assert_true((after["revealed"] as Array).has("prize"), "the chest reveals the prize")
	h.assert_true(
		(after["flags"] as Array).has("chest_open"), "and sets the flag, in authored order"
	)
	h.assert_true(after["selectedItem"] == null, "an interaction clears the held item")
	var operations := PackedStringArray()
	for entry: Variant in (opened["events"] as Array):
		var event: Dictionary = entry
		if String(event["type"]) == "effects/applied":
			operations.append(String(event["operation"]))
	h.assert_eq(operations.size(), 2, "two effects, and they are announced")
	h.assert_eq(operations[0], "set_flag", "in the order the author wrote them")

	var solved := RoomState.interact_turn(room, after, "use", "prize")
	h.assert_true(bool((solved["state"] as Dictionary)["solved"]), "taking the prize solves it")
	var kinds := PackedStringArray()
	for entry: Variant in (solved["events"] as Array):
		kinds.append(String((entry as Dictionary)["type"]))
	h.assert_true(kinds.has("room/solved"), "and says so exactly once")
	# The win's own line is appended to the interaction's, on the click that
	# solves it and no later one.
	h.assert_true(
		String((solved["state"] as Dictionary)["narration"]).ends_with(
			String((room["win"] as Dictionary)["narration"])
		),
		"the win narrates on the click that earns it"
	)


func _fixture() -> Variant:
	var file := FileAccess.open("res://tests/fixtures/pointclick_room/manifest.json", FileAccess.READ)
	if file == null:
		return null
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed
