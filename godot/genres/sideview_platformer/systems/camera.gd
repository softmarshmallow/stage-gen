class_name PlatformerCameraSystem
extends RefCounted

## Where the view sits: a dead-zone follow, bounded by the map.
##
## The browser does not compute this. It hands Phaser a world box, a follow
## target, a 300x180 dead zone and a lerp, and the engine moves the view — so
## what is ported here is **Phaser's `preRender`**, which is the arithmetic that
## actually decided the golden's numbers. Reproduced rather than approximated:
## place the dead zone on the camera's midpoint, push the scroll by however far
## the target is outside it, lerp toward that, then clamp to the bounds.
##
## It is not a cosmetic port. The spawn director asks which columns are on
## screen, so a camera that moved differently would change what the world *does*
## and not only what it looks like.
##
## The bounds are the `camera` family's — an axis is switched off by giving the
## camera no room to travel along it, which is a camera rule and not a scene one.

const VIEW_WIDTH := 1280.0
const VIEW_HEIGHT := 720.0

## The box the target may move inside before the view follows it, and how much
## of the remaining distance one frame closes.
const DEADZONE_WIDTH := 300.0
const DEADZONE_HEIGHT := 180.0
const LERP := 0.12

## Where the body sits relative to the point the camera centres. Only y is
## offset: the player is drawn a little above the middle of the frame.
const FOLLOW_OFFSET_X := 0.0
const FOLLOW_OFFSET_Y := 50.0


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "camera/follow",
			"contract_version": "camera-system-v1",
			"reads": ["hold", "player"],
			"owns": ["camera"],
		}
	)


static func update(world: PlatformerWorld, _step: Dictionary) -> void:
	if world.hold:
		return
	world.camera = advance(world.camera, float(world.player["x"]), bounds_of(world))


## One frame of the follow.
static func advance(camera: Dictionary, target_x: float, bounds: Dictionary) -> Dictionary:
	var scroll := float(camera["scrollX"])
	var follow_x := target_x - FOLLOW_OFFSET_X
	var middle := scroll + VIEW_WIDTH / 2.0
	var left := middle - DEADZONE_WIDTH / 2.0
	var right := middle + DEADZONE_WIDTH / 2.0
	if follow_x > right:
		scroll = _linear(scroll, scroll + (follow_x - right), LERP)
	elif follow_x < left:
		scroll = _linear(scroll, scroll - (left - follow_x), LERP)
	return {"scrollX": _clamped(scroll, bounds), "scrollY": float(camera["scrollY"])}


## Where the view lands the moment a map opens: the body centred, then clamped.
##
## Phaser's own snap on follow start is midpoint-based too, so this is what the
## first frame of a map would settle to rather than a place the dead zone would
## then drag the view away from over the following half second.
static func snapped(target_x: float, bounds: Dictionary) -> Dictionary:
	return {
		"scrollX": _clamped(target_x - FOLLOW_OFFSET_X - VIEW_WIDTH / 2.0, bounds),
		# The maps this genre publishes follow x only, so the view never leaves
		# the ground line. A map that followed y would take its scroll from the
		# same family call the bounds come from.
		"scrollY": 0.0,
	}


## The rectangle the view may not leave, for the map the run is on.
static func bounds_of(world: PlatformerWorld) -> Dictionary:
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	return FamilyCamera.follow_bounds(
		float(map["worldWidthPx"]), 0.0, PlatformerMaps.BASELINE_Y, VIEW_HEIGHT, false
	)


static func _clamped(scroll: float, bounds: Dictionary) -> float:
	if bounds.is_empty():
		return scroll
	var left := float(bounds["x"])
	var right := maxf(left, left + float(bounds["width"]) - VIEW_WIDTH)
	return clampf(scroll, left, right)


static func _linear(from: float, to: float, t: float) -> float:
	return from + (to - from) * t
