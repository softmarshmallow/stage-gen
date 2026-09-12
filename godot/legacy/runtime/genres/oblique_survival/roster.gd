class_name SurvivalRoster
extends RefCounted

## The genre's systems, in registration order, for the kernel to seal.
##
## Registration order is the order the browser viewer declared them in
## (`viewer/index.html:1037-1600`), because that is what its own Kahn sort broke
## ties with, and the order this host has been running since the port is that
## sort's result. Keeping the registration order lets the sealed order be
## compared against the pasted one line for line — which is the whole point of
## sealing a roster that already worked: if the declarations are right the
## derived order is the order the game has always run in, and if they are wrong
## the diff says so before a frame is drawn.
##
## The order the host ran before the kernel lives on as
## `SurvivalSim.PASTED_ORDER`, and `tests/test_survival_roster.gd` proves both
## orders respect every declared edge — which is why the goldens agree under
## either.

## The systems, named by class rather than by path.
##
## A genre references what it composes by `class_name`, never by `res://`: a
## simulation that can load a script can load anything, and the boundary test
## refuses the whole family of ways that goes wrong.
## Not a `const`: a global class is not a constant expression, so the list is
## built when it is asked for.
static func system_classes() -> Array:
	return [
		SurvivalPlayerMoveSystem,
		SurvivalCollideSystem,
		SurvivalInteractSystem,
		SurvivalDropsSystem,
		SurvivalSelectSystem,
		SurvivalUseSystem,
		SurvivalCraftSystem,
		SurvivalTimersSystem,
		SurvivalMobAiSystem,
		SurvivalVitalsSystem,
		SurvivalPlayerAnimSystem,
		SurvivalDayCycleSystem,
		SurvivalSeasonSystem,
		SurvivalWeatherSystem,
		SurvivalFirelightSystem,
	]


## The roster as scripts, in registration order.
static func scripts() -> Array:
	return system_classes()


## Seal the roster. Returns a `KernelSealed` or a `KernelRefusal`.
##
## This genre carries no frame queue yet: its systems append to `world.events`,
## which the view drains, and moving that to the kernel's queue is its own
## change with its own parity re-pin. So the roster declares no events and the
## sealer is told there is no queue.
static func seal() -> Variant:
	return KernelSealer.seal(scripts(), false)
