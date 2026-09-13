extends "res://addons/scenario_runtime/presentation/portrait_feed.gd"

## Afterlight supplies the frame geometry, motion and decorative television skin.
const DEFAULT_FRAME := Rect2(332, 135, 616, 472)
const DEFAULT_INSET := Vector2(20, 20)


func present(actor_id: String, texture: Texture2D, camera: Transform2D, effect_time: float, settings: Dictionary = {}) -> void:
	var configured := {
		"frame_rect": DEFAULT_FRAME, "feed_inset": DEFAULT_INSET,
		"face_uv_rect": Rect2(0.35, 0.14, 0.25, 0.33), "eye_uv": Vector2(0.47, 0.28),
		"hologram_strength": 0.70, "bob_amplitude": Vector2(2.0, 3.0),
		"bob_frequencies": Vector2(0.61, 0.89),
	}
	configured.merge(settings, true)
	super.present(actor_id, texture, camera, effect_time, configured)


func _draw() -> void:
	if not bool(_state["visible"]): return
	var panel := Rect2(Vector2.ZERO, size)
	var unit := _scale_factor
	# The soft perimeter is drawn geometry; the feed shader cannot affect it.
	for radius: float in [9.0, 5.0, 2.0]:
		draw_rect(panel.grow(radius * unit), Color(0.18, 0.65, 0.77, 0.025), false, 2.0 * unit)
	draw_rect(panel, Color("101c27"))
	draw_rect(panel, Color(0.43, 0.70, 0.76, 0.86), false, 1.5 * unit)
	draw_rect(Rect2(_clip.position - Vector2.ONE * unit, _clip.size + Vector2.ONE * 2.0 * unit), Color("6c929c"), false, unit)
	var corner := 22.0 * unit
	for x: float in [0.0, size.x]:
		for y: float in [0.0, size.y]:
			var origin := Vector2(x, y)
			var direction := Vector2(1.0 if x == 0.0 else -1.0, 1.0 if y == 0.0 else -1.0)
			draw_line(origin, origin + Vector2(corner * direction.x, 0.0), Color("b6e0e0"), 3.0 * unit, true)
			draw_line(origin, origin + Vector2(0.0, corner * direction.y), Color("b6e0e0"), 3.0 * unit, true)
	# Tiny status lamps imply a powered display without adding instructions/UI.
	for index in 3:
		draw_circle(Vector2(size.x - (28.0 + index * 8.0) * unit, 10.0 * unit), 1.7 * unit, Color("89cad1"))
	draw_line(Vector2(28, 10) * unit, Vector2(74, 10) * unit, Color("668692"), unit, true)
