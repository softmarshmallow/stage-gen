extends Control

## The preview uses the same function that places actors during a handoff.
const MOTION = preload("res://addons/game_presentation/motion/motion_curve.gd")
const TACTICAL_THEME = preload("res://presentation/ui/tactical_theme.gd")
var _settings: Dictionary = {}
var _progress := -1.0


func set_state(settings: Dictionary, progress: float = -1.0) -> void:
	if settings == _settings and is_equal_approx(progress, _progress):
		return
	_settings = settings.duplicate(true)
	_progress = progress
	queue_redraw()


func get_curve_samples(count: int = 121) -> Array[Vector2]:
	var points: Array[Vector2] = []
	if _settings.is_empty() or count < 2:
		return points
	for index in count:
		var progress := float(index) / float(count - 1)
		points.append(Vector2(progress, MOTION.sample(progress, _settings)))
	return points


func _plot_point(point: Vector2, plot: Rect2) -> Vector2:
	# Extra vertical room makes spring overshoot visible instead of clipping it.
	return plot.position + Vector2(point.x * plot.size.x, (1.65 - point.y) / 1.8 * plot.size.y)


func _draw() -> void:
	var background := StyleBoxFlat.new()
	background.bg_color = TACTICAL_THEME.BG
	background.border_color = TACTICAL_THEME.BORDER
	background.set_border_width_all(1)
	background.set_corner_radius_all(0)
	draw_style_box(background, Rect2(Vector2.ZERO, size))
	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(12, 18), "Motion curve", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, TACTICAL_THEME.ACCENT)
	var plot := Rect2(Vector2(28, 29), size - Vector2(42, 49))
	for amount: float in [0.0, 1.0]:
		var left := _plot_point(Vector2(0, amount), plot)
		var right := _plot_point(Vector2(1, amount), plot)
		draw_line(left, right, Color(0.60, 0.70, 0.74, 0.24), 1.0)
		draw_string(font, left + Vector2(-18, 4), str(int(amount)), HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color("a0a9ac"))
	draw_string(font, Vector2(size.x - 36, size.y - 7), "time", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color("a0a9ac"))
	var points := PackedVector2Array()
	for point: Vector2 in get_curve_samples():
		points.append(_plot_point(point, plot))
	if points.size() > 1:
		draw_polyline(points, TACTICAL_THEME.ACCENT, 2.0, true)
	if _progress >= 0.0 and not _settings.is_empty():
		var point := _plot_point(Vector2(_progress, MOTION.sample(_progress, _settings)), plot)
		draw_circle(point, 4.0, TACTICAL_THEME.SECONDARY)
