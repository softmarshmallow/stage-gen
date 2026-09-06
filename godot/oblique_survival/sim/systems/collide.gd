class_name SysCollide
extends RefCounted

## Reads `player`, writes `collision`. viewer/index.html 1097-1112.
##
## One pass over every footprint in list order: no mass, no sliding, no
## iteration. Forage and dropped items carry radius 0 and are skipped.


static func update(world: World, _dt: float) -> void:
	Targeting.push_out_of_footprints(world, world.player)
