extends Node2D

## The dialogue-scene host: one run and one scenario in, a scene out.
##
##   Godot --path godot/runtime res://hosts/dialogue_scene/main.tscn -- \
##       --run <absolute run directory> --scenario <scenario id>
##
## It opens a run directory, reads the bundle, parses one scenario program and
## draws it. It owns loading, the window, the letterboxing and the refusal card;
## every rule it does not own is under `families/scenario/`, where a headless
## harness compares it against the browser action for action.
##
## **`--scenario` is not optional in practice.** A `dialogue-scene-bundle-v8` run
## publishes the union of every scenario a game holds — The Grain's carries six —
## and a bundle with more than one is refused by name rather than opened on
## whichever came first. The browser's own `/scene/<tag>` route omits it and
## throws on every run that exists.
##
## There is no loop and no `_process`. A scenario has no clock: a transition is a
## keypress, the whole runtime is a reducer over a finite graph, and the view
## redraws when the reducer moves.

var leaf: HostDialogueLeaf = null
## Which scenario to play, when a capture chooses one per shot rather than the
## command line choosing one for the process.
var scenario_override: String = ""

var _root: Control = null


func _ready() -> void:
	var args := HostArgs.parse(OS.get_cmdline_user_args())
	if args.run.is_empty():
		_refuse("dialogue host: pass the run directory after `-- --run <dir>`")
		return
	# A scene run has no `manifest.json` at all: its document is the bundle, and
	# opening it, reading it and refusing it are all the leaf's, which is the one
	# thing that knows this genre.
	var wanted := scenario_override if scenario_override != "" else args.scenario
	var built: Variant = HostDialogueLeaf.open(args.run, wanted)
	if KernelRefusal.is_refusal(built):
		_refuse("dialogue host: %s" % (built as KernelRefusal).line())
		return

	leaf = built
	_root = Control.new()
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_root.add_child(leaf)
	leaf.grab_focus()
	_scale_to_window()
	get_viewport().size_changed.connect(_scale_to_window)


## The design space, scaled whole and centred, so the picture letterboxes rather
## than stretching.
func _scale_to_window() -> void:
	if _root == null or leaf == null:
		return
	var canvas: Dictionary = leaf.canvas()
	var design := Vector2(float(canvas["width"]), float(canvas["height"]))
	var size := Vector2(get_viewport().get_visible_rect().size)
	var factor := minf(size.x / design.x, size.y / design.y)
	_root.scale = Vector2(factor, factor)
	_root.position = Vector2(
		(size.x - design.x * factor) / 2.0, (size.y - design.y * factor) / 2.0
	)


## Say why, on screen, instead of drawing nothing.
func _refuse(line: String) -> void:
	push_error(line)
	var label := Label.new()
	label.add_theme_font_size_override("font_size", 20)
	label.text = line
	label.position = Vector2(40.0, 40.0)
	label.custom_minimum_size = Vector2(1500.0, 0.0)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var layer := CanvasLayer.new()
	layer.add_child(label)
	add_child(layer)
