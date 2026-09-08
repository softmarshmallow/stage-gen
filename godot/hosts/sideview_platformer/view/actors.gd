class_name PlatformerActors
extends Node2D

## Everything that moves: the body, the creatures, and the rounds in the air.
##
## One node per living thing, kept alongside the world's own list rather than
## inside it — a world is scalars and dictionaries so that it can be compared
## against another implementation of itself, and a sprite is not comparable.
## The pairing is by instance id, which is what the world already names them by.
##
## Sizes come from the ruler and never from the pixels: `source_px_per_unit` is
## how many source pixels the producer drew one unit of height as, and a strip
## redrawn at another resolution carries a different one and stands exactly as
## tall. `HostActor` owns that arithmetic for every genre.

## How tall the body and a creature stand, in tiles of the world's own grid.
const PLAYER_HEIGHT_TILES := 154.0 / 64.0
const MOB_HEIGHT_TILES := 110.0 / 64.0

var _package: HostRunDir = null
var _player: HostActor = null
var _mobs: Dictionary = {}
var _shots: Dictionary = {}
var _mob_specs: Dictionary = {}
var _shot_texture: Texture2D = null
var _item_textures: Array = []
var _drops: Dictionary = {}


static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerActors:
	var made := PlatformerActors.new()
	made._package = package
	made.z_index = PlatformerStage.DEPTHS["actors"]
	made._player = HostActor.of(
		package,
		_motions(manifest.get("player", {})),
		(manifest.get("player", {}) as Dictionary).get("calibration", {}),
		{"playerHeightTiles": PLAYER_HEIGHT_TILES, "tilePx": PlatformerMaps.TILE_PX},
		null
	)
	if made._player != null:
		made.add_child(made._player)
	for entry: Variant in (manifest.get("mobs", []) as Array):
		var spec: Dictionary = entry
		made._mob_specs[str(spec.get("mob_id", ""))] = spec
	for entry: Variant in (manifest.get("items", []) as Array):
		var item: Dictionary = entry
		made._item_textures.append(
			package.trimmed_texture(str((item.get("asset", {}) as Dictionary).get("path", "")))
		)
	var rounds: Array = manifest.get("projectiles", [])
	if not rounds.is_empty():
		made._shot_texture = package.trimmed_texture(
			str(((rounds[0] as Dictionary).get("asset", {}) as Dictionary).get("path", ""))
		)
	return made


## Put every living thing where the world says it is.
func sync(world: PlatformerWorld, scroll: Vector2, dt: float) -> void:
	if _player != null:
		_player.show_motion(_player_strip(world), int(world.player["airJumpsUsed"]))
		_player.advance(dt)
		_player.place(
			float(world.player["x"]) - scroll.x, float(world.player["y"]) - scroll.y
		)
		_player.flip_h = str(world.player["facing"]) == PlatformerPlayer.FACING_LEFT
	_sync_mobs(world, scroll, dt)
	_sync_shots(world, scroll)
	_sync_drops(world, scroll)


## Which strip the body plays. The world's own state names it, except that a
## published package spells two of them differently.
func _player_strip(world: PlatformerWorld) -> String:
	var state := str(world.player["state"])
	match state:
		"attack":
			return "basic_attack"
		"ranged_attack":
			return "skill_cast"
		"climb":
			return "climb_ladder"
		_:
			return state


func _sync_mobs(world: PlatformerWorld, scroll: Vector2, dt: float) -> void:
	var seen := {}
	for entry: Variant in world.mobs:
		var mob: Dictionary = entry
		var id := str(mob["instanceId"])
		seen[id] = true
		if not _mobs.has(id):
			var made := _make_mob(world, mob)
			if made == null:
				continue
			_mobs[id] = made
			add_child(made)
		var actor: HostActor = _mobs[id]
		actor.visible = bool(mob["alive"])
		actor.show_motion(_mob_strip(str(mob["state"])))
		actor.advance(dt)
		actor.place(float(mob["x"]) - scroll.x, float(mob["y"]) - scroll.y)
		actor.flip_h = int(mob["facing"]) < 0
	# A creature the world has forgotten is taken off the screen with it. The
	# world is the only record of what is alive; a node that outlived its entry
	# would stand there forever with nothing stepping it.
	for id: Variant in _mobs.keys():
		if not seen.has(id):
			(_mobs[id] as Node).queue_free()
			_mobs.erase(id)


## Creature strips are published under the creature's own name.
func _mob_strip(state: String) -> String:
	match state:
		"chase", "return_home", "attack_recovery":
			return "idle"
		"windup":
			return "attack"
		"dead":
			return "death"
		_:
			return state if state == "hurt" else "idle"


func _make_mob(world: PlatformerWorld, mob: Dictionary) -> HostActor:
	var catalogue: Array = world.package["mobs"]
	var index := int(mob["ladderIndex"])
	if index < 0 or index >= catalogue.size():
		return null
	var spec: Dictionary = catalogue[index]
	return HostActor.of(
		_package,
		_motions(spec),
		spec.get("calibration", {}),
		{"playerHeightTiles": MOB_HEIGHT_TILES, "tilePx": PlatformerMaps.TILE_PX},
		null
	)


func _sync_shots(world: PlatformerWorld, scroll: Vector2) -> void:
	var seen := {}
	for entry: Variant in world.projectiles:
		var shot: Dictionary = entry
		var id := str(shot["id"])
		seen[id] = true
		if not _shots.has(id):
			if _shot_texture == null:
				continue
			var sprite := Sprite2D.new()
			sprite.texture = _shot_texture
			sprite.z_index = PlatformerStage.DEPTHS["projectile"]
			# Drawn to a fixed length rather than to its own pixels: a round is
			# a size in the world, and the artwork is whatever resolution it was
			# generated at.
			var drawn := PlatformerMaps.TILE_PX * 0.7
			sprite.scale = Vector2.ONE * (drawn / maxf(1.0, float(_shot_texture.get_width())))
			_shots[id] = sprite
			add_child(sprite)
		var node: Sprite2D = _shots[id]
		node.position = Vector2(float(shot["x"]) - scroll.x, float(shot["y"]) - scroll.y)
		node.rotation_degrees = float(shot["spinDegrees"])
		node.flip_h = int(shot["dirSign"]) < 0
	for id: Variant in _shots.keys():
		if not seen.has(id):
			(_shots[id] as Node).queue_free()
			_shots.erase(id)


## What is lying on the ground, drawn to a fixed height so a thing is a size in
## the world rather than whatever resolution its picture was generated at.
func _sync_drops(world: PlatformerWorld, scroll: Vector2) -> void:
	var seen := {}
	for entry: Variant in world.world_items:
		var item: Dictionary = entry
		var id := str(item["id"])
		var kind := int(item["kindIndex"])
		seen[id] = true
		if not _drops.has(id):
			if kind < 0 or kind >= _item_textures.size() or _item_textures[kind] == null:
				continue
			var texture: Texture2D = _item_textures[kind]
			var sprite := Sprite2D.new()
			sprite.texture = texture
			sprite.centered = false
			sprite.z_index = PlatformerStage.DEPTHS["projectile"] - 1
			var drawn := PlatformerMaps.TILE_PX * 0.7
			sprite.scale = Vector2.ONE * (drawn / maxf(1.0, float(texture.get_height())))
			_drops[id] = sprite
			add_child(sprite)
		var node: Sprite2D = _drops[id]
		var drawn_size := node.texture.get_size() * node.scale
		var body: Dictionary = item["body"]
		node.position = Vector2(
			float(body["x"]) - scroll.x - drawn_size.x / 2.0, float(body["y"]) - scroll.y - drawn_size.y
		)
	for id: Variant in _drops.keys():
		if not seen.has(id):
			(_drops[id] as Node).queue_free()
			_drops.erase(id)


## A published `states` block, in the shape `HostActor` reads motions in.
static func _motions(spec: Dictionary) -> Array:
	var made: Array = []
	for name: Variant in (spec.get("states", {}) as Dictionary):
		var state: Dictionary = (spec["states"] as Dictionary)[name]
		var playback: Dictionary = state.get("playback", {})
		var rebase: Dictionary = (spec.get("calibration", {}) as Dictionary).get("state_rebase", {})
		made.append(
			{
				"state": str(name),
				"atlas": str((state.get("asset", {}) as Dictionary).get("path", "")),
				"columns": int(state.get("columns", 1)),
				"frames_per_second": float(playback.get("frames_per_second", 12)),
				"playback_mode": str(playback.get("mode", "once")),
				"canonical_frame_indices": playback.get("canonical_frame_indices", []),
				"rebase_multiplier": float(rebase.get(str(name), 1.0)),
				"anchor": str(state.get("anchor", "bottom")),
			}
		)
	return made
