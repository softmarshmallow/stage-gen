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


## The follow, which runs **last**. The browser does not step a camera at all:
## it hands the engine a follow target and the engine moves the view in its own
## pre-render pass, after every system has written whatever it was going to. So
## this is last, and the tremor below is written mid-frame — the follow then
## lerps from a scroll a blow has already nudged, which is what makes a shake
## settle rather than what makes it move.
static func update(world: PlatformerWorld, _step: Dictionary) -> void:
	if world.hold:
		return
	world.camera = advance(
		world.camera, float(world.player["x"]), bounds_of(world), float(world.player["y"])
	)


## Move the view from the tremor it is carrying to this frame's. Called where
## the blows are resolved, not where the follow runs.
static func carry_shake(world: PlatformerWorld, step: Dictionary) -> void:
	if world.hold:
		return
	_carry_shake(world, float(step["now"]))


## Move the view from the tremor it is carrying to this frame's.
##
## Written as a scroll offset rather than as an engine shake, whose direction
## would come from an unseeded draw and differ between two recordings of one run.
## The previous offset comes off before the next goes on, so the nudges never
## accumulate; the follow lerp that runs before the next one pulls a fraction of
## each back towards the target, which is what makes a shake settle rather than
## what makes it move.
static func _carry_shake(world: PlatformerWorld, now_ms: float) -> void:
	var samples: Array = []
	var living: Array = []
	for entry: Variant in world.shakes:
		var source: Dictionary = entry
		var elapsed := now_ms - float(source["startedMs"])
		if elapsed >= float(FamilyShake.KILL["durationMs"]):
			continue
		living.append(source)
		samples.append(
			FamilyShake.sample(
				{
					"seed": source["seed"],
					"elapsedMs": elapsed,
					"dirSign": source["dirSign"],
					"scale": source["scale"],
				},
				FamilyShake.KILL
			)
		)
	world.shakes = living
	var next := FamilyShake.sum(
		samples, float(FamilyShake.KILL["amplitudePx"]) * FamilyShake.CRITICAL_SCALE
	)
	var moved := FamilyCamera.shift_by_shake(world.camera, world.shake_carried, next)
	world.shake_carried = next
	world.camera = moved


## One frame of the follow.
static func advance(
	camera: Dictionary, target_x: float, bounds: Dictionary, target_y: float = 0.0
) -> Dictionary:
	var scroll_x := _axis(
		float(camera["scrollX"]), target_x - FOLLOW_OFFSET_X, VIEW_WIDTH, DEADZONE_WIDTH
	)
	var scroll_y := _axis(
		float(camera["scrollY"]), target_y - FOLLOW_OFFSET_Y, VIEW_HEIGHT, DEADZONE_HEIGHT
	)
	return {
		"scrollX": _clamped(scroll_x, bounds, "x", "width", VIEW_WIDTH),
		"scrollY": _clamped(scroll_y, bounds, "y", "height", VIEW_HEIGHT),
	}


## One axis of the dead-zone follow: the zone sits on the view's midpoint, and
## a target outside it pushes the scroll by however far outside it is.
static func _axis(scroll: float, follow: float, view: float, deadzone: float) -> float:
	var middle := scroll + view / 2.0
	var near := middle - deadzone / 2.0
	var far := middle + deadzone / 2.0
	if follow > far:
		return _linear(scroll, scroll + (follow - far), LERP)
	if follow < near:
		return _linear(scroll, scroll - (near - follow), LERP)
	return scroll


## Where the view lands the moment a map opens: the body centred, then clamped.
##
## Phaser's own snap on follow start is midpoint-based too, so this is what the
## first frame of a map would settle to rather than a place the dead zone would
## then drag the view away from over the following half second.
static func snapped(target_x: float, bounds: Dictionary, target_y: float = 0.0) -> Dictionary:
	return {
		"scrollX": _clamped(target_x - FOLLOW_OFFSET_X - VIEW_WIDTH / 2.0, bounds, "x", "width", VIEW_WIDTH),
		# A map that does not follow y is pinned to zero and then clamped, which
		# is the browser's own two lines: the snap centres both axes and the
		# scene puts y back before the first frame is drawn.
		"scrollY": _clamped(
			target_y - FOLLOW_OFFSET_Y - VIEW_HEIGHT / 2.0, bounds, "y", "height", VIEW_HEIGHT
		),
	}


## The rectangle the view may not leave, for the map the run is on.
static func bounds_of(world: PlatformerWorld) -> Dictionary:
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	var follows_y := bool(map["followsY"])
	# The top of the authored world: the ground line less however many rows of
	# occupancy the map drew above it.
	var top_y := PlatformerMaps.BASELINE_Y - float(map["rows"]) * PlatformerMaps.TILE_PX
	return FamilyCamera.follow_bounds(
		float(map["worldWidthPx"]),
		top_y if follows_y else 0.0,
		PlatformerMaps.BASELINE_Y,
		VIEW_HEIGHT,
		follows_y
	)


static func _clamped(
	scroll: float, bounds: Dictionary, origin: String, span: String, view: float
) -> float:
	if bounds.is_empty():
		return scroll
	var near := float(bounds[origin])
	var far := maxf(near, near + float(bounds[span]) - view)
	return clampf(scroll, near, far)


static func _linear(from: float, to: float, t: float) -> float:
	return from + (to - from) * t
