class_name RunnerParallaxSystem
extends RefCounted

## The bands behind and in front of the world.
##
## A view: it reads slices, hands them to a port, and owns nothing. It is in the
## roster because **the sealed order is derived from every system a genre
## registers** — leaving a view out would derive a different order from the one
## the browser ran, and the parity this system is not part of would then be
## proved against the wrong frame.
##
## `view` is null headless, which is the whole reason a replay needs no engine:
## an absent port draws nothing and the simulation does not notice.

static var view: Object = null


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/parallax",
		"contract_version": "parallax-system-v1",
		"reads": ["camera", "segments", "avatar", "obstacles"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	if view != null:
		view.call("sync", world)
