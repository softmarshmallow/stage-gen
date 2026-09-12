class_name FamilyBanner
extends RefCounted

## The card that names a place as it is entered, and then gets out of the way.
##
## A port of `sampleMapNameBanner` in
## `web/lib/sideview-platformer/fixed-motion.ts`. In, held, out — and sampled from
## the caller's simulation time rather than handed to the engine as a tween. A
## tween is stepped by the display's own frame delta, so under a fixed-step capture
## the same run announced the same place for a different number of frames every
## time it was recorded.

const FADE_MS := 250.0
const HOLD_MS := 1000.0


## `{alpha, done}` for a banner raised `elapsed_ms` ago.
static func sample(elapsed_ms: float) -> Dictionary:
	var elapsed := maxf(0.0, elapsed_ms)
	var out_from := FADE_MS + HOLD_MS
	if elapsed >= out_from + FADE_MS:
		return {"alpha": 0.0, "done": true}
	if elapsed <= FADE_MS:
		return {"alpha": clampf(elapsed / FADE_MS, 0.0, 1.0), "done": false}
	if elapsed <= out_from:
		return {"alpha": 1.0, "done": false}
	return {"alpha": 1.0 - clampf((elapsed - out_from) / FADE_MS, 0.0, 1.0), "done": false}
