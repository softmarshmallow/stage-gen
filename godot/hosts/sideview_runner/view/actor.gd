class_name RunnerActor
extends Sprite2D

## A published actor on screen: the avatar, or a boss.
##
## Both are the same shape of thing — a set of motion strips, one calibration,
## a per-motion rebase multiplier and anchor — and the browser drew them with
## the same three lines in two places. Here it is one class, because the two
## drifted apart in this port and the avatar's half was wrong: it sized the
## body by dividing the design height by whatever the atlas cell happened to be,
## which silently ignores both the calibration and the rebase multiplier, so
## every motion stood a slightly different height.
##
## **Size comes from the ruler, never from the pixels.** `source_px_per_unit` is
## how many source pixels the producer drew one unit of height as; a strip
## redrawn at another resolution carries a different one and stands exactly as
## tall. `rebase_multiplier` is the per-strip correction on top of it, because
## the strips were rebased against each other after they were drawn.
##
## The clock is the caller's. Nothing here reads a wall clock, so a capture that
## hands it fixed steps draws the same frame every time — which is the whole
## reason a picture of this game can be compared with another picture of it.

## Frames the strip has, when a motion does not name them.
const IMPLICIT_FRAME_LIST := []

var _motions: Dictionary = {}
var _base_scale: float = 1.0
var _state: String = ""
## An impulse count, so a repeated action replays the strip. A second air jump
## inside one `jump` state, or a second salvo inside one `attack`, has to
## restart the animation or it reads as having no animation at all.
var _impulses: int = -1
var _frame: int = 0
var _clock: float = 0.0
var _anchor: String = "bottom"
var _material: ShaderMaterial = null


## Build an actor from a published motion list.
##
## Returns null when nothing could be loaded, so a caller can say which actor
## went missing rather than drawing an empty sprite forever.
static func of(
	package: HostRunDir, motions: Array, calibration: Dictionary, config: Dictionary,
	flash_shader: Shader
) -> RunnerActor:
	var actor := RunnerActor.new()
	actor.centered = false
	for entry: Variant in motions:
		var motion: Dictionary = entry
		var texture := package.texture(String(motion["atlas"]))
		if texture == null:
			push_error("runner actor: motion %s has no atlas at %s" % [motion["state"], motion["atlas"]])
			continue
		var columns := maxi(1, int(motion["columns"]))
		var frames: Array = motion.get("canonical_frame_indices", IMPLICIT_FRAME_LIST)
		if frames.is_empty():
			frames = range(columns)
		actor._motions[String(motion["state"])] = {
			"texture": texture,
			"columns": columns,
			"fps": float(motion.get("frames_per_second", 12)),
			"loop": String(motion.get("playback_mode", "once")) == "loop",
			"frames": frames,
			"rebase": float(motion.get("rebase_multiplier", 1.0)),
			"anchor": String(motion.get("anchor", "bottom")),
		}
	if actor._motions.is_empty():
		return null
	var per_unit := float(calibration.get("source_px_per_unit", 0.0))
	if per_unit <= 0.0:
		push_error("runner actor: calibration carries no source_px_per_unit to size by")
		return null
	actor._base_scale = (
		float(config["playerHeightTiles"]) * float(config["tilePx"]) / per_unit
	)
	if flash_shader != null:
		actor._material = ShaderMaterial.new()
		actor._material.shader = flash_shader
		actor.material = actor._material
	return actor


## Does this actor have a strip for `state`?
func has_motion(state: String) -> bool:
	return _motions.has(state)


## Show one motion. Restarts the strip on a state change or a new impulse.
func show_motion(state: String, impulses: int = 0) -> void:
	var chosen := state
	if not _motions.has(chosen):
		# The contract guarantees the states a genre reads; anything else falls
		# back to the first published strip rather than vanishing, and says so
		# once rather than every frame.
		if _state != "" and _motions.has(_state):
			return
		chosen = String(_motions.keys()[0])
		push_warning("runner actor: no strip for %s; drawing %s" % [state, chosen])
	if chosen == _state and impulses == _impulses:
		return
	_state = chosen
	_impulses = impulses
	_frame = 0
	_clock = 0.0
	var motion: Dictionary = _motions[chosen]
	_anchor = String(motion["anchor"])
	var strip_scale := _base_scale * float(motion["rebase"])
	scale = Vector2(strip_scale, strip_scale)
	texture = motion["texture"]
	region_enabled = true
	_apply_region()


## Advance the strip by `dt` seconds of the caller's clock.
func advance(dt: float) -> void:
	if _state == "":
		return
	var motion: Dictionary = _motions[_state]
	var frames: Array = motion["frames"]
	_clock += dt * float(motion["fps"])
	var steps := int(_clock)
	if steps <= 0:
		return
	_clock -= float(steps)
	if bool(motion["loop"]):
		_frame = (_frame + steps) % frames.size()
	else:
		_frame = mini(_frame + steps, frames.size() - 1)
	_apply_region()


## Put the actor's anchor point at `x`, `y`. For a `bottom` anchor that is where
## the feet stand; for a `top` anchor, where the head hangs from.
func place(x: float, y: float) -> void:
	var drawn := _cell_size() * scale
	position = Vector2(x - drawn.x / 2.0, y - drawn.y if _anchor == "bottom" else y)


## How big the actor is drawn, in screen pixels. What a caller needs to put
## something else — a bar, a name — against the body rather than against the row
## the body's feet are on.
func drawn_size() -> Vector2:
	return _cell_size() * scale


## Fill the silhouette white, or stop.
func set_flash(on: bool) -> void:
	if _material != null:
		_material.set_shader_parameter("amount", 1.0 if on else 0.0)


func _apply_region() -> void:
	var motion: Dictionary = _motions[_state]
	var cell := _cell_size()
	var frames: Array = motion["frames"]
	var index := int(frames[mini(_frame, frames.size() - 1)])
	region_rect = Rect2(float(index) * cell.x, 0.0, cell.x, cell.y)


func _cell_size() -> Vector2:
	if texture == null or _state == "":
		return Vector2.ONE
	var motion: Dictionary = _motions[_state]
	return Vector2(
		float(texture.get_width()) / float(motion["columns"]), float(texture.get_height())
	)
