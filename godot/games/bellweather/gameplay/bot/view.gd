class_name PlatformerBotView
extends RefCounted

## Perception — the world as the bot is allowed to know it.
##
## A port of `web/lib/sideview-platformer/bot-view.ts`. The view is a plain
## snapshot with no engine objects in it, and that restriction is doing real work:
## a behaviour that could reach into the host would quietly grow a dependency on a
## sprite's private fields, while one that can only read this record stays a
## function of its inputs. Everything host-shaped is confined to the adapter that
## fills this in.
##
## The view is also the honest boundary of the bot's knowledge. If something is
## not here, the bot cannot cheat by consulting it — which is why mob health is
## present (it is drawn above their heads) and mob spawn timers are not.
##
## The record is
## `{nowMs, deltaMs, self, threats, pickups, healingCarried, ammoCarried,
##   weaponBand, combatEnabled, navigation, terrain, bounds}`; `self` is
## `{x, y, facing, vx, vy, airborne, support, airJumpsUsed, hp, maxHp, defeated,
##   attacking}`, with `y` at the feet, matching every other vertical value the
## runtime reports.

const FACING_LEFT := "left"
const FACING_RIGHT := "right"


static func health_fraction(self_view: Dictionary) -> float:
	var max_hp := float(self_view["maxHp"])
	if max_hp <= 0.0:
		return 0.0
	return clampf(float(self_view["hp"]) / max_hp, 0.0, 1.0)


static func horizontal_distance(a: Dictionary, b: Dictionary) -> float:
	return absf(float(a["x"]) - float(b["x"]))


## Whether two feet stand close enough in height to trade blows.
##
## Combat in this runtime is resolved on foot level rather than on overlapping
## bodies, so a mob one deck up is not a mob the character can hit no matter how
## close it looks on screen. Targeting respects the same rule the damage does,
## otherwise the bot swings at the ceiling.
static func same_foot_level(a: Dictionary, b: Dictionary, tolerance_units: float) -> bool:
	return absf(float(a["y"]) - float(b["y"])) <= tolerance_units


## Whether a flat shot from one point to another would reach, or hit the ground on
## the way.
##
## The rule the projectile itself obeys, asked one frame early: a shot dies where
## its own height meets the terrain surface, so a straight line at the release
## height either clears every column between the two or it does not. Sampled per
## column, because the terrain is per column and a midpoint test would fly
## straight through a one-column pillar.
##
## This exists because of a real softlock. Targeting used to ask only how far away
## a creature was and how close its feet were; a creature standing on a ledge
## satisfied both while the ledge face stood between them, so every throw died in
## the wall and the engage behaviour — which outranks pursuit — proposed the same
## throw forever. Declining is what lets pursuit take the frame and walk the
## character somewhere it can actually shoot from.
##
## The character's own column is skipped: it is standing on that ground, not
## shooting through it.
static func line_of_fire_clear(
	terrain: Dictionary, from_x: float, to_x: float, flight_y: float
) -> bool:
	var surfaces: PackedFloat64Array = terrain["columnSurfaceY"]
	var tile_units := float(terrain["tileUnits"])
	# A host that reports no terrain blocks nothing. Refusing every shot would be
	# worse than the defect this prevents.
	if surfaces.is_empty() or tile_units <= 0.0:
		return true
	var first := int(floor(minf(from_x, to_x) / tile_units))
	var last := int(floor(maxf(from_x, to_x) / tile_units))
	var standing := int(floor(from_x / tile_units))
	for column in range(first, last + 1):
		if column == standing:
			continue
		var index := clampi(column, 0, surfaces.size() - 1)
		# y grows downward, so the shot is in the air only while it is above the
		# surface.
		if flight_y >= surfaces[index]:
			return false
	return true


## Facing sign toward a point, with the current facing kept when already on top of
## it.
static func facing_toward(self_view: Dictionary, target_x: float) -> String:
	if target_x < float(self_view["x"]):
		return FACING_LEFT
	if target_x > float(self_view["x"]):
		return FACING_RIGHT
	return String(self_view["facing"])
