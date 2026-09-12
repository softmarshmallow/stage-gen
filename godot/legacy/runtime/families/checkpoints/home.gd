class_name FamilyCheckpoints
extends RefCounted

## Where a recovery puts a body.
##
## A port of `web/lib/families/checkpoints/home.ts`. The genre hands in the word
## it calls a safe place — a settlement, a save room, the last lit brazier — and
## the rule is the same underneath all three: the run resumes somewhere nothing
## hunts.
##
## The entry spawn is preferred when it is already somewhere safe, because a
## package that opens in its own village means that village. Otherwise the first
## safe map that has a spawn wins, and a package with no safe map at all gets its
## entry spawn back rather than nothing: a recovery that refused would end the
## session on the first death, which is the one outcome a package without saves
## cannot afford.


## `{spawnId, mapId}` of the place a defeated body comes back to.
static func respawn_target(
	entry_spawn_id: String, spawns: Dictionary, maps: Dictionary, safe_role: String
) -> Dictionary:
	var entry: Dictionary = spawns.get(entry_spawn_id, {})
	if entry.is_empty():
		return {}
	if _is_safe(maps, String(entry["mapId"]), safe_role):
		return entry
	var map_ids := maps.keys()
	map_ids.sort()
	for map_id: Variant in map_ids:
		if not _is_safe(maps, String(map_id), safe_role):
			continue
		for spawn_id: Variant in spawns:
			var spawn: Dictionary = spawns[spawn_id]
			if String(spawn["mapId"]) == String(map_id):
				return spawn
	return entry


static func _is_safe(maps: Dictionary, map_id: String, safe_role: String) -> bool:
	var map: Dictionary = maps.get(map_id, {})
	return not map.is_empty() and String(map["role"]) == safe_role
