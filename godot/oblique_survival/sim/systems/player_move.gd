class_name SysPlayerMove
extends RefCounted

## Reads `input`, writes `player`. viewer/index.html 1039-1094.

## A committed walk gives up after this long without closing on its target.
const APPROACH_STALL_SECONDS := 0.6


static func update(world: World, dt: float) -> void:
	var player: PlayerState = world.player
	# Deviation from the viewer (decisions.md: "death stops the player"): the
	# viewer keeps walking at negative health.
	if world.dead:
		player.vx = 0.0
		player.vz = 0.0
		player.approach = null
		return
	if player.busy != null:
		# A busy player is frozen; movement during an interaction is
		# discarded, not queued.
		player.vx = 0.0
		player.vz = 0.0
		return
	var speed := float((world.manifest["gameplay"] as Dictionary).get("player_speed_meters_per_second", 0.0))
	if speed == 0.0:
		speed = 3.2
	var x := float(world.input["x"])
	var z := float(world.input["z"])
	var length := sqrt(x * x + z * z)
	if length > 1.0:
		x /= length
		z /= length
	# Input arrives in screen space and is turned into world space by the
	# camera's yaw. This is the one place the simulation knows the camera.
	var c := cos(world.camera_yaw)
	var s := sin(world.camera_yaw)
	player.vx = (x * c + z * s) * speed
	player.vz = (-x * s + z * c) * speed
	if player.approach != null:
		# The key committed the player to a target out of reach. Any movement
		# key takes the walk back.
		if length > 0.0:
			player.approach = null
		else:
			var entity: Dictionary = (player.approach as Dictionary)["entity"]
			var to_x: float = float(entity["x"]) - player.x
			var to_z: float = float(entity["z"]) - player.z
			var far := sqrt(to_x * to_x + to_z * to_z)
			if far == 0.0:
				far = 1.0
			player.vx = (to_x / far) * speed
			player.vz = (to_z / far) * speed
	var from_x := player.x
	var from_z := player.z
	# The coast is a wall: try the full step, then each axis alone so the
	# player slides along the shore instead of sticking.
	var step_x := player.vx * dt
	var step_z := player.vz * dt
	if bool(world.is_land.call(player.x + step_x, player.z + step_z)):
		player.x += step_x
		player.z += step_z
	elif bool(world.is_land.call(player.x + step_x, player.z)):
		player.x += step_x
	elif bool(world.is_land.call(player.x, player.z + step_z)):
		player.z += step_z
	var half := float((world.manifest["ground"] as Dictionary)["size_meters"]) / 2.0 - 1.0
	player.x = clampf(player.x, -half, half)
	player.z = clampf(player.z, -half, half)
	player.facing = Targeting.facing_for(player.vx, player.vz, world.camera_yaw, player.facing)
	if player.approach != null:
		# A walk that is not getting anywhere is dropped rather than paced.
		var dx := player.x - from_x
		var dz := player.z - from_z
		var moved := sqrt(dx * dx + dz * dz)
		var approach := player.approach as Dictionary
		if moved < speed * dt * 0.25:
			approach["stall"] = float(approach["stall"]) + dt
		else:
			approach["stall"] = 0.0
		if float(approach["stall"]) >= APPROACH_STALL_SECONDS:
			player.approach = null
