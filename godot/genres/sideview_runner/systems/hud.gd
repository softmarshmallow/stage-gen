class_name RunnerHudSystem
extends RefCounted

## The readout: distance, score, vitals, and the boss's bar.
##
## A view, like the parallax. It reads five slices and writes none; an interface
## control that wants to *act* writes through the input latch like a key rather
## than touching a slice, which is what keeps a button and a keypress the same
## thing to the simulation.

static var view: Object = null


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/hud",
		"contract_version": "hud-system-v4",
		"reads": ["run", "avatar", "camera", "vitals", "encounter"],
		"after": ["runner/parallax"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	if view != null:
		view.call("sync", world)
