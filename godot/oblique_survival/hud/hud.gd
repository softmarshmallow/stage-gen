class_name Hud
extends CanvasLayer

## The HUD: the vitals, the pack and what is worn, the prompt, the message
## strip, the hovered thing's name and the debug panel, as Control nodes.
##
## Ported from viewer/index.html section 6 (`renderHud` :4705-4765, the
## prompt/message/debug block :5723-5771) and then rebuilt for the mouse and
## for a screen: the vitals stand top-left with bars a hand can read; the pack
## is a hotbar along the bottom whose slots are clicked (left selects, right
## uses), with the three worn places — hand, body, back — beside it and a
## button cluster (Craft, Map, Menu) at its end; resting on any slot raises
## that slot's card (icon, name, what it does, its buttons) above it; the thing
## under the pointer is named above itself in the world, not at the cursor;
## and a thing picked up flies from where it stood into the slot that took it.
## The crafting table, the death sheet and the pause menu are their own layers
## (`hud/craft_panel.gd`, `hud/death_screen.gd`, `hud/pause_menu.gd`).
##
## Everything is a pure function of the world: the panels are built once in
## `setup` and their values written in `update`, and — as the viewer did with
## `hudSignature` — the text is only rewritten when a signature of it changed.
## The buttons and the slots write one-shot inputs into the world the way the
## keys do; the sim decides what they mean.
##
## Colour note: Godot's 2D pipeline is sRGB pass-through (capabilities map
## §2g.4), so the CSS hex values are used verbatim, with no conversion.

## A panel key the frame owner should act on: `map`, `menu` (the craft button
## writes the sim's own `craft_toggle` input and needs no owner).
signal action(name: String)

const LAYER := 30
const SLOT_BOX := 56.0
const SLOT_ICON := 46.0
const CARD_ICON := 52.0
const GLYPH := 16.0
const HUD_WIDTH := 320.0
const BAR_HEIGHT := 13.0
## The day drawn as a strip under the clock: light, dusk, night, dawn, and a
## tick where the hour stands.
const DAY_STRIP_HEIGHT := 7.0
## Phase 0 is sunrise, so the hour reads 06:00 there and midnight at 0.75.
const SUNRISE_HOUR := 6.0
const CARD_WIDTH := 300.0
const MARGIN := 14.0
## `.bar > i { transition: width .12s linear }` — the fill slides, it does not jump.
const BAR_TRANSITION_SECONDS := 0.12
## `#message` is shown for three seconds after it was said (:5751).
const MESSAGE_SECONDS := 3.0
## The hotbar's slots run in one row up to here, then wrap.
const HOTBAR_COLUMNS := 12
## The hovered slot's card stays this long after the pointer leaves the slot
## and the card both, so a hand can cross the gap to its buttons.
const CARD_LINGER_SECONDS := 0.25
## A picked-up item's flight into its slot: how long, how high the arc bows,
## how big the flying icon starts and ends, and how long the slot glows after.
const FLIGHT_SECONDS := 0.5
const FLIGHT_ARC := 110.0
const FLIGHT_ICON := 40.0
const FLIGHT_END_SCALE := 0.65
const FLASH_SECONDS := 0.45
## The label stands this far above the thing's anchor.
const LABEL_LIFT := 8.0

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
## The clock under the title: the hour, and how long until dusk or dawn.
var _clock_row: Control = null
var _day_strip: DayStripView = null
var _health_row: Control = null
var _health_bar: Control = null
var _hunger_row: Control = null
var _hunger_bar: Control = null
var _warmth_row: Control = null
var _warmth_bar: Control = null
var _torch: Label = null
var _warm: Label = null

var _hotbar_panel: PanelContainer = null
var _slot_grid: GridContainer = null
var _slot_cells: Array = []
var _equip_panel: PanelContainer = null
var _equip_row: HBoxContainer = null
## kind -> the cell, in `Inventory.EQUIPMENT_KINDS` order.
var _equip_cells: Dictionary = {}
var _buttons_panel: PanelContainer = null
var _craft_button: Button = null
var _map_button: Button = null
var _menu_button: Button = null

var _card_panel: PanelContainer = null
var _card_icon_holder: Control = null
var _card_name: Label = null
var _card_hint: Label = null
var _use_button: Button = null
var _drop_button: Button = null
## The X / Z reminder, shown only when the card's slot is the selected one,
## which is the slot those keys act on.
var _card_keys: RichTextLabel = null
## What the card describes: `{"kind": "slot", "index": n}` or
## `{"kind": "equip", "key": "hand"}`, or empty while no slot is hovered.
var _card_target: Dictionary = {}
var _card_linger: float = 0.0

var _message: Label = null
var _message_panel: PanelContainer = null
## The two labels that stand in the world, outlined and unpanelled: the thing
## under the pointer named above itself, and the focus — the nearest thing
## that could be acted on — named with what the key would do (`chop pine
## (1/3)`) or what stands in the way (`chop pine · needs a Flint axe`). When
## they are the same thing the focus label alone speaks.
var _hover_label: RichTextLabel = null
var _focus_label: RichTextLabel = null
var _debug_panel: PanelContainer = null
var _debug_grid: GridContainer = null
var _debug_status: Label = null

var _hud_signature: String = ""
var _card_signature: String = ""
var _hover_signature: String = ""
var _focus_signature: String = ""
var _debug_signature: String = ""
var _extra_rows: Array = []
var _world: Variant = null
## The frame owner's last pick: `{entity, target, point}`, or empty.
var _hover: Dictionary = {}
## Where the hovered thing's label hangs, in window pixels; (-1, -1) for none.
var _anchor: Vector2 = Vector2(-1.0, -1.0)
## The frame owner's read of `world.focus` and where its label hangs.
var _focus: Variant = null
var _focus_anchor: Vector2 = Vector2(-1.0, -1.0)
var _hover_slot: int = -1
var _hover_equip: String = ""
## Flights in the air: `{icon, from, to, t, slot}`, in layer units.
var _flights: Array = []
## The frame owner's projection of a world point to window pixels, or unset;
## a flight starts where the thing stood.
var _projector: Callable = Callable()


func setup(pkg, world, _fu) -> void:
	package = pkg
	# Above `view/vignette.gd` (layer 20): in the viewer the panels are DOM
	# elements after `#vignette`, so they paint over the night vignette.
	layer = LAYER
	kit = UiKit.new(pkg, world.manifest if world != null else {})
	_root = UiKit.make_root(kit.theme)
	add_child(_root)
	_build_hud_panel()
	_build_equipment()
	_build_hotbar()
	_build_buttons()
	_build_card()
	_build_message()
	_build_labels()
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


## A pickup with a place in the world starts a flight from there into the slot
## that took it (an `out` pickup is a drop leaving the pack, and flies nowhere).
## Everything else the HUD reads off the world (`world.message` already carries
## what a death or a break says).
func handle_event(event: Dictionary) -> void:
	if str(event.get("type", "")) != "pickup" or bool(event.get("out", false)):
		return
	if _world == null or not event.has("x") or not event.has("z"):
		return
	var from := Vector2(-1.0, -1.0)
	if _projector.is_valid():
		from = _projector.call(Vector3(float(event["x"]), 0.5, float(event["z"])))
	fly_pickup(str(event.get("item", "")), from)


## Lend the HUD the camera's projection (world point -> window pixels, or
## (-1, -1) when behind the camera), so a flight can start where the thing was.
func set_projector(projector: Callable) -> void:
	_projector = projector


## What the pointer is over, from the frame owner's pick, and where its label
## hangs in window pixels (the top of the thing's card; (-1, -1) for none).
func set_hover(pick: Dictionary, anchor: Vector2 = Vector2(-1.0, -1.0)) -> void:
	_hover = pick
	_anchor = anchor


## The focus (`world.focus`, or null): the nearest thing that could be acted
## on, refused or not, and where its label hangs in window pixels. The frame
## owner reads both every frame.
func set_focus(target: Variant, anchor: Vector2 = Vector2(-1.0, -1.0)) -> void:
	_focus = target
	_focus_anchor = anchor


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
	return {"hud": "%d slots, %s, scale %.2f, %d in flight" % [
		_slot_cells.size(), "debug" if debug_on else "play", ui_scale, _flights.size()]}


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

	var clock := clock_of(world)
	_day_strip.phase = float(world.day_phase)
	_day_strip.dusk = float(clock["dusk"])
	_day_strip.queue_redraw()
	var signature := "%s|%d|%s|%s|%d|%d|%d|%s|%s|%s|%s|%d|%d|%d|%d|%s" % [
		str(manifest.get("title", manifest.get("package_id", ""))),
		int(world.day),
		"%s%s%d" % [clock["hour"], clock["word"], int(ceil(float(clock["seconds"])))],
		("%s:%s" % [_season_glyph(world), spec.get("display_name", season.get("id", ""))]) if has_calendar else "",
		int(round(health)), int(round(hunger)), int(round(warmth)),
		"warmth" if (has_calendar or warmth < warmth_max) else "",
		"cold" if (cold and not warm_running) else "",
		_slots_signature(world),
		_equipment_signature(world),
		int(ceil(float((world.torch as Dictionary).get("remaining", 0.0)))),
		int(ceil(float((world.warm as Dictionary).get("remaining", 0.0)))),
		int(world.selected), _hover_slot, _hover_equip,
	]
	if signature != _hud_signature:
		_hud_signature = signature
		_write_hud_text(world, manifest, season, spec, has_calendar, cold, warm_running,
			health, hunger, warmth)
		_write_clock(clock)

	# The bars slide rather than jump (`transition: width .12s linear`).
	_bar_target(_health_bar, health / maxf(1.0, health_max), delta)
	_bar_target(_hunger_bar, hunger / maxf(1.0, hunger_max), delta)
	_bar_target(_warmth_bar, warmth / maxf(1.0, warmth_max), delta)
	_warmth_row.visible = has_calendar or warmth < warmth_max
	_warmth_bar.visible = _warmth_row.visible

	var playing: bool = mode == "play" and not bool(world.dead)
	_hotbar_panel.visible = playing
	_equip_panel.visible = playing
	_buttons_panel.visible = playing
	_craft_button.disabled = not playing or (manifest.get("crafting", {}) as Dictionary).get("recipes", []).is_empty()
	_craft_button.set_pressed_no_signal(bool(world.craft_open))
	_settle_card_target(delta)
	_write_card(world, playing)
	_write_labels(world)
	_write_message(world)
	_write_debug(world)
	_advance_flights(delta)
	_advance_flashes(delta)
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
	var equipment: Dictionary = _equipment(world)
	for key: String in _equip_cells:
		_write_slot(world, _equip_cells[key], equipment.get(key, null), false, key == _hover_equip)

	var torch_left: float = float((world.torch as Dictionary).get("remaining", 0.0))
	_torch.visible = torch_left > 0.0
	_torch.text = "torch lit · %d s" % int(ceil(torch_left))
	var warm_left: float = float((world.warm as Dictionary).get("remaining", 0.0))
	_warm.visible = warm_left > 0.0
	_warm.text = "stone warm · %d s" % int(ceil(warm_left))


## The clock row: `☀ 08:52 · day` on the left, `dusk in 3:02` on the right.
func _write_clock(clock: Dictionary) -> void:
	_row_text(_clock_row, str(clock["glyph"]), "%s · %s" % [clock["hour"], clock["word"]],
		"%s in %s" % [clock["next"], clock_countdown(float(clock["seconds"]))], false)


## The clock read off the world: the hour (phase 0 is sunrise, 06:00), the
## part of the day (`day`, `dusk`, `night`, `dawn`), what comes next and in
## how many seconds — dusk while it is day, dark while dusk falls, dawn
## through the night, day while dawn breaks — and the glyph for it. The dusk
## is the season's (`Helpers.night_factor`'s curve), so a winter clock says
## dusk earlier, in the same hours.
static func clock_of(world) -> Dictionary:
	var phase := fposmod(float(world.day_phase), 1.0)
	var share := Helpers.night_share_of(world)
	var dusk := maxf(0.2, minf(0.76, 1.0 - share - 0.12))
	var length := float((world.manifest.get("gameplay", {}) as Dictionary).get("day_length_seconds", 0.0))
	if length <= 0.0:
		length = SysDayCycle.DEFAULT_DAY_LENGTH
	var word := "day"
	var next := "dusk"
	var target := dusk
	var glyph := "sun"
	if phase >= 0.88:
		word = "dawn"
		next = "day"
		target = 1.0
	elif phase >= dusk + 0.12:
		word = "night"
		next = "dawn"
		target = 0.88
		glyph = "moon"
	elif phase >= dusk:
		word = "dusk"
		next = "dark"
		target = dusk + 0.12
	var hour := fposmod(SUNRISE_HOUR + phase * 24.0, 24.0)
	var minutes := int(floor(hour * 60.0 + 1e-6))
	return {
		"hour": "%02d:%02d" % [minutes / 60, minutes % 60],
		"word": word, "next": next, "glyph": glyph, "dusk": dusk,
		"seconds": maxf(0.0, (target - phase) * length),
	}


## Seconds as `m:ss`.
static func clock_countdown(seconds: float) -> String:
	var whole := int(ceil(seconds))
	return "%d:%02d" % [whole / 60, whole % 60]


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
# The hotbar, the worn slots and the hovered slot's card
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
		parts.append(_entry_signature(slot))
	return ",".join(parts)


func _equipment_signature(world) -> String:
	var parts := PackedStringArray()
	var equipment: Dictionary = _equipment(world)
	for key: String in Inventory.EQUIPMENT_KINDS:
		parts.append(_entry_signature(equipment.get(key, null)))
	return ",".join(parts)


static func _entry_signature(slot: Variant) -> String:
	if not (slot is Dictionary):
		return "-"
	var entry: Dictionary = slot
	return "%s:%d:%s" % [str(entry["item"]), int(entry.get("count", 1)), str(entry.get("uses", ""))]


## What the card describes follows the pointer: the hovered slot while one is
## hovered; the last one while the pointer is on the card itself or for a
## moment after leaving both; nothing otherwise.
func _settle_card_target(delta: float) -> void:
	if _hover_slot >= 0:
		_card_target = {"kind": "slot", "index": _hover_slot}
		_card_linger = CARD_LINGER_SECONDS
		return
	if _hover_equip != "":
		_card_target = {"kind": "equip", "key": _hover_equip}
		_card_linger = CARD_LINGER_SECONDS
		return
	if _card_target.is_empty():
		return
	if _card_panel.visible and _pointer_on(_card_panel):
		_card_linger = CARD_LINGER_SECONDS
		return
	_card_linger -= delta
	if _card_linger <= 0.0 or delta <= 0.0:
		_card_target = {}


## Whether the pointer stands on a panel, in layer units. Reads the mouse
## straight from the viewport, so no Control has to relay an enter or an exit.
func _pointer_on(panel: Control) -> bool:
	if not is_inside_tree():
		return false
	return panel.get_global_rect().has_point(_root.get_global_mouse_position())


## The hovered slot's card: icon, name, what it does, its buttons. A pack
## slot has Use (Eat, Light, Wear…) and Drop; a worn slot has Take off.
func _write_card(world, playing: bool) -> void:
	var show := playing and not bool(world.craft_open) and not _card_target.is_empty()
	var entry: Variant = null
	var signature := ""
	if show:
		if str(_card_target["kind"]) == "slot":
			var index := int(_card_target["index"])
			entry = world.slots[index] if index < world.slots.size() else null
			signature = "slot%d|%s" % [index, _entry_signature(entry)]
		else:
			var key := str(_card_target["key"])
			entry = _equipment(world).get(key, null)
			signature = "equip:%s|%s" % [key, _entry_signature(entry)]
	_card_panel.visible = show
	if not show:
		_card_signature = ""
		return
	if signature == _card_signature:
		return
	_card_signature = signature
	for child in _card_icon_holder.get_children():
		_card_icon_holder.remove_child(child)
		child.queue_free()
	var worn: bool = str(_card_target["kind"]) == "equip"
	_card_keys.visible = not worn and int(_card_target.get("index", -1)) == int(world.selected)
	if entry == null:
		if worn:
			var key := str(_card_target["key"])
			_card_name.text = "%s · nothing worn" % key
			_card_hint.text = _equip_hint(key)
		else:
			_card_name.text = "slot %d · empty" % (int(_card_target["index"]) + 1)
			_card_hint.text = "click a slot, or press its number"
		_card_name.add_theme_color_override("font_color", UiKit.MUTED)
		_use_button.disabled = true
		_use_button.text = "Use"
		_drop_button.visible = not worn
		_drop_button.disabled = true
		var blank := Control.new()
		blank.custom_minimum_size = Vector2(CARD_ICON, CARD_ICON)
		blank.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_card_icon_holder.add_child(blank)
		return
	var item_id := str((entry as Dictionary)["item"])
	var spec := UiKit.item_spec(world.manifest, item_id)
	_card_icon_holder.add_child(kit.icon_rect(world.manifest, item_id, CARD_ICON))
	var many := int((entry as Dictionary).get("count", 1))
	_card_name.text = UiKit.item_name(world.manifest, item_id) + ((" ×%d" % many) if many > 1 else "")
	_card_name.add_theme_color_override("font_color", UiKit.TEXT)
	_card_hint.text = UiKit.use_hint(spec, entry)
	if worn:
		_use_button.disabled = false
		_use_button.text = "Take off"
		_drop_button.visible = false
		return
	var verb := UiKit.use_verb(spec)
	_use_button.disabled = verb == ""
	_use_button.text = (verb.substr(0, 1).to_upper() + verb.substr(1)) if verb != "" else "Use"
	_drop_button.visible = true
	_drop_button.disabled = false


static func _equip_hint(key: String) -> String:
	match key:
		"hand":
			return "a tool worn here chops or mines first"
		"body":
			return "a cloak worn here keeps the cold off"
		"back":
			return "a pack worn here carries more"
	return ""


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


## A worn slot clicked, either button: the thing comes off, back into the pack.
func _on_equip_input(event: InputEvent, key: String) -> void:
	var button := event as InputEventMouseButton
	if button == null or not button.pressed or _world == null:
		return
	if button.button_index != MOUSE_BUTTON_LEFT and button.button_index != MOUSE_BUTTON_RIGHT:
		return
	_world.input["unequip"] = key
	_root.accept_event()


func _on_slot_hover(index: int, inside: bool) -> void:
	if inside:
		_hover_slot = index
	elif _hover_slot == index:
		_hover_slot = -1


func _on_equip_hover(key: String, inside: bool) -> void:
	if inside:
		_hover_equip = key
	elif _hover_equip == key:
		_hover_equip = ""


## The card's first button: Use (or Eat, Light, Wear…) on the slot the card
## describes, which is selected first so the sim's use finds it; Take off on a
## worn thing.
func _on_use() -> void:
	if _world == null or _card_target.is_empty():
		return
	if str(_card_target["kind"]) == "equip":
		_world.input["unequip"] = str(_card_target["key"])
		return
	_world.input["select"] = int(_card_target["index"])
	_world.input["use"] = true


func _on_drop() -> void:
	if _world == null or _card_target.is_empty() or str(_card_target["kind"]) != "slot":
		return
	_world.input["select"] = int(_card_target["index"])
	_world.input["drop"] = true


func _on_craft_button() -> void:
	if _world != null:
		_world.input["craft_toggle"] = true


func _on_map_button() -> void:
	action.emit("map")


func _on_menu_button() -> void:
	action.emit("menu")


# ===========================================================================
# The pickup flight
# ===========================================================================

## An item's icon flies from a window point into the slot that holds the item
## (the first that does), bowing upward, shrinking, and lands with a glow on
## the slot. A start off the screen — or no projector — is just the glow.
func fly_pickup(item_id: String, from_window: Vector2) -> void:
	if _world == null or _root == null:
		return
	var slot := _slot_holding(item_id)
	if from_window.x < 0.0 or from_window.y < 0.0 or slot < 0 or slot >= _slot_cells.size():
		_flash_slot(slot)
		return
	var icon: Control = kit.icon_rect(_world.manifest, item_id, FLIGHT_ICON)
	icon.pivot_offset = Vector2(FLIGHT_ICON, FLIGHT_ICON) * 0.5
	icon.z_index = 10
	_root.add_child(icon)
	var from := from_window / ui_scale - Vector2(FLIGHT_ICON, FLIGHT_ICON) * 0.5
	icon.position = from
	_flights.append({"icon": icon, "from": from, "t": 0.0, "slot": slot, "item": item_id})


func _slot_holding(item_id: String) -> int:
	if _world == null:
		return -1
	var found := -1
	for index: int in _world.slots.size():
		var slot: Variant = _world.slots[index]
		if slot is Dictionary and str((slot as Dictionary)["item"]) == item_id:
			found = index
	return found


func _advance_flights(delta: float) -> void:
	if _flights.is_empty():
		return
	for index in range(_flights.size() - 1, -1, -1):
		var flight: Dictionary = _flights[index]
		var icon: Control = flight["icon"]
		flight["t"] = float(flight["t"]) + (delta / FLIGHT_SECONDS if delta > 0.0 else 1.0)
		var t := clampf(float(flight["t"]), 0.0, 1.0)
		var to := _slot_centre(int(flight["slot"])) - Vector2(FLIGHT_ICON, FLIGHT_ICON) * 0.5
		var from: Vector2 = flight["from"]
		# A quadratic arc: up and over, easing in at the slot.
		var eased := 1.0 - (1.0 - t) * (1.0 - t)
		var control := (from + to) * 0.5 + Vector2(0.0, -FLIGHT_ARC)
		var u := 1.0 - eased
		icon.position = from * u * u + control * 2.0 * u * eased + to * eased * eased
		var s := lerpf(1.0, FLIGHT_END_SCALE, eased)
		icon.scale = Vector2(s, s)
		if t >= 1.0:
			_flash_slot(int(flight["slot"]))
			_root.remove_child(icon)
			icon.queue_free()
			_flights.remove_at(index)


func _flash_slot(index: int) -> void:
	if index < 0 or index >= _slot_cells.size():
		return
	var cell: Control = _slot_cells[index]
	cell.set("flash", 1.0)
	cell.queue_redraw()


func _advance_flashes(delta: float) -> void:
	for cell: Control in _slot_cells:
		var flash := float(cell.get("flash"))
		if flash <= 0.0:
			continue
		cell.set("flash", maxf(0.0, flash - (delta / FLASH_SECONDS if delta > 0.0 else 1.0)))
		cell.queue_redraw()


## A hotbar slot's centre in layer units, after the last reflow.
func _slot_centre(index: int) -> Vector2:
	if index < 0 or index >= _slot_cells.size():
		return _hotbar_panel.position + _hotbar_panel.size * 0.5
	var cell: Control = _slot_cells[index]
	return _hotbar_panel.position + _slot_grid.position + cell.position + cell.size * 0.5


## How many flights are in the air (for a test or a capture).
func flights_in_air() -> int:
	return _flights.size()


# ===========================================================================
# World labels, message, debug
# ===========================================================================

## The two labels in the world. The focus label names the focus with what the
## key would do (the viewer's `#prompt`, moved from a strip above the
## hotbar onto the thing itself); the hover label names the thing under the
## pointer, unless that is the target, or a slot's card is up (the pointer is
## on the panel then).
func _write_labels(world) -> void:
	var playing: bool = mode == "play" and not bool(world.dead) and not bool(world.craft_open)
	var focus_text := ""
	var focus_entity: Variant = null
	if playing and _focus is Dictionary:
		focus_entity = (_focus as Dictionary).get("entity", null)
		focus_text = _describe_target(world, _focus as Dictionary)
	var hover_text := ""
	if playing and _card_target.is_empty():
		var entity: Variant = _hover.get("entity", null)
		var target: Variant = _hover.get("target", null)
		if entity is Dictionary and not is_same(entity, focus_entity):
			if target is Dictionary:
				hover_text = _describe_target(world, target as Dictionary)
			else:
				hover_text = _describe_idle(world, entity as Dictionary)
	_focus_label.visible = focus_text != ""
	if focus_text != _focus_signature:
		_focus_signature = focus_text
		_focus_label.text = focus_text
	_hover_label.visible = hover_text != ""
	if hover_text != _hover_signature:
		_hover_signature = hover_text
		_hover_label.text = hover_text


## What a target offers, in words: `walk & chop pine (1/3)`, `take twigs ×2`,
## `mine boulder · needs a pickaxe`.
func _describe_target(world, block: Dictionary) -> String:
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
		return "%stake %s%s" % [lead, item_name, many]
	var props: Dictionary = (world.manifest as Dictionary).get("props", {})
	var prop_id := str(entity.get("prop_id", ""))
	var prop: Dictionary = props.get(prop_id, {})
	var interaction: Dictionary = block.get("interaction", {})
	var verb := str(interaction.get("verb", ""))
	var hits := int(block.get("hits", 0))
	if hits == 0:
		hits = int(interaction.get("hits", 1))
	var count := " (%d/%d)" % [int(entity.get("hits", 0)), hits] if hits > 1 else ""
	var subject := str(prop.get("family", ""))
	if subject == "":
		subject = prop_id.replace("_", " ")
	if block.get("disabled", null) != null:
		return "%s %s · %s" % [verb, subject, str(block["disabled"])]
	return "%s%s %s%s" % [lead, verb, subject, count]


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
	_clock_row = _bar_row()
	box.add_child(_clock_row)
	_day_strip = DayStripView.new()
	_day_strip.custom_minimum_size = Vector2(HUD_WIDTH - 24.0, DAY_STRIP_HEIGHT)
	_day_strip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(_day_strip)
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


## The three worn places, to the left of the hotbar, each labelled.
func _build_equipment() -> void:
	_equip_panel = UiKit.panel(true, 8.0)
	_root.add_child(_equip_panel)
	_equip_row = HBoxContainer.new()
	_equip_row.add_theme_constant_override("separation", 5)
	_equip_panel.add_child(_equip_row)
	for key: String in Inventory.EQUIPMENT_KINDS:
		var cell := _make_cell(key)
		cell.gui_input.connect(_on_equip_input.bind(key))
		cell.mouse_entered.connect(_on_equip_hover.bind(key, true))
		cell.mouse_exited.connect(_on_equip_hover.bind(key, false))
		_equip_row.add_child(cell)
		_equip_cells[key] = cell


func _build_hotbar() -> void:
	_hotbar_panel = UiKit.panel(true, 8.0)
	_root.add_child(_hotbar_panel)
	_slot_grid = GridContainer.new()
	_slot_grid.columns = HOTBAR_COLUMNS
	_slot_grid.add_theme_constant_override("h_separation", 5)
	_slot_grid.add_theme_constant_override("v_separation", 5)
	_hotbar_panel.add_child(_slot_grid)


## Craft (a toggle that shows the table's state), Map and Menu, stacked at
## the hotbar's end.
func _build_buttons() -> void:
	_buttons_panel = UiKit.panel(true, 8.0)
	_root.add_child(_buttons_panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 4)
	_buttons_panel.add_child(column)
	_craft_button = UiKit.button("Craft  C", UiKit.SMALL)
	_craft_button.toggle_mode = true
	_craft_button.pressed.connect(_on_craft_button)
	column.add_child(_craft_button)
	_map_button = UiKit.button("Map  M", UiKit.SMALL)
	_map_button.pressed.connect(_on_map_button)
	column.add_child(_map_button)
	_menu_button = UiKit.button("Menu  Esc", UiKit.SMALL)
	_menu_button.pressed.connect(_on_menu_button)
	column.add_child(_menu_button)


func _build_card() -> void:
	_card_panel = UiKit.panel(true, 10.0)
	_card_panel.custom_minimum_size = Vector2(CARD_WIDTH, 0.0)
	_card_panel.visible = false
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
	_card_keys = UiKit.rich(UiKit.SMALL)
	_card_keys.text = "[color=#e8e4dc80]%s %s[/color]" % [UiKit.kbd("X"), UiKit.kbd("Z")]
	_card_keys.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	buttons.add_child(_card_keys)


func _build_message() -> void:
	_message_panel = UiKit.panel(false, 12.0)
	_root.add_child(_message_panel)
	_message = UiKit.label("", UiKit.FONT_SIZE)
	_message_panel.add_child(_message)
	_message.modulate.a = 0.0


func _build_labels() -> void:
	_hover_label = UiKit.outlined(UiKit.SMALL, UiKit.TEXT)
	_hover_label.name = "hover_label"
	_hover_label.visible = false
	_root.add_child(_hover_label)
	_focus_label = UiKit.outlined(UiKit.FONT_SIZE, UiKit.ACCENT)
	_focus_label.name = "focus_label"
	_focus_label.visible = false
	_root.add_child(_focus_label)


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


## One slot cell: the icon, a corner label (the key that selects a pack slot,
## the worn place's name), the count, the wear bar.
func _make_cell(corner: String) -> SlotCell:
	var cell := SlotCell.new()
	cell.custom_minimum_size = Vector2(SLOT_BOX, SLOT_BOX)
	cell.mouse_filter = Control.MOUSE_FILTER_STOP
	cell.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
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
	if corner != "":
		var key := UiKit.label(corner, 11, UiKit.MUTED)
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
	return cell


func _rebuild_slots(capacity: int) -> void:
	for child in _slot_grid.get_children():
		_slot_grid.remove_child(child)
		child.queue_free()
	_slot_cells.clear()
	_hover_slot = -1
	for index: int in capacity:
		# The key that selects this slot, in the corner: 1-9, then 0.
		var cell := _make_cell(str((index + 1) % 10) if index < 10 else "")
		cell.gui_input.connect(_on_slot_input.bind(index))
		cell.mouse_entered.connect(_on_slot_hover.bind(index, true))
		cell.mouse_exited.connect(_on_slot_hover.bind(index, false))
		_slot_grid.add_child(cell)
		_slot_cells.append(cell)
	_hud_signature = ""


## Panels float over the frame, so they are placed by hand once their content
## has settled: vitals top-left; the worn slots, the hotbar and the buttons in
## one strip bottom-centre; the card above the slot it describes; the prompt
## above the strip; the message top-centre; the debug panel top-right; the
## hovered thing's name above the thing.
func _reflow() -> void:
	var view: Vector2 = _root.size
	UiKit.fit(_hud_panel)
	_hud_panel.position = Vector2(MARGIN, MARGIN)

	UiKit.fit(_equip_panel)
	UiKit.fit(_hotbar_panel)
	UiKit.fit(_buttons_panel)
	var gap := 10.0
	var strip := _equip_panel.size.x + gap + _hotbar_panel.size.x + gap + _buttons_panel.size.x
	var left := roundf((view.x - strip) * 0.5)
	var bottom := view.y - MARGIN
	_equip_panel.position = Vector2(left, round(bottom - _equip_panel.size.y))
	_hotbar_panel.position = Vector2(left + _equip_panel.size.x + gap, round(bottom - _hotbar_panel.size.y))
	_buttons_panel.position = Vector2(_hotbar_panel.position.x + _hotbar_panel.size.x + gap,
		round(bottom - _buttons_panel.size.y))

	if _card_panel.visible:
		UiKit.fit(_card_panel)
		var cell_at := _hotbar_panel.position
		var cell_h := 0.0
		if str(_card_target.get("kind", "")) == "equip" and _equip_cells.has(_card_target.get("key", "")):
			var cell: Control = _equip_cells[_card_target["key"]]
			cell_at = _equip_panel.position + _equip_row.position + cell.position
			cell_h = cell.size.y
		elif int(_card_target.get("index", -1)) >= 0 and int(_card_target["index"]) < _slot_cells.size():
			var cell: Control = _slot_cells[int(_card_target["index"])]
			cell_at = _hotbar_panel.position + _slot_grid.position + cell.position
			cell_h = cell.size.y
		# Above the slot, its left edge on the slot's, flush enough that the
		# pointer can travel up into the buttons.
		var at := Vector2(cell_at.x, minf(_hotbar_panel.position.y, _equip_panel.position.y) - 6.0 - _card_panel.size.y)
		if cell_h == 0.0:
			at.y = _hotbar_panel.position.y - 6.0 - _card_panel.size.y
		at.x = clampf(at.x, MARGIN, maxf(MARGIN, view.x - _card_panel.size.x - MARGIN))
		_card_panel.position = at.round()

	UiKit.fit(_message_panel)
	_message_panel.modulate.a = _message.modulate.a
	_message_panel.position = Vector2(round((view.x - _message_panel.size.x) * 0.5), MARGIN)
	UiKit.fit(_debug_panel)
	_debug_panel.position = Vector2(view.x - _debug_panel.size.x - MARGIN, MARGIN)

	_place_label(_focus_label, _focus_anchor, view)
	_place_label(_hover_label, _anchor, view)


## A world label centred over its anchor (window pixels), lifted clear of the
## card's top, kept inside the view. An anchor behind the camera puts it
## mid-screen rather than nowhere.
func _place_label(label: RichTextLabel, anchor: Vector2, view: Vector2) -> void:
	if not label.visible:
		return
	UiKit.fit(label)
	var at := anchor / ui_scale
	if anchor.x < 0.0:
		at = view * 0.5
	at = Vector2(at.x - label.size.x * 0.5, at.y - label.size.y - LABEL_LIFT)
	at.x = clampf(at.x, MARGIN, maxf(MARGIN, view.x - label.size.x - MARGIN))
	at.y = clampf(at.y, MARGIN, maxf(MARGIN, view.y - label.size.y - MARGIN))
	label.position = at.round()


# ===========================================================================
# Small read-only helpers
# ===========================================================================

func _slot_capacity(world) -> int:
	return UiKit.slot_capacity(world.manifest, _equipment(world), int(world.base_slots))


## The world's worn things, or an empty set for a stub without any.
func _equipment(world) -> Dictionary:
	var equipment: Variant = _field(world, "equipment", null)
	return equipment if equipment is Dictionary else {}


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


## The day as a strip: the light hours warm, the dusk fading, the night dark,
## the dawn brightening again, and a tick where the hour stands, so the eye
## sees how far off the dark is without reading the countdown.
class DayStripView:
	extends Control

	const LIGHT := Color(0.93, 0.80, 0.46)
	const DARK := Color(0.16, 0.18, 0.28)
	const STEPS := 8

	var phase: float = 0.0
	var dusk: float = 0.5

	func _draw() -> void:
		var track := StyleBoxFlat.new()
		track.bg_color = UiKit.BAR_BG
		track.border_color = UiKit.BAR_BORDER
		track.set_border_width_all(1)
		track.set_corner_radius_all(4)
		draw_style_box(track, Rect2(Vector2.ZERO, size))
		var inner := Rect2(1.0, 1.0, size.x - 2.0, size.y - 2.0)
		# The light hours as one fill; the two twilights as a few steps each;
		# the night as one fill.
		draw_rect(Rect2(inner.position, Vector2(inner.size.x * dusk, inner.size.y)), LIGHT)
		for i in STEPS:
			var t0 := float(i) / STEPS
			var t1 := float(i + 1) / STEPS
			var colour := LIGHT.lerp(DARK, (t0 + t1) * 0.5)
			var x0 := inner.position.x + inner.size.x * (dusk + 0.12 * t0)
			var x1 := inner.position.x + inner.size.x * (dusk + 0.12 * t1)
			draw_rect(Rect2(x0, inner.position.y, x1 - x0, inner.size.y), colour)
			var d0 := inner.position.x + inner.size.x * (0.88 + 0.12 * t0)
			var d1 := inner.position.x + inner.size.x * (0.88 + 0.12 * t1)
			draw_rect(Rect2(d0, inner.position.y, d1 - d0, inner.size.y), DARK.lerp(LIGHT, (t0 + t1) * 0.5))
		var n0 := inner.position.x + inner.size.x * (dusk + 0.12)
		var n1 := inner.position.x + inner.size.x * 0.88
		if n1 > n0:
			draw_rect(Rect2(n0, inner.position.y, n1 - n0, inner.size.y), DARK)
		var tick_x := inner.position.x + inner.size.x * clampf(phase, 0.0, 1.0)
		draw_rect(Rect2(tick_x - 1.0, 0.0, 2.0, size.y), UiKit.TEXT)


## `.slot` — the cell behind an item's icon; `.sel` outlines the selected one,
## the hovered one lifts, and one that just took a pickup glows for a moment.
class SlotCell:
	extends Control

	var selected: bool = false
	var hovered: bool = false
	var swatch: bool = false
	var flash: float = 0.0

	func _draw() -> void:
		var box := StyleBoxFlat.new()
		box.bg_color = UiKit.SWATCH if swatch else (Color("#1f2229") if hovered else UiKit.BAR_BG)
		box.border_color = UiKit.ACCENT if selected else (UiKit.MUTED if hovered else UiKit.BAR_BORDER)
		box.set_border_width_all(2 if selected else 1)
		box.set_corner_radius_all(5)
		draw_style_box(box, Rect2(Vector2.ZERO, size))
		if flash > 0.0:
			var glow := StyleBoxFlat.new()
			glow.bg_color = Color(UiKit.ACCENT.r, UiKit.ACCENT.g, UiKit.ACCENT.b, 0.28 * flash)
			glow.border_color = Color(UiKit.ACCENT.r, UiKit.ACCENT.g, UiKit.ACCENT.b, flash)
			glow.set_border_width_all(3)
			glow.set_corner_radius_all(6)
			glow.set_expand_margin_all(2.0)
			draw_style_box(glow, Rect2(Vector2.ZERO, size))


## `.wear` — how much of a tool is left.
class WearBar:
	extends Control

	var fraction: float = 1.0

	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), UiKit.WEAR_TRACK)
		draw_rect(Rect2(0.0, 0.0, size.x * clampf(fraction, 0.0, 1.0), size.y), UiKit.WEAR_FILL)
