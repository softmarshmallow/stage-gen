extends SceneTree

const Drift := preload("res://addons/game_presentation/camera/camera_drift.gd")
const VIEW := Vector2(1280, 900)
const COVER := Rect2(-160, -110, 1600, 1120)
const EPSILON := 0.0001
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_motion_and_timing()
	_coverage_and_composition()
	_lifecycle_and_snapshots()
	_atomic_rejection()
	if _errors.is_empty():
		print("PASS Camera Drift: bounded continuous motion, zero onset, partition-independent timing, coverage-safe shared translation, lifecycle, snapshots, and atomic validation")
	else:
		for issue: String in _errors:
			printerr("FAIL Camera Drift: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _offset(camera: RefCounted) -> Vector2:
	var pose: Dictionary = camera.sample()
	return Vector2(float(pose["offset_x"]), float(pose["offset_y"]))


func _motion_and_timing() -> void:
	var camera := Drift.new()
	_expect(camera.start().is_empty(), "Default settings must start.")
	_expect(_offset(camera) == Vector2.ZERO and camera.is_active(), "A phased cue must begin at exactly zero translation.")
	camera.advance(0.001)
	_expect(_offset(camera).length() < 0.0001, "Onset must not jump into the phased vertical displacement.")
	var minimum := Vector2.ZERO
	var maximum := Vector2.ZERO
	var bounded := true
	for index in 12000:
		camera.advance(0.025)
		var offset := _offset(camera)
		minimum = minimum.min(offset)
		maximum = maximum.max(offset)
		bounded = bounded and offset.is_finite() and absf(offset.x) <= 8.0 + EPSILON and absf(offset.y) <= 5.0 + EPSILON
	_expect(bounded, "Ongoing samples must remain finite and within the authored amplitudes.")
	_expect(minimum.x < -7.0 and maximum.x > 7.0 and minimum.y < -4.0 and maximum.y > 4.0, "Both axes must drift on both sides of the original frame.")
	_expect(camera.is_active(), "Continuous drift must not complete by itself.")
	var whole := Drift.new()
	var split := Drift.new()
	whole.start({"period_x": 2.5, "period_y": 3.75, "phase_y": -2.0})
	split.start({"period_x": 2.5, "period_y": 3.75, "phase_y": -2.0})
	whole.advance(123.375)
	for index in 9870:
		split.advance(0.0125)
	_expect(_offset(whole).distance_to(_offset(split)) < EPSILON, "Splitting time must preserve the visible frame across repeated period wraps.")
	var state := camera.get_state()
	for index in 100:
		camera.sample()
	_expect(camera.get_state() == state, "Sampling must not mutate controller time or transforms.")
	camera.advance(1.0e300)
	_expect(_offset(camera).is_finite() and absf(_offset(camera).x) <= 8.0 and absf(_offset(camera).y) <= 5.0, "A huge finite delta must stay finite and bounded.")
	for settings: Dictionary in [
		{"amplitude_x": 64.0, "amplitude_y": 64.0, "period_x": 0.5, "period_y": 120.0, "phase_y": TAU},
		{"amplitude_x": 0.0, "amplitude_y": 0.0, "period_x": 120.0, "period_y": 0.5, "phase_y": -TAU},
	]:
		_expect(camera.start(settings).is_empty(), "Inclusive settings limits must be accepted.")
		camera.advance(1023.125)
		var offset := _offset(camera)
		_expect(offset.is_finite() and absf(offset.x) <= float(settings["amplitude_x"]) and absf(offset.y) <= float(settings["amplitude_y"]), "Settings limits must retain bounded output.")


func _coverage_and_composition() -> void:
	var geometries: Array[Rect2] = [COVER, Rect2(Vector2.ZERO, VIEW), Rect2(-400, 0, 1800, 900), Rect2(0, -300, 1280, 1600), Rect2(-3, -2, 1400, 1000)]
	var camera := Drift.new()
	camera.start({"amplitude_x": 64.0, "amplitude_y": 64.0})
	for geometry: Rect2 in geometries:
		_expect(Drift.can_cover(geometry, VIEW), "Valid base background must be recognized as covering.")
		var covered := true
		var relative_position_stable := true
		var portrait_base := Rect2(450, 50, 500, 1200)
		var relative_base := portrait_base.position - geometry.position
		for index in 1000:
			camera.advance(0.05)
			var offset := Drift.constrain_offset(geometry, VIEW, _offset(camera))
			var background := Rect2(geometry.position + offset, geometry.size)
			var portrait := Rect2(portrait_base.position + offset, portrait_base.size)
			covered = covered and background.grow(EPSILON).encloses(Rect2(Vector2.ZERO, VIEW))
			relative_position_stable = relative_position_stable and (portrait.position - background.position).distance_to(relative_base) < EPSILON
		_expect(covered, "Constrained drift must cover every viewport edge for " + str(geometry))
		_expect(relative_position_stable, "Shared translation must preserve portrait/background placement without accumulated movement.")
	_expect(Drift.constrain_offset(Rect2(Vector2.ZERO, VIEW), VIEW, Vector2(8, 5)) == Vector2.ZERO, "An exact-fit background must suppress drift.")
	for geometry: Rect2 in [Rect2(0, 0, 1200, 900), Rect2(10, 0, 1500, 1000), Rect2(0, 0, INF, 1000), Rect2(0, 0, -10, 1000)]:
		_expect(not Drift.can_cover(geometry, VIEW), "Host must be told to refuse non-covering or invalid base geometry.")
		_expect(Drift.constrain_offset(geometry, VIEW, Vector2(8, 5)) == Vector2.ZERO, "Invalid geometry must return a no-op offset.")
	_expect(not Drift.can_cover(COVER, Vector2.ZERO) and not Drift.can_cover(COVER, Vector2(NAN, 900)), "Invalid view dimensions must be refused.")
	_expect(Drift.constrain_offset(COVER, VIEW, Vector2(INF, 5)) == Vector2.ZERO, "Nonfinite requested motion must be suppressed.")


func _lifecycle_and_snapshots() -> void:
	var original := Drift.new()
	var independent := Drift.new()
	original.start({"phase_y": -1.4, "amplitude_x": 12.0})
	original.advance(17.125)
	_expect(not independent.is_active() and _offset(independent) == Vector2.ZERO, "Controller instances must remain independent.")
	var saved: Dictionary = JSON.parse_string(JSON.stringify(original.get_state()))
	_expect(independent.restore(saved).is_empty(), "A complete active JSON snapshot must restore.")
	_expect(_offset(original).distance_to(_offset(independent)) < EPSILON, "Restore must reproduce the visible frame.")
	for index in 200:
		original.advance(0.0625)
		independent.advance(0.0625)
	_expect(_offset(original).distance_to(_offset(independent)) < EPSILON, "Restored state must continue with identical motion.")
	var before := independent.get_state()
	saved["settings"]["amplitude_x"] = 64.0
	_expect(before == independent.get_state(), "Restored settings must not alias caller state.")
	var exposed := independent.get_state()
	exposed["settings"]["phase_y"] = 6.0
	_expect(before == independent.get_state(), "Returned settings must not expose mutable internals.")
	original.clear()
	_expect(not original.is_active() and _offset(original) == Vector2.ZERO, "Clear must immediately cancel to zero drift.")
	_expect(independent.restore(original.get_state()).is_empty() and not independent.is_active(), "An inactive snapshot must restore as inactive.")
	independent.advance(3.0)
	_expect(_offset(independent) == Vector2.ZERO, "Idle time must not generate motion.")
	original.start()
	_expect(_offset(original) == Vector2.ZERO and original.get_state()["settings"] == Drift.DEFAULT_SETTINGS, "Restart must use fresh defaults and a zero onset.")


func _atomic_rejection() -> void:
	var camera := Drift.new()
	camera.start()
	camera.advance(2.125)
	var before := camera.get_state()
	for settings: Dictionary in [{"amplitude_x": -1}, {"amplitude_y": 65}, {"period_x": 0}, {"period_y": 121}, {"phase_y": 7}, {"period_x": INF}, {"amplitude_y": NAN}, {"phase_y": "0.7"}, {"period_x": true}, {"unknown": 1}]:
		_expect(not camera.start(settings).is_empty() and camera.get_state() == before, "Invalid settings must be rejected without interrupting the cue: " + str(settings))
	for delta: float in [0.0, -1.0, NAN, INF, -INF]:
		camera.advance(delta)
		_expect(camera.get_state() == before, "Invalid deltas must preserve live state.")
	for mutation: Dictionary in [{"version": 2}, {"active": 1}, {"active": false}, {"time_x": -1}, {"time_y": 9.0}, {"time_x": INF}, {"onset_elapsed": NAN}, {"onset_elapsed": 1.01}, {"settings": {}}, {"settings": null}, {"extra": true}]:
		var malformed: Dictionary = before.duplicate(true)
		malformed.merge(mutation, true)
		_expect(not camera.restore(malformed).is_empty() and camera.get_state() == before, "Malformed state must be rejected atomically: " + str(mutation))
	for field: String in before:
		var missing: Dictionary = before.duplicate(true)
		missing.erase(field)
		_expect(not camera.restore(missing).is_empty() and camera.get_state() == before, "Each snapshot field must be required: " + field)
