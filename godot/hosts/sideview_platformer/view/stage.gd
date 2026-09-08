class_name PlatformerStage
extends Node2D

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
	"actors": 0,
	"projectile": 40,
	"foreground": 100,
}

var _package: HostRunDir = null
var _atlas: Dictionary = {}
var _bands: Array = []
var _terrain: Node2D = null
var _portals: Node2D = null
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
	_build_bands(authored, "foreground")


## Move everything that scrolls. `scroll` is the camera's, in world pixels.
func sync(scroll: Vector2) -> void:
	_terrain.position = -scroll
	_portals.position = -scroll
	for entry: Variant in _bands:
		var band: Dictionary = entry
		var sprite: Sprite2D = band["node"]
		# The band wraps rather than scrolls: the region is a whole number of
		# repeats and only its origin moves, so a map wider than its own artwork
		# never runs out of picture.
		var origin := FamilyParallax.band_tile_position(
			scroll.x, float(band["parallax"]), float(band["scale"])
		)
		sprite.region_rect = Rect2(
			fposmod(origin, float(band["sourceWidth"])),
			0.0,
			sprite.region_rect.size.x,
			sprite.region_rect.size.y
		)
		if String(band["space"]) == FamilyParallax.SPACE_WORLD:
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
		var layout := FamilyParallax.layer_layout(
			String(placement.get("vertical_anchor", "")),
			float(placement.get("vertical_offset", 0.0)),
			float(placement.get("source_height", 1.0)),
			float(placement.get("trimmed_height", asset.get("height", 1))),
			VIEW_HEIGHT,
			walk_surface_y,
			float(layer.get("parallax", 0.0))
		)
		if layout.is_empty():
			push_error(
				"platformer stage: layer %s does not describe a band" % layer.get("layer_id", "?")
			)
			continue
		var scale_factor := float(layout["scale"])
		var tile_width := maxi(1, int(round(float(asset.get("width", 1)) * scale_factor)))
		var tile_height := maxi(1, int(round(float(asset.get("height", 1)) * scale_factor)))
		var texture := HostLayerTexture.band(
			_package,
			String(asset.get("path", "")),
			layer.get("presentation", {}),
			tile_width,
			tile_height
		)
		if texture == null:
			push_error(
				(
					"platformer stage: layer %s has no image at %s"
					% [layer.get("layer_id", "?"), asset.get("path", "")]
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
		sprite.position = Vector2(0.0, float(layout["topY"]))
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
				"topY": float(layout["topY"]),
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
	var sheet := _package.texture(String(asset.get("path", "")))
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
