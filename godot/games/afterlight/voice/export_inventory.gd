extends SceneTree

## Offline authored inventory for a separately authorized preparation command.
const POLICY = preload("res://voice/voice_policy.gd")
const EPISODE = preload("res://story_beats.gd")


func _initialize() -> void:
	var output := ""
	var arguments := OS.get_cmdline_user_args()
	var status_only := arguments.has("--status")
	for index in arguments.size():
		if arguments[index] == "--output" and index + 1 < arguments.size(): output = arguments[index + 1]
	if output.is_empty() and not status_only:
		printerr("Usage: Godot --headless --path godot/games/afterlight --script res://voice/export_inventory.gd -- --output /absolute/path/inventory.json [--status]")
		quit(2)
		return
	var text_sets := {}
	var errors: Array[String] = []
	for language: String in POLICY.LANGUAGES:
		text_sets[language] = POLICY._read_json("res://text/" + language + ".json", errors)
	var policy := POLICY.new()
	if errors.is_empty(): errors.append_array(policy.load_project(EPISODE.BEATS, text_sets))
	if not errors.is_empty():
		for issue: String in errors: printerr(issue)
		quit(1)
		return
	var inventory := policy.get_status_report() if status_only else policy.get_inventory()
	if output.is_empty():
		print(JSON.stringify(inventory, "  ", true))
		quit(0)
		return
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		printerr("Cannot write Afterlight voice inventory: " + output)
		quit(1)
		return
	file.store_string(JSON.stringify(inventory, "  ", true) + "\n")
	file.close()
	print("Exported " + str(inventory["lines"].size()) + " localized authored voice-policy records to " + output)
	quit(0)
