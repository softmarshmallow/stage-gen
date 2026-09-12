class_name RunnerAvatarSystem
extends RefCounted

## The body: where it is, whether it is on the ground, and what killed it.
##
## A port of `web/lib/sideview-runner/avatar.ts`. Two locomotions live here and
## the fight swaps between them — `run` is the ordinary auto-run with a jump
## arc, `thrust` is the boss fight's held-to-climb flight. They share the
## contact family and pick different entry rules from it, which is why one
## function serves both.
##
## The arc is recomputed every step from the manifest's admission rather than
## stored: the numbers cannot drift from the level that was drawn against them.

## The air-jump budget each profile allows.
const AIR_JUMPS := {"single_arc_v1": 0, "double_arc_v1": 1}


static func declaration() -> KernelSystem:
	return KernelSystem.of({
		"id": "runner/avatar",
		"contract_version": "avatar-system-v5",
		"reads": ["clock", "intent", "difficulty"],
		"owns": ["avatar"],
		"emits": ["pit", "crush", "jumped", "landed", "slid"],
	})


static func update(world: RunnerWorld, _step: Dictionary) -> void:
	var before_impulses := int(world.avatar["jumpImpulses"])
	var before_grounded := bool(world.avatar["grounded"])
	var before_sliding := bool(world.avatar["sliding"])
	_step_avatar(world, float(world.clock["simulationDt"]))
	if int(world.avatar["jumpImpulses"]) > before_impulses:
		world.events.emit(
			{"type": "jumped", "airJump": int(world.avatar["airJumpsUsed"]) > 0}
		)
	if bool(world.avatar["grounded"]) and not before_grounded:
		world.events.emit({"type": "landed"})
	if bool(world.avatar["sliding"]) and not before_sliding:
		world.events.emit({"type": "slid"})


## The arc that clears this manifest's widest gap and highest rise.
static func jump_arc(config: Dictionary) -> Dictionary:
	var arithmetic: Dictionary = config["arithmetic"]
	return FamilyJump.jump_arc_from_admission(
		float(config["maxRiseTiles"]),
		float(config["maxClearGapColumns"]),
		float(arithmetic["baseSpeedColumnsPerSecond"]),
		float(arithmetic["jumpPeakMarginTiles"]),
		float(arithmetic["airtimeHeadroom"])
	)


static func _step_avatar(world: RunnerWorld, dt: float) -> void:
	var avatar := world.avatar
	var config := world.config
	var phase := String(world.run["phase"])
	if phase == "dead":
		avatar["motion"] = "death"
		return
	# The intro is a picture, not a pause: no physics and no intent, so a player
	# hammering the key through a cut-in arrives standing still.
	if phase == "intro":
		return
	RunnerVitalsSystem.apply_pending_recovery(world)
	var arc := jump_arc(config)
	if world.locomotion == "thrust" and not (config["encounter"] as Dictionary).is_empty():
		_step_thrust(world, dt, (config["encounter"] as Dictionary)["thrust"])
		return

	avatar["distanceColumns"] = (
		float(avatar["distanceColumns"]) + float(world.difficulty["speedColumnsPerSecond"]) * dt
	)
	var support := _support(world)

	if bool(world.intent["jump"]):
		var request := FamilyJump.resolve_jump_request(
			FamilyContact.SUPPORT_TERRAIN if bool(avatar["grounded"]) else FamilyContact.SUPPORT_AIR,
			int(avatar["airJumpsUsed"]),
			0.0,
			-1.0,
			false,
			int(AIR_JUMPS.get(String(config["jumpProfile"]), 0)),
			float(arc["initialSpeedPerSecond"]),
			float(arc["initialSpeedPerSecond"])
		)
		if String(request["kind"]) != FamilyJump.KIND_NONE:
			avatar["airJumpsUsed"] = request["airJumpsUsed"]
			_launch(world, float(request["vy"]))

	if bool(avatar["grounded"]):
		avatar["sliding"] = String(config["duckProfile"]) != "" and bool(world.intent["duck"])
		avatar["motion"] = "slide" if bool(avatar["sliding"]) else "run"
		if support < 0:
			avatar["grounded"] = false
			avatar["sliding"] = false
			avatar["motion"] = "jump"
		else:
			var contact := FamilyContact.resolve_terrain_step(
				float(avatar["y"]), float(support), 0.0
			)
			if String(contact["support"]) == FamilyContact.SUPPORT_AIR:
				avatar["grounded"] = false
				avatar["sliding"] = false
				avatar["motion"] = "jump"
			elif float(contact["footY"]) < float(avatar["y"]):
				# The ground face rose into the body. Note the resolved footY is
				# compared and never written back: on a flat step the body does
				# not move, which is what keeps a run from ratcheting upward.
				world.events.emit({"type": "crush"})
				return

	if not bool(avatar["grounded"]):
		var y_before := float(avatar["y"])
		avatar["vy"] = float(avatar["vy"]) + float(arc["gravityPerSecondSquared"]) * dt
		avatar["y"] = float(avatar["y"]) + float(avatar["vy"]) * dt
		if support < 0:
			if float(avatar["y"]) > float(config["rows"]):
				world.events.emit({"type": "pit"})
			return
		var landing := FamilyContact.resolve_vertical_landing(
			y_before,
			float(avatar["y"]),
			float(avatar["vy"]),
			float(support),
			FamilyContact.ENTRY_CROSSING
		)
		match String(landing["support"]):
			FamilyContact.SUPPORT_TERRAIN:
				avatar["y"] = landing["footY"]
				avatar["vy"] = landing["vy"]
				avatar["grounded"] = true
				avatar["airJumpsUsed"] = 0
				avatar["sliding"] = (
					String(config["duckProfile"]) != "" and bool(world.intent["duck"])
				)
				avatar["motion"] = "slide" if bool(avatar["sliding"]) else "run"
			FamilyContact.SUPPORT_BURIED:
				world.events.emit({"type": "crush"})
				return
			_:
				if float(avatar["y"]) > float(config["rows"]):
					world.events.emit({"type": "pit"})


## The boss fight's locomotion: held is up, released is down, and the floor is a
## limit rather than a hazard.
static func _step_thrust(world: RunnerWorld, dt: float, thrust: Dictionary) -> void:
	var avatar := world.avatar
	var config := world.config
	avatar["distanceColumns"] = (
		float(avatar["distanceColumns"]) + float(world.difficulty["speedColumnsPerSecond"]) * dt
	)
	var support := _support(world)
	var held := bool(world.intent["thrust"])
	avatar["sliding"] = false
	avatar["airJumpsUsed"] = 0
	if bool(avatar["grounded"]) and not held:
		avatar["vy"] = 0.0
		avatar["motion"] = "run"
		return
	if bool(avatar["grounded"]):
		avatar["grounded"] = false
	var y_before := float(avatar["y"])
	avatar["vy"] = thrust_velocity(float(avatar["vy"]), held, dt, thrust)
	avatar["y"] = float(avatar["y"]) + float(avatar["vy"]) * dt
	var ceiling := float(config["playerHeightTiles"])
	if float(avatar["y"]) < ceiling:
		avatar["y"] = ceiling
		avatar["vy"] = 0.0
	if support >= 0:
		var landing := FamilyContact.resolve_vertical_landing(
			y_before,
			float(avatar["y"]),
			float(avatar["vy"]),
			float(support),
			FamilyContact.ENTRY_CLAMP
		)
		if String(landing["support"]) == FamilyContact.SUPPORT_TERRAIN:
			avatar["y"] = landing["footY"]
			avatar["vy"] = landing["vy"]
			avatar["grounded"] = true
			avatar["motion"] = "run"
			return
	elif float(avatar["y"]) > float(config["rows"]):
		world.events.emit({"type": "pit"})
		return
	avatar["motion"] = "fly"


## One acceleration, two asymmetric caps: a body climbs slower than it falls.
static func thrust_velocity(vy: float, held: bool, dt: float, thrust: Dictionary) -> float:
	var direction := -1.0 if held else 1.0
	var accelerated := (
		vy + direction * float(thrust["climbAccelerationRowsPerSecondSquared"]) * dt
	)
	return clampf(
		accelerated,
		-float(thrust["maxClimbRowsPerSecond"]),
		float(thrust["maxFallRowsPerSecond"])
	)


static func _launch(world: RunnerWorld, vy: float) -> void:
	var avatar := world.avatar
	avatar["vy"] = vy
	avatar["grounded"] = false
	avatar["sliding"] = false
	avatar["motion"] = "jump"
	avatar["jumpImpulses"] = int(avatar["jumpImpulses"]) + 1


## The surface under the body: a row, -1 for a pit, and a reported defect for a
## column the stream never built.
static func _support(world: RunnerWorld) -> int:
	var column := int(floor(float(world.avatar["distanceColumns"])))
	var row := RunnerSegments.surface_row_at(world.segments, column)
	if row == RunnerSegments.OUTSIDE:
		# The body outran the stream. That is a streaming defect, not a hole,
		# and it is said out loud rather than played as a fall nobody can
		# explain.
		push_error(
			"runner/segments: world column %d is outside the streamed window" % column
		)
		return -1
	return row
