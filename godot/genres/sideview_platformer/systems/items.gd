class_name PlatformerItemsSystem
extends RefCounted

## What falls out of a creature, and what the body walks over.
##
## Runs after the rounds have been paid out and before the frame ends, so a kill
## lands in the same frame's loot pass rather than a frame later.
##
## The drop pool holds no creature and the pickup holds no item: a drop knows the
## catalogue index it is, and what that index is worth is the manifest's. That is
## what keeps a bag from having an opinion about geometry.

## How near the body has to be. A cheap, forgiving circle, wider than it is tall
## because a player is.
const PICKUP_RADIUS_TILES := 0.9
const PICKUP_HEIGHT_RATIO := 1.5

## Where a stack lands above the corpse that dropped it.
const DROP_RISE_TILES := 1.0


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "items/collect",
			"contract_version": "items-system-v1",
			"reads": ["hold", "player"],
			"owns": ["worldItems"],
			"writes": ["inventory"],
			"emits": ["item-collected"],
		}
	)


## Everything one creature was carrying, popped away from the blow.
##
## The seed is the place it died and which creature it was, so the same kill
## drops the same things in the same places on every replay of the package.
static func drop_loot(world: PlatformerWorld, mob: Dictionary, dir_sign: int) -> void:
	var catalogue: Array = world.package["mobs"]
	var index := int(mob["ladderIndex"])
	if index < 0 or index >= catalogue.size():
		return
	var mob_id := String((catalogue[index] as Dictionary).get("mob_id", ""))
	var seed_value := (
		(
			KernelHash.imul(int(floor(float(mob["x"]))), 2654435761)
			+ KernelHash.imul(index, 2246822519)
		)
		& KernelHash.MASK
	)
	for entry: Variant in FamilyDrop.resolve(world.package["lootRules"], mob_id, seed_value):
		var drop: Dictionary = entry
		var kind := _kind_of(world, String(drop["itemId"]))
		if kind < 0:
			continue
		for offset in FamilyDrop.spread(int(drop["quantity"])):
			world.world_items.append(
				{
					"id": "drop_%d" % world.next_drop_id,
					"kindIndex": kind,
					"body": FamilyDrop.launch(
						float(mob["x"]) + offset,
						float(mob["y"]) - PlatformerMaps.TILE_PX * DROP_RISE_TILES,
						world.next_drop_id,
						dir_sign,
						kind
					),
				}
			)
			world.next_drop_id += 1


## Step every drop, then take whatever the body is standing over.
static func update(world: PlatformerWorld, step: Dictionary) -> void:
	if world.hold:
		return
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	var margin := PlatformerMaps.TILE_PX / 2.0
	var width := float(map["worldWidthPx"])
	for entry: Variant in world.world_items:
		FamilyDrop.step(
			(entry as Dictionary)["body"],
			world.simulation_dt,
			float(step["now"]),
			func(x: float) -> float: return PlatformerMaps.surface_at_x(map, x),
			func(x: float) -> float: return clampf(x, margin, width - margin)
		)
	_collect(world, step)


## The published list, oldest first, as the golden writes it.
static func snapshots(world: PlatformerWorld) -> Array:
	var made: Array = []
	for entry: Variant in world.world_items:
		var item: Dictionary = entry
		var body: Dictionary = item["body"]
		made.append(
			{
				"kindIndex": item["kindIndex"],
				"x": body["x"],
				"y": body["y"],
				"settled": body["settled"],
			}
		)
	return made


## Which drops the body is standing over, taken and removed.
##
## Handed over back to front, because that is the order the array-splicing loop
## this replaces took them in: two drops taken on one frame are two events, and
## which comes first is what a replay hashes.
static func _collect(world: PlatformerWorld, step: Dictionary) -> void:
	if world.world_items.is_empty():
		return
	var radius := PlatformerMaps.TILE_PX * PICKUP_RADIUS_TILES
	var player_x := float(world.player["x"])
	var player_y := float(world.player["y"])
	var candidates: Array = []
	for index in range(world.world_items.size() - 1, -1, -1):
		candidates.append(world.world_items[index])
	var verdict := FamilyLoot.collect_drops(
		candidates,
		func(drop: Variant) -> String: return String((drop as Dictionary)["id"]),
		{},
		{},
		func(_drop: Variant) -> bool: return false,
		func(drop: Variant) -> bool:
			var body: Dictionary = (drop as Dictionary)["body"]
			return (
				absf(float(body["x"]) - player_x) < radius
				and absf(float(body["y"]) - player_y) < radius * PICKUP_HEIGHT_RATIO
			)
	)
	for entry: Variant in (verdict["taken"] as Array):
		var drop: Dictionary = entry
		world.world_items.erase(drop)
		var item_id := _item_id(world, int(drop["kindIndex"]))
		if item_id.is_empty():
			continue
		var change := FamilyBag.grant(world.bag, item_id, 1, FamilyBag.UNLIMITED)
		world.bag = change["bag"]
		world.inventory = {"carried": PlatformerWorld.bag_as_pairs(world.bag)}
		PlatformerTranscript.record(
			world, "item-collected", int(step["frame"]), float(step["now"]), {"itemId": item_id}
		)


static func _kind_of(world: PlatformerWorld, item_id: String) -> int:
	var catalogue: Array = world.package["items"]
	for index in range(catalogue.size()):
		if String((catalogue[index] as Dictionary).get("item_id", "")) == item_id:
			return index
	return -1


static func _item_id(world: PlatformerWorld, kind: int) -> String:
	var catalogue: Array = world.package["items"]
	if kind < 0 or kind >= catalogue.size():
		return ""
	return String((catalogue[kind] as Dictionary).get("item_id", ""))
