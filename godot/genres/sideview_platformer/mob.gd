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

## How long a corpse takes to fade out. When it is over the thing is gone: the
## world is the only record of what is on the route, and a corpse that outlived
## its fade would stand there invisible, occupying a place the director will not
## put anything else on.
const DEATH_FADE_MS := 280.0

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

## A rise this small is a step rather than a wall, and a foot stopped by a face is
## left this far clear of it — so the column lookup still resolves to the side the
## creature is standing on rather than to the wall it is touching.
const TERRAIN_STEP_UP_TOLERANCE := 1.0
const TERRAIN_WALL_CONTACT_GAP := 1.0

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
		# The shelf it stands on, kept so a creature thrown off the end of it can be
		# asked whether where it landed is still part of the shelf.
		"laneMinX": lane["minX"],
		"laneMaxX": lane["maxX"],
		"patrolMinX": maxf(lane["minX"], spawn_x - roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)),
		"patrolMaxX": minf(lane["maxX"], spawn_x + roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)),
		"speedScale": float(variation["movementSpeedScale"]),
		"patrolDirection": int(variation["initialDirection"]),
		"facing": int(variation["initialDirection"]),
		# The `actor-ai` family's hysteresis: having *been* engaged is what makes
		# losing the target a walk home rather than a shrug.
		"awareness": "idle",
		# Where the body was when somebody last told this creature, and whether it
		# was still standing. Written once a frame by the contact pass and read on
		# the next line of the same frame — which is why a creature that stood up
		# *after* that pass hunts nothing until the frame after: nobody told it.
		"observed": {},
		# The blow in flight, and when the next one may start. A wind-up already
		# committed resolves before anything else is decided.
		"strikeLandsAtMs": 0.0,
		"attackReadyAtMs": 0.0,
		# The seed it was born with and how many blows it has thrown, which
		# together decide how long the next one takes.
		"behaviorSeed": instance,
		"actionSequence": 0,
		# Which flank of an unreachable player it is walking to, and which flanks a
		# terrain face has already refused.
		"pursuit": {"side": null, "blocked": {}},
		# How wide that corridor is for this creature: the profile's, scaled by the
		# same seed that gave it its tempo, so a group does not sweep in unison.
		"sweepHalfWidthPx": (
			float(profile["inaccessibleSweepHalfWidthPx"]) * float(variation["pursuitSweepScale"])
		),
		"pendingStrike": {},
		"hurtUntil": 0.0,
		# The knockback in flight: where it started, where it is going, and when.
		"hitMotion": {},
		"diedAtMs": -1.0,
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

	# A blow already landed carries the body before anything it wants is asked —
	# and before the check that it is still alive, because a corpse is carried
	# too. That is the whole of what a kill looks like: the thing is thrown, and
	# it goes on being thrown after it has stopped deciding anything.
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

	if not bool(mob["alive"]):
		return
	var profile := PlatformerCombat.profile(String(mob["aggression"]))

	if String(mob["state"]) == STATE_HURT:
		if now_ms < float(mob["hurtUntil"]):
			return
		_adopt_forced_landing(mob, map)
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
	if directive == "flee":
		_flee(mob, map, dt_seconds, profile, player)
		return
	if directive == "attack_recovery":
		PlatformerMobBehavior.reset_pursuit(mob["pursuit"])
		mob["state"] = STATE_ATTACK_RECOVERY
		return
	if directive == "return_home":
		PlatformerMobBehavior.reset_pursuit(mob["pursuit"])
		mob["state"] = STATE_RETURN_HOME
		var going := PlatformerMobBehavior.return_home_step(
			float(mob["homeX"]),
			float(mob["x"]),
			roundf(PlatformerMaps.TILE_PX * RETURN_ARRIVAL_TILES),
			roundf(PlatformerMaps.TILE_PX * RETURN_SPEED_TILES),
			float(mob["speedScale"]),
			dt_seconds
		)
		_walk_to(mob, map, float(going["targetX"]), "pursuit")
		return
	PlatformerMobBehavior.reset_pursuit(mob["pursuit"])
	wander(mob, map, dt_seconds)


## Take the shelf a blow threw this creature onto, if it is not the one it left.
##
## Knockback may deliberately carry a creature over a drop, and once it has
## landed on a disconnected shelf its old home is unreachable — a creature can
## neither jump nor climb. Re-homing only in that case keeps ordinary knockback
## on the same shelf free of consequences while stopping a return that can never
## arrive.
static func _adopt_forced_landing(mob: Dictionary, map: Dictionary) -> void:
	var landing := float(mob["x"])
	if landing >= float(mob["laneMinX"]) and landing <= float(mob["laneMaxX"]):
		return
	var half := envelope_half_width()
	var home := clampf(landing, half, float(map["worldWidthPx"]) - half)
	var lane := _lane(map, home)
	mob["laneMinX"] = lane["minX"]
	mob["laneMaxX"] = lane["maxX"]
	mob["homeX"] = home
	mob["patrolMinX"] = maxf(
		lane["minX"], home - roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)
	)
	mob["patrolMaxX"] = minf(
		lane["maxX"], home + roundf(PlatformerMaps.TILE_PX * PATROL_HOME_RADIUS_TILES)
	)
	mob["pursuitMinX"] = maxf(
		lane["minX"], home - PlatformerMaps.TILE_PX * PURSUIT_HOME_RADIUS_TILES
	)
	mob["pursuitMaxX"] = minf(
		lane["maxX"], home + PlatformerMaps.TILE_PX * PURSUIT_HOME_RADIUS_TILES
	)
	# It has arrived somewhere it did not choose: whatever it was hunting and
	# whichever flank it was sweeping describe a place it is no longer standing.
	mob["awareness"] = "idle"
	PlatformerMobBehavior.reset_pursuit(mob["pursuit"])
	mob["y"] = _surface_at(map, float(mob["x"]))


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
		observed
		and not bool(player.get("defeated", false))
		and within_territory
		and distance <= float(profile["aggroRadiusPx"])
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
	# Cooldown outranks range, so a creature that has just swung keeps its
	# committed pose rather than falling through to patrol.
	if (
		distance <= float(profile["strikeRangePx"])
		and float(mob.get("nowMs", 0.0)) >= float(mob["attackReadyAtMs"])
	):
		# A blow it cannot reach is not a blow it holds still for: the swing
		# becomes a chase, and the chase is what closes the gap in *height*. Folding
		# the reach into the rung above instead would leave a creature standing in
		# recovery under a deck it could have walked round to.
		if reachable(mob, player):
			return "strike"
		return "chase"
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
	var timing := PlatformerMobBehavior.action_timing(
		int(mob["behaviorSeed"]),
		int(mob["actionSequence"]),
		float(profile["windupMs"]),
		float(profile["cooldownMs"]),
		float(profile["actionTimingVarianceRatio"])
	)
	mob["actionSequence"] = int(mob["actionSequence"]) + 1
	mob["strikeLandsAtMs"] = now_ms + float(timing["windupMs"])
	mob["attackReadyAtMs"] = now_ms + float(timing["cooldownMs"])


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
	mob: Dictionary,
	map: Dictionary,
	amount: float,
	direction: int,
	now_ms: float,
	knockback_scale: float = 1.0
) -> Dictionary:
	if not bool(mob["alive"]):
		return {"connected": false, "died": false, "hpAfter": int(mob["hp"])}
	var after := maxi(0, int(mob["hp"]) - int(amount))
	mob["hp"] = after
	mob["state"] = STATE_HURT
	mob["hurtUntil"] = now_ms + HURT_DURATION_MS
	# At whoever swung, which is the opposite of the way the blow throws it.
	mob["facing"] = PlatformerMobBehavior.hit_facing(direction)
	var target := _walk(
		mob,
		map,
		float(mob["x"]) + float(direction) * KNOCKBACK_PX * knockback_scale,
		"world",
		true
	)
	mob["hitMotion"] = {"startedMs": now_ms, "startX": float(mob["x"]), "targetX": float(target["x"])}
	if after <= 0:
		mob["alive"] = false
		mob["state"] = "dead"
		mob["diedAtMs"] = now_ms
	return {"connected": true, "died": after <= 0, "hpAfter": after}


## Take the blow this creature has landed, if it landed one this frame.
static func consume_strike(mob: Dictionary) -> Dictionary:
	var pending: Dictionary = mob["pendingStrike"]
	mob["pendingStrike"] = {}
	return pending


## Whether this creature could land a blow on the body from where both stand.
static func reachable(mob: Dictionary, player: Dictionary) -> bool:
	if player.is_empty():
		return false
	return (
		absf(float(mob["y"]) - float(player["y"]))
		<= PlatformerMaps.TILE_PX * VERTICAL_REACH_TILES
	)


## Close on the player at the profile's own speed, bounded by where this creature
## is allowed to hunt — and sweeping a corridor around a player it cannot reach
## rather than walking at the one coordinate it can never arrive at.
static func _chase(
	mob: Dictionary, map: Dictionary, dt_seconds: float, profile: Dictionary, player: Dictionary
) -> void:
	mob["state"] = STATE_CHASE
	var pursuit: Dictionary = mob["pursuit"]
	var decision := PlatformerMobBehavior.pursuit_target(
		pursuit,
		float(mob["x"]),
		float(player["x"]),
		reachable(mob, player),
		int(mob["facing"]),
		float(mob["sweepHalfWidthPx"]),
		float(profile["pursuitArrivalRadiusPx"])
	)
	var speed := float(profile["chaseSpeedPx"]) * float(mob["speedScale"])
	var blocked := _step_by(
		mob, map, float(decision["direction"]) * speed * dt_seconds, "pursuit"
	)
	if not bool(decision["sweeping"]):
		return
	if blocked:
		PlatformerMobBehavior.report_pursuit_blocked(pursuit)
	else:
		PlatformerMobBehavior.report_pursuit_progress(pursuit)


## Back away from the body at the same speed a chase closes with, still bounded
## by where this creature is allowed to go. It reads as `chase` while it does —
## the state names the engagement, not the direction.
static func _flee(
	mob: Dictionary, map: Dictionary, dt_seconds: float, profile: Dictionary, player: Dictionary
) -> void:
	PlatformerMobBehavior.reset_pursuit(mob["pursuit"])
	var away := -1.0 if float(player["x"]) >= float(mob["x"]) else 1.0
	var speed := float(profile["chaseSpeedPx"]) * float(mob["speedScale"])
	_step_by(mob, map, away * speed * dt_seconds, "pursuit")
	mob["state"] = STATE_CHASE


## Walk to a place, and let the pose follow the displacement that survived.
## Returns whether something stopped it. Public because it is the one way to ask
## the terrain a question — a wall, a drop, the end of a lane — without a whole
## frame of behaviour around it.
static func step_to(
	mob: Dictionary, map: Dictionary, target_x: float, boundary: String
) -> bool:
	return _walk_to(mob, map, target_x, boundary)


static func _walk_to(
	mob: Dictionary, map: Dictionary, target_x: float, boundary: String
) -> bool:
	var previous := float(mob["x"])
	var walk := _walk(mob, map, target_x, boundary)
	mob["x"] = walk["x"]
	mob["facing"] = PlatformerMobBehavior.follow_movement(
		int(mob["facing"]), previous, float(mob["x"])
	)
	mob["y"] = _surface_at(map, float(mob["x"]))
	return bool(walk["blocked"])


static func _step_by(
	mob: Dictionary, map: Dictionary, delta_x: float, boundary: String
) -> bool:
	return _walk_to(mob, map, float(mob["x"]) + delta_x, boundary)


## One frame of a creature nobody has noticed.
static func wander(mob: Dictionary, map: Dictionary, dt_seconds: float) -> void:
	if not bool(mob["alive"]):
		return
	mob["state"] = STATE_WANDER
	var speed := DEFAULT_SPEED_PX * float(mob["speedScale"])
	# A face turns a patrol the same way the end of its lane does. Reversing
	# rather than standing still is what stops a creature pressed against a rise
	# for the rest of the run, which reads as stuck rather than as bounded.
	if _step_by(mob, map, float(mob["patrolDirection"]) * speed * dt_seconds, "patrol"):
		mob["patrolDirection"] = -int(mob["patrolDirection"])


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


## A step bounded by the lane and then by the terrain, in that order.
##
## `allow_descents` is the one thing knockback is allowed that a creature's own
## legs are not: a raised face stops a blow's throw the same way it stops a walk,
## but a drop does not — a thing knocked off a ledge falls off it.
static func _walk(
	mob: Dictionary,
	map: Dictionary,
	next_x: float,
	boundary: String,
	allow_descents: bool = false
) -> Dictionary:
	var minimum := envelope_half_width()
	var maximum := float(map["worldWidthPx"]) - envelope_half_width()
	if boundary == "patrol":
		minimum = float(mob["patrolMinX"])
		maximum = float(mob["patrolMaxX"])
	elif boundary == "pursuit":
		minimum = float(mob["pursuitMinX"])
		maximum = float(mob["pursuitMaxX"])
	var step := _boundary_step(float(mob["x"]), next_x, minimum, maximum)
	var walk := FamilyContact.resolve_terrain_walk(
		float(mob["x"]),
		float(step["x"]),
		_surface_at(map, float(mob["x"])),
		PlatformerMaps.TILE_PX,
		func(column: int) -> float: return _surface_at_column(map, column),
		TERRAIN_STEP_UP_TOLERANCE,
		TERRAIN_WALL_CONTACT_GAP,
		allow_descents
	)
	if bool(walk["blocked"]) or not bool(step["blocked"]):
		return walk
	return {"x": walk["x"], "blocked": true, "blockedColumn": -1}


## A lane boundary, enforced without snapping a creature that is already outside
## it back in.
##
## Knockback and a shelf a creature was thrown onto both leave one standing
## outside its own lane. A plain clamp would teleport it back on the next step,
## which is worse than the displacement. So: already outside may step *inward* at
## full size and is not reported blocked, may not step further outward, and only
## one already inside is stopped at the edge.
static func _boundary_step(
	previous_x: float, next_x: float, minimum: float, maximum: float
) -> Dictionary:
	if previous_x < minimum:
		if next_x < previous_x:
			return {"x": previous_x, "blocked": true}
		if next_x > maximum:
			return {"x": maximum, "blocked": true}
		return {"x": next_x, "blocked": false}
	if previous_x > maximum:
		if next_x > previous_x:
			return {"x": previous_x, "blocked": true}
		if next_x < minimum:
			return {"x": minimum, "blocked": true}
		return {"x": next_x, "blocked": false}
	var bounded := clampf(next_x, minimum, maximum)
	return {"x": bounded, "blocked": bounded != next_x}


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
	# The drawn envelope, not a number of its own. There used to be a second
	# constant here — twenty-four where the envelope is fifty-five — and the two
	# never disagreed anywhere a creature actually stood, because a lane only
	# clamps at the edge of the world and nothing the population puts down
	# patrols that far. A gate's boss stands eight tiles from the east edge, and
	# thirty-one pixels of lane is the difference between hunting a player and
	# walking home.
	var world_min := envelope_half_width()
	var world_max := float(map["worldWidthPx"]) - envelope_half_width()
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


## Has this creature finished fading out? A caller prunes on it; nothing here
## removes anything, because a world's list is the world's.
static func faded(mob: Dictionary, now_ms: float) -> bool:
	if bool(mob["alive"]):
		return false
	var died := float(mob.get("diedAtMs", -1.0))
	return died >= 0.0 and now_ms - died >= DEATH_FADE_MS
