class_name PlatformerConsumablesSystem
extends RefCounted

## What the bag is spent on: the drink.
##
## A port of the state half of `useHealingItem` in
## `web/lib/sideview-platformer/prepared-scene.ts`, which lives in the scene
## there for no reason except that the scene owns the bag.
##
## **The order is the rule.** The health pool answers first and the bag is only
## opened if it says the restore connected, so a request at full health, or
## while defeated, costs nothing. Doing it the other way round — spend, then
## heal — is how a player loses a potion to a mistimed key press.

## The catalogue role a package marks a drinkable with.
const HEALING_ITEM_KIND := "healing_consumable"


static func declaration() -> KernelSystem:
	return KernelSystem.of(
		{
			"id": "consumables/drink",
			"contract_version": "consumables-system-v1",
			"reads": ["intent", "player"],
			"owns": ["bag", "inventory"],
		}
	)


## Spend one carried drinkable on the body, if it asked and if it would land.
static func drink(world: PlatformerWorld, _step: Dictionary) -> void:
	if world.hold or not bool(world.intent.get("useHealing", false)):
		return
	var item_id := _first_drinkable(world)
	if item_id.is_empty():
		return
	var change := KernelGauge.restore(
		world.player["gauge"],
		FamilyVitals.healing_restore_amount(int(world.player["maxHp"]))
	)
	if not bool(change["connected"]):
		return
	world.player["gauge"] = change["gauge"]
	world.player["hp"] = int(change["after"])
	var spent := FamilyBag.consume(world.bag, item_id, 1)
	if int(spent["moved"]) <= 0:
		return
	world.bag = spent["bag"]
	world.inventory = {"carried": PlatformerWorld.bag_as_pairs(world.bag)}


## The first drinkable the package publishes that the body is actually carrying.
##
## Catalogue order rather than bag order, and the difference matters for a
## package that ships two: which one a key press spends is the author's decision,
## made once when they wrote the catalogue, rather than an accident of whichever
## id happens to sort first.
static func _first_drinkable(world: PlatformerWorld) -> String:
	for entry: Variant in (world.package["items"] as Array):
		var item: Dictionary = entry
		if String(item.get("item_kind", "")) != HEALING_ITEM_KIND:
			continue
		var item_id := String(item.get("item_id", ""))
		if FamilyBag.carried(world.bag, item_id) >= 1:
			return item_id
	return ""
