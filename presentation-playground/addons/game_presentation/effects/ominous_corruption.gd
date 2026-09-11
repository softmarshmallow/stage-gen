extends Control

## Procedural corruption over existing world content. Optional source alpha
## defines the affected silhouette; a null source defines an environmental area.
const CORRUPTION_SHADER := preload("res://addons/game_presentation/effects/shaders/ominous_corruption.gdshader")
const DEFAULTS := {
	"darkness": 0.58, "mist_strength": 0.72, "glow_strength": 0.12,
	"refraction_px": 1.6, "aura_px": 54.0, "tint": Color(0.55, 0.025, 0.055),
	"screen": false, "noise_texture": null,
}
var _settings: Dictionary = DEFAULTS.duplicate()
var _source: Texture2D
var _source_rect := Rect2()
var _strength := 0.0
var _time := 0.0
var _has_pattern_transform := false
var _pattern_to_parent := Transform2D.IDENTITY
var _copy := BackBufferCopy.new()
var _quad := ColorRect.new()
var _field_material := ShaderMaterial.new()


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	_copy.name = "CopyBehindCorruption"
	add_child(_copy)
	_quad.name = "OminousCorruption"
	_quad.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_field_material.shader = CORRUPTION_SHADER
	_quad.material = _field_material
	add_child(_quad)
	_update_uniforms()
	_update_rect()


## Partial, atomic configuration. Screen mode ignores source alpha and padding.
func configure(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in options:
		if not key is String or not DEFAULTS.has(key):
			errors.append("Unknown Ominous Corruption setting: " + str(key))
		elif key == "screen":
			if not options[key] is bool:
				errors.append("Ominous Corruption screen must be a bool.")
		elif key == "noise_texture":
			if options[key] != null and not options[key] is Texture2D:
				errors.append("Ominous Corruption noise_texture must be Texture2D or null.")
		elif key == "tint":
			if not options[key] is Color or not _valid_color(options[key]):
				errors.append("Ominous Corruption tint must be a finite Color in [0, 1].")
		elif key == "aura_px":
			if not _number_between(options[key], 0.0, 160.0):
				errors.append("Ominous Corruption aura_px must be in [0, 160].")
		elif key == "refraction_px":
			if not _number_between(options[key], 0.0, 24.0):
				errors.append("Ominous Corruption refraction_px must be in [0, 24].")
		elif not _number_between(options[key], 0.0, 1.0):
			errors.append("Ominous Corruption " + str(key) + " must be finite and in [0, 1].")
	if not errors.is_empty():
		return errors
	_settings.merge(options, true)
	_update_uniforms()
	_update_rect()
	return errors


## Accept any RGBA sprite or reusable mask. Only its alpha channel is sampled.
## Null selects an area; it does not disable the effect. Use clear() to disable.
func set_source(source: Texture2D) -> void:
	_source = source
	_field_material.set_shader_parameter("source_texture", source)
	_field_material.set_shader_parameter("use_source", source != null)


## Match the full texture's displayed rect, not its opaque pixel bounding box.
func set_rect(rect: Rect2) -> Array[String]:
	if not rect.position.is_finite() or not rect.size.is_finite() or rect.size.x <= 0.0 or rect.size.y <= 0.0:
		return ["Ominous Corruption rect must be finite with positive dimensions."]
	_source_rect = rect
	_update_rect()
	return []


## Bind procedural pixels to an authored world/camera transform. The source
## mask, aura support, and screen vignette retain their own parent-space rect.
func set_pattern_transform(pattern_to_parent: Transform2D) -> Array[String]:
	if not pattern_to_parent.x.is_finite() or not pattern_to_parent.y.is_finite() or not pattern_to_parent.origin.is_finite():
		return ["Ominous Corruption pattern transform must be finite."]
	if pattern_to_parent.x.y != 0.0 or pattern_to_parent.y.x != 0.0 or pattern_to_parent.x.x <= 0.0 or pattern_to_parent.y.y <= 0.0:
		return ["Ominous Corruption pattern transform requires positive axis-aligned scale and translation."]
	var determinant := pattern_to_parent.determinant()
	if not is_finite(determinant) or determinant <= 0.0:
		return ["Ominous Corruption pattern transform must be invertible within canvas precision."]
	var inverse := pattern_to_parent.affine_inverse()
	if not inverse.x.is_finite() or not inverse.y.is_finite() or not inverse.origin.is_finite():
		return ["Ominous Corruption pattern transform must have a finite inverse."]
	_pattern_to_parent = pattern_to_parent
	_has_pattern_transform = true
	_update_pattern_uniforms()
	return []


## Restore the original source-local pattern, following future rect positions.
func reset_pattern_transform() -> void:
	_has_pattern_transform = false
	_pattern_to_parent = Transform2D.IDENTITY
	_update_pattern_uniforms()


## Effective transform: unbound patterns begin at the source rect's origin.
func get_pattern_transform() -> Transform2D:
	return _pattern_to_parent if _has_pattern_transform else Transform2D(0.0, _source_rect.position)


func set_time(seconds: float) -> Array[String]:
	if not is_finite(seconds) or seconds < 0.0:
		return ["Ominous Corruption time must be finite and nonnegative."]
	_time = seconds
	_field_material.set_shader_parameter("field_time", _time)
	return []


func set_strength(value: float) -> Array[String]:
	if not _number_between(value, 0.0, 1.0):
		return ["Ominous Corruption strength must be finite and in [0, 1]."]
	_strength = value
	_field_material.set_shader_parameter("strength", _strength)
	_update_rect()
	return []


## Release source/geometry/pattern binding and reset time/strength; retain settings.
func clear() -> void:
	set_source(null)
	_source_rect = Rect2()
	_strength = 0.0
	_time = 0.0
	_has_pattern_transform = false
	_pattern_to_parent = Transform2D.IDENTITY
	_update_uniforms()
	_update_rect()


func get_settings() -> Dictionary:
	return _settings.duplicate()


func get_source() -> Texture2D:
	return _source


func get_source_rect() -> Rect2:
	return _source_rect


func get_strength() -> float:
	return _strength


func get_time() -> float:
	return _time


func _update_uniforms() -> void:
	for key: String in ["darkness", "mist_strength", "glow_strength", "refraction_px", "aura_px", "tint", "noise_texture"]:
		_field_material.set_shader_parameter(key, _settings[key])
	_field_material.set_shader_parameter("screen_mode", _settings["screen"])
	_field_material.set_shader_parameter("use_noise_texture", _settings["noise_texture"] != null)
	_field_material.set_shader_parameter("strength", _strength)
	_field_material.set_shader_parameter("field_time", _time)


func _update_rect() -> void:
	var padding := 0.0 if _settings["screen"] else float(_settings["aura_px"]) + 2.0
	position = _source_rect.position - Vector2.ONE * padding
	size = _source_rect.size + Vector2.ONE * padding * 2.0
	_quad.size = size
	_field_material.set_shader_parameter("source_size", _source_rect.size.max(Vector2.ONE))
	_field_material.set_shader_parameter("padding_px", padding)
	_update_pattern_uniforms()
	visible = _source_rect.has_area() and _strength > 0.0
	_copy.copy_mode = BackBufferCopy.COPY_MODE_VIEWPORT if visible else BackBufferCopy.COPY_MODE_DISABLED


func _update_pattern_uniforms() -> void:
	var inverse := get_pattern_transform().affine_inverse()
	_field_material.set_shader_parameter("source_origin", _source_rect.position)
	_field_material.set_shader_parameter("pattern_inverse_x", inverse.x)
	_field_material.set_shader_parameter("pattern_inverse_y", inverse.y)
	_field_material.set_shader_parameter("pattern_inverse_origin", inverse.origin)


static func _number_between(value: Variant, lower: float, upper: float) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= lower and float(value) <= upper


static func _valid_color(value: Color) -> bool:
	return _number_between(value.r, 0.0, 1.0) and _number_between(value.g, 0.0, 1.0) and _number_between(value.b, 0.0, 1.0) and _number_between(value.a, 0.0, 1.0)
