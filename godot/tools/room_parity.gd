extends SceneTree

## The room's state-level parity harness.
##
##   Godot --headless --path godot --quit-after 1000 -s res://tools/room_parity.gd -- \
##       --script <abs replay json> --out <abs jsonl>
##
## A room has no clock, so there is nothing to step: it replays a list of clicks
## and prints the state and the occurrences after each one. That is the whole
## difference between this harness and the side-view genres', and it is why the
## script carries no seed and no frame count.
##
## The digest shape is the browser's: keys sorted, the bag written as its sorted
## item ids, and compact JSON written here rather than borrowed from the
## engine's formatter — Godot's puts a space after every colon, which is a
## different string and so a different hash for a reason that is not the room.


func _initialize() -> void:
	var args := _args()
	var script_path := String(args.get("script", ""))
	var out_path := String(args.get("out", ""))
	if script_path.is_empty() or out_path.is_empty():
		printerr("room parity: --script and --out are both required")
		quit(2)
		return
	var replay: Variant = _read_json(script_path)
	if not (replay is Dictionary):
		printerr("room parity: %s is not a replay script" % script_path)
		quit(2)
		return
	var manifest_path := script_path.get_base_dir().path_join("../manifest.json").simplify_path()
	var parsed: Variant = RoomContract.parse(_read_json(manifest_path))
	if KernelRefusal.is_refusal(parsed):
		printerr("room parity: %s" % (parsed as KernelRefusal).line())
		quit(2)
		return
	var manifest: Dictionary = parsed

	var state := RoomState.initial(manifest)
	var lines := PackedStringArray()
	var hashes := PackedStringArray()
	var index := 0
	for entry: Variant in ((replay as Dictionary)["script"] as Array):
		var click: Dictionary = entry
		var events: Array = []
		if String(click["kind"]) == "select":
			state = RoomState.select_item(state, click.get("item"))
		else:
			var turn := RoomState.interact_turn(
				manifest,
				state,
				String(click["verb"]),
				String(click["hotspot"]),
				click.get("item")
			)
			state = turn["state"]
			events = turn["events"]
		var record := {"state": _state(state), "events": _plain(events)}
		lines.append(
			"%s"
			% _json({"step": index, "state": record["state"], "events": record["events"]})
		)
		var context := HashingContext.new()
		context.start(HashingContext.HASH_SHA256)
		context.update(_json(record).to_utf8_buffer())
		hashes.append("%d %s" % [index, context.finish().hex_encode()])
		index += 1

	if not _write(out_path, lines):
		return
	if not _write(out_path.get_basename() + "-frames.txt", hashes):
		return
	print("room parity: %d clicks written beside %s" % [lines.size(), out_path])
	quit(0)


## The state in the browser's own digest shape: every key sorted, and the bag
## written as its sorted item ids rather than as counts, because a room's bag is
## a set and that is what both sides compare.
func _state(state: Dictionary) -> Dictionary:
	var made := _plain(state) as Dictionary
	made["inventory"] = _plain(FamilyBag.item_ids(state["inventory"]))
	var keys := made.keys()
	keys.sort()
	var sorted := {}
	for key: Variant in keys:
		sorted[key] = made[key]
	return sorted


func _plain(value: Variant) -> Variant:
	if value is Dictionary:
		var source: Dictionary = value
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
		printerr("room parity: cannot write %s" % path)
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
