class_name PlatformerProjectiles
extends RefCounted

## What is in the air, and what it hits.
##
## A port of `projectile-flight.ts` and the simulation half of `projectiles.ts`.
## A round leaves the hand on the release frame, flies flat, and stops on the
## first thing it touches — and the *first* is the caller's order rather than the
## nearest, because a replay that picked the geometrically nearest target would
## diverge the moment two creatures stood at the same distance. Deterministic
## beats nearest, and at these speeds nothing distinguishes them.
##
## The range budget is spent on the path length rather than the horizontal
## displacement, so a class that later throws in an arc cannot buy extra reach by
## falling. With a flat throw the two are identical, which is why it costs
## nothing today and prevents a surprise later.

## `flat_fast_v1`, the one flight this genre publishes.
const FLIGHT := {
	"speedTilesPerSecond": 11.0,
	"gravityPxPerSecond2": 0.0,
	"maxRangeTiles": 6.0,
	"releaseForwardTiles": 0.5,
	"releaseHeightFraction": 0.5,
	"halfWidthTiles": 0.35,
	"halfHeightTiles": 0.7,
}

## `single_target_v1`: one creature, and the round is spent.
const MAX_TARGETS := 1

## How many rounds may be in the air at once.
const POOL_CAP := 16

## The body a release height is measured up from. `y` is the ground contact
## point for every actor in this scene, so a release fraction of a half puts the
## throw at chest height.
const PLAYER_HEIGHT := 154.0


## Put one round in the air. Returns it, or an empty dictionary when the pool is
## full.
static func launch(shots: Array, next_id: int, origin_x: float, foot_y: float, dir_sign: int) -> Dictionary:
	if shots.size() >= POOL_CAP:
		return {}
	var tile := PlatformerMaps.TILE_PX
	var made := {
		"id": "shot_%d" % next_id,
		"x": origin_x + float(dir_sign) * float(FLIGHT["releaseForwardTiles"]) * tile,
		"y": foot_y - float(FLIGHT["releaseHeightFraction"]) * PLAYER_HEIGHT,
		"vxPx": float(dir_sign) * float(FLIGHT["speedTilesPerSecond"]) * tile,
		"vyPx": 0.0,
		"dirSign": dir_sign,
		"spinDegrees": 0.0,
		"struck": 0,
		"remainingPx": float(FLIGHT["maxRangeTiles"]) * tile,
		"halfWidthPx": float(FLIGHT["halfWidthTiles"]) * tile,
		"halfHeightPx": float(FLIGHT["halfHeightTiles"]) * tile,
	}
	made["spawnX"] = made["x"]
	shots.append(made)
	return made


## Step every round and say what each one struck.
##
## `targets` is this frame's boxes, in the caller's order. Returns
## `[{targetIndex, spawnX, dirSign, impactX, impactY}]` and prunes what expired.
static func update(shots: Array, targets: Array, dt_ms: float, world: Dictionary) -> Array:
	var hits: Array = []
	var index := shots.size() - 1
	while index >= 0:
		var shot: Dictionary = shots[index]
		_advance(shot, dt_ms)
		var expiry := _expiry(shot, world)
		if expiry.is_empty():
			var connected := false
			while int(shot["struck"]) < MAX_TARGETS:
				var target := _first_overlapping(shot, targets)
				if target < 0:
					break
				shot["struck"] = int(shot["struck"]) + 1
				connected = true
				hits.append(
					{
						"targetIndex": target,
						"spawnX": shot["spawnX"],
						"dirSign": shot["dirSign"],
						"impactX": shot["x"],
						"impactY": shot["y"],
					}
				)
			# Decided after the whole frame is resolved rather than inside the
			# loop: a round that stops on contact still resolves against
			# everything it arrived among.
			if connected or int(shot["struck"]) >= MAX_TARGETS:
				expiry = {"reason": "hit"}
		if not expiry.is_empty():
			shots.remove_at(index)
		index -= 1
	return hits


## The eight fields the golden hashes, oldest round first.
static func snapshots(shots: Array) -> Array:
	var made: Array = []
	for entry: Variant in shots:
		var shot: Dictionary = entry
		made.append(
			{
				"id": shot["id"],
				"x": shot["x"],
				"y": shot["y"],
				"vxPx": shot["vxPx"],
				"vyPx": shot["vyPx"],
				"dirSign": shot["dirSign"],
				"spinDegrees": shot["spinDegrees"],
				"struck": shot["struck"],
			}
		)
	return made


static func _advance(shot: Dictionary, dt_ms: float) -> void:
	var dt := dt_ms / 1000.0
	var vy := float(shot["vyPx"]) + float(FLIGHT["gravityPxPerSecond2"]) * dt
	var dx := float(shot["vxPx"]) * dt
	var dy := vy * dt
	shot["x"] = float(shot["x"]) + dx
	shot["y"] = float(shot["y"]) + dy
	shot["vyPx"] = vy
	shot["remainingPx"] = float(shot["remainingPx"]) - sqrt(dx * dx + dy * dy)


## Why this round should stop, or an empty dictionary to keep flying.
##
## Range is checked before terrain so a round that runs out of budget exactly as
## it reaches a hillside reports the reason that is actually true of it.
static func _expiry(shot: Dictionary, world: Dictionary) -> Dictionary:
	if float(shot["remainingPx"]) <= 0.0:
		return {"reason": "range"}
	if float(shot["x"]) < float(world["minX"]) or float(shot["x"]) > float(world["maxX"]):
		return {"reason": "world"}
	var surface: Callable = world["surfaceAt"]
	if float(shot["y"]) >= float(surface.call(float(shot["x"]))):
		return {"reason": "terrain"}
	return {}


## The index of the first box this round overlaps, or -1. Edge contact counts,
## which is what makes a grazing hit connect.
static func _first_overlapping(shot: Dictionary, targets: Array) -> int:
	var left := float(shot["x"]) - float(shot["halfWidthPx"])
	var right := float(shot["x"]) + float(shot["halfWidthPx"])
	var top := float(shot["y"]) - float(shot["halfHeightPx"])
	var bottom := float(shot["y"]) + float(shot["halfHeightPx"])
	for index in range(targets.size()):
		var box: Dictionary = targets[index]
		if (
			left <= float(box["right"])
			and right >= float(box["left"])
			and top <= float(box["bottom"])
			and bottom >= float(box["top"])
		):
			return index
	return -1
