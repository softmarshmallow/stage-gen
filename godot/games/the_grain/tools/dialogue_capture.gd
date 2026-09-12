extends SceneTree

const ScenarioRuntime = preload("res://addons/scenario_runtime/runtime.gd")

## The dialogue scene's gate sheet: six named moments, photographed.
##
##   Godot --path godot/games/the_grain --rendering-driver metal --disable-render-loop \
##       --audio-driver Dummy --quit-after 120000 -s res://tools/dialogue_capture.gd -- \
##       --run <absolute run directory> --out <absolute directory> --shots all
##
## A scenario has no clock either, so a shot is a *moment* rather than a frame:
## the opening, a two-hander, the same two-hander with the other one speaking,
## a line nobody says, a choice, and the end card. The steps below are written
## against `out/the-grain-scene-a`, which is the run the case points at.
##
## Two of the six come from a different scenario of the same bundle, because
## `e1_way_in` has no choice in it. A sheet that only photographed one scenario
## would be a sheet with no choice row on it.
##
## Not headless: a picture needs a real display server. The window is shrunk and
## minimised and the frames come out of an offscreen SubViewport at the scene's
## own 1672x941, and the clear colour is a magenta nothing in any package is
## anywhere near.

const UNPAINTED := Color(1.0, 0.0, 1.0, 1.0)
const WINDOW_SIZE := Vector2i(160, 100)

## Each shot is a name, the scenario it is taken in, and how many times the
## player has pressed on from the opening moment.
const SHOTS := [
	["boot", "e1_way_in", 0],
	["pair", "e1_way_in", 5],
	["swap", "e1_way_in", 6],
	["narration", "e1_way_in", 12],
	["choice", "e1_statements", 39],
	["end", "e1_way_in", 47],
]


func _initialize() -> void:
	var args := _args()
	var out_path := String(args.get("out", ""))
	if out_path.is_empty():
		printerr("dialogue capture: --out is required")
		quit(2)
		return
	var sheet := String(args.get("shots", "")) == "all"
	_shrink_window()

	var scene: PackedScene = load("res://scenes/dialogue_scene/main.tscn")
	if scene == null:
		printerr("dialogue capture: the host scene did not load")
		quit(1)
		return
	RenderingServer.set_default_clear_color(UNPAINTED)

	var wanted: Array = (
		SHOTS
		if sheet
		else [
			[
				String(args.get("shot", "boot")),
				String(args.get("scenario", "")),
				int(args.get("at", "0")),
			]
		]
	)
	for entry: Variant in wanted:
		var shot: Array = entry
		# One host per shot. A scenario walks forward and never back, so a sheet
		# that stepped one instance from moment to moment could photograph them
		# only in order — and the choice comes from another scenario entirely.
		var node: Node = scene.instantiate()
		# The scenario is chosen per shot, so the host's own `--scenario` is
		# overridden here rather than on the command line.
		node.set("scenario_override", String(shot[1]))
		var viewport := SubViewport.new()
		viewport.own_world_3d = true
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		viewport.transparent_bg = false
		viewport.size = Vector2i(
			int(DialogueLayout.STAGE_WIDTH), int(DialogueLayout.STAGE_HEIGHT)
		)
		root.add_child(viewport)
		viewport.add_child(node)
		# Two, not one: `_ready` is deferred to the first main-loop iteration.
		await process_frame
		await process_frame
		_minimise_window()

		var leaf = node.get("leaf")
		if leaf == null:
			printerr("dialogue capture: the host refused %s" % String(shot[1]))
			quit(1)
			return
		node.call("_scale_to_window")
		for _step in int(shot[2]):
			leaf.advance()

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
	await process_frame
	for _i in 4:
		RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	if image == null:
		printerr("dialogue capture: no image came back")
		return false
	DirAccess.make_dir_recursive_absolute(target.get_base_dir())
	var error := image.save_png(target)
	if error != OK:
		printerr("dialogue capture: could not write %s (error %d)" % [target, error])
		return false
	var state: Dictionary = leaf.state()
	var view: Dictionary = leaf.view()
	var staged := PackedStringArray()
	for entry: Variant in (state["actors"] as Array):
		var member: Dictionary = entry
		staged.append("%s@%s" % [String(member["actorId"]), String(member["slot"])])
	print(
		"[dialogue capture] %s  %s  %s  speaker %s  cast [%s]  stage %s  %dx%d -> %s"
		% [
			name,
			String(view.get("kind", "-")),
			ScenarioRuntime.statement_id(String(state["label"]), int(state["index"])),
			str(view.get("speaker")),
			", ".join(staged),
			str(state["stage"]),
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
