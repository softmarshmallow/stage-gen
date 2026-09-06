class_name Hud
extends CanvasLayer

## The HUD: the vitals, the pack, the prompt, the message strip, the legend
## and the debug panel, as Control nodes.
##
## Ported from viewer/index.html section 6 (`renderHud` :4705-4765, the
## prompt/message/debug block :5723-5771) and then rebuilt for the mouse and
## for a screen: the vitals stand top-left with bars a hand can read, the pack
## is a hotbar along the bottom whose slots are clicked (left selects, right
## uses) with the chosen item's card and its Use and Drop buttons beside it,
## and the thing under the pointer is named at the cursor. The craft table
## and the death sheet are their own layers (`hud/craft_panel.gd`,
## `hud/death_screen.gd`).
##
## Everything is a pure function of the world: the panels are built once in
## `setup` and their values written in `update`, and — as the viewer did with
## `hudSignature` — the text is only rewritten when a signature of it changed.
## The buttons and the slots write one-shot inputs into the world the way the
## keys do; the sim decides what they mean.
##
## Colour note: Godot's 2D pipeline is sRGB pass-through (capabilities map
## §2g.4), so the CSS hex values are used verbatim, with no conversion.

## A panel key the frame owner should act on: `map` (the craft button writes
## the sim's own `craft_toggle` input and needs no owner).
signal action(name: String)

const LAYER := 30
const SLOT_BOX := 56.0
const SLOT_ICON := 46.0
const CARD_ICON := 52.0
const GLYPH := 16.0
const HUD_WIDTH := 320.0
const BAR_HEIGHT := 13.0
const CARD_WIDTH := 300.0
const MARGIN := 14.0
## `.bar > i { transition: width .12s linear }` — the fill slides, it does not jump.
const BAR_TRANSITION_SECONDS := 0.12
## `#message` is shown for three seconds after it was said (:5751).
const MESSAGE_SECONDS := 3.0
## The hotbar's slots run in one row up to here, then wrap.
const HOTBAR_COLUMNS := 12
## Where the cursor tooltip sits, from the pointer.
const TOOLTIP_OFFSET := Vector2(18.0, 22.0)

var package: Variant = null
var kit: UiKit = null
## Whether this layer answers the backtick key itself. A frame owner that binds
## the debug panel (none does today) should set it false.
var owns_keys: bool = true
var mode: String = "play"
var look: String = ""
var debug_on: bool = false
var ui_scale: float = 1.0

var _root: Control = null
var _hud_panel: PanelContainer = null
var _title: RichTextLabel = null
var _health_row: Control = null
var _health_bar: Control = null
var _hunger_row: Control = null
var _hunger_bar: Control = null
var _warmth_row: Control = null
var _warmth_bar: Control = null
var _torch: Label = null
var _warm: Label = null
var _craft_button: Button = null
var _map_button: Button = null

var _hotbar_panel: PanelContainer = null
var _slot_grid: GridContainer = null
var _slot_cells: Array = []
var _card_panel: PanelContainer = null
var _card_icon_holder: Control = null
var _card_name: Label = null
var _card_hint: Label = null
var _use_button: Button = null
var _drop_button: Button = null

var _prompt_panel: PanelContainer = null
var _prompt: RichTextLabel = null
var _message: Label = null
var _message_panel: PanelContainer = null
var _tooltip_panel: PanelContainer = null
var _tooltip: RichTextLabel = null
var _keys: PanelContainer = null
var _debug_panel: PanelContainer = null
var _debug_grid: GridContainer = null
var _debug_status: Label = null

var _hud_signature: String = ""
var _card_signature: String = ""
var _prompt_signature: String = ""
var _tooltip_signature: String = ""
var _debug_signature: String = ""
var _extra_rows: Array = []
var _world: Variant = null
## The frame owner's last pick: `{entity, target, point}`, or empty.
var _hover: Dictionary = {}
var _hover_slot: int = -1
var _mouse: Vector2 = Vector2(-1.0, -1.0)


func setup(pkg, world, _fu) -> void:
	package = pkg
	# Above `view/vignette.gd` (layer 20): in the viewer the panels are DOM
	# elements after `#vignette`, so they paint over the night vignette.
	layer = LAYER
	kit = UiKit.new(pkg, world.manifest if world != null else {})
	_root = UiKit.make_root(kit.theme)
	add_child(_root)
	_build_hud_panel()
	_build_hotbar()
	_build_card()
	_build_prompt()
	_build_message()
	_build_tooltip()
	_build_keys()
	_build_debug()
	if world != null:
		_rebuild_slots(_slot_capacity(world))
		update(world, 0.0, {})


func _unhandled_key_input(event: InputEvent) -> void:
	if not owns_keys:
		return
	var key := event as InputEventKey
	if key != null and key.pressed and not key.echo and key.physical_keycode == KEY_QUOTELEFT:
		toggle_debug()


func set_ui_scale(scale_factor: float) -> void:
	ui_scale = maxf(0.25, scale_factor)
	UiKit.apply_scale(self, _root, ui_scale)
	_reflow()


func set_mode(new_mode: String) -> void:
	mode = new_mode


func set_look(new_look: String) -> void:
	look = new_look


## The frame owner offers every sim event to every module; the HUD reads the
## world instead (`world.message` already carries what a death or a break says).
func handle_event(_event: Dictionary) -> void:
	pass


## What the pointer is over, from the frame owner's pick, and where the
## pointer is (window pixels), for the tip at the cursor.
func set_hover(pick: Dictionary, at: Vector2 = Vector2(-1.0, -1.0)) -> void:
	_hover = pick
	_mouse = at


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
	return {"hud": "%d slots, %s, scale %.2f" % [_slot_cells.size(), "debug" if debug_on else "play", ui_scale]}


func update(world, delta: float, _cam: Dictionary) -> void:
	if _root == null or world == null:
		return
	_world = world
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

	var capacity: int = _slot_capacity(world)
	if capacity != _slot_cells.size():
		_rebuild_slots(capacity)

	var signature := "%s|%d|%s|%d|%d|%d|%s|%s|%s|%d|%d|%d|%d" % [
		str(manifest.get("title", manifest.get("package_id", ""))),
		int(world.day),
		("%s:%s" % [_season_glyph(world), spec.get("display_name", season.get("id", ""))]) if has_calendar else "",
		int(round(health)), int(round(hunger)), int(round(warmth)),
		"warmth" if (has_calendar or warmth < warmth_max) else "",
		"cold" if (cold and not warm_running) else "",
		_slots_signature(world),
		int(ceil(float((world.torch as Dictionary).get("remaining", 0.0)))),
		int(ceil(float((world.warm as Dictionary).get("remaining", 0.0)))),
		int(world.selected), _hover_slot,
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

	var playing: bool = mode == "play" and not bool(world.dead)
	_hotbar_panel.visible = playing
	_card_panel.visible = playing
	_craft_button.disabled = not playing or (manifest.get("crafting", {}) as Dictionary).get("recipes", []).is_empty()
	_write_card(world)
	_write_prompt(world)
	_write_tooltip(world)
	_write_message(world)
	_write_debug(world)
	_reflow()


# ===========================================================================
# The vitals panel
# ===========================================================================

func _write_hud_text(world, manifest: Dictionary, season: Dictionary, spec: Dictionary,
		has_calendar: bool, cold: bool, warm_running: bool,
		health: float, hunger: float, warmth: float) -> void:
	var title := str(manifest.get("title", manifest.get("package_id", "")))
	_title.clear()
	_title.push_bold()
	_title.append_text(title)
	_title.pop()
	_title.append_text(" · day %d" % int(world.day))
	if has_calendar:
		_title.append_text(" · ")
		var glyph := kit.glyph_texture(_season_glyph(world))
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
		_write_slot(world, cell, slot, index == int(world.selected), index == _hover_slot)

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
	var icon := kit.glyph_texture(glyph)
	if icon != null:
		text.add_image(icon, int(GLYPH), int(GLYPH), Color.WHITE, INLINE_ALIGNMENT_CENTER)
		text.append_text(" ")
	text.append_text(label)
	if cold:
		text.append_text(" ")
		var flake := kit.glyph_texture("snowflake")
		if flake != null:
			text.add_image(flake, int(GLYPH), int(GLYPH), UiKit.COLD, INLINE_ALIGNMENT_CENTER)
			text.append_text(" ")
		text.push_color(UiKit.COLD)
		text.append_text("cold")
		text.pop()
	text.pop_all()
	amount.text = value


# ===========================================================================
# The hotbar and the item card
# ===========================================================================

func _write_slot(world, cell: Control, slot: Variant, selected: bool, hovered: bool) -> void:
	cell.set("selected", selected)
	cell.set("hovered", hovered)
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
	var texture := kit.item_texture(world.manifest, item_id)
	icon.texture = texture
	icon.visible = texture != null
	cell.set("swatch", texture == null)
	var n := int(entry.get("count", 1))
	count.visible = n > 1
	count.text = str(n)
	var spec := UiKit.item_spec(world.manifest, item_id)
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


## The chosen slot's card: icon, name, what it does, the two buttons.
func _write_card(world) -> void:
	var index := int(world.selected)
	var selected: Variant = world.slots[index] if index < world.slots.size() else null
	var signature := "%d|" % index
	if selected is Dictionary:
		signature += "%s:%d:%s" % [str(selected["item"]), int(selected.get("count", 1)), str(selected.get("uses", ""))]
	if signature == _card_signature:
		return
	_card_signature = signature
	for child in _card_icon_holder.get_children():
		_card_icon_holder.remove_child(child)
		child.queue_free()
	if selected == null:
		_card_name.text = "slot %d · empty" % (index + 1)
		_card_name.add_theme_color_override("font_color", UiKit.MUTED)
		_card_hint.text = "click a slot, or press its number"
		_use_button.disabled = true
		_use_button.text = "Use"
		_drop_button.disabled = true
		var blank := Control.new()
		blank.custom_minimum_size = Vector2(CARD_ICON, CARD_ICON)
		blank.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_card_icon_holder.add_child(blank)
		return
	var entry: Dictionary = selected
	var item_id := str(entry["item"])
	var spec := UiKit.item_spec(world.manifest, item_id)
	_card_icon_holder.add_child(kit.icon_rect(world.manifest, item_id, CARD_ICON))
	var many := int(entry.get("count", 1))
	_card_name.text = UiKit.item_name(world.manifest, item_id) + ((" ×%d" % many) if many > 1 else "")
	_card_name.add_theme_color_override("font_color", UiKit.TEXT)
	_card_hint.text = UiKit.use_hint(spec, entry)
	var verb := UiKit.use_verb(spec)
	_use_button.disabled = verb == ""
	_use_button.text = (verb.substr(0, 1).to_upper() + verb.substr(1)) if verb != "" else "Use"
	_drop_button.disabled = false


func _on_slot_input(event: InputEvent, index: int) -> void:
	var button := event as InputEventMouseButton
	if button == null or not button.pressed or _world == null:
		return
	if button.button_index == MOUSE_BUTTON_LEFT:
		_world.input["select"] = index
	elif button.button_index == MOUSE_BUTTON_RIGHT:
		# Select and use in one step: the sim's select runs before its use.
		_world.input["select"] = index
		_world.input["use"] = true
	else:
		return
	_root.accept_event()


func _on_slot_hover(index: int, inside: bool) -> void:
	if inside:
		_hover_slot = index
	elif _hover_slot == index:
		_hover_slot = -1


func _on_use() -> void:
	if _world != null:
		_world.input["use"] = true


func _on_drop() -> void:
	if _world != null:
		_world.input["drop"] = true


func _on_craft_button() -> void:
	if _world != null:
		_world.input["craft_toggle"] = true


func _on_map_button() -> void:
	action.emit("map")


# ===========================================================================
# Prompt, tooltip, message, debug
# ===========================================================================

## The nearest thing the key would act on, as the viewer's `#prompt`.
func _write_prompt(world) -> void:
	var target: Variant = world.target
	var show: bool = target != null and mode == "play" and not bool(world.dead) and not bool(world.craft_open)
	_prompt_panel.visible = show
	if not show:
		_prompt_signature = ""
		return
	var text := _describe_target(world, target as Dictionary, true)
	if text == _prompt_signature:
		return
	_prompt_signature = text
	_prompt.text = text


## What a target offers, in words: `walk & chop pine (1/3)`, `take twigs ×2`.
func _describe_target(world, block: Dictionary, with_keys: bool) -> String:
	var player: Variant = world.player
	var walking: bool = _field(player, "approach", null) != null
	var reach := float((world.manifest as Dictionary).get("gameplay", {}).get("interact_reach_meters", 0.6))
	var far: bool = not walking and float(block.get("edge", 0.0)) > reach
	var lead := "walking to " if walking else ("walk & " if far else "")
	var entity: Dictionary = block.get("entity", {})
	if bool(block.get("item", false)):
		var item_name := UiKit.item_name(world.manifest, str(entity.get("item_id", "")))
		var many := ""
		if int(entity.get("count", 1)) > 1:
			many = " ×%d" % int(entity["count"])
		var body := "%stake %s%s" % [lead, item_name, many]
		return body if (walking or not with_keys) else "%s %s" % [UiKit.kbd("Space"), body]
	var props: Dictionary = (world.manifest as Dictionary).get("props", {})
	var prop_id := str(entity.get("prop_id", ""))
	var prop: Dictionary = props.get(prop_id, {})
	var interaction: Dictionary = block.get("interaction", {})
	var verb := str(interaction.get("verb", ""))
	var key_name := "F" if verb == "light" else "Space"
	var hits := int(block.get("hits", 0))
	if hits == 0:
		hits = int(interaction.get("hits", 1))
	var count := " (%d/%d)" % [int(entity.get("hits", 0)), hits] if hits > 1 else ""
	var subject := str(prop.get("family", ""))
	if subject == "":
		subject = prop_id.replace("_", " ")
	if block.get("disabled", null) != null:
		return "%s %s · %s" % [verb, subject, str(block["disabled"])]
	var body := "%s%s %s%s" % [lead, verb, subject, count]
	return body if (walking or not with_keys) else "%s %s" % [UiKit.kbd(key_name), body]


## The thing under the pointer, named at the cursor. A slot's tooltip takes
## precedence, because the pointer is on the panel then.
func _write_tooltip(world) -> void:
	var text := ""
	if _hover_slot >= 0 and _hover_slot < world.slots.size() and _hotbar_panel.visible:
		var slot: Variant = world.slots[_hover_slot]
		if slot is Dictionary:
			var item_id := str((slot as Dictionary)["item"])
			text = "[b]%s[/b] · %s" % [UiKit.item_name(world.manifest, item_id),
				UiKit.use_hint(UiKit.item_spec(world.manifest, item_id), slot)]
			if UiKit.use_verb(UiKit.item_spec(world.manifest, item_id)) != "":
				text += " · right-click to %s" % UiKit.use_verb(UiKit.item_spec(world.manifest, item_id))
	elif mode == "play" and not bool(world.dead) and not bool(world.craft_open):
		var entity: Variant = _hover.get("entity", null)
		var target: Variant = _hover.get("target", null)
		if entity is Dictionary:
			if target is Dictionary:
				text = _describe_target(world, target as Dictionary, false)
			else:
				text = _describe_idle(world, entity as Dictionary)
	_tooltip_panel.visible = text != ""
	if text == _tooltip_signature:
		return
	_tooltip_signature = text
	_tooltip.text = text


## A thing under the pointer that offers nothing right now: its name alone.
func _describe_idle(world, entity: Dictionary) -> String:
	var kind := str(entity.get("kind", ""))
	if kind == "prop":
		var prop: Dictionary = (world.manifest as Dictionary).get("props", {}).get(str(entity.get("prop_id", "")), {})
		var subject := str(prop.get("family", ""))
		if subject == "":
			subject = str(entity.get("prop_id", "")).replace("_", " ")
		var state := str(entity.get("state", ""))
		return "%s · %s" % [subject, state.replace("_", " ")] if state != "" else subject
	if kind == "mob":
		return str(entity.get("actor_id", "")).replace("_", " ")
	if kind == "item" or kind == "forage":
		return UiKit.item_name(world.manifest, str(entity.get("item_id", "")))
	return ""


func _write_message(world) -> void:
	_message.text = str(world.message)
	var fresh: bool = float(world.time) - float(world.message_at) < MESSAGE_SECONDS
	_message.modulate.a = 1.0 if (fresh and not bool(world.dead)) else 0.0


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
	rows.append(["ui scale", "%.2f" % ui_scale])
	var signature := ""
	for row: Array in rows:
		signature += "%s=%s;" % [row[0], row[1]]
	if signature == _debug_signature:
		return
	_debug_signature = signature
	for child in _debug_grid.get_children():
		_debug_grid.remove_child(child)
		child.queue_free()
	for row: Array in rows:
		var name_label := UiKit.label(str(row[0]), UiKit.SMALL, UiKit.MUTED)
		_debug_grid.add_child(name_label)
		var value := UiKit.label(str(row[1]), UiKit.SMALL)
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
	_hud_panel = UiKit.panel(false, 12.0)
	_hud_panel.custom_minimum_size = Vector2(HUD_WIDTH, 0.0)
	_root.add_child(_hud_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hud_panel.add_child(box)

	_title = UiKit.rich(UiKit.TITLE, HUD_WIDTH - 24.0)
	box.add_child(_title)
	box.add_child(UiKit.spacer(6.0))

	_health_row = _bar_row()
	box.add_child(_health_row)
	_health_bar = _bar(UiKit.HEALTH)
	box.add_child(_health_bar)
	_hunger_row = _bar_row()
	box.add_child(_hunger_row)
	_hunger_bar = _bar(UiKit.HUNGER)
	box.add_child(_hunger_bar)
	_warmth_row = _bar_row()
	box.add_child(_warmth_row)
	_warmth_bar = _bar(UiKit.WARMTH)
	box.add_child(_warmth_bar)

	_torch = UiKit.label("", UiKit.SMALL, UiKit.ACCENT)
	box.add_child(_torch)
	_warm = UiKit.label("", UiKit.SMALL, UiKit.ACCENT)
	box.add_child(_warm)
	box.add_child(UiKit.spacer(8.0))

	# The two panel buttons take the mouse even though the panel does not.
	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 8)
	buttons.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(buttons)
	_craft_button = UiKit.button("Craft  C", UiKit.SMALL)
	_craft_button.pressed.connect(_on_craft_button)
	buttons.add_child(_craft_button)
	_map_button = UiKit.button("Map  M", UiKit.SMALL)
	_map_button.pressed.connect(_on_map_button)
	buttons.add_child(_map_button)


func _build_hotbar() -> void:
	_hotbar_panel = UiKit.panel(true, 8.0)
	_root.add_child(_hotbar_panel)
	_slot_grid = GridContainer.new()
	_slot_grid.columns = HOTBAR_COLUMNS
	_slot_grid.add_theme_constant_override("h_separation", 5)
	_slot_grid.add_theme_constant_override("v_separation", 5)
	_hotbar_panel.add_child(_slot_grid)


func _build_card() -> void:
	_card_panel = UiKit.panel(true, 10.0)
	_card_panel.custom_minimum_size = Vector2(CARD_WIDTH, 0.0)
	_root.add_child(_card_panel)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	_card_panel.add_child(row)
	_card_icon_holder = Control.new()
	_card_icon_holder.custom_minimum_size = Vector2(CARD_ICON, CARD_ICON)
	_card_icon_holder.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_card_icon_holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(_card_icon_holder)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 4)
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(column)
	_card_name = UiKit.label("", UiKit.FONT_SIZE)
	column.add_child(_card_name)
	_card_hint = UiKit.label("", UiKit.SMALL, UiKit.MUTED)
	_card_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_card_hint.custom_minimum_size = Vector2(CARD_WIDTH - CARD_ICON - 40.0, 0.0)
	column.add_child(_card_hint)
	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 8)
	column.add_child(buttons)
	_use_button = UiKit.button("Use", UiKit.SMALL)
	_use_button.pressed.connect(_on_use)
	buttons.add_child(_use_button)
	_drop_button = UiKit.button("Drop", UiKit.SMALL)
	_drop_button.pressed.connect(_on_drop)
	buttons.add_child(_drop_button)
	var hint := UiKit.rich(UiKit.SMALL)
	hint.text = "[color=#e8e4dc80]%s %s[/color]" % [UiKit.kbd("X"), UiKit.kbd("Z")]
	hint.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	buttons.add_child(hint)


func _build_prompt() -> void:
	_prompt_panel = UiKit.panel(false, 12.0)
	_prompt_panel.visible = false
	_root.add_child(_prompt_panel)
	_prompt = UiKit.rich(UiKit.FONT_SIZE, 120.0)
	_prompt_panel.add_child(_prompt)


func _build_message() -> void:
	_message_panel = UiKit.panel(false, 12.0)
	_root.add_child(_message_panel)
	_message = UiKit.label("", UiKit.FONT_SIZE)
	_message_panel.add_child(_message)
	_message.modulate.a = 0.0


func _build_tooltip() -> void:
	_tooltip_panel = UiKit.panel(false, 8.0)
	_tooltip_panel.visible = false
	_root.add_child(_tooltip_panel)
	_tooltip = UiKit.rich(UiKit.SMALL)
	_tooltip_panel.add_child(_tooltip)


func _build_keys() -> void:
	_keys = UiKit.panel(false, 10.0)
	_root.add_child(_keys)
	var text := UiKit.rich(UiKit.SMALL, 560.0)
	text.modulate.a = 0.62
	text.text = "[right]click a thing to act on it · click the ground to walk · right-click stops\n" \
		+ "WASD move · [b]Q[/b]/[b]E[/b] turn · [b]Space[/b] interact · [b]F[/b] light · " \
		+ "[b]1[/b]–[b]0[/b] select · [b]X[/b] use · [b]Z[/b] drop · [b]C[/b] craft · [b]M[/b] map · [b]R[/b] reset\n" \
		+ "[b]G[/b] gallery · [b]V[/b] verdict · [b]N[/b] night · [b]K[/b] season · " \
		+ "[b]T[/b] weather · [b]L[/b] strike · [b]B[/b] music · [b]F11[/b] fullscreen · [b]`[/b] debug[/right]"
	_keys.add_child(text)


func _build_debug() -> void:
	_debug_panel = UiKit.panel(false, 10.0)
	_debug_panel.custom_minimum_size = Vector2(240.0, 0.0)
	_debug_panel.visible = false
	_root.add_child(_debug_panel)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 1)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_debug_panel.add_child(box)
	_debug_grid = GridContainer.new()
	_debug_grid.columns = 2
	_debug_grid.add_theme_constant_override("h_separation", 10)
	_debug_grid.add_theme_constant_override("v_separation", 1)
	_debug_grid.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(_debug_grid)
	_debug_status = UiKit.label("", UiKit.SMALL, UiKit.MISSING)
	_debug_status.visible = false
	box.add_child(_debug_status)
	var hint := UiKit.label("1 biomes · 2 weights · 3 mixer · 4 road · 0 off · J stochastic" \
		+ " · K wire · ⇧X prints · [ ] cutoff · - = zoom · I save", UiKit.SMALL, UiKit.MUTED)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.custom_minimum_size = Vector2(240.0, 0.0)
	box.add_child(hint)


func _rebuild_slots(capacity: int) -> void:
	for child in _slot_grid.get_children():
		_slot_grid.remove_child(child)
		child.queue_free()
	_slot_cells.clear()
	_hover_slot = -1
	for index: int in capacity:
		var cell := SlotCell.new()
		cell.custom_minimum_size = Vector2(SLOT_BOX, SLOT_BOX)
		cell.mouse_filter = Control.MOUSE_FILTER_STOP
		cell.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		cell.gui_input.connect(_on_slot_input.bind(index))
		cell.mouse_entered.connect(_on_slot_hover.bind(index, true))
		cell.mouse_exited.connect(_on_slot_hover.bind(index, false))
		var icon := TextureRect.new()
		icon.name = "icon"
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
		icon.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		icon.offset_left = 5.0
		icon.offset_top = 5.0
		icon.offset_right = -5.0
		icon.offset_bottom = -5.0
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cell.add_child(icon)
		# The key that selects this slot, in the corner: 1-9, then 0.
		if index < 10:
			var key := UiKit.label(str((index + 1) % 10), 11, UiKit.MUTED)
			key.name = "key"
			key.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
			key.offset_left = 4.0
			key.offset_top = 1.0
			key.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
			key.vertical_alignment = VERTICAL_ALIGNMENT_TOP
			cell.add_child(key)
		var count := UiKit.label("", UiKit.SMALL, UiKit.ACCENT)
		count.name = "count"
		count.add_theme_color_override("font_shadow_color", Color.BLACK)
		count.add_theme_constant_override("shadow_outline_size", 4)
		count.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		count.offset_right = -4.0
		count.offset_bottom = -2.0
		count.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		count.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
		cell.add_child(count)
		var wear := WearBar.new()
		wear.name = "wear"
		wear.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
		wear.offset_left = 5.0
		wear.offset_right = -5.0
		wear.offset_top = -7.0
		wear.offset_bottom = -3.0
		wear.mouse_filter = Control.MOUSE_FILTER_IGNORE
		cell.add_child(wear)
		_slot_grid.add_child(cell)
		_slot_cells.append(cell)
	_hud_signature = ""


## Panels float over the frame, so they are placed by hand once their content
## has settled: vitals top-left, hotbar and card bottom-centre, prompt above
## them, message top-centre, legend and debug top-right, tooltip at the cursor.
func _reflow() -> void:
	var view: Vector2 = _root.size
	UiKit.fit(_hud_panel)
	_hud_panel.position = Vector2(MARGIN, MARGIN)

	UiKit.fit(_hotbar_panel)
	UiKit.fit(_card_panel)
	var gap := 10.0
	var strip := _hotbar_panel.size.x + gap + _card_panel.size.x
	var left := roundf((view.x - strip) * 0.5)
	var bottom := view.y - MARGIN
	_hotbar_panel.position = Vector2(left, round(bottom - _hotbar_panel.size.y))
	_card_panel.position = Vector2(left + _hotbar_panel.size.x + gap, round(bottom - _card_panel.size.y))

	UiKit.fit(_prompt_panel)
	var above := minf(_hotbar_panel.position.y, _card_panel.position.y) if _hotbar_panel.visible else view.y - 78.0
	_prompt_panel.position = Vector2(round((view.x - _prompt_panel.size.x) * 0.5), round(above - 12.0 - _prompt_panel.size.y))

	UiKit.fit(_keys)
	_keys.position = Vector2(view.x - _keys.size.x - MARGIN, MARGIN)
	# Under the legend's row, so a long line in the legend never crosses it.
	UiKit.fit(_message_panel)
	_message_panel.modulate.a = _message.modulate.a
	_message_panel.position = Vector2(round((view.x - _message_panel.size.x) * 0.5), _keys.position.y + _keys.size.y + 10.0)
	UiKit.fit(_debug_panel)
	_debug_panel.position = Vector2(view.x - _debug_panel.size.x - MARGIN, _keys.position.y + _keys.size.y + 8.0)

	if _tooltip_panel.visible:
		UiKit.fit(_tooltip_panel)
		var at := _mouse / ui_scale + TOOLTIP_OFFSET
		if _hover_slot >= 0 and _hover_slot < _slot_cells.size():
			# Over the hotbar the tip stands above the slot, not under the hand.
			var cell: Control = _slot_cells[_hover_slot]
			var cell_at := _hotbar_panel.position + _slot_grid.position + cell.position
			at = Vector2(cell_at.x, cell_at.y - _tooltip_panel.size.y - 8.0)
		at.x = clampf(at.x, MARGIN, maxf(MARGIN, view.x - _tooltip_panel.size.x - MARGIN))
		at.y = clampf(at.y, MARGIN, maxf(MARGIN, view.y - _tooltip_panel.size.y - MARGIN))
		_tooltip_panel.position = at.round()


# ===========================================================================
# Small read-only helpers
# ===========================================================================

func _slot_capacity(world) -> int:
	return UiKit.slot_capacity(world.manifest, world.slots, int(world.base_slots))


func _season_glyph(world) -> String:
	return "moon" if float(world.night) > 0.5 else "sun"


func _limit(rules: Dictionary, key: String) -> float:
	var block: Variant = rules.get(key, null)
	if block is Dictionary:
		var value := float((block as Dictionary).get("max", 0.0))
		if value > 0.0:
			return value
	return 100.0


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


func _bar_row() -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	row.custom_minimum_size = Vector2(HUD_WIDTH - 24.0, 0.0)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var text := UiKit.rich(UiKit.FONT_SIZE)
	text.name = "text"
	text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(text)
	var value := UiKit.label("", UiKit.FONT_SIZE)
	value.name = "value"
	value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(value)
	return row


func _bar(fill: Color) -> Control:
	var bar := BarView.new()
	bar.fill = fill
	bar.custom_minimum_size = Vector2(HUD_WIDTH - 24.0, BAR_HEIGHT)
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return bar


# ===========================================================================
# The drawn widgets
# ===========================================================================

## `.bar` — a rounded track with a coloured fill (`width: n%`).
class BarView:
	extends Control

	var fraction: float = 1.0
	var fill: Color = Color.WHITE

	func _draw() -> void:
		var track := StyleBoxFlat.new()
		track.bg_color = UiKit.BAR_BG
		track.border_color = UiKit.BAR_BORDER
		track.set_border_width_all(1)
		track.set_corner_radius_all(6)
		draw_style_box(track, Rect2(Vector2.ZERO, size))
		if fraction <= 0.0:
			return
		var inner := StyleBoxFlat.new()
		inner.bg_color = fill
		inner.set_corner_radius_all(5)
		draw_style_box(inner, Rect2(1.0, 1.0, maxf(2.0, (size.x - 2.0) * fraction), size.y - 2.0))


## `.slot` — the cell behind an item's icon; `.sel` outlines the selected one,
## and the hovered one lifts.
class SlotCell:
	extends Control

	var selected: bool = false
	var hovered: bool = false
	var swatch: bool = false

	func _draw() -> void:
		var box := StyleBoxFlat.new()
		box.bg_color = UiKit.SWATCH if swatch else (Color("#1f2229") if hovered else UiKit.BAR_BG)
		box.border_color = UiKit.ACCENT if selected else (UiKit.MUTED if hovered else UiKit.BAR_BORDER)
		box.set_border_width_all(2 if selected else 1)
		box.set_corner_radius_all(5)
		draw_style_box(box, Rect2(Vector2.ZERO, size))


## `.wear` — how much of a tool is left.
class WearBar:
	extends Control

	var fraction: float = 1.0

	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), UiKit.WEAR_TRACK)
		draw_rect(Rect2(0.0, 0.0, size.x * clampf(fraction, 0.0, 1.0), size.y), UiKit.WEAR_FILL)
