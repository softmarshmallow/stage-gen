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
		_aim(world, null)
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
			_aim(world, null)
			return
		_aim(world, target)
		if world.target == null:
			# The thing stopped answering on the way (the season turned): the
			# walk ends where it is, and the reason is said — the one time a
			# refusal is spoken, because a walk ending in silence would be a
			# mystery.
			player.approach = null
			_refuse(world, target as Dictionary)
			return
		if float((target as Dictionary)["edge"]) > reach:
			return
		if not bool((target as Dictionary).get("ready", true)):
			# Within reach of a drop still moving: stand and wait for it.
			return
		Targeting.start_interaction(world, target as Dictionary)
		return
	# A thing clicked (not the viewer's: it had no mouse) is the target at any
	# distance: within reach the action starts, beyond it the click commits
	# the walk the key would have. A thing with nothing to offer says so; a
	# thing that is refused (an axe missing) is passed over — its label
	# already says what it needs, and the focus stays with the nearest rule.
	var clicked: Variant = world.input.get("click_entity", null)
	if clicked is Dictionary:
		var chosen_by_click: Variant = null
		if Targeting.index_of(world.entities, clicked) >= 0:
			chosen_by_click = Targeting.target_for(world, clicked as Dictionary)
		player.goto = null
		if chosen_by_click == null:
			_aim(world, Targeting.interactable_at(world))
			Helpers.say(world, "Nothing to be done with that.")
			return
		if (chosen_by_click as Dictionary)["disabled"] != null:
			_aim(world, Targeting.interactable_at(world))
			return
		_aim(world, chosen_by_click)
		if float((chosen_by_click as Dictionary)["edge"]) > reach \
				or not bool((chosen_by_click as Dictionary).get("ready", true)):
			# The walk, or the wait for a drop still moving: the approach is
			# both, and starts the take when the drop has settled in reach.
			player.approach = {"entity": (chosen_by_click as Dictionary)["entity"], "stall": 0.0}
			return
		Targeting.start_interaction(world, chosen_by_click as Dictionary)
		return
	if Targeting.yield_pending(world):
		# A trunk's logs are on their way down beside the player: the held
		# key waits for them rather than turning to the next tree.
		_aim(world, null)
		return
	# The focus is the nearest thing by the one rule; the target is that thing
	# only when it can be acted on. Space over a refused focus (a tree without
	# an axe) does nothing: the thing stays lit and named with what it needs,
	# and the player stays where they are.
	_aim(world, Targeting.interactable_at(world))
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
	if not bool(chosen.get("ready", true)):
		# The nearest thing is a drop still bouncing at the feet: wait for it.
		return
	Targeting.start_interaction(world, chosen)


## Focus and target, set together: the focus is what is offered (refused or
## not), the target is the focus only when nothing refuses it.
static func _aim(world: World, focus: Variant) -> void:
	world.focus = focus
	world.target = focus if focus is Dictionary and (focus as Dictionary)["disabled"] == null else null


## A refusal said aloud, sentence-cased and facing the thing: only for a walk
## that ends because its thing stopped answering.
static func _refuse(world: World, target: Dictionary) -> void:
	var entity: Dictionary = target["entity"]
	var player: PlayerState = world.player
	player.facing = Targeting.facing_for(
		float(entity["x"]) - player.x, float(entity["z"]) - player.z, world.camera_yaw, player.facing
	)
	var text := str(target["disabled"])
	Helpers.say(world, text.substr(0, 1).to_upper() + text.substr(1) + ".")


static func _advance_busy(world: World, player: PlayerState, states: Dictionary, dt: float) -> void:
	var busy := player.busy as Dictionary
	var entity: Variant = busy["entity"]
	# The thing being worked stays the focus through the swing (the viewer
	# blanked it, and its prompt strip with it; here the lift and the label
	# are on the thing, and would blink at every blow).
	_aim(world, null)
	if entity is Dictionary and Targeting.index_of(world.entities, entity) >= 0:
		_aim(world, Targeting.target_for(world, entity as Dictionary))
	busy["elapsed"] = float(busy["elapsed"]) + dt
	if float(busy["elapsed"]) < Targeting.state_duration(states.get(str(busy["state"]), null)):
		return
	var interaction: Variant = busy["interaction"]
	var spec: Variant = busy["spec"]
	if bool(busy.get("take", false)):
		_finish_take(world, player, entity as Dictionary)
	elif entity != null and Targeting.index_of(world.entities, entity) >= 0:
		_land_blow(world, player, entity as Dictionary, interaction as Dictionary, spec, int(busy["hits"]), int(busy["tool_slot"]))
	player.busy = null
	# The same tick: what the key would turn to now — the yield just thrown,
	# before anything else — so the focus never blanks between blow and drop.
	_aim(world, null if Targeting.yield_pending(world) else Targeting.interactable_at(world))


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
		if tool_slot != -1:
			# The one in hand (`HAND_SLOT`) or the pack slot that served.
			Inventory.wear_tool(world, tool_slot)
		var family := ""
		var height := 3.0
		if spec != null:
			family = str((spec as Dictionary).get("family", ""))
			var authored := float((spec as Dictionary).get("height_meters", 0.0))
			if authored != 0.0:
				height = authored
		if str(interaction.get("yield_to", "")) == "hand":
			# The authored contract for a thing gathered by hand: the yield
			# goes straight into the pack, seen as a flight from the thing to
			# the slot; what does not fit falls at the thing, and is said.
			_take_in_hand(world, player, entity, interaction["yields"], -away_x, -away_z)
		elif str(interaction.get("verb", "")) == "chop" and family == "tree":
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
	_progress_look(entity, interaction, hits)


## The yield of a hand-gathered thing, counted into the pack at the blow. Each
## piece that went is a `pickup` from where the thing stands (the HUD flies
## it to the slot); the ones the pack could not take fall toward the player.
static func _take_in_hand(
	world: World, _player: PlayerState, entity: Dictionary, yields: Variant, dir_x: float, dir_z: float
) -> void:
	if yields == null:
		return
	var fallen: Array = []
	for produced in (yields as Array):
		var block := produced as Dictionary
		var wanted := int(block.get("count", 0))
		if wanted == 0:
			wanted = 1
		var left := Inventory.inv_add(world, str(block["item_id"]), wanted)
		for n in wanted - left:
			Helpers.emit(world, {
				"type": "pickup", "item": str(block["item_id"]), "x": entity["x"], "z": entity["z"],
			})
		if left > 0:
			fallen.append({"item_id": str(block["item_id"]), "count": left})
	if not fallen.is_empty():
		Helpers.say(world, "Hands full.")
		SysDrops.spawn_drops(world, fallen, float(entity["x"]), float(entity["z"]), dir_x, dir_z, 1.0)


## The author's look for this many hits: a cracked rock, a split one.
static func _progress_look(entity: Dictionary, interaction: Dictionary, hits: int) -> void:
	var progress: Variant = interaction.get("progress", null)
	if progress != null and (progress as Array).size() > 0:
		var step: int = mini(hits - 1, (progress as Array).size() - 1)
		var look: Variant = (progress as Array)[step]
		if look != entity["state"]:
			entity["state"] = look
			entity["dirty"] = true
