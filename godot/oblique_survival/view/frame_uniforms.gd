class_name FrameUniforms
extends RefCounted
## Stands in for the web viewer's `sharedUniforms`: three shared the SAME uniform
## objects across every material, so one write reached every shader. Godot has
## no shared uniform object, so every material that includes
## `view/shaders/night.gdshaderinc` registers here and receives every frame value
## once per frame (`apply_frame`), and the once-per-boot values at registration
## (`apply_static`). Names and feeds follow maps/viewer-render.md section 5.

var materials: Array[ShaderMaterial] = []
## Static values, from the manifest (set once by the view owner at boot).
var static_values: Dictionary = {}
## Per-frame values (written by the frame owner from the world each frame).
var frame_values: Dictionary = {}

const FRAME_KEYS := ["u_time", "u_night", "u_light_intensity", "u_light_pos", "u_light_radius", "u_pool_pos", "u_rain", "u_snow", "u_flash"]

static func from_manifest(manifest: Dictionary, resolution: Vector2) -> FrameUniforms:
	var fu := FrameUniforms.new()
	var gameplay: Dictionary = manifest.get("gameplay", {})
	var night: Dictionary = gameplay.get("night", {})
	var campfire: Dictionary = gameplay.get("campfire", {})
	var weather: Dictionary = manifest.get("weather", {})
	var rain: Dictionary = weather.get("rain", {})
	var snow: Dictionary = weather.get("snow", {})
	var blend: Dictionary = manifest.get("ground", {}).get("splat", {}).get("blend", {})
	fu.static_values = {
		"u_night_tint": _vec3(night.get("tint", [0.35, 0.42, 0.70])),
		# Not the manifest's: the frame owner writes it from `--night-floor`.
		"u_night_floor": 0.0,
		"u_light_color": _vec3(campfire.get("light_color", [1.0, 0.72, 0.40])),
		"u_rain_tint": _vec3(rain.get("tint", [1.0, 1.0, 1.0])),
		"u_rain_desaturate": float(rain.get("desaturate", 0.0)),
		"u_snow_tint": _vec3(snow.get("tint", [1.0, 1.0, 1.0])),
		"u_snow_desaturate": float(snow.get("desaturate", 0.0)),
		"u_pool_radius": float(blend.get("pool_radius_meters", 9.0)),
		"u_pool_gain": float(blend.get("pool_gain", 0.0)),
		"u_vignette": float(blend.get("vignette", 0.0)),
		"u_resolution": resolution,
		"u_grade_lift": float(blend.get("grade_lift", 0.0)),
		"u_grade_warmth": float(blend.get("grade_warmth", 0.0)),
		"u_grade_desaturate": float(blend.get("grade_desaturate", 0.0)),
		"u_paper": float(blend.get("paper", 0.0)),
		"u_paper_px": float(blend.get("paper_px", 3.0)),
	}
	fu.frame_values = {
		"u_time": 0.0, "u_night": 0.0, "u_light_intensity": 0.0, "u_light_pos": Vector3.ZERO,
		"u_light_radius": 6.0, "u_pool_pos": Vector3.ZERO, "u_rain": 0.0, "u_snow": 0.0, "u_flash": 0.0,
	}
	return fu

static func _vec3(value) -> Vector3:
	if value is Array and value.size() >= 3:
		return Vector3(float(value[0]), float(value[1]), float(value[2]))
	return Vector3.ONE

## Register a material: it receives the static values now and the frame values every frame.
func register(material: ShaderMaterial) -> void:
	if material == null or materials.has(material):
		return
	materials.append(material)
	for key in static_values:
		material.set_shader_parameter(key, static_values[key])
	for key in frame_values:
		material.set_shader_parameter(key, frame_values[key])

func unregister(material: ShaderMaterial) -> void:
	materials.erase(material)

func set_static(key: String, value) -> void:
	static_values[key] = value
	for material in materials:
		material.set_shader_parameter(key, value)

func set_resolution(resolution: Vector2) -> void:
	set_static("u_resolution", resolution)

## The per-frame write, verbatim from the viewer's tick (:5520-5535):
## u_time = world.time, u_night = world.night, u_light_* from world.light,
## u_pool_pos = player, u_rain/u_snow from the weather, u_flash = envelope * 0.85.
func write_frame(values: Dictionary) -> void:
	for key in values:
		frame_values[key] = values[key]
	for material in materials:
		for key in values:
			material.set_shader_parameter(key, values[key])
