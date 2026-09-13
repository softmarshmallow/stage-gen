extends Control

## Clipped, camera-transformed portrait feed. Bindings supply geometry, effect
## settings and explicit time; optional frame decoration belongs to the caller.
## This node samples presentation only and never schedules a narrative cue.
const HOLOGRAM = preload("res://addons/game_presentation/effects/shaders/character_hologram.gdshader")
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
	if not is_finite(effect_time) or not settings.get("frame_rect") is Rect2 or not (settings["frame_rect"] as Rect2).has_area():
		clear()
		return
	var clock := maxf(0.0, effect_time)
	var base: Rect2 = settings.get("frame_rect", Rect2())
	var amplitude: Vector2 = settings.get("bob_amplitude", Vector2.ZERO)
	var frequencies: Vector2 = settings.get("bob_frequencies", Vector2.ONE)
	var bob := Vector2(amplitude.x * sin(clock * frequencies.x), amplitude.y * sin(clock * frequencies.y))
	var frame: Rect2 = camera * Rect2(base.position + bob, base.size)
	_scale_factor = camera.x.length()
	var inset: Vector2 = settings.get("feed_inset", Vector2.ZERO) * _scale_factor
	var feed_rect := Rect2(frame.position + inset, frame.size - inset * 2.0)
	var source_size := texture.get_size()
	var factor := maxf(feed_rect.size.x / source_size.x, feed_rect.size.y / source_size.y)
	var portrait_size := source_size * factor
	var portrait_rect := Rect2(feed_rect.position + (feed_rect.size - portrait_size) * 0.5, portrait_size)
	var face_uv: Rect2 = settings.get("face_uv_rect", Rect2(0, 0, 1, 1))
	var face_rect := Rect2(portrait_rect.position + portrait_rect.size * face_uv.position, portrait_rect.size * face_uv.size)
	var eye_uv: Vector2 = settings.get("eye_uv", Vector2(0.5, 0.5))
	var strength := clampf(float(settings.get("hologram_strength", 0.0)), 0.0, 1.0)
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
