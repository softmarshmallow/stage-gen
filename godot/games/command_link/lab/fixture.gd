extends RefCounted

## The Lab's prepared Command Link fixture, independent of game state.
const PROFILE = preload("res://stage_profile.gd")
const SCENES := {
	"demos/characters": "res://lab/scenes/characters.tscn",
	"demos/contact": "res://lab/scenes/contact.tscn",
	"demos/dialogue": "res://lab/scenes/dialogue.tscn",
	"demos/actor_focus": "res://lab/scenes/actor_focus.tscn",
	"demos/character_exit": "res://lab/scenes/character_exit.tscn",
	"demos/cast_transition": "res://lab/scenes/cast_transition.tscn",
	"demos/establishing_shot": "res://lab/scenes/establishing_shot.tscn",
	"demos/dialogue_camera": "res://lab/scenes/dialogue_camera.tscn",
	"demos/manpu": "res://lab/scenes/manpu.tscn",
	"demos/locations": "res://lab/scenes/locations.tscn",
	"demos/hologram": "res://lab/scenes/hologram.tscn",
}


static func prepare_scene(scene: Control, options: Dictionary = {}) -> void:
	scene.stage_profile = PROFILE.new(String(options.get("content-root", "res://")), "files" if options.has("content-root") else "resources")
