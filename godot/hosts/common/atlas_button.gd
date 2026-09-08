class_name HostAtlasButton
extends Control

## One generated button: a nine-slice at four states, a label, and a glyph.
##
## A port of `web/lib/families/ui/button.ts`. A button is the same object in
## every genre — the four looks are the producer's pixels rather than a tint,
## which is the whole reason the sheet publishes four cells, and an icon button
## is this same button with a glyph from the icon grid composed onto it, because
## the icon sheet publishes no button of its own. What differs between genres is
## where it sits and what the press means, so neither is here.
##
## The hit area is this control's own rectangle, which is the drawn body. The
## browser had to say that explicitly: its engine sized the hit area from the
## texture *frame*, which for an atlas cell is the whole sheet rectangle, and
## three buttons in a row then swallowed each other's presses.

signal pressed

## Between the glyph and the words, when both are present.
const CONTENT_GAP := 10.0
## The glyph's cell side as a fraction of the safe rect's height.
const ICON_SCALE := 1.0

const LABEL_SIZE := 23
## The light and dark ends of the range, offered in that order. Defaults only:
## each genre draws its own paper — the room's `#f2f3f5`, the scene's `#f4f1ee` —
## and hands them in, because what the measurement chooses *between* is the
## genre's palette rather than pure white.
const LIGHT_INK := Color(0.949, 0.953, 0.961)
const DARK_INK := Color(0.078, 0.09, 0.149)

var _frame: HostPanelFrame = null
var _label: Label = null
var _icon: TextureRect = null
var _hovered := false
var _held := false
var _selected := false
var _enabled := true
## Whether this button's words are laid out as a wrapped block rather than
## placed beside a glyph.
var _wrapped := false


## Build one button from a run's sheets. Returns null when the package
## publishes no button art.
static func of(
	sheets: HostUiSheets,
	rect: Dictionary,
	label: String,
	glyph: String = "",
	light: Color = LIGHT_INK,
	dark: Color = DARK_INK
) -> HostAtlasButton:
	var made := HostAtlasButton.new()
	made._frame = HostPanelFrame.of(sheets, "button_rect", {"x": 0.0, "y": 0.0, "width": float(rect["width"]), "height": float(rect["height"])}, "normal")
	if made._frame == null:
		return null
	made.position = Vector2(float(rect["x"]), float(rect["y"]))
	made.size = Vector2(float(rect["width"]), float(rect["height"]))
	made.mouse_filter = Control.MOUSE_FILTER_STOP
	made.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	made.add_child(made._frame)

	made._label = Label.new()
	made._label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._label.add_theme_font_size_override("font_size", LABEL_SIZE)
	made._label.text = label
	made.add_child(made._label)

	if glyph != "" and sheets.has("preview_icons"):
		var cell := sheets.glyph_rect(glyph)
		if cell.size.x > 0.0:
			var atlas := AtlasTexture.new()
			atlas.atlas = sheets.texture("preview_icons")
			atlas.region = cell
			made._icon = TextureRect.new()
			made._icon.texture = atlas
			made._icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
			made._icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			made._icon.stretch_mode = TextureRect.STRETCH_SCALE
			made.add_child(made._icon)

	# The words read on the button's own art, which is a different sheet from
	# the panels a host draws elsewhere.
	var face := made._frame.interior_color()
	if not face.is_empty():
		var choice := FamilyContrast.most_readable(
			face,
			[
				[light.r * 255.0, light.g * 255.0, light.b * 255.0],
				[dark.r * 255.0, dark.g * 255.0, dark.b * 255.0],
			]
		)
		if choice >= 0:
			made._label.add_theme_color_override("font_color", light if choice == 0 else dark)
	made.mouse_entered.connect(made._on_entered)
	made.mouse_exited.connect(made._on_exited)
	made._place()
	made._paint()
	return made


## Show this button as the chosen one in a group.
##
## A four-state sheet publishes no selected cell, so a toggle borrows the
## pressed art: it is the one look that reads as "this is the one that is on"
## without inventing a tint the producer never drew.
func set_selected(selected: bool) -> void:
	if selected == _selected:
		return
	_selected = selected
	_paint()


func set_enabled(enabled: bool) -> void:
	if enabled == _enabled:
		return
	_enabled = enabled
	if not enabled:
		_held = false
	mouse_filter = Control.MOUSE_FILTER_STOP if enabled else Control.MOUSE_FILTER_IGNORE
	_paint()


func set_label(text: String) -> void:
	_label.text = text
	_place()


## The same, wrapped and centred inside the button's own drawn interior.
##
## A label with no wrap answers `get_minimum_size` with its whole single-line
## width, and `_place` centres *that* — so a long option runs off both ends of
## the art. A wrapped label cannot be placed by its measured width either: the
## first version of this asked `_place` to centre a label whose minimum size it
## had just forced to the full interior, and put both options in the top-right
## corner of the frame. So a wrapped label is given the interior as its rectangle
## and centres itself in it, and `_place` leaves it alone.
func set_wrapped_label(text: String) -> void:
	_wrapped = true
	var safe := _frame.safe_rect()
	_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_label.clip_text = true
	_label.text = text
	_label.position = Vector2(float(safe["x"]), float(safe["y"]))
	_label.size = Vector2(float(safe["width"]), float(safe["height"]))


## Move and resize, keeping the content placed on the new safe interior.
func set_rect(rect: Dictionary) -> void:
	position = Vector2(float(rect["x"]), float(rect["y"]))
	size = Vector2(float(rect["width"]), float(rect["height"]))
	_frame.set_rect({"x": 0.0, "y": 0.0, "width": size.x, "height": size.y})
	if _wrapped:
		set_wrapped_label(_label.text)
		return
	_place()


func _gui_input(event: InputEvent) -> void:
	if not _enabled or not (event is InputEventMouseButton):
		return
	var click: InputEventMouseButton = event
	if click.button_index != MOUSE_BUTTON_LEFT:
		return
	if click.pressed:
		_held = true
		_paint()
		return
	var fired := _held
	_held = false
	_paint()
	if fired:
		pressed.emit()


func _on_entered() -> void:
	_hovered = true
	_paint()


func _on_exited() -> void:
	_hovered = false
	_held = false
	_paint()


func _paint() -> void:
	_frame.set_frame_state(_state())


func _state() -> String:
	if not _enabled:
		return "disabled"
	if _held or _selected:
		return "pressed"
	return "hover" if _hovered else "normal"


## Where the glyph and the words go inside the safe rect.
##
## A glyph beside words is one centred group: the glyph, a gap, then the words
## drawn from their left edge. A glyph alone or words alone sit at the centre.
func _place() -> void:
	if _wrapped:
		return
	var safe := _frame.safe_rect()
	var centre_x := float(safe["x"]) + float(safe["width"]) / 2.0
	var centre_y := float(safe["y"]) + float(safe["height"]) / 2.0
	var label_size := _label.get_minimum_size()
	var label_width := label_size.x if _label.text != "" else 0.0
	_label.size = label_size
	if _icon == null:
		_label.position = Vector2(centre_x - label_width / 2.0, centre_y - label_size.y / 2.0)
		return
	var side := minf(float(safe["height"]) * ICON_SCALE, float(safe["width"]))
	if label_width <= 0.0:
		_icon.position = Vector2(centre_x - side / 2.0, centre_y - side / 2.0)
		_icon.size = Vector2(side, side)
		_label.position = Vector2(centre_x, centre_y - label_size.y / 2.0)
		return
	var group := side + CONTENT_GAP + label_width
	var start := centre_x - group / 2.0
	_icon.position = Vector2(start, centre_y - side / 2.0)
	_icon.size = Vector2(side, side)
	_label.position = Vector2(start + side + CONTENT_GAP, centre_y - label_size.y / 2.0)
