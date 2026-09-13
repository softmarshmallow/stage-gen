extends SceneTree

## Source preview for the supplied procedural host. Custom capabilities require
## their consuming game's bindings; this preview installs only particle v1.
const GAME = preload("res://examples/_shared/host.gd")
var game: Control


func _initialize() -> void:
	_run.call_deferred()


func _run() -> void:
	var options := OS.get_cmdline_user_args()
	var content := "res://examples/combat_dialogue"
	var checkpoint := ""
	var finite := false
	var index := 0
	while index < options.size():
		var flag := options[index]
		if flag == "--check":
			finite = true
			index += 1
			continue
		if flag not in ["--content", "--checkpoint"] or index + 1 >= options.size():
			_fail("Usage: --content <directory with program.json/catalog.json> [--checkpoint <snapshot.json>] [--check]")
			return
		if flag == "--content": content = options[index + 1]
		else: checkpoint = options[index + 1]
		index += 2
	root.size = Vector2i(960, 640)
	game = GAME.new()
	game.content_directory = content
	root.add_child(game)
	game.invoke()
	if not game.errors.is_empty():
		_fail("; ".join(game.errors))
		return
	if not checkpoint.is_empty():
		var parsed := preload("res://addons/scenario_runtime/content/json_data.gd").parse(FileAccess.get_file_as_bytes(checkpoint), checkpoint)
		if parsed.has("error"):
			_fail(str(parsed.error))
			return
		# Snapshot identity belongs to the invocation. Restore may retain its ID;
		# checkpoint admission still binds exact program and catalog fingerprints.
		game.host.cancel(game.session_id, "preview_checkpoint")
		game.session_id = str(parsed.value.get("state", {}).get("session_id", ""))
		var result: Dictionary = game.restore_checkpoint(parsed.value)
		if result.has("error"):
			_fail(str(result.error))
			return
	if finite:
		game.set_process(false)
		game.step_narrative()
		if game.errors.is_empty():
			print("scenario_preview: content admitted and stepped by the installed player")
			quit(0)
		else: _fail("; ".join(game.errors))


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
