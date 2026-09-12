extends SceneTree

## Run with --game command_link --route game --language ko.
## Optional --content-root exercises the same round trip on an external bundle.
const COMMAND_LINK = preload("res://root.gd")
const LAB = preload("res://lab/root.gd")
var _issues: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _expect(condition: bool, message: String) -> void:
	if not condition: _issues.append(message)


func _run() -> void:
	for game: RefCounted in [COMMAND_LINK.new(), LAB.new()]:
		_expect(not game.validate_options({"content-root": true}).is_empty(), "A missing content-root argument must return diagnostics for every host.")
	var app = load("res://main.tscn").instantiate()
	root.add_child(app)
	await process_frame
	var original: Dictionary = app.options.duplicate(true)
	_expect(original.get("language") == "ko", "This check requires the Korean launch option.")
	_expect(app.selected_game_id == "command_link" and app.current_route == "game", "Command Link must remain the initial game.")
	var expected_root := String(original.get("content-root", "res://"))
	_expect(app.active_scene.stage_profile.content_loader.get_settings().root == expected_root, "Command Link must use the selected content root.")
	var changed: bool = app.open_route("game:lab/demos/manpu")
	_expect(changed, "The mission's launch options must not prevent a Lab detour.")
	if changed:
		await process_frame
		_expect(app.active_scene.stage_profile.content_loader.get_settings().root == expected_root, "Lab must retain the selected external fixture root.")
		_expect(app.open_route("game:command_link/opening"), "The Command Link opening must remain accessible after the detour.")
		await process_frame
		_expect(app.active_scene.video_path.ends_with("title.ogv"), "Returning to Command Link must play its opening.")
		_expect(app.active_scene.content_loader.get_settings().root == expected_root, "Returning to the opening must retain the content backend.")
	_expect(app.options == original, "Destination scoping must not mutate the stored launch options.")
	app.queue_free()
	await process_frame
	for issue: String in _issues: printerr("FAIL route options: " + issue)
	if _issues.is_empty(): print("PASS route options: Command Link -> Lab -> Command Link; content root and original options preserved.")
	quit(0 if _issues.is_empty() else 1)
