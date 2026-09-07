class_name RunnerEncounterSystem
extends RefCounted

## The boss fight: when it starts, how it is fought, and how it ends.
##
## A port of `web/lib/sideview-runner/encounter.ts`. Six phases, and the
## interesting ones are the joins: the fight waits for the arena chunk to
## actually arrive under the avatar rather than firing on a distance, and it
## waits for the cut-in to release the world rather than on a timer.
##
## Two reads are **feedback reads** and are not declared: the segment stream
## (to know what the avatar is standing on) and the run's phase. Declaring
## either would order this after a system that reads what this writes.
##
## The locomotion swap lives in a ledger held *beside* the world, because a
## ledger holds Callables and a slice that carried one would be a slice no
## digest can hash.

static var _ledgers: Dictionary = {}


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/encounter",
		"contract_version": "encounter-system-v2",
		"reads": ["clock", "avatar", "difficulty"],
		"owns": ["encounter", "locomotion"],
		"emits": [
			"encounter-started",
			"shot-contact",
			"boss-hit",
			"boss-defeated",
			"encounter-ended",
			"fx-requested",
		],
		"consumes": ["fx-released"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	_step_encounter(
		world, float(world.clock["simulationNow"]), float(world.clock["simulationDt"])
	)


static func reset(world: RunnerWorld, _scope: String) -> void:
	var key := world.get_instance_id()
	if _ledgers.has(key):
		(_ledgers[key] as FamilySwapLedger).revert_all()
		_ledgers.erase(key)


static func _step_encounter(world: RunnerWorld, now: float, dt: float) -> void:
	var state := world.encounter
	if state.is_empty():
		return
	var binding: Dictionary = world.encounter_binding
	if binding.is_empty():
		return
	# Frozen through the intro and after death: a fight is something the running
	# world does.
	if String(world.run["phase"]) != "running":
		return

	match String(state["phase"]):
		RunnerEncounterState.PHASE_IDLE:
			if FamilyDirector.trigger_reached(
				float(state["nextArenaAtColumn"]), float(world.avatar["distanceColumns"])
			):
				FamilyDirector.enter_phase(
					state, RunnerEncounterState.PHASE_ARENA_PENDING, now
				)
		RunnerEncounterState.PHASE_ARENA_PENDING:
			_arena_pending(world, state, binding, now)
		RunnerEncounterState.PHASE_CUT_IN:
			for entry: Variant in world.events.of_type("fx-released"):
				if String((entry as Dictionary).get("moment", "")) == "encounter_start":
					_begin_battle(world, state, binding, now)
					return
		RunnerEncounterState.PHASE_BATTLE:
			_step_battle(world, state, binding, now, dt)
		RunnerEncounterState.PHASE_RETREAT:
			_retreat(world, state, now, dt)
		RunnerEncounterState.PHASE_COOLDOWN:
			_cooldown(world, state, binding, now)


static func _arena_pending(
	world: RunnerWorld, state: Dictionary, binding: Dictionary, now: float
) -> void:
	var standing := RunnerSegments.chunk_at(
		world.segments, int(floor(float(world.avatar["distanceColumns"])))
	)
	if standing.is_empty() or String(standing["role"]) != "arena":
		return
	var moment: Dictionary = world.config["encounterMoment"]
	# Never clobber a moment already in flight: the phase simply repeats until
	# the screen is free.
	if not moment.is_empty() and not world.fx.is_empty():
		return
	world.events.emit({"type": "encounter-started", "index": state["encounterIndex"]})
	if moment.is_empty():
		_begin_battle(world, state, binding, now)
		return
	RunnerFxSystem.request(world, String(moment["moment"]), String(moment["choreography"]))
	FamilyDirector.enter_phase(state, RunnerEncounterState.PHASE_CUT_IN, now)


static func _begin_battle(
	world: RunnerWorld, state: Dictionary, binding: Dictionary, now: float
) -> void:
	_ledger(world).apply(_thrust_swap(world))
	state["boss"] = RunnerEncounterState.create_boss(
		binding, _boss_entry_offset(world), float(world.config["walkSurfaceRow"])
	)
	state["laneSeed"] = RunnerEncounterState.lane_seed_for(
		int(world.run["seed"]), int(state["encounterIndex"])
	)
	state["salvosFired"] = 0
	state["nextSalvoAt"] = now + float(binding["salvoPeriodSeconds"])
	state["nextPlayerShotAt"] = now + float(binding["playerFirePeriodSeconds"])
	state["outcome"] = null
	FamilyDirector.enter_phase(state, RunnerEncounterState.PHASE_BATTLE, now)


static func _end_battle(
	world: RunnerWorld, state: Dictionary, outcome: String, now: float
) -> void:
	state["outcome"] = outcome
	state["shots"] = []
	_ledger(world).revert_all()
	var boss: Dictionary = state["boss"]
	if not boss.is_empty() and outcome == "defeated":
		boss["motion"] = "death"
	FamilyDirector.enter_phase(state, RunnerEncounterState.PHASE_RETREAT, now)


static func _step_battle(
	world: RunnerWorld, state: Dictionary, binding: Dictionary, now: float, dt: float
) -> void:
	var boss: Dictionary = state["boss"]
	if boss.is_empty():
		return
	var firing := float(binding["firingDistanceColumns"])
	boss["offsetColumns"] = RunnerEncounterState.boss_approach(
		float(boss["offsetColumns"]), firing, dt
	)
	var at_stand_off := float(boss["offsetColumns"]) <= firing + 1e-9

	if boss["poseUntilSeconds"] != null and now >= float(boss["poseUntilSeconds"]):
		boss["motion"] = "hover"
		boss["poseUntilSeconds"] = null

	if (
		at_stand_off
		and state["nextSalvoAt"] != null
		and now >= float(state["nextSalvoAt"])
		and int(state["salvosFired"]) < int(binding["salvoBudget"])
	):
		_fire_salvo(world, state, binding)
		boss["poseUntilSeconds"] = now + RunnerEncounterState.ATTACK_POSE_SECONDS
		state["nextSalvoAt"] = now + float(binding["salvoPeriodSeconds"])

	if state["nextPlayerShotAt"] != null and now >= float(state["nextPlayerShotAt"]):
		_fire_player_shot(world, state, binding)
		state["nextPlayerShotAt"] = now + float(binding["playerFirePeriodSeconds"])

	var body := _avatar_box(world)
	var target := RunnerEncounterState.boss_box(boss, binding)
	var survivors: Array = []
	for entry: Variant in (state["shots"] as Array):
		var shot: Dictionary = entry
		shot["x"] = float(shot["x"]) + float(shot["vx"]) * dt
		if String(shot["owner"]) == "boss":
			if RunnerEncounterState.boxes_overlap(
				RunnerEncounterState.shot_box(shot), body
			):
				world.events.emit({"type": "shot-contact", "shotId": shot["id"]})
				continue
		elif RunnerEncounterState.boxes_overlap(
			RunnerEncounterState.shot_box(shot), target
		):
			# The boss's gauge opens no window: every pin that lands counts.
			var change := KernelGauge.drain(
				boss["hp"], 1.0, float(world.vitals["clockMs"]), 0.0
			)
			boss["hp"] = change["gauge"]
			boss["lastHitAtMs"] = world.vitals["clockMs"]
			world.events.emit({"type": "boss-hit", "remaining": change["after"]})
			continue
		if RunnerEncounterState.shot_expired(
			shot,
			float(world.config["viewportColumns"]),
			float(boss["offsetColumns"]) + firing
		):
			continue
		survivors.append(shot)
	state["shots"] = survivors

	if bool((boss["hp"] as Dictionary)["depleted"]):
		world.events.emit({"type": "boss-defeated"})
		_end_battle(world, state, "defeated", now)
		return
	if int(state["salvosFired"]) < int(binding["salvoBudget"]):
		return
	# The budget is spent. The fight is over once the last shot it fired has
	# left, so a player is never killed by a boss that has already given up.
	for entry: Variant in (state["shots"] as Array):
		if String((entry as Dictionary)["owner"]) == "boss":
			return
	_end_battle(world, state, "exhausted", now)


static func _retreat(
	world: RunnerWorld, state: Dictionary, now: float, dt: float
) -> void:
	var boss: Dictionary = state["boss"]
	if boss.is_empty():
		FamilyDirector.enter_phase(state, RunnerEncounterState.PHASE_COOLDOWN, now)
		return
	boss["offsetColumns"] = RunnerEncounterState.boss_retreat(float(boss["offsetColumns"]), dt)
	if float(boss["offsetColumns"]) <= _boss_entry_offset(world):
		return
	var outcome: Variant = state["outcome"]
	world.events.emit(
		{
			"type": "encounter-ended",
			"outcome": "exhausted" if outcome == null else outcome,
		}
	)
	state["boss"] = {}
	FamilyDirector.enter_phase(state, RunnerEncounterState.PHASE_COOLDOWN, now)


static func _cooldown(
	world: RunnerWorld, state: Dictionary, binding: Dictionary, now: float
) -> void:
	var standing := RunnerSegments.chunk_at(
		world.segments, int(floor(float(world.avatar["distanceColumns"])))
	)
	# Stay in cooldown until the arena is behind us, or the next fight would be
	# armed while the body is still standing in the last one's floor.
	if not standing.is_empty() and String(standing["role"]) == "arena":
		return
	state["nextArenaAtColumn"] = (
		float(world.avatar["distanceColumns"]) + float(binding["intervalColumns"])
	)
	state["encounterIndex"] = int(state["encounterIndex"]) + 1
	state["outcome"] = null
	FamilyDirector.enter_phase(state, RunnerEncounterState.PHASE_IDLE, now)


static func _fire_salvo(world: RunnerWorld, state: Dictionary, binding: Dictionary) -> void:
	var boss: Dictionary = state["boss"]
	var rng := KernelRng.new(int(state["laneSeed"]) + int(state["salvosFired"]))
	var salvo := RunnerEncounterState.salvo_rows(
		rng,
		float(world.config["walkSurfaceRow"]),
		float(world.config["playerHeightTiles"]),
		float(binding["laneMarginRows"]),
		float(binding["projectileHeightRows"]),
		int(binding["salvoShots"])
	)
	var half := float(binding["projectileHeightRows"]) / 2.0
	for row: float in (salvo["rows"] as PackedFloat64Array):
		_push_shot(
			state,
			{
				"owner": "boss",
				"x": float(boss["offsetColumns"]),
				"row": row,
				"vx": -float(binding["projectileSpeedColumnsPerSecond"]),
				"halfLengthColumns": half,
				"halfHeightRows": half,
			}
		)
	state["salvosFired"] = int(state["salvosFired"]) + 1
	boss["attackImpulses"] = int(boss["attackImpulses"]) + 1
	boss["motion"] = "attack"


static func _fire_player_shot(
	world: RunnerWorld, state: Dictionary, binding: Dictionary
) -> void:
	var half := float(binding["projectileHeightRows"]) / 2.0
	_push_shot(
		state,
		{
			"owner": "player",
			"x": float((world.config["arithmetic"] as Dictionary)["avatarHalfWidthColumns"]),
			"row": (
				float(world.avatar["y"]) - float(world.config["playerHeightTiles"]) / 2.0
			),
			"vx": float(binding["playerShotSpeedColumnsPerSecond"]),
			"halfLengthColumns": half,
			# A quarter, not a half: the player's pin is a slim thing and a
			# fatter box would let it clip a boss it visibly missed.
			"halfHeightRows": float(binding["projectileHeightRows"]) / 4.0,
		}
	)


static func _push_shot(state: Dictionary, shot: Dictionary) -> void:
	var shots: Array = state["shots"]
	if shots.size() >= RunnerEncounterState.SHOT_CAP:
		return
	var made := shot.duplicate()
	made["id"] = state["nextShotId"]
	shots.append(made)
	state["nextShotId"] = int(state["nextShotId"]) + 1


## Where the boss comes in from: just past the right edge of the view.
static func _boss_entry_offset(world: RunnerWorld) -> float:
	return (
		float(world.config["viewportColumns"])
		* (1.0 - RunnerContract.AVATAR_SCREEN_ANCHOR_FRACTION)
		+ 2.0
	)


## The body's box in the avatar's own frame, and never ducked: sliding under a
## barrage is the runner's other locomotion, not this one.
static func _avatar_box(world: RunnerWorld) -> Dictionary:
	var half := float((world.config["arithmetic"] as Dictionary)["avatarHalfWidthColumns"])
	return {
		"left": -half,
		"right": half,
		"top": float(world.avatar["y"]) - float(world.config["playerHeightTiles"]),
		"bottom": float(world.avatar["y"]),
	}


static func _ledger(world: RunnerWorld) -> FamilySwapLedger:
	var key := world.get_instance_id()
	if not _ledgers.has(key):
		_ledgers[key] = FamilySwapLedger.new()
	return _ledgers[key]


static func _thrust_swap(world: RunnerWorld) -> Dictionary:
	var before := world.locomotion
	return {
		"id": "locomotion",
		"apply": func() -> void: world.locomotion = "thrust",
		"revert": func() -> void: world.locomotion = before,
	}
