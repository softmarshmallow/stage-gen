extends Control

## Command Link's application shell: the mission root and the game's own Lab root.
const NAVIGATION = preload("res://addons/scene_navigation/scene_navigation.gd")
const ROOTS = preload("res://roots.gd")
const DEMOS = preload("res://lab/fixture.gd")
const LEGACY_MODES := {"full_body": "demos/characters", "reach_out": "demos/contact", "dialogue": "demos/dialogue", "manpu_gallery": "demos/manpu"}
var selected_game_id := "command_link"
var game_root
var current_route := ""
var _navigation = NAVIGATION.new()
var active_scene: Control:
	get:
		return _navigation.active_scene
var game_state: Dictionary = {}
var options: Dictionary = {}
var _game_roots: Dictionary = {}
var _game_states: Dictionary:
	get:
		return _navigation.checkpoints


func _ready() -> void:
	get_window().min_size = Vector2i(320, 225)
	options = _arguments()
	selected_game_id = str(options.get("game", "command_link"))
	game_root = ROOTS.create(selected_game_id)
	if game_root == null:
		printerr("Unknown game. Use --game command_link or --game lab.")
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
	# Keep historical asset/render regression checks outside ordinary play.
	if options.has("validate") or options.has("capture-state") or options.has("capture-all"):
		var stage: Control = load("res://tests/legacy_presentation.gd").new()
		DEMOS.prepare_scene(stage, options)
		stage.standalone_checks = true
		add_child(stage)
		stage.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		return
	var requested := String(options.get("route", game_root.entry_route()))
	if options.has("mode"):
		var mode := String(options["mode"])
		if not LEGACY_MODES.has(mode):
			printerr("Unknown legacy mode: " + mode)
			get_tree().quit(2)
			return
		requested = LEGACY_MODES[mode]
		print("Legacy --mode maps to --route " + requested)
	if not open_route(requested):
		get_tree().quit(2)
		return
	if options.has("validate-routes") or options.has("capture-routes"):
		call_deferred("_run_route_checks")
	elif options.has("validate-focus") or options.has("capture-focus"):
		call_deferred("_run_actor_focus_checks")
	elif options.has("validate-manpu-animation") or options.has("capture-manpu-animation"):
		call_deferred("_run_manpu_animation_checks")
	elif options.has("validate-character-exit") or options.has("capture-character-exit"):
		call_deferred("_run_character_exit_checks")
	elif options.has("validate-cast-transition") or options.has("capture-cast-transition"):
		call_deferred("_run_cast_transition_checks")
	elif options.has("validate-establishing-shot") or options.has("capture-establishing-shot"):
		call_deferred("_run_establishing_shot_checks")
	elif options.has("validate-dialogue-camera") or options.has("capture-dialogue-camera"):
		call_deferred("_run_dialogue_camera_checks")


func open_route(route_id: String) -> bool:
	var target_id := selected_game_id
	var destination := route_id
	if destination.begins_with("game:"):
		var target := destination.substr(5).split("/", true, 1)
		target_id = str(target[0])
		destination = str(target[1]) if target.size() > 1 else ""
	elif destination == "demos":
		target_id = "lab"
		destination = "command_link"
	elif destination.begins_with("demos/"):
		# Preserve old launch links, but make the laboratory the actual owner.
		target_id = "lab"
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
		if target_id == "command_link" and not _game_states.get(target_id, {}).is_empty():
			destination = "game"
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
	return _navigation.replace_scene(
		self, scene, selected_game_id if current_route == "game" else "", target_id, new_game,
		func(saved: Dictionary) -> void:
			selected_game_id = target_id
			game_root = target_root
			_game_roots[target_id] = target_root
			game_state = saved
			get_window().title = game_root.title()
			current_route = destination,
		func(next_scene: Control, saved: Dictionary) -> void:
			target_root.prepare_scene(next_scene, destination, destination_options, saved),
		_request_route
	)


func _request_route(route_id: String) -> void:
	open_route.call_deferred(route_id)


func _run_route_checks() -> void:
	var checks = load("res://tests/route_checks.gd").new()
	await checks.run(self, options)


func _run_actor_focus_checks() -> void:
	var checks = load("res://tests/actor_focus_checks.gd").new()
	await checks.run(self, options)


func _run_manpu_animation_checks() -> void:
	var checks = load("res://tests/manpu_animation_checks.gd").new()
	await checks.run(self, options)


func _run_character_exit_checks() -> void:
	var checks = load("res://tests/character_exit_checks.gd").new()
	await checks.run(self, options)


func _run_cast_transition_checks() -> void:
	var checks = load("res://tests/cast_transition_checks.gd").new()
	await checks.run(self, options)


func _run_establishing_shot_checks() -> void:
	var checks = load("res://tests/establishing_shot_checks.gd").new()
	await checks.run(self, options)


func _run_dialogue_camera_checks() -> void:
	var checks = load("res://tests/dialogue_camera_checks.gd").new()
	await checks.run(self, options)


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
