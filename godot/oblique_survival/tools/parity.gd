extends SceneTree

## The state-level parity harness: the host half.
##
##   Godot --headless --path godot/oblique_survival -s res://tools/parity.gd \
##       --quit-after 100000 -- --run <absolute run dir> \
##       --script res://tools/parity/02-walk-and-chop.json --out <abs jsonl>
##
## It runs one scripted input on the simulation and prints a world digest every
## N steps, one JSON object per line. `tools/parity_web.js.txt` runs the same script
## on the web viewer and prints the same lines; `tools/parity_diff.py` compares
## the two and names the first step and field that parted company. That is the
## critique's section D2 gate: parity with the viewer proved on the world's own
## numbers rather than on a picture.
##
## Nothing is drawn and no view module is built. The world here is exactly the
## one `main.gd` builds for `--mode play --time <t> --season <s> --weather <w>`,
## the keys go through the same `HostInput` sampler `main.gd` samples with, and
## the step is `Sim.step` at the fixed step — so a divergence is the
## simulation's, never the frame owner's.
##
## The input script (`tools/parity/*.json`):
##
##   {
##     "name": "02-walk-and-chop",
##     "mode": "play", "time": "noon", "season": "auto", "weather": "auto",
##     "give": {"axe": 1},
##     "digest_every": 60,
##     "steps": [
##       {"until": 300, "held": ["d"]},
##       {"until": 900, "held": ["space"], "press": ["f"]},
##       {"until": 1800, "held": []}
##     ]
##   }
##
## `until` is an absolute step number, one-based, and an entry covers every step
## up to and including it. `held` is the set of keys down for those steps, in the
## viewer's own lowercase names (`w`, `d`, `space`, `arrowleft`); a key that
## appears in one entry and not the next is released at the boundary and a key
## that appears in neither is never touched, so a held key does not re-fire the
## one-shot verbs. `press` is the one-shots (`f`, `c`, `x`, `z`, `,`, `.`, a
## digit): each is pressed and released on the first step of its entry, which is
## exactly one keydown, and lives for exactly one simulation step. `give` fills
## the pack before the first step, one unit per `invAdd`, the way the viewer's
## `give one` dev control does — the only way a script can hold a tool, because
## this run authors no `crafting.start`.
##
## Flags: `--run` and `--script` are required. `--out` writes the lines to a
## file (stdout carries the engine's own boot noise, so a diff wants the file).
## `--mode`, `--time`, `--season`, `--weather` and `--seed` override the script.
## `--quiet` prints nothing.

const FIXED_STEP := 1.0 / 60.0
## `world.message` is one line; the digest wants the run of them, so the harness
## keeps its own ring of the last few. Read-only: it watches the field change.
const MESSAGE_HISTORY := 5
## Both sides round every float to four decimals before printing, with the same
## arithmetic (`floor(v / q + 0.5) * q`), so a rounded field is comparable
## digit for digit and the diff's tolerance is slack rather than the mechanism.
const QUANTUM := 0.0001

var _out_lines: PackedStringArray = PackedStringArray()
var _quiet: bool = false


func _init() -> void:
	var flags := _flags(OS.get_cmdline_user_args())
	_quiet = flags.has("quiet")

	var run := String(flags.get("run", ""))
	var script_path := String(flags.get("script", ""))
	if run == "" or script_path == "":
		push_error("parity: --run <run directory> and --script <input script json> are both required")
		quit(2)
		return

	var script: Dictionary = _read_json(script_path)
	if script.is_empty():
		push_error("parity: could not read an input script at %s" % script_path)
		quit(2)
		return

	var mode := String(flags.get("mode", script.get("mode", "play")))
	var time := String(flags.get("time", script.get("time", "noon")))
	var season := String(flags.get("season", script.get("season", "auto")))
	var weather := String(flags.get("weather", script.get("weather", "auto")))
	var seed_flag := int(flags.get("seed", script.get("seed", 0)))
	var digest_every := int(script.get("digest_every", 60))

	# The world `main.gd` builds, built the same way: the package's layout, the
	# layout's seed unless one was named, and the four start options.
	var pkg := RunPackage.open(run)
	if pkg == null:
		push_error("parity: could not open the run at %s" % run)
		quit(2)
		return
	var layout: Dictionary = pkg.layout if not pkg.layout.is_empty() else pkg.manifest.get("layout", {})
	var seed_value: int = seed_flag if seed_flag != 0 else int(layout.get("seed", 1))
	var world := World.create(pkg, seed_value, {
		"mode": mode, "time": time, "season": season, "weather": weather,
	})
	# The camera's yaw is the simulation's only camera input: `main.gd` writes
	# `world.camera_yaw = rig.yaw` every frame and the viewer does the same, so
	# a headless run must hold the rig's resting yaw (manifest.camera.yaw_degrees,
	# 45 by default) or `d` walks east instead of screen-right.
	var camera_spec: Dictionary = pkg.manifest.get("camera", {})
	world.camera_yaw = deg_to_rad(float(camera_spec.get("yaw_degrees", 45.0)))

	# The keyboard the game itself samples. It is kept outside the scene tree
	# here exactly as `main.gd` keeps it, and the one release below is what
	# takes it off the machine's keyboard (`HostInput.polling`): a headless run
	# must not read whatever is held down on the desk.
	var sampler := HostInput.new()
	sampler.bind(world)
	sampler.set_mode(mode)
	sampler.release("space")

	# The script's opening kit, one unit at a time, which is exactly what the
	# viewer's `give one` dev control does per click (`invAdd(world, id, 1)`,
	# and its refusal line when the pack is full). A script that wants to prove
	# an interaction needing a tool has no other way to hold one: this run's
	# `crafting.start` is empty on both sides.
	var give: Dictionary = script.get("give", {}) if script.get("give") is Dictionary else {}
	for item_id: String in give.keys():
		for _n in range(int(give[item_id])):
			if Inventory.inv_add(world, item_id, 1) > 0:
				Helpers.say(world, "Hands full.")

	# The counter starts at the first scripted step, not at world creation, so
	# the web side (which can only patch its generator once the page is up)
	# counts the same span.
	world.rng.draws = 0

	var steps_spec: Array = script.get("steps", []) if script.get("steps") is Array else []
	var total := 0
	for entry: Variant in steps_spec:
		if entry is Dictionary:
			total = maxi(total, int((entry as Dictionary).get("until", 0)))
	if total <= 0:
		push_error("parity: the input script has no steps")
		quit(2)
		return

	var held: Dictionary = {}
	var event_counts: Dictionary = {}
	var messages: Array = []
	var last_message: String = world.message
	var last_message_at: float = world.message_at
	var segment := 0
	var last_segment := -1
	var digests := 0
	var digest: Dictionary = {}

	for step_index in range(1, total + 1):
		while segment < steps_spec.size() and step_index > int((steps_spec[segment] as Dictionary).get("until", 0)):
			segment += 1
		var entry: Dictionary = steps_spec[segment] if segment < steps_spec.size() else {}

		# The held set, as keyups then keydowns: a key held across a boundary is
		# not touched, so its one-shot (if it has one) does not fire twice.
		var want: Dictionary = {}
		for name: Variant in entry.get("held", []):
			want[String(name)] = true
		for name: String in held.keys():
			if not want.has(name):
				sampler.release(name)
				held.erase(name)
		for name: String in want.keys():
			if not held.has(name):
				sampler.press(name)
				held[name] = true
		if segment != last_segment:
			last_segment = segment
			for name: Variant in entry.get("press", []):
				sampler.press(String(name))
				sampler.release(String(name))

		# The frame owner's own two lines, and nothing else: write `world.input`
		# from the keys, then one fixed step.
		sampler.sample(world, mode)
		Sim.step(world, FIXED_STEP)

		# The event drain, counted by type. `main.gd` hands these to the modules
		# and clears the list; with no modules the clear is all that is left,
		# and the count is what the digest reports.
		for event: Variant in world.events:
			var type := String((event as Dictionary).get("type", ""))
			event_counts[type] = int(event_counts.get(type, 0)) + 1
		world.events.clear()

		if world.message != last_message or world.message_at != last_message_at:
			last_message = world.message
			last_message_at = world.message_at
			if last_message != "":
				messages.append(last_message)
				while messages.size() > MESSAGE_HISTORY:
					messages.remove_at(0)

		if digest_every > 0 and step_index % digest_every == 0:
			digest = _digest(world, step_index, event_counts, messages)
			_emit(JSON.stringify(digest, "", false))
			event_counts.clear()
			digests += 1

	_emit(JSON.stringify({
		"summary": true,
		"script": String(script.get("name", script_path.get_file().get_basename())),
		"seed": seed_value,
		"mode": mode,
		"start_time": time,
		"start_season": season,
		"start_weather": weather,
		"steps": total,
		"digest_every": digest_every,
		"digests": digests,
		"rng_draws": world.rng.draws,
		"entity_count": world.entities.size(),
		"drop_count": world.drop_count,
		"built": world.built,
		"final": _digest(world, total, event_counts, messages),
	}, "", false))

	sampler.free()
	var out := String(flags.get("out", ""))
	if out != "" and not _write(out):
		quit(1)
		return
	quit(0)


## One world digest. Every field the critique's D2 asks for, in the order
## `tools/parity_web.js.txt` writes them, floats rounded to four decimals.
static func _digest(world: World, step_index: int, event_counts: Dictionary, messages: Array) -> Dictionary:
	var player := world.player

	var counts: Dictionary = {}
	var forage_picked := 0
	var ground_items: Array = []
	for raw: Variant in world.entities:
		var entity: Dictionary = raw
		var kind := String(entity.get("kind", ""))
		if kind == "prop":
			var prop_key := "%s|%s" % [entity.get("prop_id", ""), entity.get("state", "")]
			counts[prop_key] = int(counts.get(prop_key, 0)) + 1
		elif kind == "mob":
			var mob_key := "mob:%s|%s" % [entity.get("actor_id", ""), entity.get("state", "")]
			counts[mob_key] = int(counts.get(mob_key, 0)) + 1
		elif kind == "forage":
			if bool(entity.get("picked", false)):
				forage_picked += 1
		elif kind == "item":
			# In the array's own order, which is the order they were dropped: if
			# the two runtimes ever spawn a pickup in a different order, that is
			# itself the divergence and sorting would hide it.
			if not bool(entity.get("taken", false)):
				ground_items.append({
					"id": String(entity.get("id", "")),
					"item": String(entity.get("item_id", "")),
					"x": _r4(entity.get("x", 0.0)),
					"z": _r4(entity.get("z", 0.0)),
				})

	var slots: Array = []
	for raw_slot: Variant in world.slots:
		if raw_slot == null:
			slots.append(null)
			continue
		var slot: Dictionary = raw_slot
		var uses: Variant = slot.get("uses", null)
		slots.append({
			"item": String(slot.get("item", "")),
			"count": int(slot.get("count", 0)),
			# -1 for "this item has no uses": the viewer writes `undefined`
			# there and `null` here, and neither survives a numeric diff.
			"uses": -1.0 if uses == null else _r4(uses),
		})

	var next_raw: float = world.rng.peek()
	return {
		"step": step_index,
		"time": _r4(world.time),
		"day": world.day,
		"day_phase": _r4(world.day_phase),
		"night": _r4(world.night),
		"season": String(world.season.get("id", "")),
		"weather": {
			"mode": String(world.weather.get("mode", "")),
			"rain": _r4(world.weather.get("rain", 0.0)),
			"snow": _r4(world.weather.get("snow", 0.0)),
			"condition": String(world.weather.get("condition", "")),
		},
		"rng_draws": world.rng.draws,
		"rng_next": _r4(next_raw),
		# The same value as the generator's own 32-bit word: an integer compares
		# exactly, where a float has to survive two JSON writers first.
		"rng_next_u32": int(round(next_raw * Mulberry32.DIVISOR)),
		"player": {
			"x": _r4(player.x),
			"z": _r4(player.z),
			"vx": _r4(player.vx),
			"vz": _r4(player.vz),
			"state": player.state,
			"facing": player.facing,
			"health": _r4(player.health),
			"hunger": _r4(player.hunger),
			"warmth": _r4(player.warmth),
			"busy": "" if player.busy == null else String((player.busy as Dictionary).get("state", "")),
		},
		"entities": _sorted(counts),
		"forage_picked": forage_picked,
		"ground_items": ground_items,
		"slots": slots,
		"torch": _r4(world.torch.get("remaining", 0.0)),
		"warm": _r4(world.warm.get("remaining", 0.0)),
		"messages": messages.duplicate(),
		"events": _sorted(event_counts),
	}


## A dictionary rebuilt with its keys in order, so two digests read the same way
## down the page even though the diff does not care.
static func _sorted(source: Dictionary) -> Dictionary:
	var keys := source.keys()
	keys.sort()
	var out: Dictionary = {}
	for key: Variant in keys:
		out[key] = source[key]
	return out


## Four decimals, by the arithmetic `parity_web.js.txt` uses to the operation:
## `floor(v / q + 0.5) * q`. Rounding the two sides the same way is what lets
## the diff hold `rng_next` to a tolerance that means something.
static func _r4(value: Variant) -> float:
	var v := float(value)
	if not is_finite(v):
		return 0.0
	return floor(v / QUANTUM + 0.5) * QUANTUM


func _emit(line: String) -> void:
	_out_lines.append(line)
	if not _quiet:
		print(line)


func _write(path: String) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_error("parity: could not write %s (%d)" % [path, FileAccess.get_open_error()])
		return false
	for line: String in _out_lines:
		file.store_line(line)
	file.close()
	return true


static func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	return parsed if parsed is Dictionary else {}


## `--flag value`, `--flag=value` and bare `--flag` (which becomes `true`).
static func _flags(argv: PackedStringArray) -> Dictionary:
	var out: Dictionary = {}
	var index := 0
	while index < argv.size():
		var token := argv[index]
		if not token.begins_with("--"):
			index += 1
			continue
		var equals := token.find("=")
		if equals > 0:
			out[token.substr(2, equals - 2)] = token.substr(equals + 1)
			index += 1
			continue
		var name := token.substr(2)
		if index + 1 < argv.size() and not argv[index + 1].begins_with("--"):
			out[name] = argv[index + 1]
			index += 2
		else:
			out[name] = true
			index += 1
	return out
