class_name FamilyDirector
extends RefCounted

## A staged event: which phase it is in, when it entered, and how it ended.
##
## A port of `web/lib/families/director/set-piece.ts` and `swaps.ts`.
##
## A trigger is **forward-only**: it fires when the tracked position has reached
## the datum, and a position that goes backwards does not un-fire it. That is
## what an auto-runner needs and it is why the datum is a bare number on the
## slice rather than an object — the slice is replay-hashed, and a hashed object
## is a hashed identity.


## Enter a phase, stamping when. The outcome is deliberately untouched: a phase
## change is not a verdict.
static func enter_phase(state: Dictionary, phase: String, now: float) -> void:
	state["phase"] = phase
	state["phaseStartedAt"] = now


## How long this phase has run, or -1 when it never started.
static func phase_elapsed(state: Dictionary, now: float) -> float:
	var started: Variant = state.get("phaseStartedAt")
	if started == null:
		return -1.0
	return now - float(started)


## Has the tracked position reached the datum?
static func trigger_reached(at: float, position: float) -> bool:
	return position >= at
