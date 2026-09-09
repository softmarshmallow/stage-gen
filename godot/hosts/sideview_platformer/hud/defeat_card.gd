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
var _frame: NinePatchRect = null
var _button: NinePatchRect = null
var _title: Label = null
var _label: Label = null
## The sheet's four states, by name, as regions into one texture.
var _button_cells: Dictionary = {}


## Build from a run's `ui` block, or nothing when it publishes no panel frame.
##
## A card with no art is no card. Drawing a plain box instead would be worse than
## drawing nothing: a placeholder is a claim that the generated frame is not
## needed, and this panel is exactly the moment the generated frame is the point.
static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerDefeatCard:
	var ui: Dictionary = manifest.get("ui", {})
	var panel: Dictionary = ui.get("panel_frame", {})
	if panel.is_empty():
		push_warning(
			"platformer host: this package publishes no ui.panel_frame, so a defeated player is shown nothing"
		)
		return null
	var art := _texture_of(package, panel)
	if art == null:
		# A block that names art the run does not carry is a package problem, and a
		# silent no-op reads as a bug in the host. Say which file, so the answer is
		# in the sentence rather than in a bisect.
		push_warning(
			"platformer host: ui.panel_frame names %s and the run does not carry it, so a defeated player is shown nothing"
			% str((panel.get("asset", {}) as Dictionary).get("path", "(no path)"))
		)
		return null

	var made := PlatformerDefeatCard.new()
	var left := (PlatformerStage.VIEW_WIDTH - CARD_WIDTH) / 2.0
	var top := (PlatformerStage.VIEW_HEIGHT - CARD_HEIGHT) / 2.0

	made._veil = ColorRect.new()
	made._veil.color = VEIL_COLOR
	made._veil.position = Vector2.ZERO
	made._veil.size = Vector2(PlatformerStage.VIEW_WIDTH, PlatformerStage.VIEW_HEIGHT)
	made.add_child(made._veil)

	made._frame = _nine_slice(art, panel, _first_cell(panel))
	made._frame.position = Vector2(left, top)
	made._frame.size = Vector2(CARD_WIDTH, CARD_HEIGHT)
	made.add_child(made._frame)

	made._title = Label.new()
	made._title.add_theme_font_size_override("font_size", TITLE_SIZE)
	made._title.add_theme_color_override("font_color", TITLE_COLOR)
	made._title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made._title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	made._title.position = Vector2(left + PADDING, top + PADDING)
	made._title.size = Vector2(CARD_WIDTH - PADDING * 2.0, TITLE_ROW_HEIGHT)
	made.add_child(made._title)

	var button_top := top + PADDING + TITLE_ROW_HEIGHT + ROW_GAP
	var button_left := left + (CARD_WIDTH - BUTTON_WIDTH) / 2.0
	var button_block: Dictionary = ui.get("button_rect", {})
	var button_art := _texture_of(package, button_block)
	if button_art == null:
		push_warning(
			"platformer host: this package publishes no readable ui.button_rect, so the defeat card's button is words on the frame"
		)
	else:
		for entry: Variant in (button_block.get("cells", []) as Array):
			var cell: Dictionary = entry
			made._button_cells[str(cell.get("state", ""))] = cell.get("cell", {})
		made._button = _nine_slice(
			button_art, button_block, made._button_cells.get("normal", {})
		)
		made._button.position = Vector2(button_left, button_top)
		made._button.size = Vector2(BUTTON_WIDTH, BUTTON_HEIGHT)
		made.add_child(made._button)

	made._label = Label.new()
	made._label.add_theme_font_size_override("font_size", LABEL_SIZE)
	made._label.add_theme_color_override("font_color", LABEL_COLOR)
	made._label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made._label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	made._label.position = Vector2(button_left, button_top)
	made._label.size = Vector2(BUTTON_WIDTH, BUTTON_HEIGHT)
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
	# The state is the world's word, and the sheet was drawn with four of them.
	# Falling back to `normal` rather than to nothing: a state this build has not
	# caught up with should still draw a button.
	var state := str(world.defeat_panel.get("buttonState", "normal"))
	var cell: Dictionary = _button_cells.get(state, _button_cells.get("normal", {}))
	if not cell.is_empty():
		_button.region_rect = Rect2(
			float(cell.get("x", 0)),
			float(cell.get("y", 0)),
			float(cell.get("width", 0)),
			float(cell.get("height", 0))
		)


static func _texture_of(package: HostRunDir, block: Dictionary) -> Texture2D:
	if block.is_empty():
		return null
	var art := package.texture(str((block.get("asset", {}) as Dictionary).get("path", "")))
	if art == null:
		art = package.texture(str(block.get("asset", "")))
	return art


static func _first_cell(block: Dictionary) -> Dictionary:
	var cells: Array = block.get("cells", [])
	if cells.is_empty():
		return {}
	return (cells[0] as Dictionary).get("cell", {})


## One published sheet as a nine-slice: the ornament at its own size in the
## corners, the bands stretched or tiled between them the way the block says.
static func _nine_slice(art: Texture2D, block: Dictionary, cell: Dictionary) -> NinePatchRect:
	var made := NinePatchRect.new()
	made.texture = art
	if not cell.is_empty():
		made.region_rect = Rect2(
			float(cell.get("x", 0)),
			float(cell.get("y", 0)),
			float(cell.get("width", art.get_width())),
			float(cell.get("height", art.get_height()))
		)
	var insets: Dictionary = block.get("insets", {})
	made.patch_margin_left = int(insets.get("left", 0))
	made.patch_margin_top = int(insets.get("top", 0))
	made.patch_margin_right = int(insets.get("right", 0))
	made.patch_margin_bottom = int(insets.get("bottom", 0))
	# `stretch` and `tile` are the two the block may name, and a band drawn the
	# wrong way is the one thing a nine-slice can get visibly wrong.
	if str(block.get("band_fill", "stretch")) == "tile":
		made.axis_stretch_horizontal = NinePatchRect.AXIS_STRETCH_MODE_TILE
		made.axis_stretch_vertical = NinePatchRect.AXIS_STRETCH_MODE_TILE
	return made
