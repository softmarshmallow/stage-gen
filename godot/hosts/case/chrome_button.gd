class_name CaseChromeButton
extends Control

## One of the shell's own controls: a bordered word, and nothing else.
##
## The container draws no generated art — see `chrome.gd` — so this is a
## rectangle, a border and a label, sized to the words it holds. That is the
## browser's own `CurtainButton` and its two smaller relatives, which are a
## `border`, a `px`, a `py` and a font size apart and nothing more.

signal pressed

const BORDER := Color(0.902, 0.902, 0.902, 0.7)
const LABEL := Color(0.902, 0.902, 0.902)
const PADDING_X := 20.0
const PADDING_Y := 8.0
const BORDER_WIDTH := 1.0

## What the button says when it is not saying something else. The backlog toggle
## carries a count that changes under it, so the count is remembered here rather
## than recomputed by whoever flips the label back.
var counted_label: String = ""

var _label: Label = null
var _frame: HostOutline = null
var _ground: Color = Color(0, 0, 0, 0)


static func of(label: String, size: int, ground: Color = Color(0, 0, 0, 0)) -> CaseChromeButton:
	var made := CaseChromeButton.new()
	made.counted_label = label
	made._ground = ground
	made.mouse_filter = Control.MOUSE_FILTER_STOP
	made.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	made._frame = HostOutline.of()
	made.add_child(made._frame)
	made._label = Label.new()
	made._label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made._label.add_theme_font_size_override("font_size", size)
	made._label.add_theme_color_override("font_color", LABEL)
	made._label.text = label
	made.add_child(made._label)
	made._relayout()
	return made


## Measured again once there is a theme to measure against.
##
## A label built outside the tree answers `get_minimum_size` from whatever font
## it can reach, which is not yet the one it will be drawn in — so a button laid
## out at construction is a box the wrong size for its own word, and two of them
## side by side overlap.
func _ready() -> void:
	_relayout()


func set_label(value: String) -> void:
	_label.text = value
	_relayout()


func _relayout() -> void:
	var measured := _label.get_minimum_size()
	_label.size = measured
	_label.position = Vector2(PADDING_X, PADDING_Y)
	size = Vector2(measured.x + PADDING_X * 2.0, measured.y + PADDING_Y * 2.0)
	custom_minimum_size = size
	_frame.size = size
	_frame.show_shapes(
		[{"rect": Rect2(Vector2.ZERO, size), "fill": _ground, "stroke": BORDER, "width": BORDER_WIDTH}]
	)


func _gui_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return
	var click: InputEventMouseButton = event
	if click.button_index == MOUSE_BUTTON_LEFT and not click.pressed:
		pressed.emit()
