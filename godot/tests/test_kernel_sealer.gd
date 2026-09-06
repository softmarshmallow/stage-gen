## The sealer's seven refusals, and the order it derives.
##
## Synthetic worlds only: this tier reads no run and needs no media, so it runs
## in the locked gate on a machine that has never generated anything.

const CASES := "res://tests/kernel/sealer_cases.gd"


func run(h: TestHarness) -> void:
	_derives_a_total_order(h)
	_breaks_ties_by_registration_order(h)
	_refuses_a_duplicate_id(h)
	_refuses_two_owners_of_one_slice(h)
	_refuses_a_write_into_an_owned_slice(h)
	_refuses_an_after_edge_naming_nobody(h)
	_refuses_a_consumed_event_nobody_emits(h)
	_refuses_a_cycle(h)
	_refuses_events_without_a_queue(h)
	_refuses_a_queue_no_system_uses(h)
	_a_deferred_consume_closes_no_cycle(h)


## Build a one-off system script from a declaration, so a case reads as a table.
func _system(fields: Dictionary) -> GDScript:
	var source := "extends RefCounted\n"
	source += "static func declaration() -> KernelSystem:\n"
	source += "\treturn KernelSystem.of(%s)\n" % _literal(fields)
	source += "static func update(_world, _step) -> void:\n\tpass\n"
	var script := GDScript.new()
	script.source_code = source
	script.reload()
	return script


func _literal(fields: Dictionary) -> String:
	return JSON.stringify(fields)


func _order_of(sealed: Variant) -> PackedStringArray:
	return (sealed as KernelSealed).order


func _derives_a_total_order(h: TestHarness) -> void:
	# b reads what a writes, so a runs first whatever order they registered in.
	var b := _system({"id": "x/b", "contract_version": "v1", "reads": ["s"]})
	var a := _system({"id": "x/a", "contract_version": "v1", "writes": ["s"]})
	var sealed: Variant = KernelSealer.seal([b, a])
	if not h.assert_false(KernelRefusal.is_refusal(sealed), "a writes-before-reads roster seals"):
		return
	h.assert_eq(
		_order_of(sealed), PackedStringArray(["x/a", "x/b"]), "the writer is ordered first"
	)


func _breaks_ties_by_registration_order(h: TestHarness) -> void:
	# Nothing orders these two, so the roster's own order stands — which is what
	# makes a sealed order a diff rather than a coin toss.
	var one := _system({"id": "x/one", "contract_version": "v1"})
	var two := _system({"id": "x/two", "contract_version": "v1"})
	var sealed: Variant = KernelSealer.seal([two, one])
	h.assert_eq(
		_order_of(sealed), PackedStringArray(["x/two", "x/one"]), "a tie keeps registration order"
	)


func _refuses_a_duplicate_id(h: TestHarness) -> void:
	var one := _system({"id": "x/same", "contract_version": "v1"})
	var two := _system({"id": "x/same", "contract_version": "v1"})
	var sealed: Variant = KernelSealer.seal([one, two])
	h.assert_true(KernelRefusal.is_refusal(sealed), "two systems under one id are refused")


func _refuses_two_owners_of_one_slice(h: TestHarness) -> void:
	var one := _system({"id": "x/one", "contract_version": "v1", "owns": ["s"]})
	var two := _system({"id": "x/two", "contract_version": "v1", "owns": ["s"]})
	var sealed: Variant = KernelSealer.seal([one, two])
	h.assert_true(KernelRefusal.is_refusal(sealed), "one slice, one author")


func _refuses_a_write_into_an_owned_slice(h: TestHarness) -> void:
	var owner := _system({"id": "x/owner", "contract_version": "v1", "owns": ["s"]})
	var other := _system({"id": "x/other", "contract_version": "v1", "writes": ["s"]})
	var sealed: Variant = KernelSealer.seal([owner, other])
	h.assert_true(KernelRefusal.is_refusal(sealed), "a write into an owned slice is refused")


func _refuses_an_after_edge_naming_nobody(h: TestHarness) -> void:
	var one := _system({"id": "x/one", "contract_version": "v1", "after": ["x/ghost"]})
	var sealed: Variant = KernelSealer.seal([one])
	h.assert_true(KernelRefusal.is_refusal(sealed), "an after edge names a registered system")


func _refuses_a_consumed_event_nobody_emits(h: TestHarness) -> void:
	var one := _system({"id": "x/one", "contract_version": "v1", "consumes": ["y/verb"]})
	var sealed: Variant = KernelSealer.seal([one], true)
	h.assert_true(KernelRefusal.is_refusal(sealed), "a channel with no other end is refused")


func _refuses_a_cycle(h: TestHarness) -> void:
	var one := _system({"id": "x/one", "contract_version": "v1", "reads": ["b"], "writes": ["a"]})
	var two := _system({"id": "x/two", "contract_version": "v1", "reads": ["a"], "writes": ["b"]})
	var sealed: Variant = KernelSealer.seal([one, two])
	h.assert_true(KernelRefusal.is_refusal(sealed), "no order satisfies a cycle")


func _refuses_events_without_a_queue(h: TestHarness) -> void:
	var one := _system({"id": "x/one", "contract_version": "v1", "emits": ["y/verb"]})
	var sealed: Variant = KernelSealer.seal([one], false)
	h.assert_true(KernelRefusal.is_refusal(sealed), "an event channel needs something to clear it")


func _refuses_a_queue_no_system_uses(h: TestHarness) -> void:
	var one := _system({"id": "x/one", "contract_version": "v1"})
	var sealed: Variant = KernelSealer.seal([one], true)
	h.assert_true(KernelRefusal.is_refusal(sealed), "a queue nobody uses is refused")


func _a_deferred_consume_closes_no_cycle(h: TestHarness) -> void:
	# The consumer is sealed before the emitter and still hears it, one frame
	# later. That is the whole point: a declared delay rather than a private
	# shadow of somebody else's state.
	var hears := _system(
		{"id": "x/hears", "contract_version": "v1", "consumes_deferred": ["y/verb"], "writes": ["a"]}
	)
	var says := _system(
		{"id": "x/says", "contract_version": "v1", "reads": ["a"], "emits": ["y/verb"]}
	)
	var sealed: Variant = KernelSealer.seal([hears, says], true)
	if not h.assert_false(KernelRefusal.is_refusal(sealed), "a deferred consume seals"):
		return
	h.assert_eq(
		_order_of(sealed),
		PackedStringArray(["x/hears", "x/says"]),
		"the deferred consumer may be sealed before the emitter",
	)
