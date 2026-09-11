extends SceneTree

## The runner's state-level parity harness.
##
##   Godot --headless --path godot/runtime -s res://tools/runner_parity.gd \
##       --quit-after 100000 -- --script <abs replay json> --out <abs jsonl>
##
## It builds the world the browser's replay test built, drives the same scripted
## intents, and prints the same digest in the same shape — one JSON object per
## line, `<frame> <json>`, every `digest_every` steps. `tools/compare.py` diffs
## it against the `.web.jsonl` beside the script and names the first step and
## field that parted company.
##
## The digest shape is the browser's `plain()` and every rule in it is load
## bearing, because a shape that differs is a diff on every line and proves
## nothing. Keys are sorted. The generator and the frozen config are skipped: one
## is a closure and the other never moves. A Set becomes a sorted array. A number
## that is exactly an integer prints as an integer and anything else prints as a
## **string** of nine decimals — which is how a float comparison is made exact
## rather than approximate, and why "mean 0.0000" is not the claim here.
##
## An empty Dictionary is this port's `null`: GDScript has no nullable
## Dictionary, so "no fight", "no moment", "no gauge" and "nowhere to recover to"
## are all the empty one, and the digest writes what the browser wrote.

## The step is read from the script rather than assumed: the platformer's is
## 1/30, and a harness that defaulted to one genre's rate would replay the
## other's intents over twice the world.
const DEFAULT_STEP := 1.0 / 60.0


func _initialize() -> void:
	var args := _args()
	var script_path := String(args.get("script", ""))
	var out_path := String(args.get("out", ""))
	if script_path.is_empty() or out_path.is_empty():
		push_error("runner parity: --script and --out are both required")
		quit(2)
		return
	var script: Variant = _read_json(script_path)
	if not (script is Dictionary):
		push_error("runner parity: %s is not a replay script" % script_path)
		quit(2)
		return
	var replay: Dictionary = script
	var manifest_path := script_path.get_base_dir().path_join("../manifest.json").simplify_path()
	var manifest: Variant = _read_json(manifest_path)
	var config: Variant = RunnerContract.parse(manifest)
	if KernelRefusal.is_refusal(config):
		push_error("runner parity: %s" % (config as KernelRefusal).line())
		quit(2)
		return

	var sealed: Variant = RunnerRoster.seal()
	if KernelRefusal.is_refusal(sealed):
		push_error("runner parity: %s" % (sealed as KernelRefusal).line())
		quit(2)
		return
	var order := sealed as KernelSealed

	var latch: Variant = FamilyIntent.of(
		RunnerWorld.neutral_intent(),
		PackedStringArray(["jump", "action"]),
		PackedStringArray(["duck", "thrust"])
	)
	RunnerIntentSystem.latch = latch
	RunnerSessionSystem.pending_seed = -1

	# The golden's world plays without fights: the browser's replay test binds no
	# boss, because a hit box needs a measured atlas and a headless replay loads
	# none. So the encounter system runs and returns, every frame, in both.
	var world := RunnerWorld.create(config, int(replay["seed"]), false, {})

	var step_seconds := float(replay.get("step_seconds", DEFAULT_STEP))
	var frames := int(replay["frames"])
	var every := int(replay["digest_every"])
	var lines := PackedStringArray()
	# One unchained sha256 per frame, beside the sampled digests. The two answer
	# different questions: the sampled world says *why* a run parted company, and
	# this says *which frame* it did — a diff rather than a claim.
	var hashes := PackedStringArray()
	for frame in range(1, frames + 1):
		_drive(latch, replay, frame)
		var step := {"dt": DEFAULT_STEP, "now": float(frame) * DEFAULT_STEP, "frame": frame}
		world.events.begin_frame()
		order.tick(world, step)
		# The composition's reset list, applied at the frame boundary: a system
		# that reset the world mid-frame would leave the systems after it reading
		# a world that no longer matches the events they are about to consume.
		if not world.events.of_type("run-restarted").is_empty():
			order.reset(world, FamilySession.SCOPE_RUN)
			world.events.discard_frames()
		hashes.append("%d %s" % [frame, _frame_hash(world)])
		if frame % every == 0:
			lines.append("%d %s" % [frame, _digest(world)])
	var file := FileAccess.open(out_path, FileAccess.WRITE)
	if file == null:
		push_error("runner parity: cannot write %s" % out_path)
		quit(2)
		return
	file.store_string("\n".join(lines) + "\n")
	file.close()
	var frames_path := out_path.get_basename() + "-frames.txt"
	var frames_file := FileAccess.open(frames_path, FileAccess.WRITE)
	if frames_file == null:
		push_error("runner parity: cannot write %s" % frames_path)
		quit(2)
		return
	frames_file.store_string("\n".join(hashes) + "\n")
	frames_file.close()
	print(
		"runner parity: %d digests and %d frame hashes written beside %s"
		% [lines.size(), hashes.size(), out_path]
	)
	quit(0)


## The scripted intents, in the browser's own vocabulary: `press` is one edge on
## exactly that frame, `hold` is a level down from `from` through `until`.
func _drive(latch: FamilyIntent, replay: Dictionary, frame: int) -> void:
	var levels := {"duck": false, "thrust": false}
	for entry: Variant in (replay["intents"] as Array):
		var intent: Dictionary = entry
		if intent.has("frame") and int(intent["frame"]) == frame:
			for key: Variant in (intent.get("press", []) as Array):
				latch.request(String(key))
		if intent.has("from"):
			var inside := frame >= int(intent["from"]) and frame <= int(intent["until"])
			for key: Variant in (intent.get("hold", []) as Array):
				if inside:
					levels[String(key)] = true
	for key: Variant in levels:
		latch.set_level(String(key), bool(levels[key]))


## The browser's per-frame hash: sha256 over the same record the sampled digest
## carries, unchained, so one moved frame shows as one moved line.
func _frame_hash(world: RunnerWorld) -> String:
	var events: Array = []
	for entry: Variant in world.events.frame():
		events.append(_plain(entry))
	var record := {"world": _plain(_slices(world)), "events": events}
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(_json(record).to_utf8_buffer())
	return context.finish().hex_encode()


func _digest(world: RunnerWorld) -> String:
	var events: Array = []
	for entry: Variant in world.events.frame():
		events.append(_plain(entry))
	return _json({"e": events, "w": _plain(_slices(world))})


## The fourteen slices both digests cover.
func _slices(world: RunnerWorld) -> Dictionary:
	return {
		"avatar": world.avatar,
		"camera": world.camera,
		"clock": world.clock,
		"difficulty": world.difficulty,
		"encounter": world.encounter,
		# The queue is an object on both sides and both digests walk it, so it
		# appears twice: once as `e`, and once inside the world where the
		# browser's own walk found it.
		"events": {"frame": world.events.frame()},
		"fx": world.fx,
		"intent": world.intent,
		"locomotion": world.locomotion,
		"obstacles": _obstacles(world.obstacles),
		"run": _run(world.run),
		"score": world.score,
		"segments": _segments(world.segments),
		"vitals": world.vitals,
	}


## The four ledgers are Sets on the browser side and Dictionaries here, so they
## are written the way a Set is: sorted, and by their keys alone.
func _obstacles(obstacles: Dictionary) -> Dictionary:
	var made := obstacles.duplicate()
	for key in ["collected", "missed", "struck", "cleared"]:
		var keys := (obstacles[key] as Dictionary).keys()
		keys.sort()
		made[key] = keys
	return made


func _run(run: Dictionary) -> Dictionary:
	# The generator is a closure on the browser side and an object here; neither
	# is state a digest can compare, and both are skipped.
	var made := run.duplicate()
	made.erase("rng")
	return made


func _segments(segments: Dictionary) -> Dictionary:
	var made := segments.duplicate()
	# The browser starts with no previous chunk at all; -1 is how that is said
	# here, and the digest says it the browser's way.
	if int(segments["lastChunkIndex"]) < 0:
		made["lastChunkIndex"] = null
	return made


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
	if value is float:
		var number: float = value
		if number == floor(number) and absf(number) < 9.0e15:
			return int(number)
		return "%.9f" % number
	return value


## Compact JSON, byte for byte what `JSON.stringify` writes in the browser.
##
## The engine's own writer puts a space after every colon, which is a different
## string and so a different sha256 — six hundred hashes that all differ for a
## reason that is not the simulation. The digest is a contract between two
## runtimes, so it is written here rather than borrowed from whichever formatter
## an engine happens to ship.
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
