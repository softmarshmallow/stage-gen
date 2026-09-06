class_name PauseMenu
extends CanvasLayer

## The pause menu: a dark sheet over the frozen world with Resume, How to
## play, Map, Begin again and Quit, and the how-to-play page behind the second
## button — the key legend the HUD used to print in its top-right corner,
## written out for a reader rather than squeezed into three lines.
##
## Not the viewer's, which had P to stop the loop and no picture of it. The
## frame owner owns `paused`; this layer only shows it (`set_open`) and asks
## for things through `action`: `resume`, `map`, `reset`, `quit`. Escape and
## P are the frame owner's keys; the buttons say the same things.

signal action(name: String)

## Above the map (31) and the death sheet (32): a pause over either still
## reads, and the death sheet closes the menu on its own (`update`).
const LAYER := 33
const SHEET := Color(0.0, 0.0, 0.0, 0.62)
const MENU_WIDTH := 360.0
const HELP_WIDTH := 720.0
const HEADLINE := 28

var kit: UiKit = null
var open: bool = false
## `menu` or `help`.
var page: String = "menu"

var _root: Control = null
var _sheet: ColorRect = null
var _menu: PanelContainer = null
var _help: PanelContainer = null
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
	_build_menu(world)
	_build_help()
	visible = false
	_layout()


func set_ui_scale(scale_factor: float) -> void:
	UiKit.apply_scale(self, _root, scale_factor)
	_layout()


func set_mode(_mode: String) -> void:
	pass


func set_look(_look: String) -> void:
	pass


func handle_event(_event: Dictionary) -> void:
	pass


func status() -> Dictionary:
	return {"pause": (page if open else "closed")}


## Show or hide the menu. Opening always lands on the menu page, never on the
## help the last pause was left at.
func set_open(value: bool) -> void:
	open = value
	visible = value
	if value:
		show_page("menu")
	_layout()


func show_page(name: String) -> void:
	page = "help" if name == "help" else "menu"
	if _menu != null:
		_menu.visible = page == "menu"
	if _help != null:
		_help.visible = page == "help"
	_layout()


func update(world, _delta: float, _cam: Dictionary) -> void:
	if _root == null or world == null:
		return
	_world = world
	# The death sheet is the only thing that closes this from outside: a run
	# that ends while paused is over, and the sheet's button starts the next.
	if open and bool(world.dead):
		action.emit("resume")
	_layout()


# ===========================================================================
# Building
# ===========================================================================

func _build_menu(world) -> void:
	_menu = UiKit.panel(true, 22.0)
	_menu.custom_minimum_size = Vector2(MENU_WIDTH, 0.0)
	_root.add_child(_menu)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	_menu.add_child(box)
	var headline := UiKit.label("Paused", HEADLINE, UiKit.ACCENT)
	headline.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(headline)
	var title := ""
	if world != null:
		var manifest: Dictionary = world.manifest
		title = str(manifest.get("title", manifest.get("package_id", "")))
	var sub := UiKit.label(title, UiKit.SMALL, UiKit.MUTED)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(sub)
	box.add_child(UiKit.spacer(8.0))
	for pair in [
		["Resume", "resume", "Esc"],
		["How to play", "help", ""],
		["Map", "map", "M"],
		["Begin again", "reset", "R"],
		["Quit", "quit", ""],
	]:
		var button := UiKit.button(str(pair[0]), UiKit.FONT_SIZE)
		button.name = str(pair[1])
		button.custom_minimum_size = Vector2(MENU_WIDTH - 44.0, 0.0)
		button.pressed.connect(_on_button.bind(str(pair[1])))
		box.add_child(button)
	var hint := UiKit.rich(UiKit.SMALL)
	hint.text = "[center][color=#e8e4dc99]%s or %s resumes[/color][/center]" % [UiKit.kbd("Esc"), UiKit.kbd("P")]
	box.add_child(hint)


func _build_help() -> void:
	_help = UiKit.panel(true, 22.0)
	_help.custom_minimum_size = Vector2(HELP_WIDTH, 0.0)
	_help.visible = false
	_root.add_child(_help)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	_help.add_child(box)
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 10)
	box.add_child(header)
	var title := UiKit.label("How to play", UiKit.TITLE, UiKit.ACCENT)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	header.add_child(title)
	var back := UiKit.button("Back", UiKit.SMALL)
	back.pressed.connect(show_page.bind("menu"))
	header.add_child(back)
	for section in help_sections():
		var heading := UiKit.label(str(section[0]), UiKit.FONT_SIZE, UiKit.ACCENT)
		box.add_child(heading)
		var text := UiKit.rich(UiKit.SMALL)
		text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		text.custom_minimum_size = Vector2(HELP_WIDTH - 44.0, 0.0)
		text.text = str(section[1])
		box.add_child(text)


## The help, as `[heading, bbcode]` pairs. A test reads this to check the
## keys it names are the ones the frame owner binds.
static func help_sections() -> Array:
	return [
		["The pointer",
			("Click a thing to act on it — take, chop, mine, gather, light — at any distance; "
			+ "beyond reach the walk comes first. Click the ground to walk there, and hold the "
			+ "button to keep following the pointer. Right-click stops. The thing under the "
			+ "pointer lifts and is named above itself; the thing in reach lifts too and says "
			+ "what %s would do to it. Grass, twigs, reeds and berries go straight into the "
			+ "pack; what an axe or a pick knocks loose lands on the ground to be picked up.") % [
				UiKit.kbd("Space")]],
		["The pack",
			("The hotbar along the bottom is the pack: left-click a slot to select it, right-click "
			+ "to use it, and rest on a slot for its card with Use and Drop. The three slots beside "
			+ "it are what is worn — %s, %s, %s: a tool in the hand chops or mines first, a cloak on "
			+ "the body keeps the cold off, a pack on the back carries more. Use a tool, a cloak or a "
			+ "pack to wear it; click the worn thing to take it off.") % [
				UiKit.kbd("hand"), UiKit.kbd("body"), UiKit.kbd("back")]],
		["Keys",
			("%s / arrows move · %s %s turn · %s interact · %s light a fire · %s–%s select · "
			% [UiKit.kbd("WASD"), UiKit.kbd("Q"), UiKit.kbd("E"), UiKit.kbd("Space"), UiKit.kbd("F"),
				UiKit.kbd("1"), UiKit.kbd("0")])
			+ ("%s use or wear · %s drop · %s craft · %s map · %s this menu · %s begin again · %s fullscreen"
			% [UiKit.kbd("X"), UiKit.kbd("Z"), UiKit.kbd("C"), UiKit.kbd("M"), UiKit.kbd("Esc"),
				UiKit.kbd("R"), UiKit.kbd("F11")])],
		["Staying alive",
			"The belly empties; berries and mushrooms grow back, and a lit fire stews them. The cold "
			+ "comes with winter and the night: a fire, a torch, a cloak or a warm stone holds it off. "
			+ "Hounds keep to their ground until you cross it."],
		["Dev keys",
			("%s gallery · %s verdict · %s night · %s season · %s weather · %s strike · %s music · "
			% [UiKit.kbd("G"), UiKit.kbd("V"), UiKit.kbd("N"), UiKit.kbd("K"), UiKit.kbd("T"),
				UiKit.kbd("L"), UiKit.kbd("B")])
			+ ("%s %s zoom · %s pause · %s debug panel" % [
				UiKit.kbd("-"), UiKit.kbd("="), UiKit.kbd("P"), UiKit.kbd("`")])],
	]


func _layout() -> void:
	if _root == null:
		return
	var view: Vector2 = _root.size
	_sheet.position = Vector2.ZERO
	_sheet.size = view
	for panel in [_menu, _help]:
		if panel == null:
			continue
		UiKit.fit(panel)
		panel.position = ((view - panel.size) * 0.5).round()


func _on_button(name: String) -> void:
	if name == "help":
		show_page("help")
		return
	action.emit(name)
