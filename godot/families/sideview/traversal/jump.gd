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


## Prove an arc: semi-implicit Euler in the controller's own step order.
##
## A port of `simulateJumpArc` in
## `web/lib/families/sideview/traversal/jump.ts`. Returns
## `{reachable, rise, gap, apexRise, landingStep, horizontalRange, airJumpStep}`,
## or an empty dictionary for values outside the supported range — a refusal,
## because an arc at zero gravity never lands and there is no partial answer to
## give.
##
## `air_jump_velocity` proves a double jump; pass a negative number for a
## character with one jump, the same "no window" convention `resolve_jump_request`
## uses for its coyote expiry, because GDScript has no nullable float. The
## impulse is spent on the first step the arc stops rising, which is both the
## height-optimal moment and the one a player naturally hits, so a route proved
## here is a route a player can fly. Landing still requires a descending foot,
## so the second arc cannot "land" on a deck it is passing on the way up.
##
## `landingStep` and `horizontalRange` are `-1` when the arc never lands, and
## `airJumpStep` is `-1` when no mid-air impulse was spent.
static func simulate_jump_arc(
	rise: float,
	gap: float,
	horizontal_speed: float,
	jump_velocity: float,
	air_jump_velocity: float,
	gravity: float,
	step_seconds: float,
	maximum_steps: int
) -> Dictionary:
	if rise < 0.0 or gap < 0.0 or horizontal_speed < 0.0:
		return {}
	if jump_velocity <= 0.0 or gravity <= 0.0 or step_seconds <= 0.0 or maximum_steps < 1:
		return {}
	var target_y := -rise
	var y := 0.0
	var vy := -jump_velocity
	var apex_rise := 0.0
	var air_jump_step := -1
	var air_jump_pending := air_jump_velocity > 0.0
	for step in range(1, maximum_steps + 1):
		var previous_y := y
		vy += gravity * step_seconds
		if air_jump_pending and vy >= 0.0:
			vy = -air_jump_velocity
			air_jump_pending = false
			air_jump_step = step
		y += vy * step_seconds
		apex_rise = maxf(apex_rise, -y)
		if vy >= 0.0 and previous_y <= target_y and y >= target_y:
			var horizontal_range := horizontal_speed * step_seconds * float(step)
			return {
				"reachable": gap <= horizontal_range,
				"rise": rise,
				"gap": gap,
				"apexRise": apex_rise,
				"landingStep": step,
				"horizontalRange": horizontal_range,
				"airJumpStep": air_jump_step,
			}
	return {
		"reachable": false,
		"rise": rise,
		"gap": gap,
		"apexRise": apex_rise,
		"landingStep": -1,
		"horizontalRange": -1.0,
		"airJumpStep": air_jump_step,
	}
