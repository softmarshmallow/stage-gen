extends SceneTree

## A deliberately abrupt valid catalog exercises residual overshoot after a
## retarget. Run headlessly; its temporary catalog is removed after loading.
const ENGINE = preload("res://addons/game_presentation/actors/actor_focus.gd")
const TEMP_CATALOG := "res://presentation/focus/.sample-bounds-test.json"
var failures: Array[String] = []


func _initialize() -> void:
	var catalog := {"version": 1, "presets": [
		{"id": "seed", "label": "Seed", "duration_seconds": 0.2,
			"focused": {"opacity": [[0, 0], [1, 0]], "brightness": [[0, 0], [1, 0]]}, "listeners": {}},
		{"id": "fall", "label": "Fall", "duration_seconds": 1.0,
			"focused": {"opacity": [[0, 1], [0.05, 0], [1, 0]],
				"brightness": [[0, 1], [0.05, 0], [1, 0]], "scale": [[0, 10], [0.05, 1], [1, 1]]}, "listeners": {}},
		{"id": "rise", "label": "Rise", "duration_seconds": 1.0,
			"focused": {"opacity": [[0, 0], [0.05, 1], [1, 1]],
				"brightness": [[0, 0], [0.05, 1], [1, 1]]}, "listeners": {}},
	]}
	var file := FileAccess.open(TEMP_CATALOG, FileAccess.WRITE)
	if file == null:
		printerr("FAIL: cannot create the temporary bounds-test catalog")
		quit(1)
		return
	file.store_string(JSON.stringify(catalog))
	file.close()
	var engine := ENGINE.new()
	var actors: Array[String] = ["mira", "lena", "sera"]
	var errors := engine.initialize(actors, TEMP_CATALOG)
	DirAccess.remove_absolute(TEMP_CATALOG)
	_check(errors.is_empty(), "The custom catalog must be valid.")
	if errors.is_empty():
		_check(engine.set_focus("mira", false).is_empty(), "Seed focus must succeed.")
		var from := engine.sample("mira")
		_check(engine.configure("fall").is_empty(), "Falling preset must succeed.")
		_check(engine.sample("mira") == from, "Retarget must preserve the exact current sample at time 0.")
		engine.advance(0.05)
		var low := engine.sample("mira")
		_check(low["opacity"] == 0.0 and low["brightness"] == 0.0, "Negative residual alpha/brightness must clamp to zero.")
		_check(is_equal_approx(low["scale"], engine.MIN_SCALE), "Negative residual scale must clamp to 0.001.")
		engine.advance(1.0)
		_check(engine.sample("mira") == {"offset_x_ratio": 0.0, "offset_y_ratio": 0.0, "scale": 1.0, "opacity": 0.0, "brightness": 0.0}, "The authored ending must remain exact.")
		engine.clear()
		_check(engine.configure("rise").is_empty(), "Rising preset must succeed.")
		_check(engine.set_focus("mira").is_empty(), "Rising focus must succeed.")
		engine.advance(0.05)
		var high := engine.sample("mira")
		_check(high["opacity"] == 1.0 and high["brightness"] == 1.0, "Residual alpha/brightness above one must clamp to one.")
		catalog["presets"][0]["focused"]["scale"] = [[0, 0.0005], [1, 1]]
		_check(not engine._validate_catalog(catalog)["errors"].is_empty(), "Scale endpoints below 0.001 must be refused.")
		catalog["presets"][0]["focused"]["scale"] = [[0, 0.001], [1, 1]]
		_check(engine._validate_catalog(catalog)["errors"].is_empty(), "Scale endpoints at 0.001 must be accepted.")
	for failure: String in failures:
		printerr("FAIL: " + failure)
	if failures.is_empty():
		print("PASS: custom-track retarget bounds, exact starting/ending samples, and matching minimum-scale validation")
	quit(0 if failures.is_empty() else 1)


func _check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)
