class_name FamilyGaugeBar
extends RefCounted

## The gauge bar: one widget for every bounded resource on screen.
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
##
## The shape is a small-radius rounded rectangle rather than the browser's pill.
## A capsule half the canvas wide reads as a lozenge sitting on the picture; a
## squared bar with soft corners reads as a readout built into it.
##
## TODO(ui-gen): a panel takes its frame from generated nine-slice art. There is
## no `bar` kind in the UI atlas, so the two borders below are drawn in code —
## when there is one, the track and the fill become published art and the host's
## bake goes with them.

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

## How soft the corners are. Small enough to stay a rectangle at any width.
const CORNER_RADIUS := 3.0

## Border one, the outline: what holds the bar apart from whatever it is drawn
## over. The runner's is drawn against a canopy, so this is nearly opaque.
const OUTLINE_COLOR := Color(0.043, 0.035, 0.031, 0.92)
const OUTLINE_WIDTH := 2.0

## The share of a bar's height the two borders may take between them.
##
## A two-pixel outline and a one-pixel rim are right on a twenty-two pixel bar
## and absurd on a five: three pixels a side against a five pixel bar leaves no
## bar. A creature's floating gauge is that small, so the borders are a fraction
## of the height rather than a constant, and above the size they were authored
## for the fraction never binds.
const BORDER_HEIGHT_SHARE := 0.28

## Border two, the fill's own edge: a darker line just inside the outline, which
## is what makes the fill read as a body sitting in the track rather than as a
## coloured area painted on it.
const INNER_RIM_WIDTH := 1.0
const INNER_RIM_SHADE := 0.62

## And the depth across that body: lifted along the top edge, shaded along the
## bottom, so a flat colour picks up a direction.
const TOP_LIFT := 0.28
const BOTTOM_SHADE := 0.32

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


## How far inside the bar's shape a point is, in pixels. Negative outside.
##
## The shape both borders are measured from, and the only place the rounding
## lives. A point's distance from a rounded rectangle's edge is the distance
## from the box it is inset into, less the radius.
## The outline this bar can afford, in pixels.
static func outline_width(height: float) -> float:
	return minf(OUTLINE_WIDTH, maxf(1.0, floorf(height * BORDER_HEIGHT_SHARE)))


## The inner rim this bar can afford. Zero when the outline has taken the budget,
## which is the honest answer for a bar too small to have two borders.
static func inner_rim_width(height: float) -> float:
	var outline := outline_width(height)
	if height * BORDER_HEIGHT_SHARE - outline < 1.0:
		return 0.0
	return INNER_RIM_WIDTH


static func inset_depth(
	x: float, y: float, width: float, height: float, radius: float
) -> float:
	var round_by := minf(radius, minf(width, height) / 2.0)
	var dx := absf(x - width / 2.0) - (width / 2.0 - round_by)
	var dy := absf(y - height / 2.0) - (height / 2.0 - round_by)
	var outside := sqrt(maxf(dx, 0.0) * maxf(dx, 0.0) + maxf(dy, 0.0) * maxf(dy, 0.0))
	return round_by - (outside + minf(maxf(dx, dy), 0.0))


## The fill's depth shading at a fraction of the way down it: above one at the
## top edge, below one at the bottom.
static func depth_multiplier(row_fraction: float) -> float:
	var t := clampf(row_fraction, 0.0, 1.0)
	return (1.0 + TOP_LIFT) + t * ((1.0 - BOTTOM_SHADE) - (1.0 + TOP_LIFT))
