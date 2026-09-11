extends SceneTree

## Credential-free behavioral checks for the finite Radial Sprite Burst.
const BURST := preload("res://addons/game_presentation/effects/particles/sprite_burst.gd")
const EPSILON := 0.0001
var _errors: Array[String] = []
var _observations: Array[String] = []
var _square: Texture2D
var _wide: Texture2D


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_square = _texture(16, 16, Color.WHITE)
	_wide = _texture(24, 8, Color.ORANGE)
	_determinism_and_art_independence()
	_motion_and_lifetime()
	_overlapping_events_and_reset()
	_rejected_input_is_atomic()
	_capacity_is_bounded()
	for observation: String in _observations:
		print("PASS Radial Sprite Burst: " + observation)
	for issue: String in _errors:
		printerr("FAIL Radial Sprite Burst: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _texture(width: int, height: int, color: Color) -> Texture2D:
	var pixels := Image.create_empty(width, height, false, Image.FORMAT_RGBA8)
	pixels.fill(color)
	return ImageTexture.create_from_image(pixels)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _emit(controller: Control, options: Dictionary = {}, origin := Vector2(400, 300), textures: Array[Texture2D] = []) -> int:
	var inputs: Array[Texture2D] = textures.duplicate()
	if inputs.is_empty():
		inputs.append(_square)
	var result: Dictionary = controller.emit_burst(origin, inputs, options)
	_expect(result.errors.is_empty() and result.instance_id > 0, "Valid emission must succeed: " + str(result))
	return int(result.instance_id)


func _same_motion(first: Dictionary, second: Dictionary) -> bool:
	if absf(float(first.elapsed) - float(second.elapsed)) > EPSILON or first.particles.size() != second.particles.size():
		return false
	for index in first.particles.size():
		var a: Dictionary = first.particles[index]
		var b: Dictionary = second.particles[index]
		if not a.position.is_equal_approx(b.position):
			return false
		for key: String in ["rotation", "scale", "sprite_size", "alpha"]:
			if absf(float(a[key]) - float(b[key])) > EPSILON:
				return false
	return true


func _determinism_and_art_independence() -> void:
	var whole := BURST.new()
	var split := BURST.new()
	var swapped := BURST.new()
	var options := {"seed": 88, "count": 18}
	var inputs: Array[Texture2D] = [_square]
	_emit(whole, options, Vector2(400, 300), inputs)
	_emit(split, options)
	_emit(swapped, options, Vector2(400, 300), [_wide, _square])
	options.seed = 999
	options.count = 2
	inputs.clear()
	whole.advance(0.625)
	for index in 40:
		split.advance(0.015625)
	swapped.advance(0.625)
	var first: Dictionary = whole.get_state()[0]
	_expect(_same_motion(first, split.get_state()[0]), "Equivalent elapsed time must match regardless of frame subdivision.")
	_expect(_same_motion(first, swapped.get_state()[0]), "A changed texture count, art and aspect ratio must preserve motion/timing.")
	_expect(first.seed == 88 and first.settings.count == 18 and first.texture_count == 1, "Caller array/settings edits must not mutate captured events.")
	var exposed: Array[Dictionary] = whole.get_state()
	exposed[0].settings.seed = -99
	exposed[0].particles[0].position = Vector2.ZERO
	exposed.clear()
	_expect(whole.get_state()[0] == first, "Returned inspection data must be independent copies.")
	var saved: Array[Dictionary] = whole.get_state()
	whole.present(Transform2D(Vector2(2, 0), Vector2(0, 3), Vector2(23, -14)))
	whole.advance(0.0)
	for index in 20:
		whole.get_state()
	_expect(whole.get_state() == saved, "Present, sample and zero-delta calls must not advance world state.")
	for particle: Dictionary in swapped.get_state()[0].particles:
		var ratio: float = particle.size.x / particle.size.y
		_expect(is_equal_approx(ratio, 3.0 if particle.texture_index == 0 else 1.0), "All source aspect ratios must survive pop scaling.")
	var alternate := BURST.new()
	_emit(alternate, {"seed": 89, "count": 18})
	alternate.advance(0.625)
	_expect(not _same_motion(first, alternate.get_state()[0]), "Different seeds must yield a distinct distribution.")
	whole.free()
	split.free()
	swapped.free()
	alternate.free()
	_observations.append("seeded motion is frame-step independent; texture pools/settings are captured and art swaps preserve timing")


func _motion_and_lifetime() -> void:
	var burst := BURST.new()
	_emit(burst)
	var initial: Dictionary = burst.get_state()[0]
	_expect(initial.particles.size() == 16 and initial.elapsed == 0.0, "Default event begins with 16 particles at zero elapsed time.")
	for particle: Dictionary in initial.particles:
		_expect(particle.scale == 0.0 and particle.alpha == 1.0 and particle.size == Vector2.ZERO, "Pop begins at zero size with source alpha unmodified.")
	burst.advance(0.1)
	var early: Dictionary = burst.get_state()[0]
	burst.advance(0.5)
	var middle: Dictionary = burst.get_state()[0]
	burst.advance(0.5)
	var late: Dictionary = burst.get_state()[0]
	for index in initial.particles.size():
		var start: Dictionary = initial.particles[index]
		var a: Dictionary = early.particles[index]
		var b: Dictionary = middle.particles[index]
		var c: Dictionary = late.particles[index]
		_expect(a.scale == 1.0 and b.alpha == 1.0 and c.alpha > 0.0 and c.alpha < 0.2, "The short pop must finish before the late fade tail.")
		var origin: Vector2 = initial.origin
		_expect(a.position.distance_to(origin) > start.position.distance_to(origin) and b.position.distance_to(origin) > a.position.distance_to(origin) and c.position.distance_to(origin) > b.position.distance_to(origin), "Sprites must disperse outward monotonically.")
		_expect(b.position.distance_to(a.position) > c.position.distance_to(b.position), "Equal middle/late time spans must slow outward travel.")
	burst.advance(0.101)
	_expect(burst.get_state().is_empty() and not burst.visible, "Duration completion must remove sprites and hide the empty layer.")
	burst.advance(1000.0)
	_expect(burst.get_state().is_empty(), "Completed bursts must not respawn.")
	_emit(burst, {"spread_degrees": 0.0, "angle_degrees": 0.0, "pop_seconds": 0.0, "spin_degrees": 0.0})
	var straight_initial: Dictionary = burst.get_state()[0]
	burst.advance(0.3)
	var straight_later: Dictionary = burst.get_state()[0]
	for index in straight_initial.particles.size():
		var a: Dictionary = straight_initial.particles[index]
		var b: Dictionary = straight_later.particles[index]
		_expect(a.scale == 1.0 and b.position.x > a.position.x and a.position.y == b.position.y and a.rotation == b.rotation, "Zero spread/spin/pop must support immediate, unspun directional movement.")
	burst.advance(1.0e30)
	_expect(burst.get_state().is_empty(), "A huge valid delta must expire events in one bounded step.")
	burst.free()
	_observations.append("pop, outward ease-out, fade tail, directional variants and finite expiry are bounded and monotonic")


func _overlapping_events_and_reset() -> void:
	var burst := BURST.new()
	var first := _emit(burst)
	burst.advance(0.25)
	var saved: Dictionary = burst.get_state()[0]
	var second := _emit(burst, {"seed": 2}, Vector2(800, 500), [_wide])
	_expect(burst.get_state().size() == 2 and burst.get_state()[0] == saved and burst.get_state()[1].elapsed == 0.0, "New emissions must not restart or change an earlier event.")
	burst.cancel(first)
	_expect(burst.get_state().size() == 1 and burst.get_state()[0].instance_id == second, "Cancellation must remove only the named event.")
	var remaining: Array[Dictionary] = burst.get_state()
	burst.cancel(first)
	burst.cancel(-1)
	_expect(burst.get_state() == remaining, "Unknown/stale cancellation must be harmless.")
	burst.clear()
	_expect(burst.get_state().is_empty() and not burst.visible, "Clear must immediately empty/hide the layer.")
	var third := _emit(burst)
	burst.cancel(second)
	_expect(third > second and burst.get_state().size() == 1, "Clear must not reuse IDs that old callbacks could cancel.")
	burst.clear()
	_emit(burst, {"duration": 0.2})
	_emit(burst, {"duration": 0.8})
	burst.advance(0.3)
	_expect(burst.get_state().size() == 1 and is_equal_approx(burst.get_state()[0].elapsed, 0.3), "Simultaneous bursts must expire independently.")
	burst.free()
	_observations.append("overlap, staggered clocks, targeted cancellation and clear preserve independent event lifetimes")


func _rejected_input_is_atomic() -> void:
	var burst := BURST.new()
	var first := _emit(burst)
	burst.advance(0.2)
	var state: Array[Dictionary] = burst.get_state()
	var malformed: Array[Dictionary] = [
		{"unknown": 1}, {7: 1}, {"count": 0}, {"count": 129}, {"count": 1.5},
		{"count": true}, {"duration": NAN}, {"duration": INF}, {"duration": 0.0},
		{"duration": 31.0}, {"distance": -1.0}, {"distance": 8193},
		{"start_radius": -1}, {"spread_degrees": 361.0}, {"angle_degrees": INF},
		{"sprite_size": 0.0}, {"sprite_size": "large"}, {"pop_seconds": -1.0},
		{"pop_seconds": 2.0}, {"fade_start": 1.0}, {"spin_degrees": 36001}, {"seed": 1.5},
	]
	for options: Dictionary in malformed:
		var result: Dictionary = burst.emit_burst(Vector2.ZERO, [_square] as Array[Texture2D], options)
		_expect(result.instance_id == -1 and not result.errors.is_empty() and burst.get_state() == state, "Invalid options must reject without changing active bursts: " + str(options))
	for origin: Vector2 in [Vector2(INF, 0), Vector2(0, NAN)]:
		_expect(not burst.emit_burst(origin, [_square] as Array[Texture2D]).errors.is_empty() and burst.get_state() == state, "Non-finite origin must reject atomically.")
	var invalid_inputs: Array = [[], [null], [ImageTexture.new()]]
	var too_many: Array[Texture2D] = []
	too_many.resize(65)
	too_many.fill(_square)
	invalid_inputs.append(too_many)
	for inputs: Array in invalid_inputs:
		var typed: Array[Texture2D] = []
		typed.assign(inputs)
		_expect(not burst.emit_burst(Vector2.ZERO, typed).errors.is_empty() and burst.get_state() == state, "Empty/null/zero-size/oversized texture inputs must reject atomically.")
	for delta: float in [-0.01, INF, NAN]:
		_expect(not burst.advance(delta).is_empty() and burst.get_state() == state, "Invalid delta must leave every event unchanged.")
	var invalid_cameras: Array[Transform2D] = [
		Transform2D(0.1, Vector2.ZERO),
		Transform2D(Vector2(1, 0), Vector2(0.2, 1), Vector2.ZERO),
		Transform2D(Vector2(-1, 0), Vector2(0, 1), Vector2.ZERO),
		Transform2D(Vector2.ZERO, Vector2(0, 1), Vector2.ZERO),
		Transform2D(Vector2(1, 0), Vector2(0, 1), Vector2(INF, 0)),
	]
	for camera: Transform2D in invalid_cameras:
		_expect(not burst.present(camera).is_empty() and burst.get_state() == state, "Invalid camera must not mutate emission state.")
	var second := _emit(burst)
	_expect(second == first + 1, "Rejected emissions must not consume event IDs.")
	burst.free()
	_observations.append("invalid settings, textures, origin, elapsed delta and camera are rejected without mutation")


func _capacity_is_bounded() -> void:
	var burst := BURST.new()
	for index in 24:
		_emit(burst, {"count": 1})
	var event_state: Array[Dictionary] = burst.get_state()
	var full: Dictionary = burst.emit_burst(Vector2.ZERO, [_square] as Array[Texture2D])
	_expect(not full.errors.is_empty() and burst.get_state() == event_state, "The 25th concurrent event must reject without evicting existing ones.")
	burst.clear()
	for index in 8:
		_emit(burst, {"count": 128})
	var particle_state: Array[Dictionary] = burst.get_state()
	full = burst.emit_burst(Vector2.ZERO, [_square] as Array[Texture2D], {"count": 1})
	_expect(not full.errors.is_empty() and burst.get_state() == particle_state, "More than 1024 concurrent sprites must reject atomically.")
	burst.advance(2.0)
	_emit(burst, {"count": 128})
	_expect(burst.get_state().size() == 1, "Expiry must release capacity for subsequent bursts.")
	burst.free()
	_observations.append("event and particle caps reject overflow; expiry releases capacity")
