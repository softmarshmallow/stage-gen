class_name FamilyParallax
extends RefCounted

## Where a scrolling band sits, and how fast it moves.
##
## A port of `web/lib/families/sideview/parallax/parallax.ts`. Pure layout
## arithmetic: nothing here draws, and both side-view genres bind it to their
## own block — the runner authors bands in `layers`, the platformer inside
## `maps`, and neither knows the other's field name.

const ANCHOR_CANVAS_COVER := "canvas_cover"
const ANCHOR_SCREEN_CENTER := "screen_center"
const ANCHOR_SCREEN_TOP := "screen_top"
const ANCHOR_SCREEN_BOTTOM := "screen_bottom"
const ANCHOR_WALK_SURFACE := "walk_surface"

const SPACE_SCREEN := "screen"
const SPACE_WORLD := "world"

## Back to front. A genre may skip a rung; it may never invert two.
const DEPTH_LADDER: PackedStringArray = PackedStringArray(
	["background", "world", "actors", "foreground", "actorHud", "hud", "overlay"]
)


## Where one band lands. Returns the layout, or an empty dictionary when the
## inputs do not describe a band — a refusal, because a band placed from
## nonsense is a band drawn somewhere nobody looks.
static func layer_layout(
	vertical_anchor: String,
	vertical_offset: float,
	source_height: float,
	trimmed_height: float,
	viewport_height: float,
	walk_surface_y: float,
	parallax: float
) -> Dictionary:
	if not is_finite(parallax) or parallax < 0.0:
		return {}
	if not is_finite(viewport_height) or viewport_height <= 0.0:
		return {}
	if not is_finite(walk_surface_y):
		return {}
	if source_height <= 0.0 or trimmed_height <= 0.0:
		return {}
	if not is_finite(vertical_offset):
		return {}
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
	var space := SPACE_WORLD if vertical_anchor == ANCHOR_WALK_SURFACE else SPACE_SCREEN
	return {
		"scale": scale,
		"topY": top_y,
		"space": space,
		"verticalScrollFactor": 1.0 if space == SPACE_WORLD else parallax,
		"sourceHeight": trimmed_height,
		"renderedHeight": rendered_height,
	}


## Where a tiled band's origin sits for this scroll.
static func band_tile_position(scroll_x: float, parallax: float, scale: float) -> float:
	return (scroll_x * parallax) / scale


## Check a depth ladder is ascending back-to-front. Returns the ladder or a
## refusal. Skipping a rung is allowed; inverting two is not.
static func seal_depth_ladder(ladder: Dictionary) -> Variant:
	var previous_rung := ""
	var previous_value := 0.0
	var seen := false
	for rung in DEPTH_LADDER:
		if not ladder.has(rung):
			continue
		var raw: Variant = ladder[rung]
		if not (raw is float or raw is int):
			return KernelRefusal.of(
				"parallax/depth", "depth rung %s must be a finite number" % rung, rung
			)
		var value := float(raw)
		if seen and value <= previous_value:
			return KernelRefusal.of(
				"parallax/depth",
				(
					"depth ladder is out of order: %s at %s is not above %s at %s"
					% [rung, value, previous_rung, previous_value]
				),
				rung
			)
		previous_rung = rung
		previous_value = value
		seen = true
	return ladder.duplicate()


## Where a band of `order` stands on the ladder.
static func band_depth(ladder: Dictionary, plane: String, order: int) -> Variant:
	var rung := "background" if plane == "background" else "foreground"
	if not ladder.has(rung):
		return KernelRefusal.of(
			"parallax/depth", "depth ladder has no %s rung for a band to stand on" % plane, rung
		)
	return float(ladder[rung]) + float(order)
