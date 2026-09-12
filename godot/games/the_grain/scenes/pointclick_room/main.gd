extends Node2D

## The point-and-click room host: one run in, a game out.
##
##   Godot --path godot/games/the_grain res://scenes/pointclick_room/main.tscn -- \
##       --run <absolute run directory>
##
## It opens a run directory, parses the room manifest, and draws the room. It
## owns loading, the window, the letterboxing and the refusal card; it owns no
## rule the document already states, and every rule it does not own is under
## `genres/pointclick_room/` where a headless harness compares it against the
## browser click for click.
##
## There is no loop here and no `_process`. A room has no clock: a transition is
## a click, the whole game is a reducer over a finite state machine, and the view
## redraws when — and only when — the reducer moves. That is why the picture gate
## for this genre shoots *named states* rather than named frames.
##
## The design space is the authored scene frame plus the HUD band beneath it, and
## the whole canvas is scaled to the window, so a published rectangle lands where
## the producer drew it whatever the display does.
##
## A refusal is shown before anything is drawn. A run of another kind, a schema
## this build does not read, or a package with no interface art is a card with a
## sentence on it rather than a black window.

var leaf: HostRoomLeaf = null

var _root: Control = null


func _ready() -> void:
	var args := GrainOptions.parse(OS.get_cmdline_user_args())
	if args.run.is_empty():
		_refuse("room host: pass the run directory after `-- --run <dir>`")
		return
	var built: Variant = HostRoomLeaf.open(args.run)
	if KernelRefusal.is_refusal(built):
		_refuse("room host: %s" % (built as KernelRefusal).line())
		return

	leaf = built
	_root = Control.new()
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_root.add_child(leaf)
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
	label.custom_minimum_size = Vector2(1200.0, 0.0)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var layer := CanvasLayer.new()
	layer.add_child(label)
	add_child(layer)
