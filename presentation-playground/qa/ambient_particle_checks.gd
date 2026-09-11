extends SceneTree

## Provider-free behavioral checks for Sprite Particle Emitter, including the
## Ambient Particles use. Native host captures separately establish visual use.
const EMITTER := preload("res://addons/game_presentation/effects/particles/ambient_particles.gd")
const EPSILON := 0.0001
var _errors: Array[String] = []
var _square: Texture2D
var _wide: Texture2D


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_square = _texture(16, 16, Color.WHITE)
	_wide = _texture(24, 8, Color.ORANGE)
	_deterministic_time_and_art()
	_lifetime_drain_and_checkpoint()
	_capacity_and_long_steps()
	_explicit_motion_and_framing()
	_atomic_validation_and_reset()
	_fallback_raster_inputs()
	for issue: String in _errors:
		printerr("FAIL Sprite Particle Emitter: " + issue)
	if _errors.is_empty():
		print("PASS Sprite Particle Emitter: seeded seek, split steps, pause, texture replacement, bounded lifetimes and long steps, drain/checkpoint replay, explicit world geometry, camera admission, atomic validation, cleanup and procedural raster inputs.")
	quit(0 if _errors.is_empty() else 1)


func _texture(width: int, height: int, color: Color) -> Texture2D:
	var pixels := Image.create_empty(width, height, false, Image.FORMAT_RGBA8)
	pixels.fill(color)
	return ImageTexture.create_from_image(pixels)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _start(emitter: Control, options: Dictionary = {}, textures: Array[Texture2D] = []) -> void:
	var inputs: Array[Texture2D] = textures.duplicate()
	if inputs.is_empty():
		inputs.append(_square)
	var errors: Array[String] = emitter.start(Rect2(100, 150, 400, 300), inputs, options)
	_expect(errors.is_empty(), "Valid start must succeed: " + str(errors))


func _same_motion(first: Dictionary, second: Dictionary) -> bool:
	if absf(float(first.elapsed) - float(second.elapsed)) > EPSILON or first.particles.size() != second.particles.size():
		return false
	for index in first.particles.size():
		var a: Dictionary = first.particles[index]
		var b: Dictionary = second.particles[index]
		if a.birth_index != b.birth_index or not a.position.is_equal_approx(b.position):
			return false
		for key: String in ["age", "lifetime", "rotation", "scale", "sprite_size", "alpha"]:
			if absf(float(a[key]) - float(b[key])) > EPSILON:
				return false
	return true


func _deterministic_time_and_art() -> void:
	var whole := EMITTER.new()
	var split := EMITTER.new()
	var swapped := EMITTER.new()
	var options := {"seed": 998, "rate": 24.0}
	var inputs: Array[Texture2D] = [_square]
	_start(whole, options, inputs)
	_start(split, options)
	_start(swapped, options, [_wide, _square])
	options.seed = 444
	inputs.clear()
	whole.advance(6.25)
	for index in 100:
		split.advance(0.0625)
	swapped.seek(6.25)
	var expected: Dictionary = whole.get_state()
	_expect(_same_motion(expected, split.get_state()), "Whole and split time steps must produce identical active particles and motion.")
	_expect(_same_motion(expected, swapped.get_state()), "Seek and art-count replacement must preserve seeded motion.")
	_expect(expected.settings.seed == 998 and expected.texture_count == 1, "The start call must capture input settings and the texture array.")
	_expect(swapped.set_textures([_wide]).is_empty(), "Texture replacement must be accepted while emitting.")
	_expect(_same_motion(expected, swapped.get_state()), "Replacing textures on an active emitter must preserve every motion sample.")
	for particle: Dictionary in swapped.get_state().particles:
		_expect(is_equal_approx(particle.size.x / particle.size.y, 3.0), "Texture replacement must preserve the new art's aspect ratio.")
	var paused: Dictionary = split.get_state()
	split.advance(0.0)
	_expect(split.get_state() == paused, "A held clock must preserve the full state exactly.")
	whole.seek(0.5)
	whole.seek(6.25)
	_expect(whole.get_state() == expected, "Backward seek followed by replay must reconstruct the exact state.")
	whole.free()
	split.free()
	swapped.free()


func _lifetime_drain_and_checkpoint() -> void:
	var emitter := EMITTER.new()
	var restored := EMITTER.new()
	var options := {"rate": 10.0, "lifetime_min": 2.0, "lifetime_max": 2.0, "warmup": false, "seed": 71}
	_start(emitter, options)
	_expect(emitter.get_state().particle_count == 1, "Cold start must begin with only the first birth.")
	emitter.advance(0.5)
	_expect(emitter.get_state().particle_count == 6, "Rate must create six scheduled births by half a second.")
	var active: Dictionary = emitter.get_state()
	emitter.stop()
	var state: Dictionary = emitter.checkpoint()
	_expect(not emitter.get_state().emitting, "Stop must halt future births immediately.")
	_expect(_same_motion(active, emitter.get_state()), "Stopping must preserve currently living particles.")
	_start(restored, options)
	_expect(restored.restore_time(state).is_empty(), "A matching fresh emitter must accept its time checkpoint.")
	_expect(restored.get_state() == emitter.get_state(), "Checkpoint reconstruction must preserve the complete stopped state.")
	emitter.advance(1.0)
	restored.advance(1.0)
	_expect(emitter.get_state() == restored.get_state(), "Restored stopped emitters must drain identically.")
	_expect(emitter.get_state().particle_count == 6, "Stop must neither spawn new particles nor expire living particles early.")
	emitter.advance(2.0)
	_expect(emitter.get_state().particle_count == 0 and not emitter.visible, "Stopped particles must drain completely and hide the Control.")
	emitter.seek(0.25)
	_expect(emitter.get_state().emitting and emitter.get_state().particle_count == 3, "Seeking before a scheduled stop must reconstruct earlier emission.")
	emitter.seek(5.0)
	_expect(not emitter.get_state().emitting and emitter.get_state().particle_count == 0, "Forward seek must retain the stop clock.")
	_start(emitter, options)
	_expect(emitter.get_state().emitting and emitter.get_state().elapsed == 0.0 and emitter.get_state().particle_count == 1, "Restart must clear the stop clock and old particle state.")
	emitter.free()
	restored.free()


func _capacity_and_long_steps() -> void:
	var emitter := EMITTER.new()
	var direct := EMITTER.new()
	var options := {"rate": 128.0, "lifetime_min": 4.0, "lifetime_max": 4.0, "max_particles": 512, "seed": 92}
	_start(emitter, options)
	_start(direct, options)
	_expect(emitter.get_state().particle_count == 512, "Warmup must fill the bounded lifetime window immediately.")
	emitter.advance(1000000.25)
	direct.seek(1000000.25)
	_expect(emitter.get_state().particle_count == 512, "A million-second step must keep capacity bounded and the emitter running.")
	_expect(emitter.get_state() == direct.get_state(), "A long time step and direct seek must reconstruct identical particles.")
	for particle: Dictionary in emitter.get_state().particles:
		_expect(particle.age >= 0.0 and particle.age < 4.0 and particle.position.is_finite(), "Only living finite particles may survive a long step.")
	direct.seek(EMITTER.MAX_TIME)
	_expect(direct.get_state().particle_count == 512, "The maximum admitted clock must retain the bounded lifetime window.")
	var final_clock: Dictionary = direct.get_state()
	_expect(not direct.advance(1.0).is_empty() and direct.get_state() == final_clock, "Clock overflow must be refused without changing particles.")
	emitter.stop()
	emitter.advance(1000000.0)
	_expect(emitter.get_state().particle_count == 0, "Large post-stop steps must drain without replaying old births.")
	emitter.free()
	direct.free()


func _explicit_motion_and_framing() -> void:
	var emitter := EMITTER.new()
	var options := {
		"rate": 1.0, "lifetime_min": 4.0, "lifetime_max": 4.0, "warmup": false,
		"velocity_min": Vector2(10, -20), "velocity_max": Vector2(10, -20), "drift": Vector2.ZERO,
		"size_min": 24.0, "size_max": 24.0, "scale_end": 2.0, "tint": Color(1, 1, 1, 0.8),
		"fade_in": 0.25, "fade_out": 0.25,
	}
	var inputs: Array[Texture2D] = [_wide]
	_expect(emitter.start(Rect2(100, 200, 0, 0), inputs, options).is_empty(), "A point is a valid emission region.")
	emitter.seek(0.5)
	var state: Dictionary = emitter.get_state()
	var particle: Dictionary = state.particles[0]
	_expect(particle.position.is_equal_approx(Vector2(105, 190)), "Particles must move in explicit logical-world velocity units.")
	_expect(is_equal_approx(particle.scale, 1.125) and particle.size.is_equal_approx(Vector2(27, 9)), "Scale interpolation must preserve texture aspect ratio and logical size.")
	_expect(is_equal_approx(particle.alpha, 0.4), "Fade-in must smoothly multiply host tint opacity.")
	var camera := Transform2D(Vector2(1.5, 0), Vector2(0, 1.5), Vector2(-200, 45))
	_expect(emitter.present(camera).is_empty(), "Positive world-to-parent framing must be accepted.")
	_expect(emitter.get_state() == state, "Camera movement must never alter logical-world motion or its clock.")
	_expect(not emitter.present(Transform2D(0.2, Vector2.ZERO)).is_empty(), "Rotated framing outside the current camera contract must be refused.")
	_expect(not emitter.present(Transform2D(Vector2.ZERO, Vector2.ZERO, Vector2.ZERO)).is_empty(), "Noninvertible framing must be refused.")
	_expect(not emitter.present(Transform2D(Vector2(1, 0), Vector2(0, 1), Vector2(INF, 0))).is_empty(), "Nonfinite framing must be refused.")
	_expect(emitter.get_state() == state, "Rejected camera inputs must preserve current state.")
	emitter.free()


func _atomic_validation_and_reset() -> void:
	var emitter := EMITTER.new()
	_start(emitter)
	emitter.advance(0.5)
	var original: Dictionary = emitter.get_state()
	var invalid_options: Array[Dictionary] = [
		{"rate": 0.0}, {"rate": NAN}, {"rate": INF}, {"rate": "many"},
		{"max_particles": 0}, {"max_particles": 513}, {"max_particles": 2}, {"seed": 1.5},
		{"lifetime_min": 6.0, "lifetime_max": 2.0}, {"lifetime_min": 0.0},
		{"velocity_min": Vector2(99, 99)}, {"velocity_max": Vector2(INF, 1)}, {"drift": "up"},
		{"size_min": 100.0, "size_max": 5.0}, {"size_max": -5.0}, {"scale_end": 9.0},
		{"fade_in": -0.1}, {"fade_out": 1.1}, {"tint": Color(1, 1, 1, NAN)}, {"warmup": 1},
		{"unknown": 1}, {"spin_min": 30, "spin_max": 10},
	]
	var textures: Array[Texture2D] = [_square]
	for options: Dictionary in invalid_options:
		_expect(not emitter.start(Rect2(0, 0, 100, 100), textures, options).is_empty(), "Invalid settings must be refused: " + str(options))
		_expect(emitter.get_state() == original, "Rejected start must leave the live emitter unchanged.")
	_expect(not emitter.start(Rect2(0, 0, -1, 4), textures).is_empty(), "Negative region sizes must be refused.")
	_expect(not emitter.start(Rect2(NAN, 0, 1, 4), textures).is_empty(), "Nonfinite geometry must be refused.")
	_expect(not emitter.set_textures([]).is_empty(), "Empty texture replacement must be refused.")
	_expect(not emitter.set_textures([null]).is_empty(), "Null textures must be refused.")
	_expect(not emitter.advance(-1).is_empty() and not emitter.advance(INF).is_empty(), "Invalid deltas must be refused.")
	_expect(not emitter.seek(NAN).is_empty() and not emitter.seek(-1).is_empty(), "Invalid seeks must be refused.")
	_expect(not emitter.restore_time({"elapsed": 1.0}).is_empty(), "Incomplete checkpoints must be refused.")
	_expect(not emitter.restore_time({"elapsed": 1.0, "stopped_at": NAN}).is_empty(), "Nonfinite checkpoint stops must be refused.")
	_expect(emitter.get_state() == original, "Every rejected mutation must be atomic.")
	var leaked: Dictionary = emitter.get_state()
	leaked.settings.seed = 45
	leaked.particles.clear()
	_expect(emitter.get_state() == original, "Inspection must return detached dictionaries.")
	emitter.clear()
	var cleared: Dictionary = emitter.get_state()
	_expect(not cleared.configured and cleared.particle_count == 0 and cleared.texture_count == 0 and not emitter.visible and emitter.material == null, "Clear must release retained art, material, settings and samples.")
	_expect(not emitter.restore_time({"elapsed": 1.0, "stopped_at": -1.0}).is_empty(), "A cleared emitter requires explicit configuration before restore.")
	emitter.free()


func _fallback_raster_inputs() -> void:
	for kind: String in ["dust", "smoke", "ember", "spark"]:
		var textures: Array[Texture2D] = EMITTER.fallback_textures(kind)
		_expect(textures.size() >= 2, "Each fallback should provide interchangeable raster variants: " + kind)
		for texture: Texture2D in textures:
			var pixels := texture.get_image()
			_expect(pixels.get_pixel(0, 0).a < 0.01, "Fallback raster corners must be transparent: " + kind)
			_expect(pixels.get_pixel(pixels.get_width() / 2, pixels.get_height() / 2).a > 0.05, "Fallback raster must contain visible center content: " + kind)
			if kind in ["ember", "spark"]:
				_expect(texture.get_height() > texture.get_width() * 2, "Ember/spark inputs must have elongated silhouettes.")
	_expect(EMITTER.fallback_textures("unknown").is_empty(), "Unknown fallback names must not silently choose an art style.")
