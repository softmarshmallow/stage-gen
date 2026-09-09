extends RefCounted

## The number that pops off a body: the run's motion, and the digits inside it.
##
## The port shipped the run — a punch, a rise, a fade — and left out the four
## things that make a number read as a struck object rather than as text: the
## knock, the critical's extra reach, the per-digit arrival, and the column two
## blows in one place stack into. This is the proof of those four.


func run(h: TestHarness) -> void:
	_the_run(h)
	_the_knock(h)
	_the_digits(h)
	_the_row(h)
	_the_column(h)
	h.done()


func _the_run(h: TestHarness) -> void:
	h.assert_true(
		FamilyCombatText.sample(-1.0).is_empty(), "a number has no state before it is raised"
	)
	h.assert_true(
		FamilyCombatText.sample(FamilyCombatText.LIFETIME_MS).is_empty(),
		"and none once it is over, which is how the view knows to retire it"
	)
	var born := FamilyCombatText.sample(0.0)
	h.assert_eq(float(born["alpha"]), 1.0, "it opens opaque")
	h.assert_near(
		float(born["scale"]), FamilyCombatText.SCALE_FROM, 1e-9, "and undersized, so it punches up"
	)
	h.assert_true(
		float(FamilyCombatText.sample(FamilyCombatText.PUNCH_PEAK_MS)["scale"])
			> float(born["scale"]),
		"the punch peaks above where it started"
	)
	h.assert_near(
		float(FamilyCombatText.sample(FamilyCombatText.PUNCH_SETTLE_MS)["scale"]),
		FamilyCombatText.SCALE_REST,
		1e-9,
		"and settles back to rest"
	)
	var late := FamilyCombatText.sample(FamilyCombatText.LIFETIME_MS - 1.0)
	h.assert_true(float(late["alpha"]) < 0.05, "it is all but gone on its last frame")
	h.assert_true(
		float(late["riseY"]) < float(born["riseY"]),
		"having climbed the whole way (y grows downward)"
	)

	# The emphasis a critical carries, which the port had dropped.
	var ordinary := FamilyCombatText.sample(240.0, 1, false)
	var big := FamilyCombatText.sample(240.0, 1, true)
	h.assert_true(
		float(big["riseY"]) < float(ordinary["riseY"]),
		"a critical climbs further than an ordinary blow, not merely bigger"
	)
	h.assert_near(
		float(big["riseY"]),
		float(ordinary["riseY"]) * FamilyCombatText.CRITICAL_SCALE,
		1e-9,
		"by exactly the emphasis the size is scaled by"
	)


func _the_knock(h: TestHarness) -> void:
	h.assert_eq(
		FamilyCombatText.shake_x(7, FamilyCombatText.SHAKE_MS),
		0.0,
		"the knock is over when its window closes"
	)
	h.assert_eq(FamilyCombatText.shake_x(7, -1.0), 0.0, "and has not started before the blow")
	var largest := 0.0
	var moved := false
	for step in range(0, int(FamilyCombatText.SHAKE_MS)):
		var offset := FamilyCombatText.shake_x(7, float(step))
		largest = maxf(largest, absf(offset))
		if not is_zero_approx(offset):
			moved = true
	h.assert_true(moved, "inside it the number is knocked sideways")
	h.assert_true(
		largest <= FamilyCombatText.SHAKE_PX,
		"never further than the two pixels it is bounded by (%f)" % largest
	)
	h.assert_true(
		absf(FamilyCombatText.shake_x(7, 6.0)) >= absf(FamilyCombatText.shake_x(7, 66.0)),
		"and it decays rather than ringing on"
	)
	var apart := false
	for step in range(0, int(FamilyCombatText.SHAKE_MS)):
		if not is_equal_approx(
			FamilyCombatText.shake_x(1, float(step)), FamilyCombatText.shake_x(2, float(step))
		):
			apart = true
	h.assert_true(apart, "two blows read different phases, so a flurry does not shake in unison")
	h.assert_eq(
		FamilyCombatText.shake_x(7, 30.0),
		FamilyCombatText.shake_x(7, 30.0),
		"and the same blow shakes the same way every time it is drawn"
	)


func _the_digits(h: TestHarness) -> void:
	var size := 64.0
	h.assert_true(
		FamilyCombatText.glyph_sample(1, 0, 0, 0.0, size, 0.0).is_empty(),
		"a run of no digits has no digits to sample"
	)
	h.assert_true(
		FamilyCombatText.glyph_sample(1, 3, 3, 0.0, size, 0.0).is_empty(),
		"and an index outside its own run is refused rather than guessed at"
	)

	# The stagger: each digit waits its turn.
	var second_at_zero := FamilyCombatText.glyph_sample(1, 1, 3, 0.0, size, 0.0)
	h.assert_eq(
		float(second_at_zero["alpha"]),
		0.0,
		"the second digit is not there on the frame the first arrives"
	)
	h.assert_eq(
		float(FamilyCombatText.glyph_sample(1, 0, 3, 0.0, size, 0.0)["alpha"]),
		1.0,
		"the first is"
	)
	h.assert_eq(
		float(
			FamilyCombatText.glyph_sample(
				1, 1, 3, 0.0, size, FamilyCombatText.GLYPH_STAGGER_MS
			)["alpha"]
		),
		1.0,
		"and the second arrives exactly one beat later"
	)

	# The arrival: oversized and high, falling into place.
	var arriving := FamilyCombatText.glyph_sample(1, 0, 3, 0.0, size, 0.0)
	var settled := FamilyCombatText.glyph_sample(
		1, 0, 3, 0.0, size, FamilyCombatText.GLYPH_SETTLE_MS
	)
	h.assert_true(
		float(arriving["scale"]) > float(settled["scale"]),
		"a digit arrives bigger than it rests, so it reads as thrown rather than typed"
	)
	h.assert_true(
		float(arriving["offsetY"]) < float(settled["offsetY"]),
		"and higher, falling into its place while it settles"
	)

	# The arc: the middle of a row sits highest.
	var left := float(FamilyCombatText.glyph_sample(1, 0, 5, 0.0, size, 1000.0)["offsetY"])
	var middle := float(FamilyCombatText.glyph_sample(1, 2, 5, 0.0, size, 1000.0)["offsetY"])
	var right := float(FamilyCombatText.glyph_sample(1, 4, 5, 0.0, size, 1000.0)["offsetY"])
	h.assert_true(
		middle < left and middle < right,
		"the digits of a settled number rest on a shallow arc rather than a ruled line"
	)

	# The displacement is a share of the size, so a big number moves further.
	var small := FamilyCombatText.glyph_sample(1, 0, 3, 0.0, 32.0, 0.0)
	var large := FamilyCombatText.glyph_sample(1, 0, 3, 0.0, 128.0, 0.0)
	h.assert_true(
		absf(float(large["offsetY"])) > absf(float(small["offsetY"])) * 3.0,
		"a number set four times larger drops four times as far, rather than sitting still"
	)

	# And it is a hash, not a draw.
	h.assert_eq(
		FamilyCombatText.glyph_sample(9, 1, 3, 0.0, size, 40.0),
		FamilyCombatText.glyph_sample(9, 1, 3, 0.0, size, 40.0),
		"the same digit of the same blow is displaced the same way every time"
	)
	var differs := false
	for index in range(3):
		if not is_equal_approx(
			float(FamilyCombatText.glyph_sample(9, index, 3, 0.0, size, 1000.0)["offsetY"]),
			float(FamilyCombatText.glyph_sample(10, index, 3, 0.0, size, 1000.0)["offsetY"])
		):
			differs = true
	h.assert_true(differs, "and two blows do not land their digits identically")


func _the_row(h: TestHarness) -> void:
	h.assert_true(
		FamilyCombatText.glyph_layout(PackedFloat64Array([]), 4.0).is_empty(),
		"an empty number lays no glyphs out"
	)
	var one := FamilyCombatText.glyph_layout(PackedFloat64Array([40.0]), 4.0)
	h.assert_near(one[0], 0.0, 1e-9, "a single digit sits on the centre")
	var three := FamilyCombatText.glyph_layout(PackedFloat64Array([40.0, 40.0, 40.0]), 4.0)
	h.assert_near(
		three[0] + three[2], 0.0, 1e-9, "and a row is centred, so a number never drifts sideways"
	)
	h.assert_near(three[1], 0.0, 1e-9, "with its middle digit on the centre")
	h.assert_near(
		three[1] - three[0], 44.0, 1e-9, "each digit an advance and a tracking step from the last"
	)
	h.assert_true(
		FamilyCombatText.nominal_glyph_advance(64.0, "!")
			< FamilyCombatText.nominal_glyph_advance(64.0, "7"),
		"the critical's bang is laid out narrower than a digit, because it is narrower"
	)


func _the_column(h: TestHarness) -> void:
	var size := 64.0
	var alone := FamilyCombatText.stack_offset([], 1, 100.0, 200.0, 500.0, size)
	h.assert_eq(float(alone["y"]), 0.0, "the first number in a place is not lifted")
	h.assert_eq(float(alone["x"]), 0.0, "nor nudged")

	var peer := [{"x": 100.0, "y": 200.0, "startedMs": 500.0}]
	var second := FamilyCombatText.stack_offset(peer, 1, 100.0, 200.0, 520.0, size)
	h.assert_true(
		float(second["y"]) < 0.0,
		"a second number in the same place goes above the first rather than through it"
	)
	h.assert_near(
		float(second["y"]),
		-size * FamilyCombatText.STACK_STEP_SHARE,
		1e-9,
		"by just under a full line, so a burst reads as one flurry"
	)
	h.assert_eq(
		float(
			FamilyCombatText.stack_offset(
				peer, 1, 100.0, 200.0, 500.0 + FamilyCombatText.STACK_WINDOW_MS + 1.0, size
			)["y"]
		),
		0.0,
		"a number that has been up too long is no longer stacked against"
	)
	h.assert_eq(
		float(
			FamilyCombatText.stack_offset(
				peer, 1, 100.0 + FamilyCombatText.STACK_RADIUS_PX + 1.0, 200.0, 520.0, size
			)["y"]
		),
		0.0,
		"and neither is one across the map, which is a different fight"
	)
	var third := FamilyCombatText.stack_offset(
		[
			{"x": 100.0, "y": 200.0, "startedMs": 500.0},
			{"x": 100.0, "y": 200.0, "startedMs": 510.0},
		],
		1,
		100.0,
		200.0,
		520.0,
		size
	)
	h.assert_near(
		float(third["y"]),
		-size * FamilyCombatText.STACK_STEP_SHARE * 2.0,
		1e-9,
		"the column steps once per number already standing in it"
	)
