extends RefCounted

## Command Link's composition: authored game, presentation bindings, and shell.
const PROFILE = preload("res://stage_profile.gd")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const SCENES := {
	"game": "res://game.tscn",
	"menu": "res://menu.tscn",
	"opening": "res://presentation/opening.tscn",
}
const OPENING_VIDEOS := {"a": "res://assets/opening/title.ogv", "b": "res://assets/opening/title_b.ogv"}


func id() -> String:
	return "command_link"


func title() -> String:
	return "Command Link"


func entry_route() -> String:
	return "opening"


func scene_path(route_id: String) -> String:
	return String(SCENES.get(route_id, ""))


func validate_options(options: Dictionary) -> Array[String]:
	if not OPENING_VIDEOS.has(str(options.get("opening-variant", "a"))):
		return ["Unknown opening variant. Use --opening-variant a or --opening-variant b."]
	if options.has("content-root") and not options["content-root"] is String:
		return ["--content-root requires an absolute local directory."]
	var content = LOCAL_CONTENT.new()
	return content.configure(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources")


func prepare_scene(scene: Control, route_id: String, options: Dictionary, saved_state: Dictionary) -> void:
	match route_id:
		"game":
			scene.stage_profile = PROFILE.new(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources")
			scene.saved_state = saved_state.duplicate(true)
		"menu":
			scene.has_saved_game = not saved_state.is_empty()
		"opening":
			scene.video_path = OPENING_VIDEOS[str(options.get("opening-variant", "a"))]
			var content = LOCAL_CONTENT.new()
			scene.content_loader = content
			scene.content_errors.assign(content.configure(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources"))
			scene.continue_label = "BEGIN BRIEFING  →"
