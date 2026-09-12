extends RefCounted

## Where a creature stands, and what it does when it was stood up on a ledge.
##
## The package authors `terrain_and_decks` and the director has always honoured
## it — the reservation it returns names a deck. What nothing did was tell the
## creature: it was created with a terrain lane and every step re-read the ground
## height under its feet, so a body reserved onto a ledge dropped to the floor on
## the first frame it moved. Both goldens author `terrain` only, so neither could
## have said so.


func run(h: TestHarness) -> void:
	var parsed: Variant = PlatformerMaps.parse(_manifest())
	if KernelRefusal.is_refusal(parsed) or not (parsed is Dictionary):
		h.fail("test_mobs: the fixture package does not parse")
		return
	var package: Dictionary = parsed
	var map: Dictionary = (package["maps"] as Dictionary)["road-map"]
	var decks: Array = map["platforms"]
	if decks.is_empty():
		h.fail("test_mobs: road-map publishes no deck to stand on")
		return
	var deck: Dictionary = decks[0]
	_on_the_ground(h, map)
	_on_a_deck(h, map, deck)
	h.done()


func _on_the_ground(h: TestHarness, map: Dictionary) -> void:
	var floor_x := float(map["worldWidthPx"]) / 2.0
	var mob := PlatformerMob.create(
		1, "mob_1", "road-map/mob/1", 0, "wary", 3, floor_x, 0.0, map
	)
	h.assert_eq(String(mob["deckId"]), "", "a creature the director put on the floor names no deck")
	# After the first step rather than at creation: `create` records the position
	# the director chose and the walk is what seats a body on the surface under it.
	PlatformerMob.wander(mob, map, 1.0 / 30.0)
	var settled := float(mob["y"])
	for step in range(40):
		PlatformerMob.wander(mob, map, 1.0 / 30.0)
	h.assert_near(
		float(mob["y"]), settled, 1e-6, "and walking never lifts it off the ground it walks on"
	)


func _on_a_deck(h: TestHarness, map: Dictionary, deck: Dictionary) -> void:
	var deck_y := float(deck["deckY"])
	var middle := (float(deck["left"]) + float(deck["right"])) / 2.0
	var mob := PlatformerMob.create(
		2, "mob_2", "road-map/mob/2", 0, "wary", 3, middle, deck_y, map, String(deck["id"])
	)
	h.assert_eq(
		String(mob["deckId"]), String(deck["id"]), "one stood up on a ledge remembers which"
	)
	h.assert_near(float(mob["y"]), deck_y, 1e-6, "and starts at the ledge's own height")
	h.assert_true(
		float(mob["laneMinX"]) >= float(deck["left"]),
		"its lane is the ledge rather than the shelf under it"
	)
	h.assert_true(float(mob["laneMaxX"]) <= float(deck["right"]), "at both ends")

	# The defect this exists for: a step used to re-read the terrain height.
	var lowest := deck_y
	for step in range(600):
		PlatformerMob.wander(mob, map, 1.0 / 30.0)
		lowest = maxf(lowest, float(mob["y"]))
		h.assert_true(
			float(mob["x"]) >= float(deck["left"]) and float(mob["x"]) <= float(deck["right"]),
			"and twenty seconds of patrol never walks it off the end"
		)
	h.assert_near(
		lowest, deck_y, 1e-6, "nor drops it to the floor the moment it moves (y grows downward)"
	)


func _manifest() -> Dictionary:
	var file := FileAccess.open(
		"res://tests/fixtures/sideview_platformer/manifest.json", FileAccess.READ
	)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed if parsed is Dictionary else {}
