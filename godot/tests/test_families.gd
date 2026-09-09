extends RefCounted

## The families the two side-view genres share, checked against the numbers the
## browser produced for the same inputs.
##
## Every expected value in here was computed by running the browser's own
## function — not by reading the port and writing down what it does. That is the
## point: a port checked against itself proves only that it is self-consistent.

## WCAG 2.1's own threshold for body text, written here rather than read from
## the port, so the two have to agree.
const BODY_TEXT_RATIO := 4.5

func run(h: TestHarness) -> void:
	_hash(h)
	_gauge(h)
	_noise(h)
	_cut_in(h)
	_transition(h)
	_traversal(h)
	_score(h)
	_vitals(h)
	_intent(h)
	_block_gate(h)
	_swaps(h)
	_contrast(h)
	h.done()


## `FamilyContrast`, against `web/lib/families/ui/contrast.ts` run on the same
## inputs. It decides what colour a word is drawn in on generated art, and it
## had no headless check at all: the picture sheets catch a wrong answer, and
## the picture sheets need a window, so nothing in the gate could see it.
func _contrast(h: TestHarness) -> void:
	h.assert_near(FamilyContrast.relative_luminance(255.0, 255.0, 255.0), 1.0, 1e-12,
		"white is luminance 1")
	h.assert_near(FamilyContrast.relative_luminance(0.0, 0.0, 0.0), 0.0, 1e-12,
		"black is luminance 0")
	h.assert_near(FamilyContrast.relative_luminance(128.0, 128.0, 128.0), 0.21586050011389923,
		1e-12, "mid grey matches the browser")
	# The weights are the point of using WCAG rather than a channel average, and
	# each one is a whole channel at full value.
	h.assert_near(FamilyContrast.relative_luminance(255.0, 0.0, 0.0), 0.2126, 1e-12, "red's weight")
	h.assert_near(FamilyContrast.relative_luminance(0.0, 255.0, 0.0), 0.7152, 1e-12,
		"green's weight")
	h.assert_near(FamilyContrast.relative_luminance(0.0, 0.0, 255.0), 0.0722, 1e-12,
		"blue's weight")

	h.assert_near(FamilyContrast.contrast_ratio([0, 0, 0], [255, 255, 255]), 21.0, 1e-12,
		"black on white is 21")
	h.assert_near(FamilyContrast.contrast_ratio([120, 90, 40], [120, 90, 40]), 1.0, 1e-12,
		"a colour on itself is 1")
	h.assert_near(FamilyContrast.contrast_ratio([250, 227, 166], [38, 30, 22]),
		12.974100256317438, 1e-9, "ink on the cream plate matches the browser")
	h.assert_near(FamilyContrast.contrast_ratio([250, 227, 166], [255, 255, 255]),
		1.264826517119333, 1e-9, "and white on it is nearly nothing")

	# Preference order, and the first candidate that clears the bar wins — which
	# is not the same rule as "the best one wins", so the case that separates
	# them is the one worth writing: 6.38 clears 4.5 and 12.97 is higher.
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166],
		[[90, 78, 66], [38, 30, 22]]), 0,
		"a legible candidate was passed over for a more legible one")
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166],
		[[255, 255, 255], [120, 112, 110], [38, 30, 22]]), 2,
		"on a cream plate the ink is chosen over the white")
	h.assert_eq(FamilyContrast.most_readable([20, 22, 28],
		[[255, 255, 255], [38, 30, 22]]), 0,
		"on a dark panel the authored white survives")
	# When nothing clears the bar the best of a bad lot is still named: a word
	# has to be drawn in something.
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166],
		[[255, 255, 255], [232, 224, 208]]), 0,
		"the least bad candidate is named rather than refused")
	h.assert_eq(FamilyContrast.most_readable([250, 227, 166], []), -1,
		"no candidates at all is -1")
	h.assert_near(FamilyContrast.BODY_TEXT_RATIO, BODY_TEXT_RATIO, 1e-12,
		"the default bar is WCAG's 4.5 for body text")


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


func _cut_in(h: TestHarness) -> void:
	var ch := FamilyCutIn.choreography(FamilyCutIn.TEAR_REVEAL)
	h.assert_true(FamilyCutIn.choreography("nothing_v1").is_empty(), "an unknown name is refused")
	var mid := FamilyCutIn.frame(500.0, ch)
	h.assert_near(float(mid["bustScale"]), 1.003333333333, 1e-12, "the bust holds at 500 ms")
	h.assert_true(not bool(mid["released"]), "and the world is still held")
	h.assert_true(bool(FamilyCutIn.frame(1600.0, ch)["released"]), "the world is let go at 1600 ms")
	h.assert_true(not bool(FamilyCutIn.frame(1599.0, ch)["finished"]), "and is not over yet")
	h.assert_true(bool(FamilyCutIn.frame(1900.0, ch)["finished"]), "the moment ends at 1900 ms")
	h.assert_true(FamilyCutIn.frame(-1.0, ch).is_empty(), "a negative elapsed time is refused")
	# The plate's own entry and exit are the browser's: it still slides off to
	# the left over the last three hundred milliseconds.
	h.assert_near(
		float(FamilyCutIn.frame(1900.0, ch)["ripX"]), -1.15, 1e-12, "the plate leaves to the left"
	)
	# The scrim is the part that changed. It comes up over a quarter second
	# instead of appearing between two frames...
	h.assert_near(
		float(FamilyCutIn.frame(600.0, ch)["dim"]), 0.0, 1e-12, "the scrim starts from nothing"
	)
	h.assert_near(
		float(FamilyCutIn.frame(860.0, ch)["dim"]), FamilyCutIn.CUT_IN_DIM, 1e-12,
		"and is fully up a quarter second later"
	)
	h.assert_near(
		float(FamilyCutIn.frame(1600.0, ch)["dim"]), FamilyCutIn.CUT_IN_DIM, 1e-12,
		"it is still up when the world is let go"
	)
	# ...and then goes quickly, and well before the plate carrying it has left:
	# an eighth of its strength sixty milliseconds in, and nothing at all while
	# the plate is still barely moving.
	h.assert_near(
		float(FamilyCutIn.frame(1660.0, ch)["dim"]), FamilyCutIn.CUT_IN_DIM * 0.125, 1e-12,
		"sixty milliseconds later it is nearly gone"
	)
	h.assert_near(float(FamilyCutIn.frame(1720.0, ch)["dim"]), 0.0, 1e-12, "and then it is gone")
	h.assert_true(
		float(FamilyCutIn.frame(1720.0, ch)["ripX"]) > -0.1,
		"with the plate it used to travel with still on screen"
	)



## The cover a restart is cut under.
##
## Not a port of anything — the browser cut between runs in the open. It is a
## placeholder for a transition a run will one day publish, so what it is held
## to is the shape of a cover: opaque while the swap happens, gone by the end,
## and nothing at all for a choreography nobody described.
func _transition(h: TestHarness) -> void:
	var ch := FamilyTransition.choreography(FamilyTransition.FADE_BLACK)
	h.assert_true(
		FamilyTransition.choreography("wipe_v1").is_empty(),
		"a choreography this build does not know is refused"
	)
	h.assert_near(float(FamilyTransition.frame(0.0, ch)["cover"]), 1.0, 1e-12, "the cut is covered")
	h.assert_near(
		float(FamilyTransition.frame(90.0, ch)["cover"]), 1.0, 1e-12,
		"and stays covered through the hold"
	)
	# Seven eighths clear by the half-way point of the fade.
	h.assert_near(
		float(FamilyTransition.frame(245.0, ch)["cover"]), 0.125, 1e-12,
		"half way through the fade the run is mostly back"
	)
	h.assert_near(
		float(FamilyTransition.frame(400.0, ch)["cover"]), 0.0, 1e-12, "and then it is gone"
	)
	h.assert_false(bool(FamilyTransition.frame(399.0, ch)["finished"]), "the cut is not over yet")
	h.assert_true(bool(FamilyTransition.frame(400.0, ch)["finished"]), "and is over at 400 ms")
	h.assert_true(FamilyTransition.frame(-1.0, ch).is_empty(), "a negative elapsed time is refused")


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


func _score(h: TestHarness) -> void:
	var state := FamilyScore.create()
	var steps := PackedInt32Array([5, 15, 30])
	var extended := PackedStringArray(["collected"])
	var awards := {"collected": 10, "boss-defeated": 500}
	for _i in 5:
		FamilyScore.apply(state, awards, steps, extended, {"collected": 1}, false, true)
	h.assert_eq(int(state["chain"]), 5, "five pickups make a chain of five")
	h.assert_eq(int(state["multiplier"]), 2, "which is the first rung")
	# The fifth is paid at the multiplier it just earned, not at the one before.
	h.assert_eq(float(state["total"]), 60.0, "and the fifth pays double")
	var broken := FamilyScore.apply(
		state, awards, steps, extended, {"collected": 1}, true, true
	)
	h.assert_eq(int(state["chain"]), 1, "a miss breaks the chain before the frame extends it")
	h.assert_true(bool(broken["broken"]), "and says so")
	h.assert_eq(float(broken["delta"]), 10.0, "so this pickup pays flat")
	FamilyScore.apply(state, awards, steps, extended, {"boss-defeated": 1}, false, true)
	h.assert_eq(int(state["chain"]), 1, "a boss does not extend the chain")
	h.assert_eq(float(state["total"]), 570.0, "and is paid flat")


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


func _intent(h: TestHarness) -> void:
	var neutral := {"jump": false, "duck": false, "thrust": false, "action": false}
	var made: Variant = FamilyIntent.of(
		neutral, PackedStringArray(["jump", "action"]), PackedStringArray(["duck", "thrust"])
	)
	h.assert_true(not KernelRefusal.is_refusal(made), "the runner's shape is well formed")
	var latch: FamilyIntent = made
	latch.request("jump")
	latch.set_level("duck", true)
	var first := latch.sample()
	h.assert_true(bool(first["jump"]), "an edge is reported once")
	h.assert_true(bool(first["duck"]), "a level is reported while it is held")
	var second := latch.sample()
	h.assert_true(not bool(second["jump"]), "and is spent by the sample that reported it")
	h.assert_true(bool(second["duck"]), "while the level stays down")
	# A jump pressed under a cut-in is discarded rather than queued.
	latch.request("jump")
	var frozen := latch.sample_held()
	h.assert_true(not bool(frozen["jump"]), "a held sample reports no edge")
	h.assert_true(not bool(latch.sample()["jump"]), "and spent it all the same")
	var both: Variant = FamilyIntent.of(
		{"jump": false}, PackedStringArray(["jump"]), PackedStringArray(["jump"])
	)
	h.assert_true(KernelRefusal.is_refusal(both), "a key cannot be both an edge and a level")
	var neither: Variant = FamilyIntent.of(
		{"jump": false}, PackedStringArray([]), PackedStringArray([])
	)
	h.assert_true(KernelRefusal.is_refusal(neither), "and cannot be neither")


func _block_gate(h: TestHarness) -> void:
	var blocks := {"gameplay": "runner-gameplay-block-v1", "fx": "fx-block-v1"}
	var ok: Variant = FamilyBlockGate.gate(blocks, "gameplay", "runner-gameplay-block-v1", false)
	h.assert_true(bool((ok as Dictionary)["published"]), "a matching block is published")
	var absent: Variant = FamilyBlockGate.gate(blocks, "layers", "runner-layers-block-v1", false)
	h.assert_true(KernelRefusal.is_refusal(absent), "an absent required block is refused")
	var optional: Variant = FamilyBlockGate.gate(blocks, "score", "score-block-v1", true)
	h.assert_true(not bool((optional as Dictionary)["published"]), "an absent optional block is not")
	# Absence is a choice; a wrong version is a mistake, optional or not.
	var wrong: Variant = FamilyBlockGate.gate(blocks, "fx", "fx-block-v2", true)
	h.assert_true(KernelRefusal.is_refusal(wrong), "an optional block at the wrong version is refused")
	h.assert_true(
		KernelRefusal.is_refusal(FamilyBlockGate.gate([], "gameplay", "x", false)),
		"a missing table is refused"
	)


func _swaps(h: TestHarness) -> void:
	var log: Array = []
	var ledger := FamilySwapLedger.new()
	var swap := {
		"id": "locomotion",
		"apply": func() -> void: log.append("apply"),
		"revert": func() -> void: log.append("revert"),
	}
	h.assert_true(ledger.apply(swap), "the first apply takes")
	h.assert_true(not ledger.apply(swap), "and a second is a no-op rather than a double")
	h.assert_true(ledger.in_force("locomotion"), "the ledger knows what is standing")
	ledger.revert_all()
	h.assert_eq(log.size(), 2, "revert undoes exactly what was applied")
	h.assert_eq(String(log[1]), "revert", "and in the other direction")
	h.assert_true(not ledger.in_force("locomotion"), "and the ledger is clear")
