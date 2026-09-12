extends Control

signal navigate(route_id: String)
var snapshot := {"line": "opening", "nested": {"choice": "none"}}
var saved_calls := 0
var key_count := 0
var prepared := false
var ready_saw_preparation := false
var ready_saw_selection := false


func _ready() -> void:
	ready_saw_preparation = prepared
	ready_saw_selection = get_parent().has_meta("selected")


func save_game() -> Dictionary:
	saved_calls += 1
	return snapshot


func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed:
		key_count += 1
