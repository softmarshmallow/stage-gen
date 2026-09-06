class_name UiKit
extends RefCounted

## What every 2D layer shares: the palette, the font and theme, the panel and
## button builders, the item icons, and the item helpers the panels read the
## world with. One instance per layer; the atlas windows are cheap.
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
const BUTTON_BG := Color("#23262e")
const BUTTON_HOVER := Color("#333844")
const BUTTON_PRESSED := Color("#1a1c22")
const BUTTON_DISABLED_TEXT := Color(232.0 / 255.0, 228.0 / 255.0, 220.0 / 255.0, 0.35)

## `13px` in the viewer; two up, because the viewer's panels were built for a
## laptop and read small even there.
const FONT_SIZE := 15
const SMALL := 13
const TITLE := 17

var font: Font = null
var theme: Theme = null

var _atlas: Texture2D = null
var _item_cells: Dictionary = {}
var _glyph_cells: Dictionary = {}
var _sprites: Dictionary = {}
var _package: Variant = null


func _init(package: Variant = null, manifest: Dictionary = {}) -> void:
	font = make_font()
	theme = make_theme(font)
	_package = package
	_read_icons(manifest)


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


static func make_theme(font_to_use: Font) -> Theme:
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
	made.set_stylebox("normal", "Button", _button_style(BUTTON_BG, BAR_BORDER))
	made.set_stylebox("hover", "Button", _button_style(BUTTON_HOVER, ACCENT))
	made.set_stylebox("pressed", "Button", _button_style(BUTTON_PRESSED, ACCENT))
	made.set_stylebox("focus", "Button", _button_style(Color(0, 0, 0, 0), Color(0, 0, 0, 0)))
	made.set_stylebox("disabled", "Button", _button_style(Color(35.0 / 255.0, 38.0 / 255.0, 46.0 / 255.0, 0.5), PANEL_BORDER))
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


## The viewer's panel: dark, bordered, rounded. `interactive` panels take the
## mouse (their buttons and rows need it); the rest let it through to the
## world.
static func panel(interactive: bool = false, margin: float = 12.0) -> PanelContainer:
	var made := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = PANEL_BG
	style.border_color = PANEL_BORDER
	style.set_border_width_all(1)
	style.set_corner_radius_all(6)
	style.content_margin_left = margin
	style.content_margin_right = margin
	style.content_margin_top = margin * 0.8
	style.content_margin_bottom = margin * 0.8
	made.add_theme_stylebox_override("panel", style)
	made.mouse_filter = Control.MOUSE_FILTER_STOP if interactive else Control.MOUSE_FILTER_IGNORE
	return made


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


static func slot_capacity(manifest: Dictionary, slots: Array, base_slots: int) -> int:
	var extra := 0
	for slot: Variant in slots:
		if not (slot is Dictionary):
			continue
		var use: Variant = item_spec(manifest, str((slot as Dictionary)["item"])).get("use", null)
		if use is Dictionary and str((use as Dictionary).get("kind", "")) == "carry":
			extra += int((use as Dictionary).get("slots", 0)) * int((slot as Dictionary).get("count", 1))
	return base_slots + extra


## The verb the Use button carries for an item, or "" when using it does
## nothing (a tool, a material, a thing that works from the pack).
static func use_verb(spec: Dictionary) -> String:
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
				return "+%d slots while carried" % int(block.get("slots", 0))
			"wear":
				return "%d%% off the cold while carried" % int(round(float(block.get("insulation", 0.0)) * 100.0))
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
