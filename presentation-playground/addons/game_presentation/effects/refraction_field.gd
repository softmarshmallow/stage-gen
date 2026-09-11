extends Control

## Localized screen refraction. Add after affected world content and before UI.
## Rects and displacement use the parent's logical pixels. The host owns time.
const FIELD_SHADER := preload("res://addons/game_presentation/effects/shaders/refraction_field.gdshader")
const DEFAULTS := {
	"mode": "barrier", "amplitude_px": 4.0, "tint": Color(0.48, 0.035, 0.065),
	"tint_strength": 0.055, "feather": 0.36, "noise_texture": null,
}
var _settings: Dictionary = DEFAULTS.duplicate()
var _source_rect := Rect2()
var _strength := 0.0
var _time := 0.0
var _copy := BackBufferCopy.new()
var _quad := ColorRect.new()
var _field_material := ShaderMaterial.new()


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	_copy.name = "CopyBehindField"
	add_child(_copy)
	_quad.name = "RefractionField"
	_quad.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_field_material.shader = FIELD_SHADER
	_quad.material = _field_material
	add_child(_quad)
	_update_uniforms()
	_update_rect()


## Partial, atomic configuration. Texture inputs are optional shared noise maps.
func configure(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in options:
		if not key is String or not DEFAULTS.has(key):
			errors.append("Unknown Refraction Field setting: " + str(key))
		elif key == "mode":
			if options[key] not in ["barrier", "heat"]:
				errors.append("Refraction Field mode must be barrier or heat.")
		elif key == "noise_texture":
			if options[key] != null and not options[key] is Texture2D:
				errors.append("Refraction Field noise_texture must be Texture2D or null.")
		elif key == "tint":
			if not options[key] is Color or not _valid_color(options[key]):
				errors.append("Refraction Field tint must be a finite Color in [0, 1].")
		elif key == "amplitude_px":
			if not _number_between(options[key], 0.0, 32.0):
				errors.append("Refraction Field amplitude_px must be in [0, 32].")
		elif not _number_between(options[key], 0.02 if key == "feather" else 0.0, 1.0):
			errors.append("Refraction Field " + str(key) + " is outside its finite range.")
	if not errors.is_empty():
		return errors
	_settings.merge(options, true)
	_update_uniforms()
	return errors


func set_rect(rect: Rect2) -> Array[String]:
	if not rect.position.is_finite() or not rect.size.is_finite() or rect.size.x <= 0.0 or rect.size.y <= 0.0:
		return ["Refraction Field rect must be finite with positive dimensions."]
	_source_rect = rect
	_update_rect()
	return []


func set_time(seconds: float) -> Array[String]:
	if not is_finite(seconds) or seconds < 0.0:
		return ["Refraction Field time must be finite and nonnegative."]
	_time = seconds
	_field_material.set_shader_parameter("field_time", _time)
	return []


func set_strength(value: float) -> Array[String]:
	if not _number_between(value, 0.0, 1.0):
		return ["Refraction Field strength must be finite and in [0, 1]."]
	_strength = value
	_field_material.set_shader_parameter("strength", _strength)
	_update_rect()
	return []


## Release geometry and reset time/strength; retain configuration for reuse.
func clear() -> void:
	_source_rect = Rect2()
	_strength = 0.0
	_time = 0.0
	_update_uniforms()
	_update_rect()


func get_settings() -> Dictionary:
	return _settings.duplicate()


func get_source_rect() -> Rect2:
	return _source_rect


func get_strength() -> float:
	return _strength


func get_time() -> float:
	return _time


func _update_uniforms() -> void:
	for key: String in ["amplitude_px", "tint", "tint_strength", "feather", "noise_texture"]:
		_field_material.set_shader_parameter(key, _settings[key])
	_field_material.set_shader_parameter("heat_mode", _settings["mode"] == "heat")
	_field_material.set_shader_parameter("use_noise_texture", _settings["noise_texture"] != null)
	_field_material.set_shader_parameter("strength", _strength)
	_field_material.set_shader_parameter("field_time", _time)


func _update_rect() -> void:
	position = _source_rect.position
	size = _source_rect.size
	_quad.size = size
	_field_material.set_shader_parameter("field_size", size.max(Vector2.ONE))
	visible = _source_rect.has_area() and _strength > 0.0
	# Copy the whole viewport: distorted samples may cross the local field edge.
	_copy.copy_mode = BackBufferCopy.COPY_MODE_VIEWPORT if visible else BackBufferCopy.COPY_MODE_DISABLED


static func _number_between(value: Variant, lower: float, upper: float) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= lower and float(value) <= upper


static func _valid_color(value: Color) -> bool:
	return _number_between(value.r, 0.0, 1.0) and _number_between(value.g, 0.0, 1.0) and _number_between(value.b, 0.0, 1.0) and _number_between(value.a, 0.0, 1.0)
