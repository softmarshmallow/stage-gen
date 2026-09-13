extends SceneTree

## Independent consumer: procedural art, its own geometry and the public v3 core.
const STAGE = preload("res://addons/scenario_runtime/presentation/front_stage.gd")
const FEED = preload("res://addons/scenario_runtime/presentation/portrait_feed.gd")
const CATALOG = preload("res://addons/scenario_runtime/program/catalog.gd")
const PROGRAM = preload("res://addons/scenario_runtime/program/program.gd")
const SESSION = preload("res://addons/scenario_runtime/execution/session.gd")
var checks := 0
var failures: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var types: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://addons/scenario_runtime/presentation/front_types.json"))
	var catalog := CATALOG.parse({"kind": "scenario-catalog", "schema_version": 1, "catalog_id": "procedural_stage", "revision": "1", "definitions": {
		"near_guide": {"type": "front_camera", "parameters": {"mode": "focus", "actor": "guide", "zoom": 1.4, "duration_seconds": 0.5}, "overrides": []}}}, types)
	_check(not catalog.has("error"), "front capability catalog admits without an owning game")
	_check(CATALOG.resolve({"preset": "near_guide"}, catalog) == CATALOG.resolve({"type": "front_camera", "parameters": {"mode": "focus", "actor": "guide", "zoom": 1.4, "duration_seconds": 0.5}}, catalog), "front preset and primitive share typed defaults")
	_check(CATALOG.resolve({"type": "front_view", "parameters": {"camera_mode": "teleport"}}, catalog).has("error"), "unknown front camera vocabulary refuses before presentation")
	var first := _stage()
	var second := _stage()
	var raw := {"kind": "scenario-program-v3", "schema_version": 3, "scenario_id": "procedural_controls", "entry": "opening", "nodes": [
		{"id": "opening", "kind": "line", "text": "A different game supplies the stage.", "next": "done", "cues": [
			{"id": "view", "at": 0.0, "effect": {"type": "front_view"}, "instance_id": "view", "duration": 0.0},
			{"id": "cast", "at": 0.0, "effect": {"type": "front_cast", "parameters": {"actors": ["guide"]}}, "instance_id": "cast", "duration": 0.0},
			{"id": "camera", "at": 0.25, "effect": {"preset": "near_guide"}, "instance_id": "camera", "duration": 0.0},
			{"id": "pan", "at": 0.5, "effect": {"type": "front_pan", "parameters": {"offset": [12.0, 0.0], "settings": {"duration_seconds": 1.0, "curve": "linear"}}}, "instance_id": "pan", "duration": 0.0}]},
		{"id": "done", "kind": "end", "outcome": "complete"}]}
	var program := PROGRAM.parse(raw, catalog)
	_check(not program.has("error"), "independent timed stage program admitted")
	var grants := {}
	for id: String in types: grants[id] = types[id].version
	var policy := {"session_id": "procedural", "capabilities": grants, "channels": ["dialogue"]}
	var large := SESSION.new()
	var small := SESSION.new()
	var first_at := _apply(first, large.start(program, catalog, policy), 0.0)
	var second_at := _apply(second, small.start(program, catalog, policy), 0.0)
	first_at = _apply(first, large.tick(1.0), first_at)
	for index in 4: second_at = _apply(second, small.tick(0.25), second_at)
	var first_camera: Dictionary = first.get("_camera").sample()
	var second_camera: Dictionary = second.get("_camera").sample()
	_check(CATALOG.equivalent(first_camera, second_camera), "actual camera controllers receive equivalent exact time across frame partitions")
	_check(is_equal_approx(float(first_camera.zoom), 1.4), "camera has its authored half second after its quarter-second cue")
	var first_pan: Transform2D = first.get("_cast_pan").sample_transform()
	var second_pan: Transform2D = second.get("_cast_pan").sample_transform()
	_check(first_pan.is_equal_approx(second_pan) and is_equal_approx(first_pan.origin.x, 6.0), "later pan receives only its own half second while camera remains composed")
	var local_rect: Rect2 = first.get("_cast").get_actor_rect("guide")
	_check(local_rect == Rect2(130, 30, 60, 120), "supplied actor geometry remains local under camera and pan composition")
	var frozen_camera: Dictionary = first.get("_camera").sample()
	first.present()
	first.present()
	_check(first.get("_camera").sample() == frozen_camera and first.get("_cast_pan").sample_transform() == first_pan, "rendering is pure sampling and does not advance controls")
	var missing := CATALOG.resolve({"type": "front_view", "parameters": {"speaker": "guide", "portrait_mode": "contact"}}, catalog)
	_check(not first.validate_operation("front_view", missing.parameters).is_empty(), "contact portrait preflight refuses absent bound art")
	_check(not first.validate_operation("front_cast", {"actors": ["missing_actor"]}).is_empty(), "unknown supplied actor refuses before stage mutation")
	_check(not first.validate_operation("front_burst", {"actor": "guide", "sprites": ["missing_sprite"]}).is_empty(), "unknown sprite binding refuses before dispatch")
	_check(first.get("_cast").visible_ids() == ["guide"], "resource preflight does not change existing cast")
	for effect: Dictionary in [
		{"type": "front_cast", "parameters": {"actors": ["relay"]}},
		{"type": "front_projection", "parameters": {"actor": "relay", "enabled": true}},
		{"type": "front_view", "parameters": {"speaker": "relay"}}]:
		var admitted := CATALOG.resolve(effect, catalog)
		_check(first.execute(admitted.type, admitted.parameters).is_empty(), "supplied feed command applies through the same typed capabilities")
	first.present()
	var feed: Dictionary = first.get("_transmission_display").snapshot()
	_check(feed.visible and feed.actor_id == "relay" and feed.feed_clipped, "front stage composes an independently skinned clipped feed")
	_check(is_equal_approx(float(feed.effect_time), first_at), "feed shader time uses the same supplied presentation clock")
	first.present()
	_check(first.get("_transmission_display").snapshot() == feed, "repeated feed presentation preserves explicit time and geometry")
	_check(first.get("_load_errors").is_empty() and second.get("_load_errors").is_empty(), "all independent front controllers remain free of runtime refusals")
	first.free()
	second.free()
	await process_frame
	for message: String in failures: printerr("FAIL front_stage: " + message)
	if failures.is_empty(): print("scenario_front_stage: %d checks passed" % checks)
	quit(0 if failures.is_empty() else 1)


func _stage() -> Control:
	var pixels := Image.create(16, 32, false, Image.FORMAT_RGBA8)
	pixels.fill(Color.CORAL)
	var texture := ImageTexture.create_from_image(pixels)
	var backdrop := Image.create(320, 240, false, Image.FORMAT_RGBA8)
	backdrop.fill(Color.DARK_SLATE_BLUE)
	var specification: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://addons/game_presentation/actors/presets/cast_transition.json"))
	specification.slots = {"left": 100.0, "right": 220.0}
	var geometry := {"width": 320.0, "actor_height": 120.0, "actor_top": 30.0, "single_center": 160.0, "spread_left": 40.0, "spread_right": 280.0, "max_actors": 5,
		"mark_height_ratio": 0.1, "mark_offset": [0.2, -0.05], "mark_bounds": [0.0, 0.0, 1.0], "handoff_specification": specification}
	var stage := STAGE.new()
	var configured := stage.configure({"design_size": [320.0, 240.0], "actors": [
		{"id": "guide", "eye_uv": [0.5, 0.25]},
		{"id": "relay", "eye_uv": [0.5, 0.25], "transmission_display": {"frame_rect": Rect2(32, 24, 96, 72), "camera_zoom": 1.2, "feed_inset": Vector2(4, 4)}}],
		"cast_geometry": geometry, "backgrounds": [{"id": "violet_room"}],
		"geometry": {"eye_anchor_y": 80.0, "detail_zoom": 1.1, "heat_rect": Rect2(0, 0, 320, 240), "barrier_rect": Rect2(0, 140, 320, 80)}},
		{"backgrounds": [ImageTexture.create_from_image(backdrop)], "actors": {"guide": texture, "relay": texture}, "portraits": {}, "details": {}, "contacts": {}, "burst": {"spark": texture}, "manpu": {"spark": texture}}, FEED.new())
	_check(configured.is_empty(), "stage accepts procedural bindings at independent geometry")
	root.add_child(stage)
	stage.reset()
	return stage


## Commands come from Session; this bridge only samples the installed controller
## at each reported boundary, then advances the remaining presentation delta.
func _apply(stage: Control, report: Dictionary, at: float) -> float:
	for event: Dictionary in report.get("events", []):
		var boundary := float(event.clocks.presentation)
		stage.advance(maxf(0.0, boundary - at))
		at = maxf(at, boundary)
		if event.type == "scenario/effect_started":
			_check(stage.execute(event.effect.type, event.effect.parameters).is_empty(), "normalized session command applies to independent front stage")
	var final_at := float(report.state.clocks.presentation)
	stage.advance(maxf(0.0, final_at - at))
	stage.present()
	return maxf(at, final_at)


func _check(condition: bool, message: String) -> void:
	checks += 1
	if not condition: failures.append(message)
