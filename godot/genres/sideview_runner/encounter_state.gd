class_name RunnerEncounterState
extends RefCounted

## A boss fight's state and the arithmetic that shapes it, apart from the system
## that drives it.
##
## A port of `web/lib/sideview-runner/encounter-arithmetic.ts`. It is split from
## the system for the same reason the browser split it: every function here is
## pure and testable without a world, and the fight's feel lives in constants
## somebody can read rather than in the middle of a state machine.

## How the boss closes, and how it leaves.
const APPROACH_COLUMNS_PER_SECOND := 5.0
const RETREAT_COLUMNS_PER_SECOND := 8.0
## How long an attack pose holds before the boss returns to hovering.
const ATTACK_POSE_SECONDS := 0.35
## How long a hit reads on the boss.
const HIT_FLASH_MS := 64.0
## The share of its height a boss is wide, when no atlas has been measured.
const HALF_WIDTH_FRACTION := 0.35
## Shots in flight at once. A cap rather than a queue: a fight that would spawn
## more than this has a period somebody mis-authored.
const SHOT_CAP := 32
const BOB_ROWS := 0.18
const BOB_PERIOD_SECONDS := 2.4

const PHASE_IDLE := "idle"
const PHASE_ARENA_PENDING := "arena_pending"
const PHASE_CUT_IN := "cut_in"
const PHASE_BATTLE := "battle"
const PHASE_RETREAT := "retreat"
const PHASE_COOLDOWN := "cooldown"

## The phases during which the director wants the arena chunk placed.
const WANTS_ARENA := [PHASE_ARENA_PENDING, PHASE_CUT_IN, PHASE_BATTLE, PHASE_RETREAT]


static func create(binding: Dictionary) -> Dictionary:
	return {
		"phase": PHASE_IDLE,
		"phaseStartedAt": null,
		"nextArenaAtColumn": float(binding["intervalColumns"]),
		"encounterIndex": 0,
		"boss": {},
		"shots": [],
		"nextShotId": 0,
		"salvosFired": 0,
		"nextSalvoAt": null,
		"nextPlayerShotAt": null,
		"laneSeed": 0,
		"outcome": null,
	}


static func wants_arena(state: Dictionary) -> bool:
	if state.is_empty():
		return false
	return WANTS_ARENA.has(String(state["phase"]))


static func create_boss(binding: Dictionary, offset_columns: float, walk_surface_row: float) -> Dictionary:
	return {
		"offsetColumns": offset_columns,
		"y": hover_feet_row(float(binding["bossHeightRows"]), walk_surface_row),
		"hp": KernelGauge.create(int(binding["hitsToDefeat"])),
		"motion": "hover",
		"attackImpulses": 0,
		"poseUntilSeconds": null,
		"lastHitAtMs": null,
	}


## Where a boss hovers: centred in the slack between its own height and the
## floor, so a tall boss sits lower and a short one higher without either
## clipping the ground or leaving the frame.
static func hover_feet_row(boss_height_rows: float, walk_surface_row: float) -> float:
	var slack := maxf(0.0, walk_surface_row - boss_height_rows)
	return walk_surface_row - slack / 2.0


## The lane seed for one fight. Derived from the run's seed and the fight's
## index rather than drawn, so the salvo lanes cost the run's generator nothing
## and a fight replays whatever the stream did before it.
static func lane_seed_for(run_seed: int, encounter_index: int) -> int:
	return (
		KernelHash.imul(run_seed ^ 0x9e3779b1, encounter_index + 1) + 0x85ebca6b
	) & 0xFFFFFFFF


static func boss_approach(offset: float, firing_distance: float, dt: float) -> float:
	if offset <= firing_distance:
		return firing_distance
	return maxf(firing_distance, offset - APPROACH_COLUMNS_PER_SECOND * dt)


static func boss_retreat(offset: float, dt: float) -> float:
	return offset + RETREAT_COLUMNS_PER_SECOND * dt


## Which rows one salvo comes down in.
##
## The **lane comes first**: a horizontal band tall enough for the avatar plus
## its margins is placed at random, and the shots are then stacked outward from
## it. So every salvo has a gap that is provably survivable, and the difficulty
## is where the gap is rather than whether there is one. The manifest refuses a
## configuration whose shots could fill the frame.
static func salvo_rows(
	rng: KernelRng,
	walk_surface_row: float,
	avatar_height_rows: float,
	lane_margin_rows: float,
	projectile_height_rows: float,
	shots: int
) -> Dictionary:
	var lane_height := avatar_height_rows + 2.0 * lane_margin_rows
	var slack := maxf(0.0, walk_surface_row - lane_height)
	var lane_top := rng.next() * slack
	var lane_bottom := lane_top + lane_height
	var half := projectile_height_rows / 2.0

	var candidates: Array = []
	var centre := lane_top - half
	while centre - half >= 0.0:
		candidates.append(centre)
		centre -= projectile_height_rows
	centre = lane_bottom + half
	while centre + half <= walk_surface_row:
		candidates.append(centre)
		centre += projectile_height_rows

	for index in range(candidates.size() - 1, 0, -1):
		var j := int(floor(rng.next() * float(index + 1)))
		var swap: Variant = candidates[index]
		candidates[index] = candidates[j]
		candidates[j] = swap

	var rows := PackedFloat64Array()
	for index in mini(shots, candidates.size()):
		rows.append(float(candidates[index]))
	return {"rows": rows, "lane": {"top": lane_top, "bottom": lane_bottom}}


## Has a shot left the part of the world anybody can see?
static func shot_expired(shot: Dictionary, behind_columns: float, ahead_columns: float) -> bool:
	if String(shot["owner"]) == "boss":
		return float(shot["x"]) < -behind_columns
	return float(shot["x"]) > ahead_columns


static func shot_box(shot: Dictionary) -> Dictionary:
	var x := float(shot["x"])
	var row := float(shot["row"])
	return {
		"left": x - float(shot["halfLengthColumns"]),
		"right": x + float(shot["halfLengthColumns"]),
		"top": row - float(shot["halfHeightRows"]),
		"bottom": row + float(shot["halfHeightRows"]),
	}


static func boss_box(boss: Dictionary, binding: Dictionary) -> Dictionary:
	var height := float(binding["bossHeightRows"])
	var authored := float(binding.get("bossHalfWidthColumns", 0.0))
	var half := authored if authored > 0.0 else height * HALF_WIDTH_FRACTION
	var offset := float(boss["offsetColumns"])
	return {
		"left": offset - half,
		"right": offset + half,
		"top": float(boss["y"]) - height,
		"bottom": float(boss["y"]),
	}


## Strict on every edge: touching is not hitting.
static func boxes_overlap(a: Dictionary, b: Dictionary) -> bool:
	return (
		float(a["left"]) < float(b["right"])
		and float(a["right"]) > float(b["left"])
		and float(a["top"]) < float(b["bottom"])
		and float(a["bottom"]) > float(b["top"])
	)


## The idle bob, which is presentation and is excluded from the hit box.
static func boss_bob_rows(now_ms: float) -> float:
	return sin((now_ms / 1000.0) * (TAU / BOB_PERIOD_SECONDS)) * BOB_ROWS
