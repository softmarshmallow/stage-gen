class_name SysCraft
extends RefCounted

## Reads `input`, `inventory_use`, `collision`; writes `craft_menu`, `built`.
## viewer/index.html 692-786 (the helpers) and 1315-1328 (the system).
##
## The crafting table: C opens it, W/S (or a click on a row) choose, Enter (or
## the Craft button) makes. Recipes, stations and products are the manifest's;
## nothing here knows a recipe by name.
##
## A thing that is built (a fire, a bench) is not put down at once: making it
## closes the table and carries it to the pointer as `world.placing`, a
## silhouette the view tints green where it can stand and red where it cannot.
## A click sets it down there, in the look the recipe names (`product.state`:
## the fire is built lit), and spends the makings then; a right click lets it
## go with nothing spent. A made thing that is worn goes straight onto an
## empty hand, body or back.

## How far in front of the player the silhouette starts, beyond the two
## footprints.
const PLACE_STAND_OFF := 0.45
## What a spot says when it refuses, on a click there.
const WHY_FAR := "Too far to reach."
const WHY_WATER := "That is water."
const WHY_ROOM := "No room there."
## How a made thing that went straight on is said.
const WORN_WORDS := {"hand": "now in hand", "body": "now worn", "back": "now on the back"}


static func update(world: World, _dt: float) -> void:
	var recipes := _recipes(world)
	if world.placing != null:
		if bool(world.input.get("place_cancel", false)) or world.dead:
			cancel_placing(world)
		else:
			_update_placing(world)
			if world.placing != null and bool(world.input.get("craft_toggle", false)):
				# The table asked for again: the build is let go, the makings
				# stay, and the table opens below.
				cancel_placing(world)
			elif world.placing != null:
				return
	if bool(world.input["craft_toggle"]):
		if recipes.is_empty():
			Helpers.say(world, "This run has no crafting table.")
			return
		world.craft_open = not world.craft_open
	if not world.craft_open:
		return
	var move := int(world.input["menu_move"])
	if move != 0:
		world.craft_index = (world.craft_index + move + recipes.size()) % recipes.size()
	# A row clicked in the panel: the pointer's spelling of W/S.
	var picked: Variant = world.input.get("menu_select", null)
	if picked != null:
		world.craft_index = clampi(int(picked), 0, recipes.size() - 1)
	if bool(world.input["menu_confirm"]):
		craft_recipe(world, recipes[world.craft_index])


static func _recipes(world: World) -> Array:
	var crafting: Variant = world.manifest.get("crafting", null)
	if crafting == null:
		return []
	var recipes: Variant = (crafting as Dictionary).get("recipes", null)
	return (recipes as Array) if recipes != null else []


## The nearest prop that serves as this station, in its required look, within
## its reach; the distance measured is the edge distance.
static func station_near(world: World, station_id: String) -> Variant:
	var crafting: Variant = world.manifest.get("crafting", null)
	if crafting == null:
		return null
	var stations: Variant = (crafting as Dictionary).get("stations", null)
	if stations == null:
		return null
	var station: Variant = (stations as Dictionary).get(station_id, null)
	if station == null:
		return null
	var block := station as Dictionary
	var wanted_state: Variant = block.get("state", null)
	var reach := float(block.get("reach_meters", 0.0))
	if reach == 0.0:
		reach = 3.0
	var best: Variant = null
	var best_distance := INF
	for entity in world.entities:
		if str(entity.get("kind", "")) != "prop":
			continue
		if str(entity.get("prop_id", "")) != str(block.get("prop_id", "")):
			continue
		if wanted_state != null and str(wanted_state) != "" and str(entity.get("state", "")) != str(wanted_state):
			continue
		var dx: float = float(entity["x"]) - world.player.x
		var dz: float = float(entity["z"]) - world.player.z
		var distance := sqrt(dx * dx + dz * dz) - float(entity.get("radius", 0.0))
		if distance <= reach and distance < best_distance:
			best = entity
			best_distance = distance
	return best


## What a recipe still needs: the short ingredients and whether its station
## is in reach.
static func recipe_status(world: World, recipe: Dictionary) -> Dictionary:
	var short: Array = []
	var ingredients: Dictionary = recipe["ingredients"]
	for item_id in ingredients:
		var wanted := int(ingredients[item_id])
		var held := Inventory.count(world, str(item_id))
		if held < wanted:
			short.append([str(item_id), wanted - held])
	var station := str(recipe.get("station", ""))
	var station_ok := station == "hand" or station_near(world, station) != null
	return {"short": short, "station_ok": station_ok, "ok": short.is_empty() and station_ok}


## Why a spot refuses the thing, or "" when it can stand there: within the
## walk-to distance of the player, on land, clear of every footprint and of
## the player's own.
static func place_verdict(world: World, x: float, z: float, radius: float) -> String:
	var player: PlayerState = world.player
	var dx := x - player.x
	var dz := z - player.z
	var distance := sqrt(dx * dx + dz * dz)
	if distance > Targeting.approach_of(world):
		return WHY_FAR
	if not bool(world.is_land.call(x, z)):
		return WHY_WATER
	if distance < radius + player.radius + 0.2 or Targeting.footprint_blocked(world, x, z, radius):
		return WHY_ROOM
	return ""


## The silhouette follows the pointer and says whether it could stand there;
## a click where it can builds, a click where it cannot says why.
static func _update_placing(world: World) -> void:
	var placing := world.placing as Dictionary
	var point: Variant = world.input.get("place_point", null)
	if point is Dictionary:
		placing["x"] = float((point as Dictionary)["x"])
		placing["z"] = float((point as Dictionary)["z"])
	var why := place_verdict(world, float(placing["x"]), float(placing["z"]), float(placing["radius"]))
	placing["ok"] = why == ""
	placing["why"] = why
	if not bool(world.input.get("place_click", false)):
		return
	if why != "":
		Helpers.say(world, why)
		return
	var recipe: Dictionary = placing["recipe"]
	var built: Variant = place_prop(
		world, str(placing["prop_id"]), str(placing["state"]), float(placing["x"]), float(placing["z"])
	)
	if built == null:
		Helpers.say(world, WHY_ROOM)
		return
	var ingredients: Dictionary = recipe["ingredients"]
	for item_id in ingredients:
		Inventory.inv_remove(world, str(item_id), int(ingredients[item_id]))
	world.placing = null
	Helpers.say(world, "%s built." % str(placing["prop_id"]).replace("_", " ").capitalize())
	Helpers.emit(world, {"type": "craft", "recipe": str(recipe["recipe_id"])})


## Let the build go: nothing was spent, so there is nothing to give back.
static func cancel_placing(world: World) -> void:
	if world.placing == null:
		return
	var name := str((world.placing as Dictionary)["prop_id"]).replace("_", " ")
	world.placing = null
	if not world.dead:
		Helpers.say(world, "The %s is not built; the makings are kept." % name)


## Build a prop at a spot, in a named look, with the prop's baseline as what
## it returns to. The spot is the caller's to have checked (`place_verdict`).
## Draws one PRNG value. A look a `light` interaction leads to is built
## burning, the way lighting it would leave it.
static func place_prop(world: World, prop_id: String, state: String, x: float, z: float) -> Variant:
	var props: Variant = world.manifest.get("props", null)
	if props == null:
		return null
	var template: Variant = (props as Dictionary).get(prop_id, null)
	if template == null:
		return null
	var spec := template as Dictionary
	var radius := float(spec.get("footprint_radius_meters", 0.0))
	if radius == 0.0:
		radius = 0.3
	var baseline: Variant = spec.get("baseline_state", "")
	var look := state if state != "" else str(baseline)
	world.built += 1
	var entity := {
		"id": "c%d" % world.built, "kind": "prop", "prop_id": prop_id,
		"state": look, "baseline": baseline, "x": x, "z": z,
		"seed": int(float(world.rand.call()) * 1e5), "radius": radius,
		"hits": 0, "regrow": 0.0, "burn": 0.0, "dirty": false,
	}
	if _lit_by_interaction(spec, look):
		var campfire: Dictionary = (world.manifest["gameplay"] as Dictionary).get("campfire", {})
		var burn := float(campfire.get("burn_seconds", 0.0))
		entity["burn"] = burn if burn != 0.0 else 60.0
		Helpers.emit(world, {"type": "puff", "kind": "sparkle", "x": x, "z": z})
	world.entities.append(entity)
	return entity


## Whether a look is the one a `light` interaction leads to: built in it, the
## thing burns as if it had just been lit.
static func _lit_by_interaction(spec: Dictionary, look: String) -> bool:
	var rows: Variant = spec.get("interactions", null)
	if rows == null:
		return false
	for row in (rows as Array):
		var block := row as Dictionary
		if str(block.get("verb", "")) == "light" and str(block.get("next_state", "")) == look:
			return true
	return false


## Where a built thing's silhouette begins: in front of the player, both
## footprints and a step away.
static func place_start(world: World, radius: float) -> Dictionary:
	var player: PlayerState = world.player
	var forward := Targeting.facing_direction(world)
	var stand := radius + player.radius + PLACE_STAND_OFF
	return {"x": player.x + float(forward["x"]) * stand, "z": player.z + float(forward["z"]) * stand}


## Make the thing, or say why not. An item is made on the spot and the
## makings are spent; a built thing goes to the pointer (`world.placing`) and
## the makings are spent when it is set down.
static func craft_recipe(world: World, recipe: Dictionary) -> bool:
	var status := recipe_status(world, recipe)
	var short: Array = status["short"]
	if not short.is_empty():
		var parts: Array = []
		for pair in short:
			parts.append("%d %s" % [int(pair[1]), Inventory.item_name(world, str(pair[0]))])
		Helpers.say(world, "Need %s." % ", ".join(parts))
		return false
	if not bool(status["station_ok"]):
		Helpers.say(world, "Needs a %s within reach." % str(recipe["station"]).replace("_", " "))
		return false
	var product: Dictionary = recipe["product"]
	var ingredients: Dictionary = recipe["ingredients"]
	var prop_id: Variant = product.get("prop_id", null)
	if prop_id != null and str(prop_id) != "":
		var props: Dictionary = world.manifest.get("props", {})
		var spec: Dictionary = props.get(str(prop_id), {})
		var radius := float(spec.get("footprint_radius_meters", 0.0))
		if radius == 0.0:
			radius = 0.3
		var state := str(product.get("state", ""))
		if state == "":
			state = str(spec.get("baseline_state", ""))
		var start := place_start(world, radius)
		world.placing = {
			"recipe": recipe, "prop_id": str(prop_id), "state": state, "radius": radius,
			"x": float(start["x"]), "z": float(start["z"]), "ok": false, "why": "",
		}
		var why := place_verdict(world, float(start["x"]), float(start["z"]), radius)
		(world.placing as Dictionary)["ok"] = why == ""
		(world.placing as Dictionary)["why"] = why
		world.craft_open = false
		Helpers.say(world, "Click where the %s goes; right-click to keep the makings." % str(prop_id).replace("_", " "))
		Helpers.emit(world, {"type": "place", "recipe": str(recipe["recipe_id"])})
		return true
	for item_id in ingredients:
		Inventory.inv_remove(world, str(item_id), int(ingredients[item_id]))
	var count := int(product.get("count", 0))
	if count == 0:
		count = 1
	var made := str(product["item_id"])
	var left := Inventory.inv_add(world, made, count)
	var worn := ""
	if left == 0:
		worn = wear_if_free(world, made)
	if left > 0:
		var forward := Targeting.facing_direction(world)
		SysDrops.spawn_drops(
			world, [{"item_id": made, "count": left}], world.player.x, world.player.z,
			float(forward["x"]), float(forward["z"]), 0.3
		)
		Helpers.say(world, "Made %s; the pack is full, so it falls at your feet." % Inventory.item_name(world, made))
	elif worn != "":
		Helpers.say(world, "Made %s, %s." % [Inventory.item_name(world, made), str(WORN_WORDS[worn])])
	elif count > 1:
		Helpers.say(world, "Made %s (%d)." % [Inventory.item_name(world, made), count])
	else:
		Helpers.say(world, "Made %s." % Inventory.item_name(world, made))
	Helpers.emit(world, {"type": "craft", "recipe": str(recipe["recipe_id"])})
	return true


## A made thing that is worn (a tool, a cloak, a pack) goes straight onto its
## place when that place is empty: the kind it went on, or "" when it stayed
## in the pack (not worn, or the place already taken).
static func wear_if_free(world: World, item_id: String) -> String:
	var kind := Inventory.equip_kind(world, item_id)
	if kind == "" or world.equipment.get(kind, null) != null:
		return ""
	for index in range(world.slots.size() - 1, -1, -1):
		var entry: Variant = world.slots[index]
		if entry is Dictionary and str((entry as Dictionary).get("item", "")) == item_id:
			return kind if Inventory.equip(world, index) else ""
	return ""
