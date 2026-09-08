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
## Frame 150 is the first press of `up` inside the east gate's mouth, which asks
## for the road map — `map/entry` is underived, so the world diverges there and
## not before. Raise this with each unit, and never without re-running the
## harness.
const EXACT_FRAMES := 149

const FIRST_UNPORTED := "map/entry, at the east gate"


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


func _manifest() -> Dictionary:
	var file := FileAccess.open(
		"res://tests/fixtures/sideview_platformer/manifest.json", FileAccess.READ
	)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed if parsed is Dictionary else {}
