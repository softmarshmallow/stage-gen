extends SceneTree

const CAST = preload("res://addons/game_presentation/actors/cast_transition.gd")
const EXIT_CATALOG := "res://addons/game_presentation/actors/presets/exit.json"
const SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
var _errors: Array[String] = []


func _initialize() -> void:
	var ids: Array[String] = ["first", "second", "third"]
	var document: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SPEC))
	var from_file = CAST.new()
	var from_data = CAST.new()
	_expect(from_file.initialize(ids, EXIT_CATALOG, SPEC).is_empty(), "File specification initializes.")
	_expect(from_data.initialize(ids, EXIT_CATALOG, document).is_empty(), "Data specification initializes.")
	from_file.start()
	from_data.start()
	for delta: float in [0.1, 0.75, 1.0, 3.0]:
		from_file.advance(delta)
		from_data.advance(delta)
		_expect(from_file.get_state() == from_data.get_state(), "File and data execute identical phases.")
	var before: Dictionary = from_data.get_state()
	document["slots"]["left"] = -20.0
	_expect(from_data.get_state() == before, "The controller owns a copy of its input.")
	_expect(not from_data.initialize(ids, EXIT_CATALOG, {"version": 999}).is_empty(), "Invalid data refuses.")
	_expect(from_data.get_state() == before, "Invalid reinitialization preserves live state.")
	document = JSON.parse_string(FileAccess.get_file_as_string(SPEC))
	document["slots"] = {"left": 150.0, "right": 450.0}
	_expect(from_data.initialize(ids, EXIT_CATALOG, document).is_empty(), "Another logical stage width is supported.")
	_expect(is_equal_approx(float(from_data.sample("first")["center_x"]), 150.0), "Supplied geometry controls placement.")
	for issue: String in _errors: printerr("FAIL Cast Transition data: " + issue)
	if _errors.is_empty(): print("PASS Cast Transition data: file/data equivalence, copied configuration, atomic refusal and independent stage geometry")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
