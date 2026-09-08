class_name PlatformerMaps
extends RefCounted

## The maps a package publishes, the terrain each describes, and the gates
## between them.
##
## A port of the map half of `web/lib/manifest/prepared-manifest.ts` and
## `prepared-terrain.ts`, plus the transition graph the gameplay contract
## carries.
##
## A **transition** is the pair the graph names — a map and one of its anchors —
## and a **spawn** is where the destination puts the body. They are separate on
## purpose: two gates may lead to one spawn, and a spawn is a place in a map
## rather than the far side of a door.

const RUNTIME_KIND := "prepared-game-runtime-v12"
const RUNTIME_SCHEMA_VERSION := 12

## The design space every published rectangle is in.
const VIEW_WIDTH := 1280.0
const VIEW_HEIGHT := 720.0
## Where the ground line sits. Every map's occupancy hangs from it, so a map with
## more rows is taller upward rather than deeper down.
const BASELINE_Y := 720.0
const TILE_PX := 64.0


## Read a prepared-game manifest into the maps and the graph, or refuse.
static func parse(manifest: Variant) -> Variant:
	if not (manifest is Dictionary):
		return KernelRefusal.of("platformer/manifest", "a prepared-game manifest must be a record")
	var doc: Dictionary = manifest
	if String(doc.get("kind", "")) != RUNTIME_KIND:
		return KernelRefusal.of(
			"platformer/manifest-kind",
			(
				"unsupported prepared game; regenerate this package with a current "
				+ "stage-gen (stage-gen generate --genre platformer)"
			),
			"kind"
		)
	if int(doc.get("schema_version", -1)) != RUNTIME_SCHEMA_VERSION:
		return KernelRefusal.of(
			"platformer/manifest-kind",
			(
				"unsupported prepared game; regenerate this package with a current "
				+ "stage-gen (stage-gen generate --genre platformer)"
			),
			"schema_version"
		)

	var climb_artwork := _climb_artwork(doc.get("player", {}))
	var maps := {}
	for entry: Variant in _array(doc.get("maps")):
		var authored: Dictionary = entry
		var built: Variant = _map(authored)
		if KernelRefusal.is_refusal(built):
			return built
		# A rope nobody drew is not a rope a body can climb. Said here, at parse,
		# rather than discovered on the frame a player grabs one: the strip a role
		# climbs on is the package's to publish, and a package that places a
		# climbable it never drew has a hole in it that no host can fill.
		for zone: Variant in ((built as Dictionary)["climbables"] as Array):
			var role := String((zone as Dictionary).get("role", ""))
			if climb_artwork.has(role):
				continue
			return KernelRefusal.of(
				"platformer/maps",
				(
					"%s places the %s %s but this package publishes no %s strip"
					% [
						String(authored.get("map_id", "")),
						role,
						String((zone as Dictionary).get("id", "")),
						String(CLIMB_STATE_BY_ROLE.get(role, role)),
					]
				),
				"player.states"
			)
		maps[String(authored.get("map_id", ""))] = built

	var gameplay: Dictionary = doc.get("gameplay", {})
	var transitions: Array = []
	for entry: Variant in _array(gameplay.get("transitions")):
		var transition: Dictionary = entry
		var to_map := String(transition.get("to_map_id", ""))
		if not maps.has(to_map):
			return KernelRefusal.of(
				"platformer/transitions",
				(
					"transition %s leads to %s, which this package does not publish"
					% [String(transition.get("transition_id", "")), to_map]
				),
				"gameplay.transitions"
			)
		transitions.append(
			{
				"transitionId": String(transition.get("transition_id", "")),
				"fromMapId": String(transition.get("from_map_id", "")),
				"fromAnchor": String(transition.get("from_anchor", "")),
				"toMapId": to_map,
				"toSpawnId": String(transition.get("to_spawn_id", "")),
			}
		)

	var spawns := {}
	for entry: Variant in _array(gameplay.get("spawns")):
		var spawn: Dictionary = entry
		spawns[String(spawn.get("spawn_id", ""))] = {
			"spawnId": String(spawn.get("spawn_id", "")),
			"mapId": String(spawn.get("map_id", "")),
			"anchor": String(spawn.get("anchor", "")),
			"normalizedX": float(spawn.get("normalized_x", 0.0)),
		}

	var player: Dictionary = gameplay.get("player", {})
	return {
		"climbArtwork": climb_artwork,
		# Which poses this package actually drew. Two of them decide what a damaged
		# body wears, because a strip nobody published is a strip no host can play.
		"playerPoses": _player_poses(doc.get("player", {})),
		"gameId": String(doc.get("game_id", "")),
		"displayName": String(doc.get("display_name", "")),
		"maps": maps,
		"transitions": transitions,
		"spawns": spawns,
		"entryMapId": String(doc.get("entry_map_id", "")),
		"entrySpawnId": String(doc.get("entry_spawn_id", "")),
		"startingHealth": int(player.get("starting_health", 6)),
		"startingItemIds": _strings(player.get("starting_item_ids")),
		"startingLevel": int(player.get("starting_level", 1)),
		"combatEnabled": bool((gameplay.get("combat", {}) as Dictionary).get("enabled", false)),
		# The whole combat block, not just its switch: the weapon class a run is
		# played with and the round it throws are read from it, and both are
		# published state a digest carries.
		"combat": gameplay.get("combat", {}),
		# Which conversationalist stands on which map. A prompt is a thing the
		# world publishes, so where they stand is the package's business rather
		# than the host's.
		"npcPlacements": gameplay.get("npc_placements", []),
		# What a villager offers, what an ending is worth, and what a quest step
		# does. Three tables read by one system, carried here rather than looked
		# up out of the raw document by whoever needs them.
		"interactions": gameplay.get("interactions", []),
		"effects": gameplay.get("effects", []),
		"quests": gameplay.get("quests", []),
		"lootRules": gameplay.get("loot_rules", []),
		"progression": gameplay.get("progression", {}),
		"inventory": gameplay.get("inventory", {}),
		"mobPopulation": gameplay.get("mob_population", {}),
		# The authored gates. Four facts each — where one stands, what stands
		# there, what plays while it does, and whether it comes back — and the
		# runtime that came before read exactly one of them.
		"bossEncounters": gameplay.get("boss_encounters", []),
		# The run's own revision, which seeds every population this package
		# spawns: two runs of one package meet the same creatures.
		"revision": int(gameplay.get("revision", 0)),
		"mobs": doc.get("mobs", []),
		"items": doc.get("items", []),
		"projectiles": doc.get("projectiles", []),
		"soundtrack": doc.get("soundtrack", {}),
	}


## Which strip each climbable role climbs on, and how long that strip is.
##
## Two authored states — `climb_ladder` and `climb_rope` — resolve to the one
## body state `climb`: the physics of the two are identical and only the drawing
## differs, so the role selects a strip rather than the state machine carrying
## two climbing states. That is the one entry in the published state vocabulary
## that is not one-to-one, which is why it is resolved here rather than beside
## the other nine.
##
## The frame count is load bearing rather than decorative: a body walks its climb
## strip by *distance* rather than by time, and the count is the modulus that
## turns a rise into a cycle. A run whose package published a two-frame strip and
## whose port assumed four would climb the same ladder in a different pose.
const CLIMB_STATE_BY_ROLE := {"ladder": "climb_ladder", "rope": "climb_rope"}


## The authored pose names, as a set.
static func _player_poses(player: Dictionary) -> Dictionary:
	var made := {}
	var states: Variant = player.get("states")
	if states is Dictionary:
		for name: Variant in (states as Dictionary):
			made[String(name)] = true
	return made


static func _climb_artwork(player: Dictionary) -> Dictionary:
	var states: Dictionary = player.get("states", {})
	var made := {}
	for role: Variant in CLIMB_STATE_BY_ROLE:
		var state := String(CLIMB_STATE_BY_ROLE[role])
		if not (states.get(state) is Dictionary):
			continue
		var binding: Dictionary = states[state]
		var playback: Dictionary = binding.get("playback", {})
		var frames := _array(playback.get("canonical_frame_indices")).size()
		if frames <= 0:
			continue
		made[String(role)] = {
			"animationKey": "player_%s" % state,
			"textureKey": "character_%s" % state,
			"frameCount": frames,
		}
	return made


## Where a body stands when it arrives at a spawn.
static func spawn_position(package: Dictionary, spawn_id: String) -> Dictionary:
	var spawn: Dictionary = (package["spawns"] as Dictionary).get(spawn_id, {})
	if spawn.is_empty():
		return {}
	var map: Dictionary = (package["maps"] as Dictionary).get(String(spawn["mapId"]), {})
	if map.is_empty():
		return {}
	return {
		"mapId": spawn["mapId"],
		"x": float(spawn["normalizedX"]) * float(map["worldWidthPx"]),
		"y": surface_at_x(map, float(spawn["normalizedX"]) * float(map["worldWidthPx"])),
	}


## Which transition a body standing at `x` on `map_id` may take, or an empty
## dictionary. A gate is taken by pressing up while standing in its mouth, so
## this answers only where the body is; the press is the caller's.
static func transition_at(package: Dictionary, map_id: String, x: float) -> Dictionary:
	var map: Dictionary = (package["maps"] as Dictionary).get(map_id, {})
	if map.is_empty():
		return {}
	for entry: Variant in (package["transitions"] as Array):
		var transition: Dictionary = entry
		if String(transition["fromMapId"]) != map_id:
			continue
		var anchor_x: float = -1.0
		for endpoint: Variant in (map["endpoints"] as Array):
			var point: Dictionary = endpoint
			if String(point["anchor"]) == String(transition["fromAnchor"]):
				anchor_x = float(point["normalizedX"]) * float(map["worldWidthPx"])
		if anchor_x < 0.0:
			continue
		# Half a tile either side: the mouth is one tile wide, which is what the
		# artwork is cropped to.
		if absf(x - anchor_x) <= TILE_PX / 2.0:
			return transition
	return {}


## The terrain surface directly under a world x.
static func surface_at_x(map: Dictionary, x: float) -> float:
	var heights: PackedInt32Array = map["heights"]
	var column := mini(
		int(float(map["worldWidthPx"]) / TILE_PX) - 1, int(floor(x / TILE_PX))
	)
	var height := 0
	if column >= 0 and column < heights.size():
		height = heights[column]
	return PlatformerVertical.terrain_surface_y(height, TILE_PX, BASELINE_Y)


static func _map(authored: Dictionary) -> Variant:
	var map_id := String(authored.get("map_id", ""))
	var ground: Dictionary = authored.get("ground", {})
	var occupancy := PackedStringArray()
	for line: Variant in _array(ground.get("occupancy")):
		occupancy.append(String(line))
	if occupancy.is_empty():
		return KernelRefusal.of(
			"platformer/maps", "%s publishes no occupancy grid" % map_id, "maps"
		)
	var columns := occupancy[0].length()
	var heights := FamilySurface.bottom_contiguous_heights(occupancy)
	var world_width := float(columns) * TILE_PX
	var platforms := PlatformerVertical.floating_platforms(
		occupancy, heights, TILE_PX, BASELINE_Y
	)
	# The grid walk produces geometry; this decides whether that geometry is a
	# world. A deck outside the map, or two whose solid bodies intersect, is a
	# package defect — and a package defect that plays is worse than one that
	# refuses, because the first is discovered by a player.
	var deck_defect := PlatformerVertical.deck_refusal(
		platforms,
		columns,
		TILE_PX,
		BASELINE_Y,
		BASELINE_Y - float(occupancy.size()) * TILE_PX,
		world_width
	)
	if not deck_defect.is_empty():
		return KernelRefusal.of("platformer/maps", "%s: %s" % [map_id, deck_defect], "ground")
	var variants := {}
	var placements: Array = []
	var climbable: Variant = authored.get("climbable")
	if climbable is Dictionary:
		for entry: Variant in _array((climbable as Dictionary).get("variants")):
			var variant: Dictionary = entry
			variants[String(variant.get("variant_id", ""))] = variant
		placements = _array((climbable as Dictionary).get("placements"))
	var climbables: Variant = PlatformerVertical.climbable_zones(
		placements, variants, platforms, heights, TILE_PX, BASELINE_Y, world_width
	)
	if KernelRefusal.is_refusal(climbables):
		return climbables
	var endpoints: Array = []
	var portal: Variant = authored.get("portal")
	if portal is Dictionary:
		for entry: Variant in _array((portal as Dictionary).get("endpoints")):
			var point: Dictionary = entry
			endpoints.append(
				{
					"anchor": String(point.get("anchor", "")),
					"normalizedX": float(point.get("normalized_x", 0.0)),
					"role": String(point.get("role", "")),
				}
			)
	return {
		"mapId": map_id,
		"occupancy": occupancy,
		"heights": heights,
		"columns": columns,
		"rows": occupancy.size(),
		"worldWidthPx": world_width,
		"platforms": platforms,
		"climbables": climbables,
		"endpoints": endpoints,
		"displayName": String(authored.get("display_name", "")),
		# What this map is *for*, which is what a recovery reads: a settlement, a
		# route, a dungeon. The word itself is the package's; what counts as safe
		# is the genre's.
		"role": String(authored.get("role", "")),
		"hostilePopulationEnabled": bool(authored.get("hostile_population_enabled", false)),
		# An axis is switched off by giving the camera no room to travel along
		# it, so what a map authors is which axes it *has*, and the bounds do the
		# rest. The village follows x alone; the road is tall enough to follow
		# both.
		"followsY": _strings((authored.get("camera", {}) as Dictionary).get("follow_axes")).has("y"),
		"trackIds": _strings(authored.get("track_ids")),
	}


static func _array(value: Variant) -> Array:
	return value if value is Array else []


static func _strings(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	for entry: Variant in _array(value):
		made.append(String(entry))
	return made
