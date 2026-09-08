class_name RunnerPresentation
extends RefCounted

## Pure presentation arithmetic for the runner's pickups and hazards.
##
## A port of `web/lib/sideview-runner/presentation.ts`, which this port left
## behind entirely: the coins stood still, the hazards drew at whatever width
## their raster happened to be, and nothing warned that a hazard was coming.
##
## None of it feeds the simulation. Occupancy and the published boxes remain the
## only gameplay geometry — these transforms make an authored opportunity or
## threat easier to read at runner speed, and a run played with them and a run
## played without them end identically.
##
## Everything is a function of a clock and a phase rather than a stored tween,
## so a fixed-step replay draws the same frame twice.

const TAU_TURNS := TAU

## How fast a collectible turns, in turns per second.
const FLIP_TURNS_PER_SECOND := 1.4
## Never collapse a face all the way to zero: a one-pixel edge disappears under
## filtering and reads as a dropped frame rather than as a coin edge-on.
const FLIP_MINIMUM_FACE := 0.16
## How far ahead a hazard starts announcing itself.
const CUE_RANGE_COLUMNS := 8.0
## The cue's own heartbeat, in cycles per second.
const CUE_PULSES_PER_SECOND := 2.2


## A stable per-instance phase, so a trail of coins ripples instead of moving as
## one slab. FNV-1a over the instance key, which is the browser's `imul` loop.
static func phase_for(key: String) -> float:
	return (float(KernelHash.fnv1a32(key)) / 4294967296.0) * TAU_TURNS


## A continuous flip, hover and glint for a single-image collectible.
##
## Returns an empty dictionary when the clock or the phase is not a number,
## which is the value form of the browser's throw.
static func collectible(elapsed_ms: float, phase_offset: float) -> Dictionary:
	if not is_finite(elapsed_ms) or not is_finite(phase_offset):
		return {}
	var phase := (elapsed_ms / 1000.0) * TAU_TURNS * FLIP_TURNS_PER_SECOND + phase_offset
	# How much of the face is turned toward the viewer, 0 edge-on to 1 flat.
	var face := absf(cos(phase))
	var hover := sin(phase * 0.5)
	return {
		"bobRows": hover * 0.1,
		"scaleXMultiplier": FLIP_MINIMUM_FACE + face * (1.0 - FLIP_MINIMUM_FACE),
		# A hair taller edge-on, the way a real disc thickens as it turns.
		"scaleYMultiplier": 0.96 + (1.0 - face) * 0.04,
		"haloAlpha": 0.1 + face * 0.22,
		"haloScale": 0.82 + face * 0.18,
	}


## Keep a hazard's visible footprint inside the exact published collision
## column, without touching its authored vertical calibration.
##
## A prop drawn wider than the column it occupies is a prop the player is sure
## they cleared and the simulation is sure they did not.
static func hazard_visual_scale(
	calibrated_scale: float, source_width: float, collision_width_pixels: float
) -> Dictionary:
	if (
		not is_finite(calibrated_scale) or calibrated_scale <= 0.0
		or not is_finite(source_width) or source_width <= 0.0
		or not is_finite(collision_width_pixels) or collision_width_pixels <= 0.0
	):
		return {}
	return {
		"scaleX": minf(calibrated_scale, collision_width_pixels / source_width),
		"scaleY": calibrated_scale,
	}


## A restrained approach cue. Behind the player it vanishes immediately.
static func hazard_cue_alpha(distance_ahead_columns: float, elapsed_ms: float) -> float:
	if not is_finite(distance_ahead_columns) or not is_finite(elapsed_ms):
		return 0.0
	if distance_ahead_columns < 0.0 or distance_ahead_columns > CUE_RANGE_COLUMNS:
		return 0.0
	var proximity := 1.0 - distance_ahead_columns / CUE_RANGE_COLUMNS
	var pulse := (
		0.75 + sin((elapsed_ms / 1000.0) * TAU_TURNS * CUE_PULSES_PER_SECOND) * 0.25
	)
	return (0.12 + proximity * 0.24) * pulse
