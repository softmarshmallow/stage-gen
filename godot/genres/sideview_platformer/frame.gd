class_name PlatformerFrame
extends RefCounted

## One frame of the platformer, in the order the browser ran it.
##
## The sealed roster lands when there are enough systems for a sealer to have an
## opinion about; until then the order is written out, and it is the order
## `assemblePlatformerSystems` declares.
##
## **Why this is one function and not two.** It was two — the host's loop and the
## parity harness's — and a proof against one of them said nothing about the
## other. The harness could have agreed with the browser for six hundred frames
## while the game played a different order, and nothing would have said so. So
## the order lives here, the host ticks it, the harness ticks it, and the pin is
## a claim about the game rather than about a test.


## The ground the body walks on, for the map it is standing in, plus the two
## things about the body that are the package's rather than the map's: how many
## jumps it has in the air, and which strip it climbs on.
static func terrain(world: PlatformerWorld) -> Dictionary:
	var map: Dictionary = (world.package["maps"] as Dictionary)[world.map_id]
	return {
		"heights": map["heights"],
		"tilePx": PlatformerMaps.TILE_PX,
		"baselineY": PlatformerMaps.BASELINE_Y,
		"worldWidthPx": map["worldWidthPx"],
		"platforms": world.platforms,
		"climbables": world.climbables,
		"maximumAirJumps": PlatformerVertical.AIR_JUMPS_MAX,
		"combatEnabled": world.package["combatEnabled"],
		"climbArtwork": world.package["climbArtwork"],
	}


## Step the world once. `step` is `{dt, now, frame}` — milliseconds, milliseconds,
## and the ordinal of this frame counting from one.
static func step(world: PlatformerWorld, step_of: Dictionary) -> void:
	# Both of these live one frame, and both are the caller's business only to the
	# extent that the caller must not forget them — so they are not the caller's
	# business. `blows` is what the interface draws numbers from and `events` is
	# what the systems talk to each other with.
	world.events.begin_frame()
	world.blows = []
	# The conversation before the body, because a held frame is decided before it
	# is spent.
	PlatformerSoundtrackSystem.update(world, step_of)
	PlatformerDialogueSystem.update(world, step_of)
	PlatformerClockSystem.update(world, step_of)
	if world.hold:
		PlatformerMapEntrySystem.apply(world, step_of)
		return
	PlatformerPlayer.update(
		world.player,
		terrain(world),
		world.simulation_dt,
		float(step_of["now"]),
		world.intent,
		PlatformerWeapon.profile(world.weapon_class)
	)
	# Both of these are the scene's in the browser rather than the body's, and both
	# run inside `updatePlayer` between the step and the contact pass: the bag is
	# the scene's to open, so the key that opens it is read where the bag lives.
	PlatformerConsumablesSystem.drink(world, step_of)
	# Defeat outranks the contact pass, and the order is the rule: a recovery
	# rebuilds the world, so the three calls under it would be resolving against a
	# roster that is about to be replaced. The browser says the same thing by
	# returning out of `updatePlayer`.
	# A recovery ends the *player* pass and nothing else. The browser returns out
	# of `updatePlayer` and the rest of its roster still runs, which is what lets
	# the map entry it asked for be taken at the bottom of this same frame.
	if not PlatformerSessionSystem.update(world, step_of):
		# The blow a creature committed on the frame before this one, read here
		# rather than after the creatures move: the browser resolves contact inside
		# `player/update`, so every creature this touches is where it stood at the
		# end of the previous frame. Resolving it a step later lands it a frame
		# early.
		PlatformerMobsSystem.strike(world, step_of)
		# The throw is the last thing `player/update` does, after the blows landing
		# on the body have been settled.
		PlatformerProjectilesSystem.throw_one(world, step_of)
	PlatformerSetPieceSystem.step(world, step_of)
	PlatformerMobsSystem.populate(world, step_of)
	PlatformerMobsSystem.step(world, step_of)
	PlatformerProjectilesSystem.update(world, step_of)
	PlatformerItemsSystem.update(world, step_of)
	PlatformerCameraSystem.carry_shake(world, step_of)
	PlatformerDialogueSystem.prompt(world, step_of)
	PlatformerMapEntrySystem.ask(world)
	PlatformerMapEntrySystem.apply(world, step_of)
	# Last, and deliberately: the browser's camera is the engine's own pre-render
	# pass, which runs after every system has written what it was going to.
	PlatformerCameraSystem.update(world, step_of)
