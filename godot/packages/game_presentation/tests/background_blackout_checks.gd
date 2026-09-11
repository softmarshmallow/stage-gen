extends SceneTree

## Focused public-contract checks for background-only coverage.
const Blackout := preload("res://addons/game_presentation/transitions/background_blackout.gd")
const EPSILON := 0.000001
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var component_script: Script = Blackout
	if not component_script.can_instantiate():
		printerr("FAIL Background Blackout: component must compile and instantiate.")
		quit(1)
		return
	_endpoints_and_hold()
	_interruption_and_clock()
	_reset_and_validation()
	if _errors.is_empty():
		print("PASS Background Blackout: endpoints, hold, layer defaults, interruption, explicit clock, reset, and atomic validation.")
	else:
		for issue: String in _errors:
			printerr("FAIL Background Blackout: " + issue)
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _endpoints_and_hold() -> void:
	var layer := Blackout.new()
	_expect(not layer.visible and layer.color == Color(0, 0, 0, 0) and not layer.is_active(), "New coverage must be hidden and transparent.")
	_expect(layer.mouse_filter == Control.MOUSE_FILTER_IGNORE and layer.modulate == Color.WHITE, "The layer must ignore pointer input and preserve neutral inherited modulation.")
	_expect(layer.anchor_left == 0.0 and layer.anchor_top == 0.0 and layer.anchor_right == 1.0 and layer.anchor_bottom == 1.0, "The layer must fill its parent stage.")
	_expect(layer.fade_to(1.0).is_empty(), "The default fade must be accepted.")
	_expect(layer.is_active() and not layer.visible, "A newly started fade must preserve its transparent initial sample.")
	layer.advance(0.2)
	_expect(absf(layer.color.a - 0.5) < EPSILON and layer.visible, "The midpoint must smoothly cover half the background.")
	layer.advance(1.0)
	_expect(layer.color == Color.BLACK and not layer.is_active(), "The fade must reach and hold exact black.")
	var held := layer.get_state()
	layer.advance(1000.0)
	_expect(layer.get_state() == held, "Completed coverage must hold without elapsed-time drift.")
	layer.fade_to(0.0, 0.5)
	layer.advance(0.5)
	_expect(layer.color == Color(0, 0, 0, 0) and not layer.visible and not layer.is_active(), "Restoration must remove every trace of coverage.")
	layer.fade_to(1.0, 0.0)
	_expect(layer.color == Color.BLACK and not layer.is_active(), "Zero duration must apply coverage immediately.")
	layer.fade_to(1.0, 30.0)
	_expect(not layer.is_active(), "Requesting an already held target must not create an empty animation.")
	layer.free()


func _interruption_and_clock() -> void:
	var whole := Blackout.new()
	var split := Blackout.new()
	whole.fade_to(1.0, 1.0)
	split.fade_to(1.0, 1.0)
	whole.advance(0.375)
	for index in 24:
		split.advance(0.015625)
	_expect(absf(whole.color.a - split.color.a) < EPSILON, "Frame partitioning must not change presented opacity.")
	var before := whole.get_state()
	for index in 20:
		whole.get_state()
		whole.advance(0.0)
	_expect(whole.get_state() == before, "Inspection and a withheld clock must not advance the transition.")
	whole.fade_to(0.0, 0.5)
	_expect(whole.color.a == float(before["strength"]), "Reversal must start continuously from the visible opacity.")
	whole.advance(0.25)
	_expect(absf(whole.color.a - float(before["strength"]) * 0.5) < EPSILON, "Reversal must interpolate from the interrupted sample.")
	whole.advance(0.25)
	_expect(not whole.visible and not whole.is_active(), "An interrupted fade must reach its new exact endpoint.")
	_expect(split.get_state() == before, "Changing one instance must not change another.")
	whole.free()
	split.free()


func _reset_and_validation() -> void:
	var layer := Blackout.new()
	var empty := layer.get_state()
	layer.fade_to(0.9, 2.0)
	layer.advance(0.7)
	var before := layer.get_state()
	for strength: float in [-0.1, 1.1, NAN, INF, -INF]:
		_expect(not layer.fade_to(strength).is_empty() and layer.get_state() == before, "Invalid opacity must be rejected atomically.")
	for duration: float in [-0.1, 30.1, NAN, INF]:
		_expect(not layer.fade_to(0.2, duration).is_empty() and layer.get_state() == before, "Invalid duration must be rejected atomically.")
	for delta: float in [-0.1, NAN, INF, -INF]:
		_expect(not layer.advance(delta).is_empty() and layer.get_state() == before, "Invalid time must be rejected atomically.")
	var exposed := layer.get_state()
	exposed["strength"] = 0.0
	_expect(layer.get_state() == before, "Returned state must not alias mutable controller state.")
	layer.clear()
	_expect(layer.get_state() == empty and not layer.visible and layer.color.a == 0.0, "Clear must reset every field and remove coverage.")
	layer.clear()
	_expect(layer.get_state() == empty, "Repeated clear must be safe.")
	layer.free()
