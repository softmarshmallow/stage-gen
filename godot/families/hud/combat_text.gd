class_name FamilyCombatText
extends RefCounted

## The number that pops off a body when a blow lands.
##
## The arithmetic half of `web/lib/sideview-platformer/combat-text.ts`. Clock
## free by construction: every value is a function of how long the number has
## been on screen, so a fixed-step capture and ordinary play sample the same
## curve, and a hitstop freezes the numbers with the world rather than letting
## them run on.
##
## The per-digit stagger the browser also draws — each digit arriving on its own
## beat and falling onto an arc — is not here. What is here is the run's own
## motion, which is what a player reads: a punch, a rise, and a fade.

const LIFETIME_MS := 640.0
const PUNCH_PEAK_MS := 96.0
const PUNCH_SETTLE_MS := 160.0
const RISE_MS := 480.0
const FADE_START_MS := 360.0

## Where the run starts, where the punch takes it, and where it settles.
const SCALE_FROM := 0.78
const SCALE_PEAK := 1.14
const SCALE_REST := 1.0

## How far a number climbs, in pixels.
const RISE_PX := 32.0

## A blow the player landed reads smaller than one they took: the second is the
## one that matters more.
const OUTGOING_SIZE := 64.0
const INCOMING_SIZE := 70.0
const CRITICAL_SCALE := 1.4

## How far above the drawn top of a body a number starts.
const RISE_ABOVE := 18.0


## One number's state at `elapsed_ms`, or an empty dictionary once it is over.
##
## Returns `{scale, riseY, alpha}`.
static func sample(elapsed_ms: float) -> Dictionary:
	if elapsed_ms < 0.0 or elapsed_ms >= LIFETIME_MS:
		return {}
	return {
		"scale": _punch(elapsed_ms),
		"riseY": -RISE_PX * FamilyParticles.ease_out_cubic(minf(1.0, elapsed_ms / RISE_MS)),
		"alpha": (
			1.0
			if elapsed_ms < FADE_START_MS
			else 1.0 - (elapsed_ms - FADE_START_MS) / (LIFETIME_MS - FADE_START_MS)
		),
	}


## The size a number is drawn at, before its own punch.
static func size_for(incoming: bool, critical: bool) -> float:
	var base := INCOMING_SIZE if incoming else OUTGOING_SIZE
	return base * (CRITICAL_SCALE if critical else 1.0)


## What a number says. The mark on a critical is deliberately the half of the
## read that survives colour-blindness and a thumbnail.
static func text_for(amount: int, critical: bool) -> String:
	return "%d!" % amount if critical else str(amount)


## Up fast, then back: the punch is what makes a number land rather than appear.
static func _punch(elapsed_ms: float) -> float:
	if elapsed_ms <= PUNCH_PEAK_MS:
		return SCALE_FROM + (SCALE_PEAK - SCALE_FROM) * FamilyParticles.ease_out_cubic(
			elapsed_ms / PUNCH_PEAK_MS
		)
	if elapsed_ms >= PUNCH_SETTLE_MS:
		return SCALE_REST
	return SCALE_PEAK + (SCALE_REST - SCALE_PEAK) * (
		(elapsed_ms - PUNCH_PEAK_MS) / (PUNCH_SETTLE_MS - PUNCH_PEAK_MS)
	)
