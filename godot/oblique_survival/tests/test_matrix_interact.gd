extends RefCounted

## Tier-1 matrix (maps/critique.md D1): T17, T18, T19.
##
## What `test_interact` and `test_drops` leave open: the dead snag's one
## progress look, the felling sign for a tree the player stands east of (the
## branch the camp-facing test never takes), and the drop machine's own
## numbers — the gravity, the single bounce, the settle speed, and the four
## PRNG draws a pickup costs, in their order.

const STEP := 1.0 / 60.0
## `spawnDrops` draws angle, speed, vy, seed — four values, in that order
## (maps/fix-round-notes.md C2; index.html:656-660).
const DRAWS_PER_PICKUP := 4


func run(h: TestHarness) -> void:
	var world := SimFixture.world()
	if world == null:
		h.fail("could not open %s" % TestHarness.RUN_DIR)
		return
	_t17_dead_snag(h, world)
	_t18_fell_sign(h, world)
	_t19_draw_order(h, world)
	_t19_flight(h, world)


# ---------------------------------------------------------------------------
# T17. The dead snag's progress look.
# ---------------------------------------------------------------------------

## `dead_snag` takes two blows with an axe and wears `broken` after the first;
## `moss_boulder`'s three looks are `test_interact`'s.
func _t17_dead_snag(h: TestHarness, world: World) -> void:
	var spec: Dictionary = (world.manifest["props"] as Dictionary)["dead_snag"]
	# The snag lists two interactions; the chop is the first, the axe's.
	var interaction: Dictionary = (spec["interactions"] as Array)[0]
	h.assert_eq(str(interaction["verb"]), "chop", "the snag's first interaction is the chop")
	h.assert_eq(interaction["progress"], ["broken"], "the snag has one progress look")
	h.assert_eq(str(interaction["next_state"]), "stump", "and ends as a stump")

	SimFixture.bare(world)
	world.player.x = 0.0
	world.player.z = 0.0
	world.player.busy = null
	world.player.approach = null
	world.dead = false
	var snag := SimFixture.prop(world, "s1", "dead_snag", "standing", 0.0, 1.0)
	world.entities.append(snag)
	Inventory.inv_add(world, "axe", 1)
	var target: Variant = Targeting.target_for(world, snag)
	h.assert_eq(int((target as Dictionary)["hits"]), 2, "an axe takes the snag in two blows")

	var seen: Array = []
	for _i in 200:
		world.input["interact"] = true
		Sim.step(world, STEP)
		var look := str(snag["state"])
		if seen.is_empty() or str(seen[seen.size() - 1]) != look:
			seen.append(look)
		if look == "stump":
			break
	h.assert_eq(seen, ["standing", "broken", "stump"],
		"the snag did not wear `broken` between the two blows")
	h.assert_eq(SimFixture.events_of(world, "hit").size(), 2, "two blows were struck")
	# The snag authors no regrow: a felled one stays a stump.
	h.assert_eq(interaction.get("regrow_seconds"), null, "the snag authors no regrow")
	h.assert_near(float(snag["regrow"]), 0.0, 1e-9, "and its clock was left at zero")


# ---------------------------------------------------------------------------
# T18. Which way a trunk falls.
# ---------------------------------------------------------------------------

## The trunk topples across the screen, away from the player: the sign is
## `screenRightComponent(awayX, awayZ, yaw) < 0 ? -1 : 1`, and the yield waits
## at `entity + right(yaw) * sign * height * 0.45` until `time + 1.1`.
func _t18_fell_sign(h: TestHarness, world: World) -> void:
	var height := float(((world.manifest["props"] as Dictionary)["pine"] as Dictionary)["height_meters"])
	h.assert_near(height, 5.44, 1e-9, "the pine's authored height")
	h.assert_near(SysInteract.FALL_SECONDS, 1.1, 1e-9, "the fall takes 1.1 s")

	# The player west of the trunk: `away` is +x, the screen right of it is
	# positive, so the sign is +1 and the crown lands east.
	var west := _fell(world, -0.9, 0.0, 0.0, 0.0, 0.0)
	h.assert_near(float(west["sign"]), 1.0, 1e-9, "from the west the trunk falls to screen right")
	h.assert_near(float(west["x"]), height * 0.45, 1e-4, "and the crown lands east of the stump")
	h.assert_near(float(west["z"]), 0.0, 1e-4, "on the trunk's own line")
	h.assert_near(float(west["at"]) - float(west["time"]), 1.1, 1e-9, "the yield waits one fall")

	# The player east of it: `away` is -x, screen right is negative, the sign
	# flips, and the crown lands west. This is the branch a camp-facing test
	# never takes.
	var east := _fell(world, 0.9, 0.0, 0.0, 0.0, 0.0)
	h.assert_near(float(east["sign"]), -1.0, 1e-9, "from the east the trunk falls to screen left")
	h.assert_near(float(east["x"]), -height * 0.45, 1e-4, "and the crown lands west of the stump")

	# A quarter turn of the camera turns the screen with it: at yaw 90 the
	# screen's right is world -z, so a player standing south of the trunk drops
	# the crown north instead of east.
	var turned := _fell(world, 0.0, 0.9, 0.0, 0.0, PI * 0.5)
	h.assert_near(float(turned["sign"]), 1.0, 1e-9, "at yaw 90 the sign is still positive")
	h.assert_near(float(turned["x"]), 0.0, 1e-4, "the crown lands on the camera's right")
	h.assert_near(float(turned["z"]), -height * 0.45, 1e-4, "which at yaw 90 is world -z")

	# The queued yield is the interaction's, and it is released as items when
	# the crown lands, not before.
	var staged := _stage_pine(world, -0.9, 0.0, 0.0, 0.0, 0.0)
	_swing(world, staged)
	h.assert_eq(world.drops.size(), 1, "one yield is queued")
	Sim.advance(world, 1.0)
	h.assert_eq(_items(world).size(), 0, "the yield fell early")
	Sim.advance(world, 0.2)
	h.assert_eq(world.drops.size(), 0, "the queue did not release")
	h.assert_eq(_items(world).size(), 2, "the pine's two logs did not land")


## Chop a pine at (tree_x, tree_z) with the player at (px, pz) and the camera
## at `yaw`; returns the queued drop plus the `fell` event's sign.
func _fell(world: World, px: float, pz: float, tree_x: float, tree_z: float, yaw: float) -> Dictionary:
	var pine := _stage_pine(world, px, pz, tree_x, tree_z, yaw)
	_swing(world, pine)
	var fell := SimFixture.events_of(world, "fell")
	if fell.is_empty() or world.drops.is_empty():
		return {"sign": 0.0, "x": INF, "z": INF, "at": 0.0, "time": 0.0}
	var queued: Dictionary = world.drops[0]
	return {
		"sign": float((fell[0] as Dictionary)["sign"]),
		"x": float(queued["x"]), "z": float(queued["z"]),
		"at": float(queued["at"]), "time": world.time,
	}


func _stage_pine(world: World, px: float, pz: float, tree_x: float, tree_z: float, yaw: float) -> Dictionary:
	SimFixture.bare(world)
	world.camera_yaw = yaw
	world.player.x = px
	world.player.z = pz
	world.player.busy = null
	world.player.approach = null
	world.dead = false
	world.drops.clear()
	var pine := SimFixture.prop(world, "p1", "pine", "grown", tree_x, tree_z)
	world.entities.append(pine)
	Inventory.inv_add(world, "axe", 1)
	return pine


func _swing(world: World, pine: Dictionary) -> void:
	for _i in 400:
		world.input["interact"] = true
		Sim.step(world, STEP)
		if str(pine["state"]) == "stump":
			break
	world.input["interact"] = false


func _items(world: World) -> Array:
	var found: Array = []
	for entity: Dictionary in world.entities:
		if str(entity.get("kind", "")) == "item":
			found.append(entity)
	return found


# ---------------------------------------------------------------------------
# T19. The drop machine.
# ---------------------------------------------------------------------------

## Four draws a pickup, in the order angle, speed, vy, seed. Drawing three
## (which `maps/viewer-sim.md` claimed) would desynchronise every stream after
## the first drop, so the order is checked value by value against an
## independent generator on the same seed.
func _t19_draw_order(h: TestHarness, world: World) -> void:
	SimFixture.bare(world)
	# `drop_count` is the counter behind the `i1, i2, …` ids and survives a
	# cleared stage; the earlier felling in this file has already spent some.
	world.drop_count = 0
	world.rng = Mulberry32.new(4242)
	world.rand = Callable(world.rng, "next")
	var reference := Mulberry32.new(4242)
	var angle := (reference.next() - 0.5) * 1.6
	var speed := 1.2 + reference.next() * 1.7 * 1.3
	var vy := 2.4 + reference.next() * 1.0
	var seed_value := int(reference.next() * 1e5)

	SysDrops.spawn_drops(world, [{"item_id": "log", "count": 1}], 3.0, -4.0, 1.0, 0.0, 1.7)
	if not h.assert_eq(world.entities.size(), 1, "one log was thrown"):
		return
	var item: Dictionary = world.entities[0]
	# dir (1, 0) rotated by `angle` is (cos, sin) of it.
	h.assert_near(float(item["vx"]), cos(angle) * speed, 1e-9, "the first draw is the angle")
	h.assert_near(float(item["vz"]), sin(angle) * speed, 1e-9, "the second is the speed")
	h.assert_near(float(item["vy"]), vy, 1e-9, "the third is the upward kick")
	h.assert_eq(int(item["seed"]), seed_value, "the fourth is the card's seed")
	# ...and exactly four, so the next draw on both sides is the same.
	h.assert_near(float(world.rand.call()), reference.next(), 1e-12,
		"a pickup cost something other than four draws")

	# The rest of the shape: it starts a hand above the ground, unsettled.
	h.assert_eq(str(item["id"]), "i1", "the first drop is i1")
	h.assert_near(float(item["x"]), 3.0, 1e-9, "it starts where it was thrown from")
	h.assert_near(float(item["z"]), -4.0, 1e-9, "on both axes")
	h.assert_near(float(item["y"]), 0.35, 1e-9, "a hand above the ground")
	h.assert_eq(bool(item["settled"]), false, "and it is still in the air")
	h.assert_eq(bool(item["grounded"]), false, "with nothing under it yet")

	# A count of four costs four times as many draws, one pickup at a time.
	var before := world.rng._state
	SysDrops.spawn_drops(world, [{"item_id": "log", "count": 4}], 0.0, 0.0, 1.0, 0.0, 1.0)
	var counted := Mulberry32.new(0)
	counted._state = before
	for _i in DRAWS_PER_PICKUP * 4:
		counted.next()
	h.assert_eq(world.rng._state, counted._state, "four logs did not cost sixteen draws")
	h.assert_eq(world.entities.size(), 5, "four more logs are on the ground")
	h.assert_eq(str((world.entities[4] as Dictionary)["id"]), "i5", "the ids run on")


## Gravity, the one bounce, the slide and the settle, each measured on its own.
func _t19_flight(h: TestHarness, world: World) -> void:
	h.assert_near(SysDrops.DROP_GRAVITY, 26.0, 1e-9, "the cartoon gravity")
	h.assert_near(SysDrops.DROP_RESTITUTION, 0.28, 1e-9, "the bounce coefficient")
	h.assert_near(SysDrops.SLIDE_GRAVITY, 9.81, 1e-9, "the g the slide brakes against")
	h.assert_near(SysDrops.DROP_SETTLE_SPEED, 0.06, 1e-9, "the settle speed")

	# Gravity: one step off the ground costs 26 m/s of upward speed a second.
	SimFixture.bare(world)
	var flying := _item(world, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0)
	SysDrops.update(world, STEP)
	h.assert_near(float(flying["vy"]), -SysDrops.DROP_GRAVITY * STEP, 1e-9, "one step of gravity")
	h.assert_near(float(flying["y"]), 2.0 - SysDrops.DROP_GRAVITY * STEP * STEP, 1e-9,
		"and the fall it bought")

	# A hard landing bounces once: the upward speed reverses and is damped, and
	# the sideways speed is cut to 0.55 of itself. It is not grounded yet.
	SimFixture.bare(world)
	var hard := _item(world, 0.0, 0.0, 0.001, 2.0, 1.0, -6.0)
	SysDrops.update(world, STEP)
	h.assert_near(float(hard["y"]), 0.0, 1e-9, "the hard landing reached the ground")
	h.assert_near(float(hard["vy"]), (-6.0 - SysDrops.DROP_GRAVITY * STEP) * -SysDrops.DROP_RESTITUTION,
		1e-9, "the bounce reverses and damps the fall")
	h.assert_near(float(hard["vx"]), 2.0 * 0.55, 1e-9, "and takes 45% off the sideways speed")
	h.assert_near(float(hard["vz"]), 1.0 * 0.55, 1e-9, "on both axes")
	h.assert_eq(bool(hard["grounded"]), false, "a bouncing drop is not down yet")

	# A soft landing does not bounce at all: it is down, and starts to slide.
	SimFixture.bare(world)
	var soft := _item(world, 0.0, 0.0, 0.001, 2.0, 0.0, -1.5)
	SysDrops.update(world, STEP)
	h.assert_near(float(soft["vy"]), 0.0, 1e-9, "a soft landing does not bounce")
	h.assert_eq(bool(soft["grounded"]), true, "it is down for good")
	h.assert_near(float(soft["vx"]), 2.0, 1e-9, "with its sideways speed intact")

	# The settle: a slide under the settle speed stops on the spot, and the
	# age is reset so a magnet run would wait its beat from here.
	SimFixture.bare(world)
	var crawling := _item(world, 0.0, 0.0, 0.0, 0.05, 0.0, 0.0)
	crawling["grounded"] = true
	crawling["age"] = 9.0
	SysDrops.update(world, STEP)
	h.assert_eq(bool(crawling["settled"]), true, "0.05 m/s is under the settle speed")
	h.assert_near(float(crawling["vx"]), 0.0, 1e-9, "and the speed is dropped")
	h.assert_near(float(crawling["age"]), 0.0, 1e-9, "the age restarts when it settles")

	# The brake itself is `friction * 9.81 * dt`, taken from under the drop.
	SimFixture.bare(world)
	var sliding := _item(world, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0)
	sliding["grounded"] = true
	var friction := world.friction_at(0.0, 0.0)
	h.assert_near(friction, 0.7, 1e-6, "the camp is forest floor")
	SysDrops.update(world, STEP)
	h.assert_near(float(sliding["vx"]), 3.0 - friction * SysDrops.SLIDE_GRAVITY * STEP, 1e-9,
		"one step of the biome's brake")


func _item(world: World, x: float, z: float, y: float, vx: float, vz: float, vy: float) -> Dictionary:
	var item := {
		"id": "i0", "kind": "item", "item_id": "log",
		"x": x, "z": z, "y": y, "vx": vx, "vz": vz, "vy": vy,
		"settled": false, "grounded": false, "age": 0.0, "radius": 0.0,
		"seed": 0, "uses": null, "taken": false, "pulled": false, "dirty": false,
	}
	world.entities.append(item)
	return item
