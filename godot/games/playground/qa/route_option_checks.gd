extends SceneTree

## Run with --game command_link --route game --opening-variant b --language ko.
## Optional --content-root exercises the same round trip on an external bundle.
const AFTERLIGHT = preload("res://games/bishoujo_afterlight/root.gd")
const COMMAND_LINK = preload("res://games/command_link/root.gd")
const LAB = preload("res://games/presentation_lab/root.gd")
var _issues: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _expect(condition: bool, message: String) -> void:
	if not condition: _issues.append(message)


func _run() -> void:
	for game: RefCounted in [COMMAND_LINK.new(), AFTERLIGHT.new(), LAB.new()]:
		_expect(not game.validate_options({"content-root": true}).is_empty(), "A missing content-root argument must return diagnostics for every host.")
	var app = load("res://main.tscn").instantiate()
	root.add_child(app)
	await process_frame
	var original: Dictionary = app.options.duplicate(true)
	_expect(original.get("opening-variant") == "b" and original.get("language") == "ko", "This check requires opening variant b and Korean launch options.")
	_expect(app.selected_game_id == "command_link" and app.current_route == "game", "Command Link must remain the initial game.")
	var expected_root := String(original.get("content-root", "res://"))
	_expect(app.active_scene.stage_profile.content_loader.get_settings().root == expected_root, "Command Link must use the selected content root.")
	_expect(not AFTERLIGHT.new().validate_options(original).is_empty(), "A direct Afterlight launch must still reject an explicit opening-video option.")
	var changed: bool = app.open_route("game:bishoujo_afterlight/game")
	_expect(changed, "Command Link's opening option must not prevent navigation to Afterlight.")
	if changed:
		await process_frame
		_expect(app.active_scene._load_errors.is_empty(), "Afterlight must load successfully after the cross-game switch.")
		_expect(app.active_scene.get_language() == "ko", "Language selection must survive destination option scoping.")
		_expect(app.active_scene.content.content_loader.get_settings().root == expected_root, "Afterlight must retain the selected content root.")
		_expect(app.open_route("game:presentation_lab/demos/manpu"), "The tactical Lab fixture must accept the same global content and language options.")
		await process_frame
		_expect(app.active_scene.stage_profile.content_loader.get_settings().root == expected_root, "Lab must retain the selected external fixture root.")
		_expect(app.open_route("game:command_link/opening"), "The Command Link opening must remain accessible after the detour.")
		await process_frame
		_expect(app.active_scene.video_path.ends_with("title_b.ogv"), "Returning to Command Link must preserve opening variant b.")
		_expect(app.active_scene.content_loader.get_settings().root == expected_root, "Returning to the opening must retain the content backend.")
	_expect(app.options == original, "Destination scoping must not mutate the stored launch options.")
	app.queue_free()
	await process_frame
	for issue: String in _issues: printerr("FAIL route options: " + issue)
	if _issues.is_empty(): print("PASS route options: Command Link variant b -> Afterlight Korean -> Lab -> Command Link variant b; content root and original options preserved; direct Afterlight video option refused.")
	quit(0 if _issues.is_empty() else 1)
