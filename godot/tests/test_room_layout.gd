extends RefCounted

## The room's rectangles, and the one claim its picture gate cannot make.
##
## `tools/room_shots_check.py` measures what is in the picture. What a picture
## cannot say is whether a sentence is *whole*: a paragraph cut cleanly between
## two lines looks exactly like a paragraph that ended there, and the sheet was
## shown to pass a build whose narration was truncated for that reason. So the
## fitting lives here, where it can be falsified, and the picture keeps the
## guard that the words are on the plate at all.
##
## The insets below are the two published rooms', already divided by the
## `draw_scale` the host divides by: `the-grain-window-a4` and
## `the-grain-motor-court-a4` both publish a `panel_frame` with 96px insets at
## `draw_scale` 2.

## `panel_frame`: 96 sheet pixels at draw_scale 2.
const PANEL_INSETS := {"left": 48.0, "top": 48.0, "right": 48.0, "bottom": 48.0}
## `button_rect` as `the-grain-window-a4` publishes it: 80/48/74/52 at scale 2.
const BUTTON_INSETS := {"left": 40.0, "top": 24.0, "right": 37.0, "bottom": 26.0}

const SCENE := {"width": 1280.0, "height": 720.0}

## The longest narration either shipped room produces on a single click is 516
## characters — `the-grain-window-a4`, the second reading of `mr_bell`. This
## stands in for it at the same length, so the assertion is about the arithmetic
## rather than about one game's prose.
const LONGEST := (
	"The keeper is perhaps sixty and has forgotten his cap. He is asked to say what happened "
	+ "when the man came downstairs, and he says the man came out of the lift with his sister, "
	+ "and that he gave him the carton because he needed both hands, and that she took the key "
	+ "from him at the door and went back up alone, and that he did not see either of them again "
	+ "until the bell rang in the receiving room and the whole floor went quiet at once."
)


func run(h: TestHarness) -> void:
	var layout := RoomLayout.of(SCENE, PANEL_INSETS, BUTTON_INSETS)
	_band(h, layout)
	_verbs(h, layout)
	_hotspots(h)
	_verb_rule(h)
	_fitting(h, layout)
	h.done()


func _band(h: TestHarness, layout: Dictionary) -> void:
	var canvas: Dictionary = layout["canvas"]
	h.assert_eq(float(canvas["width"]), 1280.0, "the canvas is as wide as the room")
	# 720 + 12 + (168 + 96) + 12 + (110 + 96).
	h.assert_eq(float(canvas["height"]), 1214.0, "and taller by exactly the HUD band")

	var narration: Dictionary = layout["narration"]
	h.assert_eq(float(narration["y"]), 732.0, "the narration plate opens below the room")
	h.assert_eq(
		float(narration["height"]),
		264.0,
		"and is its interior plus the art's own insets, not a fixed height"
	)
	var bar: Dictionary = layout["bar"]
	h.assert_eq(float(bar["y"]), 1008.0, "the control bar follows it")
	h.assert_eq(float(bar["height"]), 206.0, "and is sized the same way")
	h.assert_eq(
		float(bar["y"]) + float(bar["height"]),
		float(canvas["height"]),
		"and the band ends exactly at the canvas"
	)

	# The hint gets its own row inside the bar's art, above the slots. The
	# browser put it on the bar panel's own safe rect, which is inside slot 0:
	# with anything carried, the slot frame painted over the sentence.
	var hint: Dictionary = layout["hint"]
	var slots: Array = layout["slots"]
	h.assert_eq(float(hint["y"]), 1056.0, "the control hint sits at the bar's interior top")
	h.assert_true(not slots.is_empty(), "the bar reserves inventory slots")
	if not slots.is_empty():
		var first: Dictionary = slots[0]
		h.assert_eq(
			float(first["y"]),
			float(hint["y"]) + RoomLayout.HUD_LABEL_BAND,
			"and the first slot begins below the hint's row rather than under it"
		)
		h.assert_true(
			float(first["y"]) + float(first["height"])
				<= float(bar["y"]) + float(bar["height"]) - PANEL_INSETS["bottom"],
			"and the slot row ends inside the bar's own art"
		)


func _verbs(h: TestHarness, layout: Dictionary) -> void:
	var verbs: Dictionary = layout["verbs"]
	var act: Dictionary = verbs["act"]
	# The browser asked for a 132x60 button and the published sheet's insets left
	# it a 55x10 interior, so the glyph drew at ten pixels. The size is asked for
	# the other way round here: the interior is the constant and the art decides
	# how big the button has to be to give it.
	h.assert_eq(
		float(act["width"]),
		RoomLayout.VERB_INTERIOR_WIDTH + BUTTON_INSETS["left"] + BUTTON_INSETS["right"],
		"a verb button is its interior plus the button sheet's insets"
	)
	h.assert_eq(
		float(act["height"]),
		RoomLayout.VERB_INTERIOR_HEIGHT + BUTTON_INSETS["top"] + BUTTON_INSETS["bottom"],
		"in both directions"
	)
	h.assert_true(
		float(act["height"]) - BUTTON_INSETS["top"] - BUTTON_INSETS["bottom"] >= 40.0,
		"and its interior can hold a glyph a person can see"
	)
	var look: Dictionary = verbs["look"]
	var hint_button: Dictionary = verbs["hint"]
	h.assert_true(
		float(act["x"]) < float(look["x"]) and float(look["x"]) < float(hint_button["x"]),
		"the three verbs run left to right in the order the player reads them"
	)
	h.assert_eq(
		float(hint_button["x"]) + float(hint_button["width"]),
		1280.0 - RoomLayout.HUD_MARGIN,
		"and the row is right-aligned so the inventory grows towards it"
	)
	h.assert_true(
		float((layout["slots"] as Array)[layout["capacity"] - 1]["x"])
			+ RoomLayout.INVENTORY_SLOT_SIZE + RoomLayout.HUD_GAP <= float(act["x"]),
		"the last slot the bar admits stops before the verbs"
	)


func _hotspots(h: TestHarness) -> void:
	# A region is a fraction of the authored frame, so a room drawn at another
	# size keeps its hotspots on the things they name.
	var region := RoomLayout.hotspot_rect(SCENE, {"x": 0.5, "y": 0.25, "w": 0.1, "h": 0.5})
	h.assert_eq(float(region["x"]), 640.0, "a hotspot's x is a fraction of the frame")
	h.assert_eq(float(region["y"]), 180.0, "and so is its y")
	h.assert_eq(float(region["width"]), 128.0, "and its width")
	h.assert_eq(float(region["height"]), 360.0, "and its height")


func _verb_rule(h: TestHarness) -> void:
	# Total by construction: touch has no secondary button, so the long press and
	# the mode toggle are the only two ways to look at something.
	h.assert_eq(RoomLayout.resolve_verb("act", false, 0.0), "use", "a tap in Act mode acts")
	h.assert_eq(
		RoomLayout.resolve_verb("act", false, RoomLayout.LONG_PRESS_MS),
		"inspect",
		"a held tap looks, whatever the mode says"
	)
	h.assert_eq(
		RoomLayout.resolve_verb("act", true, 0.0), "inspect", "and so does a second button"
	)
	h.assert_eq(
		RoomLayout.resolve_verb("look", false, 0.0), "inspect", "a tap in Look mode looks"
	)


func _fitting(h: TestHarness, layout: Dictionary) -> void:
	var plate: Dictionary = layout["narration"]
	# The plate's own interior, as the host reads it: the published safe rect is
	# equal to the content rect in both shipped rooms, so the interior is the
	# outer rectangle less the insets.
	var safe := {
		"x": float(plate["x"]) + PANEL_INSETS["left"],
		"y": float(plate["y"]) + PANEL_INSETS["top"],
		"width": float(plate["width"]) - PANEL_INSETS["left"] - PANEL_INSETS["right"],
		"height": float(plate["height"]) - PANEL_INSETS["top"] - PANEL_INSETS["bottom"],
	}
	var box: Variant = RoomLayout.room_text_layout(safe)
	h.assert_true(not KernelRefusal.is_refusal(box), "the plate is big enough to lay words in")
	if KernelRefusal.is_refusal(box):
		return
	var text: Dictionary = box
	var font := ThemeDB.fallback_font
	h.assert_true(font != null, "the suite has a font to measure with")
	if font == null:
		return
	var wrap := float(text["wrapWidth"])
	var room_for := float(text["height"])
	var size := HostTextFit.fitted_size(font, LONGEST, wrap, room_for, HostRoomLeaf.NARRATION_SIZES, HostRoomLeaf.NARRATION_LINE_SPACING)
	h.assert_true(
		HostTextFit.wrapped_height(font, LONGEST, size, wrap, HostRoomLeaf.NARRATION_LINE_SPACING) <= room_for,
		"the longest sentence a shipped room can produce fits the plate it is written on"
	)
	h.assert_true(
		size >= int(HostRoomLeaf.NARRATION_SIZES[HostRoomLeaf.NARRATION_SIZES.size() - 1]),
		"and it fits at or above the ladder's floor rather than by clamping to it"
	)
	# The ladder is a ladder: a sentence too long for the top step comes down.
	var short_size := HostTextFit.fitted_size(font, "The Window", wrap, room_for, HostRoomLeaf.NARRATION_SIZES, HostRoomLeaf.NARRATION_LINE_SPACING)
	h.assert_eq(
		short_size,
		int(HostRoomLeaf.NARRATION_SIZES[0]),
		"a room's own name is written at the top of the ladder"
	)
	h.assert_true(
		size < short_size, "and a paragraph is written smaller than a name, not clipped"
	)
