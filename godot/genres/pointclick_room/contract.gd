class_name RoomContract
extends RefCounted

## What a point-and-click room says it is.
##
## A port of the simulation's half of `web/lib/pointclick/contract.ts`. The
## fields a view reads — a hotspot's region, its sprite, the scene art — are
## carried through unparsed for the host to check when it draws them; what is
## checked here is everything the reducer reads.

const RUNTIME_KIND := "pointclick-room-runtime-v3"
const RUNTIME_SCHEMA_VERSION := 3

const VERBS := ["inspect", "use"]


## Read a room manifest, or refuse.
static func parse(manifest: Variant) -> Variant:
	if not (manifest is Dictionary):
		return KernelRefusal.of("room/manifest", "a room manifest must be a record")
	var doc: Dictionary = manifest
	if String(doc.get("kind", "")) != RUNTIME_KIND:
		return KernelRefusal.of(
			"room/manifest-kind",
			(
				"unsupported point-and-click room; regenerate this room with a current "
				+ "stage-gen (stage-gen pointclick-room generate)"
			),
			"kind"
		)
	if int(doc.get("schema_version", -1)) != RUNTIME_SCHEMA_VERSION:
		return KernelRefusal.of(
			"room/manifest-kind",
			(
				"unsupported point-and-click room; regenerate this room with a current "
				+ "stage-gen (stage-gen pointclick-room generate)"
			),
			"schema_version"
		)

	var hotspots: Array = []
	var seen := {}
	for entry: Variant in _array(doc.get("hotspots")):
		if not (entry is Dictionary):
			return KernelRefusal.of("room/hotspots", "a hotspot must be a record", "hotspots")
		var hotspot: Dictionary = entry
		var id := String(hotspot.get("id", ""))
		if id.is_empty():
			return KernelRefusal.of("room/hotspots", "a hotspot must name an id", "hotspots")
		if seen.has(id):
			return KernelRefusal.of(
				"room/hotspots", "hotspots names %s twice" % id, "hotspots"
			)
		seen[id] = true
		hotspots.append(
			{
				"id": id,
				"label": String(hotspot.get("label", id)),
				"hidden": bool(hotspot.get("hidden", false)),
				"art": String(hotspot.get("art", "scenery")),
				"sprite": hotspot.get("sprite"),
				"region": hotspot.get("region", {}),
			}
		)

	var interactions: Array = []
	for entry: Variant in _array(doc.get("interactions")):
		if not (entry is Dictionary):
			return KernelRefusal.of(
				"room/interactions", "an interaction must be a record", "interactions"
			)
		var interaction: Dictionary = entry
		var on: Dictionary = interaction.get("on", {})
		var verb := String(on.get("verb", ""))
		if not VERBS.has(verb):
			return KernelRefusal.of(
				"room/interactions",
				"an interaction names the verb %s, which is not one this build performs" % verb,
				"interactions"
			)
		var hotspot_id := String(on.get("hotspot", ""))
		if not seen.has(hotspot_id):
			return KernelRefusal.of(
				"room/interactions",
				"an interaction acts on %s, which this room does not publish" % hotspot_id,
				"interactions"
			)
		var item: Variant = on.get("item")
		interactions.append(
			{
				"verb": verb,
				"hotspot": hotspot_id,
				"item": null if item == null else String(item),
				"requires": _strings(interaction.get("requires")),
				"effects": _array(interaction.get("effects")),
				"narration": String(interaction.get("narration", "")),
			}
		)

	var win: Dictionary = doc.get("win", {})
	return {
		"roomId": String(doc.get("room_id", "")),
		"displayName": String(doc.get("display_name", "")),
		"hotspots": hotspots,
		"interactions": interactions,
		"items": _array(doc.get("items")),
		"win": {
			"requires": _strings(win.get("requires")),
			"narration": String(win.get("narration", "")),
		},
		"scene": doc.get("scene", {}),
		"ui": doc.get("ui", {}),
	}


static func _array(value: Variant) -> Array:
	return value if value is Array else []


static func _strings(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in _array(value):
		made.append(String(entry))
	return made
