class_name DialogueLayout
extends RefCounted

## Where a dialogue scene puts everything, as pure arithmetic.
##
## A port of the live half of `web/lib/dialogue-scene/scene-hud.ts` and all of
## `emphasis.ts`. What is deliberately *not* here is the pre-nine-slice layout
## the browser kept beside it — a speaker chip straddling the panel edge, a fixed
## body inset, a progress point — every one of which has no consumer left. The
## words are laid out on the panel's own measured interior now.
##
## A rectangle is `{x, y, width, height}`. Nothing here rounds except the choice
## row, and that is deliberate: the cast's frames must agree with the
## single-actor framing they are derived from, and rounding them would put a
## centred actor half a pixel off the frame that defines centre.

## The design frame every published backdrop is drawn at.
const STAGE_WIDTH := 1672.0
const STAGE_HEIGHT := 941.0

const PANEL_MARGIN_X := 36.0
const PANEL_MARGIN_BOTTOM := 30.0

## What the conversation box must hold *inside its art*: a padding, a speaker's
## row, a gap, three wrapped lines of a line, and a padding.
##
## Measured rather than chosen. The longest line the six published scenarios
## carry is 288 characters — `e1_way_in` — which is three wrapped lines at the
## top of the body ladder in the 1484px the panel leaves. The browser asked for a
## 208px panel, whose interior under this sheet's 96px insets is 112, of which
## the speaker's row and the paddings take 48: sixty-four pixels, one line, and
## the other two rendered past the panel.
const PANEL_BODY_LINES := 3.0
const PANEL_INTERIOR := (
	BOX_PADDING_Y
	+ BOX_NAME_ROW_HEIGHT
	+ BOX_BODY_GAP
	+ 150.0
	+ BOX_PROGRESS_ROW_HEIGHT
	+ BOX_PADDING_Y
)

## A plate is fitted into this much of the frame before the placement scales it.
const SPRITE_HEIGHT_RATIO := 0.98
const SPRITE_MAX_WIDTH_RATIO := 0.66

## What standing at a far slot costs: a little smaller, and a little further down
## the frame, which is the whole of this genre's depth.
const SLOT_RECESSION_SCALE := 0.16
const SLOT_RECESSION_DROP := 0.35

const COMPLETE_CONTROL_WIDTH := 108.0
const COMPLETE_CONTROL_HEIGHT := 64.0
const COMPLETE_CONTROL_OFFSET_Y := 28.0
const COMPLETE_CARD_WIDTH := 760.0
const COMPLETE_CARD_HEIGHT := 240.0
const COMPLETE_CARD_MARGIN := 144.0

const CHOICE_HEIGHT := 84.0
const CHOICE_GAP := 18.0
const CHOICE_WIDTH_RATIO := 0.68
const CHOICE_TOP_FLOOR := 18.0

## Where each slot stands, as an offset in frame widths, and how far back it is.
## Five, left to right, exactly as `ScenarioProgram.SLOTS` publishes them.
const SLOT_OFFSET := {
	"far_left": -0.33,
	"left": -0.19,
	"center": 0.0,
	"right": 0.19,
	"far_right": 0.33,
}
const SLOT_RANK := {"far_left": 1, "left": 0, "center": 0, "right": 0, "far_right": 1}

## The speaker is drawn over everyone, then the near slots, then the far ones.
const SPEAKER_STACK_ORDER := 3
const SPEAKING_SCALE := 1.045
const LISTENER_ALPHA := 0.88
const FAR_LISTENER_ALPHA := 0.72
## A listener is cooled rather than dimmed alone, so a lit stage keeps its light.
const LISTENER_TINT := [183.0, 189.0, 208.0]
const FAR_LISTENER_TINT := [137.0, 144.0, 166.0]
## When nobody is speaking the whole cast is a listener, but a near one is not
## touched at all: narration is the scene looking at itself.
const NARRATION_FAR_ALPHA_LIFT := 0.08

## Inside the conversation box.
const BOX_PADDING_X := 10.0
const BOX_PADDING_Y := 6.0
const BOX_NAME_ROW_HEIGHT := 30.0
const BOX_BODY_GAP := 6.0
## The row the progress readout sits in, reserved so the line does not run under
## it. The browser declared this knob and never read it, and its readout printed
## over the tail of any line long enough to reach the bottom of the box.
const BOX_PROGRESS_ROW_HEIGHT := 20.0


static func stage_size() -> Dictionary:
	return {"width": STAGE_WIDTH, "height": STAGE_HEIGHT}


## The conversation panel across the bottom of the frame.
##
## `insets` are the panel sheet's own, already divided by its `draw_scale`. The
## height is the interior plus them, so a package with heavier border art gets a
## taller panel rather than a truncated line.
static func panel_rect(insets: Dictionary = {}) -> Dictionary:
	var height := (
		PANEL_INTERIOR + float(insets.get("top", 0.0)) + float(insets.get("bottom", 0.0))
	)
	return {
		"x": PANEL_MARGIN_X,
		"y": STAGE_HEIGHT - PANEL_MARGIN_BOTTOM - height,
		"width": STAGE_WIDTH - PANEL_MARGIN_X * 2.0,
		"height": height,
	}


## Where one plate stands when it is the only one on stage.
##
## Fitted into two thirds of the frame's width and almost all of its height,
## then scaled by the placement and hung from its top centre — because a plate is
## a head and shoulders in a tall canvas, and hanging it from the top is what
## keeps a face at the same height whatever the plate's own aspect is.
static func sprite_frame(source: Dictionary, placement: Dictionary) -> Dictionary:
	var width := float(source.get("width", 0.0))
	var height := float(source.get("height", 0.0))
	if width <= 0.0 or height <= 0.0:
		return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
	var factor := minf(
		STAGE_WIDTH * SPRITE_MAX_WIDTH_RATIO / width, STAGE_HEIGHT * SPRITE_HEIGHT_RATIO / height
	)
	var scaled_width := width * factor * float(placement["scale"])
	var scaled_height := height * factor * float(placement["scale"])
	return {
		"x": float(placement["xPercent"]) / 100.0 * STAGE_WIDTH - scaled_width / 2.0,
		"y": float(placement["yPercent"]) / 100.0 * STAGE_HEIGHT,
		"width": scaled_width,
		"height": scaled_height,
	}


## The same plate, moved to a slot and set back by its rank.
static func slot_frame(source: Dictionary, placement: Dictionary, slot: String) -> Dictionary:
	var centre := sprite_frame(source, placement)
	var rank := float(SLOT_RANK.get(slot, 0))
	var factor := 1.0 - rank * SLOT_RECESSION_SCALE
	var width := float(centre["width"]) * factor
	var height := float(centre["height"]) * factor
	var middle := (
		float(centre["x"]) + float(centre["width"]) / 2.0
		+ STAGE_WIDTH * float(SLOT_OFFSET.get(slot, 0.0))
	)
	return {
		"x": middle - width / 2.0,
		"y": float(centre["y"]) + (float(centre["height"]) - height) * SLOT_RECESSION_DROP,
		"width": width,
		"height": height,
	}


## A frame grown about its feet, which is how a speaker leans in without leaving
## the ground.
static func emphasized_frame(frame: Dictionary, scale: float) -> Dictionary:
	var width := float(frame["width"]) * scale
	var height := float(frame["height"]) * scale
	return {
		"x": float(frame["x"]) + float(frame["width"]) / 2.0 - width / 2.0,
		"y": float(frame["y"]) + float(frame["height"]) - height,
		"width": width,
		"height": height,
	}


static func slot_is_far(slot: String) -> bool:
	return int(SLOT_RANK.get(slot, 0)) == 1


## Who is drawn over whom: the far slots behind, then the near ones, then centre.
static func slot_stack_order(slot: String) -> int:
	if slot_is_far(slot):
		return 0
	return 2 if is_zero_approx(float(SLOT_OFFSET.get(slot, 0.0))) else 1


## How one actor is drawn while somebody is speaking.
## Returns `{alpha, tint, scale, stackOrder}`; `tint` is empty for none.
static func actor_emphasis(slot: String, speaking: bool) -> Dictionary:
	if speaking:
		return {
			"alpha": 1.0,
			"tint": [],
			"scale": SPEAKING_SCALE,
			"stackOrder": SPEAKER_STACK_ORDER,
		}
	var far := slot_is_far(slot)
	return {
		"alpha": FAR_LISTENER_ALPHA if far else LISTENER_ALPHA,
		"tint": FAR_LISTENER_TINT if far else LISTENER_TINT,
		"scale": 1.0,
		"stackOrder": slot_stack_order(slot),
	}


## How one actor is drawn while nobody is.
static func narration_emphasis(slot: String) -> Dictionary:
	var far := slot_is_far(slot)
	return {
		# Written as the addition rather than as 0.8, because that is what it is:
		# the far listener's alpha lifted by a hair, and the two are not the same
		# number in single precision.
		"alpha": (FAR_LISTENER_ALPHA + NARRATION_FAR_ALPHA_LIFT) if far else 1.0,
		"tint": FAR_LISTENER_TINT if far else [],
		"scale": 1.0,
		"stackOrder": slot_stack_order(slot),
	}


## The end card, centred on the frame.
static func complete_card_rect() -> Dictionary:
	var width := minf(COMPLETE_CARD_WIDTH, STAGE_WIDTH - COMPLETE_CARD_MARGIN)
	return {
		"x": (STAGE_WIDTH - width) / 2.0,
		"y": (STAGE_HEIGHT - COMPLETE_CARD_HEIGHT) / 2.0,
		"width": width,
		"height": COMPLETE_CARD_HEIGHT,
	}


static func complete_control_rect(card: Dictionary) -> Dictionary:
	return {
		"x": float(card["x"]) + (float(card["width"]) - COMPLETE_CONTROL_WIDTH) / 2.0,
		"y": float(card["y"]) + float(card["height"]) / 2.0 + COMPLETE_CONTROL_OFFSET_Y,
		"width": COMPLETE_CONTROL_WIDTH,
		"height": COMPLETE_CONTROL_HEIGHT,
	}


## The choice row, centred in the space above the panel.
##
## The one place this genre rounds, and it rounds the way the browser's
## `Math.round` does — half away from zero, which `roundf` matches for every
## positive value these produce.
static func choice_rects(count: int, insets: Dictionary = {}) -> Array:
	if count < 1:
		return []
	var width := roundf(STAGE_WIDTH * CHOICE_WIDTH_RATIO)
	var x := roundf((STAGE_WIDTH - width) / 2.0)
	var block := float(count) * CHOICE_HEIGHT + float(count - 1) * CHOICE_GAP
	var available := float(panel_rect(insets)["y"])
	var top := maxf(roundf((available - block) / 2.0), CHOICE_TOP_FLOOR)
	var rects: Array = []
	for index in count:
		rects.append(
			{
				"x": x,
				"y": top + float(index) * (CHOICE_HEIGHT + CHOICE_GAP),
				"width": width,
				"height": CHOICE_HEIGHT,
			}
		)
	return rects


## Words inside the conversation box: a speaker's row, the line under it, and a
## progress readout in the far corner.
##
## Returns `{name, body, bodyWrapWidth, progress}` where `progress` is drawn from
## its bottom-right rather than its top-left.
static func box_layout(safe: Dictionary) -> Variant:
	var left := float(safe["x"]) + BOX_PADDING_X
	var top := float(safe["y"]) + BOX_PADDING_Y
	var right := float(safe["x"]) + float(safe["width"]) - BOX_PADDING_X
	var bottom := float(safe["y"]) + float(safe["height"]) - BOX_PADDING_Y
	if right <= left or bottom <= top + BOX_NAME_ROW_HEIGHT + BOX_PROGRESS_ROW_HEIGHT:
		return KernelRefusal.of(
			"dialogue/box",
			"this package's panel art leaves no room for a speaker and a line",
			"ui.panel_frame"
		)
	return {
		"name": {"x": left, "y": top},
		"body": {"x": left, "y": top + BOX_NAME_ROW_HEIGHT + BOX_BODY_GAP},
		"bodyWrapWidth": maxf(1.0, right - left),
		# The body stops above the readout's row rather than sharing it.
		"bodyHeight": maxf(
			1.0,
			bottom - BOX_PROGRESS_ROW_HEIGHT - (top + BOX_NAME_ROW_HEIGHT + BOX_BODY_GAP)
		),
		"progress": {"x": right, "y": bottom},
	}
