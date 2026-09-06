class_name SurvivalCollideSystem
extends RefCounted

## Reads `player`, writes `collision`. viewer/index.html 1097-1112.
##
## One pass over every footprint in list order: no mass, no sliding, no
## iteration. Forage and dropped items carry radius 0 and are skipped.


static func update(world: SurvivalWorld, _dt: float) -> void:
	SurvivalTargeting.push_out_of_footprints(world, world.player)
