extends "res://addons/scenario_runtime/presentation/front_cast.gd"

## The game supplies its art and coordinate system to the optional front cast.
const CONTENT_ADAPTER = preload("res://content_adapter.gd")
const HEIGHT := 960.0
const TOP := 140.0
const MARK_HEIGHT_RATIO := 0.115


func initialize(profiles: Array, textures: Dictionary, manpu_textures: Dictionary = {}, layout: Dictionary = {}) -> Array[String]:
	var marks := manpu_textures
	if marks.is_empty():
		var loaded := CONTENT_ADAPTER.load_manpu()
		if not loaded.errors.is_empty(): return loaded.errors
		marks = loaded.textures
	var geometry := layout if not layout.is_empty() else default_layout()
	return super.initialize(profiles, textures, marks, geometry)


static func default_layout() -> Dictionary:
	return {
		"width": 1280.0, "actor_height": HEIGHT, "actor_top": TOP,
		"single_center": 640.0, "spread_left": 250.0, "spread_right": 1030.0,
		"max_actors": 4, "mark_height_ratio": MARK_HEIGHT_RATIO,
		"mark_offset": [0.23, -0.05], "mark_bounds": [0.1, 0.035, 0.85],
		"mark_y_offsets": {"sigh": 0.055, "sigh_puff": 0.055},
		"handoff_specification": JSON.parse_string(FileAccess.get_file_as_string(CAST_SPEC)),
	}
