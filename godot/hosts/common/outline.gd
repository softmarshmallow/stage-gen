class_name HostOutline
extends Control

## A list of rectangles, filled and outlined, drawn in one node.
##
## The engine has no rounded-rectangle primitive and the three turn-based hosts
## want the same two shapes — a hotspot marker and an inventory slot — so this is
## the one place either is drawn. Corners are square rather than rounded, which
## is the one visible difference from the browser's `strokeRoundedRect`, and it
## is here rather than faked with an arc because a marker's job is to say *where*
## a thing is.
##
## Each entry is `{rect: Rect2, fill: Color, stroke: Color, width: float}`; a
## fully transparent fill or stroke is simply not drawn.

var shapes: Array = []


static func of() -> HostOutline:
	var made := HostOutline.new()
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return made


## Replace everything drawn, and ask for a redraw.
func show_shapes(next: Array) -> void:
	shapes = next
	queue_redraw()


func _draw() -> void:
	for entry: Variant in shapes:
		var shape: Dictionary = entry
		var rect: Rect2 = shape["rect"]
		var fill: Color = shape.get("fill", Color(0, 0, 0, 0))
		if fill.a > 0.0:
			draw_rect(rect, fill, true)
		var stroke: Color = shape.get("stroke", Color(0, 0, 0, 0))
		if stroke.a > 0.0:
			draw_rect(rect, stroke, false, float(shape.get("width", 2.0)))
