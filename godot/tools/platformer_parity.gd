extends SceneTree

## The platformer's state-level parity harness.
##
##   Godot --headless --path godot -s res://tools/platformer_parity.gd \
##       --quit-after 100000 -- --script <abs replay json> --out <abs jsonl>
##
## It builds the world the browser's replay test built, drives the same scripted
## intents at the platformer's own step of 1/30, and prints the same record in
## the same shape — `<frame> <json>`, every `digest_every` frames, plus one
## unchained sha256 per frame beside it. `tools/compare.py` diffs the sampled
## file against the `.web.jsonl` and names the first field that parted company;
## the frame hashes name the first frame.
##
## The serialiser is `runner_parity.gd`'s and every rule in it is load bearing:
## keys sorted, an empty Dictionary written as `null`, a whole float printed as
## an integer and any other float as a **string** of nine decimals, and compact
## JSON written here rather than borrowed from the engine, whose own writer puts
## a space after every colon and would move all six hundred hashes for a reason
## that is not the simulation.
##
## Why a second harness rather than the runner's: a platformer replay carries no
## seed and its step is 1/30 rather than 1/60, its world is a class with
## twenty-four slices rather than fourteen, and its scripted keys include four
## the player intent does not carry — `interact`, `enter`, `up` and `space` are
## pressed at the scene rather than by the body.

## The platformer's step, from `PlatformerVertical.FIXED_STEP_SECONDS`. Read from
## the script rather than assumed, because a harness that defaulted to the
## runner's 1/60 would replay the same intents over twice the world.
const DEFAULT_STEP := 1.0 / 30.0

## The keys the scripted run presses at the scene rather than through the body.
const SCENE_KEYS := ["interact", "enter", "up", "space"]

## Which scene keys were down on the frame before this one, so a level can be
## turned back into the edge the browser reads.
var _scene_keys_last: Dictionary = {}


func _initialize() -> void:
	var args := _args()
	var script_path := String(args.get("script", ""))
	var out_path := String(args.get("out", ""))
	if script_path.is_empty() or out_path.is_empty():
		push_error("platformer parity: --script and --out are both required")
		quit(2)
		return
	var script: Variant = _read_json(script_path)
	if not (script is Dictionary):
		push_error("platformer parity: %s is not a replay script" % script_path)
		quit(2)
		return
	var replay: Dictionary = script
	var manifest_path := script_path.get_base_dir().path_join("../manifest.json").simplify_path()
	var manifest: Variant = _read_json(manifest_path)
	if not (manifest is Dictionary):
		push_error("platformer parity: %s is not a manifest" % manifest_path)
		quit(2)
		return
	var package: Variant = PlatformerMaps.parse(manifest)
	if KernelRefusal.is_refusal(package):
		push_error("platformer parity: %s" % (package as KernelRefusal).line())
		quit(2)
		return

	var world := PlatformerWorld.create(package as Dictionary, manifest as Dictionary)
	if world.player.is_empty():
		push_error("platformer parity: the package opens on no spawn")
		quit(2)
		return

	var step_seconds := float(replay.get("step_seconds", DEFAULT_STEP))
	var frame_ms := step_seconds * 1000.0
	var frames := int(replay["frames"])
	var every := int(replay["digest_every"])
	var lines := PackedStringArray()
	var hashes := PackedStringArray()
	for frame in range(1, frames + 1):
		world.events.begin_frame()
		world.intent = _intent_for(replay, frame)
		# `frame * frame_ms`, and the association is not incidental: the browser
		# multiplies the frame by a millisecond step, and `(frame * seconds) *
		# 1000` rounds differently in the last place. One ulp is enough to decide
		# whether an attack window that ends exactly on a frame boundary is still
		# open on it.
		_step(world, step_seconds, float(frame) * frame_ms, frame)
		hashes.append("%d %s" % [frame, _frame_hash(world)])
		if frame % every == 0:
			lines.append("%d %s" % [frame, _digest(world)])

	if not _write(out_path, "\n".join(lines) + "\n"):
		quit(2)
		return
	if not _write(out_path.get_basename() + "-frames.txt", "\n".join(hashes) + "\n"):
		quit(2)
		return
	print(
		"platformer parity: %d digests and %d frame hashes written beside %s"
		% [lines.size(), hashes.size(), out_path]
	)
	quit(0)


## One frame of the world, in the browser's own order.
##
## The sealed roster lands when there are enough systems for a sealer to have an
## opinion about; until then the order is written out, and it is the order
## `assemblePlatformerSystems` declares — the conversation before the body,
## because a held frame is decided before it is spent.
func _step(world: PlatformerWorld, step_seconds: float, now_ms: float, frame: int) -> void:
	var step := {"dt": step_seconds * 1000.0, "now": now_ms, "frame": frame}
	PlatformerSoundtrackSystem.update(world, step)
	PlatformerDialogueSystem.update(world, step)
	PlatformerClockSystem.update(world, step)
	if world.hold:
		PlatformerMapEntrySystem.apply(world, step)
		return
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	var terrain := {
		"heights": map["heights"],
		"tilePx": PlatformerMaps.TILE_PX,
		"baselineY": PlatformerMaps.BASELINE_Y,
		"worldWidthPx": map["worldWidthPx"],
		"platforms": world.platforms,
		"climbables": world.climbables,
		"maximumAirJumps": PlatformerVertical.AIR_JUMPS_MAX,
		"combatEnabled": world.package["combatEnabled"],
	}
	PlatformerPlayer.update(
		world.player,
		terrain,
		world.simulation_dt,
		now_ms,
		world.intent,
		PlatformerWeapon.profile(world.weapon_class)
	)
	# The blow a creature committed on the frame before this one, read here rather
	# than after the creatures move: the browser resolves contact inside
	# `player/update`, so every creature this touches is where it stood at the end
	# of the previous frame. Resolving it a step later lands it a frame early.
	PlatformerMobsSystem.strike(world, step)
	PlatformerCameraSystem.update(world, step)
	PlatformerProjectilesSystem.throw_one(world, step)
	PlatformerMobsSystem.populate(world, step)
	PlatformerMobsSystem.step(world, step)
	PlatformerProjectilesSystem.update(world, step)
	PlatformerDialogueSystem.prompt(world, step)
	PlatformerMapEntrySystem.ask(world)
	PlatformerMapEntrySystem.apply(world, step)


## The scripted intents, in the browser's own vocabulary: `hold` is a level down
## from `from` through `until` inclusive, `press` is one edge on exactly that
## frame, and `keys` are the scene-level presses the body does not carry.
func _intent_for(replay: Dictionary, frame: int) -> Dictionary:
	var made := PlatformerWorld.neutral_intent()
	var held := {}
	for key in SCENE_KEYS:
		made[key] = false
		held[key] = false
	for entry: Variant in (replay["intents"] as Array):
		var intent: Dictionary = entry
		if intent.has("from"):
			if frame >= int(intent["from"]) and frame <= int(intent["until"]):
				for key: Variant in (intent.get("hold", []) as Array):
					made[String(key)] = true
		if intent.has("frame") and int(intent["frame"]) == frame:
			for key: Variant in (intent.get("press", []) as Array):
				made[String(key)] = true
			for key: Variant in (intent.get("keys", []) as Array):
				held[String(key)] = true
	# A scene key is an **edge**, not a level. The browser reads them with
	# `JustDown`, and the script's `keys` are levels: two consecutive frames both
	# listing `up` is one press held across two frames, and it opens one gate.
	# The golden says so plainly — the defeat run's own comment presses `up` "on
	# alternate frames so each press is a fresh edge" — and a harness that fed
	# levels would walk through the gate it just arrived at.
	for key in SCENE_KEYS:
		made[key] = bool(held[key]) and not bool(_scene_keys_last.get(key, false))
	# The gate reads a press; the ladder reads the same key held. Both come off
	# the one scene key, and separating them here is what lets a body climb
	# without walking through every doorway it passes.
	made["upPressed"] = bool(made["up"])
	made["up"] = bool(held["up"]) or bool(made["up"])
	_scene_keys_last = held
	return made


## The browser's per-frame hash: sha256 over the same record the sampled digest
## carries, unchained, so one moved frame shows as one moved line.
func _frame_hash(world: PlatformerWorld) -> String:
	var context := HashingContext.new()
	context.start(HashingContext.HASH_SHA256)
	context.update(_json(_record(world)).to_utf8_buffer())
	return context.finish().hex_encode()


func _digest(world: PlatformerWorld) -> String:
	var record := _record(world)
	return _json({"e": record["events"], "w": record["world"]})


func _record(world: PlatformerWorld) -> Dictionary:
	var events: Array = []
	for entry: Variant in world.events.frame():
		events.append(_plain(entry))
	return {"world": _plain(world.snapshot()), "events": events}


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
	if value is PackedInt32Array:
		var made: Array = []
		for entry in (value as PackedInt32Array):
			made.append(entry)
		return made
	if value is float:
		var number: float = value
		if number == floor(number) and absf(number) < 9.0e15:
			return int(number)
		return "%.9f" % number
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


func _write(path: String, body: String) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("platformer parity: cannot write %s" % path)
		return false
	file.store_string(body)
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
