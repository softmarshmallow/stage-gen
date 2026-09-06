class_name SysInteract
extends RefCounted

## Reads `collision`, `input`, `selection`; writes `entities`, `inventory`,
## `player_action`. viewer/index.html 1114-1226.

## Felled trunk fall time, s. Shared by the sim (the drop delay) and the view
## (the trunk animation) so the yield appears exactly when the crown lands.
const FALL_SECONDS := 1.1


static func update(world: World, dt: float) -> void:
	var player: PlayerState = world.player
	var states := Targeting.player_states(world)
	if player.busy != null:
		_advance_busy(world, player, states, dt)
		return
	# Deviation from the viewer (decisions.md: "death stops the player"): the
	# viewer keeps harvesting at negative health.
	if world.dead:
		world.target = null
		return
	var reach := Targeting.reach_of(world)
	if player.approach != null:
		# Step two of a committed action: the walk. The target is re-read
		# every tick, so a drop someone else took ends the walk; arrival
		# within reach starts the action whether or not the key is down.
		var entity: Dictionary = (player.approach as Dictionary)["entity"]
		var target: Variant = null
		if Targeting.index_of(world.entities, entity) >= 0:
			target = Targeting.target_for(world, entity)
		if target == null:
			player.approach = null
			world.target = null
			return
		world.target = target
		if float((target as Dictionary)["edge"]) > reach:
			return
		Targeting.start_interaction(world, target as Dictionary)
		return
	world.target = Targeting.interactable_at(world)
	if world.target == null:
		return
	# Each verb has its own key. Space is read as held, the others as a press
	# good for this tick only; nothing is queued behind a busy player.
	var chosen := world.target as Dictionary
	var wanted: bool
	if str((chosen["interaction"] as Dictionary).get("verb", "")) == "light":
		wanted = bool(world.input["light"])
	else:
		wanted = bool(world.input["interact"])
	if not wanted:
		return
	if float(chosen["edge"]) > reach:
		player.approach = {"entity": chosen["entity"], "stall": 0.0}
		return
	Targeting.start_interaction(world, chosen)


static func _advance_busy(world: World, player: PlayerState, states: Dictionary, dt: float) -> void:
	world.target = null
	var busy := player.busy as Dictionary
	busy["elapsed"] = float(busy["elapsed"]) + dt
	if float(busy["elapsed"]) < Targeting.state_duration(states.get(str(busy["state"]), null)):
		return
	var entity: Variant = busy["entity"]
	var interaction: Variant = busy["interaction"]
	var spec: Variant = busy["spec"]
	if bool(busy.get("take", false)):
		_finish_take(world, player, entity as Dictionary)
		player.busy = null
		return
	if entity != null and Targeting.index_of(world.entities, entity) >= 0:
		_land_blow(world, player, entity as Dictionary, interaction as Dictionary, spec, int(busy["hits"]), int(busy["tool_slot"]))
	player.busy = null


static func _finish_take(world: World, player: PlayerState, entity: Dictionary) -> void:
	# The reach-and-lift is over: the piece leaves the ground and is counted,
	# unless the pack is full, in which case it stays.
	if str(entity.get("kind", "")) == "forage":
		var wanted := int(entity["count"])
		var left := Inventory.inv_add(world, str(entity["item_id"]), wanted)
		if left == wanted:
			entity["taken"] = false
			Helpers.say(world, "Hands full.")
		else:
			entity["picked"] = true
			entity["regrow"] = float(entity["regrow_seconds"])
			entity["dirty"] = true
			Helpers.emit(world, {
				"type": "pickup", "item": str(entity["item_id"]), "x": entity["x"], "z": entity["z"],
			})
			if left > 0:
				SysDrops.spawn_drops(
					world, [{"item_id": str(entity["item_id"]), "count": left}],
					float(entity["x"]), float(entity["z"]), 0.0, 1.0, 0.2
				)
		return
	var index := Targeting.index_of(world.entities, entity)
	if index >= 0:
		if SysDrops.pick_up(world, entity):
			world.entities.remove_at(index)
		else:
			entity["taken"] = false


static func _land_blow(
	world: World, player: PlayerState, entity: Dictionary,
	interaction: Dictionary, spec: Variant, busy_hits: int, tool_slot: int
) -> void:
	entity["hits"] = int(entity["hits"]) + 1
	# Which way the blow lands: from the player through the trunk. The world
	# reacts along it -- the shake, the chips, and the fall.
	var to_x: float = float(entity["x"]) - player.x
	var to_z: float = float(entity["z"]) - player.z
	var length := sqrt(to_x * to_x + to_z * to_z)
	if length == 0.0:
		length = 1.0
	var away_x := to_x / length
	var away_z := to_z / length
	var hits := int(entity["hits"])
	Helpers.emit(world, {
		"type": "hit", "id": entity["id"], "prop_id": entity["prop_id"], "state": entity["state"],
		"verb": str(interaction["verb"]), "kind": str(interaction.get("fx", "")),
		"x": entity["x"], "z": entity["z"], "away_x": away_x, "away_z": away_z,
		"last": hits >= busy_hits,
	})
	if hits >= busy_hits:
		var before: Variant = entity["state"]
		entity["hits"] = 0
		entity["state"] = interaction["next_state"]
		entity["dirty"] = true
		var regrow: Variant = interaction.get("regrow_seconds", null)
		entity["regrow"] = float(regrow) if regrow != null else 0.0
		# The tool wears once per thing it finishes, not per blow.
		if tool_slot >= 0:
			Inventory.wear_tool(world, tool_slot)
		var family := ""
		var height := 3.0
		if spec != null:
			family = str((spec as Dictionary).get("family", ""))
			var authored := float((spec as Dictionary).get("height_meters", 0.0))
			if authored != 0.0:
				height = authored
		if str(interaction.get("verb", "")) == "chop" and family == "tree":
			# The trunk topples away from the player, in the screen plane, and
			# its yield appears where the crown lands, when it lands.
			var toppling := -1.0 if Targeting.screen_right_component(away_x, away_z, world.camera_yaw) < 0.0 else 1.0
			var right_x := cos(world.camera_yaw) * toppling
			var right_z := -sin(world.camera_yaw) * toppling
			Helpers.emit(world, {
				"type": "fell", "id": entity["id"], "prop_id": entity["prop_id"], "state": before,
				"x": entity["x"], "z": entity["z"], "sign": toppling, "height": height,
			})
			world.drops.append({
				"at": world.time + FALL_SECONDS, "yields": interaction["yields"],
				"x": float(entity["x"]) + right_x * height * 0.45,
				"z": float(entity["z"]) + right_z * height * 0.45,
				"dir_x": right_x, "dir_z": right_z, "spread": 1.2,
			})
		else:
			# The yield is thrown back toward the player.
			SysDrops.spawn_drops(
				world, interaction["yields"], float(entity["x"]), float(entity["z"]),
				-away_x, -away_z, 1.0
			)
		return
	var progress: Variant = interaction.get("progress", null)
	if progress != null and (progress as Array).size() > 0:
		# The author's look for this many hits: a cracked rock, a split one.
		var step: int = mini(hits - 1, (progress as Array).size() - 1)
		var look: Variant = (progress as Array)[step]
		if look != entity["state"]:
			entity["state"] = look
			entity["dirty"] = true
