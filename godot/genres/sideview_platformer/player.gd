class_name PlatformerPlayer
extends RefCounted

## The body the player drives.
##
## A port of the simulation half of `web/lib/sideview-platformer/player.ts`. That
## file is a Phaser controller — its position lives on a sprite and its opacity
## is set on the way past — so this is a re-derivation rather than a
## translation: the state is plain data here, and the fields the browser read
## off a sprite are the ones `PARITY_EXCLUDE` drops.
##
## Health is `KernelGauge`, which is where it always belonged: the invulnerability
## window after a blow is a refractory window, and the blink is the gauge's own.
##
## Priority in one frame, and the order is the whole design: an attached ladder
## outranks everything, entering one outranks dropping through a deck, and a
## drop outranks a jump. Defeat locks input; hurt does not, because hurt is
## feedback and not a stun.

const STATE_IDLE := "idle"
const STATE_WALK := "walk"
const STATE_RUN := "run"
const STATE_JUMP := "jump"
const STATE_CROUCH := "crouch"
const STATE_CLIMB := "climb"
const STATE_HURT := "hurt"
const STATE_DEATH := "death"

const FACING_LEFT := "left"
const FACING_RIGHT := "right"

## How long a flinch plays for.
const HURT_DURATION_MS := 600.0


## A body at a spawn. `max_hp` is the package's `starting_health`.
static func create(x: float, y: float, max_hp: int) -> Dictionary:
	return {
		"x": x,
		"y": y,
		"vx": 0.0,
		"vy": 0.0,
		"facing": FACING_RIGHT,
		"rearFacing": false,
		"state": STATE_IDLE,
		"support": FamilyContact.SUPPORT_TERRAIN,
		"supportId": null,
		"airborne": false,
		"airJumpsUsed": 0,
		"coyoteExpiresAtMs": -1.0,
		"ladderId": null,
		"platformId": null,
		"column": 0,
		"attackActive": false,
		"attackUntil": 0.0,
		"attackStarted": 0.0,
		"blockedColumn": -1,
		"hp": max_hp,
		"maxHp": max_hp,
		"invulnerable": false,
		"defeated": false,
		"hurtUntil": 0.0,
		"gauge": KernelGauge.create(max_hp),
		"climbAnimationKey": null,
		"climbTextureKey": null,
		"climbFrame": null,
		"dropThroughPlatformId": null,
		"dropThroughUntil": 0.0,
		"dropTraversalPhase": null,
		"dropTraversalPlatformId": null,
		"dropTraversalPlatformBottomY": null,
		"dropTraversalLowerSupport": null,
		"dropTraversalLowerSupportId": null,
		"dropTraversalLowerSupportY": null,
		"dropTraversalStableFrames": 0,
		"activeClimbableId": null,
	}


## One step. `world` carries the terrain the body walks on:
## `{heights, tilePx, baselineY, worldWidthPx, platforms, climbables, maximumAirJumps}`.
static func update(
	player: Dictionary, world: Dictionary, dt_ms: float, now_ms: float, intent: Dictionary
) -> void:
	var dt: float = dt_ms / 1000.0
	var left := bool(intent.get("left", false))
	var right := bool(intent.get("right", false))
	var down := bool(intent.get("down", false))
	var up := bool(intent.get("up", false))
	var shift := bool(intent.get("run", false))
	var wants_jump := bool(intent.get("jump", false))

	# Defeat is the only thing that locks input. Hurt blinks and flinches while
	# ordinary movement stays live, which is what makes standing next to a
	# creature survivable rather than a stun-lock.
	var controls_locked: bool = bool(player["defeated"])
	if controls_locked:
		player["vx"] = 0.0
	player["invulnerable"] = KernelGauge.is_refractory(player["gauge"], now_ms)

	# An attached ladder outranks every movement and combat action.
	if not controls_locked and String(player["support"]) == FamilyContact.SUPPORT_CLIMBABLE:
		_continue_ladder(player, world, dt, up, down, left, right, wants_jump)
		return

	# Entering a ladder outranks dropping through a deck.
	if not controls_locked:
		var entry := FamilyTraversal.climb_entry_at(
			world.get("climbables", []),
			Callable(PlatformerVertical, "climb_geometry"),
			PlatformerVertical.CLIMBABLE_ENDPOINT_TOLERANCE,
			String(player["support"]),
			player["supportId"],
			float(player["x"]),
			float(player["y"]),
			up,
			down
		)
		if not entry.is_empty():
			var zone: Dictionary = entry["zone"]
			player["activeClimbableId"] = zone["id"]
			player["ladderId"] = zone["id"]
			_set_support(player, FamilyContact.SUPPORT_CLIMBABLE, zone["id"])
			player["vx"] = 0.0
			player["vy"] = 0.0
			player["x"] = zone["centerX"]
			player["attackActive"] = false
			_continue_ladder(player, world, dt, up, down, left, right, false)
			return

	_advance_drop_settle(player)

	var target_vx: float = float(player["vx"])
	if not controls_locked:
		target_vx = 0.0
		if left and not right:
			target_vx = -(PlatformerVertical.RUN_SPEED if shift else PlatformerVertical.WALK_SPEED)
			player["facing"] = FACING_LEFT
		elif right and not left:
			target_vx = PlatformerVertical.RUN_SPEED if shift else PlatformerVertical.WALK_SPEED
			player["facing"] = FACING_RIGHT
		# An aim override outranks the step: a policy that backs away from what
		# it is fighting would otherwise turn its back on it, and the blow leaves
		# on the frame facing is read.
		if intent.get("face") != null:
			player["facing"] = String(intent["face"])

	var crouching := (
		not controls_locked and down and String(player["support"]) != FamilyContact.SUPPORT_AIR
	)
	if crouching:
		target_vx = FamilyTraversal.resolve_crouch_horizontal_velocity(
			target_vx, PlatformerVertical.CROUCH_SPEED
		)
	if not controls_locked:
		player["vx"] = target_vx

	# Down plus jump drops through the deck underfoot. A ladder entry was already
	# taken above, so it cannot be shadowed by this.
	var dropping := (
		not controls_locked
		and wants_jump
		and down
		and String(player["support"]) == FamilyContact.SUPPORT_PLATFORM
		and player["supportId"] != null
	)
	if dropping:
		_begin_drop(player, world, now_ms)
	elif not controls_locked and wants_jump:
		var jump := FamilyJump.resolve_jump_request(
			String(player["support"]),
			int(player["airJumpsUsed"]),
			now_ms,
			float(player["coyoteExpiresAtMs"]),
			crouching,
			int(world.get("maximumAirJumps", PlatformerVertical.AIR_JUMPS_MAX)),
			PlatformerVertical.JUMP_VELOCITY,
			PlatformerVertical.AIR_JUMP_VELOCITY
		)
		if String(jump["kind"]) != FamilyJump.KIND_NONE:
			_begin_drop_recovery(player)
			player["vy"] = jump["vy"]
			player["airJumpsUsed"] = jump["airJumpsUsed"]
			player["coyoteExpiresAtMs"] = -1.0
			if String(player["support"]) != FamilyContact.SUPPORT_AIR:
				_set_support(player, FamilyContact.SUPPORT_AIR, null)

	# Horizontal motion, stopped by any column face standing above the feet. A
	# one-tile rise is a wall, not a step, so the way up is a jump.
	var tile_px: float = float(world["tilePx"])
	var previous_x: float = float(player["x"])
	var surface_at := func(column: int) -> float:
		return PlatformerVertical.terrain_surface_y(
			_height_at(world, column), tile_px, float(world["baselineY"])
		)
	var walk := FamilyContact.resolve_terrain_walk(
		previous_x,
		clampf(
			previous_x + float(player["vx"]) * dt,
			tile_px / 2.0,
			float(world["worldWidthPx"]) - tile_px / 2.0
		),
		float(player["y"]),
		tile_px,
		surface_at,
		PlatformerVertical.STEP_UP_TOLERANCE,
		PlatformerVertical.WALL_CONTACT_GAP
	)
	player["x"] = walk["x"]
	if bool(walk["blocked"]):
		player["vx"] = 0.0
		player["blockedColumn"] = walk["blockedColumn"]
	else:
		player["blockedColumn"] = -1

	# Vertical motion, and the one-way deck or terrain that catches it.
	var column: int = int(floor(float(player["x"]) / tile_px))
	player["column"] = column
	var surface_y: float = PlatformerVertical.terrain_surface_y(
		_height_at(world, column), tile_px, float(world["baselineY"])
	)

	if String(player["support"]) == FamilyContact.SUPPORT_PLATFORM:
		var deck := PlatformerVertical.platform_by_id(
			world.get("platforms", []), player["supportId"]
		)
		if (
			deck.is_empty()
			or float(player["x"]) < float(deck["left"])
			or float(player["x"]) > float(deck["right"])
		):
			_open_coyote(player, now_ms)
			_set_support(player, FamilyContact.SUPPORT_AIR, null)
			player["vy"] = 0.0
		else:
			player["y"] = deck["deckY"]
	elif String(player["support"]) == FamilyContact.SUPPORT_TERRAIN:
		# An uphill column is still absorbed, which keeps this heightfield's
		# column-locked climb. A descending column is a real ledge: the foot
		# holds its height and the airborne branch drops it under gravity rather
		# than teleporting it onto the new surface.
		var step := FamilyContact.resolve_terrain_step(float(player["y"]), surface_y, 0.0)
		player["y"] = step["footY"]
		if String(step["support"]) == FamilyContact.SUPPORT_AIR:
			_open_coyote(player, now_ms)
			_set_support(player, FamilyContact.SUPPORT_AIR, null)
			player["vy"] = 0.0

	if String(player["support"]) == FamilyContact.SUPPORT_AIR:
		player["vy"] = float(player["vy"]) + PlatformerVertical.GRAVITY * dt
		var next_foot_y: float = float(player["y"]) + float(player["vy"]) * dt
		var ignored: Variant = _active_drop_through(player, world, now_ms)
		var landing := FamilyContact.resolve_vertical_landing(
			float(player["y"]),
			next_foot_y,
			float(player["vy"]),
			surface_y,
			FamilyContact.ENTRY_CROSSING,
			float(player["x"]),
			world.get("platforms", []),
			"" if ignored == null else String(ignored)
		)
		player["y"] = landing["footY"]
		player["vy"] = landing["vy"]
		var support_id: Variant = landing["supportId"]
		if String(landing["support"]) == FamilyContact.SUPPORT_AIR or String(support_id).is_empty():
			support_id = null
		_set_support(player, String(landing["support"]), support_id)
		if (
			String(landing["support"]) != FamilyContact.SUPPORT_AIR
			and support_id != player["dropThroughPlatformId"]
		):
			_clear_drop_through(player)

	player["platformId"] = (
		player["supportId"]
		if String(player["support"]) == FamilyContact.SUPPORT_PLATFORM
		else null
	)
	_resolve_state(player, crouching, shift, now_ms)


## Land one blow. Returns whether it connected, so a caller can decide about
## knockback and transcript lines without this knowing about either.
##
## A blow during invulnerability is not an error and is not a hit — it is
## absorbed, which is what the refractory window is for.
static func take_damage(player: Dictionary, amount: float, now_ms: float) -> bool:
	var change := KernelGauge.drain(
		player["gauge"], amount, now_ms, FamilyVitals.CONTACT_REFRACTORY_MS
	)
	if not bool(change["connected"]):
		return false
	player["gauge"] = change["gauge"]
	player["hp"] = int(change["after"])
	player["defeated"] = bool(change["depleted"])
	player["invulnerable"] = true
	player["hurtUntil"] = now_ms + HURT_DURATION_MS
	return true


## The opacity a hurt body draws at. Presentation, and excluded from parity — but
## derived here because it is the gauge's rule rather than the host's.
static func blink_alpha(player: Dictionary, now_ms: float) -> float:
	return KernelGauge.refractory_blink_alpha(
		player["gauge"],
		now_ms,
		FamilyVitals.CONTACT_BLINK_INTERVAL_MS,
		FamilyVitals.CONTACT_BLINK_ALPHA
	)


static func _resolve_state(
	player: Dictionary, crouching: bool, shift: bool, now_ms: float
) -> void:
	# Defeat and the flinch outrank locomotion. A flinch has nowhere to fall back
	# to: not drawing one is the answer, because whatever was playing continues.
	var next: String = ""
	if bool(player["defeated"]):
		next = STATE_DEATH
	elif String(player["state"]) == STATE_HURT and now_ms < float(player["hurtUntil"]):
		next = STATE_HURT
	elif bool(player["attackActive"]):
		next = String(player["state"])
	elif String(player["support"]) == FamilyContact.SUPPORT_AIR:
		next = STATE_JUMP
	elif crouching:
		next = STATE_CROUCH
	elif not is_zero_approx(float(player["vx"])):
		next = STATE_RUN if shift else STATE_WALK
	else:
		next = STATE_IDLE
	player["state"] = next


static func _continue_ladder(
	player: Dictionary,
	world: Dictionary,
	dt: float,
	up: bool,
	down: bool,
	left: bool,
	right: bool,
	wants_jump: bool
) -> void:
	var zone := _climbable_by_id(world, player["activeClimbableId"])
	if zone.is_empty():
		_set_support(player, FamilyContact.SUPPORT_AIR, null)
		player["ladderId"] = null
		player["activeClimbableId"] = null
		return
	player["x"] = zone["centerX"]
	player["vx"] = 0.0
	if wants_jump:
		var jump := FamilyTraversal.climb_jump_off_velocity(
			PlatformerVertical.CLIMBABLE_JUMP_VELOCITY,
			PlatformerVertical.CLIMBABLE_JUMP_HORIZONTAL_SPEED,
			left,
			right,
			String(player["facing"])
		)
		player["vx"] = jump["vx"]
		player["vy"] = jump["vy"]
		player["x"] = float(player["x"]) + float(player["vx"]) * dt
		player["y"] = float(player["y"]) + float(player["vy"]) * dt
		player["activeClimbableId"] = null
		player["ladderId"] = null
		_set_support(player, FamilyContact.SUPPORT_AIR, null)
		player["state"] = STATE_JUMP
		return
	var motion := FamilyTraversal.advance_climb_motion(
		PlatformerVertical.climb_geometry(zone),
		PlatformerVertical.CLIMBABLE_SPEED,
		float(player["y"]),
		dt,
		up,
		down
	)
	player["y"] = motion["footY"]
	player["vy"] = motion["vy"]
	var exit: String = String(motion["exit"])
	if exit == FamilyContact.SUPPORT_PLATFORM:
		player["activeClimbableId"] = null
		player["ladderId"] = null
		_set_support(player, FamilyContact.SUPPORT_PLATFORM, zone["platformId"])
		player["state"] = STATE_IDLE
		return
	if exit == FamilyContact.SUPPORT_TERRAIN:
		player["activeClimbableId"] = null
		player["ladderId"] = null
		_set_support(player, FamilyContact.SUPPORT_TERRAIN, null)
		player["state"] = STATE_IDLE
		return
	player["state"] = STATE_CLIMB


static func _set_support(player: Dictionary, support: String, support_id: Variant) -> void:
	player["support"] = support
	player["supportId"] = support_id
	player["airborne"] = support == FamilyContact.SUPPORT_AIR
	if support != FamilyContact.SUPPORT_AIR:
		player["airJumpsUsed"] = 0
		player["coyoteExpiresAtMs"] = -1.0


## Open the grace window for a support lost by falling.
##
## Only fall sites call this. A jump clears the deadline instead, so the window
## can never turn one press into two grounded launches.
static func _open_coyote(player: Dictionary, now_ms: float) -> void:
	if String(player["support"]) == FamilyContact.SUPPORT_AIR:
		return
	player["coyoteExpiresAtMs"] = now_ms + PlatformerVertical.COYOTE_MS


static func _begin_drop(player: Dictionary, world: Dictionary, now_ms: float) -> void:
	var deck := PlatformerVertical.platform_by_id(world.get("platforms", []), player["supportId"])
	if deck.is_empty():
		return
	player["dropThroughPlatformId"] = deck["id"]
	player["dropThroughUntil"] = now_ms + PlatformerVertical.DROP_THROUGH_MS
	player["dropTraversalPlatformId"] = deck["id"]
	player["dropTraversalPlatformBottomY"] = (
		float(deck["deckY"]) + PlatformerVertical.UPPER_PLATFORM_THICKNESS
	)
	player["dropTraversalPhase"] = "drop-commanded"
	player["dropTraversalLowerSupport"] = null
	player["dropTraversalLowerSupportId"] = null
	player["dropTraversalLowerSupportY"] = null
	player["dropTraversalStableFrames"] = 0
	_set_support(player, FamilyContact.SUPPORT_AIR, null)
	player["vy"] = 0.0


static func _advance_drop_settle(player: Dictionary) -> void:
	if String(player["dropTraversalPhase"] if player["dropTraversalPhase"] != null else "") != "lower-support-landed":
		return
	if player["support"] != player["dropTraversalLowerSupport"]:
		return
	if player["supportId"] != player["dropTraversalLowerSupportId"]:
		return
	if not is_equal_approx(float(player["y"]), float(player["dropTraversalLowerSupportY"])):
		return
	player["dropTraversalStableFrames"] = int(player["dropTraversalStableFrames"]) + 1
	if int(player["dropTraversalStableFrames"]) != PlatformerVertical.DROP_SETTLE_FRAMES:
		return
	player["dropTraversalPhase"] = "lower-support-settled"


static func _begin_drop_recovery(player: Dictionary) -> void:
	if String(player["dropTraversalPhase"] if player["dropTraversalPhase"] != null else "") != "lower-support-settled":
		return
	var support: String = String(player["support"])
	if support == FamilyContact.SUPPORT_AIR or support == FamilyContact.SUPPORT_CLIMBABLE:
		return
	player["dropTraversalPhase"] = "recovery-airborne"


static func _active_drop_through(
	player: Dictionary, world: Dictionary, now_ms: float
) -> Variant:
	if player["dropThroughPlatformId"] == null:
		return null
	var deck := PlatformerVertical.platform_by_id(
		world.get("platforms", []), player["dropThroughPlatformId"]
	)
	if deck.is_empty():
		_clear_drop_through(player)
		return null
	if not FamilyTraversal.drop_through_active(
		now_ms,
		float(player["dropThroughUntil"]),
		float(player["y"]),
		float(deck["deckY"]),
		PlatformerVertical.DROP_CLEARANCE
	):
		_clear_drop_through(player)
		return null
	return player["dropThroughPlatformId"]


static func _clear_drop_through(player: Dictionary) -> void:
	player["dropThroughPlatformId"] = null
	player["dropThroughUntil"] = 0.0


static func _climbable_by_id(world: Dictionary, zone_id: Variant) -> Dictionary:
	if zone_id == null:
		return {}
	for entry: Variant in world.get("climbables", []):
		var zone: Dictionary = entry
		if String(zone["id"]) == String(zone_id):
			return zone
	return {}


static func _height_at(world: Dictionary, column: int) -> int:
	var heights: PackedInt32Array = world["heights"]
	if column < 0 or column >= heights.size():
		return 0
	return heights[column]
