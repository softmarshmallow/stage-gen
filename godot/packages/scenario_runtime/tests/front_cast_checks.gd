extends SceneTree

const FRONT_CAST = preload("res://addons/scenario_runtime/presentation/front_cast.gd")
const FEED = preload("res://addons/scenario_runtime/presentation/portrait_feed.gd")
const SPEC := "res://addons/game_presentation/actors/presets/cast_transition.json"
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var pixels := Image.create(16, 32, false, Image.FORMAT_RGBA8)
	pixels.fill(Color.CORAL)
	var texture := ImageTexture.create_from_image(pixels)
	var specification: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(SPEC))
	specification["slots"] = {"left": 100.0, "right": 220.0}
	var layout := {"width": 320.0, "actor_height": 120.0, "actor_top": 30.0,
		"single_center": 160.0, "spread_left": 40.0, "spread_right": 280.0,
		"max_actors": 5, "mark_height_ratio": 0.1, "mark_offset": [0.2, -0.05],
		"mark_bounds": [0.0, 0.0, 1.0], "handoff_specification": specification}
	var cast = FRONT_CAST.new()
	root.add_child(cast)
	_expect(cast.initialize([{"id": "first"}, {"id": "second"}, {"id": "third"}],
		{"first": texture, "second": texture, "third": texture}, {}, layout).is_empty(), "Procedural bindings initialize without game art.")
	_expect(cast.set_cast(["first", "second"]).is_empty(), "Caller-owned composition initializes.")
	_expect(cast.get_actor_rect("first") == Rect2(70, 30, 60, 120), "Explicit geometry determines the actor rectangle.")
	var before: Rect2 = cast.get_actor_rect("first")
	cast.present(Transform2D(Vector2(2, 0), Vector2(0, 2), Vector2(10, 20)))
	cast.present(Transform2D.IDENTITY)
	_expect(cast.get_actor_rect("first") == before, "Presentation does not advance motion or change local geometry.")
	_expect(cast.handoff("first", "second", "third").is_empty(), "Handoff accepts the independent supplied slots.")
	cast.advance(10.0)
	_expect(cast.visible_ids() == ["second", "third"], "The bounded handoff completes with the supplied actors.")
	_expect(is_equal_approx(cast.get_actor_rect("second").get_center().x, 100.0), "Handoff uses supplied coordinates.")
	var invalid := layout.duplicate(true)
	invalid["width"] = -1.0
	_expect(not cast.initialize([{"id": "first"}], {"first": texture}, {}, invalid).is_empty(), "Invalid geometry refuses.")
	_expect(cast.visible_ids() == ["second", "third"], "Invalid reinitialization preserves the prior cast.")
	var feed = FEED.new()
	root.add_child(feed)
	feed.present("remote", texture, Transform2D.IDENTITY, 2.0, {"frame_rect": Rect2(20, 20, 80, 60)})
	_expect(feed.snapshot()["visible"] and feed.snapshot()["feed_clipped"], "A supplied portrait fits a clipped feed without game skin.")
	feed.clear()
	_expect(not feed.snapshot()["visible"], "Feed cleanup drops the presentation.")
	cast.queue_free()
	feed.queue_free()
	await process_frame
	for issue: String in _errors: printerr("FAIL front presentation: " + issue)
	if _errors.is_empty(): print("PASS front presentation: supplied geometry/art, frozen rendering, independent handoff, atomic refusal and clipped feed lifecycle")
	quit(0 if _errors.is_empty() else 1)


func _expect(condition: bool, message: String) -> void:
	if not condition: _errors.append(message)
