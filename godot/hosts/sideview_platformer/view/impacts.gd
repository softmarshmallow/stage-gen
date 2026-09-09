class_name PlatformerImpacts
extends Node2D

## The sparks a fight throws: the fan off every blow and the burst off a kill.
##
## World space, drawn over the actors and under the numbers, so a spark sits on
## the creature it came off while the view scrolls. The geometry is
## `PlatformerImpact`'s and the clock is the frame's, so a spark freezes with the
## world during a hitstop rather than running on through it — which is the whole
## reason the hold reads as weight instead of as a dropped frame.
##
## Nothing here is an asset. The generator publishes the actors' strips and no
## effect family exists in the taxonomy yet, so every ray and shard is drawn from
## the blow's own seed. That is also why they replay: two runs of one package
## throw the same sparks.

const SPARK_COLOR := Color(1.0, 0.941, 0.651)
const CRITICAL_SPARK_COLOR := Color(1.0, 1.0, 1.0)
const BURST_COLOR := Color(1.0, 0.965, 0.816)

## Six targets times three blows, twice over, before the oldest is recycled. A
## cap rather than a queue: a burst of kills should cost a bounded amount to
## draw, and the oldest spark is the one nobody is looking at.
const ACTIVE_CAP := 48

const SWING_COLOR := Color(1.0, 0.941, 0.651)
## How wide the glare is at the head of the sweep, as a share of its radius, and
## how many segments the ribbon is built from. Sixteen is enough that a seventy-
## degree arc reads as a curve rather than as a fan of chords.
const SWING_THICKNESS_SHARE := 0.16
const SWING_SEGMENTS := 16

var _live: Array = []
## The swing being drawn, or empty. One at a time, because a body has one arm and
## the controller refuses a fresh action while one is running.
var _swing: Dictionary = {}
var _scroll: Vector2 = Vector2.ZERO
var _now_ms: float = 0.0


static func of() -> PlatformerImpacts:
	var made := PlatformerImpacts.new()
	made.z_index = PlatformerStage.DEPTHS["foreground"] + 10
	return made


## Take this frame's blows. The world hands them over on its own channel — not
## published and not hashed — because a golden records a kill, not the sparks a
## kill throws.
func take(blows: Array, now_ms: float) -> void:
	for entry: Variant in blows:
		var blow: Dictionary = entry
		_live.append(
			{
				"seed": int(blow.get("seed", 0)),
				"x": float(blow["x"]),
				"y": float(blow["y"]),
				"dirSign": int(blow.get("dirSign", 1)),
				"critical": bool(blow.get("critical", false)),
				"died": bool(blow.get("died", false)),
				"startedMs": now_ms,
			}
		)
	while _live.size() > ACTIVE_CAP:
		_live.pop_front()


## The arc the body's own swing has drawn so far.
##
## Read off the attack window rather than raised by an event, because a swing is a
## state the body is in for a tenth of a second and not a thing that happens: the
## same window the blow leaves during is the one the trail is drawn over, so the
## two cannot part company. A throw declares no arc — the round itself is the
## thing to watch, and a blade trail behind it would be a swing nobody made.
func set_swing(world: PlatformerWorld) -> void:
	var weapon := PlatformerWeapon.profile(world.weapon_class)
	if str(weapon["delivery"]) != "instant":
		_swing = {}
		return
	var started := float(world.player.get("attackStarted", 0.0))
	if started <= 0.0:
		_swing = {}
		return
	_swing = {
		"x": float(world.player["x"]),
		# Chest height, where a swing actually passes, rather than at the feet the
		# body's own position is measured from.
		"y": float(world.player["y"]) - PlatformerMaps.TILE_PX,
		"dirSign": -1 if str(world.player["facing"]) == "left" else 1,
		"radius": PlatformerMaps.TILE_PX * float(weapon["reachTiles"]),
		"startedMs": started,
	}


## Advance every spark and retire the ones that are spent.
func sync(scroll: Vector2, now_ms: float) -> void:
	_scroll = scroll
	_now_ms = now_ms
	var standing: Array = []
	for entry: Variant in _live:
		var record: Dictionary = entry
		var elapsed := now_ms - float(record["startedMs"])
		if elapsed < PlatformerImpact.lifetime_ms(bool(record["died"])):
			standing.append(record)
	_live = standing
	queue_redraw()


func _draw() -> void:
	if not _swing.is_empty():
		var arc := PlatformerImpact.swing_arc(
			float(_swing["x"]),
			float(_swing["y"]),
			int(_swing["dirSign"]),
			float(_swing["radius"]),
			_now_ms - float(_swing["startedMs"])
		)
		if not arc.is_empty():
			_draw_glare(arc)
	for entry: Variant in _live:
		var record: Dictionary = entry
		var elapsed := _now_ms - float(record["startedMs"])
		var critical := bool(record["critical"])
		var spark: Color = CRITICAL_SPARK_COLOR if critical else SPARK_COLOR
		for ray_entry: Variant in PlatformerImpact.rays(
			int(record["seed"]),
			float(record["x"]),
			float(record["y"]),
			int(record["dirSign"]),
			critical,
			elapsed
		):
			var ray: Dictionary = ray_entry
			var tint := spark
			tint.a = float(ray["alpha"])
			draw_line(
				Vector2(float(ray["x1"]), float(ray["y1"])) - _scroll,
				Vector2(float(ray["x2"]), float(ray["y2"])) - _scroll,
				tint,
				float(ray["width"])
			)
		for shard_entry: Variant in PlatformerImpact.shards(
			int(record["seed"]),
			float(record["x"]),
			float(record["y"]),
			critical,
			bool(record["died"]),
			elapsed
		):
			var shard: Dictionary = shard_entry
			var tint := BURST_COLOR
			tint.a = float(shard["alpha"])
			draw_circle(
				Vector2(float(shard["x"]), float(shard["y"])) - _scroll,
				float(shard["radius"]),
				tint
			)


## The path a blade has swept, as a ribbon rather than a line.
##
## `draw_arc` gives one stroke at one width and one colour, which is a wire and not
## a glare: the swing read as a thin ring appearing beside the character for four
## frames. What a swing actually leaves is bright and wide at the edge that is
## still moving and thins to nothing behind it — so this is a polygon between two
## radii, tapering and fading toward the tail, and the head carries a hot inner
## core over it.
##
## Built from the same sampled arc; nothing about the geometry is decided here. The
## family says where the sweep has got to and this says what a sweep looks like.
func _draw_glare(arc: Dictionary) -> void:
	var centre := Vector2(float(arc["x"]), float(arc["y"])) - _scroll
	var radius := float(arc["radius"])
	var start := float(arc["startAngle"])
	var finish := float(arc["endAngle"])
	var alpha := float(arc["alpha"])
	var widest := radius * SWING_THICKNESS_SHARE
	var outer := PackedVector2Array()
	var inner := PackedVector2Array()
	var colours := PackedColorArray()
	for step in range(SWING_SEGMENTS + 1):
		var along := float(step) / float(SWING_SEGMENTS)
		var angle := lerpf(start, finish, along)
		var facing := Vector2(cos(angle), sin(angle))
		# The tail is where the blade *was*, so it is both thinner and fainter;
		# squaring the taper keeps the widest part close to the head rather than
		# spreading the ribbon evenly along its length.
		var half := widest * along * along / 2.0
		outer.append(centre + facing * (radius + half))
		inner.append(centre + facing * (radius - half))
		var tint := SWING_COLOR
		tint.a = alpha * along
		colours.append(tint)
	# One ring of points: out along the leading edge and back along the trailing
	# one, so the polygon is the band between the two radii.
	var ribbon := PackedVector2Array()
	var ribbon_colours := PackedColorArray()
	for step in range(outer.size()):
		ribbon.append(outer[step])
		ribbon_colours.append(colours[step])
	for step in range(inner.size() - 1, -1, -1):
		ribbon.append(inner[step])
		ribbon_colours.append(colours[step])
	draw_polygon(ribbon, ribbon_colours)
	# A hot line down the middle of the sweep, so the leading edge reads even where
	# the ribbon is at its thinnest.
	var core := Color(1.0, 1.0, 1.0, alpha * 0.7)
	draw_arc(centre, radius, lerpf(start, finish, 0.55), finish, SWING_SEGMENTS, core, 2.0)
