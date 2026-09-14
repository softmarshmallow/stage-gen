extends RefCounted
## The progression screens' shared register: the fight HUD's bone and gold on ink, serif caps for
## titles and sans for facts, with Korean faces in every fallback chain (the HUD's lists have none).
## Static helpers only; every screen builds its own tree from these.

const BONE := Color(0.95, 0.91, 0.83)
const GOLD := Color(0.83, 0.67, 0.40)
const INK := Color(0.04, 0.03, 0.03)
const PANEL := Color(0.07, 0.055, 0.06, 0.96)
const VEIL := Color(0.02, 0.015, 0.02, 0.78)
const DIM := Color(0.62, 0.58, 0.52)
const PINK := Color(1.0, 0.55, 0.80)
const RARITY := {
	"common": Color(0.66, 0.64, 0.60),
	"rare": Color(0.40, 0.66, 0.98),
	"epic": Color(0.74, 0.48, 0.98),
	"legendary": Color(1.0, 0.76, 0.32),
}
const SERIF_NAMES: PackedStringArray = ["Baskerville", "Georgia", "Times New Roman", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic", "serif"]
const SANS_NAMES: PackedStringArray = ["Avenir Next", "Helvetica Neue", "Arial", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "Malgun Gothic", "sans-serif"]

static var _fonts := {}


static func serif(weight: int = 600, italic: bool = false) -> Font:
	return _font(SERIF_NAMES, weight, italic)


static func sans(weight: int = 600) -> Font:
	return _font(SANS_NAMES, weight, false)


static func _font(names: PackedStringArray, weight: int, italic: bool) -> Font:
	var key := "%s|%d|%s" % [names[0], weight, italic]
	if not _fonts.has(key):
		var f := SystemFont.new()
		f.font_names = names
		f.font_weight = weight
		f.font_italic = italic
		_fonts[key] = f
	return _fonts[key]


static func scale(viewport: Vector2) -> float:
	## Layout scale, 1.0 at 1600x900 like the HUD; a phone-wide window still keeps text legible.
	return clampf(minf(viewport.y / 900.0, viewport.x / 1200.0), 0.55, 3.0)


static func ignore(c: Control) -> Control:
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	c.focus_mode = Control.FOCUS_NONE
	return c


static func text_label(text: String, font: Font, px: float, color: Color = BONE, align: HorizontalAlignment = HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var l := ignore(Label.new()) as Label
	l.text = text
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", int(roundf(px)))
	l.add_theme_color_override("font_color", color)
	l.add_theme_color_override("font_outline_color", Color(0.0, 0.0, 0.0, 0.7))
	l.add_theme_constant_override("outline_size", int(roundf(px * 0.16)))
	l.horizontal_alignment = align
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return l


static func caps(text: String, px: float, color: Color = GOLD, align: HorizontalAlignment = HORIZONTAL_ALIGNMENT_CENTER) -> Label:
	## Spaced serif caps: the register of the HUD's banners and title card.
	var v := FontVariation.new()
	v.base_font = serif(600)
	v.spacing_glyph = int(roundf(px * 0.12))
	var l := text_label(text, v, px, color, align)
	l.uppercase = true
	return l


static func flat(color: Color, radius: float, border: Color = Color(0, 0, 0, 0), border_px: float = 0.0) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(int(roundf(radius)))
	if border_px > 0.0:
		sb.border_color = border
		sb.set_border_width_all(int(roundf(border_px)))
	return sb


static func button(text: String, px: float, primary: bool = true) -> Button:
	## A pressable: gold plate for the one action the screen wants, a thin ghost for the others. Mouse
	## and touch both press it; the Button keeps the mouse (nothing under it sees the press).
	var b := Button.new()
	b.text = text
	b.focus_mode = Control.FOCUS_NONE
	b.add_theme_font_override("font", sans(700))
	b.add_theme_font_size_override("font_size", int(roundf(px)))
	var pad := roundf(px * 0.9)
	var r := roundf(px * 0.35)
	if primary:
		b.add_theme_color_override("font_color", INK)
		b.add_theme_color_override("font_hover_color", INK)
		b.add_theme_color_override("font_pressed_color", INK)
		b.add_theme_color_override("font_disabled_color", Color(INK, 0.5))
		b.add_theme_stylebox_override("normal", _padded(flat(GOLD, r), pad, px * 0.45))
		b.add_theme_stylebox_override("hover", _padded(flat(GOLD.lightened(0.12), r), pad, px * 0.45))
		b.add_theme_stylebox_override("pressed", _padded(flat(GOLD.darkened(0.18), r), pad, px * 0.45))
		b.add_theme_stylebox_override("disabled", _padded(flat(Color(GOLD, 0.35), r), pad, px * 0.45))
	else:
		b.add_theme_color_override("font_color", BONE)
		b.add_theme_color_override("font_hover_color", Color.WHITE)
		b.add_theme_color_override("font_pressed_color", GOLD)
		b.add_theme_color_override("font_disabled_color", Color(BONE, 0.35))
		b.add_theme_stylebox_override("normal", _padded(flat(Color(BONE, 0.06), r, Color(BONE, 0.45), 1.0), pad, px * 0.45))
		b.add_theme_stylebox_override("hover", _padded(flat(Color(BONE, 0.14), r, Color(BONE, 0.7), 1.0), pad, px * 0.45))
		b.add_theme_stylebox_override("pressed", _padded(flat(Color(GOLD, 0.2), r, GOLD, 1.0), pad, px * 0.45))
		b.add_theme_stylebox_override("disabled", _padded(flat(Color(BONE, 0.03), r, Color(BONE, 0.2), 1.0), pad, px * 0.45))
	b.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	return b


static func _padded(sb: StyleBoxFlat, horizontal: float, vertical: float) -> StyleBoxFlat:
	sb.content_margin_left = horizontal
	sb.content_margin_right = horizontal
	sb.content_margin_top = vertical
	sb.content_margin_bottom = vertical
	return sb


static func veil(color: Color = VEIL) -> ColorRect:
	## The dim ground under a modal. It takes the mouse so nothing beneath (the joystick) hears a press.
	var v := ColorRect.new()
	v.color = color
	v.mouse_filter = Control.MOUSE_FILTER_STOP
	v.focus_mode = Control.FOCUS_NONE
	v.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return v


static func place(c: Control, at: Vector2, extent: Vector2) -> void:
	## Position and size, width first: a wrapping label clamps its height to the minimum its *current*
	## width needs, so sizing it in one step from zero width leaves it many lines tall and its centred
	## text well below where it was put. The stale minimum can outlive this call, so a wrapping label is
	## top-aligned and no layout reads a label's size back.
	c.position = at
	c.size = Vector2(extent.x, 0.0)
	c.size = extent


static func rule(parent: Control, color: Color = Color(GOLD, 0.7)) -> ColorRect:
	var r := ignore(ColorRect.new()) as ColorRect
	r.color = color
	parent.add_child(r)
	return r


static func pressed(event: InputEvent) -> bool:
	## True for a real press, mouse or touch, with the emulated twin of either dropped.
	var touch := event as InputEventScreenTouch
	if touch != null:
		return touch.pressed and event.device != InputEvent.DEVICE_ID_EMULATION
	var mouse := event as InputEventMouseButton
	return mouse != null and mouse.pressed and mouse.button_index == MOUSE_BUTTON_LEFT and event.device != InputEvent.DEVICE_ID_EMULATION


static func item_name(text: Callable, spec: Dictionary) -> String:
	## An item's shown name: the design's own name_key through the host's text callable.
	return String(text.call(String(spec.get("name_key", ""))))


static func label(labels: Dictionary, defaults: Dictionary, key: String, values: Dictionary = {}) -> String:
	## A chrome string: the host's label when it gave one, else the package's English default.
	return String(labels.get(key, defaults.get(key, key))).format(values)
