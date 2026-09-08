class_name PlatformerMob
extends RefCounted

## A creature on the route: what it is, where it patrols, and how it moves.
##
## A port of the simulation half of `web/lib/sideview-platformer/mob.ts` and the
## terrain lane of `mob-navigation.ts`. The browser's is a Phaser controller —
## its position lives on a sprite and its facing is a mirror flag — so this is a
## re-derivation, and what is here is the state the golden hashes plus the lane
## it is bounded by.
##
## **The behaviour seed is the instance number, not the spawn column.** The
## constructor falls back to a column-and-slot mix when no seed is passed, and
## `PlatformerMobBehavior.seed_for` ports that fallback — but the population
## director passes the instance number, so a creature's tempo comes from *when*
## it was spawned rather than *where*. Measured: the first two creatures on the
## road step -1.166040014 and -1.127991638 pixels on their spawn frame, which is
## what the instance seed gives and nine decimals away from what the column seed
## does.
##
## What is here is the wander. Chasing, striking, fleeing and returning home are
## `mob-behavior.ts`'s awareness node, and the golden does not reach them until
## the player is inside a creature's notice radius.

## The patrol speed of a creature whose package names none, before its own
## variation is applied.
const DEFAULT_SPEED_PX := 36.0

## How far from home a creature may wander, and how far it may chase.
const PATROL_HOME_RADIUS_TILES := 1.5
const PURSUIT_HOME_RADIUS_TILES := 6.0

## Half the drawn body, kept off the world's edges.
const RENDERED_HALF_WIDTH := 24.0

const STATE_WANDER := "wander"
const STATE_CHASE := "chase"
const STATE_ATTACK_RECOVERY := "attack_recovery"
const STATE_RETURN_HOME := "return_home"
const STATE_WINDUP := "windup"
const STATE_HURT := "hurt"

## How long a flinch holds a creature still.
const HURT_DURATION_MS := 600.0

## How far a blow pushes a creature, and over how long it eases out.
const KNOCKBACK_PX := 80.0
const KNOCKBACK_MS := 220.0

## The height every creature is drawn to, whatever its own art measures.
const DRAWN_HEIGHT := 110.0

## The frame a creature falls back to when its strips did not resolve.
##
## Not a detail: the drawn envelope is what a thrown round is tested against, so
## which creature a dart strikes depends on it. A package whose art loads gets
## its own frames; one whose art is absent gets a square, and the golden — taken
## against a media-free fixture — is the second case throughout. Reproducing the
## *rule* is the port; reproducing the fixture's particular absence would not be.
const FALLBACK_FRAME := 64.0

## How far above or below its own feet a creature may still reach, in tiles.
const VERTICAL_REACH_TILES := 1.0

## How near home is near enough to stop returning to it, and how fast a creature
## walks back. A return is slower than a chase: it is a creature giving up, and
## it should read as one.
const RETURN_ARRIVAL_TILES := 0.125
const RETURN_SPEED_TILES := 0.85


## A creature standing up at a reservation.
static func create(
	instance: int,
	bot_id: String,
	instance_id: String,
	slot: int,
	aggression: String,
	starting_health: int,
	spawn_x: float,
	spawn_y: float,
	map: Dictionary
) -> Dictionary:
	var profile := PlatformerCombat.profile(aggression)
	var variation := PlatformerMobBehavior.variation(instance, profile)
	var lane := _lane(map, spawn_x)
	return {
		"instanceId": instance_id,
		"botId": bot_id,
		"ladderIndex": slot,
		"aggression": aggression,
		"hp": starting_health,
		"maxHp": starting_health,
		"state": STATE_WANDER,
		"x": spawn_x,
		"y": spawn_y,
		"alive": true,
		# Not published, and not hashed: the lane it patrols, the tempo it was
		# born with, and which way it set off.
		"homeX": spawn_x,
		"patrolMinX": maxf(lane["minX"], spawn_x - roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)),
		"patrolMaxX": minf(lane["maxX"], spawn_x + roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)),
		"speedScale": float(variation["movementSpeedScale"]),
		"patrolDirection": int(variation["initialDirection"]),
		"facing": int(variation["initialDirection"]),
		# The `actor-ai` family's hysteresis: having *been* engaged is what makes
		# losing the target a walk home rather than a shrug.
		"awareness": "idle",
		# The blow in flight, and when the next one may start. A wind-up already
		# committed resolves before anything else is decided.
		"strikeLandsAtMs": 0.0,
		"attackReadyAtMs": 0.0,
		"pendingStrike": {},
		"hurtUntil": 0.0,
		# The knockback in flight: where it started, where it is going, and when.
		"hitMotion": {},
		"pursuitMinX": maxf(lane["minX"], spawn_x - PlatformerMaps.TILE_PX * PURSUIT_HOME_RADIUS_TILES),
		"pursuitMaxX": minf(lane["maxX"], spawn_x + PlatformerMaps.TILE_PX * PURSUIT_HOME_RADIUS_TILES),
	}


## One frame of a creature. The body is stepped in place, which is what a world
## of plain dictionaries is for.
##
## `player` is `{x, y}` or an empty dictionary when nothing has been observed.
## The order is the browser's: notice, decide, then move — and the decision is
## the profile's numbers under the family's hysteresis, never the other way
## round.
static func step(
	mob: Dictionary, map: Dictionary, dt_seconds: float, player: Dictionary, now_ms: float = 0.0
) -> void:
	mob["nowMs"] = now_ms
	if not bool(mob["alive"]):
		return
	var profile := PlatformerCombat.profile(String(mob["aggression"]))

	# A blow already landed carries the body before anything it wants is asked.
	# The ease is sampled from the clock rather than stepped, so the same run
	# recorded twice puts a creature in the same place.
	if not (mob["hitMotion"] as Dictionary).is_empty():
		var motion: Dictionary = mob["hitMotion"]
		var elapsed := maxf(0.0, now_ms - float(motion["startedMs"]))
		var progress := clampf(elapsed / KNOCKBACK_MS, 0.0, 1.0)
		var eased := 1.0 - pow(1.0 - progress, 3.0)
		mob["x"] = float(motion["startX"]) + (float(motion["targetX"]) - float(motion["startX"])) * eased
		if progress >= 1.0:
			mob["hitMotion"] = {}

	if String(mob["state"]) == STATE_HURT:
		if now_ms < float(mob["hurtUntil"]):
			return
		mob["state"] = STATE_WANDER

	# A wind-up already in flight resolves before anything else is decided: the
	# blow was committed when it started, so backing out of range dodges the
	# damage — the caller re-checks distance — but never cancels the swing. A
	# creature that snapped out of its own blow mid-frame would read as a glitch
	# rather than as a miss.
	if String(mob["state"]) == STATE_WINDUP:
		if now_ms < float(mob["strikeLandsAtMs"]):
			return
		mob["pendingStrike"] = {
			"damage": float(profile["damage"]), "dirSign": int(mob["facing"])
		}
		mob["state"] = STATE_WANDER if player.is_empty() else STATE_ATTACK_RECOVERY

	var directive := _directive(mob, profile, player)
	if directive == "strike":
		_windup(mob, profile, now_ms, player)
		return
	if directive == "chase":
		_chase(mob, map, dt_seconds, profile, player)
		return
	if directive == "attack_recovery":
		mob["state"] = STATE_ATTACK_RECOVERY
		return
	if directive == "return_home":
		mob["state"] = STATE_RETURN_HOME
		_walk_toward(
			mob, map, dt_seconds, float(mob["homeX"]), roundf(PlatformerMaps.TILE_PX * RETURN_SPEED_TILES)
		)
		return
	wander(mob, map, dt_seconds)


## What this creature wants this frame.
##
## Two rules over one another: the family decides whether it is engaged, holding
## or walking home, and the profile decides what engagement means at this
## distance and cadence. The ladder's order is the browser's and is load
## bearing — a cooldown outranks range, so a creature that has just swung keeps
## its committed pose rather than falling through to patrol.
static func _directive(mob: Dictionary, profile: Dictionary, player: Dictionary) -> String:
	var observed := not player.is_empty()
	var distance := 0.0
	if observed:
		distance = absf(float(player["x"]) - float(mob["x"]))
	var within_territory := (
		observed
		and float(player["x"]) >= float(mob["pursuitMinX"])
		and float(player["x"]) <= float(mob["pursuitMaxX"])
	)
	var can_engage := (
		observed and within_territory and distance <= float(profile["aggroRadiusPx"])
	)
	var home_required := not (
		float(mob["x"]) >= float(mob["patrolMinX"])
		and float(mob["x"]) <= float(mob["patrolMaxX"])
	)
	var at_home := (
		absf(float(mob["x"]) - float(mob["homeX"]))
		<= roundf(PlatformerMaps.TILE_PX * RETURN_ARRIVAL_TILES)
	)

	if can_engage:
		mob["awareness"] = "engaged"
		return _intent(mob, profile, distance, player)
	if String(mob["awareness"]) == "engaged" or home_required:
		mob["awareness"] = "returning"
	if String(mob["awareness"]) == "returning" and not at_home:
		return "return_home"
	mob["awareness"] = "idle"
	return "hold"


## What an engaged creature does at this distance. A strike it cannot reach is
## not a strike: a blow across a two-tile drop lands on nothing.
static func _intent(
	mob: Dictionary, profile: Dictionary, distance: float, player: Dictionary
) -> String:
	if not bool(profile["hostile"]):
		return "hold"
	if distance > float(profile["aggroRadiusPx"]):
		return "hold"
	if bool(profile["flees"]):
		return "flee"
	var reachable := (
		absf(float(mob["y"]) - float(player["y"]))
		<= PlatformerMaps.TILE_PX * VERTICAL_REACH_TILES
	)
	# Cooldown outranks range, so a creature that has just swung keeps its
	# committed pose rather than falling through to patrol.
	if (
		distance <= float(profile["strikeRangePx"])
		and float(mob.get("nowMs", 0.0)) >= float(mob["attackReadyAtMs"])
		and reachable
	):
		return "strike"
	if distance <= float(profile["strikeRangePx"]):
		return "attack_recovery"
	return "chase"


## Commit a blow. The creature stops where it stands for the wind-up's length,
## and the next one may not start until the cooldown has run.
static func _windup(
	mob: Dictionary, profile: Dictionary, now_ms: float, player: Dictionary
) -> void:
	if float(player["x"]) != float(mob["x"]):
		mob["facing"] = 1 if float(player["x"]) > float(mob["x"]) else -1
	mob["state"] = STATE_WINDUP
	mob["strikeLandsAtMs"] = now_ms + float(profile["windupMs"])
	mob["attackReadyAtMs"] = now_ms + float(profile["cooldownMs"])


## The box a round is tested against: the drawn envelope, standing on its feet.
static func bounds(mob: Dictionary) -> Dictionary:
	var half := envelope_half_width()
	return {
		"left": float(mob["x"]) - half,
		"right": float(mob["x"]) + half,
		"top": float(mob["y"]) - DRAWN_HEIGHT,
		"bottom": float(mob["y"]),
	}


## Half the drawn body. Square, because a creature whose strips did not resolve
## is drawn from a square placeholder scaled to the height every creature shares.
static func envelope_half_width() -> float:
	return FALLBACK_FRAME * (DRAWN_HEIGHT / FALLBACK_FRAME) / 2.0


## Land one blow on this creature. Returns `{connected, died, hpAfter}`.
static func take_hit(
	mob: Dictionary, map: Dictionary, amount: float, direction: int, now_ms: float
) -> Dictionary:
	if not bool(mob["alive"]):
		return {"connected": false, "died": false, "hpAfter": int(mob["hp"])}
	var after := maxi(0, int(mob["hp"]) - int(amount))
	mob["hp"] = after
	mob["state"] = STATE_HURT
	mob["hurtUntil"] = now_ms + HURT_DURATION_MS
	mob["facing"] = direction
	var target := _walk(mob, map, float(mob["x"]) + float(direction) * KNOCKBACK_PX, "world")
	mob["hitMotion"] = {"startedMs": now_ms, "startX": float(mob["x"]), "targetX": float(target["x"])}
	if after <= 0:
		mob["alive"] = false
		mob["state"] = "dead"
	return {"connected": true, "died": after <= 0, "hpAfter": after}


## Take the blow this creature has landed, if it landed one this frame.
static func consume_strike(mob: Dictionary) -> Dictionary:
	var pending: Dictionary = mob["pendingStrike"]
	mob["pendingStrike"] = {}
	return pending


## Close on the player at the profile's own speed, bounded by where this
## creature is allowed to hunt.
static func _chase(
	mob: Dictionary, map: Dictionary, dt_seconds: float, profile: Dictionary, player: Dictionary
) -> void:
	mob["state"] = STATE_CHASE
	_walk_toward(mob, map, dt_seconds, float(player["x"]), float(profile["chaseSpeedPx"]))


static func _walk_toward(
	mob: Dictionary, map: Dictionary, dt_seconds: float, target_x: float, speed_px: float
) -> void:
	var direction := 0
	if target_x > float(mob["x"]):
		direction = 1
	elif target_x < float(mob["x"]):
		direction = -1
	else:
		direction = int(mob["facing"])
	mob["facing"] = direction
	var speed := speed_px * float(mob["speedScale"])
	var next_x := float(mob["x"]) + float(direction) * speed * dt_seconds
	var walk := _walk(mob, map, next_x, "pursuit")
	mob["x"] = walk["x"]
	mob["y"] = _surface_at(map, float(mob["x"]))


## One frame of a creature nobody has noticed.
static func wander(mob: Dictionary, map: Dictionary, dt_seconds: float) -> void:
	if not bool(mob["alive"]):
		return
	mob["state"] = STATE_WANDER
	var speed := DEFAULT_SPEED_PX * float(mob["speedScale"])
	var next_x := float(mob["x"]) + float(mob["patrolDirection"]) * speed * dt_seconds
	var walk := _walk(mob, map, next_x, "patrol")
	mob["x"] = walk["x"]
	# A face turns a patrol the same way the end of its lane does. Reversing
	# rather than standing still is what stops a creature pressed against a rise
	# for the rest of the run, which reads as stuck rather than as bounded.
	if bool(walk["blocked"]):
		mob["patrolDirection"] = -int(mob["patrolDirection"])
	mob["y"] = _surface_at(map, float(mob["x"]))


## The eight fields the golden hashes.
static func snapshot(mob: Dictionary) -> Dictionary:
	return {
		"instanceId": mob["instanceId"],
		"botId": mob["botId"],
		"ladderIndex": mob["ladderIndex"],
		"aggression": mob["aggression"],
		"hp": mob["hp"],
		"maxHp": mob["maxHp"],
		"state": mob["state"],
		"x": mob["x"],
		"y": mob["y"],
		"alive": mob["alive"],
	}


## A step bounded by the patrol lane and then by the terrain, in that order.
static func _walk(
	mob: Dictionary, map: Dictionary, next_x: float, boundary: String
) -> Dictionary:
	var minimum := envelope_half_width()
	var maximum := float(map["worldWidthPx"]) - envelope_half_width()
	if boundary == "patrol":
		minimum = float(mob["patrolMinX"])
		maximum = float(mob["patrolMaxX"])
	elif boundary == "pursuit":
		minimum = float(mob["pursuitMinX"])
		maximum = float(mob["pursuitMaxX"])
	var bounded := clampf(next_x, minimum, maximum)
	var stopped := bounded != next_x
	var walk := FamilyContact.resolve_terrain_walk(
		float(mob["x"]),
		bounded,
		_surface_at(map, float(mob["x"])),
		PlatformerMaps.TILE_PX,
		func(column: int) -> float: return _surface_at_column(map, column),
		0.0,
		0.0,
		false
	)
	if bool(walk["blocked"]) or not stopped:
		return walk
	return {"x": walk["x"], "blocked": true, "blockedColumn": -1}


## The shelf a creature was spawned on: the run of columns at its own height.
##
## At tolerance zero adjacent equality chains to equality with the spawn column,
## so the lane is exactly the shelf and a creature never patrols off the ledge it
## stood up on.
static func _lane(map: Dictionary, spawn_x: float) -> Dictionary:
	var heights: PackedInt32Array = map["heights"]
	var columns := heights.size()
	var spawn_column := clampi(int(floor(spawn_x / PlatformerMaps.TILE_PX)), 0, columns - 1)
	var height := heights[spawn_column]
	var left := spawn_column
	while left > 0 and heights[left - 1] == height:
		left -= 1
	var right := spawn_column
	while right + 1 < columns and heights[right + 1] == height:
		right += 1
	var world_min := RENDERED_HALF_WIDTH
	var world_max := float(map["worldWidthPx"]) - RENDERED_HALF_WIDTH
	return {
		"minX": maxf(world_min, float(left) * PlatformerMaps.TILE_PX),
		"maxX": minf(world_max, float(right + 1) * PlatformerMaps.TILE_PX - 1.0),
	}


static func _surface_at(map: Dictionary, x: float) -> float:
	return _surface_at_column(map, int(floor(x / PlatformerMaps.TILE_PX)))


static func _surface_at_column(map: Dictionary, column: int) -> float:
	var heights: PackedInt32Array = map["heights"]
	var height := 0
	if column >= 0 and column < heights.size():
		height = heights[column]
	return PlatformerVertical.terrain_surface_y(
		height, PlatformerMaps.TILE_PX, PlatformerMaps.BASELINE_Y
	)
