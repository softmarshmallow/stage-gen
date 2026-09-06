class_name UiKit
extends RefCounted

## What every 2D layer shares: the palette, the font and theme, the panel and
## button builders, the item icons, and the item helpers the panels read the
## world with. One instance per layer; the atlas windows are cheap.
##
## **The frame.** A panel and a button are cut from the run's generated
## interface sheets when the manifest carries a `ui` block (the shared
## `game-ui-v5` roles: `panel_frame`, one body; `button_rect`, four state
## bodies) and drawn as Godot nine-patch styleboxes under the geometry the
## pipeline's gate detected — the cell, the insets, the band fill — never a
## number read off the pixels here. A run without the block gets the flat
## boxes the viewer had. The slot wells stay drawn from code in either case:
## a slot is not a generated role yet (TODO.md, "Game UI").
##
## **The pointer.** The same block's optional `cursor_set` is the mouse
## pointer: nine named glyphs on one sheet, each with the hotspot the gate
## measured on the drawn glyph. The kit cuts a cell to a fixed size in screen
## points (`CURSOR_POINTS`, times the display's pixel scale and never the
## HUD's: a pointer keeps the desktop's size whatever the window does, as in
## any game), scales the hotspot with it, and hands the image to Godot for
## the cursor shape the glyph stands for (`CURSOR_SHAPES`), so the
## arrow, the hand over a thing that can be acted on and the cross while a
## built thing is placed are the run's own art. A run without the set keeps
## the system pointer.
##
## The layers are laid out in 1600x900 units and scaled as a whole
## (`apply_scale`): the frame owner hands each of them the window's height
## over 900, so a panel that reads at 1600x900 reads the same on a 4K screen
## or a Retina fullscreen, where the same pixels were a third of the size.

# --- the palette, the viewer's stylesheet with the text a size up ----------
const PANEL_BG := Color(12.0 / 255.0, 13.0 / 255.0, 16.0 / 255.0, 0.86)
const PANEL_BORDER := Color("#2c2f36")
const TEXT := Color("#e8e4dc")
const MUTED := Color(232.0 / 255.0, 228.0 / 255.0, 220.0 / 255.0, 0.62)
const ACCENT := Color("#f0c887")
const ACCENT_DIM := Color(240.0 / 255.0, 200.0 / 255.0, 135.0 / 255.0, 0.14)
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
## The world labels' outline: near-black, and thick enough that the monospace
## strokes stay whole over foliage.
const OUTLINE := Color(0.04, 0.045, 0.06, 0.92)
const OUTLINE_SIZE := 5
const BUTTON_BG := Color("#23262e")
const BUTTON_HOVER := Color("#333844")
const BUTTON_PRESSED := Color("#1a1c22")
const BUTTON_DISABLED_TEXT := Color(232.0 / 255.0, 228.0 / 255.0, 220.0 / 255.0, 0.35)

## `13px` in the viewer; two up, because the viewer's panels were built for a
## laptop and read small even there.
const FONT_SIZE := 15
const SMALL := 13
const TITLE := 17

## How densely a generated sheet is read, over the contract's own hint. The
## sheet's `draw_scale` says a 1024 canvas is drawn at twice a HUD's density;
## this HUD is laid out in 900 units and scaled up to the window, so the sheets
## are read at twice that again: four sheet pixels per layout unit, which puts
## a 96-pixel panel inset at 24 units and a button's frame at about 12 — the
## margins the flat boxes had. One number for both roles, so a panel and the
## button on it are cut from the same ruler.
const SHEET_DENSITY := 2.0
## The states a button sheet publishes, in the theme's names.
const BUTTON_STATES := ["normal", "hover", "pressed", "disabled"]
## The pointer's size in screen points: the desktop's own arrow, fixed. It is
## multiplied by the display's pixel scale (2 on a Retina screen) and by nothing
## else — a pointer does not grow with the window or the HUD, unlike a panel.
## Godot caps a custom cursor at 256 pixels a side.
const CURSOR_POINTS := 32.0
const CURSOR_MAX_PX := 256
## Which Godot cursor shape each glyph of the fixed vocabulary stands for; a
## glyph the host never asks for is still installed, so a Control that asks
## for the shape gets the run's art.
const CURSOR_SHAPES := {
	"arrow": [Input.CURSOR_ARROW],
	"hand": [Input.CURSOR_POINTING_HAND],
	"grab": [Input.CURSOR_DRAG, Input.CURSOR_CAN_DROP],
	"crosshair": [Input.CURSOR_CROSS],
	"inspect": [Input.CURSOR_HELP],
	"busy": [Input.CURSOR_BUSY, Input.CURSOR_WAIT],
	"forbidden": [Input.CURSOR_FORBIDDEN],
	"move": [Input.CURSOR_MOVE],
	"text": [Input.CURSOR_IBEAM],
}

var font: Font = null
var theme: Theme = null

var _atlas: Texture2D = null
var _item_cells: Dictionary = {}
var _glyph_cells: Dictionary = {}
var _sprites: Dictionary = {}
var _package: Variant = null
## The generated panel frame, cut once; every panel draws a duplicate of it.
var _panel_box: StyleBoxTexture = null
## The generated button, one stylebox per sheet state.
var _button_boxes: Dictionary = {}
## What the frames were cut from, for the debug panel and the tests.
var _frame_note: String = "flat"
## The cursor sheet as an image, and `glyph -> {cell: Rect2i, hotspot: Vector2i}`
## in sheet pixels; empty when the run publishes no cursor set.
var _cursor_sheet: Image = null
var _cursor_cells: Dictionary = {}
## The scale the pointers were last installed at; -1 before the first.
var _cursor_scale: float = -1.0


func _init(package: Variant = null, manifest: Dictionary = {}) -> void:
	font = make_font()
	_package = package
	_read_icons(manifest)
	_read_frames(manifest)
	_read_cursors(manifest)
	theme = make_theme(font, _button_boxes)


# ===========================================================================
# Scale
# ===========================================================================

## Scale a layer as a whole and shrink its root to match, so everything laid
## out inside keeps its 1600x900 arithmetic. The root must not be anchored to
## the viewport (anchors follow the viewport's pixels, not the layer's scale).
static func apply_scale(layer: CanvasLayer, root: Control, scale_factor: float) -> void:
	var s := maxf(0.25, scale_factor)
	layer.transform = Transform2D(0.0, Vector2.ZERO).scaled(Vector2(s, s))
	if root == null:
		return
	var viewport := layer.get_viewport()
	if viewport != null:
		root.size = viewport.get_visible_rect().size / s


## A layer's root: unanchored, full-size in layer units, transparent to the
## mouse (the panels inside decide for themselves).
static func make_root(theme_to_use: Theme) -> Control:
	var root := Control.new()
	root.name = "root"
	root.set_anchors_preset(Control.PRESET_TOP_LEFT)
	root.size = Vector2(1600.0, 900.0)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = theme_to_use
	return root


# ===========================================================================
# Font, theme, widgets
# ===========================================================================

## `font: ui-monospace, SFMono-Regular, Menlo, monospace`.
static func make_font() -> Font:
	var made := SystemFont.new()
	made.font_names = PackedStringArray(["ui-monospace", "SF Mono", "SFMono-Regular", "Menlo",
		"Monaco", "DejaVu Sans Mono", "monospace"])
	return made


## The theme: the font, the text colours, and the button's four looks — the
## generated sheet's states when `buttons` carries them (the producer's own
## pixels for hover and pressed, not a tint), the flat boxes otherwise.
static func make_theme(font_to_use: Font, buttons: Dictionary = {}) -> Theme:
	var made := Theme.new()
	made.default_font = font_to_use
	made.default_font_size = FONT_SIZE
	made.set_color("font_color", "Label", TEXT)
	made.set_color("default_color", "RichTextLabel", TEXT)
	made.set_constant("line_separation", "RichTextLabel", 2)
	made.set_color("font_color", "Button", TEXT)
	made.set_color("font_hover_color", "Button", ACCENT)
	made.set_color("font_pressed_color", "Button", ACCENT)
	made.set_color("font_focus_color", "Button", TEXT)
	made.set_color("font_disabled_color", "Button", BUTTON_DISABLED_TEXT)
	var flat := {
		"normal": _button_style(BUTTON_BG, BAR_BORDER),
		"hover": _button_style(BUTTON_HOVER, ACCENT),
		"pressed": _button_style(BUTTON_PRESSED, ACCENT),
		"disabled": _button_style(Color(35.0 / 255.0, 38.0 / 255.0, 46.0 / 255.0, 0.5), PANEL_BORDER),
	}
	for state: String in BUTTON_STATES:
		var box: StyleBox = buttons[state] if buttons.has(state) else flat[state]
		made.set_stylebox(state, "Button", box)
	made.set_stylebox("focus", "Button", _button_style(Color(0, 0, 0, 0), Color(0, 0, 0, 0)))
	return made


static func _button_style(bg: Color, border: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(5)
	style.content_margin_left = 12.0
	style.content_margin_right = 12.0
	style.content_margin_top = 6.0
	style.content_margin_bottom = 6.0
	return style


## A panel: the run's generated frame when the manifest carries one, the
## viewer's dark bordered box otherwise. `interactive` panels take the mouse
## (their buttons and rows need it); the rest let it through to the world.
## `margin` is the padding inside the frame; a generated frame's own insets
## are the floor of it, so nothing is ever laid over the border band.
func panel(interactive: bool = false, margin: float = 12.0) -> PanelContainer:
	var made := PanelContainer.new()
	made.add_theme_stylebox_override("panel", panel_style(margin))
	made.mouse_filter = Control.MOUSE_FILTER_STOP if interactive else Control.MOUSE_FILTER_IGNORE
	return made


## The stylebox a panel of this kit draws.
func panel_style(margin: float = 12.0) -> StyleBox:
	if _panel_box != null:
		var cut: StyleBoxTexture = _panel_box.duplicate()
		cut.content_margin_left = maxf(cut.texture_margin_left, margin)
		cut.content_margin_right = maxf(cut.texture_margin_right, margin)
		cut.content_margin_top = maxf(cut.texture_margin_top, margin * 0.8)
		cut.content_margin_bottom = maxf(cut.texture_margin_bottom, margin * 0.8)
		return cut
	return flat_panel_style(margin)


## The viewer's panel: dark, bordered, rounded.
static func flat_panel_style(margin: float = 12.0) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = PANEL_BG
	style.border_color = PANEL_BORDER
	style.set_border_width_all(1)
	style.set_corner_radius_all(6)
	style.content_margin_left = margin
	style.content_margin_right = margin
	style.content_margin_top = margin * 0.8
	style.content_margin_bottom = margin * 0.8
	return style


## True when the panels and buttons are cut from the run's generated sheets.
func has_frames() -> bool:
	return _panel_box != null and not _button_boxes.is_empty()


## What the frames were cut from: `flat`, or the sheets' sizes and states.
func frame_note() -> String:
	return _frame_note


## The button's stylebox for one sheet state, or null when the kit is flat.
func button_style(state: String) -> StyleBoxTexture:
	return _button_boxes.get(state, null)


static func button(text: String, size: int = FONT_SIZE) -> Button:
	var made := Button.new()
	made.text = text
	made.focus_mode = Control.FOCUS_NONE
	made.add_theme_font_size_override("font_size", size)
	made.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	return made


static func label(text: String, size: int = FONT_SIZE, colour: Color = TEXT) -> Label:
	var made := Label.new()
	made.text = text
	made.add_theme_font_size_override("font_size", size)
	made.add_theme_color_override("font_color", colour)
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return made


## A one-line rich label that never wraps or scrolls.
static func rich(size: int = FONT_SIZE, min_width: float = 0.0) -> RichTextLabel:
	var made := RichTextLabel.new()
	made.bbcode_enabled = true
	made.fit_content = true
	made.scroll_active = false
	made.autowrap_mode = TextServer.AUTOWRAP_OFF
	made.add_theme_font_size_override("normal_font_size", size)
	made.add_theme_font_size_override("bold_font_size", size)
	made.custom_minimum_size = Vector2(min_width, 0.0)
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return made


## A label that stands in the world with no panel behind it: the text drawn
## over a dark outline, so it reads on the bright meadow and the black night
## alike. What names the thing under the pointer and the thing in reach.
static func outlined(size: int = SMALL, colour: Color = TEXT) -> RichTextLabel:
	var made := rich(size)
	made.add_theme_color_override("default_color", colour)
	made.add_theme_color_override("font_outline_color", OUTLINE)
	made.add_theme_constant_override("outline_size", OUTLINE_SIZE)
	return made


static func spacer(height: float) -> Control:
	var made := Control.new()
	made.custom_minimum_size = Vector2(0.0, height)
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return made


static func fit(control: Control) -> void:
	control.size = control.get_combined_minimum_size()


## `<kbd>` in the viewer's legend.
static func kbd(key: String) -> String:
	return "[bgcolor=%s] %s [/bgcolor]" % [KBD_BG, key]


# ===========================================================================
# The generated frames
# ===========================================================================

## Read the manifest's `ui` block: the panel frame's one body and the button
## sheet's four, each cut into a nine-patch stylebox under the published
## geometry. A block a run does not carry, or a sheet that will not load,
## leaves the kit flat; the frames are a look, not a dependency.
func _read_frames(manifest: Dictionary) -> void:
	var ui: Variant = manifest.get("ui", null)
	if not (ui is Dictionary) or _package == null:
		return
	var block: Dictionary = ui
	var panel_cut := _cut_sheet(block.get("panel_frame", null))
	var button_cut := _cut_sheet(block.get("button_rect", null))
	if panel_cut.has("default"):
		_panel_box = panel_cut["default"]
	for state: String in BUTTON_STATES:
		if button_cut.has(state):
			_button_boxes[state] = button_cut[state]
	if _panel_box == null and _button_boxes.is_empty():
		return
	var notes := PackedStringArray()
	if _panel_box != null:
		var region := _panel_box.region_rect
		notes.append("panel %dx%d inset %d" % [int(region.size.x), int(region.size.y),
			int(_panel_box.texture_margin_left)])
	if not _button_boxes.is_empty():
		notes.append("button %d states" % _button_boxes.size())
	_frame_note = " · ".join(notes)


## One role's sheet, cut: `state -> StyleBoxTexture`. The sheet is read at
## `draw_scale * SHEET_DENSITY` sheet pixels per layout unit, so every number
## the manifest publishes in sheet pixels is divided by that once, here; the
## band fill the art was admitted under picks stretch or tile for the edges.
func _cut_sheet(role: Variant) -> Dictionary:
	if not (role is Dictionary):
		return {}
	var spec: Dictionary = role
	var density := maxf(1.0, float(spec.get("draw_scale", 2))) * SHEET_DENSITY
	var texture := _sheet_texture(str(spec.get("asset", "")), density)
	if texture == null:
		return {}
	var insets: Variant = spec.get("insets", null)
	if not (insets is Dictionary):
		return {}
	var band: Dictionary = insets
	var tile := str(spec.get("band_fill", "stretch")) == "tile"
	var axis := StyleBoxTexture.AXIS_STRETCH_MODE_TILE if tile else StyleBoxTexture.AXIS_STRETCH_MODE_STRETCH
	var out := {}
	for entry: Variant in spec.get("cells", []):
		if not (entry is Dictionary) or not ((entry as Dictionary).get("cell", null) is Dictionary):
			continue
		var cell: Dictionary = (entry as Dictionary)["cell"]
		var box := StyleBoxTexture.new()
		box.texture = texture
		box.region_rect = Rect2(
			float(cell.get("x", 0)) / density, float(cell.get("y", 0)) / density,
			float(cell.get("width", 0)) / density, float(cell.get("height", 0)) / density)
		box.texture_margin_left = float(band.get("left", 0)) / density
		box.texture_margin_top = float(band.get("top", 0)) / density
		box.texture_margin_right = float(band.get("right", 0)) / density
		box.texture_margin_bottom = float(band.get("bottom", 0)) / density
		# The content sits inside the insets: the frame is the padding.
		box.content_margin_left = box.texture_margin_left
		box.content_margin_top = box.texture_margin_top
		box.content_margin_right = box.texture_margin_right
		box.content_margin_bottom = box.texture_margin_bottom
		box.axis_stretch_horizontal = axis
		box.axis_stretch_vertical = axis
		box.draw_center = true
		out[str((entry as Dictionary).get("state", "default"))] = box
	return out


## The sheet shrunk by the density once, so the nine-patch's corners land at
## their layout size (a stylebox draws its corners at texture pixels). Cached.
func _sheet_texture(ref: String, density: float) -> Texture2D:
	if ref == "" or _package == null:
		return null
	var key := "sheet:%s@%.2f" % [ref, density]
	if _sprites.has(key):
		return _sprites[key]
	var source: Image = _package.image(ref)
	var made: Texture2D = null
	if source != null and source.get_width() > 0 and source.get_height() > 0:
		var copy := Image.new()
		copy.copy_from(source)
		if copy.has_mipmaps():
			copy.clear_mipmaps()
		copy.resize(
			maxi(1, int(round(copy.get_width() / density))),
			maxi(1, int(round(copy.get_height() / density))),
			Image.INTERPOLATE_LANCZOS)
		made = ImageTexture.create_from_image(copy)
	_sprites[key] = made
	return made


# ===========================================================================
# The pointer
# ===========================================================================

## Read the manifest's `ui.cursor_set`: the sheet and, per glyph, the published
## cell and the hotspot the gate measured inside it. Nothing here is read off
## the pixels; a set a run does not carry leaves the system pointer.
func _read_cursors(manifest: Dictionary) -> void:
	var ui: Variant = manifest.get("ui", null)
	if not (ui is Dictionary) or _package == null:
		return
	var spec: Variant = (ui as Dictionary).get("cursor_set", null)
	if not (spec is Dictionary):
		return
	var block: Dictionary = spec
	var source: Image = _package.image(str(block.get("asset", "")))
	if source == null or source.get_width() <= 0:
		return
	var cells := {}
	for entry: Variant in block.get("cells", []):
		if not (entry is Dictionary):
			continue
		var row: Dictionary = entry
		var cell: Variant = row.get("cell", null)
		var hotspot: Variant = row.get("hotspot", null)
		if not (cell is Dictionary) or not (hotspot is Dictionary):
			continue
		cells[str(row.get("glyph", ""))] = {
			"cell": Rect2i(int((cell as Dictionary).get("x", 0)), int((cell as Dictionary).get("y", 0)),
				int((cell as Dictionary).get("width", 0)), int((cell as Dictionary).get("height", 0))),
			"hotspot": Vector2i(int((hotspot as Dictionary).get("x", 0)), int((hotspot as Dictionary).get("y", 0))),
		}
	if cells.is_empty():
		return
	_cursor_sheet = source
	_cursor_cells = cells


## True when the run publishes a cursor set the kit can install.
func has_cursors() -> bool:
	return _cursor_sheet != null and not _cursor_cells.is_empty()


## The glyphs the set names, in the sheet's order.
func cursor_glyphs() -> Array:
	return _cursor_cells.keys()


## One pointer cut and scaled: `{image: Image, hotspot: Vector2}`, the image
## `size_px` a side and the hotspot the published one scaled by the same
## factor, so it stays on the arrow's tip. Empty when the set lacks the glyph.
func cursor_image(glyph: String, size_px: int) -> Dictionary:
	if not has_cursors() or not _cursor_cells.has(glyph):
		return {}
	var spec: Dictionary = _cursor_cells[glyph]
	var cell: Rect2i = spec["cell"]
	var side := clampi(size_px, 8, CURSOR_MAX_PX)
	var cut := Image.create_empty(cell.size.x, cell.size.y, false, _cursor_sheet.get_format())
	cut.blit_rect(_cursor_sheet, cell, Vector2i.ZERO)
	if cut.get_format() != Image.FORMAT_RGBA8:
		cut.convert(Image.FORMAT_RGBA8)
	cut.resize(side, side, Image.INTERPOLATE_LANCZOS)
	var factor := float(side) / float(cell.size.x)
	var hotspot: Vector2i = spec["hotspot"]
	var point := Vector2(
		clampf(round(float(hotspot.x) * factor), 0.0, float(side - 1)),
		clampf(round(float(hotspot.y) * factor), 0.0, float(side - 1)))
	return {"image": cut, "hotspot": point}


## The pointer's side in physical pixels on a display of the given pixel scale.
static func cursor_px(display_scale: float) -> int:
	return clampi(int(round(CURSOR_POINTS * maxf(0.5, display_scale))), 8, CURSOR_MAX_PX)


## The pixel scale of the display the window is on: 2 on a Retina screen, 1 on
## a plain one and under the dummy display server.
static func display_scale() -> float:
	var screen := DisplayServer.window_get_current_screen()
	var value := DisplayServer.screen_get_scale(screen)
	return value if value > 0.0 else 1.0


## Hand every glyph to Godot as the cursor shapes it stands for, at the fixed
## point size on a display of this pixel scale; called again when the window
## moves or resizes, and re-cut only when the display scale changed. Returns
## how many shapes were installed (0 when the run has no set, or nothing moved).
func install_cursors(display_scale_factor: float) -> int:
	if not has_cursors():
		return 0
	if is_equal_approx(display_scale_factor, _cursor_scale):
		return 0
	_cursor_scale = display_scale_factor
	var side := cursor_px(display_scale_factor)
	var installed := 0
	for glyph: String in CURSOR_SHAPES:
		var cut := cursor_image(glyph, side)
		if cut.is_empty():
			continue
		var texture := ImageTexture.create_from_image(cut["image"])
		for shape: Variant in CURSOR_SHAPES[glyph]:
			Input.set_custom_mouse_cursor(texture, shape as Input.CursorShape, cut["hotspot"])
			installed += 1
	return installed


## Give the pointer back to the system: every shape the set stood for is
## cleared, and the textures behind them are released while the renderer is
## still up (a cursor texture left with Input outlives the rendering server at
## exit and is torn down without one). Called when the HUD leaves the tree.
func uninstall_cursors() -> void:
	if _cursor_scale < 0.0:
		return
	for glyph: String in CURSOR_SHAPES:
		for shape: Variant in CURSOR_SHAPES[glyph]:
			Input.set_custom_mouse_cursor(null, shape as Input.CursorShape)
	_cursor_scale = -1.0


## What the pointer is, for the debug panel: `system`, or the set's glyph count
## and the size it was last installed at.
func cursor_note() -> String:
	if not has_cursors():
		return "system"
	if _cursor_scale < 0.0:
		return "%d glyphs, not installed" % _cursor_cells.size()
	return "%d glyphs at %d px" % [_cursor_cells.size(), cursor_px(_cursor_scale)]


# ===========================================================================
# Icons
# ===========================================================================

func _read_icons(manifest: Dictionary) -> void:
	var icons: Variant = manifest.get("icons", null)
	if not (icons is Dictionary) or _package == null:
		return
	var block: Dictionary = icons
	var atlas_ref := str(block.get("atlas", ""))
	if atlas_ref == "":
		return
	_atlas = _package.texture(atlas_ref)
	if _atlas == null:
		return
	for cell: Variant in block.get("cells", []):
		if not (cell is Dictionary):
			continue
		var entry: Dictionary = cell
		# Godot does not flip textures: the sheet's top-left pixel window is
		# the atlas region as authored.
		var window := Rect2(float(entry.get("x", 0)), float(entry.get("y", 0)),
			float(entry.get("w", 0)), float(entry.get("h", 0)))
		if entry.has("item_id"):
			_item_cells[str(entry["item_id"])] = window
		elif entry.has("glyph"):
			_glyph_cells[str(entry["glyph"])] = window


func has_glyphs() -> bool:
	return _atlas != null and not _glyph_cells.is_empty()


func glyph_texture(glyph: String) -> Texture2D:
	if _atlas == null or not _glyph_cells.has(glyph):
		return null
	var key := "glyph:%s" % glyph
	if _sprites.has(key):
		return _sprites[key]
	var texture := AtlasTexture.new()
	texture.atlas = _atlas
	texture.region = _glyph_cells[glyph]
	texture.filter_clip = true
	_sprites[key] = texture
	return texture


## The sheet's window, then the pickup sprite, then null (the caller draws a
## flat swatch).
func item_texture(manifest: Dictionary, item_id: String) -> Texture2D:
	var key := "item:%s" % item_id
	if _sprites.has(key):
		return _sprites[key]
	var made: Texture2D = null
	if _atlas != null and _item_cells.has(item_id):
		var texture := AtlasTexture.new()
		texture.atlas = _atlas
		texture.region = _item_cells[item_id]
		texture.filter_clip = true
		made = texture
	else:
		var image_ref := str(item_spec(manifest, item_id).get("image", ""))
		if image_ref != "" and _package != null:
			made = _package.texture(image_ref)
	_sprites[key] = made
	return made


## The prop's baseline-state sprite.
func prop_texture(manifest: Dictionary, prop_id: String) -> Texture2D:
	var key := "prop:%s" % prop_id
	if _sprites.has(key):
		return _sprites[key]
	var made: Texture2D = null
	var prop: Variant = manifest.get("props", {}).get(prop_id, null)
	if prop is Dictionary:
		var states: Dictionary = (prop as Dictionary).get("states", {})
		var state: Variant = states.get(str((prop as Dictionary).get("baseline_state", "")), null)
		if state == null and not states.is_empty():
			state = states[states.keys()[0]]
		if state is Dictionary and _package != null:
			made = _package.texture(str((state as Dictionary).get("image", "")))
	_sprites[key] = made
	return made


## An icon control: the texture, or the flat swatch when there is none.
func icon_rect(manifest: Dictionary, item_id: String, box: float) -> Control:
	var texture := item_texture(manifest, item_id)
	if texture != null:
		var rect := TextureRect.new()
		rect.texture = texture
		rect.custom_minimum_size = Vector2(box, box)
		rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		rect.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
		rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
		return rect
	var swatch := ColorRect.new()
	swatch.color = SWATCH
	swatch.custom_minimum_size = Vector2(box, box)
	swatch.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return swatch


# ===========================================================================
# Reading the world (the sim's own helpers are typed `World`; these read the
# same fields off a stub too, so a capture or a test can drive a panel)
# ===========================================================================

static func item_spec(manifest: Dictionary, item_id: String) -> Dictionary:
	var spec: Variant = manifest.get("items", {}).get(item_id, null)
	return spec if spec is Dictionary else {}


static func item_name(manifest: Dictionary, item_id: String) -> String:
	var display := str(item_spec(manifest, item_id).get("display_name", ""))
	return display if display != "" else item_id.replace("_", " ")


static func prop_name(manifest: Dictionary, prop_id: String) -> String:
	var prop: Variant = manifest.get("props", {}).get(prop_id, null)
	if prop is Dictionary:
		var display := str((prop as Dictionary).get("display_name", ""))
		if display != "":
			return display
	return prop_id.replace("_", " ")


static func inv_count(slots: Array, item_id: String) -> int:
	var total := 0
	for slot: Variant in slots:
		if slot is Dictionary and str((slot as Dictionary)["item"]) == item_id:
			total += int((slot as Dictionary).get("count", 1))
	return total


## The base slots plus the pack worn on the back (`equipment.back`); a pack in
## a slot carries nothing.
static func slot_capacity(manifest: Dictionary, equipment: Dictionary, base_slots: int) -> int:
	var back: Variant = equipment.get("back", null)
	if not (back is Dictionary):
		return base_slots
	var use: Variant = item_spec(manifest, str((back as Dictionary)["item"])).get("use", null)
	if use is Dictionary and str((use as Dictionary).get("kind", "")) == "carry":
		return base_slots + int((use as Dictionary).get("slots", 0))
	return base_slots


## The verb the Use button carries for an item, or "" when using it does
## nothing (a material). A tool, a cloak or a pack is worn.
static func use_verb(spec: Dictionary) -> String:
	if spec.get("tool", null) is Dictionary:
		return "wear"
	var use: Variant = spec.get("use", null)
	if not (use is Dictionary):
		return ""
	var block: Dictionary = use
	match str(block.get("kind", "")):
		"consume":
			return "eat" if float(block.get("hunger", 0.0)) != 0.0 else "apply"
		"light":
			return "light"
		"warm":
			return "warm"
		"wear", "carry":
			return "wear"
	return ""


## Which of the three worn places an item goes: `hand` for a tool, `body` for
## a `wear` use, `back` for a `carry` use, "" for the rest. The sim's
## `Inventory.equip_kind`, read off a manifest so a panel can ask.
static func equip_kind(spec: Dictionary) -> String:
	if spec.get("tool", null) is Dictionary:
		return "hand"
	var use: Variant = spec.get("use", null)
	if use is Dictionary:
		match str((use as Dictionary).get("kind", "")):
			"wear":
				return "body"
			"carry":
				return "back"
	return ""


## What a slot's item is for, in one line, after its name.
static func use_hint(spec: Dictionary, slot: Variant) -> String:
	var use: Variant = spec.get("use", null)
	var tool: Variant = spec.get("tool", null)
	if use is Dictionary:
		var block: Dictionary = use
		match str(block.get("kind", "")):
			"consume":
				var parts := PackedStringArray()
				if float(block.get("hunger", 0.0)) != 0.0:
					parts.append("+%d hunger" % int(round(float(block["hunger"]))))
				if float(block.get("health", 0.0)) != 0.0:
					parts.append("+%d health" % int(round(float(block["health"]))))
				if float(block.get("warmth", 0.0)) != 0.0:
					parts.append("+%d warmth" % int(round(float(block["warmth"]))))
				return " · ".join(parts)
			"light":
				return "lights for %d s, %.1f m" % [
					int(round(float(block.get("burn_seconds", 0.0)))), float(block.get("radius_meters", 0.0))]
			"carry":
				return "+%d slots while worn on the back" % int(block.get("slots", 0))
			"wear":
				return "%d%% off the cold while worn" % int(round(float(block.get("insulation", 0.0)) * 100.0))
			"warm":
				return "holds the cold off for %d s" % int(round(float(block.get("heat_seconds", 0.0))))
	if tool is Dictionary:
		var left: Variant = (slot as Dictionary).get("uses", null) if slot is Dictionary else null
		var uses := str(left) if left != null else str((tool as Dictionary).get("uses", 0))
		return "%ss · %s uses left" % [str((tool as Dictionary).get("verb", "")), uses]
	return "a material"


## The death screen's headline for a cause the sim reported.
static func death_headline(cause: String) -> String:
	match cause:
		"cold":
			return "You froze."
		"hunger":
			return "You starved."
		"hurt":
			return "You did not last."
	return "You did not last."


static func death_line(cause: String) -> String:
	match cause:
		"cold":
			return "The cold took you. A fire, a cloak, a warm stone."
		"hunger":
			return "The belly emptied. Berries stew at a lit fire."
		"hurt":
			return "The hound was faster."
	return "The hollow keeps what it takes."


## `m:ss` for a run's length.
static func clock_text(seconds: float) -> String:
	var whole := int(floor(maxf(0.0, seconds)))
	return "%d:%02d" % [whole / 60, whole % 60]
