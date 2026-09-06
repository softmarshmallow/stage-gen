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

const SYSTEM_FILES := [
	"res://genres/oblique_survival/systems/player_move.gd",
	"res://genres/oblique_survival/systems/collide.gd",
	"res://genres/oblique_survival/systems/interact.gd",
	"res://genres/oblique_survival/systems/drops.gd",
	"res://genres/oblique_survival/systems/select.gd",
	"res://genres/oblique_survival/systems/use.gd",
	"res://genres/oblique_survival/systems/craft.gd",
	"res://genres/oblique_survival/systems/timers.gd",
	"res://genres/oblique_survival/systems/mob_ai.gd",
	"res://genres/oblique_survival/systems/vitals.gd",
	"res://genres/oblique_survival/systems/player_anim.gd",
	"res://genres/oblique_survival/systems/day_cycle.gd",
	"res://genres/oblique_survival/systems/season.gd",
	"res://genres/oblique_survival/systems/weather.gd",
	"res://genres/oblique_survival/systems/firelight.gd",
]


## The roster as scripts, in registration order.
static func scripts() -> Array:
	var found: Array = []
	for path in SYSTEM_FILES:
		if not ResourceLoader.exists(path):
			push_error("survival roster: %s is not in the project" % path)
			continue
		found.append(load(path))
	return found


## Seal the roster. Returns a `KernelSealed` or a `KernelRefusal`.
##
## This genre carries no frame queue yet: its systems append to `world.events`,
## which the view drains, and moving that to the kernel's queue is its own
## change with its own parity re-pin. So the roster declares no events and the
## sealer is told there is no queue.
static func seal() -> Variant:
	return KernelSealer.seal(scripts(), false)
