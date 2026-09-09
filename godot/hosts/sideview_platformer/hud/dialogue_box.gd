class_name PlatformerDialogueBox
extends Control

## What a villager is saying, on the panel and the faces the run published art for.
##
## The frame is `HostPanelFrame`'s, and that is the substance of this file rather
## than a tidying. This box used to build its own `NinePatchRect` and read the
## block's insets straight onto it, which drops `draw_scale`: the sheet is laid out
## at twice the density it is drawn at, so a hundred-and-twelve-pixel corner
## ornament was drawn a hundred and twelve *screen* pixels wide. Two of them plus
## two ninety-six-pixel bands left eighteen pixels of panel in a two-hundred-and-
## ten-pixel box, which is why the panel came out crushed and the words in it
## landed nowhere near the middle. The shared widget lays the slices out at the
## sheet's own density and scales the whole thing back, which is the only way a
## generated ornament keeps its drawn proportion to the body it frames.
##
## Words sit in the frame's `safe_rect` — the interior less the measured curl of
## the ornament — rather than in a rectangle this file guesses at, so a package
## whose frame has a heavier flourish gets narrower text instead of text under it.
##
## Screen space, above everything the world draws. A conversation is furniture.
##
## The portrait slot down the left is the other half. Every villager the generator
## draws publishes a `dialogue` sheet — a grid of expressions, named in the order
## they are laid out — and the scenario stages which one is on by name, so both
## halves were published and neither was drawn. A conversation with a blank slot
## beside it is the one place a package's character art was supposed to be the
## point.

## The panel, in the 1280x720 the manifest publishes its rectangles in.
const PANEL_INSET_X := 40.0
const PANEL_HEIGHT := 220.0
const PANEL_BOTTOM_GAP := 24.0

## How much of the interior the portrait takes down its left, and the gap after it.
const PORTRAIT_SLOT_SHARE := 0.24
const COLUMN_GAP := 20.0
const NAME_ROW_HEIGHT := 34.0
const ROW_GAP := 8.0

const NAME_SIZE := 26
const BODY_SIZE := 22
const NAME_COLOR := Color(1.0, 0.867, 0.639)
const BODY_COLOR := Color(0.965, 0.953, 0.929)

var _frame: HostPanelFrame = null
var _portrait: TextureRect = null
var _name: Label = null
var _body: Label = null
## Every villager's expression sheet, by the id the scenario stages them under.
var _sheets: Dictionary = {}


## Build from a run's `ui` block, or nothing when it publishes no panel frame.
static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerDialogueBox:
	var sheets := HostUiSheets.of(package, manifest.get("ui", {}))
	var width := PlatformerStage.VIEW_WIDTH - PANEL_INSET_X * 2.0
	var top := PlatformerStage.VIEW_HEIGHT - PANEL_BOTTOM_GAP - PANEL_HEIGHT
	var frame := HostPanelFrame.of(
		sheets,
		"panel_frame",
		{"x": PANEL_INSET_X, "y": top, "width": width, "height": PANEL_HEIGHT}
	)
	if frame == null:
		push_warning(
			"platformer host: this package publishes no ui.panel_frame, so a conversation has no panel"
		)
		return null

	var made := PlatformerDialogueBox.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._frame = frame
	made.add_child(frame)
	made._sheets = _dialogue_sheets(package, manifest)

	# The interior the ornament leaves, which is what everything below is laid out
	# in. Measured off the sheet rather than assumed, so a package with a heavier
	# flourish gets narrower text instead of text under it.
	var safe := frame.safe_rect()
	var safe_x := float(safe["x"])
	var safe_y := float(safe["y"])
	var safe_w := float(safe["width"])
	var safe_h := float(safe["height"])
	var portrait_w := safe_w * PORTRAIT_SLOT_SHARE

	made._portrait = TextureRect.new()
	made._portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	# Aspect kept and pinned to the bottom of the slot, so a portrait stands on the
	# panel floor the way a person stands on the ground rather than floating.
	made._portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	made._portrait.clip_contents = true
	made._portrait.position = Vector2(safe_x, safe_y)
	made._portrait.size = Vector2(portrait_w, safe_h)
	made.add_child(made._portrait)

	var text_left := safe_x + portrait_w + COLUMN_GAP
	var text_width := safe_x + safe_w - text_left
	made._name = Label.new()
	made._name.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._name.add_theme_font_size_override("font_size", NAME_SIZE)
	made._name.add_theme_color_override("font_color", NAME_COLOR)
	made._name.position = Vector2(text_left, safe_y)
	made._name.size = Vector2(text_width, NAME_ROW_HEIGHT)
	made.add_child(made._name)

	made._body = Label.new()
	made._body.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._body.add_theme_font_size_override("font_size", BODY_SIZE)
	made._body.add_theme_color_override("font_color", BODY_COLOR)
	made._body.position = Vector2(text_left, safe_y + NAME_ROW_HEIGHT + ROW_GAP)
	made._body.size = Vector2(text_width, safe_h - NAME_ROW_HEIGHT - ROW_GAP)
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
		_portrait.visible = false
		return
	# A line with no speaker is narration, which is drawn with the name row
	# empty rather than with a placeholder nobody said.
	var label: Variant = view.get("speakerLabel")
	_name.text = "" if label == null else str(label).to_upper()
	_body.text = str(view.get("text", ""))
	_show_portrait(world, view.get("speaker"))


## The speaker's face, at the expression the scenario has them staged in.
##
## Nothing is drawn for a speaker with no published sheet, and that is the right
## answer rather than a placeholder: the player character is a member of the cast
## with no villager record, so narration and the player's own lines leave the slot
## empty exactly as they should.
func _show_portrait(world: PlatformerWorld, speaker: Variant) -> void:
	_portrait.visible = false
	if speaker == null:
		return
	var sheet: Dictionary = _sheets.get(str(speaker), {})
	if sheet.is_empty():
		return
	var staged := FamilyScenarioRuntime.actor(world.dialogue_state, str(speaker))
	var expression := str(staged.get("expression", ""))
	var art: Texture2D = sheet["texture"]
	var columns: int = maxi(1, int(sheet["columns"]))
	var rows: int = maxi(1, int(sheet["rows"]))
	var names: PackedStringArray = sheet["expressions"]
	# An expression the sheet does not carry falls back to the first cell rather
	# than to nothing: the author named a face this build has no square for, and a
	# villager with the wrong expression is better than a villager with none.
	var index := maxi(0, names.find(expression))
	var cell_width := float(art.get_width()) / float(columns)
	var cell_height := float(art.get_height()) / float(rows)
	var atlas := AtlasTexture.new()
	atlas.atlas = art
	atlas.region = Rect2(
		float(index % columns) * cell_width,
		float(index / columns) * cell_height,
		cell_width,
		cell_height
	)
	_portrait.texture = atlas
	_portrait.visible = true


## Every villager's expression sheet, by the id the scenario stages them under.
##
## `npc_id` and the scenario's `actor_id` are the same name, which is what lets a
## line find its face without a second table binding them.
static func _dialogue_sheets(package: HostRunDir, manifest: Dictionary) -> Dictionary:
	var made := {}
	for entry: Variant in (manifest.get("npcs", []) as Array):
		var npc: Dictionary = entry
		var block: Dictionary = npc.get("dialogue", {})
		if block.is_empty():
			continue
		var art := package.texture(str((block.get("asset", {}) as Dictionary).get("path", "")))
		if art == null:
			push_warning(
				"platformer host: %s publishes a dialogue sheet the run does not carry, so it speaks faceless"
				% str(npc.get("npc_id", "(unnamed)"))
			)
			continue
		var names := PackedStringArray()
		for name: Variant in (block.get("expressions", []) as Array):
			names.append(str(name))
		made[str(npc.get("npc_id", ""))] = {
			"texture": art,
			"columns": int(block.get("columns", 1)),
			"rows": int(block.get("rows", 1)),
			"expressions": names,
		}
	return made
