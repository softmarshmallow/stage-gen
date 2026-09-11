extends TextureRect

## Actor-local Outer Glow. Draw behind the host's unchanged original sprite.
## The input rect is the full texture's displayed rect in this node's parent space.
const HALO_SHADER := preload("res://addons/game_presentation/effects/shaders/actor_halo.gdshader")
const DEFAULTS := {"color": Color(1.0, 0.79, 0.57, 0.8), "radius": 24.0, "intensity": 1.0}
var _settings: Dictionary = DEFAULTS.duplicate()
var _source_rect := Rect2()
var _strength := 1.0
var _halo_material: ShaderMaterial


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	stretch_mode = TextureRect.STRETCH_SCALE
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	_halo_material = ShaderMaterial.new()
	_halo_material.shader = HALO_SHADER
	material = _halo_material
	_update_uniforms()
	_update_rect()


## Partial configuration. Invalid input leaves all configuration and geometry intact.
func configure(settings: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in settings:
		if not key is String or not DEFAULTS.has(key):
			errors.append("Unknown Actor Halo setting: " + str(key))
		elif key == "color":
			if not settings[key] is Color or not _valid_color(settings[key]):
				errors.append("Actor Halo color must be a finite Color with components in [0, 1].")
		elif key == "radius" and not _number_between(settings[key], 0.0, 128.0):
			errors.append("Actor Halo radius must be finite and in [0, 128] logical pixels.")
		elif key == "intensity" and not _number_between(settings[key], 0.0, 4.0):
			errors.append("Actor Halo intensity must be finite and in [0, 4].")
	if not errors.is_empty():
		return errors
	_settings.merge(settings, true)
	_update_uniforms()
	_update_rect()
	return errors


## Null removes the source. Source color channels are never used by the effect.
func set_source(source: Texture2D) -> void:
	texture = source
	_halo_material.set_shader_parameter("source_texture", source)
	_update_rect()


## Match the host sprite's actual full-texture rect, after its aspect-fit calculation.
func set_rect(source_rect: Rect2) -> Array[String]:
	var errors: Array[String] = []
	if not source_rect.position.is_finite() or not source_rect.size.is_finite() or source_rect.size.x <= 0.0 or source_rect.size.y <= 0.0:
		errors.append("Actor Halo rect must be finite with positive width and height.")
		return errors
	_source_rect = source_rect
	_update_rect()
	return errors


## The host owns animation/time. Zero hides the glow without changing the source sprite.
func set_strength(strength: float) -> Array[String]:
	var errors: Array[String] = []
	if not is_finite(strength) or strength < 0.0 or strength > 1.0:
		errors.append("Actor Halo strength must be finite and in [0, 1].")
		return errors
	_strength = strength
	_update_uniforms()
	_update_rect()
	return errors


func get_strength() -> float:
	return _strength


func get_settings() -> Dictionary:
	return _settings.duplicate()


func get_source_rect() -> Rect2:
	return _source_rect


## Reset only the binding. Configuration and strength remain available for reuse.
func clear() -> void:
	texture = null
	_halo_material.set_shader_parameter("source_texture", null)
	_source_rect = Rect2()
	_update_rect()


func _update_uniforms() -> void:
	_halo_material.set_shader_parameter("halo_color", _settings["color"])
	_halo_material.set_shader_parameter("halo_radius", float(_settings["radius"]))
	_halo_material.set_shader_parameter("halo_intensity", float(_settings["intensity"]))
	_halo_material.set_shader_parameter("halo_strength", _strength)


func _update_rect() -> void:
	var padding := float(_settings["radius"]) + 2.0
	position = _source_rect.position - Vector2.ONE * padding
	size = _source_rect.size + Vector2.ONE * padding * 2.0
	_halo_material.set_shader_parameter("source_size", _source_rect.size.max(Vector2.ONE))
	_halo_material.set_shader_parameter("halo_padding", padding)
	visible = texture != null and _source_rect.has_area() and _strength > 0.0 and float(_settings["radius"]) > 0.0 and float(_settings["intensity"]) > 0.0 and (_settings["color"] as Color).a > 0.0


static func _number_between(value: Variant, lower: float, upper: float) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= lower and float(value) <= upper


static func _valid_color(value: Color) -> bool:
	return _number_between(value.r, 0.0, 1.0) and _number_between(value.g, 0.0, 1.0) and _number_between(value.b, 0.0, 1.0) and _number_between(value.a, 0.0, 1.0)
