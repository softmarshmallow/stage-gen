class_name SurvivalWorldFactory
extends RefCounted

## Game composition loads plates once; simulation receives decoded masks.
static func create(pkg: HostRunDir, seed_value: int, options: Dictionary = {}) -> SurvivalWorld:
	var prepared := options.duplicate()
	if not prepared.get("masks") is SurvivalMasks:
		prepared["masks"] = SurvivalMaskLoader.from_package(pkg)
	return SurvivalWorld.create(pkg, seed_value, prepared)
