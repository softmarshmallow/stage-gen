class_name PlatformerDefeatCard
extends Control

## What a defeated player is asked, on the panel and the button the run published
## art for.
##
## The state was whole and nothing drew it. `session/defeat` has always decided
## when the card is up, how far it has faded in, what the button says and which of
## the sheet's four states it is in — and the goldens hash every one of those, so
## six hundred exact frames of the defeat run said the feature worked while a
## player who died saw the body fall and then nothing at all.
##
## Screen space, over everything: a death screen is furniture, and it is the one
## piece of furniture that must not be scrolled away from.
##
## The frame and the button are `HostPanelFrame`'s, which is what makes them the
## right size. A block's insets are in *sheet* pixels and the sheet is laid out at
## `draw_scale` times the density it is drawn at, so reading them straight onto a
## `NinePatchRect` draws a hundred-and-twelve-pixel corner ornament a hundred and
## twelve screen pixels wide — and a card that is all corner. The shared widget
## lays the slices out at the sheet's own density and scales the whole thing back.
##
## The words are the world's rather than this file's. `buttonLabel` names where
## the run resumes — "Return to Bellweather", not a promise of "continue" — and it
## is written by the system that knows where home is.

## The card, in the 1280x720 the manifest publishes its rectangles in.
const CARD_WIDTH := 560.0
const CARD_HEIGHT := 260.0

## Same division as the browser's: a title row across the top of the interior and
## a centred button below it, both inside the frame's own padding. The button's
## size is what the interior allows rather than a number the art may not fit.
const PADDING := 28.0
const TITLE_ROW_HEIGHT := 60.0
const ROW_GAP := 18.0
const BUTTON_WIDTH := 380.0
const BUTTON_HEIGHT := 62.0

const TITLE_SIZE := 34
const LABEL_SIZE := 24
const TITLE_COLOR := Color(1.0, 0.867, 0.639)
const LABEL_COLOR := Color(0.976, 0.965, 0.945)
## Behind the card, so the world it is covering reads as stopped rather than as
## still going on underneath.
const VEIL_COLOR := Color(0.043, 0.035, 0.047, 0.72)

var _veil: ColorRect = null
var _frame: HostPanelFrame = null
var _button: HostPanelFrame = null
var _title: Label = null
var _label: Label = null


## Build from a run's `ui` block, or nothing when it publishes no panel frame.
##
## A card with no art is no card. Drawing a plain box instead would be worse than
## drawing nothing: a placeholder is a claim that the generated frame is not
## needed, and this panel is exactly the moment the generated frame is the point.
static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerDefeatCard:
	var sheets := HostUiSheets.of(package, manifest.get("ui", {}))
	var left := (PlatformerStage.VIEW_WIDTH - CARD_WIDTH) / 2.0
	var top := (PlatformerStage.VIEW_HEIGHT - CARD_HEIGHT) / 2.0
	var frame := HostPanelFrame.of(
		sheets, "panel_frame", {"x": left, "y": top, "width": CARD_WIDTH, "height": CARD_HEIGHT}
	)
	if frame == null:
		push_warning(
			"platformer host: this package publishes no ui.panel_frame, so a defeated player is shown nothing"
		)
		return null

	var made := PlatformerDefeatCard.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._veil = ColorRect.new()
	made._veil.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._veil.color = VEIL_COLOR
	made._veil.position = Vector2.ZERO
	made._veil.size = Vector2(PlatformerStage.VIEW_WIDTH, PlatformerStage.VIEW_HEIGHT)
	made.add_child(made._veil)
	made._frame = frame
	made.add_child(frame)

	# Same division as the browser's: a title row across the top of the interior
	# and a centred button below it, both inside the ornament's own curl. The
	# button's size is what the interior allows rather than a number the art may
	# not fit.
	var safe := frame.safe_rect()
	var safe_x := float(safe["x"])
	var safe_y := float(safe["y"])
	var safe_w := float(safe["width"])
	var safe_h := float(safe["height"])

	made._title = Label.new()
	made._title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._title.add_theme_font_size_override("font_size", TITLE_SIZE)
	made._title.add_theme_color_override("font_color", TITLE_COLOR)
	made._title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made._title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	made._title.position = Vector2(safe_x, safe_y)
	made._title.size = Vector2(safe_w, TITLE_ROW_HEIGHT)
	made.add_child(made._title)

	var button_w := minf(BUTTON_WIDTH, safe_w)
	var button_h := minf(BUTTON_HEIGHT, maxf(0.0, safe_h - TITLE_ROW_HEIGHT - ROW_GAP))
	var button_left := safe_x + (safe_w - button_w) / 2.0
	var button_top := safe_y + TITLE_ROW_HEIGHT + ROW_GAP
	made._button = HostPanelFrame.of(
		sheets,
		"button_rect",
		{"x": button_left, "y": button_top, "width": button_w, "height": button_h},
		"normal"
	)
	if made._button == null:
		push_warning(
			"platformer host: this package publishes no ui.button_rect, so the defeat card's button is words on the frame"
		)
	else:
		made.add_child(made._button)

	made._label = Label.new()
	made._label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._label.add_theme_font_size_override("font_size", LABEL_SIZE)
	made._label.add_theme_color_override("font_color", LABEL_COLOR)
	made._label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made._label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	made._label.position = Vector2(button_left, button_top)
	made._label.size = Vector2(button_w, button_h)
	made.add_child(made._label)

	made.visible = false
	return made


## Show the card if the run says it is up, at the alpha it says.
##
## Nothing here decides *whether* a player has been defeated or *when* the card
## arrives. Both are `session/defeat`'s, sampled from the world's own clock, so a
## replay and ordinary play raise the card on the same frame.
func sync(world: PlatformerWorld, now_ms: float) -> void:
	if not bool(world.player.get("defeated", false)) or world.defeated_at_ms == null:
		visible = false
		return
	var prompt := FamilyDefeatPrompt.prompt_state(
		float(world.defeated_at_ms),
		now_ms,
		PlatformerSessionSystem.PROMPT_DELAY_MS,
		PlatformerSessionSystem.PROMPT_FADE_MS
	)
	if not bool(prompt["visible"]):
		visible = false
		return
	visible = true
	modulate.a = float(prompt["alpha"])
	_title.text = str(world.defeat_panel.get("title", ""))
	_label.text = str(world.defeat_panel.get("buttonLabel", ""))
	if _button == null:
		return
	# The state is the world's word, and the sheet was drawn with four of them, so
	# a hover and a pressed look are the producer's own pixels rather than a tint.
	_button.set_frame_state(str(world.defeat_panel.get("buttonState", "normal")))
