class_name SysCraft
extends RefCounted

## Reads `input`, `inventory_use`, `collision`; writes `craft_menu`, `built`.
## viewer/index.html 692-786 (the helpers) and 1315-1328 (the system).
##
## The crafting table: C opens it, W/S (or a click on a row) choose, Enter (or
## the Craft button) makes. Recipes, stations and products are the manifest's;
## nothing here knows a recipe by name.

## The headings tried around the player's facing when a prop is built.
const PLACE_OFFSETS := [0.0, 0.7, -0.7, 1.4, -1.4, 2.1, -2.1, PI]


static func update(world: World, _dt: float) -> void:
	var recipes := _recipes(world)
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


## Build a prop in front of the player, in its baseline look: the spot has to
## be land and clear of every footprint, tried at eight headings before the
## build is refused. Draws one PRNG value on success.
static func place_prop(world: World, prop_id: String) -> Variant:
	var props: Variant = world.manifest.get("props", null)
	if props == null:
		return null
	var template: Variant = (props as Dictionary).get(prop_id, null)
	if template == null:
		return null
	var radius := float((template as Dictionary).get("footprint_radius_meters", 0.0))
	if radius == 0.0:
		radius = 0.3
	var player: PlayerState = world.player
	var forward := Targeting.facing_direction(world)
	var base := atan2(float(forward["z"]), float(forward["x"]))
	var reach := radius + player.radius + 0.45
	for offset in PLACE_OFFSETS:
		var x: float = player.x + cos(base + float(offset)) * reach
		var z: float = player.z + sin(base + float(offset)) * reach
		if not bool(world.is_land.call(x, z)):
			continue
		if Targeting.footprint_blocked(world, x, z, radius):
			continue
		world.built += 1
		var baseline: Variant = (template as Dictionary).get("baseline_state", "")
		var entity := {
			"id": "c%d" % world.built, "kind": "prop", "prop_id": prop_id,
			"state": baseline, "baseline": baseline, "x": x, "z": z,
			"seed": int(float(world.rand.call()) * 1e5), "radius": radius,
			"hits": 0, "regrow": 0.0, "burn": 0.0, "dirty": false,
		}
		world.entities.append(entity)
		return entity
	return null


## Spend the ingredients and make the thing, or say why not.
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
		var built: Variant = place_prop(world, str(prop_id))
		if built == null:
			# The ingredients are not spent when there is no room.
			Helpers.say(world, "No room to build here.")
			return false
		for item_id in ingredients:
			Inventory.inv_remove(world, str(item_id), int(ingredients[item_id]))
		Helpers.say(world, "%s built." % str(prop_id).replace("_", " "))
	else:
		for item_id in ingredients:
			Inventory.inv_remove(world, str(item_id), int(ingredients[item_id]))
		var count := int(product.get("count", 0))
		if count == 0:
			count = 1
		var made := str(product["item_id"])
		var left := Inventory.inv_add(world, made, count)
		if left > 0:
			var forward := Targeting.facing_direction(world)
			SysDrops.spawn_drops(
				world, [{"item_id": made, "count": left}], world.player.x, world.player.z,
				float(forward["x"]), float(forward["z"]), 0.3
			)
			Helpers.say(world, "Made %s; the pack is full, so it falls at your feet." % Inventory.item_name(world, made))
		elif count > 1:
			Helpers.say(world, "Made %s (%d)." % [Inventory.item_name(world, made), count])
		else:
			Helpers.say(world, "Made %s." % Inventory.item_name(world, made))
	Helpers.emit(world, {"type": "craft", "recipe": str(recipe["recipe_id"])})
	return true
