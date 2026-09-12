class_name DialogueFraming
extends RefCounted

## How far away a scene stands from its cast, as three numbers a view can use.
##
## A port of the runtime's half of `web/lib/dialogue-scene/framing.ts`. The rest
## of that file is a producer-side prompt mapper — the words "full shot",
## "medium shot", "close-up" and the face-height bands it asks a model for — and
## none of it reaches a runtime. What does reach one is the `presentation` block:
## a scale, and an anchor in percent of the frame.
##
## The scale is **normalised against the zoom the plates were drawn at**, not
## used raw. A package that drew its cast at 70 and plays at 70 gets exactly 1;
## one that drew at 70 and plays at 85 gets 1.37. Used raw, every plate would be
## drawn three times too large.

const PUBLIC_MIN := 0.0
const PUBLIC_MAX := 100.0
## Outside this band the evidence the tiers were measured from runs out, so a
## zoom is clamped into it rather than extrapolated.
const EVIDENCE_MIN := 25.0
const EVIDENCE_MAX := 85.0

## The face height, in percent of the frame, that a full shot puts a head at.
## Every scale is a ratio against this.
const FULL_SHOT_FACE_MIDPOINT := 9.0

## The three anchors the tiers are measured at, and what each publishes.
const ANCHORS := [25.0, 60.0, 85.0]
const FACE_LOW := [7.0, 18.0, 34.0]
const FACE_HIGH := [11.0, 26.0, 46.0]
const HEADROOM_LOW := [4.0, 4.0, 3.0]
const HEADROOM_HIGH := [8.0, 8.0, 7.0]
const PRESENTATION_X := [72.0, 62.0, 52.0]


## One zoom, mapped. Returns `{scale, xPercent, yPercent, saturated}`.
static func map_zoom(zoom: float) -> Dictionary:
	var clamped := clampf(zoom, PUBLIC_MIN, PUBLIC_MAX)
	var effective := clampf(clamped, EVIDENCE_MIN, EVIDENCE_MAX)
	var lower := 0
	var ratio := 0.0
	if effective <= ANCHORS[1]:
		ratio = (effective - ANCHORS[0]) / (ANCHORS[1] - ANCHORS[0])
	else:
		lower = 1
		ratio = (effective - ANCHORS[1]) / (ANCHORS[2] - ANCHORS[1])
	var face_low := _round_to(_lerp(FACE_LOW[lower], FACE_LOW[lower + 1], ratio), 1)
	var face_high := _round_to(_lerp(FACE_HIGH[lower], FACE_HIGH[lower + 1], ratio), 1)
	var head_low := _round_to(_lerp(HEADROOM_LOW[lower], HEADROOM_LOW[lower + 1], ratio), 1)
	var head_high := _round_to(_lerp(HEADROOM_HIGH[lower], HEADROOM_HIGH[lower + 1], ratio), 1)
	return {
		"scale": _round_to((face_low + face_high) / 2.0 / FULL_SHOT_FACE_MIDPOINT, 3),
		"xPercent": _round_to(_lerp(PRESENTATION_X[lower], PRESENTATION_X[lower + 1], ratio), 1),
		"yPercent": _round_to((head_low + head_high) / 2.0, 1),
		"saturated": not is_equal_approx(effective, clamped),
	}


## The placement a view draws with: the played zoom against the drawn one.
##
## Returns `{scale, xPercent, yPercent}`, or a refusal when either zoom maps to a
## scale of nothing — which would divide the cast into a point.
static func placement(framing_zoom: float, source_framing_zoom: float) -> Variant:
	if not is_finite(framing_zoom) or not is_finite(source_framing_zoom):
		return KernelRefusal.of(
			"dialogue/framing", "a scene's framing zoom must be a finite number", "placement"
		)
	var played := map_zoom(framing_zoom)
	var drawn := map_zoom(source_framing_zoom)
	if float(drawn["scale"]) <= 0.0 or float(played["scale"]) <= 0.0:
		return KernelRefusal.of(
			"dialogue/framing", "a scene's framing scales must be positive", "placement"
		)
	return {
		"scale": _round_to(float(played["scale"]) / float(drawn["scale"]), 3),
		"xPercent": float(played["xPercent"]),
		"yPercent": float(played["yPercent"]),
	}


static func _lerp(low: float, high: float, ratio: float) -> float:
	return low + (high - low) * ratio


## Half away from zero at `digits`, which is what the browser's `Math.round` on a
## scaled value does for every positive number this produces.
static func _round_to(value: float, digits: int) -> float:
	var factor := pow(10.0, float(digits))
	return roundf(value * factor) / factor
