class_name FamilyCamera
extends RefCounted

## Where the view sits over the world.
##
## A port of `web/lib/families/camera/camera.ts`. Two modes, and the runner uses
## only the first: **anchored** pins a tracked value to a fixed screen position,
## which is what an auto-runner wants; **follow** bounds a camera to the terrain
## and carries a shake, which is what the platformer wants.


## The scroll that puts `tracked_px` at `anchor_px` on screen.
static func anchored_scroll(tracked_px: float, anchor_px: float) -> float:
	return tracked_px - anchor_px


## The rectangle a following camera may not leave. Returns `{x, y, width,
## height}`, or an empty dictionary when the inputs do not describe a world —
## a refusal, because a camera bounded by nonsense silently shows nothing.
static func follow_bounds(
	world_width: float,
	top_y: float,
	baseline_y: float,
	viewport_height: float,
	follows_y: bool
) -> Dictionary:
	if not is_finite(world_width) or not is_finite(top_y):
		return {}
	if not is_finite(baseline_y) or not is_finite(viewport_height):
		return {}
	if world_width <= 0.0 or viewport_height <= 0.0:
		return {}
	if baseline_y <= top_y:
		return {}
	return {
		"x": 0.0,
		"y": top_y if follows_y else 0.0,
		"width": world_width,
		"height": (baseline_y - top_y) if follows_y else viewport_height,
	}


## Swap one shake offset for another without accumulating drift: the previous
## offset is taken back out before the next goes in.
static func shift_by_shake(scroll: Dictionary, applied: Dictionary, next: Dictionary) -> Dictionary:
	return {
		"scrollX": (
			float(scroll.get("scrollX", 0.0))
			- float(applied.get("x", 0.0))
			+ float(next.get("x", 0.0))
		),
		"scrollY": (
			float(scroll.get("scrollY", 0.0))
			- float(applied.get("y", 0.0))
			+ float(next.get("y", 0.0))
		),
	}
