extends RefCounted

## Presentation Lab's prepared Command Link fixture, independent of game state.
const PROFILE = preload("res://games/command_link/stage_profile.gd")
const SCENES := {
	"demos/characters": "res://demos/scenes/characters.tscn",
	"demos/contact": "res://demos/scenes/contact.tscn",
	"demos/dialogue": "res://demos/scenes/dialogue.tscn",
	"demos/actor_focus": "res://demos/scenes/actor_focus.tscn",
	"demos/character_exit": "res://demos/scenes/character_exit.tscn",
	"demos/cast_transition": "res://demos/scenes/cast_transition.tscn",
	"demos/establishing_shot": "res://demos/scenes/establishing_shot.tscn",
	"demos/dialogue_camera": "res://demos/scenes/dialogue_camera.tscn",
	"demos/manpu": "res://demos/scenes/manpu.tscn",
	"demos/locations": "res://demos/scenes/locations.tscn",
	"demos/hologram": "res://demos/scenes/hologram.tscn",
}


static func prepare_scene(scene: Control, options: Dictionary = {}) -> void:
	scene.stage_profile = PROFILE.new(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources")
