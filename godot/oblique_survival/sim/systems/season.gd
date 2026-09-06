class_name SysSeason
extends RefCounted

## The calendar: which season this day is in, and what it holds. On a turn the
## forage the season hides goes under the snow (and comes back through the
## regrow timer), the world is told, and the event is emitted for the ear.
## Reads `clock`, writes `season` (index.html:1501-1523).

static func update(world: World, _dt: float) -> void:
	var season := world.season
	var now := Helpers.season_for(season, world.day)
	season["index"] = now["index"]
	season["day_in_season"] = now["day_in_season"]
	if String(now["id"]) == String(season["id"]):
		return
	season["id"] = now["id"]
	var specs: Dictionary = season["specs"]
	season["spec"] = specs.get(String(now["id"]), Helpers.NO_SEASON)
	var spec: Dictionary = season["spec"]
	var hidden: Array = spec.get("hidden_forage", [])
	for entity: Dictionary in world.entities:
		if entity["kind"] != "forage":
			continue
		var hide: bool = hidden.has(entity["item_id"])
		if hide == entity["hidden"]:
			continue
		entity["hidden"] = hide
		if not hide and not entity["picked"]:
			entity["taken"] = false
		entity["dirty"] = true
	if int(season["turns"]) > 0 or String(season["force"]) != "auto":
		var name := String(spec.get("display_name", ""))
		world.say("%s comes." % (name if name != "" else "The season"))
	season["turns"] = int(season["turns"]) + 1
	world.emit({"type": "season", "id": now["id"]})
