class_name FamilyVitals
extends RefCounted

## A body that can be hurt: a gauge, a refractory window, and what a contact
## costs.
##
## A port of `web/lib/families/vitals/vitals.ts`. The slice is a Dictionary with
## `gauge`, `clockMs`, `pendingRecovery`, `hurtThisFrame` and `depletedThisFrame`.
##
## The consequence table is the genre's, not the family's: the same contact ends
## the run in one package and costs a point in another, and that is an authored
## decision the manifest carries. What the family owns is the *order* the
## verdicts come out in, because it decides which of two sources in one frame
## the player is told killed them.

const CONSEQUENCE_END := "end_run_v1"
const CONSEQUENCE_DRAIN := "drain_v1"
const CONSEQUENCE_DRAIN_AND_RECOVER := "drain_and_recover_v1"

const VERDICT_DRAINED := "drained"
const VERDICT_ABSORBED := "absorbed"
const VERDICT_ENDED := "ended"

## What a contact costs and how long it protects. Shared by both side-view
## genres; a genre that wants another profile states one rather than editing it.
const CONTACT_DRAIN_AMOUNT := 1.0
const CONTACT_REFRACTORY_MS := 900.0
const CONTACT_BLINK_INTERVAL_MS := 75.0
const CONTACT_BLINK_ALPHA := 0.35


## A fresh slice. `max_points` of 0 means this package has no vitals at all, and
## the gauge stays empty — every consequence then ends the run, which is the
## true reading of a package that declared no health.
static func create(max_points: int) -> Dictionary:
	return {
		"gauge": {} if max_points <= 0 else KernelGauge.create(max_points),
		"clockMs": 0.0,
		"pendingRecovery": {},
		"hurtThisFrame": false,
		"depletedThisFrame": false,
	}


## Resolve every damage source this frame, in the order they were emitted.
##
## Returns the verdicts in order. **The first verdict that ends the run is the
## last verdict**: once the run is over the remaining sources are not resolved,
## so a player who fell into a pit and touched a hazard on the same frame is
## told about the pit and the hazard never happened.
##
## `recover` is called only for `drain_and_recover_v1` and answers with a place
## to put the body, or an empty dictionary for "nowhere" — which ends the run,
## because a body that must be moved and cannot be is not a body that survived.
static func resolve(
	vitals: Dictionary,
	sources: PackedStringArray,
	consequences: Dictionary,
	drain_amount: float,
	refractory_ms: float,
	recover: Callable
) -> Array:
	var verdicts: Array = []
	for source in sources:
		var consequence := String(consequences.get(source, ""))
		if consequence == "" or consequence == CONSEQUENCE_END:
			verdicts.append({"kind": VERDICT_ENDED, "source": source})
			return verdicts
		var gauge: Dictionary = vitals.get("gauge", {})
		if gauge.is_empty():
			verdicts.append({"kind": VERDICT_ENDED, "source": source})
			return verdicts
		var change := KernelGauge.drain(
			gauge, drain_amount, float(vitals.get("clockMs", 0.0)), refractory_ms
		)
		if not bool(change.get("connected", false)):
			verdicts.append({"kind": VERDICT_ABSORBED, "source": source})
			continue
		vitals["gauge"] = change["gauge"]
		vitals["hurtThisFrame"] = true
		verdicts.append(
			{"kind": VERDICT_DRAINED, "source": source, "remaining": change["after"]}
		)
		if consequence == CONSEQUENCE_DRAIN_AND_RECOVER:
			var somewhere: Dictionary = recover.call(source)
			if somewhere.is_empty():
				verdicts.append({"kind": VERDICT_ENDED, "source": source})
				return verdicts
			vitals["pendingRecovery"] = somewhere
		if bool(change.get("depleted", false)):
			vitals["depletedThisFrame"] = true
			verdicts.append({"kind": VERDICT_ENDED, "source": source})
			return verdicts
	return verdicts


## Is the body inside its window, and so untouchable?
static func body_is_immune(vitals: Dictionary) -> bool:
	var gauge: Dictionary = vitals.get("gauge", {})
	if gauge.is_empty():
		return false
	return KernelGauge.is_refractory(gauge, float(vitals.get("clockMs", 0.0)))


## The alpha a hurt body draws at.
static func body_blink_alpha(
	vitals: Dictionary, interval_ms: float, dim_alpha: float
) -> float:
	var gauge: Dictionary = vitals.get("gauge", {})
	if gauge.is_empty():
		return 1.0
	return KernelGauge.refractory_blink_alpha(
		gauge, float(vitals.get("clockMs", 0.0)), interval_ms, dim_alpha
	)


## Seconds on the simulation clock, in the milliseconds a gauge counts.
static func vitals_clock_ms(simulation_now_seconds: float) -> float:
	return simulation_now_seconds * 1000.0
