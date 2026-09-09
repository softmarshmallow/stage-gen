class_name PlatformerBodyBars
extends Node2D

## A small gauge under every body: the player's own, and every creature that has
## been hurt.
##
## World space, not screen furniture: it scrolls and zooms with the camera, and
## it hangs from the body's own foot line rather than from the bottom of its drawn
## art. It is drawn above the near foreground so a readout is not hidden behind the
## foliage its owner walks through, and above every other creature so bodies do not
## occlude each other's.
##
## **The player's belongs here and not in a corner.** It was drawn as a
## three-hundred-pixel bar pinned to the top left, which is a different game's
## interface: this one is read at the body, where the eye already is during a
## fight, and a readout across the room is a readout nobody looks at while
## something is hitting them. The player's capsule is deliberately larger than a
## creature's — several are on screen at once and one of them is the player's own,
## so the size difference is what keeps "how am I doing" separable from "how is
## that one doing" without colour-coding the two apart and losing the spectrum.
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
const PLAYER_BAR_SIZE := Vector2(72.0, 8.0)

## How far below the foot line the bar's centre sits.
const FOOT_GAP := 8.0
const PLAYER_FOOT_GAP := 11.0

var _bars: Dictionary = {}
var _player: HostGaugeBar = null


static func of() -> PlatformerBodyBars:
	var made := PlatformerBodyBars.new()
	made.z_index = PlatformerStage.DEPTHS["foreground"] + 10
	return made


func sync(world: PlatformerWorld, scroll: Vector2) -> void:
	_sync_player(world, scroll)
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


## The player's own, under their feet and always up.
##
## Always, unlike a creature's: a creature at full health has nothing to report and
## a bar over every idle body is noise, but the player's own health is the one
## number they are steering by and it should not appear only once it is too late to
## act on.
func _sync_player(world: PlatformerWorld, scroll: Vector2) -> void:
	if _player == null:
		_player = HostGaugeBar.of(PLAYER_BAR_SIZE.x, PLAYER_BAR_SIZE.y)
		add_child(_player)
	_player.visible = not bool(world.player.get("defeated", false))
	if not _player.visible:
		return
	_player.position = Vector2(
		float(world.player["x"]) - scroll.x - PLAYER_BAR_SIZE.x / 2.0,
		float(world.player["y"]) - scroll.y + PLAYER_FOOT_GAP
	)
	_player.show_gauge(
		float(world.player["hp"]),
		float(world.player["maxHp"]),
		bool(world.player.get("invulnerable", false))
	)
