class_name RunnerDustSystem
extends RefCounted

## The dust a stride, a slide, a take-off and a landing throw.
##
## The one system on the **frame** clock rather than the simulation's, and
## deliberately: a cut-in stops the world, but dust already in the air keeps
## settling, because it is a picture of something that already happened. Every
## other system in this genre reads `clock.simulationNow`; this one reads
## `step.now`, and that asymmetry is load-bearing.
##
## The puffs are seeded from the run's seed and the frame number, so two runs of
## one seed throw the same dust and a picture comparison means something.

static var view: Object = null


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/dust",
		"contract_version": "dust-system-v2",
		"reads": ["avatar", "run", "camera", "difficulty"],
		"consumes": ["jumped", "landed", "slid"],
		"after": ["runner/parallax", "runner/audio"],
	})


static func update(world: RunnerWorld, step: Dictionary) -> void:
	if view != null:
		view.call("sync", world, step)


static func reset(_world: RunnerWorld, _scope: String) -> void:
	if view != null and view.has_method("clear_puffs"):
		view.call("clear_puffs")
