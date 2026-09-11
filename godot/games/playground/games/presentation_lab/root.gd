extends RefCounted

## The laboratory binds prepared game fixtures without sharing running stories.
const COMMAND_FIXTURE = preload("res://demos/root.gd")
const AFTERLIGHT_FIXTURE = preload("res://games/bishoujo_afterlight/root.gd")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const AFTERLIGHT_ROUTES := {
	"approach_study": "res://games/presentation_lab/afterlight/study.tscn",
	"eye_study": "res://games/presentation_lab/afterlight/eye_study.tscn",
	"effects_menu": "res://games/presentation_lab/afterlight/effects_menu.tscn",
	"intertitle_study": "res://games/presentation_lab/afterlight/intertitle_study.tscn",
	"drift_study": "res://games/presentation_lab/afterlight/drift_study.tscn",
	"halo_study": "res://games/presentation_lab/afterlight/halo_study.tscn",
	"actor_motion_study": "res://games/presentation_lab/afterlight/actor_motion_study.tscn",
	"sigh_puff_study": "res://games/presentation_lab/afterlight/sigh_puff_study.tscn",
	"sprite_burst_study": "res://games/presentation_lab/afterlight/sprite_burst_study.tscn",
	"background_blackout_study": "res://games/presentation_lab/afterlight/background_blackout_study.tscn",
	"cast_pan_study": "res://games/presentation_lab/afterlight/cast_pan_study.tscn",
	"ominous_study": "res://games/presentation_lab/afterlight/ominous_study.tscn",
	"ambient_particles_study": "res://games/presentation_lab/afterlight/ambient_particles_study.tscn",
	"transmission_voice_study": "res://games/presentation_lab/afterlight/transmission_voice_study.tscn",
}
var _afterlight_fixture = AFTERLIGHT_FIXTURE.new()


func id() -> String:
	return "presentation_lab"


func title() -> String:
	return "Presentation Lab"


func entry_route() -> String:
	return "menu"


func scene_path(route_id: String) -> String:
	if route_id in ["menu", "command_link"]:
		return "res://games/presentation_lab/menu.tscn"
	return str(AFTERLIGHT_ROUTES.get(route_id, COMMAND_FIXTURE.SCENES.get(route_id, "")))


func validate_options(options: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	if options.has("language") and options["language"] not in ["en", "ko"]:
		errors.append("Presentation Lab language must be en or ko.")
	if options.has("content-root") and not options["content-root"] is String:
		errors.append("--content-root requires an absolute local directory.")
		return errors
	var content = LOCAL_CONTENT.new()
	errors.append_array(content.configure(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources"))
	return errors


func prepare_scene(scene: Control, route_id: String, options: Dictionary, _saved_state: Dictionary) -> void:
	if COMMAND_FIXTURE.SCENES.has(route_id):
		COMMAND_FIXTURE.prepare_scene(scene, options)
	elif AFTERLIGHT_ROUTES.has(route_id):
		_afterlight_fixture.prepare_scene(scene, route_id, options, {})
	else:
		scene.collection = "command_link" if route_id == "command_link" else ""
