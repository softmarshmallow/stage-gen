extends RefCounted

const ScenarioProgram = preload("res://addons/scenario_runtime/program.gd")

## The dialogue scene's arithmetic: its framing, its slots and its box.
##
## The scenario runtime this scene plays is already exact against the browser
## for twenty-six actions. What that proof cannot reach is where a portrait
## stands, how big it is drawn, and whether the line fits the panel — and the
## first of those is the one number in this genre that a picture gate can only
## catch by its consequences.

## The two zooms every published run carries. A scene drawn at 70 and played at
## 70 is drawn at its own size and nothing else.
const PLAYED := 70.0
const DRAWN := 70.0

## `panel_frame` as both published runs carry it: 96 sheet pixels at draw_scale 2.
const PANEL_INSETS := {"left": 48.0, "top": 48.0, "right": 48.0, "bottom": 48.0}

## Every published plate is this, and every backdrop is the design frame.
const PLATE := {"width": 1024.0, "height": 1536.0}

## The longest line the six published scenarios carry is 288 characters, in
## `e1_way_in`. This stands in for it at the same length.
const LONGEST := (
	"He considers the coat, the shoes, the hands and the expression, and none of it is an "
	+ "inspection; it is seating preparation, the kind a man does at a door he has stood at for "
	+ "thirty years, and by the time he has finished he knows which chair the visitor will be "
	+ "given and which one he will not."
)


func run(h: TestHarness) -> void:
	_framing(h)
	_slots(h)
	_emphasis(h)
	_panel(h)
	_choices(h)
	h.done()


func _framing(h: TestHarness) -> void:
	# The three numbers the browser's own tests pin, reproduced exactly.
	var mapped := DialogueFraming.map_zoom(PLAYED)
	h.assert_near(float(mapped["scale"]), 3.244, 1e-9, "zoom 70 maps to a scale of 3.244")
	h.assert_near(float(mapped["xPercent"]), 58.0, 1e-9, "and an anchor 58% across")
	h.assert_near(float(mapped["yPercent"]), 5.6, 1e-9, "and 5.6% down")

	# **The number this whole genre turns on.** The scale is a ratio against the
	# zoom the plates were painted at, never the raw one: used raw, every
	# portrait is drawn 3.244 times too large and the cast fills the frame.
	var placement: Variant = DialogueFraming.placement(PLAYED, DRAWN)
	h.assert_true(not KernelRefusal.is_refusal(placement), "a scene played at its own zoom places")
	if KernelRefusal.is_refusal(placement):
		return
	h.assert_near(
		float((placement as Dictionary)["scale"]),
		1.0,
		1e-9,
		"a scene drawn at 70 and played at 70 draws its cast at exactly its own size"
	)
	h.assert_near(
		float((DialogueFraming.placement(25.0, DRAWN) as Dictionary)["scale"]),
		0.308,
		1e-9,
		"pulled back to a full shot it is 0.308 of that"
	)
	h.assert_near(
		float((DialogueFraming.placement(85.0, DRAWN) as Dictionary)["scale"]),
		1.37,
		1e-9,
		"and pushed to a close-up, 1.37"
	)
	# Outside the band the tiers were measured in, a zoom is clamped rather than
	# extrapolated into a scale nobody has evidence for.
	h.assert_true(bool(DialogueFraming.map_zoom(5.0)["saturated"]), "a zoom below the evidence saturates")
	h.assert_true(bool(DialogueFraming.map_zoom(99.0)["saturated"]), "and so does one above it")


func _slots(h: TestHarness) -> void:
	var placement: Dictionary = DialogueFraming.placement(PLAYED, DRAWN)
	var centre := DialogueLayout.slot_frame(PLATE, placement, "center")
	h.assert_near(float(centre["width"]), 614.787, 0.01, "a centred plate is 614.8 wide")
	h.assert_near(float(centre["height"]), 922.180, 0.01, "and 922.2 tall")
	h.assert_near(float(centre["x"]), 662.367, 0.01, "and stands at 662.4")
	h.assert_near(float(centre["y"]), 52.696, 0.01, "hung from 52.7 down the frame")

	# Five slots, and the two at the ends are set back rather than merely moved.
	var far_left := DialogueLayout.slot_frame(PLATE, placement, "far_left")
	var left := DialogueLayout.slot_frame(PLATE, placement, "left")
	var right := DialogueLayout.slot_frame(PLATE, placement, "right")
	var far_right := DialogueLayout.slot_frame(PLATE, placement, "far_right")
	h.assert_true(
		float(far_left["x"]) < float(left["x"])
			and float(left["x"]) < float(centre["x"])
			and float(centre["x"]) < float(right["x"])
			and float(right["x"]) < float(far_right["x"]),
		"the five slots run left to right in the order the document publishes them"
	)
	h.assert_true(
		float(far_left["width"]) < float(left["width"]),
		"a far slot is drawn smaller than a near one"
	)
	h.assert_true(
		float(far_left["y"]) > float(left["y"]), "and lower down, which is this genre's depth"
	)
	h.assert_eq(
		ScenarioProgram.SLOTS.size(),
		5,
		"and the program publishes exactly those five"
	)

	# A speaker leans in about its feet, so the ground it stands on does not move.
	var leaned := DialogueLayout.emphasized_frame(centre, DialogueLayout.SPEAKING_SCALE)
	h.assert_near(
		float(leaned["y"]) + float(leaned["height"]),
		float(centre["y"]) + float(centre["height"]),
		1e-3,
		"emphasis grows a portrait about its feet, not its head"
	)
	h.assert_true(float(leaned["height"]) > float(centre["height"]), "and grows it")


func _emphasis(h: TestHarness) -> void:
	var speaking := DialogueLayout.actor_emphasis("center", true)
	var listening := DialogueLayout.actor_emphasis("center", false)
	h.assert_near(float(speaking["alpha"]), 1.0, 1e-9, "a speaker is drawn at full")
	h.assert_true((speaking["tint"] as Array).is_empty(), "and untinted")
	h.assert_true(float(listening["alpha"]) < 1.0, "a listener is drawn back")
	h.assert_true(not (listening["tint"] as Array).is_empty(), "and cooled")
	h.assert_true(
		int(speaking["stackOrder"]) > int(listening["stackOrder"]),
		"and the speaker is drawn over everyone"
	)
	var far := DialogueLayout.actor_emphasis("far_left", false)
	h.assert_true(
		float(far["alpha"]) < float(listening["alpha"]), "a far listener is further back still"
	)
	# When nobody is speaking the whole cast is a listener, but a near one is not
	# touched at all: narration is the scene looking at itself.
	h.assert_near(
		float(DialogueLayout.narration_emphasis("center")["alpha"]),
		1.0,
		1e-9,
		"narration leaves a near actor alone"
	)
	h.assert_near(
		float(DialogueLayout.narration_emphasis("far_left")["alpha"]),
		DialogueLayout.FAR_LISTENER_ALPHA + DialogueLayout.NARRATION_FAR_ALPHA_LIFT,
		1e-9,
		"and lifts a far one by a hair rather than to a round number"
	)


func _panel(h: TestHarness) -> void:
	var panel := DialogueLayout.panel_rect(PANEL_INSETS)
	h.assert_eq(
		float(panel["height"]),
		DialogueLayout.PANEL_INTERIOR + 96.0,
		"the panel is its interior plus the sheet's own insets"
	)
	h.assert_eq(
		float(panel["y"]) + float(panel["height"]),
		DialogueLayout.STAGE_HEIGHT - DialogueLayout.PANEL_MARGIN_BOTTOM,
		"and sits on the frame's bottom margin however tall that makes it"
	)
	var safe := {
		"x": float(panel["x"]) + PANEL_INSETS["left"],
		"y": float(panel["y"]) + PANEL_INSETS["top"],
		"width": float(panel["width"]) - PANEL_INSETS["left"] - PANEL_INSETS["right"],
		"height": float(panel["height"]) - PANEL_INSETS["top"] - PANEL_INSETS["bottom"],
	}
	var box: Variant = DialogueLayout.box_layout(safe)
	h.assert_true(not KernelRefusal.is_refusal(box), "and leaves room for a speaker and a line")
	if KernelRefusal.is_refusal(box):
		return
	var laid: Dictionary = box

	# The claim the picture gate cannot make: a line cut cleanly between two
	# wrapped lines looks exactly like a line that ended there.
	var font := ThemeDB.fallback_font
	h.assert_true(font != null, "the suite has a font to measure with")
	if font == null:
		return
	var wrap := float(laid["bodyWrapWidth"])
	var room_for := float(laid["bodyHeight"])
	var size := HostTextFit.fitted_size(
		font,
		LONGEST,
		wrap,
		room_for,
		HostDialogueLeaf.BODY_SIZES,
		HostDialogueLeaf.BODY_LINE_SPACING
	)
	h.assert_true(
		HostTextFit.wrapped_height(font, LONGEST, size, wrap, HostDialogueLeaf.BODY_LINE_SPACING)
			<= room_for,
		"the longest line a published scenario carries fits the box it is written in"
	)
	h.assert_eq(
		size,
		int(HostDialogueLeaf.BODY_SIZES[0]),
		"and fits it at the top of the ladder rather than by shrinking"
	)


func _choices(h: TestHarness) -> void:
	h.assert_true(DialogueLayout.choice_rects(0, PANEL_INSETS).is_empty(), "no options, no row")
	var three := DialogueLayout.choice_rects(3, PANEL_INSETS)
	h.assert_eq(three.size(), 3, "three options, three buttons")
	var first: Dictionary = three[0]
	var second: Dictionary = three[1]
	h.assert_eq(float(first["width"]), 1137.0, "a choice is 1137 wide")
	h.assert_eq(float(first["x"]), 268.0, "centred at 268")
	h.assert_eq(
		float(second["y"]) - float(first["y"]),
		DialogueLayout.CHOICE_HEIGHT + DialogueLayout.CHOICE_GAP,
		"and the row is evenly spaced"
	)
	# The row is centred above the panel, so a longer list opens higher rather
	# than running under the conversation box.
	var panel := DialogueLayout.panel_rect(PANEL_INSETS)
	var five := DialogueLayout.choice_rects(5, PANEL_INSETS)
	h.assert_true(
		float((five[0] as Dictionary)["y"]) < float(first["y"]),
		"five options open higher than three"
	)
	var last: Dictionary = five[4]
	h.assert_true(
		float(last["y"]) + float(last["height"]) <= float(panel["y"]),
		"and the last of them still stops above the panel"
	)
