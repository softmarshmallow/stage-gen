extends Control

## Afterlight's floating television: a game-owned frame around one portrait feed.
## The host supplies a logical world camera and its already-owned effect clock.
## present() is stateless sampling; it does not start timers, advance simulation,
## or follow the speaking actor. clear() hides the feed without keeping a call.
const HOLOGRAM = preload("res://addons/game_presentation/effects/shaders/character_hologram.gdshader")
const DEFAULT_FRAME := Rect2(332, 135, 616, 472)
const DEFAULT_INSET := Vector2(20, 20)
const EMPTY_STATE := {"visible": false, "actor_id": "", "frame_rect": Rect2(), "feed_rect": Rect2(),
	"portrait_rect": Rect2(), "face_rect": Rect2(), "eye_point": Vector2.ZERO,
	"effect_time": 0.0, "hologram_strength": 0.0}
var _clip: Control
var _feed: TextureRect
var _material: ShaderMaterial
var _state := EMPTY_STATE.duplicate(true)
var _scale_factor := 1.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_clip = Control.new()
	_clip.name = "ClippedTransmissionFeed"
	_clip.clip_contents = true
	_clip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_clip)
	_feed = TextureRect.new()
	_feed.name = "TransmissionPortrait"
	_feed.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_feed.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_clip.add_child(_feed)
	_material = ShaderMaterial.new()
	_material.shader = HOLOGRAM
	_feed.material = _material
	clear()


func present(actor_id: String, texture: Texture2D, camera: Transform2D, effect_time: float, settings: Dictionary = {}) -> void:
	if _feed == null or actor_id.is_empty() or texture == null:
		clear()
		return
	var clock := maxf(0.0, effect_time)
	var base: Rect2 = settings.get("frame_rect", DEFAULT_FRAME)
	var bob := Vector2(2.0 * sin(clock * 0.61), 3.0 * sin(clock * 0.89))
	var frame: Rect2 = camera * Rect2(base.position + bob, base.size)
	_scale_factor = camera.x.length()
	var inset: Vector2 = settings.get("feed_inset", DEFAULT_INSET) * _scale_factor
	var feed_rect := Rect2(frame.position + inset, frame.size - inset * 2.0)
	var source_size := texture.get_size()
	var factor := maxf(feed_rect.size.x / source_size.x, feed_rect.size.y / source_size.y)
	var portrait_size := source_size * factor
	var portrait_rect := Rect2(feed_rect.position + (feed_rect.size - portrait_size) * 0.5, portrait_size)
	var face_uv: Rect2 = settings.get("face_uv_rect", Rect2(0.35, 0.14, 0.25, 0.33))
	var face_rect := Rect2(portrait_rect.position + portrait_rect.size * face_uv.position, portrait_rect.size * face_uv.size)
	var eye_uv: Vector2 = settings.get("eye_uv", Vector2(0.47, 0.28))
	var strength := clampf(float(settings.get("hologram_strength", 0.70)), 0.0, 1.0)
	position = frame.position
	size = frame.size
	_clip.position = inset
	_clip.size = feed_rect.size
	_feed.texture = texture
	_feed.position = portrait_rect.position - feed_rect.position
	_feed.size = portrait_rect.size
	_material.set_shader_parameter("effect_time", clock)
	_material.set_shader_parameter("strength", strength)
	_state = {"visible": true, "actor_id": actor_id, "frame_rect": frame, "feed_rect": feed_rect,
		"portrait_rect": portrait_rect, "face_rect": face_rect,
		"eye_point": portrait_rect.position + portrait_rect.size * eye_uv,
		"effect_time": clock, "hologram_strength": strength}
	show()
	queue_redraw()


func clear() -> void:
	hide()
	_state = EMPTY_STATE.duplicate(true)
	_scale_factor = 1.0
	position = Vector2.ZERO
	size = Vector2.ZERO
	if _feed != null: _feed.texture = null
	if _material != null:
		_material.set_shader_parameter("effect_time", 0.0)
		_material.set_shader_parameter("strength", 0.0)


func snapshot() -> Dictionary:
	var result := _state.duplicate(true)
	result["visible"] = visible
	result["feed_clipped"] = _clip != null and _clip.clip_contents
	if _material != null:
		result["hologram_strength"] = float(_material.get_shader_parameter("strength"))
		result["effect_time"] = float(_material.get_shader_parameter("effect_time"))
	return result


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
