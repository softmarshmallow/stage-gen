class_name Smoke
extends SceneTree

## The play smoke: run the real scene in a real window, play twelve seconds of
## the game with scripted keys, save three frames, and time the render loop.
##
##   Godot --path godot/oblique_survival --rendering-driver metal \
##       -s res://tools/smoke.gd -- --run <absolute run dir> --out <directory> \
##       [--seconds 12] [--timing-frames 120]
##
## This is the one host run where the render loop must be **on**: the capture
## harness takes its pictures with `--disable-render-loop` and
## `RenderingServer.force_draw`, which says nothing about what a frame costs
## while somebody is playing. Here the window is the project's own 1600x900,
## vsync is off (`project.godot` sets `vsync_mode = 0`), and the loop runs free
## so a frame's time is the frame's work.
##
## The twelve seconds are simulated one fixed step per real frame, with the
## keys fed through the harness (`main.press_key` / `release_key`), so what the
## window shows is what a player would see. The script: walk to the nearest
## pine, take an axe from the dev pack control, chop the pine down, walk to a
## log it dropped, pick it up, and open the craft panel. Nothing here asserts a
## game rule — the headless tests do that. It is here to catch what only a
## whole running frame can: a module that crashes on an event, a texture that
## is not there when the look swaps, a frame that costs too much.

const STEP := 1.0 / 60.0
const WINDOW := Vector2i(1600, 900)
const DEFAULT_SECONDS := 12.0
const DEFAULT_TIMING_FRAMES := 120
## How close the walk has to get before the axe starts swinging.
const CHOP_RANGE := 2.4
const PICKUP_RANGE := 1.0
## The keys are re-aimed at this interval; every step would be pointless.
const STEER_SECONDS := 0.25

var _run := ""
var _out := ""
var _seconds := DEFAULT_SECONDS
var _timing_frames := DEFAULT_TIMING_FRAMES

var _main = null
var _world = null
var _phase := "walk"
var _target: Variant = null
var _held := {}
var _next_steer := 0.0
var _log: Array[String] = []
var _errors := 0

func _initialize() -> void:
	var argv := OS.get_cmdline_user_args()
	_run = _arg(argv, "--run", "")
	_out = _arg(argv, "--out", "").rstrip("/")
	_seconds = maxf(1.0, float(_arg(argv, "--seconds", str(DEFAULT_SECONDS))))
	_timing_frames = maxi(10, int(_arg(argv, "--timing-frames", str(DEFAULT_TIMING_FRAMES))))
	if _run == "" or _out == "":
		printerr("smoke: --run <run dir> and --out <directory> are both required")
		quit(2)
		return
	if DisplayServer.get_name() == "headless":
		printerr("smoke: this run needs a real window; drop --headless")
		quit(2)
		return
	DisplayServer.window_set_size(WINDOW)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0
	DirAccess.make_dir_recursive_absolute(_out)
	_play()

func _play() -> void:
	var main = load("res://main.tscn").instantiate()
	main.arg_overrides = {"run": _run, "mode": "play", "time": "noon"}
	# The smoke drives the steps itself for the scripted stretch, then hands
	# the loop back for the timing run.
	main.autostep = false
	root.add_child(main)
	await process_frame
	await process_frame
	if main.world == null:
		printerr("smoke: the run did not open; nothing to play")
		quit(1)
		return
	_main = main
	_world = main.get_world()
	# Take the sampler off the keyboard before the first step: `HostInput`
	# polls the machine's keys until somebody feeds it one, so a modifier fed
	# and dropped immediately is what claims the key set for this script.
	_main.release_all_keys()
	_main.press_key("shift")
	_main.release_key("shift")

	await _save("smoke-0s.png")

	var steps := int(round(_seconds / STEP))
	var half := steps / 2
	for index in range(steps):
		var elapsed := float(index) * STEP
		_script(elapsed)
		_main.frame(STEP, true)
		_drain_messages()
		await process_frame
		if index == half - 1:
			await _save("smoke-%ds.png" % int(_seconds / 2.0))
	await _save("smoke-%ds.png" % int(_seconds))

	print("[smoke] script: %s" % " | ".join(_log))
	print("[smoke] world:  %s" % _main.status())
	await _timing()
	print("[smoke] done, %d errors" % _errors)
	quit(1 if _errors > 0 else 0)

# ------------------------------------------------------------------ the script

## One simulated step of scripted play. Every branch is defensive: the smoke
## must reach the end and report, not stop at the first thing it cannot find.
func _script(elapsed: float) -> void:
	# Whatever the world did, the last stretch belongs to the craft panel: the
	# smoke has to reach its last frame with the HUD's biggest layer drawn.
	if elapsed > _seconds * 0.85 and _phase != "craft" and _phase != "done":
		_note("giving up on '%s' at %.1f s; opening the craft panel" % [_phase, elapsed])
		_stop()
		_target = null
		_phase = "craft"
	if elapsed >= 0.5 and _phase == "walk" and _target == null:
		var given: int = _main.give("axe", 1)
		_note("axe given" if given == 0 else "axe did not fit (%d left over)" % given)
		_target = _nearest_prop("pine")
		if _target == null:
			_note("no pine in the layout; walking anyway")
			_phase = "craft"
		else:
			_note("nearest pine %.1f m away" % _distance(_target))
	match _phase:
		"walk":
			if _target == null:
				return
			if _distance(_target) <= CHOP_RANGE:
				_stop()
				_phase = "chop"
				_note("in range at %.1f s" % elapsed)
				return
			if elapsed >= _next_steer:
				_next_steer = elapsed + STEER_SECONDS
				_steer_towards(_target)
		"chop":
			# Space is held: the interact system swings again the moment the
			# last swing ends, and commits to a walk when the target drifts
			# out of reach.
			_hold("space", true)
			if String((_target as Dictionary).get("state", "")) != "grown":
				_hold("space", false)
				_note("pine felled at %.1f s (state %s)" % [
					elapsed, String((_target as Dictionary).get("state", "?"))])
				_target = null
				_phase = "collect"
		"collect":
			if _target == null:
				_target = _nearest_item("log")
				if _target == null:
					return
				_note("log on the ground %.1f m away" % _distance(_target))
			if not _world.entities.has(_target):
				_stop()
				_note("log picked up at %.1f s (%d in the pack)" % [
					elapsed, Inventory.count(_world, "log")])
				_target = null
				_phase = "craft"
				return
			if _distance(_target) <= PICKUP_RANGE:
				_stop()
				_hold("space", true)
			elif elapsed >= _next_steer:
				_next_steer = elapsed + STEER_SECONDS
				_steer_towards(_target)
		"craft":
			_stop()
			if not bool(_world.craft_open):
				_main.press_key("c")
				_main.release_key("c")
			else:
				_note("craft panel open at %.1f s" % elapsed)
				_phase = "done"

## Screen-space keys for a world-space direction. Input is turned into world
## space by the camera yaw (`SysPlayerMove`), so this is that rotation
## inverted: x = wx·cos − wz·sin, z = wx·sin + wz·cos.
func _steer_towards(entity: Variant) -> void:
	var to_x: float = float((entity as Dictionary)["x"]) - _world.player.x
	var to_z: float = float((entity as Dictionary)["z"]) - _world.player.z
	var length := sqrt(to_x * to_x + to_z * to_z)
	if length < 0.001:
		_stop()
		return
	to_x /= length
	to_z /= length
	var c := cos(_world.camera_yaw)
	var s := sin(_world.camera_yaw)
	var x := to_x * c - to_z * s
	var z := to_x * s + to_z * c
	_hold("d", x > 0.38)
	_hold("a", x < -0.38)
	_hold("s", z > 0.38)
	_hold("w", z < -0.38)

func _stop() -> void:
	for name: String in ["w", "a", "s", "d", "space"]:
		_hold(name, false)

func _hold(name: String, down: bool) -> void:
	if bool(_held.get(name, false)) == down:
		return
	_held[name] = down
	if down:
		_main.press_key(name)
	else:
		_main.release_key(name)

func _nearest_prop(prop_id: String) -> Variant:
	var best: Variant = null
	var best_distance := INF
	for entity: Dictionary in _world.entities:
		if String(entity.get("kind", "")) != "prop" or String(entity.get("prop_id", "")) != prop_id:
			continue
		if String(entity.get("state", "")) != "grown":
			continue
		var distance := _distance(entity)
		if distance < best_distance:
			best_distance = distance
			best = entity
	return best

func _nearest_item(item_id: String) -> Variant:
	var best: Variant = null
	var best_distance := INF
	for entity: Dictionary in _world.entities:
		if String(entity.get("kind", "")) != "item" or String(entity.get("item_id", "")) != item_id:
			continue
		var distance := _distance(entity)
		if distance < best_distance:
			best_distance = distance
			best = entity
	return best

func _distance(entity: Variant) -> float:
	var dx: float = float((entity as Dictionary)["x"]) - _world.player.x
	var dz: float = float((entity as Dictionary)["z"]) - _world.player.z
	return sqrt(dx * dx + dz * dz)

## The world's own messages, so a refusal ("needs a Flint axe") shows up in the
## smoke's log rather than only on the HUD for a third of a second.
func _drain_messages() -> void:
	var said := String(_world.message)
	if said != "" and (_log.is_empty() or not _log[_log.size() - 1].ends_with(said)):
		if _world.message_at >= _world.time - STEP * 1.5:
			_note("said: %s" % said)

func _note(line: String) -> void:
	_log.append(line)
	print("[smoke] %s" % line)

# ------------------------------------------------------------------- the timing

## Hand the loop back to `main._process` and time whole frames. `process_frame`
## fires once per main-loop iteration, which with the render loop on is once
## per drawn frame; vsync is off, so the delta is the frame's work and not the
## display's refresh.
func _timing() -> void:
	_main.autostep = true
	_stop()
	# Two frames to settle after the scripted stretch before the clock starts.
	await process_frame
	await process_frame
	var total := 0
	var worst := 0
	var worst_at := 0
	var last := Time.get_ticks_usec()
	for index in range(_timing_frames):
		await process_frame
		var now := Time.get_ticks_usec()
		var delta := now - last
		last = now
		total += delta
		if delta > worst:
			worst = delta
			worst_at = index
	var average := float(total) / float(_timing_frames) / 1000.0
	print("[smoke] frame time over %d frames at %dx%d: average %.2f ms (%.0f fps), worst %.2f ms (frame %d); engine fps %d" % [
		_timing_frames, WINDOW.x, WINDOW.y, average,
		1000.0 / maxf(average, 0.001), float(worst) / 1000.0, worst_at,
		Engine.get_frames_per_second(),
	])
	# The same frames again, with the step driven from here, so the host's own
	# work (the fixed step and every module's `update`) can be told apart from
	# what the engine spends drawing what those modules built.
	_main.autostep = false
	_main.reset_profile()
	_main.profile = true
	var script_total := 0
	var script_worst := 0
	last = Time.get_ticks_usec()
	total = 0
	for _index in range(_timing_frames):
		var before := Time.get_ticks_usec()
		_main.frame(STEP, true)
		var after := Time.get_ticks_usec()
		script_total += after - before
		script_worst = maxi(script_worst, after - before)
		await process_frame
		var now := Time.get_ticks_usec()
		total += now - last
		last = now
	var script_average := float(script_total) / float(_timing_frames) / 1000.0
	var whole := float(total) / float(_timing_frames) / 1000.0
	print("[smoke] of a %.2f ms frame, the host's step and module updates are %.2f ms (worst %.2f); the engine's own %.2f ms" % [
		whole, script_average, float(script_worst) / 1000.0, whole - script_average,
	])
	_main.profile = false
	var per_module: Array = []
	for id: String in _main.module_micros.keys():
		per_module.append([float(_main.module_micros[id]) / float(_timing_frames) / 1000.0, id])
	per_module.sort_custom(func(a, b): return a[0] > b[0])
	var line: Array[String] = []
	for entry: Array in per_module:
		if entry[0] >= 0.05:
			line.append("%s %.2f" % [entry[1], entry[0]])
	print("[smoke] per module, ms a frame: %s" % ", ".join(line))
	# The simulation's own fifteen, so the ~13 ms that is neither a module nor
	# the engine can be read rather than guessed at.
	var per_system: Array = []
	for id: String in Sim.system_micros.keys():
		per_system.append([float(Sim.system_micros[id]) / float(_timing_frames) / 1000.0, id])
	per_system.sort_custom(func(a, b): return a[0] > b[0])
	var system_line: Array[String] = []
	for entry: Array in per_system:
		if entry[0] >= 0.02:
			system_line.append("%s %.2f" % [entry[1], entry[0]])
	print("[smoke] per system, ms a frame: %s" % ", ".join(system_line))

# -------------------------------------------------------------------- pictures

## The window's own frame, HUD and all: this is a play smoke, not a picture
## gate, so nothing is hidden. `frame_post_draw` is safe here and only here —
## it never emits under `--headless` (capabilities map §3c).
func _save(file_name: String) -> void:
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	if image == null:
		printerr("smoke: no image came back for %s" % file_name)
		_errors += 1
		return
	var path := "%s/%s" % [_out, file_name]
	var error := image.save_png(path)
	if error != OK:
		printerr("smoke: could not write %s (error %d)" % [path, error])
		_errors += 1
		return
	print("[smoke] %s  %dx%d" % [path, image.get_width(), image.get_height()])

static func _arg(argv: PackedStringArray, name: String, fallback: String) -> String:
	for i in range(argv.size()):
		if argv[i] == name and i + 1 < argv.size():
			return argv[i + 1]
		if argv[i].begins_with(name + "="):
			return argv[i].substr(name.length() + 1)
	return fallback
