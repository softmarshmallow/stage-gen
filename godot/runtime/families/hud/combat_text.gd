class_name FamilyCombatText
extends RefCounted

## The number that pops off a body when a blow lands.
##
## The arithmetic half of `web/lib/sideview-platformer/combat-text.ts`. Clock
## free by construction: every value is a function of how long the number has
## been on screen, so a fixed-step capture and ordinary play sample the same
## curve, and a hitstop freezes the numbers with the world rather than letting
## them run on.
##
## A number is drawn one digit at a time, and each digit is placed, sized and
## revealed on its own. That is the whole difference between a damage number and
## a damage *effect*: one text object can only pop as a block, while a row of
## digits arrives left to right, each landing slightly off the line its
## neighbours sit on, so six digits read as six struck things rather than as one
## word that grew.
##
## Every per-digit displacement is a share of the font size rather than a pixel
## count. A number set two and a half times larger has to arc, jitter and drop
## two and a half times as far, or it reads as a big number sitting perfectly
## still.

const LIFETIME_MS := 640.0
const PUNCH_PEAK_MS := 96.0
const PUNCH_SETTLE_MS := 160.0
const RISE_MS := 480.0
const FADE_START_MS := 360.0

## Where the run starts, where the punch takes it, and where it settles.
const SCALE_FROM := 0.78
const SCALE_PEAK := 1.14
const SCALE_REST := 1.0

## How far a number climbs, in pixels.
const RISE_PX := 32.0

## A blow the player landed reads smaller than one they took: the second is the
## one that matters more.
const OUTGOING_SIZE := 64.0
const INCOMING_SIZE := 70.0
const CRITICAL_SCALE := 1.4

## How far above the drawn top of a body a number starts.
const RISE_ABOVE := 18.0

## How long the number knocks sideways for, the beat it changes direction on, how
## far it goes, and the fixed pattern it follows.
const SHAKE_MS := 72.0
const SHAKE_STEP_MS := 12.0
const SHAKE_PX := 2.0
const SHAKE_PATTERN := [0.0, 1.0, -0.75, 0.5, -0.35, 0.0]

## The beat between one digit arriving and the next. Time, so it does not scale.
const GLYPH_STAGGER_MS := 26.0
## How long a digit takes to fall from its arrival size to its resting one.
const GLYPH_SETTLE_MS := 120.0
## The size a digit arrives at. Bigger than rest, so it reads as thrown rather
## than typed.
const GLYPH_ARRIVAL_SCALE := 1.45
## Height of the shallow arc the digits of one number come to rest on, at its
## middle.
const GLYPH_ARC_SHARE := 0.25
## How far a digit may sit either side of that arc, so the row is never a ruled
## line.
const GLYPH_JITTER_SHARE := 0.15
## How far a digit falls into its place while it settles.
const GLYPH_DROP_SHARE := 0.3
## How much a digit's size may vary either side of the run's own.
const GLYPH_SIZE_VARIANCE := 0.1
## Space added between digit boxes.
##
## Positive, not negative. Tight tracking is what an arcade number looks like
## *without* an outline; with one, each digit is fattened by half the dark edge on
## every side, so packing them fuses those edges into a single dark mass and the
## digits stop being separable. The space pays for the edge.
const GLYPH_TRACKING_SHARE := 0.05
## A digit's advance as a share of the font size, when the renderer cannot measure
## the real one, and the same for the narrow marks a number can carry.
const GLYPH_NOMINAL_ADVANCE := 0.62
const NARROW_GLYPH_NOMINAL_ADVANCE := 0.34
const NARROW_GLYPHS := "!.,+-e"

## Numbers that land on the same creature within a few frames stack upward instead
## of drawing on top of each other, which is the column read of a multi-hit.
const STACK_WINDOW_MS := 300.0
const STACK_RADIUS_PX := 48.0
## Just under a full line. A burst reads as one flurry when its blows nearly
## touch — but a step shorter than the glyphs is a step that overlaps them, and two
## overlapping numbers are one unreadable one.
const STACK_STEP_SHARE := 0.95
const STACK_JITTER_SHARE := 0.15

## Thirty-two bits, which is the width the digit hash mixes in.
const MASK := 0xFFFFFFFF


## One number's state at `elapsed_ms`, or an empty dictionary once it is over.
##
## Returns `{shakeX, scale, riseY, alpha}`.
static func sample(elapsed_ms: float, event_id: int = 0, critical: bool = false) -> Dictionary:
	if elapsed_ms < 0.0 or elapsed_ms >= LIFETIME_MS:
		return {}
	# A critical goes further as well as bigger, in both the knock and the climb:
	# the emphasis is the one number that says this blow was not an ordinary one.
	var emphasis := CRITICAL_SCALE if critical else 1.0
	return {
		"shakeX": shake_x(event_id, elapsed_ms) * emphasis,
		"scale": _punch(elapsed_ms),
		"riseY": (
			-RISE_PX
			* FamilyParticles.ease_out_cubic(minf(1.0, elapsed_ms / RISE_MS))
			* emphasis
		),
		"alpha": (
			1.0
			if elapsed_ms < FADE_START_MS
			else 1.0 - (elapsed_ms - FADE_START_MS) / (LIFETIME_MS - FADE_START_MS)
		),
	}


## The size a number is drawn at, before its own punch.
static func size_for(incoming: bool, critical: bool) -> float:
	var base := INCOMING_SIZE if incoming else OUTGOING_SIZE
	return base * (CRITICAL_SCALE if critical else 1.0)


## What a number says. The mark on a critical is deliberately the half of the
## read that survives colour-blindness and a thumbnail.
static func text_for(amount: int, critical: bool) -> String:
	return "%d!" % amount if critical else str(amount)


## Deterministic, bounded horizontal shake; it never touches a camera or an actor.
##
## A blow that lands should knock its own number sideways for a few frames. The
## pattern is a fixed table read from a phase the event id picks, rather than a
## draw, for the reason every motion in this file is sampled: the same blow has to
## shake the same way in ordinary play and in a fixed-frame capture.
static func shake_x(event_id: int, elapsed_ms: float) -> float:
	if elapsed_ms < 0.0 or elapsed_ms >= SHAKE_MS:
		return 0.0
	var step := int(floor(elapsed_ms / SHAKE_STEP_MS))
	var phase := absi(event_id) % SHAKE_PATTERN.size()
	return (
		float(SHAKE_PATTERN[(phase + step) % SHAKE_PATTERN.size()])
		* SHAKE_PX
		* (1.0 - elapsed_ms / SHAKE_MS)
	)


## Deterministic per-digit noise in [-1, 1).
##
## A hash rather than a random draw, for the same reason: the same blow displaces
## its digits the same way every time it is drawn.
static func glyph_noise(event_id: int, index: int, channel: int) -> int:
	var value := (
		(absi(event_id) * 0x9e3779b1 + index * 0x85ebca77 + channel * 0xc2b2ae3d) & MASK
	)
	value = ((value ^ (value >> 15)) * (value | 1)) & MASK
	value = (value + ((value ^ (value >> 7)) * (value | 61))) & MASK
	return (value ^ (value >> 14)) & MASK


static func _noise_unit(event_id: int, index: int, channel: int) -> float:
	return float(glyph_noise(event_id, index, channel)) / 2147483648.0 - 1.0


## Lay a run of glyphs out around its own centre.
##
## Separate from the sampler below, because *where* a digit sits along the row is a
## question about the glyphs the font actually drew, while *how* it arrives is a
## question about time. The caller supplies real advance widths when it can
## measure them and nominal ones when it cannot; either way the row is centred, so
## a number never drifts sideways as it grows a digit.
static func glyph_layout(advances: PackedFloat64Array, tracking_px: float) -> PackedFloat64Array:
	var centres := PackedFloat64Array()
	if advances.is_empty():
		return centres
	var total := tracking_px * float(advances.size() - 1)
	for advance: float in advances:
		total += advance
	var cursor := -total / 2.0
	for advance: float in advances:
		centres.append(cursor + advance / 2.0)
		cursor += advance + tracking_px
	return centres


## The advance to lay a character out on when the renderer reports no usable width.
static func nominal_glyph_advance(font_size_px: float, character: String) -> float:
	var share := (
		NARROW_GLYPH_NOMINAL_ADVANCE
		if NARROW_GLYPHS.contains(character)
		else GLYPH_NOMINAL_ADVANCE
	)
	return font_size_px * share


## One digit of a number, at `elapsed_ms` into the run it belongs to.
##
## Everything here is relative to the run: the caller places the number with
## `sample` and then displaces each digit by this. A digit is invisible until its
## turn, arrives oversized and high, and falls into a resting place that is a
## shallow arc plus its own fixed jitter.
##
## Returns `{offsetX, offsetY, scale, alpha}` — the first two in pixels from the
## run's own anchor, the last two multipliers on the run's. An empty dictionary is
## the refusal for an index outside its own run, which is a caller's mistake rather
## than a state a number can be in.
static func glyph_sample(
	event_id: int,
	index: int,
	count: int,
	centre_offset_x: float,
	glyph_size_px: float,
	elapsed_ms: float
) -> Dictionary:
	if count <= 0 or index < 0 or index >= count:
		return {}
	var local_ms := maxf(0.0, elapsed_ms) - float(index) * GLYPH_STAGGER_MS
	var arc := (
		-glyph_size_px
		* GLYPH_ARC_SHARE
		* sin(PI * (float(index) + 0.5) / float(count))
	)
	var jitter := _noise_unit(event_id, index, 1) * glyph_size_px * GLYPH_JITTER_SHARE
	var variance := 1.0 + _noise_unit(event_id, index, 2) * GLYPH_SIZE_VARIANCE
	var settle := FamilyParticles.ease_out_cubic(
		clampf(local_ms / GLYPH_SETTLE_MS, 0.0, 1.0)
	)
	return {
		"offsetX": centre_offset_x,
		"offsetY": arc + jitter - glyph_size_px * GLYPH_DROP_SHARE * (1.0 - settle),
		"scale": lerpf(GLYPH_ARRIVAL_SCALE, 1.0, settle) * variance,
		"alpha": 0.0 if local_ms < 0.0 else 1.0,
	}


## Where a new number goes relative to where it was asked for, given the numbers
## already up.
##
## Counts the live peers shown within the stack window at nearly the same place —
## measured at their *unstacked* anchors, so a column does not drift as it grows —
## and lifts the new one by a step per peer, with a small sideways jitter from its
## own id so a straight column still reads as separate blows. The offset is decided
## once when the number is shown and folded into its anchor, so the rise and the
## fade never have to know. `peers` is an array of `{x, y, startedMs}`.
static func stack_offset(
	peers: Array, event_id: int, x: float, y: float, now_ms: float, glyph_size_px: float
) -> Dictionary:
	var count := 0
	for entry: Variant in peers:
		var peer: Dictionary = entry
		if now_ms - float(peer["startedMs"]) > STACK_WINDOW_MS:
			continue
		if absf(float(peer["x"]) - x) > STACK_RADIUS_PX:
			continue
		if absf(float(peer["y"]) - y) > STACK_RADIUS_PX:
			continue
		count += 1
	if count == 0:
		return {"x": 0.0, "y": 0.0}
	var jitter := float((absi(event_id) * 7) % 3 - 1)
	return {
		"x": jitter * glyph_size_px * STACK_JITTER_SHARE,
		"y": -glyph_size_px * STACK_STEP_SHARE * float(count),
	}


## Up fast, then back: the punch is what makes a number land rather than appear.
static func _punch(elapsed_ms: float) -> float:
	if elapsed_ms <= PUNCH_PEAK_MS:
		return SCALE_FROM + (SCALE_PEAK - SCALE_FROM) * FamilyParticles.ease_out_cubic(
			elapsed_ms / PUNCH_PEAK_MS
		)
	if elapsed_ms >= PUNCH_SETTLE_MS:
		return SCALE_REST
	return SCALE_PEAK + (SCALE_REST - SCALE_PEAK) * (
		(elapsed_ms - PUNCH_PEAK_MS) / (PUNCH_SETTLE_MS - PUNCH_PEAK_MS)
	)
