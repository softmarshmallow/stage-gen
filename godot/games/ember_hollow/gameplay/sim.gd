class_name SurvivalSim
extends RefCounted

## The fifteen systems and the fixed-step loop around them.
##
## The order is **derived, not written**: `SurvivalRoster.seal()` runs the
## kernel's sealer over the fifteen declarations and returns the order, and
## `tests/test_survival_roster.gd` pins it so a declaration edit that reorders
## the frame is a visible diff rather than a behaviour change nobody sees until
## a replay drifts.
##
## Until the kernel landed this list was pasted in: the result of the browser
## viewer's own sort (`viewer/index.html:354-386`), copied because there was
## nothing here to derive it. That sort emitted a whole layer of ready systems
## per round; the kernel emits the first ready system and re-scans. Both are
## valid topological orders of the same declarations, and they differ — which
## is exactly the case where an undeclared coupling would show. It does not:
## all three replay goldens come out byte-identical under either order, which
## is what says the fifteen declarations are complete.

const FIXED_STEP := 1.0 / 60.0
const MAX_SUBSTEPS := 5
## The viewer clamps a frame delta before it reaches the loop (index.html:5447).
const MAX_FRAME_DELTA := 0.25

## The order the browser viewer's layered sort produced, kept as history: it is
## what this host ran from the port until the kernel derived one, and the
## roster test records that the two agree on every golden.
const PASTED_ORDER: Array[String] = [
	"player_move",
	"collide",
	"select",
	"mob_ai",
	"day_cycle",
	"season",
	"weather",
	"interact",
	"drops",
	"use",
	"craft",
	"timers",
	"vitals",
	"player_anim",
	"firelight",
]

## One-shot inputs: a press lives for exactly one simulation step. Not
## consumed, not kept (index.html:5507-5515).
const ONE_SHOT_INPUT := {
	"light": false,
	"craft_toggle": false,
	"menu_move": 0,
	"menu_confirm": false,
	"use": false,
	"drop": false,
	"select": null,
	"cycle": 0,
	# The pointer's three (not the viewer's, which had no mouse): a recipe row
	# clicked, a thing in the world clicked, a spot on the ground clicked.
	"menu_select": null,
	"click_entity": null,
	"click_point": null,
	# The equipment's two: the chosen slot worn, a worn kind taken off.
	"equip": false,
	"unequip": null,
	# Placing a built thing: set it down where the silhouette stands, or let
	# it go and keep the makings.
	"place_click": false,
	"place_cancel": false,
}

## The sealed roster, resolved once. The step walks it rather than re-sealing
## fifteen declarations sixty times a second.
static var _sealed: KernelSealed = null
static var _resolved_done: bool = false

## Sum microseconds per system id. Off by default; the frame owner's `profile`
## flag turns it on and the smoke run is what asks for that.
##
## A simulation may not read the wall clock — that is the whole basis of a
## replay — so the timing comes from a probe the host passes in, and the host is
## where `Time` is allowed to live.
static var profile: bool = false:
	set(value):
		profile = value
		if _sealed != null:
			_sealed.probe = _probe if value else Callable()

## The host's stopwatch, set with `profile`. Microseconds, monotonic.
static var _probe: Callable = Callable()

## system id -> microseconds spent in `update` since `reset_profile`.
static var system_micros: Dictionary:
	get:
		return _sealed.system_micros if _sealed != null else {}

## Hand the roster a way to time a system. The frame owner calls this once.
static func set_probe(probe: Callable) -> void:
	_probe = probe
	if _sealed != null and profile:
		_sealed.probe = probe

static func reset_profile() -> void:
	if _sealed != null:
		_sealed.system_micros.clear()

## One simulation step. The host writes `world.input` before calling.
static func step(world: SurvivalWorld, dt: float) -> void:
	if not _resolved_done:
		_resolve()
	if _sealed != null:
		_sealed.tick(world, dt)
	clear_one_shots(world)

## Resolve the system scripts once. A system that is not in the project is
## warned about here and then simply absent from the walk.
## Resolve the order once, from the sealer. A refusal is fatal rather than
## skipped: a roster the kernel will not order is a frame nobody can define,
## and running fourteen of fifteen systems would be a different game played
## quietly.
static func _resolve() -> void:
	_resolved_done = true
	var sealed: Variant = SurvivalRoster.seal()
	if not (sealed is KernelSealed):
		push_error("sim: the roster was refused: %s" % (sealed as KernelRefusal).line())
		_sealed = null
		return
	_sealed = sealed as KernelSealed
	if profile:
		_sealed.probe = _probe

## Advance the world by a span of simulated time, the way the viewer's
## `window.__survival.advance` does: whole fixed steps, at least one.
static func advance(world: SurvivalWorld, seconds: float) -> void:
	var steps := maxi(1, int(round(seconds / FIXED_STEP)))
	for _i in steps:
		step(world, FIXED_STEP)

## The frame loop's accumulator: at most `MAX_SUBSTEPS` steps, and on hitting
## the cap the accumulator is zeroed, so a stall drops time instead of
## spiralling. Returns how many steps ran.
static func tick(world: SurvivalWorld, delta: float) -> int:
	world.accumulator += minf(delta, MAX_FRAME_DELTA)
	var steps := 0
	while world.accumulator >= FIXED_STEP and steps < MAX_SUBSTEPS:
		step(world, FIXED_STEP)
		world.accumulator -= FIXED_STEP
		steps += 1
	if steps == MAX_SUBSTEPS:
		world.accumulator = 0.0
	return steps

static func clear_one_shots(world: SurvivalWorld) -> void:
	for key: String in ONE_SHOT_INPUT:
		world.input[key] = ONE_SHOT_INPUT[key]

## Which system ids the project actually ships, in execution order.
static func present_systems() -> Array[String]:
	if not _resolved_done:
		_resolve()
	var found: Array[String] = []
	if _sealed == null:
		return found
	for full in _sealed.order:
		found.append(String(full).trim_prefix("survival/"))
	return found


## The execution order, derived. One place asks the roster; everything else
## asks here.
static func system_order() -> Array[String]:
	return present_systems()
