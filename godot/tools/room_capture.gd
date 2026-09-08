extends SceneTree

## The point-and-click room's gate sheet: five named states, photographed.
##
##   Godot --path godot --rendering-driver metal --disable-render-loop \
##       --audio-driver Dummy --quit-after 120000 -s res://tools/room_capture.gd -- \
##       --run <absolute run directory> --out <absolute directory> --shots all
##
## A room has no clock, so a shot is not a frame number the way the runner's is:
## it is a **named state**, reached by playing the clicks that reach it. The
## steps below are written against `out/the-grain-window-a4`, which is one of the
## two rooms published at the schema this build reads.
##
## Not headless. A picture needs a real display server; under the dummy renderer
## `get_texture().get_image()` returns null. The window is shrunk and minimised
## and the frames come out of an offscreen SubViewport at the room's own canvas
## size, which is taller than most screens and must not be clamped by one.
##
## The clear colour is a magenta nothing in any package is anywhere near, so a
## region nothing drew looks like a region nothing drew. `room_shots_check.py`
## reads it back.

const UNPAINTED := Color(1.0, 0.0, 1.0, 1.0)
const WINDOW_SIZE := Vector2i(160, 100)

## Each shot is a name and the steps that reach it, in order. A step is one of
## `{"click": <hotspot id>}`, `{"mode": "act"|"look"}` or `{"hints": true|false}`.
const SHOTS := [
	["boot", []],
	["look", [{"mode": "look"}]],
	["hints", [{"hints": true}]],
	# `stage_door` and not a middling one: at 516 characters it is the longest
	# sentence either shipped room can produce on a click, it requires nothing so
	# it is reachable first, and it is the one that did not fit the plate this
	# host first shipped.
	["narrated", [{"click": "stage_door"}]],
	["solved", [{"click": "the_man"}, {"click": "service_lift"}]],
]


func _initialize() -> void:
	var args := _args()
	var out_path := String(args.get("out", ""))
	if out_path.is_empty():
		printerr("room capture: --out is required")
		quit(2)
		return
	var sheet := String(args.get("shots", "")) == "all"
	_shrink_window()

	var scene: PackedScene = load("res://hosts/pointclick_room/main.tscn")
	if scene == null:
		printerr("room capture: the host scene did not load")
		quit(1)
		return
	RenderingServer.set_default_clear_color(UNPAINTED)

	var wanted: Array = SHOTS if sheet else [[String(args.get("shot", "boot")), []]]
	for entry: Variant in wanted:
		var shot: Array = entry
		# One host per shot. A room's state machine has no rewind — `fired` never
		# clears — so a sheet that walked one instance from state to state could
		# only ever photograph a monotone sequence, and the "before" of any pair
		# would be unreachable after the "after".
		var node: Node = scene.instantiate()
		var viewport := SubViewport.new()
		viewport.own_world_3d = true
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		viewport.transparent_bg = false
		root.add_child(viewport)
		viewport.add_child(node)
		# Two, not one: `_ready` is deferred to the first main-loop iteration, and
		# nothing is registered with the rendering scenario until the loop has run.
		await process_frame
		await process_frame
		_minimise_window()

		var leaf = node.get("leaf")
		if leaf == null:
			printerr("room capture: the host refused the run")
			quit(1)
			return
		var canvas: Dictionary = leaf.canvas()
		viewport.size = Vector2i(int(float(canvas["width"])), int(float(canvas["height"])))
		node.call("_scale_to_window")

		for step: Variant in (shot[1] as Array):
			var action: Dictionary = step
			if action.has("click"):
				leaf.click_hotspot(String(action["click"]))
			elif action.has("mode"):
				leaf.set_mode(String(action["mode"]))
			elif action.has("hints"):
				leaf.set_hints(bool(action["hints"]))

		var target := (
			out_path.path_join("%s.png" % String(shot[0])) if sheet else out_path
		)
		if not await _write(viewport, leaf, String(shot[0]), target):
			quit(1)
			return
		viewport.queue_free()
		await process_frame
	quit(0)


func _write(viewport: SubViewport, leaf, name: String, target: String) -> bool:
	# One idle frame so the view's node changes reach the rendering server, then a
	# few forced draws so the buffer holds this state rather than the one before.
	await process_frame
	for _i in 4:
		RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	if image == null:
		printerr("room capture: no image came back")
		return false
	DirAccess.make_dir_recursive_absolute(target.get_base_dir())
	var error := image.save_png(target)
	if error != OK:
		printerr("room capture: could not write %s (error %d)" % [target, error])
		return false
	var state: Dictionary = leaf.state()
	print(
		"[room capture] %s  flags %d  fired %d  solved %s  hints %s  %dx%d -> %s"
		% [
			name,
			(state["flags"] as Array).size(),
			(state["fired"] as Array).size(),
			str(bool(state["solved"])),
			str(leaf.hints_visible()),
			image.get_width(),
			image.get_height(),
			target,
		]
	)
	return true


func _shrink_window() -> void:
	if DisplayServer.get_name() == "headless":
		return
	DisplayServer.window_set_size(WINDOW_SIZE)
	DisplayServer.window_set_position(Vector2i(0, 0))
	DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_NO_FOCUS, true)


func _minimise_window() -> void:
	if DisplayServer.get_name() == "headless":
		return
	# Ignored before the first `process_frame`, which is why it happens here.
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_MINIMIZED)


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
