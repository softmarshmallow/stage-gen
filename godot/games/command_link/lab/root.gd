extends RefCounted

## Command Link's laboratory: the tactical fixture studies, with the mission paused.
const FIXTURE = preload("res://lab/fixture.gd")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")


func id() -> String:
	return "lab"


func title() -> String:
	return "Command Link Lab"


func entry_route() -> String:
	return "menu"


func scene_path(route_id: String) -> String:
	if route_id in ["menu", "command_link"]:
		return "res://lab/menu.tscn"
	return str(FIXTURE.SCENES.get(route_id, ""))


func validate_options(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	if options.has("content-root") and not options["content-root"] is String:
		errors.append("--content-root requires an absolute local directory.")
		return errors
	var content = LOCAL_CONTENT.new()
	errors.append_array(content.configure(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources"))
	return errors


func prepare_scene(scene: Control, route_id: String, options: Dictionary, _saved_state: Dictionary) -> void:
	if FIXTURE.SCENES.has(route_id):
		FIXTURE.prepare_scene(scene, options)
	else:
		scene.collection = "command_link" if route_id == "command_link" else ""
