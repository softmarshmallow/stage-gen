extends SceneTree

## The case's gate sheet: five named states of the container, photographed.
##
##   Godot --path godot/legacy/runtime --rendering-driver metal --disable-render-loop \
##       --audio-driver Dummy --quit-after 200000 -s res://tools/case_capture.gd -- \
##       --run <absolute case run directory> --out <absolute directory> --shots all
##
## What a case draws that its leaves do not: the bar naming where you are, the
## Continue a finished beat offers, the backlog, and the card that closes it. The
## steps below are written against `out/the-grain-episode-one`, whose eight beats
## are six scenarios of `the-grain-scene-a` and two rooms.
##
## A case walks forward and never back, so each shot opens on its own beat rather
## than playing to it — the same reason the platformer's shot opens on a named
## map. `open_on` is the host's own affordance for that and does exactly what
## entering the beat does, minus the walk.

const UNPAINTED := Color(1.0, 0.0, 1.0, 1.0)
const WINDOW_SIZE := Vector2i(160, 100)
const CANVAS := Vector2i(1672, 1024)

## Each shot is a name, the beat it opens on, what to do there, and whether the
## backlog is pulled down over it.
##
## `steps` is a number of moments to press through; `clicks` are a room's
## hotspots, in order; `finish` answers a beat that has reported its outcome.
## `seed` plays a throwaway host first so that the real one finds a save
## waiting, which is the only way to photograph the offer to continue.
const SHOTS := [
	["boot", "b_office", {}],
	["room", "b_motor_court", {}],
	["backlog", "b_office", {"steps": 8, "backlog": true}],
	["crossing", "b_motor_court", {"clicks": ["service_bell"]}],
	["continue", "", {"seed": 6, "seed_beat": "b_office"}],
	["finished", "b_statements", {"steps": 400, "finish": true}],
]


func _initialize() -> void:
	var args := _args()
	var out_path := String(args.get("out", ""))
	if out_path.is_empty():
		printerr("case capture: --out is required")
		quit(2)
		return
	var sheet := String(args.get("shots", "")) == "all"
	_shrink_window()

	var scene: PackedScene = load("res://hosts/case/main.tscn")
	if scene == null:
		printerr("case capture: the host scene did not load")
		quit(1)
		return
	RenderingServer.set_default_clear_color(UNPAINTED)

	var wanted: Array = (
		SHOTS if sheet else [[String(args.get("shot", "boot")), String(args.get("beat", "")), {}]]
	)
	var tag := String(args.get("run", "")).get_file()
	for entry: Variant in wanted:
		var shot: Array = entry
		var plan: Dictionary = shot[2]
		# Every shot opens on a clean store, so the sheet says the same thing
		# however many times it is taken and whatever was played here before.
		CaseStore.clear(tag)
		if int(plan.get("seed", 0)) > 0:
			var seeded: Node = scene.instantiate()
			var throwaway := SubViewport.new()
			throwaway.own_world_3d = true
			throwaway.size = CANVAS
			root.add_child(throwaway)
			throwaway.add_child(seeded)
			await process_frame
			await process_frame
			seeded.call("open_on", String(plan.get("seed_beat", "")))
			_play(seeded, {"steps": int(plan["seed"])})
			throwaway.queue_free()
			await process_frame
		var node: Node = scene.instantiate()
		var viewport := SubViewport.new()
		viewport.own_world_3d = true
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		viewport.transparent_bg = false
		viewport.size = CANVAS
		root.add_child(viewport)
		viewport.add_child(node)
		await process_frame
		await process_frame
		_minimise_window()

		# `get` on a host whose script did not load answers `null`, and calling a
		# method on that is a second error rather than a message — which is how a
		# capture ends up burning its whole `--quit-after` budget instead of
		# saying what went wrong.
		var opened: Variant = node.get("document")
		if not (opened is Dictionary) or (opened as Dictionary).is_empty():
			printerr("case capture: the host refused the run")
			quit(1)
			return
		node.call("_scale_to_window")
		if String(shot[1]) != "":
			node.call("open_on", String(shot[1]))
		_play(node, plan)

		var target := out_path.path_join("%s.png" % String(shot[0])) if sheet else out_path
		if not await _write(viewport, node, String(shot[0]), target):
			quit(1)
			return
		viewport.queue_free()
		await process_frame
	quit(0)


## Press through a beat the way a player would: a choice is answered with its
## first option, anything else is a step forward.
func _play(node: Node, plan: Dictionary) -> void:
	var leaf = node.get("leaf")
	for hotspot: Variant in (plan.get("clicks", []) as Array):
		if leaf != null and leaf.has_method("click_hotspot"):
			leaf.call("click_hotspot", String(hotspot))
	for _step in int(plan.get("steps", 0)):
		leaf = node.get("leaf")
		if leaf == null or not leaf.has_method("view"):
			break
		var view: Dictionary = leaf.call("view")
		if String(view.get("kind", "")) == "choice":
			leaf.call("choose", 0)
		elif String(view.get("kind", "")) == "end":
			break
		else:
			leaf.call("advance")
	if bool(plan.get("finish", false)):
		leaf = node.get("leaf")
		if leaf != null and leaf.has_method("advance"):
			leaf.call("advance")
	if bool(plan.get("backlog", false)):
		node.call("toggle_backlog")


func _write(viewport: SubViewport, node: Node, name: String, target: String) -> bool:
	await process_frame
	for _i in 4:
		RenderingServer.force_draw(false)
	var image := viewport.get_texture().get_image()
	if image == null:
		printerr("case capture: no image came back")
		return false
	DirAccess.make_dir_recursive_absolute(target.get_base_dir())
	var error := image.save_png(target)
	if error != OK:
		printerr("case capture: could not write %s (error %d)" % [target, error])
		return false
	var state: Dictionary = node.get("state")
	var progress: Dictionary = state["progress"]
	print(
		"[case capture] %s  phase %s  beat %s  facts %d  backlog %d  pending %s  %dx%d -> %s"
		% [
			name,
			String(state["phase"]),
			String(progress["beatId"]),
			(progress["facts"] as PackedStringArray).size(),
			(state["backlog"] as Array).size(),
			"yes" if state["pending"] != null else "no",
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
