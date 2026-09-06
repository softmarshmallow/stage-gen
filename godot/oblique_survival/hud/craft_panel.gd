class_name CraftPanel
extends CanvasLayer

## The crafting table as a panel: every recipe as a row with its product's
## icon, its ingredients as have/need chips, and where it is made; the chosen
## row outlined; a Craft button that is live only when the recipe can be made
## here and now; a close button.
##
## The sim owns the table (`SysCraft`): C or Escape toggles it, W/S and Enter
## still work, and this panel speaks to it in the same one-shot inputs — a
## clicked row is `menu_select`, a double-click or the button is
## `menu_confirm`, the close button is `craft_toggle`. Nothing here crafts.

const LAYER := 30
const WIDTH := 640.0
const ICON := 44.0
const CHIP_ICON := 20.0
const ROW_HEIGHT := 64.0
## The list scrolls past this many rows rather than growing past the window.
const MAX_LIST_HEIGHT := 560.0
const DOUBLE_CLICK_SECONDS := 0.35

var kit: UiKit = null

var _root: Control = null
var _panel: PanelContainer = null
var _rows: VBoxContainer = null
var _scroll: ScrollContainer = null
var _craft_button: Button = null
var _hint: RichTextLabel = null
var _signature: String = ""
var _world: Variant = null
var _station_memo: Dictionary = {}
var _last_click_index: int = -1
var _last_click_at: float = -10.0


func setup(pkg, world, _fu) -> void:
	layer = LAYER
	kit = UiKit.new(pkg, world.manifest if world != null else {})
	_root = UiKit.make_root(kit.theme)
	add_child(_root)
	_build()
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


func handle_event(_event: Dictionary) -> void:
	pass


func status() -> Dictionary:
	return {"craft": "open" if visible else "closed"}


func update(world, _delta: float, _cam: Dictionary) -> void:
	if _root == null or world == null:
		return
	_world = world
	var open: bool = bool(world.craft_open) and not bool(world.dead)
	if not open:
		if visible:
			visible = false
		_signature = ""
		return
	visible = true
	_station_memo.clear()
	var recipes: Array = _recipes(world)
	var signature := "%d|%d|" % [int(world.craft_index), recipes.size()]
	for recipe: Dictionary in recipes:
		var state := _recipe_status(world, recipe)
		signature += "%s%s%s;" % [str(recipe.get("recipe_id", "")), state["ok"], state["short"]]
	if signature != _signature:
		_signature = signature
		_write(world, recipes)
	_layout()


# ===========================================================================
# Building
# ===========================================================================

func _build() -> void:
	_panel = UiKit.panel(true, 14.0)
	_panel.custom_minimum_size = Vector2(WIDTH, 0.0)
	_root.add_child(_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	_panel.add_child(box)

	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 10)
	box.add_child(header)
	var title := UiKit.label("Craft", UiKit.TITLE, UiKit.ACCENT)
	title.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	header.add_child(title)
	_hint = UiKit.rich(UiKit.SMALL)
	_hint.text = "[color=#e8e4dc99]click a row · double-click or %s makes · %s / %s choose · %s closes[/color]" % [
		UiKit.kbd("Enter"), UiKit.kbd("W"), UiKit.kbd("S"), UiKit.kbd("C")]
	_hint.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_hint.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	header.add_child(_hint)
	var close := UiKit.button("×", UiKit.TITLE)
	close.pressed.connect(_on_close)
	header.add_child(close)

	_scroll = ScrollContainer.new()
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	_scroll.custom_minimum_size = Vector2(WIDTH - 28.0, 0.0)
	box.add_child(_scroll)
	_rows = VBoxContainer.new()
	_rows.add_theme_constant_override("separation", 2)
	_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.add_child(_rows)

	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 10)
	footer.alignment = BoxContainer.ALIGNMENT_END
	box.add_child(footer)
	var close_button := UiKit.button("Close")
	close_button.pressed.connect(_on_close)
	footer.add_child(close_button)
	_craft_button = UiKit.button("Craft")
	_craft_button.pressed.connect(_on_craft)
	footer.add_child(_craft_button)


func _write(world, recipes: Array) -> void:
	for child in _rows.get_children():
		_rows.remove_child(child)
		child.queue_free()
	var chosen := int(world.craft_index)
	var can_make := false
	for index: int in recipes.size():
		var recipe: Dictionary = recipes[index]
		var state := _recipe_status(world, recipe)
		if index == chosen:
			can_make = bool(state["ok"])
		_rows.add_child(_row(world, recipe, index, index == chosen, state))
	_craft_button.disabled = not can_make
	var list_height := minf(MAX_LIST_HEIGHT, float(recipes.size()) * (ROW_HEIGHT + 2.0))
	_scroll.custom_minimum_size = Vector2(WIDTH - 28.0, list_height)


func _row(world, recipe: Dictionary, index: int, selected: bool, state: Dictionary) -> Control:
	var manifest: Dictionary = world.manifest
	var product: Dictionary = recipe.get("product", {})
	var item_id: Variant = product.get("item_id", null)
	var prop_id: Variant = product.get("prop_id", null)
	var product_id := str(item_id) if item_id != null else str(prop_id)
	var name_text := ""
	if item_id != null:
		var many := int(product.get("count", 1))
		name_text = UiKit.item_name(manifest, product_id) + ((" ×%d" % many) if many > 1 else "")
	else:
		name_text = "%s · build" % UiKit.prop_name(manifest, product_id)

	var frame := CraftRow.new()
	frame.index = index
	frame.selected = selected
	frame.ok = bool(state["ok"])
	frame.custom_minimum_size = Vector2(WIDTH - 40.0, ROW_HEIGHT)
	frame.mouse_filter = Control.MOUSE_FILTER_STOP
	frame.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	frame.gui_input.connect(_on_row_input.bind(index))
	frame.mouse_entered.connect(frame.set_hovered.bind(true))
	frame.mouse_exited.connect(frame.set_hovered.bind(false))
	if not bool(state["ok"]):
		# The row reads at half strength: the recipe is not for now.
		frame.modulate.a = 0.6

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	row.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	row.offset_left = 8.0
	row.offset_right = -8.0
	row.offset_top = 4.0
	row.offset_bottom = -4.0
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	frame.add_child(row)

	var icon: Control
	if item_id != null:
		icon = kit.icon_rect(manifest, product_id, ICON)
	else:
		var rect := TextureRect.new()
		rect.texture = kit.prop_texture(manifest, product_id)
		rect.custom_minimum_size = Vector2(ICON, ICON)
		rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		rect.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		icon = rect
	icon.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(icon)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 3)
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(column)

	var name_label := UiKit.label(name_text, UiKit.FONT_SIZE, UiKit.ACCENT if selected else UiKit.TEXT)
	column.add_child(name_label)

	var chips := HBoxContainer.new()
	chips.add_theme_constant_override("separation", 10)
	chips.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(chips)
	var ingredients: Dictionary = recipe.get("ingredients", {})
	for id: String in ingredients.keys():
		var want := int(ingredients[id])
		var have := UiKit.inv_count(world.slots, id)
		var chip := HBoxContainer.new()
		chip.add_theme_constant_override("separation", 4)
		chip.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var chip_icon := kit.icon_rect(manifest, id, CHIP_ICON)
		chip_icon.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		chip.add_child(chip_icon)
		var short := have < want
		var text := UiKit.label("%s %d/%d" % [UiKit.item_name(manifest, id), have, want],
			UiKit.SMALL, UiKit.SHORT if short else UiKit.MUTED)
		text.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		chip.add_child(text)
		chips.add_child(chip)

	var station_id := str(recipe.get("station", "hand"))
	var station_text := "by hand"
	if station_id != "hand":
		station_text = ("at a lit %s" % station_id.replace("_", " ")).replace("lit workbench", "workbench")
		if not bool(state["station_ok"]):
			station_text += " · none in reach"
	var station := UiKit.label(station_text, UiKit.SMALL,
		UiKit.MUTED if bool(state["station_ok"]) else UiKit.SHORT)
	station.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	station.custom_minimum_size = Vector2(150.0, 0.0)
	station.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(station)
	return frame


func _layout() -> void:
	if _root == null:
		return
	var view: Vector2 = _root.size
	UiKit.fit(_panel)
	_panel.position = Vector2(round((view.x - _panel.size.x) * 0.5), round(maxf(24.0, (view.y - _panel.size.y) * 0.42)))


# ===========================================================================
# Talking to the sim
# ===========================================================================

func _on_row_input(event: InputEvent, index: int) -> void:
	var button := event as InputEventMouseButton
	if button == null or not button.pressed or button.button_index != MOUSE_BUTTON_LEFT:
		return
	if _world == null:
		return
	var now := Time.get_ticks_msec() / 1000.0
	var twice: bool = index == _last_click_index and now - _last_click_at <= DOUBLE_CLICK_SECONDS
	_last_click_index = index
	_last_click_at = now
	_world.input["menu_select"] = index
	if twice or button.double_click:
		_world.input["menu_confirm"] = true
	_root.accept_event()


func _on_craft() -> void:
	if _world != null:
		_world.input["menu_confirm"] = true


func _on_close() -> void:
	if _world != null and bool(_world.craft_open):
		_world.input["craft_toggle"] = true


## The same reading of a recipe the HUD and the sim make.
func _recipe_status(world, recipe: Dictionary) -> Dictionary:
	var short := PackedStringArray()
	for id: String in recipe.get("ingredients", {}).keys():
		var want := int((recipe["ingredients"] as Dictionary)[id])
		var have := UiKit.inv_count(world.slots, id)
		if have < want:
			short.append("%s%d" % [id, want - have])
	var station_id := str(recipe.get("station", "hand"))
	var station_ok := station_id == "hand" or _station_near(world, station_id)
	return {"short": ",".join(short), "station_ok": station_ok, "ok": short.is_empty() and station_ok}


func _station_near(world, station_id: String) -> bool:
	var memo: Variant = _station_memo.get(station_id)
	if memo != null:
		return bool(memo)
	var stations: Dictionary = (world.manifest as Dictionary).get("crafting", {}).get("stations", {})
	var station: Variant = stations.get(station_id, null)
	var answer := false
	if station is Dictionary:
		var block: Dictionary = station
		var want_state: Variant = block.get("state", null)
		var reach := float(block.get("reach_meters", 3.0))
		var wanted_prop := str(block.get("prop_id", ""))
		var px := float(world.player.x)
		var pz := float(world.player.z)
		for entity: Variant in world.entities:
			if not (entity is Dictionary):
				continue
			var e: Dictionary = entity
			if e.get("kind", "") != "prop" or e.get("prop_id", "") != wanted_prop:
				continue
			if want_state != null and e.get("state", "") != want_state:
				continue
			var dx := float(e.get("x", 0.0)) - px
			var dz := float(e.get("z", 0.0)) - pz
			if sqrt(dx * dx + dz * dz) - float(e.get("radius", 0.0)) <= reach:
				answer = true
				break
	_station_memo[station_id] = answer
	return answer


static func _recipes(world) -> Array:
	var crafting: Variant = (world.manifest as Dictionary).get("crafting", null)
	if not (crafting is Dictionary):
		return []
	var recipes: Variant = (crafting as Dictionary).get("recipes", null)
	return recipes if recipes is Array else []


## One recipe's row: the outline when chosen, a lift when hovered (the dimming
## of a recipe that cannot be made here is the frame's modulate).
class CraftRow:
	extends Control

	var index: int = 0
	var selected: bool = false
	var hovered: bool = false
	var ok: bool = true

	func set_hovered(value: bool) -> void:
		hovered = value
		queue_redraw()

	func _draw() -> void:
		var box := StyleBoxFlat.new()
		box.set_corner_radius_all(5)
		if selected:
			box.bg_color = UiKit.ACCENT_DIM
			box.border_color = UiKit.ACCENT
			box.set_border_width_all(1)
		elif hovered:
			box.bg_color = Color(1.0, 1.0, 1.0, 0.05)
		else:
			box.bg_color = Color(0, 0, 0, 0)
		draw_style_box(box, Rect2(Vector2.ZERO, size))
