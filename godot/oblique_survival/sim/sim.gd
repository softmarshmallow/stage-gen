class_name Sim
extends RefCounted

## The fifteen systems, in the order the viewer's `orderSystems` resolves them
## (a Kahn sort over writes-before-reads; re-running it on the viewer's exact
## tags gives this sequence), and the fixed-step loop around them.
##
## Systems are looked up by script path rather than by class so a partly built
## project still runs: a system that is not present yet is skipped, once with a
## warning.

const FIXED_STEP := 1.0 / 60.0
const MAX_SUBSTEPS := 5
## The viewer clamps a frame delta before it reaches the loop (index.html:5447).
const MAX_FRAME_DELTA := 0.25

const SYSTEM_IDS: Array[String] = [
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
}

static var _scripts: Dictionary = {}
static var _warned: Dictionary = {}
## The systems that are actually in the project, resolved once, in order. The
## step walks this rather than re-resolving fifteen script paths sixty times a
## second.
static var _resolved: Array = []
static var _resolved_done: bool = false

## Sum microseconds per system id in `system_micros`. Off by default; the frame
## owner's `profile` flag is what turns it on, and the smoke run is what asks
## for that. A `Time.get_ticks_usec()` pair around every system is cheap but not
## free, so the step is written twice rather than branching per system.
static var profile: bool = false
## system id -> microseconds spent in `update` since `reset_profile`.
static var system_micros: Dictionary = {}

static func reset_profile() -> void:
	system_micros.clear()

## One simulation step. The host writes `world.input` before calling.
static func step(world: World, dt: float) -> void:
	if not _resolved_done:
		_resolve()
	if not profile:
		for entry: Array in _resolved:
			(entry[1] as GDScript).update(world, dt)
	else:
		for entry: Array in _resolved:
			var id: String = entry[0]
			var started := Time.get_ticks_usec()
			(entry[1] as GDScript).update(world, dt)
			system_micros[id] = int(system_micros.get(id, 0)) + (Time.get_ticks_usec() - started)
	clear_one_shots(world)

## Resolve the system scripts once. A system that is not in the project is
## warned about here and then simply absent from the walk.
static func _resolve() -> void:
	var found: Array = []
	for id in SYSTEM_IDS:
		var script := system_script(id)
		if script == null:
			if not _warned.has(id):
				_warned[id] = true
				push_warning("sim: system '%s' is not present; skipping it" % id)
			continue
		found.append([id, script])
	_resolved = found
	_resolved_done = true

## Advance the world by a span of simulated time, the way the viewer's
## `window.__survival.advance` does: whole fixed steps, at least one.
static func advance(world: World, seconds: float) -> void:
	var steps := maxi(1, int(round(seconds / FIXED_STEP)))
	for _i in steps:
		step(world, FIXED_STEP)

## The frame loop's accumulator: at most `MAX_SUBSTEPS` steps, and on hitting
## the cap the accumulator is zeroed, so a stall drops time instead of
## spiralling. Returns how many steps ran.
static func tick(world: World, delta: float) -> int:
	world.accumulator += minf(delta, MAX_FRAME_DELTA)
	var steps := 0
	while world.accumulator >= FIXED_STEP and steps < MAX_SUBSTEPS:
		step(world, FIXED_STEP)
		world.accumulator -= FIXED_STEP
		steps += 1
	if steps == MAX_SUBSTEPS:
		world.accumulator = 0.0
	return steps

static func clear_one_shots(world: World) -> void:
	for key: String in ONE_SHOT_INPUT:
		world.input[key] = ONE_SHOT_INPUT[key]

## The script implementing a system id, or null when it is not in the project.
static func system_script(id: String) -> GDScript:
	if _scripts.has(id):
		return _scripts[id]
	var path := "res://sim/systems/%s.gd" % id
	var script: GDScript = null
	if ResourceLoader.exists(path):
		script = load(path)
	# A script that failed to parse still loads, as an empty one; treat it as
	# absent rather than erroring once per step for the rest of the run.
	if script != null and not script.has_method("update"):
		push_error("sim: system '%s' has no static update(world, dt)" % id)
		script = null
	_scripts[id] = script
	return script

## Which system ids the project actually ships, in execution order.
static func present_systems() -> Array[String]:
	var found: Array[String] = []
	for id in SYSTEM_IDS:
		if system_script(id) != null:
			found.append(id)
	return found
