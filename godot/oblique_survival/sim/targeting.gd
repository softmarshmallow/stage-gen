class_name Targeting
extends RefCounted

## What the player could do to a thing, how far it is, and how an action
## begins. Ported verbatim from viewer/index.html lines 715-996 plus the
## facing rule at 1006-1035.
##
## Edge conventions, kept exactly: a prop's edge is the centre distance minus
## its footprint radius; a dropped item's and a forage piece's edge is the
## plain centre distance. The nearest edge wins, ties to the earlier entity
## in list order.

## Fallback approach radius, m, when the run predates gameplay.approach_meters.
const APPROACH_DEFAULT := 4.5

## Host overrides for the `?reach=` / `?approach=` query settings; 0 means
## "use the manifest". The host sets these once from its command line.
static var reach_override: float = 0.0
static var approach_override: float = 0.0


## manifest.props[entity.prop_id], or null.
static func prop_spec(world: World, entity: Dictionary) -> Variant:
	var props: Variant = world.manifest.get("props", null)
	if props == null:
		return null
	return (props as Dictionary).get(str(entity.get("prop_id", "")), null)


## The player actor's states block, or an empty dictionary.
static func player_states(world: World) -> Dictionary:
	if world.player_id == null or str(world.player_id) == "":
		return {}
	var actors: Variant = world.manifest.get("actors", null)
	if actors == null:
		return {}
	var actor: Variant = (actors as Dictionary).get(str(world.player_id), null)
	if actor == null:
		return {}
	var states: Variant = (actor as Dictionary).get("states", null)
	return states if states != null else {}


## How long one play of an authored strip lasts, in seconds.
static func state_duration(spec: Variant) -> float:
	if spec == null:
		return 0.5
	var block := spec as Dictionary
	var frames := 4
	var indices: Variant = block.get("canonical_frame_indices", null)
	if indices != null:
		frames = (indices as Array).size()
	var fps := float(block.get("fps", 0.0))
	if fps == 0.0:
		fps = 8.0
	return float(frames) / fps


## How far a world-space direction points along the screen's right edge.
static func screen_right_component(x: float, z: float, yaw: float) -> float:
	return x * cos(yaw) - z * sin(yaw)


## The component of a world direction that points at the camera.
static func toward_camera_component(x: float, z: float, yaw: float) -> float:
	return x * sin(yaw) + z * cos(yaw)


## Which of the four facings a world heading shows, against the camera's yaw.
## The side wins on a perfect diagonal; a heading under 0.05 keeps the last.
static func facing_for(x: float, z: float, yaw: float, current: String) -> String:
	var sx := screen_right_component(x, z, yaw)
	var sy := toward_camera_component(x, z, yaw)
	if sqrt(sx * sx + sy * sy) < 0.05:
		return current if current != "" else "front"
	if absf(sx) >= absf(sy) - 1e-6:
		return "left" if sx < 0.0 else "right"
	return "front" if sy > 0.0 else "back"


## -1 for a mirrored left-facing card, else 1.
static func facing_sign(facing: String) -> float:
	return -1.0 if facing == "left" else 1.0


## The world direction the player faces, from the facing name and the yaw.
static func facing_direction(world: World) -> Dictionary:
	var facing: String = world.player.facing
	var sx := 0.0
	if facing == "left":
		sx = -1.0
	elif facing == "right":
		sx = 1.0
	var sy := 0.0
	if facing == "front":
		sy = 1.0
	elif facing == "back":
		sy = -1.0
	var yaw: float = world.camera_yaw
	return {"x": sx * cos(yaw) + sy * sin(yaw), "z": -sx * sin(yaw) + sy * cos(yaw)}


## The reach: the edge distance inside which an action starts on the spot.
static func reach_of(world: World) -> float:
	if reach_override != 0.0:
		return reach_override
	var authored := float((world.manifest.get("gameplay", {}) as Dictionary).get("interact_reach_meters", 0.0))
	return authored if authored != 0.0 else 0.6


## The approach radius: out to here the key commits to a walk instead.
static func approach_of(world: World) -> float:
	if approach_override != 0.0:
		return approach_override
	var authored := float((world.manifest.get("gameplay", {}) as Dictionary).get("approach_meters", 0.0))
	return authored if authored != 0.0 else APPROACH_DEFAULT


## The footprint of one entity for the collision pass (section 9.4): the
## layout's radius when it carried one, else the prop's, else 0. Forage and
## dropped items are 0 and never block.
static func footprint_radius(entity: Dictionary) -> float:
	return float(entity.get("radius", 0.0))


## One pass over every footprint, pushing the player out to the touching
## distance. No mass, no sliding, no iteration -- the viewer's `collide`.
static func push_out_of_footprints(world: World, player: PlayerState) -> void:
	for entity in world.entities:
		# `footprint_radius` inlined: this runs once per entity per fixed step,
		# and at a few thousand entities the static call is most of the pass.
		var radius := float(entity.get("radius", 0.0))
		if radius <= 0.0:
			continue
		var dx: float = player.x - float(entity["x"])
		var dz: float = player.z - float(entity["z"])
		var reach := radius + player.radius
		var distance := sqrt(dx * dx + dz * dz)
		if distance < reach and distance > 1e-5:
			player.x = float(entity["x"]) + (dx / distance) * reach
			player.z = float(entity["z"]) + (dz / distance) * reach


## Whether a footprint of ``radius`` at (x, z) would overlap a prop or a mob.
## The build clearance of `placeProp`: (their radius or 0.3) + radius + 0.2.
static func footprint_blocked(world: World, x: float, z: float, radius: float) -> bool:
	for entity in world.entities:
		var kind := str(entity.get("kind", ""))
		if kind != "prop" and kind != "mob":
			continue
		var other := float(entity.get("radius", 0.0))
		if other == 0.0:
			other = 0.3
		var dx: float = float(entity["x"]) - x
		var dz: float = float(entity["z"]) - z
		if sqrt(dx * dx + dz * dz) < other + radius + 0.2:
			return true
	return false


## What the player could do to one entity right now, with how far its edge is
## from the player, or null when it offers nothing (a spent bush, a lit fire,
## a drop still bouncing).
static func target_for(world: World, entity: Dictionary) -> Variant:
	var player: PlayerState = world.player
	var kind := str(entity.get("kind", ""))
	if kind == "item":
		# A drop is taken by hand, on the key. One still in the air is a
		# target from the moment it leaves the thing that yielded it (the eye
		# follows it, and so does the held key), and is taken once it has
		# settled: `ready` says which.
		var pickup := str((world.manifest["gameplay"] as Dictionary).get("pickup", ""))
		if pickup == "":
			pickup = "manual"
		if pickup != "manual":
			return null
		if bool(entity.get("taken", false)):
			return null
		var target := _take_target(entity, _centre_distance(player, entity), false)
		target["ready"] = bool(entity.get("settled", false))
		return target
	if kind == "forage":
		# A piece on the ground is taken by hand like a drop; not while the
		# season hides it.
		if bool(entity.get("taken", false)) or bool(entity.get("hidden", false)):
			return null
		return _take_target(entity, _centre_distance(player, entity), true)
	if kind != "prop":
		return null
	var spec: Variant = prop_spec(world, entity)
	if spec == null:
		return null
	var rows: Variant = (spec as Dictionary).get("interactions", null)
	if rows == null or (rows as Array).is_empty():
		return null
	# The package lists what can be done to the prop in priority order, each
	# entry from the states it applies to. The offer is the first available
	# one for the prop's state; when none is, the first that applies is
	# offered with its refusal (`disabled`), so the thing is still the focus
	# — lit and named with what it needs — while the key has no target in it.
	var state := str(entity.get("state", ""))
	var edge := _centre_distance(player, entity) - float(entity.get("radius", 0.0))
	var refused: Variant = null
	for row in (rows as Array):
		var block := row as Dictionary
		var from: Variant = block.get("from", null)
		if from == null or not (from as Array).has(state):
			continue
		var target := _prop_target(world, entity, spec, block, edge)
		if target["disabled"] == null:
			return target
		if refused == null:
			refused = target
	return refused


## One interaction weighed against the pack and the season: its hits with the
## tool in hand, or the refusal that stands in the way.
static func _prop_target(world: World, entity: Dictionary, spec: Variant, block: Dictionary, edge: float) -> Dictionary:
	var verb := str(block.get("verb", ""))
	var hits := int(block.get("hits", 0))
	if hits == 0:
		hits = 1
	var disabled: Variant = null
	var tool_slot := -1
	var tool_spec: Variant = block.get("tool", null)
	if tool_spec != null:
		var tool_block := tool_spec as Dictionary
		tool_slot = Inventory.inv_find_tool(world, verb)
		if tool_slot != -1:
			var tool_hits := int(tool_block.get("hits", 0))
			if tool_hits != 0:
				hits = tool_hits
		elif bool(tool_block.get("required", false)):
			disabled = "needs a %s" % Inventory.item_name(world, str(tool_block.get("item_id", "")))
	# The season's barren list: the bush has nothing on it while it lasts.
	var season_spec: Dictionary = world.season["spec"]
	if disabled == null and verb != "light":
		var barren: Variant = season_spec.get("barren", null)
		if barren != null and (barren as Array).has(str(entity.get("prop_id", ""))):
			var label := str(season_spec.get("display_name", ""))
			if label == "":
				label = str(season_spec.get("season_id", ""))
			disabled = "bare in %s" % label.to_lower()
	return {
		"entity": entity, "interaction": block, "spec": spec, "item": false, "forage": false,
		"edge": edge, "hits": hits, "disabled": disabled, "tool_slot": tool_slot,
	}


## Seconds after a drop settles during which it is still "the yield": taken
## before anything else in the notice radius. `age` is zeroed when it settles.
const FRESH_SECONDS := 1.5


## The focus: the nearest thing that could be acted on, within the notice
## radius, or null — one rule for everything, refused or not (a pine without
## an axe is the focus, with its refusal on it; `SysInteract` makes it the
## target only when nothing refuses it). The nearest wins, drop or prop, so a
## log at the feet is taken before the
## stump behind it is chopped — except that a yield on its way down, or one
## that has just landed, comes first whatever stands nearer: the stone the
## player has just mined is the thing they are looking at, and the held key
## must not turn to the bush behind them while it bounces.
static func interactable_at(world: World) -> Variant:
	var notice := maxf(reach_of(world), approach_of(world))
	var player: PlayerState = world.player
	var px := player.x
	var pz := player.z
	var best: Variant = null
	var best_edge := INF
	var best_fresh := false
	for entity in world.entities:
		# Broad phase, and exactly the test below: every kind that can answer
		# with a target reports `edge` as the centre distance less the entity's
		# own footprint radius (a drop's and a forage piece's radius is 0, and
		# their edge is the plain centre distance), so anything failing here
		# would fail `edge > notice` too. Without it the whole notice test costs
		# a Dictionary and a fistful of manifest lookups per entity, which at a
		# few thousand entities is the most expensive thing in the step.
		var dx: float = px - float(entity.get("x", 0.0))
		var dz: float = pz - float(entity.get("z", 0.0))
		if sqrt(dx * dx + dz * dz) - float(entity.get("radius", 0.0)) > notice:
			continue
		var target: Variant = target_for(world, entity)
		if target == null:
			continue
		var edge := float((target as Dictionary)["edge"])
		if edge > notice:
			continue
		var fresh := bool((target as Dictionary).get("item", false)) and not bool((target as Dictionary).get("forage", false)) \
				and (not bool((target as Dictionary).get("ready", true)) or float(entity.get("age", INF)) < FRESH_SECONDS)
		# A fresh yield first; then the nearest edge, ties to the earlier
		# entity in list order.
		if fresh and not best_fresh:
			best_fresh = true
			best_edge = edge
			best = target
		elif fresh == best_fresh and edge < best_edge:
			best_edge = edge
			best = target
	return best


## Begin the action on a target already within reach: take a drop, light a
## fire, or play the one authored reach-and-lift at a harvestable prop.
static func start_interaction(world: World, target: Dictionary) -> void:
	var player: PlayerState = world.player
	var states := player_states(world)
	var entity: Dictionary = target["entity"]
	var interaction: Variant = target["interaction"]
	player.approach = null
	player.facing = facing_for(
		float(entity["x"]) - player.x, float(entity["z"]) - player.z, world.camera_yaw, player.facing
	)
	if target["disabled"] != null:
		# Never a target (`SysInteract._aim`): the refusal is said in its
		# place, and nothing starts.
		var text := str(target["disabled"])
		Helpers.say(world, text.substr(0, 1).to_upper() + text.substr(1) + ".")
		return
	if bool(target.get("item", false)):
		# Taking a drop plays the same authored reach-and-lift as harvesting,
		# and the drop goes when the lift ends. One still bouncing is waited
		# for, not reached after.
		if not bool(target.get("ready", true)):
			return
		entity["taken"] = true
		player.busy = {
			"state": "gather", "elapsed": 0.0, "entity": entity, "interaction": null,
			"spec": null, "take": true, "hits": 1, "tool_slot": -1,
		}
		player.state = "gather"
		player.elapsed = 0.0
		world.target = null
		return
	var block := interaction as Dictionary
	if str(block.get("verb", "")) == "light":
		# Instant, no animation, and the fire consumes no fuel.
		entity["state"] = "lit"
		entity["dirty"] = true
		var campfire: Dictionary = (world.manifest["gameplay"] as Dictionary).get("campfire", {})
		var burn := float(campfire.get("burn_seconds", 0.0))
		entity["burn"] = burn if burn != 0.0 else 60.0
		Helpers.emit(world, {
			"type": "puff", "kind": str(block.get("fx", "")), "x": entity["x"], "z": entity["z"],
		})
		Helpers.say(world, "The fire catches.")
		return
	# Every harvesting verb plays the one authored reach-and-lift.
	var action := "gather" if states.has("gather") else str(block["verb"])
	var hits := int(target.get("hits", 0))
	if hits == 0:
		hits = int(block.get("hits", 0))
	if hits == 0:
		hits = 1
	player.busy = {
		"state": action, "elapsed": 0.0, "entity": entity, "interaction": block,
		"spec": target["spec"], "take": false, "hits": hits,
		"tool_slot": int(target.get("tool_slot", -1)),
	}
	player.state = action
	player.elapsed = 0.0


## The index of an entity in the world's list, by identity (not by value:
## Godot compares dictionaries deeply, which would match a twin).
static func index_of(entities: Array, entity: Variant) -> int:
	for i in entities.size():
		if is_same(entities[i], entity):
			return i
	return -1


static func _centre_distance(player: PlayerState, entity: Dictionary) -> float:
	var dx: float = player.x - float(entity["x"])
	var dz: float = player.z - float(entity["z"])
	return sqrt(dx * dx + dz * dz)


static func _take_target(entity: Dictionary, edge: float, forage: bool) -> Dictionary:
	return {
		"entity": entity, "interaction": {"verb": "take"}, "spec": null, "item": true,
		"forage": forage, "edge": edge, "hits": 1, "disabled": null, "tool_slot": -1,
		"ready": true,
	}


## Whether a yield is still on its way to the ground near the player: a drop
## in the air or sliding, or a trunk's logs waiting for the crown to land.
## The held key waits for it rather than turning to the next thing.
static func yield_pending(world: World) -> bool:
	var notice := maxf(reach_of(world), approach_of(world))
	var player: PlayerState = world.player
	for queued in world.drops:
		var dx: float = player.x - float(queued["x"])
		var dz: float = player.z - float(queued["z"])
		if sqrt(dx * dx + dz * dz) <= notice:
			return true
	return false
