class_name RunnerVitalsSystem
extends RefCounted

## What a contact costs the body.
##
## A port of `web/lib/sideview-runner/vitals.ts`. The family owns the order the
## verdicts come out in; this owns the runner's answer to two questions the
## family asks: what the damage sources are called, and where a body that must
## be moved is put.

## How far ahead a fallen body looks for somewhere to stand.
const RECOVERY_LOOKAHEAD_COLUMNS := 12

## The events that hurt, and the source name each becomes.
const SOURCES := {
	"hazard-contact": "hazard",
	"pit": "pit",
	"crush": "crush",
	"shot-contact": "shot",
}


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/vitals",
		"contract_version": "vitals-system-v3",
		"reads": ["clock", "avatar", "segments"],
		"owns": ["vitals"],
		"consumes": ["hazard-contact", "pit", "crush", "shot-contact"],
		"emits": ["drained", "absorbed", "run-ended"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	var vitals := world.vitals
	vitals["clockMs"] = FamilyVitals.vitals_clock_ms(float(world.clock["simulationNow"]))
	vitals["hurtThisFrame"] = false
	vitals["depletedThisFrame"] = false
	if String(world.run["phase"]) != "running":
		return

	# In emission order, which is what decides which of two sources in one frame
	# the player is told about.
	var sources := PackedStringArray()
	for entry: Variant in world.events.frame():
		var event: Dictionary = entry
		var name := String(event["type"])
		if SOURCES.has(name):
			sources.append(String(SOURCES[name]))
	if sources.is_empty():
		return

	var verdicts := FamilyVitals.resolve(
		vitals,
		sources,
		world.config["consequences"],
		FamilyVitals.CONTACT_DRAIN_AMOUNT,
		FamilyVitals.CONTACT_REFRACTORY_MS,
		func(_source: String) -> Dictionary: return recovery_surface(world)
	)
	for entry: Variant in verdicts:
		var verdict: Dictionary = entry
		match String(verdict["kind"]):
			FamilyVitals.VERDICT_DRAINED:
				world.events.emit(
					{
						"type": "drained",
						"source": verdict["source"],
						"remaining": verdict["remaining"],
					}
				)
			FamilyVitals.VERDICT_ABSORBED:
				world.events.emit({"type": "absorbed", "source": verdict["source"]})
			FamilyVitals.VERDICT_ENDED:
				world.events.emit({"type": "run-ended", "source": verdict["source"]})


## The nearest place ahead the body can stand, or nowhere.
##
## A body that must be moved and has nowhere to go ends the run — which is the
## true reading of falling into a pit with no floor for twelve columns.
static func recovery_surface(world: RunnerWorld) -> Dictionary:
	var start := int(floor(float(world.avatar["distanceColumns"])))
	for offset in RECOVERY_LOOKAHEAD_COLUMNS + 1:
		var column := start + offset
		var row := RunnerSegments.surface_row_at(world.segments, column)
		if row >= 0:
			return {"column": column, "row": row}
	return {}


## Put a recovered body down.
##
## Called from the *avatar's* step rather than from here, and that is the point:
## the vitals system decides where the body goes and the avatar system owns
## where the body is, so the hand-off is one frame of feedback rather than one
## system writing into another's slice mid-frame.
##
## The body never moves backwards — a recovery is a rescue, not a rewind.
static func apply_pending_recovery(world: RunnerWorld) -> void:
	var recovery: Dictionary = world.vitals["pendingRecovery"]
	if recovery.is_empty():
		return
	world.vitals["pendingRecovery"] = {}
	var avatar := world.avatar
	avatar["distanceColumns"] = maxf(
		float(avatar["distanceColumns"]), float(recovery["column"])
	)
	avatar["y"] = float(recovery["row"])
	avatar["vy"] = 0.0
	avatar["grounded"] = true
	avatar["airJumpsUsed"] = 0
	avatar["sliding"] = false
	avatar["motion"] = "run"
