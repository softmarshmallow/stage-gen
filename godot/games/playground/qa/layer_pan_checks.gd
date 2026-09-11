extends SceneTree

const PAN = preload("res://addons/game_presentation/motion/layer_pan.gd")
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_endpoints_and_hold()
	_clocks_and_retarget()
	_validation_and_reset()
	for issue: String in _errors:
		printerr("FAIL Layer Pan: " + issue)
	if _errors.is_empty():
		print("PASS Layer Pan: endpoints, held target, clock partitioning, retargeting, instance isolation, reset, and atomic validation.")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _endpoints_and_hold() -> void:
	var pan = PAN.new()
	_expect(pan.sample_transform() == Transform2D.IDENTITY and not pan.is_moving(), "New pan must be inactive identity.")
	_expect(pan.pan_to(Vector2(200, -60)).is_empty(), "Finite pan must start with defaults.")
	_expect(pan.sample_transform() == Transform2D.IDENTITY and pan.is_moving(), "The initial sample must preserve the previous offset.")
	pan.advance(0.225)
	_expect(pan.sample_transform().origin.is_equal_approx(Vector2(100, -30)), "Both axes must use the same existing ease curve.")
	pan.advance(10.0)
	_expect(pan.sample_transform() == Transform2D(0.0, Vector2(200, -60)) and not pan.is_moving(), "Completion must hold exact translation without scale or rotation.")
	var held: Dictionary = pan.get_state()
	pan.advance(10.0)
	_expect(pan.get_state() == held, "Held state must not accumulate time.")
	pan.pan_to(Vector2(-400, 1200), {"duration_seconds": 0.0})
	_expect(pan.sample_transform().origin == Vector2(-400, 1200) and not pan.is_moving(), "Zero duration must apply an unrestricted finite offset immediately.")
	pan.pan_to(Vector2(-400, 1200))
	_expect(not pan.is_moving(), "Requesting the current held offset must complete immediately.")


func _clocks_and_retarget() -> void:
	var whole = PAN.new()
	var split = PAN.new()
	for curve: String in ["linear", "ease_in_out", "spring"]:
		whole.clear()
		split.clear()
		whole.pan_to(Vector2(320, -120), {"duration_seconds": 1.0, "curve": curve})
		split.pan_to(Vector2(320, -120), {"duration_seconds": 1.0, "curve": curve})
		whole.advance(0.375)
		for index in 24:
			split.advance(0.015625)
		_expect(whole.sample_transform().is_equal_approx(split.sample_transform()), "Each motion curve must be independent of frame partitioning.")
		var frozen: Dictionary = whole.get_state()
		for index in 10:
			whole.sample_transform()
			whole.advance(0.0)
		_expect(whole.get_state() == frozen, "Sampling and a withheld clock must preserve the cue.")
		whole.pan_to(Vector2(-160, 40), {"duration_seconds": 0.4})
		_expect(whole.sample_transform().origin == frozen["offset"], "Retargeting must start continuously at the current position.")
		whole.advance(0.4)
		_expect(whole.sample_transform().origin == Vector2(-160, 40), "Retargeted motion must reach the exact new target.")
		_expect(split.get_state() == frozen, "Changing one instance must not affect another.")


func _validation_and_reset() -> void:
	var pan = PAN.new()
	pan.pan_to(Vector2(200, 100))
	pan.advance(0.1)
	var before: Dictionary = pan.get_state()
	for offset: Vector2 in [Vector2(NAN, 0), Vector2(0, INF)]:
		_expect(not pan.pan_to(offset).is_empty() and pan.get_state() == before, "Nonfinite offset must reject atomically.")
	for settings: Dictionary in [{"other": 1}, {"duration_seconds": -1}, {"duration_seconds": 5.1}, {"duration_seconds": NAN}, {"duration_seconds": "fast"}, {"curve": "other"}, {"frequency": 0.1}, {"damping_ratio": 2.0}]:
		_expect(not pan.pan_to(Vector2.ZERO, settings).is_empty() and pan.get_state() == before, "Invalid settings must leave the current cue untouched.")
	for delta: float in [-1.0, NAN, INF]:
		pan.advance(delta)
		_expect(pan.get_state() == before, "Invalid time must not mutate the cue.")
	var exposed: Dictionary = pan.get_state()
	exposed["settings"]["duration_seconds"] = 0.0
	_expect(pan.get_state() == before, "Inspection dictionaries must not expose mutable state.")
	pan.clear()
	_expect(pan.sample_transform() == Transform2D.IDENTITY and not pan.is_moving(), "Clear must restore inactive identity.")
	var empty: Dictionary = pan.get_state()
	pan.clear()
	_expect(pan.get_state() == empty, "Repeated clear must be safe.")
