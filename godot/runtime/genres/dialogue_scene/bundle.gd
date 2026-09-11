class_name DialogueBundle
extends RefCounted

## What a dialogue-scene run publishes, read once into the shape a view walks.
##
## A port of the runtime's half of `web/lib/dialogue-scene/bundle.ts` and
## `schema.ts`. A run's `bundle.json` carries the union of several scenarios —
## The Grain's carries six — plus every plate, backdrop and track any of them
## names, so reading it takes a `scenario_id` as well as the document. That is
## not a convenience: the browser's own `/scene/<tag>` route omits it and throws
## on every run that exists, because all three published runs carry six.
##
## The document is `lower_snake_case` on the wire and stays that way there; this
## is the adapter, and the names it hands on are the ones the view reads.

const BUNDLE_KIND := "dialogue-scene-bundle-v8"
const BUNDLE_SCHEMA_VERSION := 8

## The state a plate is looked up under when a line names none.
const DEFAULT_EXPRESSION := "neutral"


## Read a run's bundle for one scenario, or refuse.
static func parse(document: Variant, scenario_id: String = "") -> Variant:
	if not (document is Dictionary):
		return KernelRefusal.of("dialogue/bundle", "a scene bundle must be a record")
	var doc: Dictionary = document
	if String(doc.get("kind", "")) != BUNDLE_KIND:
		return KernelRefusal.of(
			"dialogue/bundle-kind",
			(
				"unsupported dialogue scene; regenerate this scene with a current stage-gen "
				+ "(stage-gen dialogue-scene generate)"
			),
			"kind"
		)
	if int(doc.get("schema_version", -1)) != BUNDLE_SCHEMA_VERSION:
		return KernelRefusal.of(
			"dialogue/bundle-kind",
			(
				"unsupported dialogue scene; regenerate this scene with a current stage-gen "
				+ "(stage-gen dialogue-scene generate)"
			),
			"schema_version"
		)
	var scene: Variant = doc.get("scene_data")
	if not (scene is Dictionary):
		return KernelRefusal.of("dialogue/scene-data", "this bundle publishes no scene", "scene_data")
	var data: Dictionary = scene

	var by_id := {}
	for entry: Variant in _array(doc.get("assets")):
		var asset: Dictionary = entry
		by_id[String(asset.get("id", ""))] = String(asset.get("path", ""))

	var scenarios: Array = _array(data.get("scenarios"))
	var ids := PackedStringArray()
	for entry: Variant in scenarios:
		ids.append(String((entry as Dictionary).get("scenario_id", "")))
	if scenarios.is_empty():
		return KernelRefusal.of(
			"dialogue/scenarios", "this bundle publishes no scenario", "scene_data.scenarios"
		)
	var chosen: Dictionary = {}
	if scenario_id.is_empty():
		if scenarios.size() != 1:
			return KernelRefusal.of(
				"dialogue/scenarios",
				(
					"this run publishes %d scenarios (%s); name one with --scenario"
					% [scenarios.size(), ", ".join(ids)]
				),
				"scene_data.scenarios"
			)
		chosen = scenarios[0]
	else:
		for entry: Variant in scenarios:
			if String((entry as Dictionary).get("scenario_id", "")) == scenario_id:
				chosen = entry
				break
		if chosen.is_empty():
			return KernelRefusal.of(
				"dialogue/scenarios",
				"this run publishes no scenario %s; it has %s" % [scenario_id, ", ".join(ids)],
				"scene_data.scenarios"
			)

	var stages: Array = []
	for entry: Variant in _array(data.get("stages")):
		var stage: Dictionary = entry
		var asset_id := String(stage.get("asset_id", ""))
		stages.append(
			{
				"stageId": String(stage.get("stage_id", "")),
				"assetId": asset_id,
				"path": String(by_id.get(asset_id, "")),
				"alt": String(stage.get("alt", "")),
			}
		)
	var tracks: Array = []
	for entry: Variant in _array(data.get("tracks")):
		var track: Dictionary = entry
		var asset_id := String(track.get("asset_id", ""))
		tracks.append(
			{
				"trackId": String(track.get("track_id", "")),
				"assetId": asset_id,
				"path": String(by_id.get(asset_id, "")),
			}
		)
	var actors: Array = []
	for entry: Variant in _array(data.get("actors")):
		var member: Dictionary = entry
		var variants: Array = []
		for raw: Variant in _array(member.get("expression_variants")):
			var variant: Dictionary = raw
			var asset_id := String(variant.get("asset_id", ""))
			variants.append(
				{
					"state": String(variant.get("state", "")),
					"assetId": asset_id,
					"path": String(by_id.get(asset_id, "")),
					"label": String(variant.get("label", "")),
				}
			)
		actors.append(
			{
				"actorId": String(member.get("actor_id", "")),
				"label": String((member.get("appearance", {}) as Dictionary).get("label", "")),
				"expressions": variants,
			}
		)

	# A scene names its interface sheets by asset id where a room names them by
	# path. Both are the document's own vocabulary and neither is wrong; this is
	# the adapter, so the id is resolved here and the view is handed a path like
	# every other genre's.
	var ui: Dictionary = {}
	for role: Variant in (data.get("ui", {}) as Dictionary).keys():
		var block: Dictionary = ((data["ui"] as Dictionary)[role] as Dictionary).duplicate(true)
		if not block.has("asset"):
			block["asset"] = String(by_id.get(String(block.get("asset_id", "")), ""))
		ui[String(role)] = block

	var placement: Dictionary = data.get("placement", {})
	var style_id := String(data.get("style_asset_id", ""))
	return {
		"title": String(data.get("title", "")),
		"sceneLabel": String(data.get("scene_label", "")),
		"stages": stages,
		"tracks": tracks,
		"actors": actors,
		"placement": {
			"framingZoom": float(placement.get("framing_zoom", 0.0)),
			"sourceFramingZoom": float(placement.get("source_framing_zoom", 0.0)),
		},
		"ui": ui,
		"style": String(by_id.get(style_id, "")),
		"scenario": chosen,
		"scenarioId": String(chosen.get("scenario_id", "")),
		"scenarioIds": ids,
	}


## The stage a scenario named, or an empty record.
static func stage(bundle: Dictionary, stage_id: String) -> Dictionary:
	for entry: Variant in (bundle["stages"] as Array):
		var found: Dictionary = entry
		if String(found["stageId"]) == stage_id:
			return found
	return {}


static func track(bundle: Dictionary, track_id: String) -> Dictionary:
	for entry: Variant in (bundle["tracks"] as Array):
		var found: Dictionary = entry
		if String(found["trackId"]) == track_id:
			return found
	return {}


static func actor(bundle: Dictionary, actor_id: String) -> Dictionary:
	for entry: Variant in (bundle["actors"] as Array):
		var found: Dictionary = entry
		if String(found["actorId"]) == actor_id:
			return found
	return {}


## The plate an actor wears in a state, the one it wears in `neutral`, or its
## first — in that order.
##
## The fallback is not a nicety. The Grain's cast has no `neutral` state at all:
## Ruth is `composed`, Edwin is `formal`, and a line that names no expression
## would leave every one of them undrawn without it.
static func expression(bundle: Dictionary, actor_id: String, state: Variant) -> Dictionary:
	var member := actor(bundle, actor_id)
	if member.is_empty():
		return {}
	var variants: Array = member["expressions"]
	if variants.is_empty():
		return {}
	var wanted := DEFAULT_EXPRESSION if state == null else String(state)
	for entry: Variant in variants:
		var variant: Dictionary = entry
		if String(variant["state"]) == wanted:
			return variant
	return variants[0]


## Every plate the view may have to draw, so a host can load them once.
static func plates(bundle: Dictionary) -> Array:
	var found: Array = []
	for entry: Variant in (bundle["actors"] as Array):
		var member: Dictionary = entry
		for raw: Variant in (member["expressions"] as Array):
			var variant: Dictionary = raw
			if String(variant["path"]) != "":
				found.append({"actorId": member["actorId"], "state": variant["state"], "path": variant["path"]})
	return found


static func _array(value: Variant) -> Array:
	return value if value is Array else []
