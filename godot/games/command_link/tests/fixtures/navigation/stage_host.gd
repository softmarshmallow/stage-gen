extends "res://presentation/stage.gd"

var actions: Array[String] = []
var render_updates := 0


func _ready() -> void:
	pass


func _update_character_layers() -> void:
	render_updates += 1


func _set_mode(mode: String) -> void:
	actions.append(mode)


func _advance_dialogue() -> void:
	actions.append("advance")


func _restart() -> void:
	actions.append("restart")
