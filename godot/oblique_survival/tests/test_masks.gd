extends RefCounted

## The ground plates read back as data. The expected answers were computed
## independently from the same PNGs (Pillow, the same arithmetic as the
## viewer's canvas read-back), so this is a cross-check, not a tautology.

func run(h: TestHarness) -> void:
	var pkg := h.package()
	if not h.assert_true(pkg != null, "full-v66 did not open"):
		return
	var masks := Masks.from_package(pkg)
	h.assert_near(masks.size, 256.0, 1e-9, "mask world size")

	# The camp and the player's spawn are on land; so is the clearing around
	# them (0.7 m of erosion at 1024 cells over 256 m is a 3-cell inset).
	var camp: Dictionary = pkg.layout.get("camp_position", {})
	h.assert_true(
		masks.is_land(float(camp.get("x", 0.0)), float(camp.get("z", 0.0))),
		"the camp is not land",
	)
	var spawn: Dictionary = pkg.layout.get("player_spawn", {})
	h.assert_true(
		masks.is_land(float(spawn.get("x", 0.0)), float(spawn.get("z", 0.0))),
		"the player spawn is not land",
	)

	# The far corner of the plate is open water, and outside the plate is water
	# too: the mask reads out of bounds as not land.
	h.assert_false(masks.is_land(-125.0, -125.0), "the south-west corner is not water")
	h.assert_false(masks.is_land(125.0, 125.0), "the north-east corner is not water")
	h.assert_false(masks.is_land(200.0, 200.0), "out of bounds is not water")

	# Friction comes from the biome under the point: the base biome around the
	# camp, and a dry-meadow patch out in the north-west.
	h.assert_eq(masks.biome_at(0.0, 0.0), "forest_floor", "biome at the camp")
	h.assert_near(masks.friction_at(0.0, 0.0), 0.7, 1e-6, "friction on the base biome")
	h.assert_eq(masks.biome_at(-30.0, 40.0), "dry_meadow", "biome at (-30, 40)")
	h.assert_near(masks.friction_at(-30.0, 40.0), 0.55, 1e-6, "friction on dry meadow")

	# Every biome the manifest declares must be reachable through a channel.
	var biomes: Dictionary = pkg.manifest.get("ground", {}).get("biomes", {})
	for id: String in biomes.keys():
		var friction: float = float(biomes[id].get("friction", -1.0))
		h.assert_true(friction > 0.0, "%s has no friction" % id)

	# A world with no plates walks anywhere, at the default friction — what the
	# viewer had until its splat resolved, and what a run with no coast gets.
	var bare := Masks.new()
	h.assert_true(bare.is_land(9999.0, -9999.0), "a run with no splat is not all land")
	h.assert_near(bare.friction_at(0.0, 0.0), Masks.DEFAULT_FRICTION, 1e-9, "default friction")
	h.assert_eq(bare.biome_at(0.0, 0.0), "", "a run with no biome plate named a biome")

	# The world delegates to the masks it was created with, and keeps them
	# across a reset (the viewer lost both on R).
	var world := World.create(pkg, 7, {"masks": masks})
	h.assert_true(world.is_land(0.0, 0.0), "world.is_land disagrees at the camp")
	h.assert_false(world.is_land(-125.0, -125.0), "world.is_land disagrees in the water")
	h.assert_near(world.friction_at(0.0, 0.0), 0.7, 1e-6, "world.friction_at at the camp")
	var next := World.reset(world)
	h.assert_true(next.masks == masks, "a reset dropped the masks")
	h.assert_eq(next.seed, 8, "a reset did not advance the seed")
