extends Control

## Sprite Particle Emitter: sustained, seeded sprites in supplied world geometry.
## Ambient dust and dramatic smoke/embers are host-owned uses of this mechanism.
## The host owns time, framing, textures, composition, and route checkpoints.
const MAX_PARTICLES := 512
const MAX_TEXTURES := 64
const MAX_TIME := 3153600000.0
const DEFAULTS := {
	"seed": 0, "max_particles": 256, "rate": 18.0,
	"lifetime_min": 3.0, "lifetime_max": 5.0,
	"velocity_min": Vector2(-12.0, -24.0), "velocity_max": Vector2(12.0, -10.0),
	"drift": Vector2(12.0, 5.0), "drift_frequency": 0.16,
	"spin_min": -20.0, "spin_max": 20.0,
	"size_min": 8.0, "size_max": 18.0, "scale_end": 1.0,
	"tint": Color(1.0, 0.94, 0.8, 0.55),
	"fade_in": 0.18, "fade_out": 0.35, "warmup": true, "additive": false,
}
static var _fallback_cache: Dictionary = {}
var _settings: Dictionary = {}
var _region := Rect2()
var _textures: Array[Texture2D] = []
var _particles: Array[Dictionary] = []
var _elapsed := 0.0
var _stopped_at := -1.0
var _camera := Transform2D.IDENTITY


func _init() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	visible = false


## A successful start atomically replaces the prior emitter and resets its clock.
## Settings and the texture array are copied; texture pixels remain host-owned.
func start(region: Rect2, textures: Array[Texture2D], options: Dictionary = {}) -> Array[String]:
	var errors := _validate_options(options)
	errors.append_array(_validate_textures(textures))
	if not region.position.is_finite() or not region.size.is_finite() or region.size.x < 0.0 or region.size.y < 0.0 or region.position.abs().x > 32768.0 or region.position.abs().y > 32768.0 or region.size.x > 32768.0 or region.size.y > 32768.0:
		errors.append("Sprite Particle Emitter region must be finite, nonnegative in size, and within 32768 logical pixels per component.")
	if not errors.is_empty():
		return errors
	_settings = DEFAULTS.duplicate()
	_settings.merge(options, true)
	_region = region
	_textures = textures.duplicate()
	_elapsed = 0.0
	_stopped_at = -1.0
	var blend := CanvasItemMaterial.new()
	blend.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD if bool(_settings["additive"]) else CanvasItemMaterial.BLEND_MODE_MIX
	material = blend
	_refresh()
	return []


## Pause by withholding advance. No engine process, GPU clock, or frame history.
func advance(delta: float) -> Array[String]:
	if not is_finite(delta) or delta < 0.0 or delta > MAX_TIME - _elapsed:
		return ["Sprite Particle Emitter delta must be finite, nonnegative, and keep elapsed time within 100 years."]
	if _settings.is_empty() or delta == 0.0:
		return []
	_elapsed += delta
	_refresh()
	return []


## Seek samples directly; cost depends on configured capacity, never elapsed time.
## A prior stop remains at its authored clock position during backward seeks.
func seek(elapsed: float) -> Array[String]:
	if not _between(elapsed, 0.0, MAX_TIME):
		return ["Sprite Particle Emitter elapsed must be finite and in [0, 100 years]."]
	if _settings.is_empty():
		return ["Sprite Particle Emitter must be started before seeking."]
	_elapsed = elapsed
	_refresh()
	return []


## Stop births at the current clock; existing particles finish their lifetimes.
## Restart with start; clear is the immediate interruption/reset operation.
func stop() -> void:
	if _settings.is_empty() or _stopped_at >= 0.0:
		return
	_stopped_at = _elapsed
	_refresh()


func clear() -> void:
	_settings.clear()
	_textures.clear()
	_particles.clear()
	_region = Rect2()
	_elapsed = 0.0
	_stopped_at = -1.0
	_camera = Transform2D.IDENTITY
	material = null
	_refresh()


## Art can change without restarting the emission clock or changing motion.
func set_textures(textures: Array[Texture2D]) -> Array[String]:
	var errors := _validate_textures(textures)
	if _settings.is_empty():
		errors.append("Sprite Particle Emitter must be started before changing textures.")
	if not errors.is_empty():
		return errors
	_textures = textures.duplicate()
	_refresh()
	return []


## World-to-parent framing. The host keeps this Control's own transform identity.
func present(camera: Transform2D) -> Array[String]:
	if not camera.x.is_finite() or not camera.y.is_finite() or not camera.origin.is_finite():
		return ["Sprite Particle Emitter camera must be finite."]
	if camera.x.y != 0.0 or camera.y.x != 0.0 or camera.x.x <= 0.0 or camera.y.y <= 0.0:
		return ["Sprite Particle Emitter camera requires positive axis-aligned scale and translation."]
	var determinant := camera.determinant()
	if not is_finite(determinant) or determinant <= 0.0:
		return ["Sprite Particle Emitter camera must be invertible within canvas precision."]
	var inverse := camera.affine_inverse()
	if not inverse.x.is_finite() or not inverse.y.is_finite() or not inverse.origin.is_finite():
		return ["Sprite Particle Emitter camera must have a finite inverse."]
	_camera = camera
	queue_redraw()
	return []


## Small in-session time checkpoint. The host restores the same region, seed,
## settings and art with start, then restores time. This is not a durable save.
func checkpoint() -> Dictionary:
	return {"elapsed": _elapsed, "stopped_at": _stopped_at}


func restore_time(state: Dictionary) -> Array[String]:
	if _settings.is_empty():
		return ["Sprite Particle Emitter must be started before restoring time."]
	if state.size() != 2 or not state.has("elapsed") or not state.has("stopped_at"):
		return ["Sprite Particle Emitter time checkpoint requires elapsed and stopped_at only."]
	if not _between(state["elapsed"], 0.0, MAX_TIME) or not (state["stopped_at"] is int or state["stopped_at"] is float):
		return ["Sprite Particle Emitter checkpoint times must be numeric and bounded."]
	var stopped_at := float(state["stopped_at"])
	if stopped_at != -1.0 and not _between(stopped_at, 0.0, MAX_TIME):
		return ["Sprite Particle Emitter stopped_at must be -1 or a finite bounded time."]
	_elapsed = float(state["elapsed"])
	_stopped_at = stopped_at
	_refresh()
	return []


## Detached logical-world samples; camera and texture resources are not exposed.
func get_state() -> Dictionary:
	return {
		"configured": not _settings.is_empty(), "elapsed": _elapsed,
		"stopped_at": _stopped_at, "emitting": not _settings.is_empty() and (_stopped_at < 0.0 or _elapsed < _stopped_at),
		"region": _region, "settings": _settings.duplicate(true),
		"texture_count": _textures.size(), "particle_count": _particles.size(),
		"particles": _particles.duplicate(true),
	}


func _refresh() -> void:
	_particles.clear()
	if not _settings.is_empty():
		var rate := float(_settings["rate"])
		var lifetime_max := float(_settings["lifetime_max"])
		var first := int(floor((_elapsed - lifetime_max) * rate)) + 1
		if not bool(_settings["warmup"]):
			first = maxi(first, 0)
		var last := int(floor(_elapsed * rate))
		if _stopped_at >= 0.0:
			last = mini(last, int(floor(_stopped_at * rate)))
		# Validation ensures the candidate lifetime window fits the hard capacity.
		# This clamp also guards rare floating-point boundary rounding.
		first = maxi(first, last - int(_settings["max_particles"]) + 1)
		for birth_index in range(first, last + 1):
			var sample := _sample(birth_index)
			if not sample.is_empty():
				_particles.append(sample)
	visible = not _particles.is_empty()
	queue_redraw()


func _sample(birth_index: int) -> Dictionary:
	var age := _elapsed - float(birth_index) / float(_settings["rate"])
	var rng := RandomNumberGenerator.new()
	rng.seed = int(_settings["seed"]) ^ (birth_index * 104729)
	var lifetime := rng.randf_range(float(_settings["lifetime_min"]), float(_settings["lifetime_max"]))
	if age < 0.0 or age >= lifetime:
		return {}
	var origin := _region.position + _region.size * Vector2(rng.randf(), rng.randf())
	var minimum: Vector2 = _settings["velocity_min"]
	var maximum: Vector2 = _settings["velocity_max"]
	var velocity := Vector2(rng.randf_range(minimum.x, maximum.x), rng.randf_range(minimum.y, maximum.y))
	var phase := Vector2(rng.randf_range(-PI, PI), rng.randf_range(-PI, PI))
	var frequency := TAU * float(_settings["drift_frequency"]) * rng.randf_range(0.7, 1.3)
	var drift: Vector2 = _settings["drift"]
	var offset := Vector2(sin(age * frequency + phase.x) - sin(phase.x), sin(age * frequency + phase.y) - sin(phase.y)) * drift
	var rotation := rng.randf_range(-PI, PI)
	var spin := deg_to_rad(rng.randf_range(float(_settings["spin_min"]), float(_settings["spin_max"])))
	var sprite_size := rng.randf_range(float(_settings["size_min"]), float(_settings["size_max"]))
	# A fixed random draw follows all motion draws regardless of input art count.
	var art_pick := rng.randf()
	var texture_index := mini(int(floor(art_pick * _textures.size())), _textures.size() - 1)
	var texture_size := _textures[texture_index].get_size()
	var progress := age / lifetime
	var scale := lerpf(1.0, float(_settings["scale_end"]), progress)
	var fade := 1.0
	if float(_settings["fade_in"]) > 0.0:
		fade *= smoothstep(0.0, float(_settings["fade_in"]), progress)
	if float(_settings["fade_out"]) > 0.0:
		fade *= smoothstep(0.0, float(_settings["fade_out"]), 1.0 - progress)
	var tint: Color = _settings["tint"]
	return {
		"birth_index": birth_index, "age": age, "lifetime": lifetime,
		"position": origin + velocity * age + offset,
		"rotation": rotation + spin * age, "scale": scale,
		"sprite_size": sprite_size, "size": texture_size / maxf(texture_size.x, texture_size.y) * sprite_size * scale,
		"alpha": tint.a * fade, "texture_index": texture_index,
	}


func _draw() -> void:
	for particle: Dictionary in _particles:
		if float(particle["alpha"]) <= 0.0 or float(particle["scale"]) <= 0.0:
			continue
		draw_set_transform_matrix(_camera * Transform2D(float(particle["rotation"]), particle["position"]))
		var sprite_size: Vector2 = particle["size"]
		var tint: Color = _settings["tint"]
		tint.a = float(particle["alpha"])
		draw_texture_rect(_textures[int(particle["texture_index"])], Rect2(-sprite_size * 0.5, sprite_size), false, tint)
	draw_set_transform_matrix(Transform2D.IDENTITY)


static func _validate_textures(textures: Array[Texture2D]) -> Array[String]:
	var errors: Array[String] = []
	if textures.is_empty() or textures.size() > MAX_TEXTURES:
		errors.append("Sprite Particle Emitter requires between 1 and 64 textures.")
	for texture: Texture2D in textures:
		if texture == null or texture.get_width() <= 0 or texture.get_height() <= 0:
			errors.append("Sprite Particle Emitter textures must have positive dimensions.")
	return errors


static func _validate_options(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	for key: Variant in options:
		if not key is String or not DEFAULTS.has(key):
			errors.append("Unknown Sprite Particle Emitter setting: " + str(key))
			continue
		var value: Variant = options[key]
		match key:
			"seed":
				if not value is int:
					errors.append("Sprite Particle Emitter seed must be an integer.")
			"max_particles":
				if not value is int or value < 1 or value > MAX_PARTICLES:
					errors.append("Sprite Particle Emitter max_particles must be an integer in [1, 512].")
			"rate":
				if not _between(value, 0.1, 128.0):
					errors.append("Sprite Particle Emitter rate must be in [0.1, 128] births per second.")
			"lifetime_min", "lifetime_max":
				if not _between(value, 0.05, 60.0):
					errors.append("Sprite Particle Emitter lifetimes must be in [0.05, 60] seconds.")
			"velocity_min", "velocity_max", "drift":
				if not value is Vector2 or not value.is_finite() or value.abs().x > 8192.0 or value.abs().y > 8192.0:
					errors.append("Sprite Particle Emitter velocity and drift must be finite Vector2 values within 8192 pixels per component.")
			"drift_frequency":
				if not _between(value, 0.0, 10.0):
					errors.append("Sprite Particle Emitter drift_frequency must be in [0, 10] cycles per second.")
			"spin_min", "spin_max":
				if not _between(value, -36000.0, 36000.0):
					errors.append("Sprite Particle Emitter spin must be in [-36000, 36000] degrees per second.")
			"size_min", "size_max":
				if not _between(value, 0.1, 2048.0):
					errors.append("Sprite Particle Emitter sizes must be in [0.1, 2048] logical pixels.")
			"scale_end":
				if not _between(value, 0.0, 8.0):
					errors.append("Sprite Particle Emitter scale_end must be in [0, 8].")
			"fade_in", "fade_out":
				if not _between(value, 0.0, 1.0):
					errors.append("Sprite Particle Emitter fade fractions must be in [0, 1].")
			"warmup", "additive":
				if not value is bool:
					errors.append("Sprite Particle Emitter warmup and additive must be booleans.")
			"tint":
				if not value is Color or not _between(value.r, 0.0, 1.0) or not _between(value.g, 0.0, 1.0) or not _between(value.b, 0.0, 1.0) or not _between(value.a, 0.0, 1.0):
					errors.append("Sprite Particle Emitter tint must be a finite Color with channels in [0, 1].")
	if not errors.is_empty():
		return errors
	var settings := DEFAULTS.duplicate()
	settings.merge(options, true)
	for pair: Array in [["lifetime_min", "lifetime_max"], ["spin_min", "spin_max"], ["size_min", "size_max"]]:
		if float(settings[pair[0]]) > float(settings[pair[1]]):
			errors.append("Sprite Particle Emitter minimum exceeds maximum: " + str(pair[0]))
	var minimum: Vector2 = settings["velocity_min"]
	var maximum: Vector2 = settings["velocity_max"]
	if minimum.x > maximum.x or minimum.y > maximum.y:
		errors.append("Sprite Particle Emitter velocity_min must not exceed velocity_max per component.")
	if ceilf(float(settings["rate"]) * float(settings["lifetime_max"])) > float(settings["max_particles"]):
		errors.append("Sprite Particle Emitter capacity must cover ceil(rate * lifetime_max), up to 512 particles.")
	return errors


static func _between(value: Variant, lower: float, upper: float) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= lower and float(value) <= upper


## Replaceable code-authored raster fixtures, never a required particle type.
## Returned resources are shared immutable inputs; callers may tint at emission.
static func fallback_textures(kind: String) -> Array[Texture2D]:
	var result: Array[Texture2D] = []
	if kind not in ["dust", "smoke", "ember", "spark"]:
		return result
	if not _fallback_cache.has(kind):
		var generated: Array[Texture2D] = []
		for variant in (3 if kind == "smoke" else 2):
			generated.append(_make_fallback(kind, variant))
		_fallback_cache[kind] = generated
	result.assign(_fallback_cache[kind])
	return result


static func _make_fallback(kind: String, variant: int) -> Texture2D:
	var dimensions := Vector2i(64, 64)
	if kind == "smoke":
		dimensions = Vector2i(112, 112)
	elif kind == "ember":
		dimensions = Vector2i(32, 80)
	elif kind == "spark":
		dimensions = Vector2i(24, 96)
	var pixels := Image.create_empty(dimensions.x, dimensions.y, false, Image.FORMAT_RGBA8)
	for y in dimensions.y:
		for x in dimensions.x:
			var p := (Vector2(x, y) + Vector2.ONE * 0.5) / Vector2(dimensions) * 2.0 - Vector2.ONE
			var pixel := Color.WHITE
			match kind:
				"dust":
					var core := exp(-p.length_squared() * (18.0 if variant == 0 else 32.0))
					var rays := exp(-absf(p.x) * 38.0 - absf(p.y) * 5.5) + exp(-absf(p.y) * 38.0 - absf(p.x) * 5.5)
					pixel.a = clampf(core * 0.7 + rays * 0.28, 0.0, 1.0) * (1.0 - smoothstep(0.7, 1.0, p.length()))
				"smoke":
					var phase := float(variant) * 1.9
					var density := 0.0
					for lobe in 7:
						var angle := float(lobe) * TAU / 7.0 + phase
						var center := Vector2(cos(angle), sin(angle)) * (0.30 + 0.12 * sin(float(lobe) * 2.7 + phase))
						var local := (p - center) * Vector2(1.0 + 0.18 * sin(angle), 1.0 + 0.2 * cos(angle))
						density += exp(-local.length_squared() * (6.0 + float(lobe % 3))) * 0.25
					var billow := sin(p.x * 11.0 + sin(p.y * 8.0 + phase) + phase) * sin(p.y * 12.0 - p.x * 3.0) * 0.13
					var grain := sin(p.x * 39.0 + p.y * 21.0 + phase) * sin(p.y * 29.0 - p.x * 19.0) * 0.028
					var edge := 1.0 - smoothstep(0.65, 0.99, p.length())
					var shade := clampf(0.80 + billow + grain, 0.5, 1.0)
					pixel = Color(shade, shade, shade, clampf(density * (0.8 + billow + grain) * edge, 0.0, 0.85))
				"ember":
					var center := 0.13 * sin(p.y * 3.0 + float(variant))
					var width := 0.16 + 0.13 * (1.0 - p.y) * 0.5
					var body := exp(-pow((p.x - center) / width, 2.0) * 2.0) * pow(maxf(0.0, 1.0 - p.y * p.y), 1.7)
					var heat := exp(-p.length_squared() * 5.0)
					pixel = Color(1.0, 0.32 + 0.55 * heat, 0.06 + 0.48 * heat, body)
				"spark":
					var body := exp(-p.x * p.x * (55.0 if variant == 0 else 85.0)) * pow(maxf(0.0, 1.0 - p.y * p.y), 2.0)
					pixel = Color(1.0, 0.82, 0.42, body)
			pixels.set_pixel(x, y, pixel)
	return ImageTexture.create_from_image(pixels)
