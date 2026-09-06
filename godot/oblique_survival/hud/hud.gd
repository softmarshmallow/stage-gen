class_name Hud
extends CanvasLayer

## The HUD: the viewer's DOM overlay, rebuilt as Control nodes.
##
## Ported from viewer/index.html section 6 (`renderHud` :4705-4765,
## `renderCraft` :4768-4795, the prompt/message/debug block :5723-5771) and the
## CSS at :26-100. Everything here is a pure function of the world: the panels
## are built once in `setup` and their values written in `update`, and — as the
## viewer does with `hudSignature` — the text is only rewritten when a
## signature of it changed.
##
## Colour note: Godot's 2D pipeline is sRGB pass-through (capabilities map
## §2g.4), so the CSS hex values are used verbatim, with no conversion.

# --- the palette, straight from the stylesheet -----------------------------
const PANEL_BG := Color(12.0 / 255.0, 13.0 / 255.0, 16.0 / 255.0, 0.82)
const PANEL_BORDER := Color("#2c2f36")
const TEXT := Color("#e8e4dc")
const ACCENT := Color("#f0c887")
const BAR_BG := Color("#16181d")
const BAR_BORDER := Color("#3a3e46")
const HEALTH := Color("#c4543f")
const HUNGER := Color("#c79a3e")
const WARMTH := Color("#7fb3d5")
const COLD := Color("#9fc5e8")
const WEAR_TRACK := Color("#2c2f36")
const WEAR_FILL := Color("#7fc07a")
const SHORT := Color("#e07a5f")
const MISSING := Color("#e2795f")
const SWATCH := Color("#5a4a3a")
const KBD_BG := "#2b2f38"

const SLOT_BOX := 40.0
const SLOT_ICON := 34.0
const CRAFT_ICON := 36.0
const GLYPH := 14.0
const SLOT_COLUMNS := 6
## `#hud { min-width: 286px }`.
const HUD_MIN_WIDTH := 286.0
const CRAFT_WIDTH := 320.0
## `.bar > i { transition: width .12s linear }` — the fill slides, it does not jump.
const BAR_TRANSITION_SECONDS := 0.12
## `#message` is shown for three seconds after it was said (:5751).
const MESSAGE_SECONDS := 3.0

var package: Variant = null
## Whether this layer answers the backtick key itself. A frame owner that binds
## the debug panel (none does today) should set it false.
var owns_keys: bool = true
var mode: String = "play"
var look: String = ""
var debug_on: bool = false

var _atlas: Texture2D = null
var _atlas_size := Vector2(1.0, 1.0)
## item_id / glyph name -> the cell's window in the sheet, in pixels.
var _item_cells: Dictionary = {}
var _glyph_cells: Dictionary = {}
var _item_sprites: Dictionary = {}

var _font: Font = null
var _root: Control = null
var _hud_panel: PanelContainer = null
var _hud_box: VBoxContainer = null
var _title: RichTextLabel = null
var _health_row: Control = null
var _health_bar: Control = null
var _hunger_row: Control = null
var _hunger_bar: Control = null
var _warmth_row: Control = null
var _warmth_bar: Control = null
var _slot_grid: GridContainer = null
var _selected: RichTextLabel = null
var _torch: Label = null
var _warm: Label = null
var _craft_panel: PanelContainer = null
var _craft_rows: VBoxContainer = null
var _prompt_panel: PanelContainer = null
var _prompt: RichTextLabel = null
var _message: Label = null
var _keys: PanelContainer = null
var _debug_panel: PanelContainer = null
var _debug_grid: GridContainer = null
var _debug_status: Label = null

var _hud_signature: String = ""
var _craft_signature: String = ""
var _prompt_signature: String = ""
var _debug_signature: String = ""
var _slot_cells: Array = []
## station_id -> whether one is in reach, memoised for the length of one
## `update`. `_recipe_status` asks per recipe and `_craft_row` asks again, and
## each ask was a walk over every entity in the world.
var _station_near_memo: Dictionary = {}
## Rows the frame owner adds to the debug panel (each `[name, value]`), so a
## module's own `status()` shows up there without the HUD knowing about it.
var _extra_rows: Array = []


func setup(pkg, world, _fu) -> void:
	package = pkg
	# Above `view/vignette.gd` (layer 20): in the viewer the panels are DOM
	# elements after `#vignette`, so they paint over the night vignette.
	layer = 30
	_read_icons(world)
	_font = _make_font()
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = _make_theme()
	add_child(_root)
	_build_hud_panel()
	_build_craft_panel()
	_build_prompt()
	_build_message()
	_build_keys()
	_build_debug()
	_rebuild_slots(_slot_capacity(world))
	update(world, 0.0, {})


func _unhandled_key_input(event: InputEvent) -> void:
	if not owns_keys:
		return
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo and key.physical_keycode == KEY_QUOTELEFT:
		toggle_debug()


func set_mode(new_mode: String) -> void:
	mode = new_mode


func set_look(new_look: String) -> void:
	look = new_look


## The frame owner offers every sim event to every module; the HUD reads the
## world instead (`world.message` already carries what a death or a break says).
func handle_event(_event: Dictionary) -> void:
	pass


## The debug panel, toggled by the backtick key.
func set_debug(on: bool) -> void:
	debug_on = on
	if _debug_panel != null:
		_debug_panel.visible = on


func toggle_debug() -> void:
	set_debug(not debug_on)


## Extra debug rows from the frame owner: `[[name, value], ...]` or a
## dictionary. Whatever a module's `status()` wants shown.
func set_debug_rows(rows: Variant) -> void:
	var flat: Array = []
	if rows is Dictionary:
		for key: Variant in rows:
			flat.append([str(key), str(rows[key])])
	elif rows is Array:
		for row: Variant in rows:
			if row is Array and (row as Array).size() >= 2:
				flat.append([str(row[0]), str(row[1])])
	_extra_rows = flat


## What this module reports into a debug panel (its own or another's).
func status() -> Dictionary:
	return {"hud": "%d slots, %s" % [_slot_cells.size(), "debug" if debug_on else "play"]}


func update(world, delta: float, _cam: Dictionary) -> void:
	if _root == null or world == null:
		return
	_station_near_memo.clear()
	var manifest: Dictionary = world.manifest
	var rules: Dictionary = manifest.get("gameplay", {})
	var player: Variant = world.player
	var health: float = maxf(0.0, _num(player, "health", 0.0))
	var hunger: float = maxf(0.0, _num(player, "hunger", 0.0))
	var warmth: float = maxf(0.0, _num(player, "warmth", 0.0))
	var health_max: float = _limit(rules, "health")
	var hunger_max: float = _limit(rules, "hunger")
	var warmth_max: float = _limit(rules, "warmth")
	var season: Dictionary = world.season
	var spec: Dictionary = season.get("spec", {})
	var has_calendar: bool = season.get("calendar", null) != null
	var cold: bool = float(spec.get("cold", 0.0)) > 0.0
	var warm_running: bool = float((world.warm as Dictionary).get("remaining", 0.0)) > 0.0

	# --- the pack -----------------------------------------------------------
	var capacity: int = _slot_capacity(world)
	if capacity != _slot_cells.size():
		_rebuild_slots(capacity)

	# --- the signature: the whole panel as one string, as the viewer does ---
	var signature := "%s|%d|%s|%d|%d|%d|%s|%s|%s|%d|%d|%s" % [
		str(manifest.get("title", manifest.get("package_id", ""))),
		int(world.day),
		("%s:%s" % [_season_glyph(world), spec.get("display_name", season.get("id", ""))]) if has_calendar else "",
		int(round(health)), int(round(hunger)), int(round(warmth)),
		"warmth" if (has_calendar or warmth < warmth_max) else "",
		"cold" if (cold and not warm_running) else "",
		_slots_signature(world),
		int(ceil(float((world.torch as Dictionary).get("remaining", 0.0)))),
		int(ceil(float((world.warm as Dictionary).get("remaining", 0.0)))),
		str(world.selected),
	]
	if signature != _hud_signature:
		_hud_signature = signature
		_write_hud_text(world, manifest, season, spec, has_calendar, cold, warm_running,
			health, hunger, warmth)

	# The bars slide rather than jump (`transition: width .12s linear`).
	_bar_target(_health_bar, health / maxf(1.0, health_max), delta)
	_bar_target(_hunger_bar, hunger / maxf(1.0, hunger_max), delta)
	_bar_target(_warmth_bar, warmth / maxf(1.0, warmth_max), delta)
	_warmth_row.visible = has_calendar or warmth < warmth_max
	_warmth_bar.visible = _warmth_row.visible

	_write_craft(world)
	_write_prompt(world)
	_write_message(world)
	_write_debug(world)
	_reflow()


# ===========================================================================
# The left panel
# ===========================================================================

func _write_hud_text(world, manifest: Dictionary, season: Dictionary, spec: Dictionary,
		has_calendar: bool, cold: bool, warm_running: bool,
		health: float, hunger: float, warmth: float) -> void:
	var title := str(manifest.get("title", manifest.get("package_id", "")))
	_title.clear()
	_title.push_font(_font, 12)
	_title.append_text("%s · day %d" % [title, int(world.day)])
	if has_calendar:
		_title.append_text(" · ")
		var glyph := _glyph_texture(_season_glyph(world))
		if glyph != null:
			_title.add_image(glyph, int(GLYPH), int(GLYPH), Color.WHITE, INLINE_ALIGNMENT_CENTER)
			_title.append_text(" ")
		_title.append_text(str(spec.get("display_name", season.get("id", ""))))
	_title.pop_all()

	_row_text(_health_row, "heart", "health", "%d" % int(round(health)), false)
	_row_text(_hunger_row, "bowl", "hunger", "%d" % int(round(hunger)), false)
	_row_text(_warmth_row, "flame", "warmth", "%d" % int(round(warmth)), cold and not warm_running)

	for index: int in _slot_cells.size():
		var cell: Control = _slot_cells[index]
		var slot: Variant = world.slots[index] if index < world.slots.size() else null
		_write_slot(world, cell, slot, index == int(world.selected))

	_selected.clear()
	_selected.push_font(_font, 11)
	_selected.append_text("")
	var selected: Variant = world.slots[int(world.selected)] if int(world.selected) < world.slots.size() else null
	if selected == null:
		_selected.append_text("slot %d · empty" % (int(world.selected) + 1))
	else:
		var slot: Dictionary = selected
		var item_spec: Dictionary = _item_spec(world, str(slot["item"]))
		var use: Variant = item_spec.get("use", null)
		var tool: Variant = item_spec.get("tool", null)
		var hint := ""
		if use is Dictionary:
			var kind := str((use as Dictionary).get("kind", ""))
			match kind:
				"consume":
					hint = " · %s %s" % [
						_kbd("X"), "eat" if float((use as Dictionary).get("hunger", 0.0)) != 0.0 else "apply",
					]
				"light":
					hint = " · %s light" % _kbd("X")
				"carry":
					hint = " · +%d slots while carried" % int((use as Dictionary).get("slots", 0))
				"wear":
					hint = " · %d%% off the cold while carried" % int(
						round(float((use as Dictionary).get("insulation", 0.0)) * 100.0))
				"warm":
					hint = " · %s warm, %d s" % [
						_kbd("X"), int(round(float((use as Dictionary).get("heat_seconds", 0.0)))),
					]
		elif tool is Dictionary:
			hint = " · %ss, %s left" % [str((tool as Dictionary).get("verb", "")), str(slot.get("uses", 0))]
		_selected.append_text("%s%s · %s drop" % [_item_name(world, str(slot["item"])), hint, _kbd("Z")])
	_selected.pop_all()

	var torch_left: float = float((world.torch as Dictionary).get("remaining", 0.0))
	_torch.visible = torch_left > 0.0
	_torch.text = "torch lit · %d s" % int(ceil(torch_left))
	var warm_left: float = float((world.warm as Dictionary).get("remaining", 0.0))
	_warm.visible = warm_left > 0.0
	_warm.text = "stone warm · %d s" % int(ceil(warm_left))


func _row_text(row: Control, glyph: String, label: String, value: String, cold: bool) -> void:
	var text: RichTextLabel = row.get_node("text")
	var amount: Label = row.get_node("value")
	text.clear()
	text.push_font(_font, 11)
	var icon := _glyph_texture(glyph)
	if icon != null:
		text.add_image(icon, int(GLYPH), int(GLYPH), Color.WHITE, INLINE_ALIGNMENT_CENTER)
		text.append_text(" ")
	text.append_text(label)
	if cold:
		text.append_text(" ")
		var flake := _glyph_texture("snowflake")
		if flake != null:
			text.add_image(flake, int(GLYPH), int(GLYPH), COLD, INLINE_ALIGNMENT_CENTER)
			text.append_text(" ")
		text.push_color(COLD)
		text.append_text("cold")
		text.pop()
	text.pop_all()
	amount.text = value


func _write_slot(world, cell: Control, slot: Variant, selected: bool) -> void:
	cell.set("selected", selected)
	cell.queue_redraw()
	var icon: TextureRect = cell.get_node("icon")
	var count: Label = cell.get_node("count")
	var wear: Control = cell.get_node("wear")
	if slot == null:
		icon.texture = null
		icon.visible = false
		count.visible = false
		wear.visible = false
		cell.set("swatch", false)
		return
	var entry: Dictionary = slot
	var item_id := str(entry["item"])
	var texture := _item_texture(world, item_id, SLOT_ICON)
	icon.texture = texture
	icon.visible = texture != null
	cell.set("swatch", texture == null)
	var n := int(entry.get("count", 1))
	count.visible = n > 1
	count.text = str(n)
	var spec: Dictionary = _item_spec(world, item_id)
	var tool: Variant = spec.get("tool", null)
	if tool is Dictionary and entry.get("uses", null) != null:
		var total := maxf(1.0, float((tool as Dictionary).get("uses", 1)))
		wear.visible = true
		wear.set("fraction", clampf(float(entry["uses"]) / total, 0.0, 1.0))
		wear.queue_redraw()
	else:
		wear.visible = false


func _slots_signature(world) -> String:
	var parts := PackedStringArray()
	for index: int in _slot_cells.size():
		var slot: Variant = world.slots[index] if index < world.slots.size() else null
		if slot == null:
			parts.append("-")
			continue
		var entry: Dictionary = slot
		parts.append("%s:%d:%s" % [str(entry["item"]), int(entry.get("count", 1)), str(entry.get("uses", ""))])
	return ",".join(parts)


# ===========================================================================
# The craft panel
# ===========================================================================

func _write_craft(world) -> void:
	var open: bool = bool(world.craft_open)
	_craft_panel.visible = open
	if not open:
		_craft_signature = ""
		return
	var crafting: Dictionary = (world.manifest as Dictionary).get("crafting", {})
	var recipes: Array = crafting.get("recipes", [])
	var signature := "%d|" % int(world.craft_index)
	for recipe: Dictionary in recipes:
		var status := _recipe_status(world, recipe)
		signature += "%s%s%s;" % [str(recipe.get("recipe_id", "")), status["ok"], status["short"]]
	if signature == _craft_signature:
		return
	_craft_signature = signature
	for child in _craft_rows.get_children():
		child.queue_free()
		_craft_rows.remove_child(child)
	for index: int in recipes.size():
		_craft_rows.add_child(_craft_row(world, recipes[index], index == int(world.craft_index)))


func _craft_row(world, recipe: Dictionary, selected: bool) -> Control:
	var status := _recipe_status(world, recipe)
	var product: Dictionary = recipe.get("product", {})
	var item_id: Variant = product.get("item_id", null)
	var prop_id: Variant = product.get("prop_id", null)
	var product_id := str(item_id) if item_id != null else str(prop_id)
	var label := ""
	if item_id != null:
		var many := int(product.get("count", 1))
		label = _item_name(world, product_id) + ((" ×%d" % many) if many > 1 else "")
	else:
		label = "%s · build" % product_id.replace("_", " ")

	var frame := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.content_margin_left = 6.0
	style.content_margin_right = 6.0
	style.content_margin_top = 4.0
	style.content_margin_bottom = 4.0
	style.corner_radius_top_left = 4
	style.corner_radius_top_right = 4
	style.corner_radius_bottom_left = 4
	style.corner_radius_bottom_right = 4
	if selected:
		style.bg_color = Color(240.0 / 255.0, 200.0 / 255.0, 135.0 / 255.0, 0.14)
		style.set_border_width_all(1)
		style.border_color = ACCENT
	else:
		style.bg_color = Color(0, 0, 0, 0)
	frame.add_theme_stylebox_override("panel", style)
	if not bool(status["ok"]):
		frame.modulate.a = 0.55

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	frame.add_child(row)

	var icon := TextureRect.new()
	icon.custom_minimum_size = Vector2(CRAFT_ICON, CRAFT_ICON)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	if item_id != null:
		icon.texture = _item_texture(world, product_id, CRAFT_ICON)
	else:
		icon.texture = _prop_texture(world, product_id)
	row.add_child(icon)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 2)
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(column)

	var name_label := Label.new()
	name_label.text = label
	column.add_child(name_label)

	var need := RichTextLabel.new()
	need.bbcode_enabled = true
	need.fit_content = true
	need.scroll_active = false
	need.autowrap_mode = TextServer.AUTOWRAP_OFF
	need.modulate.a = 0.85
	var parts := PackedStringArray()
	for id: String in recipe.get("ingredients", {}).keys():
		var want := int((recipe["ingredients"] as Dictionary)[id])
		var have := _inv_count(world, id)
		var text := "%s %d/%d" % [_item_name(world, id), have, want]
		parts.append("[color=#e07a5f]%s[/color]" % text if have < want else text)
	need.text = "[font_size=11]%s[/font_size]" % " · ".join(parts)
	column.add_child(need)

	var station_id := str(recipe.get("station", "hand"))
	var station_text := ""
	if station_id == "hand":
		station_text = "by hand"
	else:
		station_text = ("at a lit %s" % station_id.replace("_", " ")).replace("lit workbench", "workbench")
		if not bool(status["station_ok"]):
			station_text += " · none in reach"
	var station := Label.new()
	station.text = station_text
	station.add_theme_font_size_override("font_size", 10)
	if bool(status["station_ok"]):
		station.modulate.a = 0.7
	else:
		station.add_theme_color_override("font_color", SHORT)
	column.add_child(station)
	return frame


## `recipeStatus` (:706-712) plus `stationNear` (:694-704).
func _recipe_status(world, recipe: Dictionary) -> Dictionary:
	var short := PackedStringArray()
	for id: String in recipe.get("ingredients", {}).keys():
		var want := int((recipe["ingredients"] as Dictionary)[id])
		var have := _inv_count(world, id)
		if have < want:
			short.append("%s%d" % [id, want - have])
	var station_id := str(recipe.get("station", "hand"))
	var station_ok := station_id == "hand" or _station_near(world, station_id)
	return {"short": ",".join(short), "station_ok": station_ok,
		"ok": short.is_empty() and station_ok}


func _station_near(world, station_id: String) -> bool:
	var memo: Variant = _station_near_memo.get(station_id)
	if memo != null:
		return bool(memo)
	var answer := _scan_for_station(world, station_id)
	_station_near_memo[station_id] = answer
	return answer


func _scan_for_station(world, station_id: String) -> bool:
	var crafting: Dictionary = (world.manifest as Dictionary).get("crafting", {})
	var stations: Dictionary = crafting.get("stations", {})
	var station: Variant = stations.get(station_id, null)
	if not (station is Dictionary):
		return false
	var block: Dictionary = station
	var want_state: Variant = block.get("state", null)
	var reach := float(block.get("reach_meters", 3.0))
	var wanted_prop := str(block.get("prop_id", ""))
	var player: Variant = world.player
	var px := _num(player, "x", 0.0)
	var pz := _num(player, "z", 0.0)
	for entity: Variant in world.entities:
		if not (entity is Dictionary):
			continue
		var e: Dictionary = entity
		if e.get("kind", "") != "prop":
			continue
		if e.get("prop_id", "") != wanted_prop:
			continue
		if want_state != null and e.get("state", "") != want_state:
			continue
		var dx := float(e.get("x", 0.0)) - px
		var dz := float(e.get("z", 0.0)) - pz
		if sqrt(dx * dx + dz * dz) - float(e.get("radius", 0.0)) <= reach:
			return true
	return false


# ===========================================================================
# Prompt, message, keys, debug
# ===========================================================================

func _write_prompt(world) -> void:
	var target: Variant = world.target
	_prompt_panel.visible = target != null
	if target == null:
		_prompt_signature = ""
		return
	var block: Dictionary = target
	var player: Variant = world.player
	var walking: bool = _field(player, "approach", null) != null
	var reach := float((world.manifest as Dictionary).get("gameplay", {}).get("interact_reach_meters", 0.6))
	var far: bool = not walking and float(block.get("edge", 0.0)) > reach
	var lead := "walking to " if walking else ("walk & " if far else "")
	var entity: Dictionary = block.get("entity", {})
	var text := ""
	if bool(block.get("item", false)):
		var item_name := _item_name(world, str(entity.get("item_id", "")))
		var many := ""
		if bool(block.get("forage", false)) and int(entity.get("count", 1)) > 1:
			many = " ×%d" % int(entity["count"])
		text = "%stake %s%s" % [lead, item_name, many] if walking \
			else "%s%stake %s%s" % [_kbd("Space"), lead, item_name, many]
	else:
		var props: Dictionary = (world.manifest as Dictionary).get("props", {})
		var prop: Dictionary = props.get(str(entity.get("prop_id", "")), {})
		var interaction: Dictionary = block.get("interaction", {})
		var verb := str(interaction.get("verb", ""))
		var key_name := "F" if verb == "light" else "Space"
		var hits := int(block.get("hits", 0))
		if hits == 0:
			hits = int(interaction.get("hits", 1))
		var count := " (%d/%d)" % [int(entity.get("hits", 0)), hits] if hits > 1 else ""
		if block.get("disabled", null) != null:
			text = "%s %s · %s" % [verb, str(prop.get("family", "")), str(block["disabled"])]
		else:
			text = "%s%s%s %s%s" % [
				"" if walking else _kbd(key_name), lead, verb, str(prop.get("family", "")), count,
			]
	if text == _prompt_signature:
		return
	_prompt_signature = text
	_prompt.text = text


func _write_message(world) -> void:
	_message.text = str(world.message)
	var fresh: bool = float(world.time) - float(world.message_at) < MESSAGE_SECONDS
	_message.modulate.a = 1.0 if fresh else 0.0


func _write_debug(world) -> void:
	if not debug_on:
		return
	var rows: Array = []
	rows.append(["run", str((world.manifest as Dictionary).get("run", {}).get("id",
		(world.manifest as Dictionary).get("package_id", "")))])
	rows.append(["mode", mode])
	rows.append(["entities", str((world.entities as Array).size())])
	rows.append(["day phase", "%.2f" % float(world.day_phase)])
	rows.append(["night", "%.2f" % float(world.night)])
	for extra: Array in _extra_rows:
		rows.append(extra)
	rows.append(["player", "%.1f, %.1f" % [_num(world.player, "x", 0.0), _num(world.player, "z", 0.0)]])
	rows.append(["look", world.look if str(world.look) != "" else "summer"])
	var signature := ""
	for row: Array in rows:
		signature += "%s=%s;" % [row[0], row[1]]
	if signature == _debug_signature:
		return
	_debug_signature = signature
	for child in _debug_grid.get_children():
		child.queue_free()
		_debug_grid.remove_child(child)
	for row: Array in rows:
		var name_label := Label.new()
		name_label.text = str(row[0])
		name_label.add_theme_font_size_override("font_size", 11)
		name_label.modulate.a = 0.6
		_debug_grid.add_child(name_label)
		var value := Label.new()
		value.text = str(row[1])
		value.add_theme_font_size_override("font_size", 11)
		value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		_debug_grid.add_child(value)
	_debug_status.text = _status_line(world.manifest)
	_debug_status.visible = _debug_status.text != ""


## `statusLine` (:4797-4801): every `manifest.status.*` that is not "ok".
func _status_line(manifest: Dictionary) -> String:
	var parts := PackedStringArray()
	for key: String in manifest.get("status", {}).keys():
		var value := str((manifest["status"] as Dictionary)[key])
		if value != "ok":
			parts.append("%s=%s" % [key, value])
	if parts.is_empty():
		return ""
	return "incomplete: %s" % " ".join(parts)


# ===========================================================================
# Building the panels
# ===========================================================================

func _build_hud_panel() -> void:
	_hud_panel = _panel()
	_hud_panel.custom_minimum_size = Vector2(HUD_MIN_WIDTH, 0.0)
	_root.add_child(_hud_panel)
	_hud_box = VBoxContainer.new()
	_hud_box.add_theme_constant_override("separation", 0)
	_hud_panel.add_child(_hud_box)

	_title = RichTextLabel.new()
	_title.bbcode_enabled = true
	_title.fit_content = true
	_title.scroll_active = false
	_title.autowrap_mode = TextServer.AUTOWRAP_OFF
	_title.custom_minimum_size = Vector2(HUD_MIN_WIDTH - 20.0, 0.0)
	_hud_box.add_child(_title)
	_hud_box.add_child(_spacer(6))

	_health_row = _bar_row()
	_hud_box.add_child(_health_row)
	_health_bar = _bar(HEALTH)
	_hud_box.add_child(_health_bar)
	_hunger_row = _bar_row()
	_hud_box.add_child(_hunger_row)
	_hunger_bar = _bar(HUNGER)
	_hud_box.add_child(_hunger_bar)
	_warmth_row = _bar_row()
	_hud_box.add_child(_warmth_row)
	_warmth_bar = _bar(WARMTH)
	_hud_box.add_child(_warmth_bar)

	_hud_box.add_child(_spacer(4))
	_slot_grid = GridContainer.new()
	_slot_grid.columns = SLOT_COLUMNS
	_slot_grid.add_theme_constant_override("h_separation", 4)
	_slot_grid.add_theme_constant_override("v_separation", 4)
	_hud_box.add_child(_slot_grid)
	_hud_box.add_child(_spacer(5))

	_selected = RichTextLabel.new()
	_selected.bbcode_enabled = true
	_selected.fit_content = true
	_selected.scroll_active = false
	_selected.autowrap_mode = TextServer.AUTOWRAP_OFF
	_selected.custom_minimum_size = Vector2(HUD_MIN_WIDTH - 20.0, 15.0)
	_selected.modulate.a = 0.85
	_hud_box.add_child(_selected)

	_torch = Label.new()
	_torch.add_theme_font_size_override("font_size", 11)
	_torch.add_theme_color_override("font_color", ACCENT)
	_hud_box.add_child(_torch)
	_warm = Label.new()
	_warm.add_theme_font_size_override("font_size", 11)
	_warm.add_theme_color_override("font_color", ACCENT)
	_hud_box.add_child(_warm)


func _build_craft_panel() -> void:
	_craft_panel = _panel()
	_craft_panel.custom_minimum_size = Vector2(CRAFT_WIDTH, 0.0)
	_craft_panel.visible = false
	_craft_panel.clip_contents = true
	_root.add_child(_craft_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 0)
	_craft_panel.add_child(box)
	var header := RichTextLabel.new()
	header.bbcode_enabled = true
	header.fit_content = true
	header.scroll_active = false
	header.autowrap_mode = TextServer.AUTOWRAP_OFF
	header.custom_minimum_size = Vector2(CRAFT_WIDTH - 20.0, 0.0)
	header.modulate.a = 0.85
	header.text = "[font_size=11]craft · %s/%s choose · %s make · %s close[/font_size]" % [
		_kbd("W"), _kbd("S"), _kbd("Enter"), _kbd("C"),
	]
	box.add_child(header)
	box.add_child(_spacer(6))
	_craft_rows = VBoxContainer.new()
	_craft_rows.add_theme_constant_override("separation", 0)
	box.add_child(_craft_rows)


func _build_prompt() -> void:
	_prompt_panel = _panel()
	_prompt_panel.visible = false
	_root.add_child(_prompt_panel)
	_prompt = RichTextLabel.new()
	_prompt.bbcode_enabled = true
	_prompt.fit_content = true
	_prompt.scroll_active = false
	_prompt.autowrap_mode = TextServer.AUTOWRAP_OFF
	_prompt.custom_minimum_size = Vector2(120.0, 0.0)
	_prompt_panel.add_child(_prompt)


func _build_message() -> void:
	var panel := _panel()
	_root.add_child(panel)
	_message = Label.new()
	panel.add_child(_message)
	_message.modulate.a = 0.0
	panel.set_meta("message_panel", true)
	_message.set_meta("panel", panel)


func _build_keys() -> void:
	_keys = _panel()
	_root.add_child(_keys)
	var text := RichTextLabel.new()
	text.bbcode_enabled = true
	text.fit_content = true
	text.scroll_active = false
	text.autowrap_mode = TextServer.AUTOWRAP_OFF
	text.custom_minimum_size = Vector2(560.0, 0.0)
	text.modulate.a = 0.58
	# The legend at index.html:117-121, verbatim.
	text.text = "[font_size=11][right]WASD move · [b]Q[/b]/[b]E[/b] turn 45° · " \
		+ "[b]Space[/b] interact / take · [b]C[/b] craft · [b]F[/b] light · " \
		+ "[b]1[/b]–[b]0[/b] [b],[/b] [b].[/b] select · [b]X[/b] use · [b]Z[/b] drop · " \
		+ "[b]M[/b] map · [b]R[/b] reset\n" \
		+ "[b]G[/b] gallery · [b]V[/b] verdict · [b]N[/b] night · [b]K[/b] season · " \
		+ "[b]T[/b] weather · [b]L[/b] strike · [b]B[/b] music · [b]`[/b] debug[/right][/font_size]"
	_keys.add_child(text)


func _build_debug() -> void:
	_debug_panel = _panel()
	_debug_panel.custom_minimum_size = Vector2(220.0, 0.0)
	_debug_panel.visible = false
	_root.add_child(_debug_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	_debug_panel.add_child(box)
	_debug_grid = GridContainer.new()
	_debug_grid.columns = 2
	_debug_grid.add_theme_constant_override("h_separation", 10)
	_debug_grid.add_theme_constant_override("v_separation", 1)
	box.add_child(_debug_grid)
	_debug_status = Label.new()
	_debug_status.add_theme_font_size_override("font_size", 11)
	_debug_status.add_theme_color_override("font_color", MISSING)
	_debug_status.visible = false
	box.add_child(_debug_status)
	var hint := Label.new()
	hint.add_theme_font_size_override("font_size", 11)
	hint.modulate.a = 0.55
	hint.text = "1 biomes · 2 weights · 3 mixer · 4 road · 0 off · J stochastic" \
		+ " · K wire · ⇧X prints · [ ] cutoff · - = zoom · I save"
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.custom_minimum_size = Vector2(220.0, 0.0)
	box.add_child(hint)


func _rebuild_slots(capacity: int) -> void:
	for child in _slot_grid.get_children():
		child.queue_free()
		_slot_grid.remove_child(child)
	_slot_cells.clear()
	for _index: int in capacity:
		var cell := SlotCell.new()
		cell.custom_minimum_size = Vector2(SLOT_BOX, SLOT_BOX)
		var icon := TextureRect.new()
		icon.name = "icon"
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
		icon.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		icon.offset_left = 3.0
		icon.offset_top = 3.0
		icon.offset_right = -3.0
		icon.offset_bottom = -3.0
		cell.add_child(icon)
		var count := Label.new()
		count.name = "count"
		count.add_theme_font_size_override("font_size", 10)
		count.add_theme_color_override("font_color", ACCENT)
		count.add_theme_color_override("font_shadow_color", Color.BLACK)
		count.add_theme_constant_override("shadow_outline_size", 3)
		# `.slot > b { right: 3; bottom: 1 }` — anchored to the whole cell and
		# aligned into its corner, because a minimum-size preset would be
		# measured before the label has any text.
		count.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		count.offset_right = -3.0
		count.offset_bottom = -1.0
		count.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		count.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
		cell.add_child(count)
		var wear := WearBar.new()
		wear.name = "wear"
		wear.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
		wear.offset_left = 3.0
		wear.offset_right = -3.0
		wear.offset_top = -5.0
		wear.offset_bottom = -2.0
		cell.add_child(wear)
		_slot_grid.add_child(cell)
		_slot_cells.append(cell)


## Panels float over the frame, so they are placed by hand once their content
## has settled (`#hud` left/top 12, `#craft` left 310, `#keys` right/bottom 12…).
func _reflow() -> void:
	var view: Vector2 = _root.size
	_fit(_hud_panel)
	_hud_panel.position = Vector2(12.0, 12.0)
	_fit(_craft_panel)
	_craft_panel.position = Vector2(310.0, 12.0)
	_fit(_prompt_panel)
	_prompt_panel.position = Vector2(
		round((view.x - _prompt_panel.size.x) * 0.5), view.y - 78.0 - _prompt_panel.size.y)
	var message_panel: Control = _message.get_meta("panel")
	_fit(message_panel)
	message_panel.modulate.a = _message.modulate.a
	message_panel.position = Vector2(round((view.x - message_panel.size.x) * 0.5), 14.0)
	_fit(_keys)
	_keys.position = Vector2(view.x - _keys.size.x - 12.0, view.y - _keys.size.y - 12.0)
	_fit(_debug_panel)
	_debug_panel.position = Vector2(view.x - _debug_panel.size.x - 12.0, 12.0)


func _fit(control: Control) -> void:
	control.size = control.get_combined_minimum_size()


# ===========================================================================
# Icons
# ===========================================================================

func _read_icons(world) -> void:
	var manifest: Dictionary = world.manifest
	var icons: Variant = manifest.get("icons", null)
	if not (icons is Dictionary):
		return
	var block: Dictionary = icons
	var atlas_ref := str(block.get("atlas", ""))
	if atlas_ref == "" or package == null:
		return
	_atlas = package.texture(atlas_ref)
	if _atlas == null:
		return
	_atlas_size = Vector2(float(block.get("width_px", _atlas.get_width())),
		float(block.get("height_px", _atlas.get_height())))
	for cell: Variant in block.get("cells", []):
		if not (cell is Dictionary):
			continue
		var entry: Dictionary = cell
		# Godot does not flip textures: the sheet's top-left pixel window is
		# the atlas region as authored. (The viewer's `1 - (y+h)/height` is a
		# WebGL-only correction and must not be copied.)
		var window := Rect2(float(entry.get("x", 0)), float(entry.get("y", 0)),
			float(entry.get("w", 0)), float(entry.get("h", 0)))
		if entry.has("item_id"):
			_item_cells[str(entry["item_id"])] = window
		elif entry.has("glyph"):
			_glyph_cells[str(entry["glyph"])] = window


func _glyph_texture(glyph: String) -> Texture2D:
	if _atlas == null or not _glyph_cells.has(glyph):
		return null
	var key := "glyph:%s" % glyph
	if _item_sprites.has(key):
		return _item_sprites[key]
	var texture := AtlasTexture.new()
	texture.atlas = _atlas
	texture.region = _glyph_cells[glyph]
	texture.filter_clip = true
	_item_sprites[key] = texture
	return texture


## `iconStyle` (:4673-4685): the sheet's window, then the pickup sprite, then
## nothing (the caller draws the flat swatch).
func _item_texture(world, item_id: String, _box: float) -> Texture2D:
	var key := "item:%s" % item_id
	if _item_sprites.has(key):
		return _item_sprites[key]
	var made: Texture2D = null
	if _atlas != null and _item_cells.has(item_id):
		var texture := AtlasTexture.new()
		texture.atlas = _atlas
		texture.region = _item_cells[item_id]
		texture.filter_clip = true
		made = texture
	else:
		var spec := _item_spec(world, item_id)
		var image_ref := str(spec.get("image", ""))
		if image_ref != "" and package != null:
			made = package.texture(image_ref)
	_item_sprites[key] = made
	return made


## `propIconStyle` (:4698-4702): the prop's baseline-state sprite.
func _prop_texture(world, prop_id: String) -> Texture2D:
	var key := "prop:%s" % prop_id
	if _item_sprites.has(key):
		return _item_sprites[key]
	var made: Texture2D = null
	var props: Dictionary = (world.manifest as Dictionary).get("props", {})
	var prop: Variant = props.get(prop_id, null)
	if prop is Dictionary:
		var states: Dictionary = (prop as Dictionary).get("states", {})
		var state: Variant = states.get(str((prop as Dictionary).get("baseline_state", "")), null)
		if state == null and not states.is_empty():
			state = states[states.keys()[0]]
		if state is Dictionary and package != null:
			made = package.texture(str((state as Dictionary).get("image", "")))
	_item_sprites[key] = made
	return made


# ===========================================================================
# Small read-only helpers
# ===========================================================================
# The sim ships `Inventory.item_name` / `slot_capacity` / `count`, but they are
# typed `world: World`; the HUD keeps its own read-only copies so it can also be
# driven by a stub world in a capture or a test. They read the same fields.

func _item_spec(world, item_id: String) -> Dictionary:
	var items: Dictionary = (world.manifest as Dictionary).get("items", {})
	var spec: Variant = items.get(item_id, null)
	return spec if spec is Dictionary else {}


func _item_name(world, item_id: String) -> String:
	var spec := _item_spec(world, item_id)
	var display := str(spec.get("display_name", ""))
	return display if display != "" else item_id.replace("_", " ")


func _slot_capacity(world) -> int:
	var extra := 0
	for slot: Variant in world.slots:
		if not (slot is Dictionary):
			continue
		var use: Variant = _item_spec(world, str((slot as Dictionary)["item"])).get("use", null)
		if use is Dictionary and str((use as Dictionary).get("kind", "")) == "carry":
			extra += int((use as Dictionary).get("slots", 0)) * int((slot as Dictionary).get("count", 1))
	return int(world.base_slots) + extra


func _inv_count(world, item_id: String) -> int:
	var total := 0
	for slot: Variant in world.slots:
		if slot is Dictionary and str((slot as Dictionary)["item"]) == item_id:
			total += int((slot as Dictionary).get("count", 1))
	return total


func _season_glyph(world) -> String:
	return "moon" if float(world.night) > 0.5 else "sun"


func _limit(rules: Dictionary, key: String) -> float:
	var block: Variant = rules.get(key, null)
	if block is Dictionary:
		var value := float((block as Dictionary).get("max", 0.0))
		if value > 0.0:
			return value
	return 100.0


func _kbd(key: String) -> String:
	return "[bgcolor=%s] %s [/bgcolor]" % [KBD_BG, key]


func _num(object: Variant, key: String, fallback: float) -> float:
	var value: Variant = _field(object, key, fallback)
	return float(value) if (value is float or value is int) else fallback


func _field(object: Variant, key: String, fallback: Variant) -> Variant:
	if object is Dictionary:
		return (object as Dictionary).get(key, fallback)
	if object is Object and key in object:
		return object.get(key)
	return fallback


func _bar_target(bar: Control, fraction: float, delta: float) -> void:
	var wanted := clampf(fraction, 0.0, 1.0)
	var shown := float(bar.get("fraction"))
	if delta <= 0.0 or is_equal_approx(shown, wanted):
		bar.set("fraction", wanted)
	else:
		bar.set("fraction", move_toward(shown, wanted, delta / BAR_TRANSITION_SECONDS))
	bar.queue_redraw()


func _spacer(height: int) -> Control:
	var control := Control.new()
	control.custom_minimum_size = Vector2(0.0, float(height))
	return control


func _bar_row() -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	row.custom_minimum_size = Vector2(HUD_MIN_WIDTH - 20.0, 0.0)
	row.modulate.a = 0.82
	var text := RichTextLabel.new()
	text.name = "text"
	text.bbcode_enabled = true
	text.fit_content = true
	text.scroll_active = false
	text.autowrap_mode = TextServer.AUTOWRAP_OFF
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(text)
	var value := Label.new()
	value.name = "value"
	value.add_theme_font_size_override("font_size", 11)
	value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(value)
	return row


func _bar(fill: Color) -> Control:
	var bar := BarView.new()
	bar.fill = fill
	bar.custom_minimum_size = Vector2(HUD_MIN_WIDTH - 20.0, 9.0)
	return bar


func _panel() -> PanelContainer:
	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = PANEL_BG
	style.border_color = PANEL_BORDER
	style.set_border_width_all(1)
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	style.content_margin_left = 10.0
	style.content_margin_right = 10.0
	style.content_margin_top = 8.0
	style.content_margin_bottom = 8.0
	panel.add_theme_stylebox_override("panel", style)
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return panel


## `font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace`.
func _make_font() -> Font:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["ui-monospace", "SF Mono", "SFMono-Regular", "Menlo",
		"Monaco", "DejaVu Sans Mono", "monospace"])
	return font


func _make_theme() -> Theme:
	var theme := Theme.new()
	theme.default_font = _font
	theme.default_font_size = 13
	theme.set_color("font_color", "Label", TEXT)
	theme.set_color("default_color", "RichTextLabel", TEXT)
	theme.set_constant("line_separation", "RichTextLabel", 2)
	return theme


# ===========================================================================
# The two drawn widgets
# ===========================================================================

## `.bar` — a rounded track with a coloured fill (`width: n%`).
class BarView:
	extends Control

	var fraction: float = 1.0
	var fill: Color = Color.WHITE

	func _draw() -> void:
		var track := StyleBoxFlat.new()
		track.bg_color = Hud.BAR_BG
		track.border_color = Hud.BAR_BORDER
		track.set_border_width_all(1)
		track.corner_radius_top_left = 5
		track.corner_radius_top_right = 5
		track.corner_radius_bottom_left = 5
		track.corner_radius_bottom_right = 5
		draw_style_box(track, Rect2(Vector2.ZERO, size))
		if fraction <= 0.0:
			return
		var inner := StyleBoxFlat.new()
		inner.bg_color = fill
		inner.corner_radius_top_left = 4
		inner.corner_radius_top_right = 4
		inner.corner_radius_bottom_left = 4
		inner.corner_radius_bottom_right = 4
		draw_style_box(inner, Rect2(1.0, 1.0, maxf(2.0, (size.x - 2.0) * fraction), size.y - 2.0))


## `.slot` — the cell behind an item's icon; `.sel` outlines the selected one.
class SlotCell:
	extends Control

	var selected: bool = false
	var swatch: bool = false

	func _draw() -> void:
		var box := StyleBoxFlat.new()
		box.bg_color = Hud.SWATCH if swatch else Hud.BAR_BG
		box.border_color = Hud.ACCENT if selected else Hud.BAR_BORDER
		box.set_border_width_all(2 if selected else 1)
		box.corner_radius_top_left = 4
		box.corner_radius_top_right = 4
		box.corner_radius_bottom_left = 4
		box.corner_radius_bottom_right = 4
		draw_style_box(box, Rect2(Vector2.ZERO, size))


## `.wear` — how much of a tool is left.
class WearBar:
	extends Control

	var fraction: float = 1.0

	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), Hud.WEAR_TRACK)
		draw_rect(Rect2(0.0, 0.0, size.x * clampf(fraction, 0.0, 1.0), size.y), Hud.WEAR_FILL)
