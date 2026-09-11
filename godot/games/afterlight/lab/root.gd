extends RefCounted

## Afterlight's laboratory: focused studies on the game's own cast and content, with the story paused.
const FIXTURE = preload("res://root.gd")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const ROUTES := {
	"approach_study": "res://lab/study.tscn",
	"eye_study": "res://lab/eye_study.tscn",
	"effects_menu": "res://lab/effects_menu.tscn",
	"intertitle_study": "res://lab/intertitle_study.tscn",
	"drift_study": "res://lab/drift_study.tscn",
	"halo_study": "res://lab/halo_study.tscn",
	"actor_motion_study": "res://lab/actor_motion_study.tscn",
	"sigh_puff_study": "res://lab/sigh_puff_study.tscn",
	"sprite_burst_study": "res://lab/sprite_burst_study.tscn",
	"background_blackout_study": "res://lab/background_blackout_study.tscn",
	"cast_pan_study": "res://lab/cast_pan_study.tscn",
	"ominous_study": "res://lab/ominous_study.tscn",
	"ambient_particles_study": "res://lab/ambient_particles_study.tscn",
	"transmission_voice_study": "res://lab/transmission_voice_study.tscn",
}
var _fixture = FIXTURE.new()


func id() -> String:
	return "lab"


func title() -> String:
	return "Afterlight Lab"


func entry_route() -> String:
	return "effects_menu"


func scene_path(route_id: String) -> String:
	if route_id == "menu":
		route_id = "effects_menu"
	return str(ROUTES.get(route_id, ""))


func validate_options(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	if options.has("language") and options["language"] not in ["en", "ko"]:
		errors.append("Afterlight Lab language must be en or ko.")
	if options.has("content-root") and not options["content-root"] is String:
		errors.append("--content-root requires an absolute local directory.")
		return errors
	var content = LOCAL_CONTENT.new()
	errors.append_array(content.configure(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources"))
	return errors


func prepare_scene(scene: Control, route_id: String, options: Dictionary, _saved_state: Dictionary) -> void:
	if route_id == "menu":
		route_id = "effects_menu"
	_fixture.prepare_scene(scene, route_id, options, {})
