extends SceneTree

const CONTACT = preload("res://addons/game_presentation/interaction/point_contact.gd")
var _errors: Array[String] = []
var _signals: Array[Vector2] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var contact = CONTACT.new()
	var other = CONTACT.new()
	contact.confirmed.connect(func(point: Vector2): _signals.append(point))
	var center := Vector2(400, 300)
	_expect(not contact.is_confirmed(), "A new contact must await input.")
	_expect(CONTACT.hit_test(center + Vector2(30, 40), center, 50), "The exact circle edge must be included.")
	_expect(not CONTACT.hit_test(center + Vector2(31, 40), center, 50), "An outside point must miss.")
	_expect(not contact.confirm_at(Vector2.ZERO, center, 50) and _signals.is_empty(), "Misses must not confirm or emit.")
	_expect(contact.confirm_at(center, center, 50) and contact.is_confirmed() and _signals == [center], "The first hit must latch and emit its input point.")
	_expect(contact.confirm_at(center, center, 50) and _signals.size() == 1, "Repeated hits must remain usable without duplicate confirmation.")
	_expect(not other.is_confirmed(), "Contacts must have independent state.")
	contact.reset()
	var moved := center + Vector2(120, -30)
	_expect(not contact.confirm_at(center, moved, 50), "A moved target must use new geometry without cached coordinates.")
	_expect(contact.confirm_at(moved, moved, 50) and _signals.size() == 2, "Reset permits a new confirmation at the current target.")
	contact.reset(true)
	_expect(contact.is_confirmed() and _signals.size() == 2, "Checkpoint acknowledgement must restore without a synthetic signal.")
	contact.reset()
	for radius: float in [0, -1, NAN, INF]:
		_expect(not contact.confirm_at(center, center, radius), "Invalid radius must miss.")
	_expect(not contact.confirm_at(Vector2(NAN, 0), center, 50) and not contact.confirm_at(center, Vector2(0, INF), 50), "Nonfinite input coordinates must miss.")
	_expect(not contact.is_confirmed() and _signals.size() == 2, "Invalid input must leave state unchanged.")
	var camera := Transform2D(Vector2(1.5, 0), Vector2(0, 1.5), Vector2(-70, 40))
	_expect(CONTACT.hit_test(camera * (center + Vector2(30, 0)), camera * center, 50 * 1.5), "A host may consistently transform point, target and radius into its input space.")
	for issue: String in _errors:
		printerr("FAIL Point Contact: " + issue)
	if _errors.is_empty():
		print("PASS Point Contact: circle boundaries, current coordinates, one-time confirmation, repeated hit feedback, reset/checkpoint semantics, invalid geometry and instance isolation.")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)
