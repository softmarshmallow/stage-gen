class_name RunnerDust
extends RefCounted

## Ground dust: what running, sliding, taking off and landing kick up.
##
## A port of the arithmetic half of `web/lib/sideview-runner/dust.ts`. The
## avatar is pinned on screen and the world scrolls under it, so a puff born at
## the feet belongs to the **ground**, not to the character: it drifts away at
## the scroll speed and thins as it swells.
##
## Everything here is a pure sample over a clock. A puff is a record of where and
## when the ground was struck, and a frame asks what every live record looks like
## at one instant. Nothing owns an emitter, a timer or a random draw, so a
## fixed-step replay of a run draws the same dust on the same frame as the run
## that was played.
##
## None of this existed in the port. `RunnerDustSystem` forwarded to a view that
## was never built, so a run threw no dust at all.

## How long one puff lives, from a flat speck at the heel to nothing.
const PUFF_LIFE_MS := 380.0
## A stride puff every so often while running; the cadence is not the strip's footfall.
const STRIDE_INTERVAL_MS := 230.0
## A slide lays dust far denser than a run: it is one long contact, not a footfall.
const SLIDE_INTERVAL_MS := 90.0
const TAKEOFF_PUFFS := 3
const LAND_PUFFS := 4
const DEFAULT_ACTIVE_CAP := 64

## Cream paper over graphite ink: the flat fill and the rim the package's style
## keywords name. Only the procedural fallback uses them.
const FILL_COLOR := Color(0.953, 0.918, 0.851)
const RIM_COLOR := Color(0.165, 0.184, 0.227)
const RIM_WIDTH_PX := 2.0

## Puff radius as a fraction of a tile, by kind; the stride grows with the speed
## ramp. A tile is about a third of the avatar, and dust that reads at runner
## speed is a third to a half of the character it trails — a speck vanishes under
## the strip's own motion.
const RADIUS_TILE_FRACTION := {
	"stride": 0.18,
	"slide": 0.28,
	"takeoff": 0.24,
	"land": 0.3,
}
const STRIDE_INTENSITY_RADIUS_TILE_FRACTION := 0.12
## A puff is solid for most of its life and fades only at the end. Flat cel dust
## pops out rather than dissolving, and an opaque cloud is also what lets its
## lobes overlap without a seam: two half-transparent ellipses show their union
## as a darker lens where they cross.
const SOLID_LIFE_FRACTION := 0.6
## How far up its own half-height a newborn puff sits, so it rests on the line
## rather than across it.
const SEAT_FRACTION := 0.7

## The ellipse box is the puff's core, not its outline: a drawn cloud carries
## lobes past it, so a sprite fitted exactly inside the box reads smaller than
## the shape it replaces.
const SPRITE_OVERSCAN := 1.35


## Where a puff is kicked, in tiles, relative to the feet: `x` positive is
## forward (the way the avatar faces), `y` positive is up.
##
## A stride and a slide throw dust back along the ground; a takeoff throws it
## back and up off the push; a landing splays it both ways.
static func kick(record: Dictionary) -> Dictionary:
	var channel := int(record["index"]) * 16
	var seed_value := int(record["seed"])
	var one := FamilyParticles.unit_noise(seed_value, channel + 1)
	var two := FamilyParticles.unit_noise(seed_value, channel + 2)
	match String(record["kind"]):
		"stride":
			return {"x": -(0.25 + 0.2 * one), "y": 0.16 + 0.1 * two}
		"slide":
			return {"x": -(0.45 + 0.3 * one), "y": 0.2 + 0.14 * two}
		"takeoff":
			var fan := (float(record["index"]) / float(maxi(1, TAKEOFF_PUFFS - 1))) * 0.5
			return {
				"x": -(0.35 + 0.45 * fan + 0.15 * one),
				"y": 0.12 + 0.4 * (1.0 - fan) + 0.1 * two,
			}
		_:
			# The ground is already sliding back under the feet, so the forward
			# half of the splay must be thrown harder than the back half or it
			# lands under the avatar and is never seen.
			var side := -1.0 if int(record["index"]) % 2 == 0 else 1.0
			var forward: float = 1.8 if side > 0.0 else 1.0
			var reach := (0.3 + 0.35 * floorf(float(record["index"]) / 2.0)) * forward
			return {"x": side * (reach + 0.15 * one), "y": 0.14 + 0.12 * two}


## One puff at one instant, or an empty dictionary once it is spent (or not yet
## born).
##
## The puff starts wide and flat at the heel, swells into a rounder cloud as it
## lifts, and thins along a curve that keeps it solid for its first two thirds.
## Its x follows the ground: however far the camera has scrolled since birth is
## how far the puff has slid back along the screen.
static func sample_puff(record: Dictionary, now_ms: float, scroll_x_now: float) -> Dictionary:
	var born_at := float(record["bornAtMs"])
	var safe_now := now_ms if is_finite(now_ms) else born_at
	var age := safe_now - born_at
	if age < 0.0 or age >= PUFF_LIFE_MS:
		return {}
	var progress := age / PUFF_LIFE_MS
	var swell := FamilyParticles.ease_out_cubic(progress)
	var ground_drift := scroll_x_now - float(record["scrollXAtBirth"])
	var thrown := kick(record)
	var tile := float(record["tilePx"])
	var kind := String(record["kind"])
	var intensity_bonus := (
		STRIDE_INTENSITY_RADIUS_TILE_FRACTION * float(record["intensity"])
		if kind == "stride" else 0.0
	)
	var radius := (
		tile
		* (float(RADIUS_TILE_FRACTION[kind]) + intensity_bonus)
		* (
			0.6
			+ 0.9 * FamilyParticles.unit_noise(
				int(record["seed"]), int(record["index"]) * 16 + 3
			)
		)
	)
	var grown := radius * (0.45 + 0.85 * swell)
	var radius_y := grown * (0.7 + 0.3 * swell)
	var fade := maxf(0.0, (progress - SOLID_LIFE_FRACTION) / (1.0 - SOLID_LIFE_FRACTION))
	return {
		"x": float(record["feetX"]) - ground_drift + float(thrown["x"]) * tile * swell,
		"y": (
			float(record["feetY"])
			- radius_y * SEAT_FRACTION
			- float(thrown["y"]) * tile * swell
		),
		"radiusX": grown * (1.0 + 0.35 * (1.0 - swell)),
		"radiusY": radius_y,
		"alpha": 1.0 - fade * fade,
		"kind": kind,
		"progress": progress,
	}


## The cloud a puff is drawn as: its own ellipse and two smaller lobes riding its
## upper shoulders, so the union reads as cartoon dust rather than a bubble.
static func cloud_lobes(puff: Dictionary) -> Array:
	var x := float(puff["x"])
	var y := float(puff["y"])
	var rx := float(puff["radiusX"])
	var ry := float(puff["radiusY"])
	return [
		{"x": x, "y": y, "radiusX": rx, "radiusY": ry},
		{
			"x": x - rx * 0.55, "y": y - ry * 0.35,
			"radiusX": rx * 0.6, "radiusY": ry * 0.62,
		},
		{
			"x": x + rx * 0.5, "y": y - ry * 0.45,
			"radiusX": rx * 0.5, "radiusY": ry * 0.55,
		},
	]


## True once nothing of the record can still be drawn.
static func record_spent(record: Dictionary, now_ms: float) -> bool:
	return now_ms - float(record["bornAtMs"]) >= PUFF_LIFE_MS


## Where one puff's art goes: the centre, and the size that fits the puff's box
## with the frame's own aspect preserved and its base seated where the ellipse's
## base sits.
##
## Preserving the frame aspect is what keeps a wide cloud wide — stretching art
## to the box would undo the silhouette the art was chosen for.
static func sprite_rect(puff: Dictionary, frame_width: float, frame_height: float) -> Dictionary:
	if frame_width <= 0.0 or frame_height <= 0.0:
		return {}
	var scale := (
		minf(
			float(puff["radiusX"]) * 2.0 / frame_width,
			float(puff["radiusY"]) * 2.0 / frame_height
		)
		* SPRITE_OVERSCAN
	)
	var width := frame_width * scale
	var height := frame_height * scale
	return {
		"x": float(puff["x"]),
		"y": float(puff["y"]) + float(puff["radiusY"]) - height / 2.0,
		"width": width,
		"height": height,
	}


## The record one contact lays down.
##
## The seed folds the run's seed with the birth frame, so shapes replay with the
## run rather than with the wall clock.
static func record(
	kind: String, index: int, run_seed: int, frame: int, now_ms: float,
	feet_x: float, feet_y: float, scroll_x: float, tile_px: float, intensity: float
) -> Dictionary:
	return {
		"kind": kind,
		"index": index,
		"seed": (run_seed ^ KernelHash.imul(frame + 1, 0x27d4eb2f)) & 0xFFFFFFFF,
		"bornAtMs": now_ms,
		"feetX": feet_x,
		"feetY": feet_y,
		"scrollXAtBirth": scroll_x,
		"tilePx": tile_px,
		"intensity": intensity,
	}
