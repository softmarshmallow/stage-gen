class_name HostRoomLeaf
extends Control

## A point-and-click room, drawn and played.
##
## A port of `web/lib/pointclick/room-scene.ts`. The room is the whole game
## inside its own canvas: the backdrop, the hotspots, the narration, the
## inventory and the verb controls are all drawn in one fixed design space that
## the host scales to whatever window it lands in. Embedded on a phone it fills
## the screen; in a page it letterboxes.
##
## **It lives in `hosts/common/` because three hosts draw it**: the room host
## plays one, and the case host plays one whenever a beat says `kind = "room"`.
## The layering forbids `hosts/case/` from naming anything of
## `hosts/pointclick_room/`, and rightly — the answer is not a back door but the
## honest statement that a leaf player is shared host code.
##
## Every transition still goes through the pure reducer in
## `genres/pointclick_room/state.gd`, the same state machine the Python
## solvability proof searches, so putting a drawing underneath did not give the
## room a second source of truth about whether it can be finished.

## Fired after every click, with the state and what happened inside it, so a case
## shell can autosave and notice the win without polling.
signal changed(state: Dictionary, events: Array)

const ACCENT := Color(1.0, 0.874, 0.541)
const BODY_TEXT := Color(0.949, 0.953, 0.961)
## The dark end of the range, for when the drawn plate is light.
const INK_TEXT := Color(0.078, 0.09, 0.149)
const DIM_TEXT := Color(0.596, 0.627, 0.671)
const SLOT_FILL := Color(0.066, 0.082, 0.106, 0.95)
const SLOT_FILL_HELD := Color(0.165, 0.141, 0.086, 0.95)
const SLOT_STROKE := Color(0.427, 0.459, 0.498, 0.6)
const WIN_DIM := Color(0.02, 0.027, 0.039, 0.72)
## The canvas the room is laid on. The HUD keeps a margin at the edges and a gap
## between its plates, and without a ground those are pixels nothing painted.
const CANVAS_GROUND := Color(0.02, 0.027, 0.039)

## The step-down ladder. A fixed plate holds authored prose only if the size
## comes down until it fits; below the floor the words would be smaller than the
## control hints, so the last step clamps and the label clips inside the plate
## rather than painting the tail across the picture.
const NARRATION_SIZES := [26, 23, 20, 18]
const NARRATION_LINE_SPACING := 8
const HINT_SIZE := 18
const LABEL_SIZE := 22
const WIN_TITLE_SIZE := 28
const WIN_LINE_SIZE := 26

const HOVER_LABEL_LIFT := 8.0
const HOVER_LABEL_FLOOR := 28.0

var manifest: Dictionary = {}
var layout: Dictionary = {}

var _package: HostRunDir = null
var _sheets: HostUiSheets = null
var _scene: Dictionary = {}
var _state: Dictionary = {}
var _mode := RoomLayout.MODE_ACT
var _hints_visible := false
var _pressed_at := 0.0

var _backdrop: TextureRect = null
var _markers: HostOutline = null
var _slot_frames: HostOutline = null
var _hover: Label = null
var _narration: Label = null
var _narration_box: Dictionary = {}
var _hint: Label = null
var _win_layer: Control = null
var _hotspots: Dictionary = {}
var _slot_icons: Array = []
var _verbs: Dictionary = {}
var _hint_button: HostAtlasButton = null


## What a room run's document is called.
const DOCUMENT_REF := "manifest.json"


## Open a room run and build the leaf that plays it, or refuse.
##
## The parse is behind this door rather than in front of it, and that is the
## layering rather than a convenience: `hosts/case/` may not name `RoomContract`,
## because a host naming another recipe's classes is how two hosts grow into one.
## What a case may name is a leaf player, and a leaf player knows its own genre.
static func open(
	run_dir: String,
	carried: PackedStringArray = PackedStringArray(),
	resume: Variant = null
) -> Variant:
	var package := HostRunDir.open(run_dir, Callable(), "", DOCUMENT_REF)
	if package == null:
		return KernelRefusal.of(
			"room/run", "%s is not a readable room run" % run_dir, run_dir
		)
	var parsed: Variant = RoomContract.parse(package.manifest)
	if KernelRefusal.is_refusal(parsed):
		return parsed
	return of(package, parsed as Dictionary, carried, resume)


## Build one room over an opened run. Returns a `KernelRefusal` when the document
## does not carry what a picture needs — a host that drew an untextured
## rectangle instead would be reporting a package fault as a rendering one.
static func of(
	package: HostRunDir,
	document: Dictionary,
	carried: PackedStringArray = PackedStringArray(),
	resume: Variant = null
) -> Variant:
	var scene: Variant = document.get("scene")
	if not (scene is Dictionary) or not (scene as Dictionary).has("backdrop"):
		return KernelRefusal.of("room/scene", "this room publishes no scene frame", "scene")
	var frame: Dictionary = scene
	if float(frame.get("width", 0)) <= 0.0 or float(frame.get("height", 0)) <= 0.0:
		return KernelRefusal.of("room/scene", "this room's scene frame has no size", "scene")
	var sheets := HostUiSheets.of(package, document.get("ui"))
	if not sheets.has("panel_frame") or not sheets.has("button_rect"):
		return KernelRefusal.of(
			"room/ui",
			(
				"this room publishes no panel or button art; regenerate it with a current "
				+ "stage-gen (stage-gen pointclick-room generate)"
			),
			"ui"
		)

	var made := HostRoomLeaf.new()
	made._package = package
	made._sheets = sheets
	made.manifest = document
	made._scene = {"width": float(frame["width"]), "height": float(frame["height"])}
	made.layout = RoomLayout.of(
		made._scene,
		made._screen_insets("panel_frame"),
		made._screen_insets("button_rect")
	)
	made._state = resume if resume is Dictionary else RoomState.initial(document, carried)
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	made.size = Vector2(
		float((made.layout["canvas"] as Dictionary)["width"]),
		float((made.layout["canvas"] as Dictionary)["height"])
	)
	var built: Variant = made._build()
	if KernelRefusal.is_refusal(built):
		return built
	made._render()
	return made


## The design space this leaf draws in: the authored frame plus the HUD band.
func canvas() -> Dictionary:
	return layout["canvas"]


func state() -> Dictionary:
	return _state


## Say the state that is already on screen. A shell that connects after the leaf
## was built asks for it once, so its first save is the room as it opens.
func report() -> void:
	changed.emit(_state, [])


## Play one click from a script rather than from a pointer, for a capture. The
## verb is resolved the same way a press is; passing `""` lets the mode decide.
func click_hotspot(hotspot_id: String, verb: String = "") -> void:
	_act(hotspot_id, verb if verb != "" else RoomLayout.resolve_verb(_mode, false, 0.0))


func set_mode(mode: String) -> void:
	_mode = mode
	_render()


func set_hints(visible: bool) -> void:
	_hints_visible = visible
	_render()


func hints_visible() -> bool:
	return _hints_visible


# --------------------------------------------------------------------- build


func _build() -> Variant:
	var room: Dictionary = layout["room"]
	var canvas_size: Dictionary = layout["canvas"]
	var ground := ColorRect.new()
	ground.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ground.color = CANVAS_GROUND
	ground.position = Vector2(0.0, 0.0)
	ground.size = Vector2(float(canvas_size["width"]), float(canvas_size["height"]))
	add_child(ground)

	_backdrop = TextureRect.new()
	_backdrop.texture = _package.texture(String(_scene_ref()))
	if _backdrop.texture == null:
		return KernelRefusal.of(
			"room/backdrop",
			"this room's backdrop (%s) will not decode" % _scene_ref(),
			"scene.backdrop"
		)
	_backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_backdrop.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_backdrop.stretch_mode = TextureRect.STRETCH_SCALE
	_backdrop.position = Vector2(0.0, 0.0)
	_backdrop.size = Vector2(float(room["width"]), float(room["height"]))
	add_child(_backdrop)

	for entry: Variant in (manifest["hotspots"] as Array):
		var hotspot: Dictionary = entry
		_hotspots[String(hotspot["id"])] = _build_hotspot(hotspot)

	_markers = HostOutline.of()
	add_child(_markers)

	_hover = Label.new()
	_hover.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hover.add_theme_font_size_override("font_size", LABEL_SIZE)
	_hover.add_theme_color_override("font_color", ACCENT)
	_hover.visible = false
	add_child(_hover)

	var built: Variant = _build_hud()
	if KernelRefusal.is_refusal(built):
		return built
	_build_win_card()
	return true


func _build_hotspot(hotspot: Dictionary) -> Control:
	var region := RoomLayout.hotspot_rect(_scene, hotspot["region"])
	var node: Control = null
	var sprite: Variant = hotspot.get("sprite")
	if sprite != null and String(sprite) != "":
		var art := TextureRect.new()
		art.texture = _package.texture(String(sprite))
		art.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		# Fitted inside the authored region and drawn on it, so the marker the
		# "Hotspots" toggle draws and the rectangle a press lands on are the same
		# rectangle. The browser fitted the art to its own aspect and outlined the
		# region, so its overlay pointed at somewhere you could not click.
		art.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		node = art
	else:
		node = Control.new()
	node.position = Vector2(float(region["x"]), float(region["y"]))
	node.size = Vector2(float(region["width"]), float(region["height"]))
	node.mouse_filter = Control.MOUSE_FILTER_STOP
	node.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	var id := String(hotspot["id"])
	node.gui_input.connect(func(event: InputEvent) -> void: _on_hotspot_input(id, event))
	node.mouse_entered.connect(func() -> void: _on_hotspot_hover(hotspot, true))
	node.mouse_exited.connect(func() -> void: _on_hotspot_hover(hotspot, false))
	add_child(node)
	return node


func _build_hud() -> Variant:
	var bar_panel := HostPanelFrame.of(_sheets, "panel_frame", layout["bar"])
	add_child(bar_panel)
	var narration_panel := HostPanelFrame.of(_sheets, "panel_frame", layout["narration"])
	add_child(narration_panel)

	# Where the words go is measured on the drawn frame, not guessed: the
	# producer publishes the ornament-free interior and the layout turns it into
	# an origin and a wrap width, so a heavier border in a future run moves the
	# text instead of running under it.
	var narration_box: Variant = RoomLayout.room_text_layout(narration_panel.safe_rect())
	if KernelRefusal.is_refusal(narration_box):
		return narration_box
	_narration_box = narration_box
	_narration = Label.new()
	_narration.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_narration.position = Vector2(float(_narration_box["x"]), float(_narration_box["y"]))
	_narration.size = Vector2(
		float(_narration_box["wrapWidth"]), float(_narration_box["height"])
	)
	_narration.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	# The one thing the browser could not do: a plate that is too small for a
	# package's prose loses the tail *inside its own art* rather than painting it
	# across the backdrop and the control bar.
	_narration.clip_text = true
	_narration.add_theme_constant_override("line_spacing", NARRATION_LINE_SPACING)
	_narration.add_theme_color_override(
		"font_color", _readable(narration_panel, [BODY_TEXT, INK_TEXT], 4.5, BODY_TEXT)
	)
	add_child(_narration)

	_hint = Label.new()
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hint.add_theme_font_size_override("font_size", HINT_SIZE)
	# Deliberately quiet, so its dim grey is offered first and only replaced when
	# the drawn bar makes it unreadable rather than merely subtle.
	_hint.add_theme_color_override(
		"font_color", _readable(bar_panel, [DIM_TEXT, INK_TEXT, BODY_TEXT], 3.0, DIM_TEXT)
	)
	var hint_point: Dictionary = layout["hint"]
	_hint.position = Vector2(float(hint_point["x"]), float(hint_point["y"]))
	add_child(_hint)

	_slot_frames = HostOutline.of()
	add_child(_slot_frames)
	for entry: Variant in (layout["slots"] as Array):
		var slot: Dictionary = entry
		var icon := TextureRect.new()
		icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.position = Vector2(float(slot["x"]) + 8.0, float(slot["y"]) + 8.0)
		icon.size = Vector2(float(slot["width"]) - 16.0, float(slot["height"]) - 16.0)
		icon.visible = false
		add_child(icon)
		var index := _slot_icons.size()
		var zone := Control.new()
		zone.position = Vector2(float(slot["x"]), float(slot["y"]))
		zone.size = Vector2(float(slot["width"]), float(slot["height"]))
		zone.mouse_filter = Control.MOUSE_FILTER_STOP
		zone.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		zone.gui_input.connect(func(event: InputEvent) -> void: _on_slot_input(index, event))
		add_child(zone)
		_slot_icons.append(icon)

	# The verbs carry the two glyphs the preview set holds for them: a hand for
	# acting and a magnifying glass for looking. The hotspot toggle has no glyph
	# in the set and says its word alone rather than borrowing a symbol that
	# means something else.
	var buttons: Dictionary = layout["verbs"]
	_verbs[RoomLayout.MODE_ACT] = _control(buttons["act"], "Act", "hand")
	_verbs[RoomLayout.MODE_ACT].pressed.connect(
		func() -> void: set_mode(RoomLayout.MODE_ACT)
	)
	_verbs[RoomLayout.MODE_LOOK] = _control(buttons["look"], "Look", "search")
	_verbs[RoomLayout.MODE_LOOK].pressed.connect(
		func() -> void: set_mode(RoomLayout.MODE_LOOK)
	)
	_hint_button = _control(buttons["hint"], "Hotspots", "")
	_hint_button.pressed.connect(func() -> void: set_hints(not _hints_visible))
	return true


func _control(rect: Dictionary, label: String, glyph: String) -> HostAtlasButton:
	var button := HostAtlasButton.of(_sheets, rect, label, glyph)
	add_child(button)
	return button


func _build_win_card() -> void:
	_win_layer = Control.new()
	_win_layer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_win_layer.visible = false
	add_child(_win_layer)

	var room: Dictionary = layout["room"]
	var dim := ColorRect.new()
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	dim.color = WIN_DIM
	dim.position = Vector2(0.0, 0.0)
	dim.size = Vector2(float(room["width"]), float(room["height"]))
	_win_layer.add_child(dim)

	# The end card is the same published `panel_frame` the bar and the plate are,
	# which is what `docs/spec/game/pointclick-room.md` says it is. The browser
	# drew a hard-coded dark rounded rectangle instead, and a dark card on a
	# package that ships a cream interface is the same legibility fault the
	# measured text colour exists to prevent.
	var card := HostPanelFrame.of(_sheets, "panel_frame", layout["win"])
	_win_layer.add_child(card)
	var safe := card.safe_rect()
	var ink := _readable(card, [BODY_TEXT, INK_TEXT], 4.5, BODY_TEXT)

	var title := Label.new()
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title.add_theme_font_size_override("font_size", WIN_TITLE_SIZE)
	# Accent gold first, then the ink end of the range: on a package that ships a
	# cream plate the accent is the one colour on the card that cannot be read,
	# which is the exact fault the measurement exists to prevent.
	title.add_theme_color_override(
		"font_color", _readable(card, [ACCENT, INK_TEXT, BODY_TEXT], 4.5, ACCENT)
	)
	title.text = "Room complete"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.position = Vector2(float(safe["x"]), float(safe["y"]))
	title.size = Vector2(float(safe["width"]), float(WIN_TITLE_SIZE) * 1.6)
	_win_layer.add_child(title)

	var line := Label.new()
	line.mouse_filter = Control.MOUSE_FILTER_IGNORE
	line.add_theme_font_size_override("font_size", WIN_LINE_SIZE)
	line.add_theme_color_override("font_color", ink)
	line.add_theme_constant_override("line_spacing", NARRATION_LINE_SPACING)
	line.text = String((manifest["win"] as Dictionary)["narration"])
	line.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	line.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	line.clip_text = true
	var top := float(safe["y"]) + float(WIN_TITLE_SIZE) * 1.6 + 12.0
	line.position = Vector2(float(safe["x"]), top)
	line.size = Vector2(
		float(safe["width"]), maxf(1.0, float(safe["y"]) + float(safe["height"]) - top)
	)
	_win_layer.add_child(line)


# --------------------------------------------------------------------- input


func _on_hotspot_input(hotspot_id: String, event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return
	var click: InputEventMouseButton = event
	if click.button_index != MOUSE_BUTTON_LEFT and click.button_index != MOUSE_BUTTON_RIGHT:
		return
	if click.pressed:
		# Stamped on this hotspot's own press. The browser stamped it too, but
		# never reset it, so a pointer that went down on a button and up on a
		# hotspot arrived with an arbitrarily old timestamp and read as a long
		# press — a look the player never asked for.
		_pressed_at = _now_ms()
		return
	if bool(_state["solved"]):
		return
	var verb := RoomLayout.resolve_verb(
		_mode, click.button_index == MOUSE_BUTTON_RIGHT, _now_ms() - _pressed_at
	)
	_pressed_at = _now_ms()
	_act(hotspot_id, verb)


func _on_hotspot_hover(hotspot: Dictionary, entering: bool) -> void:
	if not entering:
		_hover.visible = false
		return
	var region := RoomLayout.hotspot_rect(_scene, hotspot["region"])
	_hover.text = String(hotspot["label"])
	var width := _hover.get_minimum_size().x
	_hover.size = _hover.get_minimum_size()
	_hover.position = Vector2(
		float(region["x"]) + float(region["width"]) / 2.0 - width / 2.0,
		maxf(HOVER_LABEL_FLOOR, float(region["y"]) - HOVER_LABEL_LIFT) - _hover.size.y
	)
	_hover.visible = true


func _on_slot_input(index: int, event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return
	var click: InputEventMouseButton = event
	if click.button_index != MOUSE_BUTTON_LEFT or click.pressed:
		return
	var carried := FamilyBag.item_ids(_state["inventory"])
	if index >= carried.size():
		return
	_state = RoomState.select_item(_state, carried[index])
	_render()


func _act(hotspot_id: String, verb: String) -> void:
	var turn := (
		RoomState.interact_turn(manifest, _state, "inspect", hotspot_id)
		if verb == "inspect"
		else RoomState.click_hotspot_turn(manifest, _state, hotspot_id)
	)
	_state = turn["state"]
	_render()
	changed.emit(_state, turn["events"])


# -------------------------------------------------------------------- render


## One pass over the whole view from the reducer's state: no partial updates.
func _render() -> void:
	var markers: Array = []
	for entry: Variant in (manifest["hotspots"] as Array):
		var hotspot: Dictionary = entry
		var id := String(hotspot["id"])
		var node: Control = _hotspots.get(id)
		if node == null:
			continue
		var visible_now := RoomState.hotspot_visible(manifest, _state, id)
		node.visible = visible_now
		node.mouse_filter = (
			Control.MOUSE_FILTER_STOP if visible_now else Control.MOUSE_FILTER_IGNORE
		)
		if visible_now and _hints_visible:
			var region := RoomLayout.hotspot_rect(_scene, hotspot["region"])
			markers.append(
				{
					"rect": Rect2(
						float(region["x"]),
						float(region["y"]),
						float(region["width"]),
						float(region["height"])
					),
					"stroke": Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.85),
					"width": 3.0,
				}
			)
	_markers.show_shapes(markers)

	_set_narration(String(_state["narration"]))
	_render_inventory()

	for mode: Variant in _verbs.keys():
		(_verbs[mode] as HostAtlasButton).set_selected(String(mode) == _mode)
	_hint_button.set_selected(_hints_visible)
	_win_layer.visible = bool(_state["solved"])


## Put the words on the plate, and keep them on it.
##
## A label wraps to a width and grows downward without limit, so the only way a
## fixed plate holds authored prose is to step the size down until it fits.
## Three steps and a floor: below that the words would be smaller than the
## control hints and unreadable, so the last step clamps and `clip_text` keeps
## whatever does not fit inside the art.
func _set_narration(value: String) -> void:
	var font := _narration.get_theme_font("font")
	var size := HostTextFit.fitted_size(
		font,
		value,
		float(_narration_box["wrapWidth"]),
		float(_narration_box["height"]),
		NARRATION_SIZES,
		NARRATION_LINE_SPACING
	)
	_narration.add_theme_font_size_override("font_size", size)
	_narration.text = value




func _render_inventory() -> void:
	var carried := FamilyBag.item_ids(_state["inventory"])
	var frames: Array = []
	var slots: Array = layout["slots"]
	for index in _slot_icons.size():
		var icon: TextureRect = _slot_icons[index]
		if index >= carried.size():
			icon.visible = false
			continue
		var item := _item(String(carried[index]))
		if item.is_empty():
			icon.visible = false
			continue
		var slot: Dictionary = slots[index]
		var held := _state["selectedItem"] != null and String(_state["selectedItem"]) == String(carried[index])
		frames.append(
			{
				"rect": Rect2(
					float(slot["x"]),
					float(slot["y"]),
					float(slot["width"]),
					float(slot["height"])
				),
				"fill": SLOT_FILL_HELD if held else SLOT_FILL,
				"stroke": ACCENT if held else SLOT_STROKE,
				"width": 3.0 if held else 2.0,
			}
		)
		icon.texture = _package.texture(String(item.get("icon", "")))
		icon.visible = icon.texture != null
	_slot_frames.show_shapes(frames)

	var held_id: Variant = _state["selectedItem"]
	if held_id == null:
		_hint.text = "tap to act · hold to look"
		return
	var held_item := _item(String(held_id))
	_hint.text = (
		"holding %s — tap what to use it on" % String(held_item.get("label", held_id))
		if not held_item.is_empty()
		else "tap to act · hold to look"
	)


# -------------------------------------------------------------------- private


func _item(item_id: String) -> Dictionary:
	for entry: Variant in (manifest["items"] as Array):
		var item: Dictionary = entry
		if String(item.get("id", "")) == item_id:
			return item
	return {}


func _scene_ref() -> String:
	return String((manifest["scene"] as Dictionary).get("backdrop", ""))


## A role's insets in screen pixels: the sheet's own, divided by the density it
## was authored at.
func _screen_insets(role: String) -> Dictionary:
	var block := _sheets.block(role)
	var insets: Dictionary = block.get("insets", {})
	var factor := maxf(1.0, float(block.get("draw_scale", 1)))
	return {
		"left": float(insets.get("left", 0)) / factor,
		"top": float(insets.get("top", 0)) / factor,
		"right": float(insets.get("right", 0)) / factor,
		"bottom": float(insets.get("bottom", 0)) / factor,
	}


## The first candidate that reads on the drawn plate, or `fallback` when the
## sheet cannot be sampled — which is the signal to keep whatever colour the
## interface was authored with rather than guess.
func _readable(
	panel: HostPanelFrame, candidates: Array, ratio: float, fallback: Color
) -> Color:
	var face := panel.interior_color()
	if face.is_empty():
		return fallback
	var channels: Array = []
	for entry: Variant in candidates:
		var colour: Color = entry
		channels.append([colour.r * 255.0, colour.g * 255.0, colour.b * 255.0])
	var choice := FamilyContrast.most_readable(face, channels, ratio)
	return fallback if choice < 0 else candidates[choice]


## Milliseconds since the host started, for the long-press rule. The one clock a
## leaf reads, and it is a host's to read.
func _now_ms() -> float:
	return float(Time.get_ticks_msec())
