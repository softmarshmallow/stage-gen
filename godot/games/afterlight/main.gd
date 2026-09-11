extends Control

## Bishōjo: Afterlight's application shell: the story root and the game's own Lab root.
const ROOTS = preload("res://roots.gd")
const LAB_STUDIES := ["approach_study", "eye_study", "effects_menu", "intertitle_study", "drift_study", "halo_study"]
var selected_game_id := "afterlight"
var game_root
var current_route := ""
var active_scene: Control
var game_state: Dictionary = {}
var options: Dictionary = {}
var _game_roots: Dictionary = {}
var _game_states: Dictionary = {}


func _ready() -> void:
	get_window().min_size = Vector2i(320, 225)
	options = _arguments()
	selected_game_id = str(options.get("game", "afterlight"))
	game_root = ROOTS.create(selected_game_id)
	if game_root == null:
		printerr("Unknown game. Use --game afterlight or --game lab.")
		get_tree().quit(2)
		return
	selected_game_id = game_root.id()
	_game_roots[selected_game_id] = game_root
	get_window().title = game_root.title()
	var option_errors: Array[String] = game_root.validate_options(options)
	if not option_errors.is_empty():
		for issue in option_errors:
			printerr(issue)
		get_tree().quit(2)
		return
	var requested := String(options.get("route", game_root.entry_route()))
	if not open_route(requested):
		get_tree().quit(2)
		return


func open_route(route_id: String) -> bool:
	var target_id := selected_game_id
	var destination := route_id
	if destination.begins_with("game:"):
		var target := destination.substr(5).split("/", true, 1)
		target_id = str(target[0])
		destination = str(target[1]) if target.size() > 1 else ""
	elif destination in LAB_STUDIES:
		# Preserve old launch links, but make the laboratory the actual owner.
		target_id = "lab"
	if target_id == "afterlight" and destination == "menu":
		# Afterlight's former menu alias was the walking study, not a pause menu.
		target_id = "lab"
		destination = "approach_study"
	var target_root = _game_roots.get(target_id)
	if target_root == null:
		target_root = ROOTS.create(target_id)
	if target_root == null:
		printerr("Unknown game: " + target_id)
		return false
	var destination_options := options.duplicate()
	var option_errors: Array[String] = target_root.validate_options(destination_options)
	if not option_errors.is_empty():
		for issue in option_errors: printerr(issue)
		return false
	target_id = target_root.id()
	if destination.is_empty():
		destination = target_root.entry_route()
	var new_game := destination == "new_game"
	if new_game:
		destination = "game"
	var path: String = target_root.scene_path(destination)
	if path.is_empty():
		printerr("Unknown route for %s: %s" % [target_id, destination])
		return false
	var scene: PackedScene = load(path)
	if scene == null:
		printerr("Cannot load route: " + path)
		return false
	if current_route == "game" and active_scene != null and active_scene.has_method("save_game"):
		_game_states[selected_game_id] = active_scene.save_game().duplicate(true)
	if new_game:
		_game_states.erase(target_id)
	get_viewport().gui_release_focus()
	if active_scene != null:
		# Stop old input listeners immediately, before deferred freeing.
		remove_child(active_scene)
		active_scene.queue_free()
	selected_game_id = target_id
	game_root = target_root
	_game_roots[target_id] = target_root
	game_state = _game_states.get(target_id, {}).duplicate(true)
	get_window().title = game_root.title()
	current_route = destination
	active_scene = scene.instantiate()
	game_root.prepare_scene(active_scene, destination, destination_options, game_state)
	active_scene.navigate.connect(_request_route)
	add_child(active_scene)
	active_scene.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return true


func _request_route(route_id: String) -> void:
	open_route.call_deferred(route_id)


func _arguments() -> Dictionary:
	var result := {}
	var args := OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		var argument := String(args[index])
		if argument.begins_with("--"):
			var key := argument.substr(2)
			if index + 1 < args.size() and not String(args[index + 1]).begins_with("--"):
				result[key] = String(args[index + 1])
				index += 1
			else:
				result[key] = true
		index += 1
	return result
