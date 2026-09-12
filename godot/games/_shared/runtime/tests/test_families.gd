extends RefCounted

## Browser-derived golden values, grouped by the implementation owner.

func run(h: TestHarness) -> void:
	_hash(h)
	_gauge(h)
	_noise(h)
	_traversal(h)
	_vitals(h)
	h.done()

func _hash(h: TestHarness) -> void:
	h.assert_eq(KernelHash.fnv1a32(""), 2166136261, "FNV-1a's offset basis is the empty string")
	h.assert_eq(KernelHash.fnv1a32("stage_start"), 2265586838, "fnv1a32 matches the browser")
	h.assert_eq(KernelHash.fnv1a32("runner/avatar"), 1823181989, "fnv1a32 matches on a system id")
	h.assert_eq(KernelHash.mix32(1, 2), 3753300549, "mix32 matches the browser")


func _gauge(h: TestHarness) -> void:
	var g := KernelGauge.create(3)
	h.assert_eq(float(g["value"]), 3.0, "a fresh gauge is full")
	h.assert_true(KernelGauge.create(0).is_empty(), "a gauge with no ceiling is refused")
	var first := KernelGauge.drain(g, 1.0, 0.0, 900.0)
	h.assert_true(bool(first["connected"]), "the first drain connects")
	h.assert_eq(float(first["after"]), 2.0, "and takes one point")
	h.assert_eq(
		float((first["gauge"] as Dictionary)["refractoryUntilMs"]), 900.0, "and opens the window"
	)
	var during := KernelGauge.drain(first["gauge"], 1.0, 100.0, 900.0)
	h.assert_true(not bool(during["connected"]), "a drain inside the window is absorbed")
	h.assert_eq(float(during["after"]), 2.0, "and costs nothing")
	var after := KernelGauge.drain(first["gauge"], 1.0, 1000.0, 900.0)
	h.assert_eq(float(after["after"]), 1.0, "a drain past the window connects again")
	# The blink counts down from the time remaining, so it ends on the beat the
	# protection does however long the window was.
	h.assert_eq(
		KernelGauge.refractory_blink_alpha(first["gauge"], 862.0, 75.0, 0.35),
		0.35,
		"an even phase draws dim"
	)
	h.assert_eq(
		KernelGauge.refractory_blink_alpha(first["gauge"], 820.0, 75.0, 0.35),
		1.0,
		"an odd phase draws solid"
	)


func _noise(h: TestHarness) -> void:
	h.assert_near(
		FamilyParticles.unit_noise(12345, 0), 0.737330413656, 1e-12, "seeded noise matches"
	)
	h.assert_near(
		FamilyParticles.unit_noise(0xdeadbeef, 16),
		0.617346277926,
		1e-12,
		"seeded noise matches on a high seed"
	)
	h.assert_near(FamilyParticles.ease_out_cubic(0.3), 0.657, 1e-12, "the ease matches")


func _traversal(h: TestHarness) -> void:
	var arc := FamilyJump.jump_arc_from_admission(3.0, 4.0, 6.0, 0.75, 1.15)
	h.assert_near(
		float(arc["initialSpeedPerSecond"]), 15.652173913043, 1e-11, "the arc's speed matches"
	)
	h.assert_near(
		float(arc["gravityPerSecondSquared"]), 32.665406427221, 1e-11, "the arc's gravity matches"
	)
	h.assert_true(
		FamilyJump.jump_arc_from_admission(3.0, 4.0, 0.0, 0.75, 1.15).is_empty(),
		"an arc at no speed is refused rather than flown"
	)
	var grounded := FamilyJump.resolve_jump_request("terrain", 0, 0.0, -1.0, false, 1, 9.0, 9.0)
	h.assert_eq(String(grounded["kind"]), "ground", "a grounded jump is a ground jump")
	var air := FamilyJump.resolve_jump_request("air", 0, 0.0, -1.0, false, 1, 9.0, 9.0)
	h.assert_eq(String(air["kind"]), "air", "the first air jump is spent from the budget")
	h.assert_eq(int(air["airJumpsUsed"]), 1, "and counted")
	var spent := FamilyJump.resolve_jump_request("air", 1, 0.0, -1.0, false, 1, 9.0, 9.0)
	# The second jump's two modes. `impulse` replaces the velocity, so a body still
	# rising loses the rise it had left and the apex depends on when the key went
	# down; `sustained` keeps that rise and adds the same gain on top, so it does
	# not. Both agree on a body already falling, which has no rise to keep.
	h.assert_near(
		FamilyJump.air_jump_speed(9.0, -4.0, 10.0, FamilyJump.AIR_JUMP_IMPULSE),
		9.0,
		1e-9,
		"an impulse jump is worth its own velocity whenever it is pressed"
	)
	h.assert_near(
		FamilyJump.air_jump_speed(9.0, -4.0, 10.0, FamilyJump.AIR_JUMP_SUSTAINED),
		sqrt(97.0),
		1e-9,
		"a sustained one keeps the rise the body still had and adds its own on top"
	)
	h.assert_near(
		FamilyJump.air_jump_speed(9.0, 4.0, 10.0, FamilyJump.AIR_JUMP_SUSTAINED),
		9.0,
		1e-9,
		"and agrees with the impulse on a body already falling, which has no rise left"
	)
	# The property the whole change exists for: press it anywhere on the way up and
	# the apex is the same.
	var gravity := 10.0
	var apexes: PackedFloat64Array = PackedFloat64Array()
	for tenth in range(1, 10):
		var vy := -9.0 * float(tenth) / 10.0
		# Where the body is when it presses, measured as the rise it has already
		# made from the launch, plus everything the second jump then buys.
		var risen := (81.0 - vy * vy) / (2.0 * gravity)
		var speed := FamilyJump.air_jump_speed(9.0, vy, gravity, FamilyJump.AIR_JUMP_SUSTAINED)
		apexes.append(risen + speed * speed / (2.0 * gravity))
	for index in range(1, apexes.size()):
		h.assert_near(
			apexes[index],
			apexes[0],
			1e-9,
			"a sustained second jump reaches one apex however early it is pressed"
		)
	h.assert_eq(String(spent["kind"]), "none", "a budget spent refuses rather than errors")
	# The runner never crouches into a jump, but the platformer does, and the
	# refusal lives here rather than in either genre.
	h.assert_eq(
		String(FamilyJump.resolve_jump_request("terrain", 0, 0.0, -1.0, true, 1, 9.0, 9.0)["kind"]),
		"none",
		"a crouching body cannot jump"
	)

	var step := FamilyContact.resolve_terrain_step(5.0, 5.5, 0.0)
	h.assert_eq(String(step["support"]), "air", "a surface below the foot is air")
	var rise := FamilyContact.resolve_terrain_step(5.0, 4.0, 0.0)
	h.assert_eq(float(rise["footY"]), 4.0, "a rise is absorbed, and the caller judges it")
	var buried := FamilyContact.resolve_vertical_landing(5.0, 6.0, -1.0, 5.5, "crossing")
	h.assert_eq(String(buried["support"]), "buried", "rising into terrain buries the body")
	var clamped := FamilyContact.resolve_vertical_landing(5.0, 6.0, 1.0, 5.5, "clamp")
	h.assert_eq(String(clamped["support"]), "terrain", "the same step under clamp simply lands")
	h.assert_eq(float(clamped["vy"]), 0.0, "and stops it")

	var rows := PackedStringArray(["000", "010", "111"])
	h.assert_eq(FamilySurface.bottom_contiguous_surface_row(rows, 0), 2, "a one-cell floor")
	h.assert_eq(FamilySurface.bottom_contiguous_surface_row(rows, 1), 1, "a two-cell stack")
	h.assert_eq(
		FamilySurface.bottom_contiguous_surface_row(PackedStringArray(["1", "0"]), 0),
		-1,
		"a floating cell is a pit, not a roof to land on"
	)


func _vitals(h: TestHarness) -> void:
	var consequences := {"hazard": "drain_v1", "pit": "end_run_v1", "crush": "drain_v1"}
	var v := FamilyVitals.create(3)
	var nowhere := func(_source: String) -> Dictionary: return {}
	var one := FamilyVitals.resolve(
		v, PackedStringArray(["hazard"]), consequences, 1.0, 900.0, nowhere
	)
	h.assert_eq(one.size(), 1, "one source, one verdict")
	h.assert_eq(String((one[0] as Dictionary)["kind"]), "drained", "a drain drains")
	# Two sources in one frame: the window the first opened absorbs the second.
	var both := FamilyVitals.resolve(
		v, PackedStringArray(["hazard", "crush"]), consequences, 1.0, 900.0, nowhere
	)
	h.assert_eq(String((both[0] as Dictionary)["kind"]), "absorbed", "the window absorbs")
	# An ending source stops the rest being resolved at all.
	var ended := FamilyVitals.resolve(
		FamilyVitals.create(3),
		PackedStringArray(["pit", "hazard"]),
		consequences,
		1.0,
		900.0,
		nowhere
	)
	h.assert_eq(ended.size(), 1, "the first verdict that ends the run is the last verdict")
	h.assert_eq(String((ended[0] as Dictionary)["kind"]), "ended", "and it is the pit")
	# A package with no vitals ends on anything, which is the true reading.
	var bare := FamilyVitals.resolve(
		FamilyVitals.create(0), PackedStringArray(["hazard"]), consequences, 1.0, 900.0, nowhere
	)
	h.assert_eq(String((bare[0] as Dictionary)["kind"]), "ended", "no gauge means no absorbing")
