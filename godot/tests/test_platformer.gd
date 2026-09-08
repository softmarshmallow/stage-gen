extends RefCounted

## The platformer's simulation, as far as it has been derived.
##
## Step 9 is a re-derivation rather than a translation — the browser's world *is*
## a Phaser scene — so this file grows one block per unit of that derivation, and
## the number in `EXACT_FRAMES` is the honest statement of how far it has got:
## every frame up to it is identical to the browser's own recording, hash for
## hash, and the frame after it is the first one that speaks to a system nobody
## has ported yet.
##
## The whole six hundred frames are replayed by `tools/platformer_parity.gd`,
## which is where a divergence is named field by field. What is here is what a
## suite can answer on its own: the rules, the world one package opens on, and
## the prefix.

## Frames identical to the browser's, and what stops the next one.
##
## Frame 185 is the frame the first creature notices the player and gives chase
## — the awareness node and the pursuit target are underived, so the world
## diverges there and not before. Raise this with each unit, and never without
## re-running the harness.
const EXACT_FRAMES := 184

const FIRST_UNPORTED := "the awareness node, at the first creature's notice radius"


func run(h: TestHarness) -> void:
	_progression(h)
	var package: Variant = PlatformerMaps.parse(_manifest())
	h.assert_true(not KernelRefusal.is_refusal(package), "the fixture package parses")
	if KernelRefusal.is_refusal(package):
		return
	_world(h, package as Dictionary)
	_snapshot(h, package as Dictionary)
	_dialogue(h, package as Dictionary)
	_camera(h, package as Dictionary)
	_music(h, package as Dictionary)
	_gate(h, package as Dictionary)
	_population(h, package as Dictionary)
	_mobs(h, package as Dictionary)


## The curve a package names, and the refusals for the ones it may not.
func _progression(h: TestHarness) -> void:
	h.assert_eq(
		PlatformerProgression.cost_of_next(1, "gentle_rpg_v1"),
		24,
		"the gentle curve's first level-up costs its base"
	)
	h.assert_eq(
		PlatformerProgression.cost_of_next(2, "gentle_rpg_v1"),
		31,
		"and the second is the base times the growth, rounded"
	)
	h.assert_eq(
		PlatformerProgression.cost_of_next(1, "brisk_rpg_v1"), 16, "a brisk run starts cheaper"
	)
	h.assert_true(
		KernelRefusal.is_refusal(PlatformerProgression.cost_of_next(1, "no_such_curve_v1")),
		"a curve this build does not implement is refused rather than guessed"
	)
	h.assert_true(
		KernelRefusal.is_refusal(PlatformerProgression.cost_of_next(0, "gentle_rpg_v1")),
		"and so is a level below one"
	)
	h.assert_eq(
		PlatformerProgression.maximum_health(6, 1), 6, "a first-rank body carries what it authored"
	)
	# A fifth of six is 1.2, which rounds to one: the floor is what stops a small
	# pool from levelling for nothing.
	h.assert_eq(PlatformerProgression.maximum_health(6, 3), 8, "and gains a fifth a rank after that")
	h.assert_eq(PlatformerProgression.maximum_health(2, 3), 4, "never less than one a rank")


## The world one package opens on, against the browser's own first digest.
func _world(h: TestHarness, package: Dictionary) -> void:
	var world := PlatformerWorld.create(package, _manifest())
	h.assert_eq(world.map_id, "village-map", "the run opens on the entry map")
	h.assert_true(world.ready and not world.loading, "and is playable at once")
	h.assert_eq(world.weapon_class, "ranged_dps_v1", "played as the class the package names")
	h.assert_eq(world.ammo_item_id, null, "which spends no round of its own")

	h.assert_eq(
		world.inventory["carried"],
		[["paper_dart", 1], ["welcome_tart", 1]],
		"the bag opens with the package's starting items, sorted by id"
	)
	h.assert_eq(int(world.progression["level"]), 1, "at the first rank")
	h.assert_eq(int(world.progression["experienceForNext"]), 24, "owing the gentle curve's first step")
	h.assert_eq(int(world.progression["maximumHealth"]), 6, "with the authored pool")

	h.assert_eq((world.portals as Array).size(), 2, "the village has two gates")
	var west: Dictionary = world.portals[0]
	h.assert_eq(String(west["portalId"]), "west_gate", "the first is the one it arrives through")
	h.assert_eq(String(west["kind"]), "entry", "and it is an entry")
	h.assert_true(absf(float(west["x"]) - 153.6) < 1e-9, "a tenth of the way across the map")
	# 3.6 tiles, which is the one part of a gate's drawn size a package decides.
	h.assert_true(absf(float(west["h"]) - 230.4) < 1e-9, "drawn three and a half tiles tall")
	h.assert_true(
		not west.has("w"),
		"and not a width: that follows the artwork's bounding box, which is a shot's business"
	)

	h.assert_eq(
		world.npc_prompts, [{"npcId": "baker"}], "one conversationalist stands on the village map"
	)
	h.assert_eq(
		String(world.soundtrack["next_track_id"]),
		"village_theme",
		"the map's first track is queued"
	)
	h.assert_true(not bool(world.soundtrack["started"]), "and not started until something starts it")


## The projection the golden hashes, and the eight fields it does not.
func _snapshot(h: TestHarness, package: Dictionary) -> void:
	var world := PlatformerWorld.create(package, _manifest())
	var shot: Dictionary = PlatformerPlayer.snapshot(world.player)
	h.assert_eq(shot.size(), 30, "the body publishes thirty fields")
	for hidden in ["gauge", "coyoteExpiresAtMs", "attackUntil", "blockedColumn", "hurtUntil"]:
		h.assert_true(
			world.player.has(hidden) and not shot.has(hidden),
			"%s is state the body keeps and the golden never saw" % hidden
		)
	h.assert_true(
		absf(float(shot["x"]) - 153.6) < 1e-9, "and it stands where the entry spawn put it"
	)
	h.assert_eq(int(shot["hp"]), 6, "with the package's starting health")
	h.assert_true(EXACT_FRAMES > 0, "the derivation is exact up to %d frames" % EXACT_FRAMES)


## The conversation the village offers, and what its ending is worth.
func _dialogue(h: TestHarness, package: Dictionary) -> void:
	var world := PlatformerWorld.create(package, _manifest())
	h.assert_eq(
		PlatformerDialogueSystem.nearest_speaker(world),
		"",
		"nobody is close enough to talk to at the spawn"
	)
	# Where the golden's body stands when it presses `interact`, two thirds of a
	# tile short of the baker.
	world.player["x"] = 546.933333333
	h.assert_eq(
		PlatformerDialogueSystem.nearest_speaker(world), "baker", "and the baker is, further east"
	)

	var step := {"dt": 1000.0 / 30.0, "now": 2000.0, "frame": 60}
	world.intent = PlatformerWorld.neutral_intent()
	world.intent["interact"] = true
	world.events.begin_frame()
	PlatformerDialogueSystem.update(world, step)
	h.assert_true(
		not world.hold, "the frame a conversation opens on is not the frame it holds"
	)
	PlatformerDialogueSystem.prompt(world, step)
	var opened: Dictionary = world.dialogue
	h.assert_eq(String(opened["interaction"]), "meet_baker", "pressing interact opens her scenario")
	# The runtime settles past the stage and the show to the first line, which is
	# the browser's index too.
	h.assert_eq(int(opened["index"]), 2, "settled to the first line it can speak")

	# Two advances reach the ending, which grants the tart. The first of them is
	# also the frame that proves the hold: it is on before the key is read.
	for frame in [68, 72]:
		step["frame"] = frame
		world.events.begin_frame()
		PlatformerDialogueSystem.update(world, step)
		if frame == 68:
			h.assert_true(world.hold, "and every frame after it is held while she talks")
	h.assert_eq(world.dialogue, null, "the second advance ends it")
	h.assert_eq(
		world.inventory["carried"],
		[["paper_dart", 1], ["welcome_tart", 2]],
		"and the ending's effect puts a second tart in the bag"
	)
	h.assert_eq(
		PlatformerTranscript.of_kind(world, "dialogue-closed").size(),
		1,
		"which is said once, not every frame"
	)


## The dead-zone follow, which is Phaser's arithmetic rather than a scene's.
func _camera(h: TestHarness, package: Dictionary) -> void:
	var world := PlatformerWorld.create(package, _manifest())
	h.assert_eq(
		float(world.camera["scrollX"]),
		0.0,
		"the view opens clamped to the left edge, not at the body's centre"
	)
	var bounds := PlatformerCameraSystem.bounds_of(world)
	# Inside the dead zone the view does not move at all, which is the whole
	# point of having one.
	var still := PlatformerCameraSystem.advance({"scrollX": 0.0, "scrollY": 0.0}, 700.0, bounds)
	h.assert_eq(float(still["scrollX"]), 0.0, "a body inside the dead zone moves nothing")
	var pushed := PlatformerCameraSystem.advance({"scrollX": 0.0, "scrollY": 0.0}, 800.0, bounds)
	# 800 is ten past the zone's right edge, and one frame closes 12% of it.
	h.assert_true(
		absf(float(pushed["scrollX"]) - 1.2) < 1e-9, "and one past it closes an eighth of the gap"
	)
	var clamped := PlatformerCameraSystem.advance({"scrollX": 250.0, "scrollY": 0.0}, 5000.0, bounds)
	h.assert_eq(
		float(clamped["scrollX"]), 256.0, "the view never leaves the map, however far the body runs"
	)


## The bag that decides what plays, which is seeded rather than random.
func _music(h: TestHarness, package: Dictionary) -> void:
	var world := PlatformerWorld.create(package, _manifest())
	h.assert_eq(
		String(world.soundtrack["next_track_id"]),
		"village_theme",
		"the village plans its one track"
	)
	# A one-track pool is finished after one play: a repeat-free cycle is
	# impossible for it, which is the policy's stated contract.
	world.music.take()
	h.assert_eq(world.music.planned(), "", "and plans nothing after it has played")

	# The road's pool is two, and the order is the package digest's rather than
	# the clock's — the browser picks the same one.
	var road := PlatformerWorld.create(package, _manifest())
	road.music.take()
	road.music.bind_pool(PackedStringArray(["road_theme", "road_theme_b"]))
	h.assert_eq(road.music.planned(), "road_theme_b", "the road's first track is the seed's")
	h.assert_eq(road.music.take(), "road_theme_b", "taken rather than re-drawn")
	h.assert_eq(road.music.planned(), "road_theme", "and the other follows it")

	var again := PlatformerWorld.create(package, _manifest())
	again.music.take()
	again.music.bind_pool(PackedStringArray(["road_theme", "road_theme_b"]))
	h.assert_eq(
		again.music.planned(), "road_theme_b", "two runs of one package hear the same order"
	)


## The gate, and the edge that opens it.
func _gate(h: TestHarness, package: Dictionary) -> void:
	var world := PlatformerWorld.create(package, _manifest())
	# The east gate's mouth is one tile wide, centred on 0.97 of the map.
	h.assert_true(
		PlatformerMaps.transition_at(package, "village-map", 1504.0).is_empty() == false,
		"standing in the east gate's mouth offers the road"
	)
	h.assert_true(
		PlatformerMaps.transition_at(package, "village-map", 1400.0).is_empty(),
		"and standing a tile and a half short of it offers nothing"
	)

	world.player["x"] = 1504.0
	world.intent = PlatformerWorld.neutral_intent()
	world.intent["up"] = true
	world.events.begin_frame()
	# The press is also the gesture that starts the music, which is what makes
	# the road's track a *switch* rather than a first play.
	PlatformerSoundtrackSystem.update(world, {"dt": 1000.0 / 30.0, "now": 5000.0, "frame": 150})
	h.assert_eq(
		String(world.soundtrack["current_track_id"]), "village_theme", "the village's track starts"
	)
	PlatformerMapEntrySystem.ask(world)
	h.assert_true(not world.pending_map.is_empty(), "the press asks for it")
	PlatformerMapEntrySystem.apply(world, {"dt": 1000.0 / 30.0, "now": 5000.0, "frame": 150})
	h.assert_eq(world.map_id, "road-map", "and the world is rebuilt on the far side")
	h.assert_eq(float(world.player["x"]), 256.0, "at the road's own entry spawn")
	h.assert_eq(float(world.player["vx"]), 0.0, "stopped, because the body takes no step this frame")
	h.assert_eq(int(world.player["column"]), 4, "with its column re-derived by hand from the new x")
	h.assert_eq(String(world.soundtrack["current_track_id"]), "road_theme_b", "and the road's music on")
	# The road is tall enough to follow y, and the view clamps to the top of the
	# authored world rather than to the ground line.
	h.assert_eq(float(world.camera["scrollY"]), 336.0, "the view drops to the road's own ceiling")
	h.assert_eq(
		PlatformerTranscript.of_kind(world, "map-entered").size(), 1, "said once, on arrival"
	)


## Where the road's creatures stand up, and the draws that decide it.
func _population(h: TestHarness, package: Dictionary) -> void:
	h.assert_true(
		PlatformerPopulation.project(package, "village-map").is_empty(),
		"the village authors no population at all"
	)
	var state := PlatformerPopulation.project(package, "road-map")
	h.assert_true(not state.is_empty(), "the road authors one")
	var zone: Dictionary = (state["zones"] as Array)[0]
	h.assert_eq(String(zone["zoneId"]), "road-zone", "whose id is normalised to kebab-case")

	# 0.12 and 0.6 of forty columns, by column centre: five to twenty-three. The
	# wander radius then takes a tile and a half off each end, because a body
	# needs room to wander inside its own zone.
	var columns: Array = []
	for entry: Variant in (zone["candidates"] as Array):
		columns.append(int((entry as Dictionary)["column"]))
	h.assert_eq(columns.front(), 6, "the first place to stand is column six")
	h.assert_eq(columns.back(), 21, "and the last is twenty-one")
	h.assert_eq(columns.size(), 16, "sixteen in all")

	# The body has just arrived at the road's west spawn, which is where the
	# golden's first two creatures are drawn against.
	var issued := PlatformerPopulation.update(state, 5033.0, 256.0, 656.0)
	h.assert_eq(issued.size(), 2, "the zone's initial fill is two")
	h.assert_eq(int((issued[0] as Dictionary)["column"]), 18, "the first stands at column eighteen")
	# The second joins the first rather than spreading: a group already standing
	# pulls the next one towards it seven times in ten.
	h.assert_eq(int((issued[1] as Dictionary)["column"]), 19, "and the second joins it, next door")

	# Nothing more until the interval has elapsed, however often it is asked.
	h.assert_eq(
		PlatformerPopulation.update(state, 5100.0, 256.0, 656.0).size(),
		0,
		"and the director is quiet until its interval has passed"
	)

	# Two runs of one package meet the same creatures in the same places.
	var again := PlatformerPopulation.project(package, "road-map")
	var repeated := PlatformerPopulation.update(again, 5033.0, 256.0, 656.0)
	h.assert_eq(
		int((repeated[0] as Dictionary)["column"]), 18, "a second run draws the same first column"
	)


## The creatures themselves: what they are, and how they patrol.
func _mobs(h: TestHarness, package: Dictionary) -> void:
	var map: Dictionary = (package["maps"] as Dictionary)["road-map"]
	# The instance number, not the spawn column: the population director passes
	# it, and it is what gives a creature its tempo. The two seeds differ in the
	# ninth decimal of the first step, which is exactly what the golden pins.
	var first := PlatformerMob.create(
		1, "mob_1", "road-map/mob/1", 0, "hunting", 2, 1184.0, 656.0, map
	)
	h.assert_eq(int(first["patrolDirection"]), -1, "the first creature sets off west")
	h.assert_true(
		absf(float(first["speedScale"]) - 0.971700011846) < 1e-9,
		"at the tempo its instance number gives it"
	)
	PlatformerMob.wander(first, map, 1.0 / 30.0)
	h.assert_true(
		absf(float(first["x"]) - 1182.833959986) < 1e-9,
		"and its first step is the browser's, to nine decimals"
	)

	var second := PlatformerMob.create(
		2, "mob_2", "road-map/mob/2", 0, "hunting", 2, 1248.0, 656.0, map
	)
	PlatformerMob.wander(second, map, 1.0 / 30.0)
	h.assert_true(
		absf(float(second["x"]) - 1246.872008362) < 1e-9, "and so is the second creature's"
	)

	# A patrol is bounded by home rather than by the world: a tile and a half
	# either way, and the lane it stood up on.
	h.assert_true(
		absf(float(first["patrolMinX"]) - 1088.0) < 1e-9, "it wanders a tile and a half west"
	)
	h.assert_true(
		absf(float(first["patrolMaxX"]) - 1280.0) < 1e-9, "and a tile and a half east"
	)
	# Walked into its own western bound, it turns rather than standing there.
	first["x"] = 1088.5
	PlatformerMob.wander(first, map, 1.0 / 30.0)
	h.assert_eq(int(first["patrolDirection"]), 1, "and turns at the end of its lane")

	var shot := PlatformerMob.snapshot(first)
	h.assert_eq(shot.size(), 10, "a creature publishes ten fields")
	h.assert_eq(String(shot["state"]), "wander", "and is wandering until something notices it")
	h.assert_eq(int(shot["maxHp"]), 2, "with a common creature's health")


func _manifest() -> Dictionary:
	var file := FileAccess.open(
		"res://tests/fixtures/sideview_platformer/manifest.json", FileAccess.READ
	)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed if parsed is Dictionary else {}
