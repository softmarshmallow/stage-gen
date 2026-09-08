class_name FamilyGaugeBar
extends RefCounted

## The capsule gauge bar: one widget for every bounded resource on screen.
##
## A port of the arithmetic in `web/lib/families/hud/gauge-bar.ts`. What makes it
## read at a glance is that the fill is one continuous rounded bar over a
## spectrum, not a row of pips, and **the colour under the fill's leading edge is
## the reading**. Reveal is a crop of a gradient baked once per size, so the
## colour at a given fraction is a property of the texture rather than something
## recomputed — a bar at half is the same amber whether it got there in one hit
## or in four.
##
## The port had drawn a single rectangle lerped from red to green, which loses
## exactly that: a lerp gives no fixed colour to a fraction, so the same reading
## looks different depending on where the maximum happens to sit.

## Low to high, left to right. Not decoration: the hand-off from red through
## amber is where a player decides to back out.
const GRADIENT_STOPS := [
	[0.0, Color(0.831, 0.239, 0.184)],
	[0.35, Color(0.910, 0.455, 0.231)],
	[0.6, Color(0.949, 0.757, 0.306)],
	[0.82, Color(0.620, 0.796, 0.278)],
	[1.0, Color(0.247, 0.749, 0.435)],
]

const TRACK_FILL := Color(0.055, 0.039, 0.035, 0.78)
const TRACK_RIM := Color(0.0, 0.0, 0.0, 0.7)
const RIM_WIDTH := 1.0

## Alpha applied to the whole bar while its gauge is refusing input.
const DIMMED_ALPHA := 0.55


## How much of the capsule the fill covers.
##
## A gauge with anything left never draws an empty bar: below one cap's worth the
## rounded end has nothing left to round and the bar reads as spent, which on
## something one hit from empty is the difference between pressing on and backing
## off. Reaching zero is the only state that empties it, and it empties it
## completely.
static func fill_width(value: float, max_value: float, width: float, height: float) -> float:
	var top := maxf(0.0, max_value)
	var held := minf(maxf(0.0, value), top)
	if held <= 0.0 or top <= 0.0:
		return 0.0
	return minf(width, maxf(height, (held / top) * width))


## Whether a bar has anything to say yet.
##
## A full gauge's bar reports that nothing has happened, and a stage carrying a
## dozen of them is a dozen readouts competing with the bodies they belong to.
## Callers whose bar is a promise about the run rather than news about one body —
## the player's own — simply do not ask.
static func revealed_by_change(value: float, max_value: float) -> bool:
	if not is_finite(value) or not is_finite(max_value):
		return false
	if max_value <= 0.0:
		return false
	return value < max_value


## The spectrum's colour at a fraction of the bar.
static func color_at(fraction: float) -> Color:
	var t := clampf(fraction, 0.0, 1.0)
	var previous: Array = GRADIENT_STOPS[0]
	for entry: Variant in GRADIENT_STOPS:
		var stop: Array = entry
		var at := float(stop[0])
		if t <= at:
			var span := at - float(previous[0])
			if span <= 0.0:
				return stop[1]
			return (previous[1] as Color).lerp(stop[1], (t - float(previous[0])) / span)
		previous = stop
	return GRADIENT_STOPS[GRADIENT_STOPS.size() - 1][1]
