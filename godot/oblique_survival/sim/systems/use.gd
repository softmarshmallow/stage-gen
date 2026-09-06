class_name SysUse
extends RefCounted

## Reads `input`, `selection`, `inventory`; writes `inventory_use`, `torch`,
## `warm`, `vitals_delta`. viewer/index.html 788-845 and 1305-1313.


static func update(world: World, _dt: float) -> void:
	if bool(world.input["use"]):
		use_selected(world)
	if bool(world.input["drop"]):
		drop_selected(world)


## X: eat or apply the selected item, or light it as a torch.
static func use_selected(world: World) -> void:
	var slot: Variant = null
	if world.selected >= 0 and world.selected < world.slots.size():
		slot = world.slots[world.selected]
	if slot == null:
		Helpers.say(world, "Nothing selected.")
		return
	var entry := slot as Dictionary
	var spec: Variant = Inventory.item_spec(world, str(entry["item"]))
	var use: Variant = (spec as Dictionary).get("use", null) if spec != null else null
	var display := Inventory.item_name(world, str(entry["item"]))
	if use == null:
		Helpers.say(world, "The %s is not for using here; Z drops it." % display)
		return
	var block := use as Dictionary
	var kind := str(block.get("kind", ""))
	if kind == "consume":
		var player: PlayerState = world.player
		var rules: Dictionary = world.manifest["gameplay"]
		var hunger_max := _limit(rules, "hunger")
		var health_max := _limit(rules, "health")
		var warmth_max := _limit(rules, "warmth")
		player.hunger = maxf(0.0, minf(hunger_max, player.hunger + float(block.get("hunger", 0.0))))
		player.health = maxf(0.0, minf(health_max, player.health + float(block.get("health", 0.0))))
		player.warmth = maxf(0.0, minf(warmth_max, player.warmth + float(block.get("warmth", 0.0))))
		_consume_one(world, entry)
		Helpers.emit(world, {"type": "eat", "item": str(entry["item"])})
		if float(block.get("health", 0.0)) > 0.0 and float(block.get("hunger", 0.0)) == 0.0:
			Helpers.say(world, "The %s helps." % display)
		else:
			Helpers.say(world, "Ate %s." % display)
	elif kind == "light":
		if world.torch["remaining"] > 0.0:
			Helpers.say(world, "A torch is already lit.")
			return
		var burn := float(block.get("burn_seconds", 0.0))
		var radius := float(block.get("radius_meters", 0.0))
		world.torch = {
			"remaining": burn if burn != 0.0 else 60.0,
			"radius": radius if radius != 0.0 else 3.0,
		}
		_consume_one(world, entry)
		Helpers.emit(world, {"type": "puff", "kind": "sparkle", "x": world.player.x, "z": world.player.z})
		Helpers.say(world, "The %s catches." % display)
	elif kind == "carry":
		Helpers.say(world, "The %s carries while it is in the pack. Nothing to do." % display)
	elif kind == "wear":
		Helpers.say(world, "The %s warms while it is in the pack. Nothing to do." % display)
	elif kind == "warm":
		if world.warm["remaining"] > 0.0:
			Helpers.say(world, "A stone is already warm.")
			return
		var heat := float(block.get("heat_seconds", 0.0))
		world.warm = {"remaining": heat if heat != 0.0 else 120.0}
		_consume_one(world, entry)
		Helpers.emit(world, {"type": "puff", "kind": "sparkle", "x": world.player.x, "z": world.player.z})
		Helpers.say(world, "The %s's heat spreads." % display)


## Z: one of the selected item, dropped at the feet. A pack must be empty of
## its own slots first.
static func drop_selected(world: World) -> void:
	var slot: Variant = null
	if world.selected >= 0 and world.selected < world.slots.size():
		slot = world.slots[world.selected]
	if slot == null:
		return
	var entry := slot as Dictionary
	var spec: Variant = Inventory.item_spec(world, str(entry["item"]))
	if spec != null:
		var use: Variant = (spec as Dictionary).get("use", null)
		if use != null and str((use as Dictionary).get("kind", "")) == "carry":
			var after := Inventory.slot_capacity(world) - int((use as Dictionary).get("slots", 0))
			for i in world.slots.size():
				if world.slots[i] != null and i >= after:
					Helpers.say(world, "Empty the pack's own slots first.")
					return
	var uses: Variant = entry["uses"]
	_consume_one(world, entry)
	var forward := Targeting.facing_direction(world)
	SysDrops.spawn_drops(
		world, [{"item_id": str(entry["item"]), "count": 1}],
		world.player.x, world.player.z, float(forward["x"]), float(forward["z"]), 0.3, uses
	)
	Helpers.emit(world, {
		"type": "pickup", "item": str(entry["item"]), "x": world.player.x, "z": world.player.z,
	})


static func _consume_one(world: World, entry: Dictionary) -> void:
	entry["count"] = int(entry["count"]) - 1
	if int(entry["count"]) <= 0:
		world.slots[world.selected] = null


static func _limit(rules: Dictionary, key: String) -> float:
	var block: Variant = rules.get(key, null)
	if block == null:
		return 100.0
	var authored := float((block as Dictionary).get("max", 0.0))
	return authored if authored != 0.0 else 100.0
