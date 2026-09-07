class_name FamilyCutIn
extends RefCounted

## The choreography of a cut-in: a tear, a bust, a banner, and when the world is
## let go.
##
## A port of `web/lib/families/screen-fx/cut-in.ts`. Every number is a
## millisecond on the *frame* clock, because a moment plays over a world it has
## itself stopped — measuring it on the clock it froze would freeze the picture
## too.
##
## Only two of the nine outputs reach the simulation: `released`, which is when
## the world may move again, and `finished`, which is when the moment is over.
## The other seven are the drawing, and a host that draws none of them still
## plays the same game.

const TEAR_REVEAL := "tear_reveal_v1"

const RIP_ENTRY_SCALE := 1.12
const BUST_ENTRY_OFFSET := -0.3
const BUST_ENTRY_SCALE := 1.25
const BUST_HOLD_PUSH := 0.04
const CUT_IN_DIM := 0.35


## The one choreography both side-view genres bind.
static func choreography(name: String) -> Dictionary:
	if name != TEAR_REVEAL:
		return {}
	return {
		"ripInEndMs": 180.0,
		"bustInStartMs": 100.0,
		"bustInEndMs": 400.0,
		"bannerInStartMs": 300.0,
		"bannerInEndMs": 480.0,
		"dimFromMs": 600.0,
		"releaseMs": 1600.0,
		"durationMs": 1900.0,
		"stripeDriftPerSecond": 4.4,
	}


## One frame of the moment. Returns the nine fields; an empty dictionary when
## the elapsed time is not a time, which is a refusal rather than a guess.
static func frame(elapsed_ms: float, ch: Dictionary) -> Dictionary:
	if not is_finite(elapsed_ms) or elapsed_ms < 0.0:
		return {}
	var release_ms := float(ch["releaseMs"])
	var duration_ms := float(ch["durationMs"])
	var entry := FamilyParticles.ease_out_cubic(_segment(elapsed_ms, 0.0, float(ch["ripInEndMs"])))
	var exit := _ease_in_cubic(_segment(elapsed_ms, release_ms, duration_ms))
	var bust_in := _segment(elapsed_ms, float(ch["bustInStartMs"]), float(ch["bustInEndMs"]))
	var hold := _segment(elapsed_ms, float(ch["bustInEndMs"]), release_ms)
	var banner_in := FamilyParticles.ease_out_cubic(
		_segment(elapsed_ms, float(ch["bannerInStartMs"]), float(ch["bannerInEndMs"]))
	)
	return {
		"ripX": (1.0 - entry) - exit * 1.15,
		"ripScale": RIP_ENTRY_SCALE - (RIP_ENTRY_SCALE - 1.0) * entry,
		"bustDx": BUST_ENTRY_OFFSET * (1.0 - _ease_out_back(bust_in)),
		"bustScale": (
			(BUST_ENTRY_SCALE - (BUST_ENTRY_SCALE - 1.0) * FamilyParticles.ease_out_cubic(bust_in))
			* (1.0 + BUST_HOLD_PUSH * hold)
		),
		"stripePhase": (elapsed_ms / 1000.0) * float(ch["stripeDriftPerSecond"]),
		"bannerX": (1.0 - banner_in) * 0.55 - exit * 1.15,
		"dim": CUT_IN_DIM if elapsed_ms >= float(ch["dimFromMs"]) else 0.0,
		"released": elapsed_ms >= release_ms,
		"finished": elapsed_ms >= duration_ms,
	}


static func _segment(t: float, start: float, end: float) -> float:
	return minf(1.0, maxf(0.0, (t - start) / (end - start)))


static func _ease_in_cubic(x: float) -> float:
	return x * x * x


static func _ease_out_back(x: float) -> float:
	var c1 := 1.70158
	var c3 := c1 + 1.0
	var d := x - 1.0
	return 1.0 + c3 * d * d * d + c1 * d * d
