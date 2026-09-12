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
## Only two of the outputs reach the simulation: `released`, which is when the
## world may move again, and `finished`, which is when the moment is over. The
## rest are the drawing, and a host that draws none of them still plays the same
## game — which is why the scrim behind the moment can be re-timed here without
## anything about the run changing.
##
## **The plate slides; the scrim fades.** The browser did neither: the scrim
## appeared between one frame and the next part-way through the moment, held,
## and then rode the plate off the left edge, so the world stayed pushed back
## until after the thing pushing it back had gone. It comes up over a quarter
## second now and is gone early in the exit, well before the plate has finished
## leaving, which puts the world back in front of the player at the moment they
## are given it. The plate's own entry and exit are the browser's, unchanged.

const TEAR_REVEAL := "tear_reveal_v1"

const RIP_ENTRY_SCALE := 1.12
const BUST_ENTRY_OFFSET := -0.3
const BUST_ENTRY_SCALE := 1.25
const BUST_HOLD_PUSH := 0.04
## How far the world behind the moment is pushed back. Deliberately light: the
## plate already carries the eye, and a heavier scrim reads as a black card
## dropped over the game rather than as depth.
const CUT_IN_DIM := 0.22
## How long the scrim takes to arrive. It used to appear between one frame and
## the next.
const DIM_FADE_MS := 260.0
## How much of the exit the scrim takes to leave. It goes well before the plate
## has finished sliding off, rather than travelling with it.
const DIM_EXIT_FRACTION := 0.4


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
	# The scrim arrives over a quarter second and leaves inside the first part of
	# the exit, with most of it gone in the first few frames of that.
	var dim_from := float(ch["dimFromMs"])
	var dim_in := FamilyParticles.ease_out_cubic(
		_segment(elapsed_ms, dim_from, dim_from + DIM_FADE_MS)
	)
	var dim_out := FamilyParticles.ease_out_cubic(
		_segment(
			elapsed_ms, release_ms, release_ms + (duration_ms - release_ms) * DIM_EXIT_FRACTION
		)
	)
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
		"dim": CUT_IN_DIM * dim_in * (1.0 - dim_out),
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
