class_name PlatformerStage
extends Node2D

const Parallax = preload("res://addons/sideview_rendering/parallax.gd")
const ImageBaker = preload("res://addons/sideview_rendering/image_baker.gd")
const SideviewRefusal = preload("res://addons/sideview_rendering/refusal.gd")

## The map, drawn: the bands behind it, the ground it stands on, and the gates
## out of it.
##
## Everything here is a mirror of what the world says now. Nothing reads an
## event and nothing decides a rule — a band's parallax, a square's cell and a
## gate's place are all published, and this puts them where the manifest says.
##
## The design space is the browser's 1280x720. The camera scrolls inside it and
## the whole canvas is scaled to the window by the frame owner, so a published
## rectangle lands where the producer drew it whatever the display does.

const VIEW_WIDTH := 1280.0
const VIEW_HEIGHT := 720.0

## Back to front, and the gaps are deliberate: a band's own `order` is added to
## its plane's rung, so a map with four background bands still sits under the
## world.
const DEPTHS := {
	"background": -400,
	"terrain": -100,
	"portal": -50,
	"climbable": -40,
	"prop": -20,
	"actors": 0,
	"npc": 20,
	"projectile": 40,
	"foreground": 100,
}

var _package: HostRunDir = null
var _atlas: Dictionary = {}
var _bands: Array = []
var _terrain: Node2D = null
## The offer a gate makes. `▲` is the key it is asking for, which is the same
## glyph the villagers ask with — one gesture, said the same way twice.
const GATE_PROMPT_TEXT := "▲ Enter"
const GATE_PROMPT_SIZE := 18
const GATE_PROMPT_WIDTH := 320.0
## How far above the feet the offer floats: clear of the body, under the numbers.
const GATE_PROMPT_LIFT := 210.0
const GATE_PROMPT_COLOR := Color(1.0, 0.874, 0.541)
const GATE_PROMPT_OUTLINE := Color(0.063, 0.055, 0.078, 0.9)

var _portals: Node2D = null
## The offer a gate makes when the body is standing in its mouth, and the gate it
## is currently made over.
var _gate_prompt: Label = null
var _climbables: Node2D = null
var _map_id: String = ""


static func of(package: HostRunDir, atlas: Dictionary) -> PlatformerStage:
	var made := PlatformerStage.new()
	made._package = package
	made._atlas = atlas
	made._terrain = Node2D.new()
	made._terrain.z_index = DEPTHS["terrain"]
	made.add_child(made._terrain)
	made._portals = Node2D.new()
	made._portals.z_index = DEPTHS["portal"]
	made.add_child(made._portals)
	# Over the gates rather than among them, so a mouth drawn behind the body does
	# not take its own offer with it.
	made._gate_prompt = Label.new()
	made._gate_prompt.z_index = DEPTHS["foreground"] + 30
	made._gate_prompt.add_theme_font_size_override("font_size", GATE_PROMPT_SIZE)
	made._gate_prompt.add_theme_color_override("font_color", GATE_PROMPT_COLOR)
	made._gate_prompt.add_theme_color_override("font_outline_color", GATE_PROMPT_OUTLINE)
	made._gate_prompt.add_theme_constant_override("outline_size", 5)
	made._gate_prompt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	made._gate_prompt.size = Vector2(GATE_PROMPT_WIDTH, float(GATE_PROMPT_SIZE) * 1.4)
	made._gate_prompt.visible = false
	made.add_child(made._gate_prompt)
	made._climbables = Node2D.new()
	made._climbables.z_index = DEPTHS["climbable"]
	made.add_child(made._climbables)
	return made


## Rebuild for the map the run has arrived on. Called once at boot and again at
## every gate, because a map is a whole picture rather than a change to one.
func open_on(world: PlatformerWorld) -> void:
	if world.map_id == _map_id:
		return
	_map_id = world.map_id
	var authored := _authored_map(world)
	if authored.is_empty():
		push_error("platformer stage: %s is not a map this package publishes" % _map_id)
		return
	_clear()
	_build_bands(authored, "background")
	_build_terrain(authored)
	_build_portals(world, authored)
	_build_climbables(world, authored)
	_build_bands(authored, "foreground")


## Move everything that scrolls, and make the offer a gate makes when the body is
## standing in one. `scroll` is the camera's, in world pixels.
func sync(world: PlatformerWorld, scroll: Vector2) -> void:
	_terrain.position = -scroll
	_portals.position = -scroll
	_sync_gate_prompt(world, scroll)
	_climbables.position = -scroll
	for entry: Variant in _bands:
		var band: Dictionary = entry
		var sprite: Sprite2D = band["node"]
		# The band wraps rather than scrolls: the region is a whole number of
		# repeats and only its origin moves, so a map wider than its own artwork
		# never runs out of picture.
		var origin: Variant = Parallax.band_tile_position(
			scroll.x, float(band["parallax"]), float(band["scale"])
		)
		if SideviewRefusal.is_refusal(origin):
			push_error("platformer stage: %s" % SideviewRefusal.line(origin))
			continue
		sprite.region_rect = Rect2(
			fposmod(float(origin), float(band["sourceWidth"])),
			0.0,
			sprite.region_rect.size.x,
			sprite.region_rect.size.y
		)
		if String(band["space"]) == Parallax.SPACE_WORLD:
			sprite.position.y = float(band["topY"]) - scroll.y
		else:
			sprite.position.y = float(band["topY"]) - scroll.y * float(band["parallax"])


func _build_bands(authored: Dictionary, plane: String) -> void:
	var walk_surface_y := _walk_surface_y(authored)
	for entry: Variant in (authored.get("layers", []) as Array):
		var layer: Dictionary = entry
		if String(layer.get("plane", "")) != plane:
			continue
		var placement: Dictionary = layer.get("placement", {})
		var asset: Dictionary = layer.get("asset", {})
		var layout := Parallax.layer_layout(
			String(placement.get("vertical_anchor", "")),
			float(placement.get("vertical_offset", 0.0)),
			float(placement.get("source_height", 1.0)),
			float(placement.get("trimmed_height", asset.get("height", 1))),
			VIEW_HEIGHT,
			walk_surface_y,
			float(layer.get("parallax", 0.0))
		)
		if SideviewRefusal.is_refusal(layout):
			push_error(
				"platformer stage: layer %s: %s" % [layer.get("layer_id", "?"), SideviewRefusal.line(layout)]
			)
			continue
		var scale_factor := float(layout["scale"])
		var tile_width := maxi(1, int(round(float(asset.get("width", 1)) * scale_factor)))
		var tile_height := maxi(1, int(round(float(asset.get("height", 1)) * scale_factor)))
		var texture: Variant = ImageBaker.texture(
			_package.image(String(asset.get("path", ""))),
			layer.get("presentation", {}),
			tile_width,
			tile_height
		)
		if SideviewRefusal.is_refusal(texture):
			push_error(
				(
					"platformer stage: layer %s: %s"
					% [layer.get("layer_id", "?"), SideviewRefusal.line(texture)]
				)
			)
			continue
		var sprite := Sprite2D.new()
		sprite.texture = texture
		sprite.centered = false
		sprite.region_enabled = true
		# Enough whole repeats to cover the viewport from wherever the wrap has
		# put the left edge, counted in tiles rather than screens: a tile
		# narrower than the canvas would otherwise leave a bare strip.
		var repeats := 1 + int(ceil(VIEW_WIDTH / float(tile_width)))
		sprite.region_rect = Rect2(0.0, 0.0, float(tile_width * repeats), float(tile_height))
		sprite.texture_repeat = CanvasItem.TEXTURE_REPEAT_ENABLED
		sprite.position = Vector2(0.0, float(layout["top_y"]))
		sprite.z_index = (
			(DEPTHS["background"] if plane == "background" else DEPTHS["foreground"])
			+ int(layer.get("order", 0))
		)
		add_child(sprite)
		_bands.append(
			{
				"node": sprite,
				"parallax": float(layer.get("parallax", 0.0)),
				"scale": scale_factor,
				"sourceWidth": float(tile_width),
				"topY": float(layout["top_y"]),
				"space": String(layout["space"]),
			}
		)


## One sprite per filled square, each cut from the sheet by what its neighbours
## are doing.
func _build_terrain(authored: Dictionary) -> void:
	var ground: Dictionary = authored.get("ground", {})
	var asset: Dictionary = ground.get("asset", {})
	var sheet := _package.texture(String(asset.get("path", "")))
	if sheet == null:
		push_error("platformer stage: this map publishes no ground sheet")
		return
	var occupancy := PackedStringArray()
	for entry: Variant in (ground.get("occupancy", []) as Array):
		occupancy.append(String(entry))
	if occupancy.is_empty():
		return
	var cell_width := float(sheet.get_width()) / float(FamilyTerrainAtlas.COLUMNS)
	var cell_height := float(sheet.get_height()) / float(FamilyTerrainAtlas.ROWS)
	var tile := PlatformerMaps.TILE_PX
	# The art overhangs its own footing, so a square is drawn a little above the
	# line a body stands on rather than starting at it.
	var inset := FamilyTerrainAtlas.walk_surface_offset(tile)
	var top_row_y := PlatformerMaps.BASELINE_Y - float(occupancy.size()) * tile
	for entry: Variant in FamilyTerrainAtlas.overscan_plan(occupancy):
		var cell: Dictionary = entry
		var at: Array = FamilyTerrainAtlas.cell_for(_atlas, String(cell["mask"]))
		var sprite := Sprite2D.new()
		sprite.texture = sheet
		sprite.centered = false
		sprite.region_enabled = true
		sprite.region_rect = Rect2(
			float(at[0]) * cell_width, float(at[1]) * cell_height, cell_width, cell_height
		)
		sprite.position = Vector2(
			float(cell["column"]) * tile, top_row_y + float(cell["row"]) * tile - inset
		)
		sprite.scale = Vector2(tile / cell_width, tile / cell_height)
		_terrain.add_child(sprite)


func _build_portals(world: PlatformerWorld, authored: Dictionary) -> void:
	var portal: Dictionary = authored.get("portal", {})
	var asset: Dictionary = portal.get("asset", {})
	var path := String(asset.get("path", ""))
	if path.is_empty():
		return
	var sheet := _package.texture(path)
	if sheet == null:
		return
	# A pair sheet holds both mouths side by side: the entry on the left, the
	# exit on the right.
	var half := float(sheet.get_width()) / 2.0
	for entry: Variant in world.portals:
		var gate: Dictionary = entry
		var sprite := Sprite2D.new()
		sprite.texture = sheet
		sprite.centered = false
		sprite.region_enabled = true
		sprite.region_rect = Rect2(
			0.0 if String(gate["kind"]) == "entry" else half,
			0.0,
			half,
			float(sheet.get_height())
		)
		var height := float(gate["h"])
		var width := height * (half / maxf(1.0, float(sheet.get_height())))
		sprite.scale = Vector2(width / half, height / float(sheet.get_height()))
		sprite.position = Vector2(float(gate["x"]) - width / 2.0, float(gate["y"]) - height)
		_portals.add_child(sprite)


## The ladders and ropes, each cut from the map's own climbable sheet.
##
## A climbable is drawn taller than the rise it spans: it overshoots the deck it
## reaches by half a tile and the ground it stands on by the same, so it reads as
## fixed to both rather than as floating between them.
func _build_climbables(world: PlatformerWorld, authored: Dictionary) -> void:
	var block: Dictionary = authored.get("climbable", {})
	var path := String((block.get("asset", {}) as Dictionary).get("path", ""))
	if path.is_empty():
		return
	var sheet := _package.texture(path)
	if sheet == null:
		return
	var cells := {}
	for entry: Variant in (block.get("variants", []) as Array):
		var variant: Dictionary = entry
		cells[String(variant.get("variant_id", ""))] = variant.get("cell", {})
	var map: Dictionary = (world.package["maps"] as Dictionary)[_map_id]
	for entry: Variant in (map["climbables"] as Array):
		var zone: Dictionary = entry
		var cell: Dictionary = cells.get(String(zone["variantId"]), {})
		if cell.is_empty():
			push_error(
				"platformer stage: climbable %s names a variant this map does not publish"
				% zone["id"]
			)
			continue
		var top := float(zone["upperDeckY"]) - float(zone["visualTopOvershoot"])
		var bottom := float(zone["lowerSurfaceY"]) + float(zone["visualBottomOvershoot"])
		var width := float(zone["visualWidth"])
		var sprite := Sprite2D.new()
		sprite.texture = sheet
		sprite.centered = false
		sprite.region_enabled = true
		sprite.region_rect = Rect2(
			float(cell["x"]), float(cell["y"]), float(cell["width"]), float(cell["height"])
		)
		sprite.position = Vector2(float(zone["centerX"]) - width / 2.0, top)
		sprite.scale = Vector2(
			width / maxf(1.0, float(cell["width"])),
			(bottom - top) / maxf(1.0, float(cell["height"]))
		)
		_climbables.add_child(sprite)


## The screen line the ground meets, which is what a `walk_surface` band is
## anchored to.
func _walk_surface_y(authored: Dictionary) -> float:
	var ground: Dictionary = authored.get("ground", {})
	var rows: Array = ground.get("occupancy", [])
	var surface_row := int(ground.get("walk_surface_row", rows.size()))
	return PlatformerMaps.BASELINE_Y - float(rows.size() - surface_row) * PlatformerMaps.TILE_PX


func _authored_map(world: PlatformerWorld) -> Dictionary:
	for entry: Variant in (world.manifest.get("maps", []) as Array):
		var map: Dictionary = entry
		if String(map.get("map_id", "")) == _map_id:
			return map
	return {}


func _clear() -> void:
	for entry: Variant in _bands:
		(entry as Dictionary)["node"].queue_free()
	_bands = []
	for child in _terrain.get_children():
		child.queue_free()
	for child in _portals.get_children():
		child.queue_free()
	for child in _climbables.get_children():
		child.queue_free()


## The offer a gate makes, when the body is standing in its mouth.
##
## A door that opens on a key press and says nothing is a door a player walks past.
## The villagers have said what they want pressed since the port began; the gates
## out of a map never did, and they are the one affordance a player cannot discover
## by bumping into it — walking into a gate does nothing at all, which reads as a
## wall rather than as a door waiting to be asked.
##
## The question is the *simulation's* own, asked one frame early: the same
## `transition_at` the entry system reads decides both whether a press would work
## and whether the offer is shown, so the label can never appear over a mouth that
## would refuse it, or stay hidden over one that would not.
func _sync_gate_prompt(world: PlatformerWorld, scroll: Vector2) -> void:
	if world.hold:
		_gate_prompt.visible = false
		return
	var standing := PlatformerMaps.transition_at(
		world.package, world.map_id, float(world.player["x"])
	)
	if standing.is_empty():
		_gate_prompt.visible = false
		return
	# The place it leads, so a player knows what they are agreeing to rather than
	# only that a key does something here.
	var going: Dictionary = (world.package["spawns"] as Dictionary).get(
		String(standing["toSpawnId"]), {}
	)
	var named := ""
	if not going.is_empty():
		var map: Dictionary = (world.package["maps"] as Dictionary).get(
			String(going["mapId"]), {}
		)
		named = str(map.get("displayName", "")).strip_edges()
	_gate_prompt.text = GATE_PROMPT_TEXT if named.is_empty() else "%s %s" % [GATE_PROMPT_TEXT, named]
	_gate_prompt.visible = true
	_gate_prompt.position = Vector2(
		float(world.player["x"]) - scroll.x - GATE_PROMPT_WIDTH / 2.0,
		float(world.player["y"]) - scroll.y - GATE_PROMPT_LIFT
	)
