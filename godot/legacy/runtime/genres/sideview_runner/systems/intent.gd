class_name RunnerIntentSystem
extends RefCounted

## The player's ask, sampled once per step.
##
## A port of `web/lib/sideview-runner/intent.ts`. The latch is the host's — a
## keyboard, a pointer, a scripted replay and a bot are one source with
## different producers — and this system is only the point at which it is read.
##
## While the clock is held the sample is the *held* one: levels are reported and
## edges are spent unasked, so a jump pressed under a cut-in is discarded rather
## than queued up to fire the instant the picture clears.

static var latch: FamilyIntent = null


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/intent",
		"contract_version": "intent-system-v5",
		"reads": ["clock"],
		"owns": ["intent"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	if latch == null:
		world.intent = RunnerWorld.neutral_intent()
		return
	world.intent = latch.sample_held() if bool(world.clock["held"]) else latch.sample()


static func reset(_world: RunnerWorld, _scope: String) -> void:
	if latch != null:
		latch.reset()
