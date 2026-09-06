class_name DeathScreen
extends CanvasLayer

## The end of a run: a dark sheet over the world, the cause in one line, how
## long the run lasted, and the one button that starts over.
##
## Not the viewer's, which said "Press R" in the message strip and left the
## world running under it. Here the sheet takes the mouse (nothing under it is
## clickable while it is up), the button asks the frame owner for the reset
## through `restart_requested`, and R still works because keys are not taken.

signal restart_requested

## Above the map (31): a player can die with the map open.
const LAYER := 32
const SHEET := Color(0.0, 0.0, 0.0, 0.74)
const PANEL_WIDTH := 520.0
const HEADLINE := 34
## The sheet fades in over this long, so the last frame is seen.
const FADE_SECONDS := 0.6

var kit: UiKit = null
var cause: String = ""

var _root: Control = null
var _sheet: ColorRect = null
var _panel: PanelContainer = null
var _headline: Label = null
var _line: Label = null
var _run_line: Label = null
var _button: Button = null
var _shown_at: float = -1.0
var _fade: float = 0.0
var _world: Variant = null


func setup(pkg, world, _fu) -> void:
	layer = LAYER
	kit = UiKit.new(pkg, world.manifest if world != null else {})
	_root = UiKit.make_root(kit.theme)
	add_child(_root)

	_sheet = ColorRect.new()
	_sheet.name = "sheet"
	_sheet.color = SHEET
	_sheet.mouse_filter = Control.MOUSE_FILTER_STOP
	_sheet.mouse_default_cursor_shape = Control.CURSOR_ARROW
	_root.add_child(_sheet)

	_panel = kit.panel(true, 22.0)
	_panel.custom_minimum_size = Vector2(PANEL_WIDTH, 0.0)
	_root.add_child(_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	_panel.add_child(box)
	_headline = UiKit.label("", HEADLINE, UiKit.ACCENT)
	_headline.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_headline)
	_line = UiKit.label("", UiKit.FONT_SIZE, UiKit.TEXT)
	_line.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_line.custom_minimum_size = Vector2(PANEL_WIDTH - 44.0, 0.0)
	box.add_child(_line)
	_run_line = UiKit.label("", UiKit.SMALL, UiKit.MUTED)
	_run_line.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_run_line)
	box.add_child(UiKit.spacer(10.0))
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_child(row)
	_button = UiKit.button("Begin again", UiKit.TITLE)
	_button.pressed.connect(_on_begin_again)
	row.add_child(_button)
	var hint := UiKit.rich(UiKit.SMALL)
	hint.text = "[color=#e8e4dc99]or %s[/color]" % UiKit.kbd("R")
	hint.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(UiKit.spacer(0.0))
	row.add_child(hint)
	visible = false
	if world != null:
		update(world, 0.0, {})


func set_ui_scale(scale_factor: float) -> void:
	UiKit.apply_scale(self, _root, scale_factor)
	_layout()


func set_mode(_mode: String) -> void:
	pass


func set_look(_look: String) -> void:
	pass


## The sim's death event names the cause; the world's `dead` flag shows the
## screen, so a world that died before this layer saw the event still gets
## a headline.
func handle_event(event: Dictionary) -> void:
	if str(event.get("type", "")) == "death":
		cause = str(event.get("cause", ""))


func status() -> Dictionary:
	return {"death": cause if visible else "-"}


func update(world, delta: float, _cam: Dictionary) -> void:
	if _root == null or world == null:
		return
	_world = world
	var dead: bool = bool(world.dead)
	if not dead:
		if visible:
			visible = false
		_shown_at = -1.0
		_fade = 0.0
		cause = ""
		return
	if not visible:
		visible = true
		_shown_at = float(world.time)
		_fade = 0.0
		_write(world)
	_fade = minf(1.0, _fade + (delta / FADE_SECONDS if delta > 0.0 else 1.0))
	_sheet.color = Color(SHEET.r, SHEET.g, SHEET.b, SHEET.a * _fade)
	_panel.modulate.a = _fade
	_layout()


func _write(world) -> void:
	var manifest: Dictionary = world.manifest
	_headline.text = UiKit.death_headline(cause)
	_line.text = UiKit.death_line(cause)
	var title := str(manifest.get("title", manifest.get("package_id", "")))
	var season: Dictionary = world.season
	var spec: Dictionary = season.get("spec", {})
	var season_text := ""
	if season.get("calendar", null) != null:
		season_text = " · %s" % str(spec.get("display_name", season.get("id", "")))
	_run_line.text = "%s · day %d%s · %s survived" % [
		title, int(world.day), season_text, UiKit.clock_text(float(world.time))]


func _layout() -> void:
	if _root == null:
		return
	var view: Vector2 = _root.size
	_sheet.position = Vector2.ZERO
	_sheet.size = view
	UiKit.fit(_panel)
	_panel.position = ((view - _panel.size) * 0.5).round()


func _on_begin_again() -> void:
	restart_requested.emit()
