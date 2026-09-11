extends RefCounted

## Native Godot styles for the disposable presentation scenes. The palette,
## square borders, and procedural slider handles require no external UI art.
const TEXT := Color("edf2f1")
const MUTED := Color("a8b5ba")
const ACCENT := Color("e5ad58")
const SECONDARY := Color("79b8b1")
const BG := Color("10171d")
const PANEL := Color("182229")
const PANEL_RAISED := Color("202e36")
const BORDER := Color("52626a")
const DISABLED := Color("718087")
const INK := Color("142027")


static func heading_font() -> Font:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Avenir Next Condensed", "Arial Narrow", "Noto Sans"])
	font.font_weight = 700
	return font


static func build() -> Theme:
	var theme := Theme.new()
	theme.default_font_size = 14
	# Use Godot's bundled font so the same metrics work on every local scene.
	theme.default_font = ThemeDB.fallback_font
	theme.set_color("font_color", "Label", TEXT)
	theme.set_color("font_shadow_color", "Label", Color(0.0, 0.0, 0.0, 0.35))
	theme.set_constant("shadow_offset_x", "Label", 0)
	theme.set_constant("shadow_offset_y", "Label", 1)
	theme.set_stylebox("panel", "Panel", panel_style())
	theme.set_stylebox("panel", "PanelContainer", panel_style())
	for control: String in ["Button", "OptionButton", "MenuButton"]:
		theme.set_font_size("font_size", control, 14)
		theme.set_color("font_color", control, TEXT)
		theme.set_color("font_hover_color", control, Color.WHITE)
		theme.set_color("font_pressed_color", control, TEXT)
		theme.set_color("font_hover_pressed_color", control, Color.WHITE)
		theme.set_color("font_focus_color", control, TEXT)
		theme.set_color("font_disabled_color", control, DISABLED)
		theme.set_stylebox("normal", control, button_style())
		theme.set_stylebox("hover", control, button_style(true))
		theme.set_stylebox("pressed", control, button_style(false, true))
		theme.set_stylebox("hover_pressed", control, button_style(true, true))
		theme.set_stylebox("disabled", control, disabled_style())
		theme.set_stylebox("focus", control, focus_style())
		theme.set_constant("outline_size", control, 0)
		theme.set_constant("h_separation", control, 8)
	for slider: String in ["HSlider", "VSlider"]:
		var vertical := slider == "VSlider"
		theme.set_stylebox("slider", slider, _slider_track(Color("111a20"), BORDER, vertical))
		theme.set_stylebox("grabber_area", slider, _slider_track(SECONDARY.darkened(0.3), SECONDARY.darkened(0.1), vertical))
		theme.set_stylebox("grabber_area_highlight", slider, _slider_track(SECONDARY, SECONDARY.lightened(0.15), vertical))
		theme.set_stylebox("focus", slider, focus_style())
		theme.set_icon("grabber", slider, _slider_handle(ACCENT, vertical))
		theme.set_icon("grabber_highlight", slider, _slider_handle(Color("f4cf87"), vertical))
		theme.set_icon("grabber_disabled", slider, _slider_handle(DISABLED.darkened(0.25), vertical))
		theme.set_constant("center_grabber", slider, 0)
		theme.set_constant("grabber_offset", slider, 0)
		theme.set_constant("tick_offset", slider, 0)
	theme.set_stylebox("panel", "PopupPanel", panel_style())
	theme.set_stylebox("panel", "TooltipPanel", _box(PANEL, SECONDARY, 1, 10, 7))
	theme.set_font_size("font_size", "TooltipLabel", 13)
	theme.set_color("font_color", "TooltipLabel", TEXT)
	return theme


static func button_style(hovered: bool = false, selected: bool = false) -> StyleBox:
	var fill := PANEL_RAISED if hovered else PANEL
	var line := SECONDARY if hovered else BORDER
	if selected:
		fill = Color("483927") if hovered else Color("372f25")
		line = ACCENT
	return _box(fill, line, 1, 10, 4)


static func focus_style() -> StyleBox:
	var style := _box(Color.TRANSPARENT, SECONDARY, 2, 10, 4)
	style.draw_center = false
	style.set_expand_margin_all(2)
	return style


static func disabled_style() -> StyleBox:
	return _box(Color("151e24"), Color("34434b"), 1, 10, 4)


static func panel_style() -> StyleBox:
	return _box(PANEL, BORDER.darkened(0.25), 1, 14, 12)


## Primary actions use amber fill and dark text in every active state. Apply
## after a route's local button overrides so the default style cannot leak in.
static func style_primary(button: Button) -> void:
	button.add_theme_stylebox_override("normal", _box(ACCENT, ACCENT, 1, 10, 4))
	button.add_theme_stylebox_override("hover", _box(Color("f1c27d"), Color("f7d5a0"), 1, 10, 4))
	button.add_theme_stylebox_override("pressed", _box(Color("c98e3d"), Color("edbd76"), 1, 10, 4))
	button.add_theme_stylebox_override("hover_pressed", _box(Color("d39a48"), Color("f1c27d"), 1, 10, 4))
	button.add_theme_stylebox_override("disabled", disabled_style())
	button.add_theme_stylebox_override("focus", focus_style())
	for state: String in ["font_color", "font_hover_color", "font_pressed_color", "font_hover_pressed_color", "font_focus_color"]:
		button.add_theme_color_override(state, INK)
	button.add_theme_color_override("font_disabled_color", DISABLED)


static func _box(fill: Color, line: Color, width: int, horizontal: float, vertical: float) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = line
	style.set_border_width_all(width)
	style.set_corner_radius_all(0)
	style.anti_aliasing = false
	style.content_margin_left = horizontal
	style.content_margin_right = horizontal
	style.content_margin_top = vertical
	style.content_margin_bottom = vertical
	return style


static func _slider_track(fill: Color, line: Color, vertical: bool) -> StyleBox:
	var style := _box(fill, line, 1, 3 if vertical else 0, 0 if vertical else 3)
	return style


static func _slider_handle(colour: Color, vertical: bool) -> Texture2D:
	# A native gradient resource supplies a solid rectangular handle directly
	# from code. There is no image file, generated artwork, or import dependency.
	var gradient := Gradient.new()
	gradient.colors = PackedColorArray([colour, colour])
	var handle := GradientTexture2D.new()
	handle.gradient = gradient
	handle.width = 20 if vertical else 10
	handle.height = 10 if vertical else 20
	return handle
