extends RefCounted

## Targeting: the edge conventions, nearest-wins, and the facing rule.


func run(h: TestHarness) -> void:
	var w := SimFixture.world()
	if w == null:
		h.fail("test_targeting: could not open %s" % TestHarness.RUN_DIR)
		return
	_edges(h, w)
	_nearest_wins(h, w)
	_ties_keep_list_order(h, w)
	_facing(h, w)
	_offers_nothing(h, w)


func _edges(h: TestHarness, w: World) -> void:
	# A prop's edge is the centre distance less its footprint; a forage piece
	# and a dropped item measure from their centre.
	SimFixture.bare(w)
	var pine := SimFixture.prop(w, "p1", "pine", "grown", 0.0, 3.0)
	var moss := SimFixture.forage(w, "f1", 11, 0.0, 2.8)
	w.entities.append(pine)
	w.entities.append(moss)
	h.assert_near(float(pine["radius"]), 0.374, 1e-6, "the pine footprint is the authored one")
	var pine_target: Variant = Targeting.target_for(w, pine)
	var moss_target: Variant = Targeting.target_for(w, moss)
	h.assert_true(pine_target != null, "a grown pine offers a chop")
	h.assert_true(moss_target != null, "an untaken moss patch offers a take")
	h.assert_near(float((pine_target as Dictionary)["edge"]), 3.0 - 0.374, 1e-6,
		"the prop edge subtracts the footprint radius")
	h.assert_near(float((moss_target as Dictionary)["edge"]), 2.8, 1e-6,
		"the forage edge is the centre distance")


func _nearest_wins(h: TestHarness, w: World) -> void:
	# The pine's centre is farther than the moss patch's, but its edge is
	# nearer, and the edge is what the scan compares.
	SimFixture.bare(w)
	var pine := SimFixture.prop(w, "p1", "pine", "grown", 0.0, 3.0)
	var moss := SimFixture.forage(w, "f1", 11, 0.0, 2.8)
	w.entities.append(moss)
	w.entities.append(pine)
	var best: Variant = Targeting.interactable_at(w)
	h.assert_true(best != null, "something is within the approach radius")
	h.assert_eq(str(((best as Dictionary)["entity"] as Dictionary)["id"]), "p1",
		"the nearer edge wins, not the nearer centre")
	# Outside the notice radius (max(reach, approach) = 4.5 m) nothing is seen.
	SimFixture.bare(w)
	w.entities.append(SimFixture.forage(w, "f2", 11, 0.0, 4.6))
	h.assert_true(Targeting.interactable_at(w) == null, "4.6 m is past the approach radius")


func _ties_keep_list_order(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	w.entities.append(SimFixture.prop(w, "a", "grass_tuft", "standing", 1.0, 0.0))
	w.entities.append(SimFixture.prop(w, "b", "grass_tuft", "standing", -1.0, 0.0))
	var best: Variant = Targeting.interactable_at(w)
	h.assert_eq(str(((best as Dictionary)["entity"] as Dictionary)["id"]), "a",
		"a tie goes to the earlier entity in list order")


func _facing(h: TestHarness, w: World) -> void:
	# The side wins whenever the sideways part is at least as large as the
	# toward-or-away part, so a perfect diagonal shows the side card.
	h.assert_eq(Targeting.facing_for(1.0, -1.0, 0.0, "front"), "right",
		"up and right together shows the right card")
	h.assert_eq(Targeting.facing_for(-1.0, -1.0, 0.0, "front"), "left",
		"up and left together shows the left card")
	h.assert_eq(Targeting.facing_for(1.0, 1.0, 0.0, "back"), "right",
		"down and right together shows the right card")
	h.assert_eq(Targeting.facing_for(0.0, 1.0, 0.0, "back"), "front",
		"straight at the camera is front")
	h.assert_eq(Targeting.facing_for(0.0, -1.0, 0.0, "front"), "back",
		"straight away from the camera is back")
	h.assert_eq(Targeting.facing_for(0.01, 0.02, 0.0, "left"), "left",
		"a heading under 0.05 keeps the last facing")
	h.assert_near(Targeting.facing_sign("left"), -1.0, 1e-9, "a left card mirrors")
	h.assert_near(Targeting.facing_sign("right"), 1.0, 1e-9, "a right card does not")
	# The yaw turns the whole rule with the camera: at 90 degrees, world +x
	# points at the camera.
	h.assert_eq(Targeting.facing_for(1.0, 0.0, PI / 2.0, "back"), "front",
		"at yaw 90 the world +x heading faces the camera")


func _offers_nothing(h: TestHarness, w: World) -> void:
	SimFixture.bare(w)
	# A spent bush waits for its regrow timer; a lit fire is not lit again.
	var picked := SimFixture.prop(w, "b1", "thorn_bush", "full", 0.0, 1.0)
	picked["state"] = "picked"
	w.entities.append(picked)
	h.assert_true(Targeting.target_for(w, picked) == null, "a picked bush offers nothing")
	var lit := SimFixture.prop(w, "c1", "campfire", "unlit", 0.0, 1.0)
	h.assert_true(Targeting.target_for(w, lit) != null, "an unlit fire offers a light")
	lit["state"] = "lit"
	h.assert_true(Targeting.target_for(w, lit) == null, "a lit fire offers nothing")
	# A mob is not a target; an unsettled drop is one from the moment it flies
	# (the eye and the held key follow it), but not ready until it settles.
	var hound := SimFixture.mob(w, "m1", "grub_hound", 0.0, 1.0)
	h.assert_true(Targeting.target_for(w, hound) == null, "a mob offers nothing")
	SysDrops.spawn_drops(w, [{"item_id": "log", "count": 1}], 0.0, 1.0, 0.0, 1.0, 1.0)
	var drop: Dictionary = w.entities[w.entities.size() - 1]
	var bouncing: Variant = Targeting.target_for(w, drop)
	h.assert_true(bouncing != null, "a bouncing drop is a target already")
	h.assert_false(bool((bouncing as Dictionary)["ready"]), "but not ready to be taken")
	Targeting.start_interaction(w, bouncing as Dictionary)
	h.assert_true(w.player.busy == null and not bool(drop["taken"]), "and starting the take waits")
	drop["settled"] = true
	var settled: Variant = Targeting.target_for(w, drop)
	h.assert_true(settled != null and bool((settled as Dictionary)["ready"]), "a settled drop is ready")
