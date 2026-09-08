class_name RunnerBossView
extends Node2D

## The boss and its shots on screen.
##
## A port of `web/lib/sideview-runner/boss-view.ts`. Everything here is a
## projection of the director's state: it decides no outcome and reads no clock
## of its own — the bob rides the simulation's clock so a replayed run draws
## identical frames, and the hit flash is a comparison against a timestamp the
## director stamped.
##
## The boss sits one rung behind the avatar and its shots one rung in front, so
## a salvo crossing the body reads as passing between the two rather than
## disappearing behind either.
##
## Nothing drew this before. The fight ran — the boss took hits, fired salvos
## and killed the player — with not one pixel of it on screen, which is what
## "it just dies on its own" was.

var _boss: RunnerActor = null
var _shots: Node2D = null
var _shot_views: Dictionary = {}
var _projectiles: Dictionary = {}
var _config: Dictionary = {}


## Build the view, or null when this run plays without fights or its boss
## cannot be loaded.
static func of(
	package: HostRunDir, config: Dictionary, boss_depth: int, shot_depth: int,
	flash_shader: Shader
) -> RunnerBossView:
	var encounter: Dictionary = config.get("encounter", {})
	if encounter.is_empty():
		return null
	var published := {}
	for entry: Variant in (package.manifest.get("bosses", []) as Array):
		var candidate: Dictionary = entry
		if String(candidate["boss_id"]) == String(encounter["bossId"]):
			published = candidate
	if published.is_empty():
		push_error("runner boss view: this run declares %s and publishes no such boss" % encounter["bossId"])
		return null
	var actor := RunnerActor.of(
		package, published.get("motions", []), published.get("calibration", {}), config,
		flash_shader
	)
	if actor == null:
		return null
	var view := RunnerBossView.new()
	view._config = config
	view._boss = actor
	actor.z_index = boss_depth
	actor.visible = false
	view.add_child(actor)
	view._shots = Node2D.new()
	view._shots.z_index = shot_depth
	view.add_child(view._shots)
	for entry: Variant in (package.manifest.get("projectiles", []) as Array):
		var projectile: Dictionary = entry
		view._projectiles[String(projectile["projectile_id"])] = {
			"texture": package.trimmed_texture(String(projectile["image"])),
			"lengthUnits": float(projectile.get("length_units", 0.0)),
			"silhouette": String(projectile.get("silhouette", "")),
		}
	return view


func sync(world: RunnerWorld, dt: float) -> void:
	var state := world.encounter
	var encounter: Dictionary = world.config.get("encounter", {})
	if state.is_empty() or encounter.is_empty():
		return
	var clock_ms := float(world.vitals.get("clockMs", 0.0))
	var boss: Dictionary = state.get("boss", {})
	if boss.is_empty():
		_boss.visible = false
	else:
		_sync_boss(boss, clock_ms, dt)
	_sync_shots(state.get("shots", []), encounter)


func _sync_boss(boss: Dictionary, clock_ms: float, dt: float) -> void:
	_boss.visible = true
	_boss.show_motion(String(boss["motion"]), int(boss.get("attackImpulses", 0)))
	_boss.advance(dt)
	# The hover bobs; a dying machine does not, because it is falling.
	var bob := 0.0 if String(boss["motion"]) == "death" else RunnerEncounterState.boss_bob_rows(clock_ms)
	_boss.place(
		RunnerEncounterState.offset_screen_x(
			float(boss["offsetColumns"]),
			float(_config["avatarScreenX"]),
			float(_config["tilePx"])
		),
		RunnerContract.row_to_screen_y(float(boss["y"]) + bob, _config)
	)
	var struck: Variant = boss.get("lastHitAtMs")
	_boss.set_flash(
		struck != null and clock_ms - float(struck) < RunnerEncounterState.HIT_FLASH_MS
	)


func _sync_shots(shots: Array, encounter: Dictionary) -> void:
	var live := {}
	for entry: Variant in shots:
		var shot: Dictionary = entry
		var id := int(shot["id"])
		live[id] = true
		var sprite: Sprite2D = _shot_views.get(id)
		if sprite == null:
			sprite = _build_shot(shot, encounter)
			if sprite == null:
				continue
			_shot_views[id] = sprite
			_shots.add_child(sprite)
		sprite.position = Vector2(
			RunnerEncounterState.offset_screen_x(
				float(shot["x"]), float(_config["avatarScreenX"]), float(_config["tilePx"])
			) - sprite.scale.x * float(sprite.texture.get_width()) / 2.0,
			(
				RunnerContract.row_to_screen_y(float(shot["row"]), _config)
				- sprite.scale.y * float(sprite.texture.get_height()) / 2.0
			)
		)
	# A shot that left the arena leaves the picture with it.
	for id: Variant in _shot_views.keys():
		if live.has(id):
			continue
		(_shot_views[id] as Node).queue_free()
		_shot_views.erase(id)


func _build_shot(shot: Dictionary, encounter: Dictionary) -> Sprite2D:
	var projectile_id := String(
		encounter["bossProjectileId"] if String(shot["owner"]) == "boss"
		else encounter["playerProjectileId"]
	)
	var drawn: Dictionary = _projectiles.get(projectile_id, {})
	var texture: Texture2D = drawn.get("texture")
	if texture == null:
		push_error("runner boss view: projectile %s has no image" % projectile_id)
		return null
	var sprite := Sprite2D.new()
	sprite.texture = texture
	sprite.centered = false
	# The declared length is along the travel axis, which is the drawn width;
	# the height follows from the raster's own aspect, so a thick knot and a
	# slim pin of the same declared length stay in proportion rather than both
	# being squared off.
	var length_units := float(drawn.get("lengthUnits", 0.0))
	if length_units <= 0.0:
		length_units = float(encounter.get("projectileHeightRows", 1.0))
	var length_px := (
		length_units * float(_config["playerHeightTiles"]) * float(_config["tilePx"])
	)
	var draw_scale := length_px / maxf(1.0, float(texture.get_width()))
	sprite.scale = Vector2(draw_scale, draw_scale)
	# Every projectile is drawn pointing right, so only a leftward shot is
	# mirrored; a radial silhouette reads the same either way and is left alone.
	if float(shot["vx"]) < 0.0 and String(drawn.get("silhouette", "")) != "radial_v1":
		sprite.scale.x = -draw_scale
		sprite.offset.x = float(texture.get_width())
	return sprite


## A restart throws the fight away; the shots in flight go with it.
func clear_shots() -> void:
	for id: Variant in _shot_views.keys():
		(_shot_views[id] as Node).queue_free()
	_shot_views.clear()
	if _boss != null:
		_boss.visible = false
