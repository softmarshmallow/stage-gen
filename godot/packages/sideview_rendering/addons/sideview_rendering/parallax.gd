extends RefCounted

const Refusal = preload("refusal.gd")

const ANCHOR_CANVAS_COVER := "canvas_cover"
const ANCHOR_SCREEN_CENTER := "screen_center"
const ANCHOR_SCREEN_TOP := "screen_top"
const ANCHOR_SCREEN_BOTTOM := "screen_bottom"
const ANCHOR_WALK_SURFACE := "walk_surface"

const SPACE_SCREEN := "screen"
const SPACE_WORLD := "world"

## Layout in caller-provided coordinates. No camera, scene or depth ladder.
## Returns a layout dictionary or a structured refusal.
static func layer_layout(
	vertical_anchor: String,
	vertical_offset: float,
	source_height: float,
	trimmed_height: float,
	viewport_height: float,
	walk_surface_y: float,
	parallax: float
) -> Dictionary:
	if not [ANCHOR_CANVAS_COVER, ANCHOR_SCREEN_CENTER, ANCHOR_SCREEN_TOP, ANCHOR_SCREEN_BOTTOM, ANCHOR_WALK_SURFACE].has(vertical_anchor):
		return Refusal.of("sideview/anchor", "unsupported vertical anchor", "vertical_anchor")
	var dimensions := {"source_height": source_height, "trimmed_height": trimmed_height, "viewport_height": viewport_height}
	for field: String in dimensions:
		var value: float = dimensions[field]
		if not is_finite(value) or value <= 0.0:
			return Refusal.of("sideview/dimensions", "dimension must be finite and positive", field)
	var inputs := {"vertical_offset": vertical_offset, "walk_surface_y": walk_surface_y, "parallax": parallax}
	for field: String in inputs:
		var value: float = inputs[field]
		if not is_finite(value) or (field == "parallax" and value < 0.0):
			return Refusal.of("sideview/layout", "layout input is outside its finite range", field)
	var scale := viewport_height / source_height
	var rendered_height := trimmed_height * scale
	var top_y := 0.0
	match vertical_anchor:
		ANCHOR_CANVAS_COVER:
			top_y = 0.0
		ANCHOR_SCREEN_CENTER:
			top_y = viewport_height / 2.0 - rendered_height / 2.0 + vertical_offset * rendered_height
		ANCHOR_SCREEN_TOP:
			top_y = vertical_offset * rendered_height
		_:
			var datum := viewport_height if vertical_anchor == ANCHOR_SCREEN_BOTTOM else walk_surface_y
			top_y = datum - (1.0 - vertical_offset) * rendered_height
	if not is_finite(scale) or scale <= 0.0 or not is_finite(rendered_height) or rendered_height <= 0.0 or not is_finite(top_y):
		return Refusal.of("sideview/layout", "layout arithmetic exceeds its finite range", "")
	var space := SPACE_WORLD if vertical_anchor == ANCHOR_WALK_SURFACE else SPACE_SCREEN
	return {
		"scale": scale,
		"top_y": top_y,
		"space": space,
		"vertical_scroll_factor": 1.0 if space == SPACE_WORLD else parallax,
		"trimmed_height": trimmed_height,
		"rendered_height": rendered_height,
	}


## Where a tiled band's origin sits for this scroll.
static func band_tile_position(scroll_x: float, parallax: float, scale: float) -> Variant:
	if not is_finite(scroll_x) or not is_finite(parallax) or parallax < 0.0 or not is_finite(scale) or scale <= 0.0:
		return Refusal.of("sideview/scroll", "scroll needs finite values, nonnegative parallax and positive scale", "")
	var position := (scroll_x * parallax) / scale
	if not is_finite(position):
		return Refusal.of("sideview/scroll", "scroll arithmetic exceeds its finite range", "")
	return position
