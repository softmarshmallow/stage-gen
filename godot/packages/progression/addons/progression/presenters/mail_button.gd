extends Control
## The mailbox's entry: a drawn envelope with an unread badge, top-right of the hub. It is the only
## Control in its layer that takes a press (mouse or touch, emulated twins dropped), so the joystick
## under it still starts anywhere else.

signal pressed

const STYLE := preload("style.gd")

var unread := 0:
	set(v):
		unread = maxi(v, 0)
		queue_redraw()
var ui := 1.0
var _hover := false
var _press := 0.0


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_NONE
	mouse_entered.connect(func() -> void: _hover = true; queue_redraw())
	mouse_exited.connect(func() -> void: _hover = false; queue_redraw())


func place(viewport: Vector2) -> void:
	ui = STYLE.scale(viewport)
	var side := roundf(54.0 * ui)
	size = Vector2(side, side)
	position = Vector2(viewport.x - side - 18.0 * ui, 18.0 * ui)
	queue_redraw()


func _gui_input(event: InputEvent) -> void:
	if STYLE.pressed(event):
		_press = 1.0
		queue_redraw()
		pressed.emit()
	if event is InputEventScreenTouch or (event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT):
		accept_event()


func _process(delta: float) -> void:
	if _press > 0.0:
		_press = maxf(_press - delta * 4.0, 0.0)
		queue_redraw()


func _draw() -> void:
	var s := ui
	var k := 1.0 - 0.08 * _press
	var c := size * 0.5
	var w := size.x * 0.72 * k
	var h := size.y * 0.5 * k
	var rect := Rect2(c - Vector2(w, h) * 0.5, Vector2(w, h))
	var plate := Color(0.03, 0.025, 0.03, 0.78 if not _hover else 0.9)
	draw_rect(Rect2(Vector2.ZERO, size), plate)
	draw_rect(Rect2(Vector2.ZERO, size), Color(STYLE.GOLD, 0.75 if _hover else 0.5), false, maxf(1.5 * s, 1.0))
	var body := STYLE.BONE if not _hover else Color.WHITE
	draw_rect(rect, body)
	# the flap: two strokes from the top corners to a point a little below the middle
	var flap := PackedVector2Array([rect.position, Vector2(c.x, rect.position.y + h * 0.62), rect.position + Vector2(w, 0.0)])
	draw_polyline(flap, Color(0.08, 0.06, 0.06), maxf(2.0 * s, 1.0), true)
	draw_rect(rect, Color(0.08, 0.06, 0.06), false, maxf(1.5 * s, 1.0))
	if unread > 0:
		var badge_r := 10.0 * s
		var bc := rect.position + Vector2(w, 0.0)
		draw_circle(bc, badge_r, Color(0.86, 0.22, 0.2))
		var font := STYLE.sans(800)
		var px := int(roundf(12.0 * s))
		var t := str(mini(unread, 99))
		var tw := font.get_string_size(t, HORIZONTAL_ALIGNMENT_LEFT, -1.0, px).x
		draw_string(font, bc + Vector2(-tw * 0.5, px * 0.36), t, HORIZONTAL_ALIGNMENT_LEFT, -1.0, px, Color.WHITE)
