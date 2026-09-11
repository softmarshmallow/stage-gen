extends SceneTree

const Shake := preload("res://addons/game_presentation/camera/impact_shake.gd")
const VIEW := Vector2(1280, 900)
const EPSILON := 0.001
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_motion()
	_composition()
	_snapshots_and_validation()
	if _errors.is_empty():
		print("PASS Impact Shake: deterministic finite motion, smooth onset and settlement, coverage-safe composition, snapshots, and atomic validation")
	else:
		for issue: String in _errors:
			printerr("FAIL Impact Shake: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _offset(camera: RefCounted) -> Vector2:
	var pose: Dictionary = camera.sample()
	return Vector2(float(pose.offset_x), float(pose.offset_y))


func _motion() -> void:
	var camera := Shake.new()
	_expect(camera.start().is_empty(), "Default cue must start.")
	_expect(camera.is_active() and _offset(camera) == Vector2.ZERO, "Onset must start exactly at zero.")
	camera.advance(0.00001)
	_expect(_offset(camera).length() < 0.0001, "First onset samples must settle smoothly from the base.")
	var peak := Vector2.ZERO
	var bounded := true
	for index in 1300:
		camera.advance(0.001)
		var pose: Dictionary = camera.sample()
		var offset := _offset(camera)
		peak = peak.max(offset.abs())
		bounded = bounded and offset.is_finite() and absf(offset.x) <= float(pose.max_offset_x) + EPSILON and absf(offset.y) <= float(pose.max_offset_y) + EPSILON
	_expect(bounded, "Every displacement must remain inside its envelope bound.")
	_expect(peak.x > 18.0 and peak.y > 14.0, "Default impact must visibly exceed gentle walking motion.")
	camera.advance(0.04998)
	_expect(camera.is_active() and _offset(camera).length() < 0.0001, "Tail must settle before completion.")
	camera.advance(1.0e300)
	_expect(not camera.is_active() and _offset(camera) == Vector2.ZERO, "Huge finite deltas must complete with neutral motion.")
	var whole := Shake.new()
	var split := Shake.new()
	whole.start({"seed": 173, "duration": 7.0})
	split.start({"seed": 173, "duration": 7.0})
	whole.advance(1.375)
	for index in 110:
		split.advance(0.0125)
	_expect(_offset(whole).distance_to(_offset(split)) < EPSILON, "Different frame partitions must preserve the same motion.")
	var before := whole.get_state()
	for index in 50:
		whole.sample()
	_expect(before == whole.get_state(), "Sampling must not advance time.")
	split.start({"seed": 174, "duration": 7.0})
	split.advance(1.375)
	_expect(_offset(whole).distance_to(_offset(split)) > 1.0, "Different seeds must give different motion.")
	whole.clear()
	_expect(not whole.is_active() and _offset(whole) == Vector2.ZERO, "Clear must cancel immediately.")
	_expect(split.is_active(), "Independent instances must retain their own state.")


func _composition() -> void:
	var geometry := Rect2(Vector2.ZERO, VIEW)
	var bases: Array[Transform2D] = [Transform2D.IDENTITY,
		Transform2D(Vector2(2.35, 0), Vector2(0, 2.35), Vector2.ZERO),
		Transform2D(Vector2(2.35, 0), Vector2(0, 2.35), VIEW * (1.0 - 2.35)),
		Transform2D(Vector2(1.2, 0), Vector2(0, 1.3), Vector2(-70, -150))]
	var camera := Shake.new()
	for base: Transform2D in bases:
		_expect(Shake.can_compose(base, geometry, VIEW), "Centered and edge-clamped base frames must be accepted.")
		camera.start({"amplitude_x": 128.0, "amplitude_y": 128.0})
		_expect(camera.compose(base, geometry, VIEW) == base, "Onset composition must leave the base exactly unchanged.")
		var covered := true
		for index in 1350:
			camera.advance(0.001)
			var composed := camera.compose(base, geometry, VIEW)
			var transformed := Rect2(composed * geometry.position, geometry.size * Vector2(composed.x.x, composed.y.y))
			covered = covered and transformed.grow(EPSILON).encloses(Rect2(Vector2.ZERO, VIEW))
		_expect(covered, "Maximum shake must retain background cover at every frame, including authored edge crops.")
		camera.advance(1.0)
		_expect(camera.compose(base, geometry, VIEW) == base, "Completion must restore the exact base with no accumulated zoom.")
	camera.start()
	camera.advance(0.08)
	var peak_transform := camera.compose(Transform2D.IDENTITY, geometry, VIEW)
	_expect(is_equal_approx(peak_transform.x.x, 1.0 + 44.0 / 900.0), "Peak guard zoom must use maximum amplitude, not the current jitter sample.")
	var near_end := Shake.new()
	near_end.start()
	near_end.advance(1.34999)
	var final_transform := near_end.compose(Transform2D.IDENTITY, geometry, VIEW)
	_expect(final_transform.origin.length() < EPSILON and absf(final_transform.x.x - 1.0) < EPSILON, "Overscan and displacement must both settle before completion.")
	for bad_base: Transform2D in [Transform2D(0.1, Vector2.ZERO), Transform2D(Vector2(-1, 0), Vector2(0, 1), Vector2.ZERO), Transform2D(0.0, Vector2(1, 0))]:
		_expect(not Shake.can_compose(bad_base, geometry, VIEW), "Rotation, mirrored scale, and uncovered bases must be refused.")
		_expect(camera.compose(bad_base, geometry, VIEW) == bad_base, "Invalid composition must leave the caller's base unchanged.")
	_expect(not Shake.can_compose(Transform2D.IDENTITY, geometry, Vector2.ZERO), "Zero viewport must be refused.")
	_expect(not Shake.can_compose(Transform2D.IDENTITY, Rect2(0, 0, INF, 900), VIEW), "Nonfinite geometry must be refused.")


func _snapshots_and_validation() -> void:
	var camera := Shake.new()
	camera.start({"seed": 92})
	camera.advance(0.3125)
	var before := camera.get_state()
	var restored := Shake.new()
	_expect(restored.restore(JSON.parse_string(JSON.stringify(before))).is_empty(), "JSON snapshot must restore.")
	_expect(_offset(camera).distance_to(_offset(restored)) < EPSILON, "Snapshot must preserve the visible frame.")
	camera.advance(0.125)
	restored.advance(0.125)
	_expect(_offset(camera).distance_to(_offset(restored)) < EPSILON, "Restored cue must continue identically.")
	before = camera.get_state()
	for bad: Dictionary in [{"amplitude_x": -1}, {"amplitude_y": 129}, {"frequency": INF}, {"duration": 0.05}, {"attack": 1.35}, {"seed": 0.5}, {"seed": true}, {"unknown": 1}]:
		_expect(not camera.start(bad).is_empty() and camera.get_state() == before, "Invalid start must preserve active state: " + str(bad))
	for delta: float in [0.0, -1.0, INF, NAN]:
		camera.advance(delta)
		_expect(camera.get_state() == before, "Invalid time must preserve active state.")
	for bad: Dictionary in [{"version": 2}, {"elapsed": -1}, {"elapsed": 50}, {"elapsed": 1.35}, {"active": false}, {"active": 1}, {"settings": {}}, {"settings": null}, {"extra": true}]:
		var changed := before.duplicate(true)
		changed.merge(bad, true)
		_expect(not camera.restore(changed).is_empty() and camera.get_state() == before, "Invalid restore must be atomic: " + str(bad))
	for field: String in before:
		var missing := before.duplicate(true)
		missing.erase(field)
		_expect(not camera.restore(missing).is_empty() and camera.get_state() == before, "Snapshot must require field: " + field)
	var exposed := camera.get_state()
	exposed.settings.seed = 700
	_expect(camera.get_state() == before, "Snapshots must not alias controller settings.")
	camera.clear()
	_expect(restored.restore(camera.get_state()).is_empty() and not restored.is_active(), "Cleared state must round-trip.")
	camera.start()
	camera.advance(20.0)
	_expect(restored.restore(camera.get_state()).is_empty() and not restored.is_active(), "Completed state must round-trip.")
