class_name PlatformerBotAdapter
extends RefCounted

## The adapter — the one place the world and the bot are allowed to meet.
##
## A port of `web/lib/sideview-platformer/bot-adapter.ts`. Everything under
## `bot/` is written against plain values, and this file is what makes that
## affordable: it reads the world's own vocabulary — heightmap columns, upper
## platforms, climbable zones, a body, a bag — and produces the navigation graph
## and the world view. Porting the bot to another runtime means rewriting this file
## and nothing else beneath it.
##
## The direction of the dependency matters. The bot never reaches into the world;
## the world fills the bot's inputs. That is what keeps the bot testable without a
## host, and what stops a behaviour from quietly learning about a sprite.

## The class that declares no flight path, and therefore has no line of fire to
## test. Negative rather than null: GDScript has no nullable float, and a release
## height below the feet is outside every real one.
const NO_RELEASE_HEIGHT := -1.0


## Resolved standing surface for every terrain column, left to right.
static func column_surfaces(terrain: Dictionary) -> PackedFloat64Array:
	var made := PackedFloat64Array()
	var tile_px := float(terrain["tilePx"])
	var baseline_y := float(terrain["baselineY"])
	for height: Variant in (terrain["heights"] as Array):
		made.append(PlatformerVertical.terrain_surface_y(int(height), tile_px, baseline_y))
	return made


## Build the traversal graph for the map the world has just entered.
##
## Called on map entry rather than per frame. The graph describes terrain and
## declared geometry, neither of which changes while a map is being played, and
## rebuilding it every frame would spend a jump proof per link on an answer that
## cannot have moved.
static func nav_graph(terrain: Dictionary, capabilities: Dictionary) -> Dictionary:
	var platforms: Array = []
	for entry: Variant in (terrain["platforms"] as Array):
		var platform: Dictionary = entry
		platforms.append(
			{
				"id": platform["id"],
				"left": platform["left"],
				"right": platform["right"],
				"deckY": platform["deckY"],
			}
		)
	var climbables: Array = []
	for entry: Variant in (terrain["climbables"] as Array):
		var zone: Dictionary = entry
		climbables.append(
			{
				"id": zone["id"],
				"centerX": zone["centerX"],
				"upperDeckY": zone["upperDeckY"],
				"lowerSurfaceY": zone["lowerSurfaceY"],
			}
		)
	return FamilyNavGraph.build(
		{
			"columnSurfaceY": column_surfaces(terrain),
			"tileUnits": float(terrain["tilePx"]),
			"platforms": platforms,
			"climbables": climbables,
			"capabilities": capabilities,
		}
	)


## Project a weapon class onto the distances the bot reasons in.
##
## Here rather than on the table itself because the tile is the map's constant, not
## the table's, and this file is the one place the two vocabularies are allowed to
## meet. Every number the bot uses to decide where to stand originates in the same
## record the runtime resolves damage from.
static func weapon_band(weapon_class: String) -> Dictionary:
	var weapon := PlatformerWeapon.profile(weapon_class)
	var stand_off: Dictionary = weapon["standOffTiles"]
	var tile := PlatformerMaps.TILE_PX
	# Only a class that actually throws declares a release height, and only then
	# does the flight path exist to be blocked. The height comes from the object
	# rather than from the weapon, for the same reason everything else about the
	# flight does.
	var release := NO_RELEASE_HEIGHT
	if String(weapon["delivery"]) == "projectile":
		release = (
			float(PlatformerProjectiles.FLIGHT["releaseHeightFraction"])
			* PlatformerProjectiles.PLAYER_HEIGHT
		)
	return {
		"minimumUnits": float(stand_off["minimum"]) * tile,
		"approachUnits": float(stand_off["approach"]) * tile,
		"maximumUnits": float(stand_off["maximum"]) * tile,
		"verticalToleranceUnits": float(weapon["verticalTiles"]) * tile,
		# Whether the class spends something to attack, and therefore can run out.
		"requiresAmmo": not String(weapon["ammoKind"]).is_empty(),
		"releaseHeightUnits": release,
	}


## The body as the bot is allowed to know it.
##
## `attacking` reports that the attack animation owns the character, which is
## broader than `attackActive` — that one names the few frames the hit window is
## open. The bot wants the broader fact, because it describes when a swing is
## already under way: a casting character is as committed as a swinging one.
static func self_view(player: Dictionary) -> Dictionary:
	var state := String(player["state"])
	return {
		"x": float(player["x"]),
		"y": float(player["y"]),
		"facing": String(player["facing"]),
		"vx": float(player["vx"]),
		"vy": float(player["vy"]),
		"airborne": bool(player["airborne"]),
		"support": String(player["support"]),
		"airJumpsUsed": int(player["airJumpsUsed"]),
		"hp": int(player["hp"]),
		"maxHp": int(player["maxHp"]),
		"defeated": bool(player["defeated"]),
		"attacking": (
			state == PlatformerPlayer.STATE_ATTACK
			or state == PlatformerPlayer.STATE_RANGED_ATTACK
		),
	}


## Live mobs only. A corpse is not a target and never reaches the bot.
static func threats(world: PlatformerWorld) -> Array:
	var made: Array = []
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		if not bool(mob["alive"]):
			continue
		made.append(
			{
				"id": String(mob["botId"]),
				"x": float(mob["x"]),
				"y": float(mob["y"]),
				"hp": float(mob["hp"]),
			}
		)
	return made


## What is lying on the ground. Unsettled drops are still falling and move as they
## land, which is why the bot is told which is which.
static func pickups(world: PlatformerWorld) -> Array:
	var made: Array = []
	for entry: Variant in world.world_items:
		var item: Dictionary = entry
		var body: Dictionary = item["body"]
		made.append(
			{
				"id": String(item["id"]),
				"x": float(body["x"]),
				"y": float(body["y"]),
				"settled": bool(body["settled"]),
			}
		)
	return made


## Whether the bag holds anything drinkable right now, not whether the package
## ships one.
static func healing_carried(world: PlatformerWorld) -> bool:
	for entry: Variant in (world.package["items"] as Array):
		var item: Dictionary = entry
		if String(item.get("item_kind", "")) != PlatformerConsumablesSystem.HEALING_ITEM_KIND:
			continue
		if FamilyBag.carried(world.bag, String(item.get("item_id", ""))) >= 1:
			return true
	return false


## Whether the bag holds a round right now. Always true for a class that spends
## nothing, which is what keeps a swinging body from declining every attack.
static func ammo_carried(world: PlatformerWorld) -> bool:
	if world.ammo_item_id == null:
		return true
	return FamilyBag.carried(world.bag, String(world.ammo_item_id)) >= 1


## Everything one frame of thought is given.
##
## `terrain` is `PlatformerFrame.terrain(world)` and `navigation` the graph built
## from it on map entry — both handed in rather than derived here, because the
## caller already holds the first and rebuilding the second per frame would spend a
## jump proof per link on an answer that cannot have moved.
static func world_view(
	world: PlatformerWorld,
	terrain: Dictionary,
	navigation: Dictionary,
	now_ms: float,
	delta_ms: float
) -> Dictionary:
	return {
		"nowMs": now_ms,
		"deltaMs": delta_ms,
		"self": self_view(world.player),
		"threats": threats(world),
		"pickups": pickups(world),
		"healingCarried": healing_carried(world),
		"ammoCarried": ammo_carried(world),
		"weaponBand": weapon_band(world.weapon_class),
		# False for a package with combat disabled, which makes every fighting
		# behaviour decline.
		"combatEnabled": bool(terrain["combatEnabled"]),
		"navigation": navigation,
		# What the ground does between here and there. The navigation graph is
		# built from the same profile but cannot answer this question: its nodes are
		# walkable spans, and a projectile does not care where a character could
		# stand — it cares what is in the way at the height it is flying.
		"terrain": {
			"columnSurfaceY": column_surfaces(terrain),
			"tileUnits": float(terrain["tilePx"]),
		},
		# Walkable extent of the current map, which is what keeps a patrol on the
		# map.
		"bounds": {"left": 0.0, "right": float(terrain["worldWidthPx"])},
	}
