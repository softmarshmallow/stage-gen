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
			var tint := SWING_COLOR
			tint.a = float(arc["alpha"])
			draw_arc(
				Vector2(float(arc["x"]), float(arc["y"])) - _scroll,
				float(arc["radius"]),
				float(arc["startAngle"]),
				float(arc["endAngle"]),
				24,
				tint,
				float(arc["width"])
			)
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
