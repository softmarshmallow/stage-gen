class_name RoomLayout
extends RefCounted

## Where every rectangle a room draws goes, as a pure function of its frame and
## its published panel art.
##
## A port of `web/lib/pointclick/room-hud.ts` and the `text-plate` half of
## `web/lib/families/ui/text-plate.ts`, **corrected**. Both were already free of
## the browser's engine for the same reason they are free of this one: "which
## rectangle" and "which verb did that press mean" are decisions a headless test
## can hold to account, and a layout measured off whatever the view happened to
## build is a layout nothing can check.
##
## The HUD gets its own band *under* the room rather than floating over it. A
## room authors hotspot regions across its whole frame — the window room hides a
## torn piece low and to the right — so a panel drawn on top eventually covers
## something the player has to be able to click. The canvas is therefore taller
## than the authored frame by exactly the band.
##
## **What is corrected, and why.** The browser's constants were authored when the
## HUD was drawn rectangles with no border. The panels then became generated
## nine-slice art whose corners eat `insets / draw_scale` on every side — 48
## screen pixels in every package published so far — and nothing was
## re-measured. Three visible faults follow from that one cause: the narration
## plate is 156 px tall and its interior is 52, so the window room's 516-character
## line renders *past the plate onto the backdrop*; the control hint is placed on
## the bar panel's interior, which is inside inventory slot 0; and a 132x60 verb
## button has a 55x10 interior, so its glyph draws at ten pixels.
##
## So the sizes here are **interiors**, and the outer rectangle is the interior
## plus the package's own insets. That is self-correcting for any package's art
## rather than true for the one it was measured against.
##
## A rectangle here is `{x, y, width, height}` and a point is `{x, y}`. Not a
## `Vector2`: this file is simulation, the deny-list is why, and the host turns
## these into engine types at the one place it draws them.

## Gap between the HUD and the canvas edges, in design pixels.
const HUD_MARGIN := 24.0

const HUD_GAP := 12.0

## What the narration plate must hold *inside its art*.
##
## Measured rather than chosen: the longest sentence either shipped room can
## produce on one click is 516 characters (`the-grain-window-a4`, the interaction
## on `bell_booth`), and the widest plate a 1280-wide room gives is 1136 px of
## interior. At the step-down ladder's floor that is four wrapped lines; this
## holds five with room to spare, and the host clips to it so that a package with
## a longer line loses the tail inside the plate rather than painting it across
## the picture.
const NARRATION_INTERIOR := 168.0

## What the control bar must hold inside its art: the hint band, then the slots.
const HUD_LABEL_BAND := 26.0
const INVENTORY_SLOT_SIZE := 84.0
const INVENTORY_SLOT_GAP := 14.0
const BAR_INTERIOR := HUD_LABEL_BAND + INVENTORY_SLOT_SIZE

## What a verb control must hold inside its art. The browser asked for a 132x60
## button and got a 55x10 interior out of it; this asks for the interior and lets
## the art decide how big the button has to be to give it.
const VERB_INTERIOR_WIDTH := 118.0
const VERB_INTERIOR_HEIGHT := 40.0

## How long a press must be held, with no second button, to mean "look at it".
const LONG_PRESS_MS := 420.0

## The narration plate's asymmetric inner padding. The room's, not the family's:
## a conversation box uses the same plate with different numbers in it.
const TEXT_PADDING_X := 6.0
const TEXT_PADDING_Y := 4.0

const MODE_ACT := "act"
const MODE_LOOK := "look"


## Every rectangle the room draws, from the scene frame and the screen-space
## insets of the two sheets it draws with.
##
## `scene` is `{width, height}`, the authored frame. `panel_insets` and
## `button_insets` are `{left, top, right, bottom}` **already divided by the
## sheet's `draw_scale`**, because that division is the host's reading of the
## document and this is arithmetic on screen pixels.
static func of(scene: Dictionary, panel_insets: Dictionary, button_insets: Dictionary) -> Dictionary:
	var width := float(scene["width"])
	var height := float(scene["height"])
	var panel_y := _side(panel_insets, "top") + _side(panel_insets, "bottom")
	var narration_height := NARRATION_INTERIOR + panel_y
	var bar_height := BAR_INTERIOR + panel_y

	var narration := {
		"x": HUD_MARGIN,
		"y": height + HUD_GAP,
		"width": width - HUD_MARGIN * 2.0,
		"height": narration_height,
	}
	var bar := {
		"x": 0.0,
		"y": height + HUD_GAP + narration_height + HUD_GAP,
		"width": width,
		"height": bar_height,
	}
	var bar_interior_y := float(bar["y"]) + _side(panel_insets, "top")

	var verb_width := VERB_INTERIOR_WIDTH + _side(button_insets, "left") + _side(button_insets, "right")
	var verb_height := VERB_INTERIOR_HEIGHT + _side(button_insets, "top") + _side(button_insets, "bottom")
	var verb_y := bar_interior_y + (BAR_INTERIOR - verb_height) / 2.0
	var right := width - HUD_MARGIN
	var verbs := {
		"hint": _verb_rect(right, verb_y, 0, verb_width, verb_height),
		"look": _verb_rect(right, verb_y, 1, verb_width, verb_height),
		"act": _verb_rect(right, verb_y, 2, verb_width, verb_height),
	}

	# The hint gets its own row above the slots. The line changes with the game —
	# it says what a tap does until something is held, then what the held thing is
	# for — so it needs a row rather than whatever space the inventory leaves.
	var hint := {"x": HUD_MARGIN, "y": bar_interior_y}
	var slot_y := bar_interior_y + HUD_LABEL_BAND
	var available := float((verbs["act"] as Dictionary)["x"]) - HUD_GAP - HUD_MARGIN
	var capacity := maxi(
		0, int(floorf((available + INVENTORY_SLOT_GAP) / (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GAP)))
	)
	var slots: Array = []
	for index in capacity:
		slots.append(
			{
				"x": HUD_MARGIN + index * (INVENTORY_SLOT_SIZE + INVENTORY_SLOT_GAP),
				"y": slot_y,
				"width": INVENTORY_SLOT_SIZE,
				"height": INVENTORY_SLOT_SIZE,
			}
		)

	# The end card, centred on the room rather than on the whole canvas, and sized
	# so that its own interior can hold the win sentence.
	var win_width := minf(width - HUD_MARGIN * 4.0, 720.0)
	var win_height := 220.0 + panel_y
	return {
		"canvas": {
			"width": width,
			"height": float(bar["y"]) + bar_height,
		},
		"room": {"x": 0.0, "y": 0.0, "width": width, "height": height},
		"narration": narration,
		"bar": bar,
		"hint": hint,
		"slots": slots,
		"capacity": capacity,
		"verbs": verbs,
		"win": {
			"x": (width - win_width) / 2.0,
			"y": (height - win_height) / 2.0,
			"width": win_width,
			"height": win_height,
		},
	}


## A hotspot's normalised region in design pixels. The document publishes
## fractions of the authored frame, so a room re-drawn at another size keeps its
## hotspots on the things they name.
static func hotspot_rect(scene: Dictionary, region: Variant) -> Dictionary:
	var box: Dictionary = region if region is Dictionary else {}
	return {
		"x": float(box.get("x", 0.0)) * float(scene["width"]),
		"y": float(box.get("y", 0.0)) * float(scene["height"]),
		"width": float(box.get("w", 0.0)) * float(scene["width"]),
		"height": float(box.get("h", 0.0)) * float(scene["height"]),
	}


## Which verb one press meant.
##
## Total by construction, because the alternative is a room that cannot be
## inspected on a phone: touch has no secondary button, so the long press and
## the mode toggle are the only two ways in, and both have to work whatever the
## other is doing.
static func resolve_verb(mode: String, secondary: bool, held_ms: float) -> String:
	if secondary or held_ms >= LONG_PRESS_MS:
		return "inspect"
	return "inspect" if mode == MODE_LOOK else "use"


## Divide a frame's safe rect into a portrait slot and a text column.
##
## The `ui` family's text plate. A caller that draws no portrait and no speaker
## still gets both back and ignores them, rather than the port growing two
## nullable halves every consumer then has to test. What it does not get is a
## plate that does not fit: a safe rect too small for the slots it was asked for
## is refused rather than laid out into negative widths, because a panel whose
## art cannot hold its words is a producer's problem and a silent clamp would
## hide it.
##
## `knobs` carries `portrait_slot_width`, `column_gap`, `name_row_height`,
## `row_gap`, `padding_x`, `padding_y`.
static func text_plate_layout(safe: Dictionary, knobs: Dictionary) -> Variant:
	var padding_x := float(knobs.get("padding_x", 0.0))
	var padding_y := float(knobs.get("padding_y", 0.0))
	var portrait_slot_width := float(knobs.get("portrait_slot_width", 0.0))
	var column_gap := float(knobs.get("column_gap", 0.0))
	var name_row_height := float(knobs.get("name_row_height", 0.0))
	var row_gap := float(knobs.get("row_gap", 0.0))
	var inner_x := float(safe["x"]) + padding_x
	var inner_y := float(safe["y"]) + padding_y
	var inner_width := float(safe["width"]) - 2.0 * padding_x
	var inner_height := float(safe["height"]) - 2.0 * padding_y
	if inner_width <= portrait_slot_width + column_gap or inner_height <= name_row_height:
		return KernelRefusal.of(
			"room/text-plate",
			(
				"a %.0fx%.0f safe rect is too small for the plate it was asked for; this "
				+ "package's panel art cannot hold its words"
			) % [float(safe["width"]), float(safe["height"])]
		)
	var text_x := inner_x + portrait_slot_width + column_gap
	return {
		"portrait": {
			"centerX": inner_x + portrait_slot_width / 2.0,
			"bottomY": inner_y + inner_height,
			"height": inner_height,
		},
		"name": {"x": text_x, "y": inner_y},
		"text": {
			"x": text_x,
			"y": inner_y + name_row_height + row_gap,
			"wrapWidth": maxf(1.0, inner_width - portrait_slot_width - column_gap),
			"height": maxf(1.0, inner_height - name_row_height - row_gap),
		},
	}


## Where narration text sits inside a generated panel: the plate with the
## portrait slot and the speaker row set to zero, which is the whole of what
## makes a narration plate a different thing from a conversation box.
static func room_text_layout(safe: Dictionary) -> Variant:
	var laid: Variant = text_plate_layout(
		safe,
		{
			"portrait_slot_width": 0.0,
			"column_gap": 0.0,
			"name_row_height": 0.0,
			"row_gap": 0.0,
			"padding_x": TEXT_PADDING_X,
			"padding_y": TEXT_PADDING_Y,
		}
	)
	if KernelRefusal.is_refusal(laid):
		return laid
	return (laid as Dictionary)["text"]


static func _side(insets: Dictionary, name: String) -> float:
	return float(insets.get(name, 0.0))


static func _verb_rect(
	right: float, y: float, index_from_right: int, width: float, height: float
) -> Dictionary:
	return {
		"x": right - (index_from_right + 1) * width - index_from_right * HUD_GAP,
		"y": y,
		"width": width,
		"height": height,
	}
