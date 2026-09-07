class_name FamilyJump
extends RefCounted

## Whether a jump is allowed, and the arc it flies.
##
## A port of `web/lib/families/sideview/traversal/jump.ts`.
##
## The arc is **derived, not authored**. A genre states the widest gap it will
## ask a player to clear and the highest rise it will ask them to make; the
## speed and the gravity that make both reachable fall out of those two numbers
## and the run speed. That is why a package cannot publish an unclearable level:
## the admission that drew it and the physics that flies it read the same
## fields.

const KIND_NONE := "none"
const KIND_GROUND := "ground"
const KIND_AIR := "air"


## May this jump happen, and at what velocity? Returns `{kind, vy, airJumpsUsed}`.
##
## `vy` is negative because up is a smaller row. A refusal is `kind == "none"`
## with the budget untouched, never an error: a jump pressed with nothing left
## is an ordinary thing a player does.
static func resolve_jump_request(
	support: String,
	air_jumps_used: int,
	now_ms: float,
	coyote_expires_at_ms: float,
	crouching: bool,
	maximum_air_jumps: int,
	jump_velocity: float,
	air_jump_velocity: float
) -> Dictionary:
	var refused := {"kind": KIND_NONE, "vy": 0.0, "airJumpsUsed": air_jumps_used}
	if support == "climbable":
		return refused
	if support != FamilyContact.SUPPORT_AIR:
		if crouching:
			return refused
		return {"kind": KIND_GROUND, "vy": -jump_velocity, "airJumpsUsed": 0}
	# A negative expiry is "no window": the browser passes null and GDScript has
	# no nullable float, so the absence is a value outside every real clock.
	var coyote_open := coyote_expires_at_ms >= 0.0 and now_ms <= coyote_expires_at_ms
	if coyote_open and air_jumps_used == 0:
		return {"kind": KIND_GROUND, "vy": -jump_velocity, "airJumpsUsed": 0}
	if air_jumps_used >= maximum_air_jumps:
		return refused
	return {"kind": KIND_AIR, "vy": -air_jump_velocity, "airJumpsUsed": air_jumps_used + 1}


## The arc that clears `max_clear_gap` while rising `max_rise`, at `min_speed`.
##
## Returns `{initialSpeedPerSecond, gravityPerSecondSquared, peakUnits,
## airtimeSeconds}`, or an empty dictionary when the speed is not positive —
## which is a refusal, because an arc at zero speed is an infinite airtime.
static func jump_arc_from_admission(
	max_rise: float,
	max_clear_gap: float,
	min_speed: float,
	peak_margin: float,
	airtime_headroom: float
) -> Dictionary:
	if min_speed <= 0.0:
		return {}
	var peak_units := max_rise + peak_margin
	var airtime := ((max_clear_gap + 1.0) / min_speed) * airtime_headroom
	return {
		"initialSpeedPerSecond": 4.0 * peak_units / airtime,
		"gravityPerSecondSquared": 8.0 * peak_units / (airtime * airtime),
		"peakUnits": peak_units,
		"airtimeSeconds": airtime,
	}
