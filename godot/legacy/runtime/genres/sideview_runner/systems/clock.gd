class_name RunnerClockSystem
extends RefCounted

## The simulation clock, and the one thing that stops it.
##
## A port of `web/lib/sideview-runner/clock.ts`. The runner declares exactly one
## holder: a cut-in in flight that has not yet released the world.
##
## The read of `fx` is deliberately **not** declared. Declaring it would assert
## that the moment system runs before this one, and the moment system reads the
## clock — that is a cycle, and the sealer would refuse it. So the hold is a
## feedback read: it begins one frame after the moment does. One frame of
## movement under a cut-in is invisible; a roster that will not seal is not.

static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "clock/step",
		"contract_version": "clock-system-v1",
		"owns": ["clock"],
	})


static func update(world: RunnerWorld, step: Dictionary) -> void:
	FamilyClock.advance(world.clock, _holders(), world, step)


static func reset(world: RunnerWorld, scope: String) -> void:
	FamilyClock.reset(world.clock, scope)


static func _holders() -> Array:
	return [{"name": "moment", "held": Callable(RunnerClockSystem, "_moment_holds")}]


static func _moment_holds(world: RunnerWorld, _step: Dictionary) -> bool:
	return not world.fx.is_empty() and not bool(world.fx.get("released", false))
