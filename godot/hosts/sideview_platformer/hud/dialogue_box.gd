class_name PlatformerDialogueBox
extends Control

## What a villager is saying, on the panel the run published art for.
##
## A nine-slice frame across the bottom of the design space: the generated art's
## corners are drawn at their own size and its bands stretch or tile between
## them, so the same sheet fits a panel of any width without smearing an
## ornament. The insets and the band rule come from the run's `ui` block, never
## from a number measured off the pixels here.
##
## Screen space, above everything the world draws. A conversation is furniture.

## The panel, in the 1280x720 the manifest publishes its rectangles in.
const PANEL_INSET_X := 40.0
const PANEL_HEIGHT := 210.0
const PANEL_CENTRE_Y := 592.0

## Where the words sit inside it: a slot down the left a portrait would stand in,
## a row for the speaker's name, and the body under both.
const PORTRAIT_SLOT_WIDTH := 210.0
const COLUMN_GAP := 24.0
const NAME_ROW_HEIGHT := 34.0
const ROW_GAP := 10.0
const PADDING := 8.0

const NAME_SIZE := 26
const BODY_SIZE := 22
const NAME_COLOR := Color(1.0, 0.867, 0.639)
const BODY_COLOR := Color(0.965, 0.953, 0.929)

var _frame: NinePatchRect = null
var _name: Label = null
var _body: Label = null


## Build from a run's `ui` block, or nothing when it publishes no panel frame.
static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerDialogueBox:
	var block: Dictionary = (manifest.get("ui", {}) as Dictionary).get("panel_frame", {})
	if block.is_empty():
		return null
	var art := package.texture(str((block.get("asset", {}) as Dictionary).get("path", "")))
	if art == null:
		art = package.texture(str(block.get("asset", "")))
	if art == null:
		return null

	var made := PlatformerDialogueBox.new()
	var cells: Array = block.get("cells", [])
	var cell: Dictionary = (cells[0] as Dictionary).get("cell", {}) if not cells.is_empty() else {}
	var insets: Dictionary = block.get("insets", {})

	made._frame = NinePatchRect.new()
	made._frame.texture = art
	if not cell.is_empty():
		made._frame.region_rect = Rect2(
			float(cell.get("x", 0)),
			float(cell.get("y", 0)),
			float(cell.get("width", art.get_width())),
			float(cell.get("height", art.get_height()))
		)
	made._frame.patch_margin_left = int(insets.get("left", 0))
	made._frame.patch_margin_top = int(insets.get("top", 0))
	made._frame.patch_margin_right = int(insets.get("right", 0))
	made._frame.patch_margin_bottom = int(insets.get("bottom", 0))
	# `stretch` and `tile` are the two the block may name, and a band drawn the
	# wrong way is the one thing a nine-slice can get visibly wrong.
	if str(block.get("band_fill", "stretch")) == "tile":
		made._frame.axis_stretch_horizontal = NinePatchRect.AXIS_STRETCH_MODE_TILE
		made._frame.axis_stretch_vertical = NinePatchRect.AXIS_STRETCH_MODE_TILE
	var width := PlatformerStage.VIEW_WIDTH - PANEL_INSET_X * 2.0
	made._frame.position = Vector2(PANEL_INSET_X, PANEL_CENTRE_Y - PANEL_HEIGHT / 2.0)
	made._frame.size = Vector2(width, PANEL_HEIGHT)
	made.add_child(made._frame)

	var text_left := PANEL_INSET_X + PORTRAIT_SLOT_WIDTH + COLUMN_GAP + PADDING
	var text_top := PANEL_CENTRE_Y - PANEL_HEIGHT / 2.0 + PADDING
	made._name = Label.new()
	made._name.add_theme_font_size_override("font_size", NAME_SIZE)
	made._name.add_theme_color_override("font_color", NAME_COLOR)
	made._name.position = Vector2(text_left, text_top)
	made.add_child(made._name)
	made._body = Label.new()
	made._body.add_theme_font_size_override("font_size", BODY_SIZE)
	made._body.add_theme_color_override("font_color", BODY_COLOR)
	made._body.position = Vector2(text_left, text_top + NAME_ROW_HEIGHT + ROW_GAP)
	made._body.size = Vector2(
		PlatformerStage.VIEW_WIDTH - text_left - PANEL_INSET_X - PADDING,
		PANEL_HEIGHT - NAME_ROW_HEIGHT - ROW_GAP - PADDING * 2.0
	)
	made._body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	made.add_child(made._body)
	made.visible = false
	return made


## Show whatever the conversation is saying now, or nothing when none is open.
func sync(world: PlatformerWorld) -> void:
	if not (world.dialogue is Dictionary):
		visible = false
		return
	var view := FamilyScenarioRuntime.view(world.scenario, world.dialogue_state)
	if view.is_empty():
		visible = false
		return
	visible = true
	if str(view.get("kind", "")) == "choice":
		# A choice is a numbered list rather than a line, and the number is the
		# key that picks it. Nobody is speaking, so the name row is the prompt.
		_name.text = "CHOOSE"
		var lines := PackedStringArray()
		var index := 1
		for entry: Variant in (view.get("options", []) as Array):
			lines.append("%d. %s" % [index, str((entry as Dictionary).get("text", ""))])
			index += 1
		_body.text = "\n".join(lines)
		return
	# A line with no speaker is narration, which is drawn with the name row
	# empty rather than with a placeholder nobody said.
	var label: Variant = view.get("speakerLabel")
	_name.text = "" if label == null else str(label).to_upper()
	_body.text = str(view.get("text", ""))
