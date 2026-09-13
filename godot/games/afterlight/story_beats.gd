extends RefCounted

## Read-only episode inspection for the game's UI, voice inventory and checks.
## Runtime execution consumes program.json through Scenario Session exclusively.
static var BEATS: Array = _review()


static func _review() -> Array:
	var document: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://narrative/program.json"))
	var catalog: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://narrative/catalog.json"))
	var result: Array = []
	var seen := {}
	for node: Dictionary in document["nodes"]:
		if not node.get("presentation", {}).has("review"): continue
		var item: Dictionary = inspect(node, catalog)
		if seen.has(item["id"]): continue
		seen[item["id"]] = true
		result.append(item)
	return result


static func inspect(node: Dictionary, catalog: Dictionary) -> Dictionary:
	var item: Dictionary = node.get("presentation", {}).get("review", {}).duplicate(true)
	for cue: Dictionary in node.get("cues", []):
		var effect: Dictionary = cue["effect"]
		if effect.has("preset"): effect = catalog["definitions"][effect["preset"]]
		var values: Dictionary = effect.get("parameters", {})
		match effect["type"]:
			"front_background": item["background"] = values["index"]
			"front_cast": item["cast"] = values["actors"].duplicate()
			"front_handoff":
				item["cast"] = [values["outgoing"], values["survivor"], values["incoming"]]
				item["exit_preset"] = values.get("settings", {}).get("exit_preset", "silhouette_fade")
			"front_focus":
				item["focus"] = values.get("preset", "bounce")
				item["focus_replay"] = values.get("replay", false)
			"front_mark":
				item["mark"] = values["sprite"]
				item["mark_preset"] = values.get("preset", "")
			"front_reaction":
				if not item.has("manpu_events"): item["manpu_events"] = []
				item["manpu_events"].append({"actor": values["actor"], "id": values["sprite"], "preset": values["preset"]})
				item["manpu_timing"] = "after_reveal" if cue.get("on") == "text_revealed" else "on_enter"
			"front_camera": item["camera"] = "close" if values.get("mode") == "focus" else "wide"
			"front_eye":
				item["eye_mode"] = values["mode"]
				item["eye_settings"] = values.get("settings", {})
			"front_view":
				for key: String in ["heat", "barrier", "scene_corruption", "duration_seconds"]:
					if values.has(key): item[key] = values[key]
				if values.has("corruption"):
					item["corruption"] = values["corruption"].duplicate(true)
					var area: Variant = item["corruption"].get("area")
					if area is Array: item["corruption"]["area"] = Rect2(area[0], area[1], area[2], area[3])
				item["eye_portrait"] = values.get("portrait_mode") == "eye"
				item["vfx_fade_out"] = values.get("field_envelope") == "fade_out"
			"front_shake": item["shake"] = values.duplicate(true)
			"front_burst", "front_pan", "front_approach":
				var key: String = {"front_burst": "sprite_burst", "front_pan": "cast_pan", "front_approach": "quick_approach"}[effect["type"]]
				item[key] = values.duplicate(true)
				item[key]["delay_seconds"] = cue.get("at", 0.0)
				if key == "sprite_burst" and values.has("origin_uv"): item[key]["origin_uv"] = Vector2(values["origin_uv"][0], values["origin_uv"][1])
			"front_blackout":
				if values.get("strength") == 1: item["background_blackout"] = {"delay_seconds": cue.get("at", 0.0), "fade_seconds": values["duration_seconds"]}
			"front_projection":
				if not values.get("enabled", true):
					if not item.has("physical"): item["physical"] = []
					item["physical"].append(values["actor"])
	return item
