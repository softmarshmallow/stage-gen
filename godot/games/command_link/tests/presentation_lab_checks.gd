extends SceneTree

## Lab ownership and paused-mission checks with prepared local media.
const GAME_ROOTS = preload("res://roots.gd")
const LAB_ROOT = preload("res://lab/root.gd")
const COMMAND_FIXTURE = preload("res://lab/fixture.gd")
var _errors: Array[String] = []
var _shell: Control
var _capture_enabled := false


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	_capture_enabled = OS.get_cmdline_user_args().has("--capture-lab")
	if _capture_enabled and DisplayServer.get_name() == "headless":
		printerr("Lab captures require a native renderer.")
		quit(2)
		return
	_shell = load("res://main.tscn").instantiate()
	root.add_child(_shell)
	await process_frame
	_expect(_open("game:lab"), "The laboratory must launch as its own root.")
	_expect(_shell.selected_game_id == "lab" and _shell.current_route == "menu", "The lab must enter its own collection menu.")
	var menu: Control = _shell.active_scene
	_expect(menu._collection_buttons.keys() == ["command_link"], "The lab must offer the Command Link study collection.")
	await _capture("collections")
	_open("command_link")
	await _capture("command-link-studies")
	_expect(GAME_ROOTS.create("command_link").scene_path("demos/manpu").is_empty(), "Command Link must not own technical study routes.")
	_expect(_open("game:command_link/game"), "The mission must be playable independently of the lab.")
	var command: Control = _shell.active_scene
	command.set("_capture_frozen", true)
	command.set_process(false)
	var command_state: Dictionary = command.save_game()
	_open("menu")
	await _capture("command-link-menu")
	_expect(_open("game:lab"), "Opening the lab must pause the mission.")
	var route_ids: Array = COMMAND_FIXTURE.SCENES.keys()
	_expect(COMMAND_FIXTURE.SCENES.size() == 11, "The laboratory must expose 11 tactical studies, excluding the collection menu.")
	for route_id: String in route_ids:
		_expect(_open(route_id), "The laboratory must resolve " + route_id)
		var study: Control = _shell.active_scene
		study.set_process(false)
		_expect(_shell.selected_game_id == "lab", "Every technical study must belong to the lab: " + route_id)
		_expect((study.get("_load_errors") as Array).is_empty(), "Prepared study must load: " + route_id)
		await process_frame
	_expect(_open("game:command_link/game"), "Returning from a study must restore the mission.")
	_shell.active_scene.set_process(false)
	_expect(_shell.active_scene.save_game() == command_state, "Visiting every study must preserve the mission's full paused state.")
	_expect(_open("demos/manpu"), "Legacy command demo links must remain usable.")
	_expect(_shell.selected_game_id == "lab", "Legacy command links must resolve in the lab.")
	root.remove_child(_shell)
	_shell.queue_free()
	await process_frame
	for error: String in _errors:
		printerr("FAIL command link lab: " + error)
	if _errors.is_empty():
		print("PASS command link lab: separate roots, all %d studies plus their collection menu, legacy redirects, and preserved mission state" % route_ids.size())
	quit(0 if _errors.is_empty() else 1)


func _open(route_id: String) -> bool:
	return bool(_shell.open_route(route_id))


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _capture(name: String) -> void:
	if not _capture_enabled:
		return
	await process_frame
	await process_frame
	RenderingServer.force_draw(false)
	var image := root.get_texture().get_image()
	var folder := "res://tests/presentation-lab/captures"
	_expect(DirAccess.make_dir_recursive_absolute(folder) == OK, "The laboratory capture directory must be writable.")
	var path := folder.path_join(name + ".png")
	_expect(image.save_png(path) == OK, "The laboratory view must be captured: " + name)
	print("Presentation Lab capture: " + ProjectSettings.globalize_path(path))
