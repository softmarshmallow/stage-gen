class_name PlatformerMobBars
extends Node2D

## A small gauge under every creature that has been hurt.
##
## World space, not screen furniture: it scrolls and zooms with the camera, and
## it hangs from the creature's own foot line rather than from the bottom of its
## drawn art. It is drawn above the near foreground so a readout is not hidden
## behind the foliage its owner walks through, and above every other creature so
## bodies do not occlude each other's.
##
## **Never at spawn.** A creature starts undamaged, and an undamaged creature has
## nothing to report. The bar arrives with the first point of damage and leaves
## at the killing blow — explicitly, before the death strip and before any fade,
## so a corpse never drags a gauge down with it.
##
## Two gates, deliberately not merged: `is it damaged` and `is it alive`. The
## first is true at zero health, which is why the second exists.

## The capsule every creature gets, whatever it is. A boss draws half again as
## tall and gets the same bar: the size is what keeps "how is that one doing"
## from competing with "how am I doing".
const BAR_SIZE := Vector2(46.0, 5.0)

## How far below the foot line the bar's centre sits.
const FOOT_GAP := 8.0

var _bars: Dictionary = {}


static func of() -> PlatformerMobBars:
	var made := PlatformerMobBars.new()
	made.z_index = PlatformerStage.DEPTHS["foreground"] + 10
	return made


func sync(world: PlatformerWorld, scroll: Vector2) -> void:
	var seen := {}
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		var id := str(mob.get("instanceId", ""))
		if id.is_empty():
			# A creature the director has forgotten still has a body; it keeps
			# whatever bar it had until the body itself is gone.
			id = "%s@%d" % [mob["botId"], int(mob["ladderIndex"])]
		seen[id] = true
		if not _bars.has(id):
			var made := HostGaugeBar.of(BAR_SIZE.x, BAR_SIZE.y)
			_bars[id] = made
			add_child(made)
		var bar: HostGaugeBar = _bars[id]
		bar.visible = _shown(mob)
		if not bar.visible:
			continue
		bar.show_gauge(float(mob["hp"]), float(mob["maxHp"]), false)
		# The widget's sprites are drawn from their top-left, and the placement
		# the browser publishes is the capsule's centre.
		bar.position = Vector2(
			float(mob["x"]) - scroll.x - BAR_SIZE.x / 2.0,
			float(mob["y"]) - scroll.y + FOOT_GAP - BAR_SIZE.y / 2.0
		)
	for id: Variant in _bars.keys():
		if not seen.has(id):
			(_bars[id] as Node).queue_free()
			_bars.erase(id)


## Alive, and hurt. Anything else shows nothing.
static func _shown(mob: Dictionary) -> bool:
	if not bool(mob["alive"]):
		return false
	var maximum := float(mob["maxHp"])
	if maximum <= 0.0:
		return false
	return float(mob["hp"]) < maximum
