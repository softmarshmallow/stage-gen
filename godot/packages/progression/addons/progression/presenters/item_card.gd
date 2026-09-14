extends Control
## One item tile: a rarity-coloured frame on ink, a drawn icon (a coin for a currency, a cut crystal for
## a material; no media), the count as "×N" in the corner and the name beneath. Ignores the mouse.
## The popup reveals cards one after another: `reveal` in [0, 1] scales and fades the tile in.

const STYLE := preload("style.gd")

var item_id := ""
var spec: Dictionary = {}       # {type, rarity, stack}
var count := 1
var item_name := ""
var ui := 1.0
var reveal := 1.0:
	set(v):
		reveal = clampf(v, 0.0, 1.0)
		_apply_reveal()

var _frame: Panel
var _icon: Control
var _count_label: Label
var _name_label: Label


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	_frame = STYLE.ignore(Panel.new()) as Panel
	add_child(_frame)
	_icon = STYLE.ignore(Icon.new())
	_frame.add_child(_icon)
	_count_label = STYLE.text_label("", STYLE.sans(700), 14.0, STYLE.BONE, HORIZONTAL_ALIGNMENT_RIGHT)
	_frame.add_child(_count_label)
	_name_label = STYLE.text_label("", STYLE.sans(500), 12.0, STYLE.DIM, HORIZONTAL_ALIGNMENT_CENTER)
	_name_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	add_child(_name_label)


func configure(id: String, item_spec: Dictionary, n: int, shown_name: String, scale_factor: float) -> void:
	item_id = id
	spec = item_spec
	count = n
	item_name = shown_name
	ui = scale_factor
	_layout()


static func tile_size(scale_factor: float) -> Vector2:
	## The whole card, frame plus name line.
	return Vector2(roundf(96.0 * scale_factor), roundf(96.0 * scale_factor + 26.0 * scale_factor))


func _layout() -> void:
	var s := ui
	var side := roundf(96.0 * s)
	var rarity: Color = STYLE.RARITY.get(String(spec.get("rarity", "common")), STYLE.RARITY["common"])
	custom_minimum_size = tile_size(s)
	size = custom_minimum_size
	_frame.position = Vector2.ZERO
	_frame.size = Vector2(side, side)
	var sb := STYLE.flat(Color(rarity, 0.14), 8.0 * s, rarity, maxf(1.5 * s, 1.0))
	_frame.add_theme_stylebox_override("panel", sb)
	_icon.position = Vector2(side * 0.12, side * 0.1)
	_icon.size = Vector2(side * 0.76, side * 0.62)
	(_icon as Icon).kind = String(spec.get("type", "material"))
	(_icon as Icon).tint = rarity
	(_icon as Icon).ui = s
	_icon.queue_redraw()
	_count_label.text = "×%d" % count
	_count_label.add_theme_font_size_override("font_size", int(roundf(15.0 * s)))
	_count_label.add_theme_constant_override("outline_size", int(roundf(3.0 * s)))
	_count_label.position = Vector2(0.0, side - 24.0 * s)
	_count_label.size = Vector2(side - 8.0 * s, 22.0 * s)
	_name_label.text = item_name
	_name_label.add_theme_font_size_override("font_size", int(roundf(12.5 * s)))
	_name_label.add_theme_constant_override("outline_size", int(roundf(2.0 * s)))
	_name_label.position = Vector2(-6.0 * s, side + 3.0 * s)
	_name_label.size = Vector2(side + 12.0 * s, 22.0 * s)
	pivot_offset = Vector2(side * 0.5, side * 0.5)
	_apply_reveal()


func _apply_reveal() -> void:
	var e := 1.0 - pow(1.0 - reveal, 3.0)
	var k := lerpf(0.6, 1.0, e)
	scale = Vector2(k, k)
	modulate.a = e
	visible = reveal > 0.001


class Icon extends Control:
	var kind := "material"
	var tint := Color.WHITE
	var ui := 1.0

	func _draw() -> void:
		var c := size * 0.5
		var r := minf(size.x, size.y) * 0.42
		if kind == "currency":
			# a coin: a warm disc, a darker rim, a thin inner ring and a highlight crescent
			draw_circle(c + Vector2(0.0, 2.0 * ui), r, Color(0.0, 0.0, 0.0, 0.35))
			draw_circle(c, r, tint.darkened(0.35))
			draw_circle(c, r * 0.86, tint)
			draw_arc(c, r * 0.62, 0.0, TAU, 40, tint.darkened(0.3), maxf(1.5 * ui, 1.0), true)
			draw_arc(c + Vector2(-r * 0.12, -r * 0.12), r * 0.7, PI * 1.05, PI * 1.75, 24, Color(1.0, 1.0, 1.0, 0.55), maxf(2.0 * ui, 1.0), true)
		else:
			# a cut crystal: a hexagon with a lit upper facet and a dark lower one
			var pts := PackedVector2Array()
			for i in 6:
				var a := -PI * 0.5 + TAU * float(i) / 6.0
				pts.append(c + Vector2(cos(a), sin(a)) * r)
			draw_colored_polygon(pts, tint.darkened(0.25))
			var upper := PackedVector2Array([pts[5], pts[0], pts[1], c])
			draw_colored_polygon(upper, tint.lightened(0.25))
			var lower := PackedVector2Array([pts[2], pts[3], pts[4], c])
			draw_colored_polygon(lower, tint.darkened(0.45))
			var ring := pts.duplicate()
			ring.append(pts[0])
			draw_polyline(ring, Color(1.0, 1.0, 1.0, 0.5), maxf(1.2 * ui, 1.0), true)
			draw_line(pts[0], c, Color(1.0, 1.0, 1.0, 0.35), maxf(1.0 * ui, 1.0), true)
