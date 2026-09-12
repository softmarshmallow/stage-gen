extends RefCounted

## What a connected blow looks like beyond the number.
##
## The hitstop and the camera shake were ported because the world carries them and
## the goldens hash them. The three that are *drawn* — the flash, the spark fan and
## the burst a kill throws — were not, and could not have been noticed: a frame
## hash records that a creature died, and says nothing about whether anything
## happened on screen when it did. This is decision 0066's thesis with a second
## piece of evidence under it.


func run(h: TestHarness) -> void:
	_the_flash(h)
	_the_fan(h)
	_the_burst(h)
	_the_swing(h)
	_it_replays(h)
	h.done()


func _the_flash(h: TestHarness) -> void:
	h.assert_true(PlatformerImpact.flash(0.0), "a struck body is filled white on the frame it is hit")
	h.assert_true(
		PlatformerImpact.flash(PlatformerImpact.FLASH_MS - 1.0), "for a couple of frames"
	)
	h.assert_false(PlatformerImpact.flash(PlatformerImpact.FLASH_MS), "and no longer")
	h.assert_false(PlatformerImpact.flash(-1.0), "nor before the blow landed")
	h.assert_true(
		PlatformerImpact.lifetime_ms(true) > PlatformerImpact.lifetime_ms(false),
		"a kill is presented for longer than a hit, because it has a burst to finish"
	)


func _the_fan(h: TestHarness) -> void:
	var early := PlatformerImpact.rays(77, 100.0, 200.0, 1, false, 10.0)
	h.assert_eq(early.size(), PlatformerImpact.SPARK_RAYS, "a blow throws a fan of rays")
	h.assert_eq(
		PlatformerImpact.rays(77, 100.0, 200.0, 1, false, PlatformerImpact.SPARK_MS).size(),
		0,
		"and the fan is spent when its window closes"
	)

	# The fan grows, then fades.
	var grown := PlatformerImpact.rays(77, 100.0, 200.0, 1, false, 60.0)
	h.assert_true(
		_longest(grown, 100.0, 200.0) > _longest(early, 100.0, 200.0),
		"the rays grow out of the contact point rather than appearing at length"
	)
	var late := PlatformerImpact.rays(77, 100.0, 200.0, 1, false, 140.0)
	h.assert_true(
		float((late[0] as Dictionary)["alpha"]) < float((grown[0] as Dictionary)["alpha"]),
		"and fade once they have"
	)

	# Direction: the fan follows the blow.
	var rightward := PlatformerImpact.rays(77, 100.0, 200.0, 1, false, 60.0)
	var leftward := PlatformerImpact.rays(77, 100.0, 200.0, -1, false, 60.0)
	h.assert_true(
		_mean_x(rightward) > 100.0 and _mean_x(leftward) < 100.0,
		"a blow struck rightward throws its sparks rightward, and one struck left throws them left"
	)

	# A critical throws further and thicker.
	var ordinary := PlatformerImpact.rays(77, 100.0, 200.0, 1, false, 60.0)
	var big := PlatformerImpact.rays(77, 100.0, 200.0, 1, true, 60.0)
	h.assert_true(
		_longest(big, 100.0, 200.0) > _longest(ordinary, 100.0, 200.0),
		"a critical throws its sparks further"
	)
	h.assert_true(
		float((big[0] as Dictionary)["width"]) > float((ordinary[0] as Dictionary)["width"]),
		"and thicker, so the two read apart at a glance"
	)


func _the_burst(h: TestHarness) -> void:
	h.assert_eq(
		PlatformerImpact.shards(9, 100.0, 200.0, false, false, 10.0).size(),
		0,
		"a blow that did not kill scatters nothing"
	)
	var thrown := PlatformerImpact.shards(9, 100.0, 200.0, false, true, 10.0)
	h.assert_eq(thrown.size(), PlatformerImpact.BURST_SHARDS, "a kill scatters shards")
	h.assert_eq(
		PlatformerImpact.shards(9, 100.0, 200.0, false, true, PlatformerImpact.BURST_MS).size(),
		0,
		"and they are gone when the burst is over"
	)

	# Gravity: the cloud is thrown up and comes down.
	var rising := _mean_y(PlatformerImpact.shards(9, 100.0, 200.0, false, true, 40.0))
	var falling := _mean_y(PlatformerImpact.shards(9, 100.0, 200.0, false, true, 380.0))
	h.assert_true(
		rising < 200.0,
		"the shards leave with a lift on them, so a burst reads as thrown off the body (%f)" % rising
	)
	h.assert_true(
		falling > rising, "and fall back under gravity rather than drifting outward forever"
	)
	var early: Dictionary = (PlatformerImpact.shards(9, 100.0, 200.0, false, true, 20.0))[0]
	var late: Dictionary = (PlatformerImpact.shards(9, 100.0, 200.0, false, true, 380.0))[0]
	h.assert_true(
		float(late["alpha"]) < float(early["alpha"]) and float(late["radius"]) < float(early["radius"]),
		"and shrink and fade as they go"
	)


func _the_swing(h: TestHarness) -> void:
	h.assert_true(
		PlatformerImpact.swing_arc(0.0, 0.0, 1, 60.0, PlatformerImpact.SWING_MS).is_empty(),
		"a swing's arc is spent when the swing is"
	)
	var opening := PlatformerImpact.swing_arc(0.0, 0.0, 1, 60.0, 10.0)
	var closing := PlatformerImpact.swing_arc(0.0, 0.0, 1, 60.0, 120.0)
	h.assert_true(
		float(closing["endAngle"]) > float(opening["endAngle"]),
		"the head of the arc travels from up-front to down-front, so it reads as a blade passing"
	)
	h.assert_true(
		float(closing["alpha"]) < float(opening["alpha"]), "fading as it goes"
	)
	h.assert_true(
		float(closing["width"]) < float(opening["width"]), "and thinning"
	)
	var mirrored := PlatformerImpact.swing_arc(0.0, 0.0, -1, 60.0, 10.0)
	h.assert_true(
		not is_equal_approx(float(mirrored["endAngle"]), float(opening["endAngle"])),
		"a swing to the left is mirrored about the vertical rather than drawn the same way"
	)


## The whole reason none of this is a random draw: two replays of one run throw
## the same sparks, and a fixed-frame capture is the same picture twice.
func _it_replays(h: TestHarness) -> void:
	h.assert_eq(
		PlatformerImpact.rays(1234, 10.0, 20.0, 1, false, 40.0),
		PlatformerImpact.rays(1234, 10.0, 20.0, 1, false, 40.0),
		"the same blow throws the same fan every time it is drawn"
	)
	h.assert_eq(
		PlatformerImpact.shards(1234, 10.0, 20.0, false, true, 40.0),
		PlatformerImpact.shards(1234, 10.0, 20.0, false, true, 40.0),
		"and the same burst"
	)
	var apart := false
	var mine := PlatformerImpact.rays(1234, 10.0, 20.0, 1, false, 40.0)
	var theirs := PlatformerImpact.rays(1235, 10.0, 20.0, 1, false, 40.0)
	for index in range(mine.size()):
		if not is_equal_approx(
			float((mine[index] as Dictionary)["x2"]), float((theirs[index] as Dictionary)["x2"])
		):
			apart = true
	h.assert_true(apart, "while two blows do not, so a flurry is not one spark drawn five times")


func _longest(rays: Array, x: float, y: float) -> float:
	var longest := 0.0
	for entry: Variant in rays:
		var ray: Dictionary = entry
		var dx := float(ray["x2"]) - x
		var dy := float(ray["y2"]) - y
		longest = maxf(longest, sqrt(dx * dx + dy * dy))
	return longest


func _mean_x(rays: Array) -> float:
	var total := 0.0
	for entry: Variant in rays:
		total += float((entry as Dictionary)["x2"])
	return total / float(maxi(1, rays.size()))


func _mean_y(shards: Array) -> float:
	var total := 0.0
	for entry: Variant in shards:
		total += float((entry as Dictionary)["y"])
	return total / float(maxi(1, shards.size()))
