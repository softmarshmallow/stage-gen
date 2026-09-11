extends SceneTree

## Offline behavior checks for the asset-agnostic Walking Approach controller.
## Run: Godot --headless --path godot/games/playground --script res://qa/walking_approach_checks.gd
const CAMERA_PATH := "res://addons/game_presentation/camera/walking_approach.gd"
const VIEW := Vector2(1280, 900)
const COVER := Rect2(-160, -110, 1600, 1120)
const EPSILON := 0.0001
var _camera_script: Script
var _errors: Array[String] = []
var _observations: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_camera_script = load(CAMERA_PATH)
	if _camera_script == null or not _camera_script.can_instantiate():
		printerr("FAIL Walking Approach: controller must load and instantiate.")
		quit(1)
		return
	_motion_and_timing()
	_background_coverage()
	_lifecycle_and_isolation()
	_snapshot_continuation()
	_rejected_input_is_atomic()
	if _errors.is_empty():
		for observation: String in _observations:
			print("PASS Walking Approach: " + observation)
	else:
		for issue: String in _errors:
			printerr("FAIL Walking Approach: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _make(view: Vector2 = VIEW, background: Rect2 = COVER, settings: Dictionary = {}) -> RefCounted:
	var camera: RefCounted = _camera_script.new()
	_expect((camera.call("initialize", view, background) as Array).is_empty(), "Valid background geometry must initialize.")
	_expect((camera.call("configure", settings) as Array).is_empty(), "Valid settings must configure: " + str(settings))
	return camera


func _start(camera: RefCounted, settings: Dictionary = {}) -> void:
	_expect((camera.call("start", settings) as Array).is_empty(), "A valid Walking Approach must start.")


func _pose_equal(first: Dictionary, second: Dictionary) -> bool:
	for field: String in ["zoom", "offset_x", "offset_y", "bob_y", "progress"]:
		if not first.has(field) or not second.has(field) or absf(float(first[field]) - float(second[field])) > EPSILON:
			return false
	return first.get("active") == second.get("active")


func _is_finite_pose(pose: Dictionary) -> bool:
	for field: String in ["zoom", "offset_x", "offset_y", "bob_y", "progress"]:
		if not (pose.get(field) is float or pose.get(field) is int) or not is_finite(float(pose[field])):
			return false
	return pose.get("active") is bool


func _motion_and_timing() -> void:
	var camera := _make()
	_start(camera)
	var beginning: Dictionary = camera.call("sample")
	_expect(is_equal_approx(float(beginning["zoom"]), 1.0) and is_zero_approx(float(beginning["offset_x"])) and is_zero_approx(float(beginning["offset_y"])), "An approach starts at the original wide transform.")
	_expect(is_zero_approx(float(beginning["bob_y"])) and bool(beginning["active"]), "The first sample is active without an initial vertical jump.")
	var minimum_bob := 0.0
	var maximum_bob := 0.0
	var previous_zoom := 1.0
	var zoom_progresses := true
	for index in 660:
		camera.call("advance", 5.5 / 660.0)
		var pose: Dictionary = camera.call("sample")
		minimum_bob = minf(minimum_bob, float(pose["bob_y"]))
		maximum_bob = maxf(maximum_bob, float(pose["bob_y"]))
		zoom_progresses = zoom_progresses and float(pose["zoom"]) >= previous_zoom - EPSILON
		previous_zoom = float(pose["zoom"])
	_expect(zoom_progresses, "The push-in must approach its target without reversing zoom.")
	_expect(minimum_bob < -1.0 and maximum_bob > 1.0, "A normal shot must visibly bob in both vertical directions.")
	var bobbed := _make()
	var still := _make(VIEW, COVER, {"bob_amplitude": 0.0})
	_start(bobbed)
	_start(still)
	var reported_bob_is_applied := true
	for index in 110:
		bobbed.call("advance", 0.05)
		still.call("advance", 0.05)
		var moving_pose: Dictionary = bobbed.call("sample")
		var still_pose: Dictionary = still.call("sample")
		reported_bob_is_applied = reported_bob_is_applied and absf(float(moving_pose["offset_y"]) - float(still_pose["offset_y"]) - float(moving_pose["bob_y"])) < 0.001
	_expect(reported_bob_is_applied, "Reported walking bob must be part of the output transform, so the rendered background actually moves.")
	var held: Dictionary = camera.call("sample")
	_expect(not bool(camera.call("is_active")) and not bool(held["active"]), "A shot ends when its authored duration elapses.")
	_expect(is_equal_approx(float(held["zoom"]), 1.24) and is_equal_approx(float(held["progress"]), 1.0), "The held shot reaches its authored zoom and full progress.")
	_expect(is_zero_approx(float(held["bob_y"])), "Walking bob settles completely at the held endpoint.")
	for index in 200:
		camera.call("advance", 0.25)
	_expect(_pose_equal(held, camera.call("sample")), "Completed shots hold their exact endpoint without accumulated drift.")
	var whole_step := _make()
	var split_step := _make()
	_start(whole_step)
	_start(split_step)
	whole_step.call("advance", 2.375)
	for index in 190:
		split_step.call("advance", 0.0125)
	_expect(_pose_equal(whole_step.call("sample"), split_step.call("sample")), "The same elapsed time must produce the same frame regardless of frame splitting.")
	var before_sampling: Dictionary = split_step.call("get_state")
	for index in 100:
		split_step.call("sample")
	_expect(before_sampling == split_step.call("get_state"), "Sampling must not advance or accumulate camera motion.")
	var settling := _make()
	_start(settling)
	settling.call("advance", 5.5 - 0.001)
	var almost_held: Dictionary = settling.call("sample")
	settling.call("advance", 0.001)
	var final_pose: Dictionary = settling.call("sample")
	_expect(absf(float(almost_held["offset_y"]) - float(final_pose["offset_y"])) < 0.1, "The last motion frame must meet its held pose without a visible snap.")
	_observations.append("vertical walking bob, gradual push-in, deterministic time, and a stable settled endpoint")


func _background_coverage() -> void:
	var geometries: Array[Dictionary] = [
		{"name": "exact fit", "view": VIEW, "background": Rect2(Vector2.ZERO, VIEW)},
		{"name": "landscape cover", "view": VIEW, "background": Rect2(-280, 0, 1840, 900)},
		{"name": "portrait source cover", "view": VIEW, "background": Rect2(0, -550, 1280, 2000)},
		{"name": "portrait viewport", "view": Vector2(720, 1280), "background": Rect2(-450, -30, 1620, 1340)},
		{"name": "off-center cover", "view": VIEW, "background": Rect2(-310, -15, 1700, 1190)},
	]
	for geometry: Dictionary in geometries:
		for duration: float in [1.0, 15.0]:
			for zoom: float in [1.0, 1.8]:
				for amplitude: float in [0.0, 40.0]:
					for cadence: float in [0.5, 3.0]:
						var settings := {"duration_seconds": duration, "target_zoom": zoom, "bob_amplitude": amplitude, "bob_cycles_per_second": cadence}
						var camera := _make(geometry["view"], geometry["background"], settings)
						_start(camera)
						var all_covered := true
						var all_finite := true
						var bounded_bob := true
						for index in 601:
							var pose: Dictionary = camera.call("sample")
							all_finite = all_finite and _is_finite_pose(pose)
							var background: Rect2 = geometry["background"]
							var transformed := Rect2(background.position * float(pose["zoom"]) + Vector2(float(pose["offset_x"]), float(pose["offset_y"])), background.size * float(pose["zoom"]))
							all_covered = all_covered and transformed.grow(EPSILON).encloses(Rect2(Vector2.ZERO, geometry["view"]))
							bounded_bob = bounded_bob and absf(float(pose["bob_y"])) <= amplitude + EPSILON
							camera.call("advance", duration / 600.0)
						var description := String(geometry["name"]) + " " + str(settings)
						_expect(all_finite, "Every output must remain finite: " + description)
						_expect(all_covered, "The final composed zoom and bob must never expose an uncovered edge: " + description)
						_expect(bounded_bob, "Coverage adaptation must respect the requested maximum bob: " + description)
	_observations.append("background coverage across five geometries and every combination of settings limits")


func _lifecycle_and_isolation() -> void:
	var camera := _make()
	var companion := _make()
	var idle: Dictionary = companion.call("sample")
	var defaults: Dictionary = camera.call("get_settings")
	_start(camera, {"target_zoom": 1.5})
	camera.call("advance", 1.8)
	_expect(_pose_equal(idle, companion.call("sample")), "A camera's running state must not affect another instance.")
	_expect(defaults == camera.call("get_settings"), "Per-shot overrides must not mutate configured defaults.")
	var before_configuration: Dictionary = camera.call("sample")
	_expect((camera.call("configure", {"duration_seconds": 2.0, "target_zoom": 1.1}) as Array).is_empty(), "A host can configure its next shot while the current shot is active.")
	_expect(_pose_equal(before_configuration, camera.call("sample")), "Configuring the next shot must not change the active shot's timing or pose.")
	camera.call("skip")
	var skipped: Dictionary = camera.call("sample")
	_expect(not bool(skipped["active"]) and is_equal_approx(float(skipped["zoom"]), 1.5) and is_zero_approx(float(skipped["bob_y"])), "Skip must immediately settle the running shot at its own target.")
	camera.call("skip")
	_expect(_pose_equal(skipped, camera.call("sample")), "Repeated skip must preserve the held endpoint.")
	_start(camera)
	var replay: Dictionary = camera.call("sample")
	_expect(is_equal_approx(float(replay["zoom"]), 1.0) and is_zero_approx(float(replay["progress"])) and is_zero_approx(float(replay["bob_y"])), "Replay begins from a clean wide pose with no carried-over bob.")
	camera.call("advance", 2.0)
	var configured_end: Dictionary = camera.call("sample")
	_expect(not bool(configured_end["active"]) and is_equal_approx(float(configured_end["zoom"]), 1.1), "The next shot must use the newly configured timing and target.")
	camera.call("clear")
	_expect(_pose_equal(idle, camera.call("sample")), "Clear must restore the idle wide transform.")
	camera.call("skip")
	_expect(_pose_equal(idle, camera.call("sample")), "Skipping an idle camera must not synthesize an unrequested shot.")
	var exposed_settings: Dictionary = camera.call("get_settings")
	exposed_settings["target_zoom"] = 1.8
	_expect(is_equal_approx(float((camera.call("get_settings") as Dictionary)["target_zoom"]), 1.1), "Returned settings must not expose mutable internal state.")
	var never_initialized: RefCounted = _camera_script.new()
	_expect(not (never_initialized.call("start") as Array).is_empty(), "A shot must require initialized geometry.")
	_expect((never_initialized.call("configure", {"target_zoom": 1.6}) as Array).is_empty(), "Settings may be authored before geometry is supplied.")
	_expect((never_initialized.call("initialize", VIEW, COVER) as Array).is_empty(), "Previously configured camera must initialize.")
	_start(never_initialized)
	never_initialized.call("skip")
	_expect(is_equal_approx(float((never_initialized.call("sample") as Dictionary)["zoom"]), 1.6), "Initialization must preserve authored settings.")
	_observations.append("isolated instances, per-shot overrides, next-shot configuration, skip, replay, and reset")


func _snapshot_continuation() -> void:
	var original := _make(VIEW, COVER, {"target_zoom": 1.7})
	_start(original, {"duration_seconds": 7.0, "bob_amplitude": 30.0})
	original.call("advance", 2.125)
	original.call("configure", {"target_zoom": 1.1})
	var saved: Dictionary = original.call("get_state")
	var restored := _make(Vector2(720, 1280), Rect2(-100, -100, 920, 1480))
	var serialized: Variant = JSON.parse_string(JSON.stringify(saved))
	_expect(serialized is Dictionary, "Snapshots must survive JSON serialization.")
	_expect((restored.call("restore", serialized) as Array).is_empty(), "An active JSON snapshot must restore with its original geometry and independent running settings.")
	_expect(_pose_equal(original.call("sample"), restored.call("sample")), "Restoring an active shot must reproduce the saved visible frame.")
	var matches := true
	for index in 100:
		original.call("advance", 0.0625)
		restored.call("advance", 0.0625)
		matches = matches and _pose_equal(original.call("sample"), restored.call("sample"))
	_expect(matches, "A restored shot must continue identically through completion.")
	var held_snapshot: Dictionary = original.call("get_state")
	_expect((restored.call("restore", held_snapshot) as Array).is_empty() and _pose_equal(original.call("sample"), restored.call("sample")), "Held snapshots must remain held after restoration.")
	_start(restored)
	restored.call("skip")
	_expect(is_equal_approx(float((restored.call("sample") as Dictionary)["zoom"]), 1.1), "Restoration must preserve configured defaults separately from saved shot overrides.")
	var isolated: Dictionary = original.call("get_state")
	(isolated["settings"] as Dictionary)["target_zoom"] = 1.8
	(isolated["shot_settings"] as Dictionary)["target_zoom"] = 1.0
	_expect(held_snapshot == original.call("get_state"), "Snapshot dictionaries must not alias controller internals.")
	var receiver := _make()
	var copied: Dictionary = original.call("get_state")
	_expect((receiver.call("restore", copied) as Array).is_empty(), "Valid snapshot restores into another receiver.")
	var before_external_edit: Dictionary = receiver.call("get_state")
	(copied["settings"] as Dictionary)["target_zoom"] = 1.8
	(copied["shot_settings"] as Dictionary)["target_zoom"] = 1.0
	_expect(before_external_edit == receiver.call("get_state"), "Restored state must not retain aliases to the caller's snapshot.")
	_observations.append("active and held snapshot restoration, identical continuation, and snapshot ownership")


func _rejected_input_is_atomic() -> void:
	var camera := _make()
	_start(camera)
	camera.call("advance", 1.75)
	var before: Dictionary = camera.call("get_state")
	var invalid_settings: Array[Dictionary] = [
		{"duration_seconds": 0.9}, {"duration_seconds": 15.1}, {"duration_seconds": NAN},
		{"target_zoom": 0.9}, {"target_zoom": 1.9}, {"target_zoom": INF},
		{"bob_amplitude": -1.0}, {"bob_amplitude": 41.0}, {"bob_amplitude": "12"},
		{"bob_cycles_per_second": 0.4}, {"bob_cycles_per_second": 3.1}, {"bob_cycles_per_second": true},
		{"targetZoom": 1.2}, {"duration_seconds": 2.0, "target_zoom": -1.0},
	]
	for settings: Dictionary in invalid_settings:
		_expect(not (camera.call("configure", settings) as Array).is_empty(), "Invalid configuration must be rejected: " + str(settings))
		_expect(before == camera.call("get_state"), "Rejected configuration must not partially mutate the running shot or defaults.")
		_expect(not (camera.call("start", settings) as Array).is_empty(), "Invalid shot overrides must be rejected: " + str(settings))
		_expect(before == camera.call("get_state"), "A rejected start must not interrupt or restart a valid shot.")
	for delta: float in [-1.0, NAN, INF, -INF, 0.0]:
		camera.call("advance", delta)
		_expect(before == camera.call("get_state"), "Invalid or zero frame deltas must leave the camera unchanged.")
	var invalid_geometry: Array[Dictionary] = [
		{"view": Vector2.ZERO, "background": COVER},
		{"view": Vector2(NAN, 900), "background": COVER},
		{"view": VIEW, "background": Rect2(0, 0, 1200, 900)},
		{"view": VIEW, "background": Rect2(20, 0, 1600, 1000)},
		{"view": VIEW, "background": Rect2(0, 0, INF, 1000)},
	]
	for geometry: Dictionary in invalid_geometry:
		_expect(not (camera.call("initialize", geometry["view"], geometry["background"]) as Array).is_empty(), "Unusable or uncovered geometry must be rejected.")
		_expect(before == camera.call("get_state"), "Rejected initialization must preserve the running shot.")
	var invalid_states: Array[Dictionary] = []
	for mutation: Dictionary in [
		{"version": 2}, {"initialized": "yes"}, {"has_shot": "yes"},
		{"elapsed": -1.0}, {"elapsed": INF}, {"elapsed": 50.0},
		{"viewport_size": [0.0, 900.0]}, {"viewport_size": [1280.0]},
		{"background_rect": [0.0, 0.0, 100.0, 100.0]},
		{"settings": {"target_zoom": 1.2}}, {"shot_settings": {"target_zoom": 1.2}},
		{"unexpected": 1}, {"has_shot": false}, {"initialized": false},
	]:
		var malformed: Dictionary = before.duplicate(true)
		malformed.merge(mutation, true)
		invalid_states.append(malformed)
	var missing_field: Dictionary = before.duplicate(true)
	missing_field.erase("elapsed")
	invalid_states.append(missing_field)
	for state: Dictionary in invalid_states:
		_expect(not (camera.call("restore", state) as Array).is_empty(), "Malformed or inconsistent snapshots must be rejected: " + str(state))
		_expect(before == camera.call("get_state"), "A rejected snapshot must not mutate any valid running state.")
	_observations.append("atomic rejection of invalid settings, shot requests, geometry, snapshots, and frame deltas")
