class_name RunnerAudioSystem
extends RefCounted

## What the run sounds like.
##
## A view over the frame's events. The cue table — which event fires which
## sound, on which channel, at what strength — lives in the host beside the
## sinks that play it; what the roster needs here is the *consume* list, because
## that is what orders this system after everything that speaks.
##
## The two channels matter: a hurt both plays a sound and ducks the music, and
## a death both plays a sound and stops it. One event, two sinks, declared once.

static var view: Object = null


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/audio",
		"contract_version": "audio-system-v5",
		"reads": ["run", "score"],
		"consumes": [
			"jumped",
			"landed",
			"slid",
			"hazard-cleared",
			"collected",
			"drained",
			"run-ended",
		],
		"after": ["session/run", "runner/hud"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	if view != null:
		view.call("sync", world)


static func reset(_world: RunnerWorld, scope: String) -> void:
	if view != null and view.has_method("reset_cues"):
		view.call("reset_cues", scope)
