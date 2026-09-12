extends SceneTree

## The dialogue scene's state-level parity harness.
##
##   Godot --headless --path godot/games/the_grain --quit-after 1000 -s res://tools/scene_parity.gd -- \
##       --script <abs replay json> --out <abs jsonl>
##
## A scenario has no clock, so this replays a list of actions rather than
## frames, the way the room's harness replays clicks.
##
## The digest hashes the **view** as well as the state, which the side-view
## genres do not: what is drawn here is a pure function of the state, and a
## change that moved one without the other would be a change in this genre's
## whole contract with its consumers rather than a drawing difference a host is
## allowed to have.


func _initialize() -> void:
	var args := _args()
	var script_path := String(args.get("script", ""))
	var out_path := String(args.get("out", ""))
	if script_path.is_empty() or out_path.is_empty():
		printerr("scene parity: --script and --out are both required")
		quit(2)
		return
	var replay: Variant = _read_json(script_path)
	if not (replay is Dictionary):
		printerr("scene parity: %s is not a replay script" % script_path)
		quit(2)
		return
	var program_path := script_path.get_base_dir().path_join("../program.json").simplify_path()
	var parsed: Variant = FamilyScenarioProgram.parse(_read_json(program_path))
	if KernelRefusal.is_refusal(parsed):
		printerr("scene parity: %s" % (parsed as KernelRefusal).line())
		quit(2)
		return
	var program: Dictionary = parsed

	var opening := FamilyScenarioRuntime.initial_turn(program)
	var state: Dictionary = opening["state"]
	var lines := PackedStringArray()
	var hashes := PackedStringArray()
	# The settle that reaches the first moment is a transition like any other and
	# is hashed like one, before any action is taken.
	hashes.append(
		"opening %s"
		% _hash(state, opening["events"], FamilyScenarioRuntime.view(program, state))
	)

	var index := 0
	for entry: Variant in ((replay as Dictionary)["script"] as Array):
		var action: Dictionary = entry
		var turn := FamilyScenarioRuntime.reduce_turn(program, state, action)
		state = turn["state"]
		var view := FamilyScenarioRuntime.view(program, state)
		hashes.append("%d %s" % [index, _hash(state, turn["events"], view)])
		lines.append(
			_json(
				{
					"step": index,
					"action": _plain(action),
					"state": _plain(state),
					"events": _plain(turn["events"]),
					"view": _plain(view),
				}
			)
		)
		index += 1

	if not _write(out_path, lines):
		return
	if not _write(out_path.get_basename() + "-frames.txt", hashes):
		return
	print("scene parity: %d actions written beside %s" % [lines.size(), out_path])
	quit(0)


func _hash(state: Dictionary, events: Array, view: Dictionary) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(
		_json({"state": _plain(state), "events": _plain(events), "view": _plain(view)})
		. to_utf8_buffer()
	)
	return context.finish().hex_encode()


## An empty Dictionary is this port's `null`: there is no nullable Dictionary in
## GDScript, so "nothing is drawn" and "no condition" are both the empty one.
func _plain(value: Variant) -> Variant:
	if value is Dictionary:
		var source: Dictionary = value
		if source.is_empty():
			return null
		var keys := source.keys()
		keys.sort()
		var made := {}
		for key: Variant in keys:
			made[String(key)] = _plain(source[key])
		return made
	if value is Array:
		var made: Array = []
		for entry: Variant in (value as Array):
			made.append(_plain(entry))
		return made
	if value is PackedStringArray:
		var made: Array = []
		for entry in (value as PackedStringArray):
			made.append(entry)
		return made
	# JSON has one number type, so a document's `0` parses as a float here and
	# would be written back as `0.0` — a different string, and so a different
	# hash, for a number that never changed.
	if value is float:
		var number: float = value
		if number == floor(number) and absf(number) < 9.0e15:
			return int(number)
	return value


## Compact JSON, byte for byte what `JSON.stringify` writes in the browser.
func _json(value: Variant) -> String:
	if value == null:
		return "null"
	if value is bool:
		return "true" if value else "false"
	if value is int:
		return str(value)
	if value is String:
		return JSON.stringify(value)
	if value is Dictionary:
		var pairs := PackedStringArray()
		for key: Variant in (value as Dictionary):
			pairs.append("%s:%s" % [JSON.stringify(String(key)), _json((value as Dictionary)[key])])
		return "{%s}" % ",".join(pairs)
	if value is Array:
		var entries := PackedStringArray()
		for entry: Variant in (value as Array):
			entries.append(_json(entry))
		return "[%s]" % ",".join(entries)
	return JSON.stringify(value)


func _write(path: String, lines: PackedStringArray) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		printerr("scene parity: cannot write %s" % path)
		quit(2)
		return false
	file.store_string("\n".join(lines) + "\n")
	file.close()
	return true


func _args() -> Dictionary:
	var made := {}
	var argv := OS.get_cmdline_user_args()
	var index := 0
	while index < argv.size():
		var key := String(argv[index])
		if key.begins_with("--") and index + 1 < argv.size():
			made[key.substr(2)] = argv[index + 1]
			index += 2
			continue
		index += 1
	return made


func _read_json(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return null
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed
