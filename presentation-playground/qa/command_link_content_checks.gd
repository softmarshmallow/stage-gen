extends SceneTree

## External content integration, including historical catalog paths and WebP.
const GAME = preload("res://games/command_link/root.gd")
const OPENING = preload("res://presentation/opening.gd")
var _issues: Array[String] = []
var _fixture_root := "/private/tmp/command-link-content-" + str(Time.get_ticks_usec())


func _initialize() -> void:
	_run.call_deferred()


func _expect(condition: bool, message: String) -> void:
	if not condition: _issues.append(message)


func _write_json(relative_path: String, value: Variant) -> void:
	var path := _fixture_root.path_join(relative_path)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(value))


func _prepare() -> void:
	DirAccess.make_dir_recursive_absolute(_fixture_root.path_join("assets/manpu"))
	DirAccess.make_dir_recursive_absolute(_fixture_root.path_join("assets/locations"))
	DirAccess.make_dir_recursive_absolute(_fixture_root.path_join("assets/opening"))
	var actor := Image.create(16, 24, false, Image.FORMAT_RGBA8)
	actor.fill(Color(0.12, 0.65, 0.36, 1.0))
	for name: String in ["full_open", "full_closed", "touch", "second_standing", "third_standing"]:
		actor.save_png(_fixture_root.path_join("assets/character_" + name + ".png"))
	_write_json("assets/layout.json", {"touch_point": [0.4, 0.3], "touch_radius": 0.05})
	var marks: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/manpu/catalog.json"))
	var mark := Image.create(8, 8, false, Image.FORMAT_RGBA8)
	mark.fill(Color(0.9, 0.3, 0.1, 0.8))
	for entry: Dictionary in marks.manpu:
		var relative := "assets/manpu/" + String(entry.id) + ".webp"
		mark.save_webp(_fixture_root.path_join(relative), false)
		entry.file = "res://" + relative if entry.id == "surprise" else relative
	_write_json("assets/manpu/catalog.json", marks)
	var places: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://assets/locations/catalog.json"))
	var background := Image.create(64, 45, false, Image.FORMAT_RGB8)
	background.fill(Color(0.18, 0.28, 0.48))
	for entry: Dictionary in places.locations:
		var relative := "assets/locations/" + String(entry.id) + ".webp"
		background.save_webp(_fixture_root.path_join(relative), false)
		entry.background = relative
	_write_json("assets/locations/catalog.json", places)
	# The optional local OGV is copied across the temporary test-content boundary.
	var video := "res://assets/opening/title_placeholder.ogv"
	if FileAccess.file_exists(video):
		DirAccess.copy_absolute(video, _fixture_root.path_join("assets/opening/title.ogv"))


func _run() -> void:
	_prepare()
	var game = GAME.new()
	var options := {"content-root": _fixture_root}
	_expect(game.validate_options(options).is_empty(), "An existing absolute content root must be accepted.")
	_expect(not game.validate_options({"content-root": "../outside"}).is_empty(), "Relative external roots must be refused.")
	var stage = load(game.scene_path("game")).instantiate()
	game.prepare_scene(stage, "game", options, {"story": "preserved"})
	_expect(stage.stage_profile.validation_errors().is_empty(), "External bindings must preserve profile validation.")
	stage._load_assets()
	stage._load_manpu()
	stage._load_locations()
	_expect(stage._load_errors.is_empty(), "External content must load without a project-local PNG assumption: " + str(stage._load_errors))
	_expect(stage._textures.size() == 5 and stage._textures.open.get_size() == Vector2(16, 24), "Actor textures must come from the supplied directory, not the repository artwork.")
	_expect(stage._manpu_textures.size() == 9 and stage._manpu_textures.surprise.get_width() == 8, "Both historical res:// and new relative WebP catalog entries must use the external root.")
	_expect(stage._location_textures.size() == 3 and stage._location_textures.forward_command.get_width() == 64, "Opaque external WebP backgrounds must retain their own pixels.")
	_expect(stage._layout_loaded and stage._touch_point == Vector2(0.4, 0.3), "Contact geometry must load from the same supplied content root.")
	stage._load_errors.clear()
	_expect(stage._load_content_image("../escape.png", "Escape") == null and not stage._load_errors.is_empty(), "Catalog paths must not escape the selected content root.")
	stage.free()
	await _opening(game, options)
	_remove_tree(_fixture_root)
	for issue: String in _issues: printerr("FAIL Command Link content: " + issue)
	if _issues.is_empty():
		print("PASS Command Link content: external actor/Manpu/location/geometry bindings, WebP catalogs, traversal refusal, independent opening backend and explicit-input fallback.")
	quit(0 if _issues.is_empty() else 1)


func _opening(game: RefCounted, options: Dictionary) -> void:
	var opening = OPENING.new()
	opening.size = Vector2(1280, 900)
	game.prepare_scene(opening, "opening", options, {})
	var navigations := {"count": 0}
	opening.navigate.connect(func(_route: String): navigations.count += 1)
	root.add_child(opening)
	await process_frame
	if FileAccess.file_exists(_fixture_root.path_join("assets/opening/title.ogv")):
		_expect(opening._player != null and opening.content_errors.is_empty(), "The selected external OGV must prepare a video player.")
		if opening._player != null:
			_expect(opening._player.loop and opening._player.stream.file.begins_with(_fixture_root), "The opening must loop the external file with its original policy.")
			opening._player.finished.emit()
	var key := InputEventKey.new()
	key.pressed = true
	key.keycode = KEY_SPACE
	opening._input(key)
	await process_frame
	_expect(navigations.count == 0, "Keyboard input and stream completion must never continue automatically.")
	opening.queue_free()
	await process_frame
	var missing = OPENING.new()
	game.prepare_scene(missing, "opening", {"content-root": _fixture_root, "opening-variant": "b"}, {})
	missing.navigate.connect(func(_route: String): navigations.count += 1)
	root.add_child(missing)
	await process_frame
	_expect(missing._player == null and not missing.content_errors.is_empty() and navigations.count == 0, "Missing external media must retain the black opening until explicit input.")
	var click := InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	missing._input(click)
	await process_frame
	_expect(navigations.count == 1, "Explicit pointer input must still enter the story when media is missing.")
	missing.queue_free()
	await process_frame


func _remove_tree(path: String) -> void:
	var directory := DirAccess.open(path)
	if directory == null: return
	for name: String in directory.get_files(): DirAccess.remove_absolute(path.path_join(name))
	for name: String in directory.get_directories(): _remove_tree(path.path_join(name))
	DirAccess.remove_absolute(path)
