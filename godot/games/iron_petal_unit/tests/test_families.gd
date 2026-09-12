extends RefCounted

## Browser-derived golden values, grouped by the implementation owner.

func run(h: TestHarness) -> void:
	_cut_in(h)
	_transition(h)
	_score(h)
	_intent(h)
	_block_gate(h)
	_swaps(h)
	h.done()

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
