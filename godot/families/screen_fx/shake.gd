class_name FamilyShake
extends RefCounted

## Camera shake: a decaying, seeded nudge, and the rule for adding several up.
##
## A port of `web/lib/families/screen-fx/shake.ts`. Deterministic and clock-free
## by construction — the phase is a hash of the source's own seed and the elapsed
## time is passed in — so a fixed-step replay produces identical frames and a
## reduced-motion viewer is served by a caller that simply raises no source.
##
## It returns an *offset*. What a host does with it is the host's business, and
## that is the whole reason this is a family rather than a method that writes
## into somebody else's scroll: an effect whose only expression is a mutation
## cannot be owned by anyone.

## What a kill shakes like: four pixels, an eighth of a second, six steps.
const KILL := {
	"amplitudePx": 4.0,
	"durationMs": 130.0,
	"stepMs": 16.0,
	"pattern": [1.0, -0.8, 0.55, -0.35, 0.2, 0.0],
	"verticalFraction": 0.6,
}

## A critical shakes harder than an ordinary kill.
const CRITICAL_SCALE := 1.35


## The offset one source contributes now; zero once it has run out.
##
## `source` is `{seed, elapsedMs, dirSign, scale}`.
static func sample(source: Dictionary, profile: Dictionary) -> Dictionary:
	var elapsed := float(source["elapsedMs"])
	if elapsed >= float(profile["durationMs"]):
		return {"x": 0.0, "y": 0.0}
	var pattern: Array = profile["pattern"]
	var step := int(floor(elapsed / float(profile["stepMs"])))
	var phase := absi(int(source["seed"])) % pattern.size()
	var decay := 1.0 - elapsed / float(profile["durationMs"])
	var amplitude := float(profile["amplitudePx"]) * float(source["scale"]) * decay
	return {
		"x": float(pattern[(phase + step) % pattern.size()]) * amplitude * float(source["dirSign"]),
		# Two steps out of phase, so the view moves on a diagonal rather than
		# along one axis.
		"y": (
			float(pattern[(phase + step + 2) % pattern.size()])
			* amplitude
			* float(profile["verticalFraction"])
		),
	}


## Several sources at once, bounded so a crowd of kills does not throw the view
## off the map.
static func sum(samples: Array, bound_px: float) -> Dictionary:
	var x := 0.0
	var y := 0.0
	for entry: Variant in samples:
		var offset: Dictionary = entry
		x += float(offset["x"])
		y += float(offset["y"])
	return {"x": clampf(x, -bound_px, bound_px), "y": clampf(y, -bound_px, bound_px)}
