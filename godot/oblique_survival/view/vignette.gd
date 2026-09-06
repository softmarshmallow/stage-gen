extends CanvasLayer

## The night vignette: the viewer's `#vignette` div, a CSS radial gradient over
## the whole frame whose opacity is `night * 0.85 * (1 - flash)`
## (index.html:33-34, :5536).
##
## This is the *night* vignette and is not the shader's `u_vignette`, which is
## the day one inside `apply_night`. Both are in the frame at once by design.
##
## The gradient is `radial-gradient(ellipse at 50% 45%, rgba(0,0,0,0) 30%,
## rgba(2,4,12,0.92) 100%)`. CSS sizes a `farthest-corner` ellipse so it passes
## through the farthest corner while keeping the farthest-side aspect: for a
## centre at (0.5, 0.45) the radii are sqrt(2) * (0.5, 0.55) of the box. The
## stops interpolate in premultiplied alpha, so the colour is constant and only
## the alpha ramps — which is the `smoothstep`-free linear ramp below.
##
## A `canvas_item` shader works on sRGB-encoded values (Godot's 2D pipeline is
## pass-through), which is exactly the space a browser composites a div in, so
## the numbers are the CSS numbers.

const SHADER := """
shader_type canvas_item;

// No `source_color`: a canvas_item shader never leaves sRGB, so the CSS
// numbers are used as written.
uniform vec4 u_colour = vec4(0.0078431, 0.0156863, 0.0470588, 1.0);
uniform float u_alpha = 0.92;
uniform float u_stop = 0.3;
uniform float u_opacity = 0.0;

void fragment() {
	vec2 centre = vec2(0.5, 0.45);
	vec2 radii = vec2(0.70710678, 0.77781746);
	vec2 d = (SCREEN_UV - centre) / radii;
	float t = clamp((length(d) - u_stop) / max(1.0 - u_stop, 1e-4), 0.0, 1.0);
	COLOR = vec4(u_colour.rgb, u_alpha * t * u_opacity);
}
"""

var rect: ColorRect = null

var _material: ShaderMaterial = null

func setup(_pkg, _world, _fu) -> void:
	layer = 20
	var shader := Shader.new()
	shader.code = SHADER
	_material = ShaderMaterial.new()
	_material.shader = shader
	# rgba(2, 4, 12, 0.92): the colour is written straight, in sRGB, because a
	# canvas_item shader never leaves that space. `source_color` would decode
	# it, so the uniform below is set as a raw vec4 instead.
	_material.set_shader_parameter("u_colour", Vector4(2.0 / 255.0, 4.0 / 255.0, 12.0 / 255.0, 1.0))
	_material.set_shader_parameter("u_alpha", 0.92)
	_material.set_shader_parameter("u_stop", 0.3)
	_material.set_shader_parameter("u_opacity", 0.0)
	rect = ColorRect.new()
	rect.name = "Vignette"
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rect.material = _material
	add_child(rect)

func update(world, _delta: float, _cam: Dictionary) -> void:
	if world == null:
		return
	set_opacity(float(world.night) * 0.85 * (1.0 - flash_of(world)))

## `night * 0.85 * (1 - flash)`, where `flash` is the strike envelope without
## the 0.85 the shaders scale it by.
func set_opacity(value: float) -> void:
	if _material != null:
		_material.set_shader_parameter("u_opacity", clampf(value, 0.0, 1.0))

static func flash_of(world) -> float:
	var weather: Variant = world.get("weather")
	if not (weather is Dictionary):
		return 0.0
	var manifest: Dictionary = world.manifest
	var seconds := 0.5
	var weather_block: Variant = manifest.get("weather")
	if weather_block is Dictionary and (weather_block as Dictionary).get("rain") is Dictionary:
		var rain: Dictionary = (weather_block as Dictionary)["rain"]
		if rain.get("strike") is Dictionary:
			seconds = float((rain["strike"] as Dictionary).get("flash_seconds", 0.5))
	var age: float = world.time - float((weather as Dictionary).get("flash_at", -99.0))
	if age < 0.0 or age > seconds:
		return 0.0
	if age < 0.05:
		return 1.0
	if age < 0.09:
		return 0.3
	if age < 0.16:
		return 0.9
	return maxf(0.0, 0.9 * (1.0 - (age - 0.16) / maxf(0.01, seconds - 0.16)))
