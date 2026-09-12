class_name FamilyClock
extends RefCounted

## The simulation's own clock, which a moment can stop.
##
## A port of `web/lib/families/clock/clock.ts`. The slice is `{simulationDt,
## simulationNow, held, heldBy}`.
##
## Two clocks exist and every system picks one deliberately. The **frame** clock
## (`step.now`, `step.frame`) counts steps the loop actually ran and never
## stops. The **simulation** clock counts steps the world was allowed to move
## for, and a cut-in freezing the world freezes it. Anything that integrates
## reads the simulation clock; anything that measures the presentation of a
## thing that plays *over* a frozen world reads the frame clock. Getting that
## backwards is invisible until a moment plays, and then the world lurches.
##
## `heldBy` names which holder stopped it, so a world that is stuck reports the
## reason rather than only the fact.


static func create() -> Dictionary:
	return {"simulationDt": 0.0, "simulationNow": 0.0, "held": false, "heldBy": null}


## Advance, unless a holder says not to. `holders` is an array of
## `{name, held: Callable(world, step) -> bool}` in priority order: the first to
## answer yes is the one named.
static func advance(clock: Dictionary, holders: Array, world: Variant, step: Dictionary) -> void:
	var held_by: Variant = null
	for holder: Variant in holders:
		var entry: Dictionary = holder
		var predicate: Callable = entry["held"]
		if bool(predicate.call(world, step)):
			held_by = String(entry["name"])
			break
	clock["held"] = held_by != null
	clock["heldBy"] = held_by
	clock["simulationDt"] = 0.0 if held_by != null else float(step["dt"])
	clock["simulationNow"] = float(clock["simulationNow"]) + float(clock["simulationDt"])


## Forget the hold. The integral survives a run reset and is zeroed only by a
## session reset: a refractory window stamped against it must not be reopened by
## a restart.
static func reset(clock: Dictionary, scope: String) -> void:
	clock["held"] = false
	clock["heldBy"] = null
	clock["simulationDt"] = 0.0
	if scope == FamilySession.SCOPE_SESSION:
		clock["simulationNow"] = 0.0
