class_name WarmthVeil
extends CanvasLayer

## The screen says how warm the player is. A 2D layer over the finished frame,
## above the night vignette (20) and the hurt flash (21), under the HUD (30).
##
## Two veils, one shader. **Cold**: a pale frost creeps in from the edges as
## warmth falls under `COLD_ONSET` of the bar, full at none (where the cold
## takes health and the hurt flash throbs under it). **Hot**: an amber heat
## rises while the player stands at full warmth inside a fire's heat
## (`world.hot`, the sim's fact) with nothing left to gain, and lets go a step
## back. Both move with time constants, so a bar crossing the onset does not
## flicker and a step away is seen to cool. Like the hurt flash, this is read
## off the world and never asks the cause.
##
## No asset. The ramps are arithmetic; `set_mask` takes a generated overlay
## whose alpha is the shape when one is made.

const LAYER := 22
## Warmth, as a share of the bar, under which the frost begins.
const COLD_ONSET := 0.35
const COLD_SECONDS := 1.2
const HOT_ATTACK := 2.0
const HOT_RELEASE := 1.5
const COLD_ALPHA := 0.78
const HOT_ALPHA := 0.55

const SHADER := """
shader_type canvas_item;

// sRGB as written: a canvas_item shader never leaves that space.
uniform vec4 u_cold_colour = vec4(0.74, 0.86, 0.97, 1.0);
uniform vec4 u_hot_colour = vec4(0.96, 0.46, 0.12, 1.0);
uniform float u_cold = 0.0;
uniform float u_hot = 0.0;
uniform sampler2D u_mask;
uniform float u_has_mask = 0.0;

// The vignette's own ellipse (centre 0.5, 0.45; farthest-corner radii).
float edge(vec2 uv, float stop) {
	vec2 d = (uv - vec2(0.5, 0.45)) / vec2(0.70710678, 0.77781746);
	return clamp((length(d) - stop) / max(1.0 - stop, 1e-4), 0.0, 1.0);
}

void fragment() {
	// The frost reaches further in than the heat: cold closes the view down.
	float cold_ramp = pow(edge(SCREEN_UV, 0.18), 1.3);
	float hot_ramp = pow(edge(SCREEN_UV, 0.32), 1.4);
	if (u_has_mask > 0.5) {
		float m = texture(u_mask, SCREEN_UV).a;
		cold_ramp = m;
		hot_ramp = m;
	}
	float cold_a = u_cold * cold_ramp;
	float hot_a = u_hot * hot_ramp;
	float a = 1.0 - (1.0 - cold_a) * (1.0 - hot_a);
	vec3 colour = mix(u_cold_colour.rgb, u_hot_colour.rgb, hot_a / max(cold_a + hot_a, 1e-4));
	COLOR = vec4(colour, clamp(a, 0.0, 0.92));
}
"""

var rect: ColorRect = null

var _material: ShaderMaterial = null
var _cold: float = 0.0
var _hot: float = 0.0


func setup(_pkg, _world, _fu) -> void:
	layer = LAYER
	var shader := Shader.new()
	shader.code = SHADER
	_material = ShaderMaterial.new()
	_material.shader = shader
	_material.set_shader_parameter("u_cold_colour", Vector4(0.74, 0.86, 0.97, 1.0))
	_material.set_shader_parameter("u_hot_colour", Vector4(0.96, 0.46, 0.12, 1.0))
	_material.set_shader_parameter("u_cold", 0.0)
	_material.set_shader_parameter("u_hot", 0.0)
	_material.set_shader_parameter("u_has_mask", 0.0)
	rect = ColorRect.new()
	rect.name = "WarmthVeil"
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rect.material = _material
	add_child(rect)


## The with-asset pass: a generated overlay whose alpha is the shape; null
## returns to the arithmetic ramps.
func set_mask(texture: Texture2D) -> void:
	if _material == null:
		return
	_material.set_shader_parameter("u_mask", texture)
	_material.set_shader_parameter("u_has_mask", 1.0 if texture != null else 0.0)


func update(world, delta: float, _cam: Dictionary) -> void:
	if world == null or world.player == null:
		return
	var warmth_max := _limit(world)
	var share := clampf(float(world.player.warmth) / maxf(1.0, warmth_max), 0.0, 1.0)
	var cold_target := clampf((COLD_ONSET - share) / COLD_ONSET, 0.0, 1.0)
	if world.dead:
		cold_target = 0.0
	_cold = _toward(_cold, cold_target, delta / COLD_SECONDS)
	var hot_target := 1.0 if bool(world.hot) and not world.dead else 0.0
	_hot = _toward(_hot, hot_target, delta / (HOT_ATTACK if hot_target > _hot else HOT_RELEASE))
	if _material != null:
		_material.set_shader_parameter("u_cold", _cold * COLD_ALPHA)
		_material.set_shader_parameter("u_hot", _hot * HOT_ALPHA)


## The frost envelope: 0 above the onset, 1 at no warmth.
func cold() -> float:
	return _cold


## The heat envelope: 0 away from the fire, 1 after two seconds too close.
func hot() -> float:
	return _hot


func status() -> Dictionary:
	return {"veil": "cold %.2f hot %.2f" % [_cold, _hot]}


static func _toward(value: float, target: float, step: float) -> float:
	if value < target:
		return minf(target, value + step)
	return maxf(target, value - step)


static func _limit(world) -> float:
	var rules: Variant = (world.manifest as Dictionary).get("gameplay", {})
	if rules is Dictionary and (rules as Dictionary).get("warmth") is Dictionary:
		var value := float(((rules as Dictionary)["warmth"] as Dictionary).get("max", 0.0))
		if value > 0.0:
			return value
	return 100.0
