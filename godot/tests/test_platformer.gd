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
## Frame 60 is the first press of `interact`, which opens the baker's
## conversation — `dialogue/input` and the scenario it plays are unported, so the
## world diverges there and not before. Raise this with each unit, and never
## without re-running the harness.
const EXACT_FRAMES := 59

const FIRST_UNPORTED := "dialogue/input, at the baker's conversation"


func run(h: TestHarness) -> void:
	_progression(h)
	var package: Variant = PlatformerMaps.parse(_manifest())
	h.assert_true(not KernelRefusal.is_refusal(package), "the fixture package parses")
	if KernelRefusal.is_refusal(package):
		return
	_world(h, package as Dictionary)
	_snapshot(h, package as Dictionary)


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


func _manifest() -> Dictionary:
	var file := FileAccess.open(
		"res://tests/fixtures/sideview_platformer/manifest.json", FileAccess.READ
	)
	if file == null:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	return parsed if parsed is Dictionary else {}
