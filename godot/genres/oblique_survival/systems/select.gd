class_name SurvivalSelectSystem
extends RefCounted

## Reads `input`, writes `selection`. viewer/index.html 1295-1303.


static func update(world: SurvivalWorld, _dt: float) -> void:
	var capacity := SurvivalInventory.slot_capacity(world)
	if world.input["select"] != null:
		world.selected = maxi(0, mini(capacity - 1, int(world.input["select"])))
	var cycle := int(world.input["cycle"])
	if cycle != 0:
		world.selected = (world.selected + cycle + capacity) % capacity
	if world.selected >= capacity:
		world.selected = capacity - 1
	if world.selected < 0:
		world.selected = 0
