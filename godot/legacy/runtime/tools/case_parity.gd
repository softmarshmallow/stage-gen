extends SceneTree

## The case runtime's state-level parity harness.
##
##   Godot --headless --path godot/legacy/runtime --quit-after 1000 -s res://tools/case_parity.gd -- \
##       --script <abs replay json> --out <abs jsonl>
##
## It plays the episode the browser's own golden plays: opened cold, each
## scenario leaf played for real through the scenario runtime, and the room beat
## finished by the flags the case declares it writes.
##
## The leaves are **played** rather than their actions replayed out of the dump,
## which would be reading the answer's inputs from the answer. The room is
## finished by its writes because the room's own reducer already has its own
## golden, and what the case does with the flags it is handed is the layer this
## harness measures.


func _initialize() -> void:
	var args := _args()
	var script_path := String(args.get("script", ""))
	var out_path := String(args.get("out", ""))
	if script_path.is_empty() or out_path.is_empty():
		printerr("case parity: --script and --out are both required")
		quit(2)
		return
	var replay: Variant = _read_json(script_path)
	if not (replay is Dictionary):
		printerr("case parity: %s is not a replay script" % script_path)
		quit(2)
		return
	var replay_doc: Dictionary = replay
	var root := script_path.get_base_dir().path_join("..").simplify_path()
	var parsed: Variant = CaseDocument.parse(_read_json(root.path_join("document.json")))
	if KernelRefusal.is_refusal(parsed):
		printerr("case parity: %s" % (parsed as KernelRefusal).line())
		quit(2)
		return
	var document: Dictionary = parsed

	var leaves := {}
	for key: Variant in (replay_doc["leaves"] as Dictionary):
		var program: Variant = FamilyScenarioProgram.parse(
			_read_json(root.path_join(String((replay_doc["leaves"] as Dictionary)[key])))
		)
		if KernelRefusal.is_refusal(program):
			printerr("case parity: %s" % (program as KernelRefusal).line())
			quit(2)
			return
		leaves[String(key)] = program

	var tag := String(replay_doc.get("tag", "demo"))
	var at := String(replay_doc.get("at", ""))
	var state := CaseRuntime.initial(document)
	var lines := PackedStringArray()
	var hashes := PackedStringArray()
	hashes.append("opening %s" % _hash(state, []))
	# The leaf state each `play-leaf` finished on, so the `finish-leaf` after it
	# reports the outcome and the flags that leaf actually reached.
	var finished := {}
	var index := 0

	for entry: Variant in (replay_doc["script"] as Array):
		var step: Dictionary = entry
		match String(step["kind"]):
			"play-leaf":
				var beat_id := String(step["beatId"])
				var program: Dictionary = leaves[beat_id]
				var scenario := FamilyScenarioRuntime.initial_state(
					program, (state["progress"] as Dictionary)["facts"]
				)
				for _guard in 200:
					var view := FamilyScenarioRuntime.view(program, scenario)
					var line: Variant = null
					if String(view.get("kind", "")) == "line":
						line = {"speaker": view["speakerLabel"], "text": view["text"]}
					var action := {
						"kind": "presented",
						"statementId": (
							null
							if scenario["outcome"] != null
							else FamilyScenarioRuntime.statement_id(
								String(scenario["label"]), int(scenario["index"])
							)
						),
						"line": line,
						"scenario": scenario,
						"outcome": scenario["outcome"],
					}
					var turn := CaseRuntime.reduce(document, tag, state, action, at)
					state = turn["state"]
					hashes.append("%d %s" % [index, _hash(state, turn["events"])])
					lines.append(_record(index, action, state, turn["events"]))
					index += 1
					if scenario["outcome"] != null:
						break
					# A choice is answered with its first option: this golden is
					# about the layer above the leaf, so the route only has to be
					# one a player could take and the same one every run.
					scenario = FamilyScenarioRuntime.reduce(
						program,
						scenario,
						(
							{"kind": "choose", "option": 0}
							if String(view.get("kind", "")) == "choice"
							else {"kind": "advance"}
						)
					)
				finished[beat_id] = scenario
			"finish-leaf":
				var beat_id := String(step["beatId"])
				var scenario: Dictionary = finished[beat_id]
				var action := {
					"kind": "finish",
					"beatId": beat_id,
					"outcome": scenario["outcome"],
					"flags": scenario["flags"],
				}
				var turn := CaseRuntime.reduce(document, tag, state, action, at)
				state = turn["state"]
				hashes.append("%d %s" % [index, _hash(state, turn["events"])])
				lines.append(_record(index, action, state, turn["events"]))
				index += 1
			_:
				var turn := CaseRuntime.reduce(document, tag, state, step, at)
				state = turn["state"]
				hashes.append("%d %s" % [index, _hash(state, turn["events"])])
				lines.append(_record(index, step, state, turn["events"]))
				index += 1

	if not _write(out_path, lines):
		return
	if not _write(out_path.get_basename() + "-frames.txt", hashes):
		return
	print("case parity: %d actions written beside %s" % [lines.size(), out_path])
	quit(0)


func _record(index: int, action: Dictionary, state: Dictionary, events: Array) -> String:
	return _json(
		{
			"step": index,
			"action": _plain(action),
			"state": _plain(state),
			"events": _plain(events),
		}
	)


func _hash(state: Dictionary, events: Array) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(_json({"state": _plain(state), "events": _plain(events)}).to_utf8_buffer())
	return context.finish().hex_encode()


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
		printerr("case parity: cannot write %s" % path)
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
