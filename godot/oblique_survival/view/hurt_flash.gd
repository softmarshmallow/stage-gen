class_name HurtFlash
extends CanvasLayer

## The screen bleeds when health does. A 2D layer over the finished frame,
## above the night vignette (20) and under the HUD (30), so it shows in the
## black night and never over a panel.
##
## Two shapes, one shader. A **punch**: a hound's bite (`hurt`), or any drop
## of `PUNCH_HEALTH` or more in a frame, floods the edges red and fades in
## `FLASH_SECONDS`. A **throb**: health falling a little every frame (the
## belly empty, the cold in) raises a slow red edge that beats at
## `THROB_HERTZ`, deeper the lower health is, and lets go over `THROB_RELEASE`
## seconds once the drain stops. The cause is never asked: a drop is a drop,
## so a source the sim grows later shows without touching this file.
##
## No asset. The ramp is arithmetic (`_edge` below); `set_mask` takes a
## generated overlay when one is made and the shader reads its alpha in place
## of the ramp, so the with-asset pass is a texture, not a rewrite.

const LAYER := 21
## The hound's bite is 10; a drop this large in one frame is a blow, not a drain.
const PUNCH_HEALTH := 3.0
const FLASH_SECONDS := 0.7
const THROB_HERTZ := 1.15
## How long after the last seen drop the throb is still "draining".
const DRAIN_MEMORY := 0.4
const THROB_ATTACK := 0.9
const THROB_RELEASE := 1.4
## The throb's opacity at full health and at none.
const THROB_HIGH := 0.6
const THROB_LOW := 0.85

const SHADER := """
shader_type canvas_item;

// sRGB as written: a canvas_item shader never leaves that space.
uniform vec4 u_colour = vec4(0.55, 0.05, 0.03, 1.0);
uniform float u_flash = 0.0;
uniform float u_throb = 0.0;
uniform sampler2D u_mask;
uniform float u_has_mask = 0.0;

// The vignette's own ellipse (centre 0.5, 0.45; farthest-corner radii), so
// the blood sits where the night sits.
float edge(vec2 uv, float stop) {
	vec2 d = (uv - vec2(0.5, 0.45)) / vec2(0.70710678, 0.77781746);
	return clamp((length(d) - stop) / max(1.0 - stop, 1e-4), 0.0, 1.0);
}

void fragment() {
	float flash_ramp = edge(SCREEN_UV, 0.12);
	// Steeper than the flood and starting further out: a border, not a wash.
	float throb_ramp = pow(edge(SCREEN_UV, 0.3), 1.5);
	if (u_has_mask > 0.5) {
		float m = texture(u_mask, SCREEN_UV).a;
		flash_ramp = m;
		throb_ramp = m * m;
	}
	// The punch also lays a thin wash over the whole frame, so the middle is not
	// untouched by a bite.
	float a = u_flash * (0.16 + 0.84 * flash_ramp) + u_throb * throb_ramp;
	COLOR = vec4(u_colour.rgb, clamp(a, 0.0, 0.95));
}
"""

var rect: ColorRect = null

var _material: ShaderMaterial = null
var _last_health: float = -1.0
var _flash: float = 0.0
var _throb: float = 0.0
var _drain_for: float = 0.0
var _beat_time: float = 0.0
var _punched: bool = false


func setup(_pkg, world, _fu) -> void:
	layer = LAYER
	var shader := Shader.new()
	shader.code = SHADER
	_material = ShaderMaterial.new()
	_material.shader = shader
	_material.set_shader_parameter("u_colour", Vector4(0.55, 0.05, 0.03, 1.0))
	_material.set_shader_parameter("u_flash", 0.0)
	_material.set_shader_parameter("u_throb", 0.0)
	_material.set_shader_parameter("u_has_mask", 0.0)
	rect = ColorRect.new()
	rect.name = "HurtFlash"
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	rect.material = _material
	add_child(rect)
	if world != null and world.player != null:
		_last_health = float(world.player.health)


## The with-asset pass: a generated overlay whose alpha is the shape; null
## returns to the arithmetic ramp.
func set_mask(texture: Texture2D) -> void:
	if _material == null:
		return
	_material.set_shader_parameter("u_mask", texture)
	_material.set_shader_parameter("u_has_mask", 1.0 if texture != null else 0.0)


func handle_event(event: Dictionary) -> void:
	if str(event.get("type", "")) == "hurt":
		punch()


## The flood, from the top: a blow landed.
func punch() -> void:
	_flash = 1.0
	_punched = true


func update(world, delta: float, _cam: Dictionary) -> void:
	if world == null or world.player == null:
		return
	var health := float(world.player.health)
	if _last_health < 0.0:
		_last_health = health
	var dropped := _last_health - health
	_last_health = health
	if delta > 0.0 and dropped > 0.0 and not world.dead:
		if dropped >= PUNCH_HEALTH and not _punched:
			punch()
		elif not _punched:
			_drain_for = DRAIN_MEMORY
	_punched = false
	_drain_for = maxf(0.0, _drain_for - delta)
	if _drain_for > 0.0 and not world.dead:
		if _throb == 0.0:
			# The beat starts with the drain, so the first pulse is a whole one.
			_beat_time = 0.0
		_throb = minf(1.0, _throb + delta / THROB_ATTACK)
	else:
		_throb = maxf(0.0, _throb - delta / THROB_RELEASE)
	_flash = maxf(0.0, _flash - delta / FLASH_SECONDS)
	_beat_time += delta
	var health_max := _limit(world)
	var low := 1.0 - clampf(health / maxf(1.0, health_max), 0.0, 1.0)
	var beat := pow(maxf(0.0, sin(_beat_time * TAU * THROB_HERTZ)), 3.0)
	var throb_alpha := _throb * lerpf(THROB_HIGH, THROB_LOW, low) * (0.55 + 0.45 * beat)
	if _material != null:
		_material.set_shader_parameter("u_flash", _flash * _flash)
		_material.set_shader_parameter("u_throb", throb_alpha)


## The punch envelope, 1 at the blow and 0 when it has faded.
func flash() -> float:
	return _flash


## The drain envelope, 0 when health is holding and 1 after a second of it going.
func throb() -> float:
	return _throb


func status() -> Dictionary:
	return {"hurt": "%.2f/%.2f" % [_flash, _throb]}


static func _limit(world) -> float:
	var rules: Variant = (world.manifest as Dictionary).get("gameplay", {})
	if rules is Dictionary and (rules as Dictionary).get("health") is Dictionary:
		var value := float(((rules as Dictionary)["health"] as Dictionary).get("max", 0.0))
		if value > 0.0:
			return value
	return 100.0
