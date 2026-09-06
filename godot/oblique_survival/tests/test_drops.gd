extends RefCounted

## Drops: the three-phase airborne / sliding / settled machine, the biome's
## friction, and the magnet pickup.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_drops: could not open %s" % TestHarness.RUN_DIR)
		return
	_settles_on_land(h, w)
	_friction_decides_the_skid(h, w)
	_magnet_pickup(h, w)


func _settles_on_land(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	h.assert_true(bool(w.is_land.call(0.0, 0.0)), "the camp is on land")
	SysDrops.spawn_drops(w, [{"item_id": "log", "count": 4}], 0.0, 0.0, 1.0, 0.0, 1.2)
	h.assert_eq(w.entities.size(), 4, "four logs were thrown")
	var settled_at := -1.0
	var left_the_land := false
	for i in 120:
		Sim.step(w, SimFixture.STEP)
		var all_settled := true
		for entity in w.entities:
			var item := entity as Dictionary
			if not bool(item["settled"]):
				all_settled = false
			if not bool(w.is_land.call(float(item["x"]), float(item["z"]))):
				left_the_land = true
		if all_settled and settled_at < 0.0:
			settled_at = float(i + 1) * SimFixture.STEP
	h.assert_true(settled_at >= 0.0 and settled_at <= 2.0,
		"every drop settles inside two seconds (settled at %s s)" % str(settled_at))
	h.assert_true(not left_the_land, "and no drop ever leaves the land")
	for entity in w.entities:
		var item := entity as Dictionary
		h.assert_near(float(item["y"]), 0.0, 1e-9, "a settled drop rests on the ground")
		h.assert_near(float(item["vx"]), 0.0, 1e-9, "with no sideways speed left")
		h.assert_true(bool(item["grounded"]), "and it is down for good")


func _friction_decides_the_skid(h: TestHarness, w: World) -> void:
	# Same throw, two surfaces. The slide brakes at the biome's friction times
	# g, sampled under the drop, so a stone runs on scree (0.45) and stops
	# short in the bog (1.1). Both patches are flat runs of one biome, on land,
	# taken from the run's own biome plate.
	h.assert_near(float(w.friction_at(24.0, -200.0)), 0.45, 1e-6, "the scree patch is scree")
	h.assert_near(float(w.friction_at(-88.0, -200.0)), 1.1, 1e-6, "the bog patch is bog")
	var scree := _skid(w, 24.0, -200.0)
	var bog := _skid(w, -88.0, -200.0)
	h.assert_true(scree > bog,
		"a low-friction surface carries the drop farther (%.3f m on scree vs %.3f m in the bog)" % [scree, bog])
	# v^2 / (2 * friction * g), within a step of the discrete slide.
	h.assert_near(scree, 9.0 / (2.0 * 0.45 * SysDrops.SLIDE_GRAVITY), 0.06,
		"the scree skid matches the closed-form slide")
	h.assert_near(bog, 9.0 / (2.0 * 1.1 * SysDrops.SLIDE_GRAVITY), 0.06,
		"the bog skid matches it too")


## A stone laid on the ground at (x, z) with 3 m/s along +x, slid until it
## settles; returns how far it travelled. Laid by hand rather than thrown, so
## no PRNG draw stands between the two surfaces.
func _skid(w: World, x: float, z: float) -> float:
	SimFixture.bare(w)
	w.entities.append({
		"id": "i0", "kind": "item", "item_id": "stone",
		"x": x, "z": z, "y": 0.0, "vx": 3.0, "vz": 0.0, "vy": 0.0,
		"settled": false, "grounded": true, "age": 0.0, "radius": 0.0,
		"seed": 0, "uses": null, "taken": false, "pulled": false, "dirty": false,
	})
	var item: Dictionary = w.entities[0]
	for i in 600:
		SysDrops.update(w, SimFixture.STEP)
		if bool(item["settled"]):
			break
	return absf(float(item["x"]) - x)


func _magnet_pickup(h: TestHarness, w: World) -> void:
	var gameplay: Dictionary = w.manifest["gameplay"]
	var before: Variant = gameplay.get("pickup", "manual")
	gameplay["pickup"] = "magnet"
	SimFixture.bare(w)
	w.player.x = 0.0
	w.player.z = 0.0
	# Dropped straight down at the player's feet, well inside PICKUP_RADIUS.
	SysDrops.spawn_drops(w, [{"item_id": "berry", "count": 1}], 0.6, 0.0, 0.0, 0.0, 0.0)
	var item: Dictionary = w.entities[0]
	h.assert_true(Targeting.target_for(w, item) == null,
		"under magnet pickup the key never targets a drop")
	var taken := false
	for i in 240:
		Sim.step(w, SimFixture.STEP)
		if w.entities.is_empty():
			taken = true
			break
	h.assert_true(taken, "the magnet drew the berry in")
	h.assert_eq(Inventory.count(w, "berry"), 1, "and it is in the pack")
	h.assert_eq(SimFixture.events_of(w, "pickup").size(), 1, "one pickup was heard")
	# A full pack releases the magnet rather than eating the drop.
	SimFixture.bare(w)
	Inventory.inv_add(w, "log", 120)
	SysDrops.spawn_drops(w, [{"item_id": "berry", "count": 1}], 0.2, 0.0, 0.0, 0.0, 0.0)
	var stuck: Dictionary = w.entities[w.entities.size() - 1]
	w.message = ""
	for i in 240:
		Sim.step(w, SimFixture.STEP)
	h.assert_true(Targeting.index_of(w.entities, stuck) >= 0, "a full pack leaves the drop on the ground")
	h.assert_eq(w.message, "Hands full.", "and says so")
	gameplay["pickup"] = before
