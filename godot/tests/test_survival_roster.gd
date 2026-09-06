## The sealed order is pinned, and the order the host ran before it is proved
## equivalent.
##
## `SurvivalSim.PASTED_ORDER` was copied in when the host was ported: the result
## of the browser viewer's own layered sort, because there was no sealer here to
## derive one. The kernel's sealer emits the first ready system and re-scans
## instead, so it produces a different — and equally valid — topological order of
## the same fifteen declarations.
##
## That difference is the interesting part. Two valid orders of a declared
## dataflow must give the same world; if they do not, something is coupled
## without saying so. All three replay goldens come out byte-identical under
## either order (`tools/parity.gd` over `tests/fixtures/oblique_survival/replay`),
## which is what says the declarations are complete. The derived order is what
## runs now, and it is pinned here so a declaration edit that reorders the frame
## is a visible diff.
##
## Nothing here reads a run: the declarations and the sealer are all it needs.

## The order the kernel derives from the fifteen declarations.
const SEALED_ORDER: Array[String] = [
	"player_move",
	"collide",
	"select",
	"mob_ai",
	"day_cycle",
	"interact",
	"drops",
	"use",
	"craft",
	"season",
	"timers",
	"vitals",
	"player_anim",
	"weather",
	"firelight",
]


func run(h: TestHarness) -> void:
	_the_roster_seals(h)
	_the_sealed_order_is_pinned(h)
	_the_simulation_runs_the_sealed_order(h)
	_the_pasted_order_is_also_valid(h)
	_every_system_declares_an_id_and_a_contract(h)


func _the_roster_seals(h: TestHarness) -> void:
	var sealed: Variant = SurvivalRoster.seal()
	if KernelRefusal.is_refusal(sealed):
		h.fail("the roster was refused: %s" % (sealed as KernelRefusal).line())
		return
	h.assert_true(sealed is KernelSealed, "the roster seals")


func _the_sealed_order_is_pinned(h: TestHarness) -> void:
	var sealed: Variant = SurvivalRoster.seal()
	if not (sealed is KernelSealed):
		return
	var derived: Array[String] = []
	for full in (sealed as KernelSealed).order:
		derived.append(String(full).trim_prefix("survival/"))
	h.assert_eq(derived, SEALED_ORDER, "the derived order is the pinned one")


func _the_simulation_runs_the_sealed_order(h: TestHarness) -> void:
	# One authority: the loop asks the roster rather than carrying its own list.
	h.assert_eq(SurvivalSim.present_systems(), SEALED_ORDER, "the loop runs the sealed order")


func _the_pasted_order_is_also_valid(h: TestHarness) -> void:
	# Both orders respect every declared edge, which is why the goldens agree
	# under either. If a declaration were missing, one of these would fail here
	# rather than in a replay a week later.
	h.assert_true(_respects_declarations(SEALED_ORDER), "the sealed order respects every edge")
	h.assert_true(
		_respects_declarations(SurvivalSim.PASTED_ORDER),
		"the order the host ran before the kernel respects every edge too",
	)


## True when every slice a system reads was written by a system earlier in
## `order`, or by nobody at all (a feedback read, undeclared by rule).
func _respects_declarations(order: Array) -> bool:
	var written: Dictionary = {}
	var declarations: Dictionary = {}
	for script: Variant in SurvivalRoster.scripts():
		var system := (script as GDScript).call("declaration") as KernelSystem
		declarations[system.id.trim_prefix("survival/")] = system
	for id: Variant in order:
		var system: KernelSystem = declarations[String(id)]
		for slice in system.reads:
			var writers := 0
			for other: Variant in declarations:
				if (declarations[other] as KernelSystem).writes.has(slice):
					writers += 1
			if writers > 0 and not written.has(slice):
				return false
		for slice in system.writes:
			written[slice] = true
	return true


func _every_system_declares_an_id_and_a_contract(h: TestHarness) -> void:
	# A declaration with no contract version is a system whose world contract
	# cannot be bumped, which is the thing the version is for.
	for script: Variant in SurvivalRoster.scripts():
		var system := (script as GDScript).call("declaration") as KernelSystem
		h.assert_true(system.id.begins_with("survival/"), "a system id carries its genre")
		h.assert_true(
			system.contract_version.ends_with("-v1"), "a system declares its contract version"
		)
