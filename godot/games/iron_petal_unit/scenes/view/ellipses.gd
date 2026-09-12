class_name RunnerEllipses
extends Node2D

## The soft shapes under and around things: contact shadows, hazard grounding,
## the approach rim and a pickup's glint.
##
## Godot draws circles and polygons, not ellipses, so a unit ring is built once
## and scaled per shape. The browser had `scene.add.ellipse`, which is the only
## reason this file exists at all.
##
## Specs are refilled every frame rather than retained: an ellipse is four
## numbers and a colour, there are a few dozen of them, and a retained one is
## how a shadow outlives the hazard it belonged to.

## Enough segments that a tile-wide ellipse has no visible corners.
const SEGMENTS := 32

var _fills: Array = []
var _strokes: Array = []
var _ring: PackedVector2Array = PackedVector2Array()


func _init() -> void:
	for index in SEGMENTS:
		var angle := TAU * float(index) / float(SEGMENTS)
		_ring.append(Vector2(cos(angle), sin(angle)))


## Forget last frame's shapes. Call once, then add, then `commit`.
func begin() -> void:
	_fills.clear()
	_strokes.clear()


func add_fill(
	center_x: float, center_y: float, radius_x: float, radius_y: float, color: Color
) -> void:
	if color.a <= 0.0 or radius_x <= 0.0 or radius_y <= 0.0:
		return
	_fills.append([center_x, center_y, radius_x, radius_y, color])


func add_stroke(
	center_x: float, center_y: float, radius_x: float, radius_y: float,
	color: Color, width: float
) -> void:
	if color.a <= 0.0 or radius_x <= 0.0 or radius_y <= 0.0:
		return
	_strokes.append([center_x, center_y, radius_x, radius_y, color, width])


func commit() -> void:
	queue_redraw()


func _draw() -> void:
	for entry: Variant in _fills:
		var spec: Array = entry
		draw_colored_polygon(_shape(spec), spec[4])
	for entry: Variant in _strokes:
		var spec: Array = entry
		var points := _shape(spec)
		points.append(points[0])
		draw_polyline(points, spec[4], float(spec[5]), true)


func _shape(spec: Array) -> PackedVector2Array:
	var made := PackedVector2Array()
	var center := Vector2(float(spec[0]), float(spec[1]))
	var radius := Vector2(float(spec[2]), float(spec[3]))
	for point in _ring:
		made.append(center + point * radius)
	return made
