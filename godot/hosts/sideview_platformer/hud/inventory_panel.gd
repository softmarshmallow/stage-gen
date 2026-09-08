class_name PlatformerInventoryPanel
extends Control

## What the body is carrying, on the panel the run published art for.
##
## The whole 1536x1024 canvas is stretched into a rectangle a third of the
## viewport wide, top-right inside a capture-safe margin. It is not a crop and
## not a nine-slice: the producer drew a panel and this draws that panel, and the
## `panel_bounds` the block declares is layout documentation the drawing never
## reads.
##
## Slot centres come from the manifest rather than from a formula here, and the
## formula is written beside them anyway — the published block is validated to
## exactly `208 + column * 288` by the producer, so a package that drifts is
## refused there rather than quietly drawn wrong here.
##
## Screen space, above everything: it is furniture rather than a thing in the
## world, so it neither scrolls nor zooms.

## The share of the viewport the panel takes, and the inset from the corner.
const WIDTH_FRACTION := 0.34
const SAFE_MARGIN := 24.0

## The icon inside a slot, in canvas pixels — about three quarters of a slot.
const ICON_CANVAS_PX := 192.0

## Where a count sits relative to its slot's centre, as a share of the icon, and
## how large it is drawn.
const COUNT_OFFSET_FRACTION := 0.3
const COUNT_SIZE_FRACTION := 0.18
const COUNT_MINIMUM_SIZE := 10

var _panel: Sprite2D = null
var _slots: Array = []
var _icons: Array = []
var _counts: Array = []
var _textures: Array = []
var _scale: float = 1.0
var _origin: Vector2 = Vector2.ZERO


## Build the panel from a run's `ui` block, or nothing when it publishes none.
static func of(package: HostRunDir, manifest: Dictionary) -> PlatformerInventoryPanel:
	var block: Dictionary = (manifest.get("ui", {}) as Dictionary).get("inventory_panel", {})
	if block.is_empty():
		return null
	var art := package.texture(str(block.get("asset", "")))
	if art == null:
		art = package.texture(str((block.get("asset", {}) as Dictionary).get("path", "")))
	if art == null:
		push_error("platformer inventory: the run publishes a panel with no art")
		return null
	var canvas: Dictionary = block.get("canvas", {})
	var canvas_size := Vector2(
		float(canvas.get("width", art.get_width())), float(canvas.get("height", art.get_height()))
	)

	var made := PlatformerInventoryPanel.new()
	# The floor is transcribed rather than folded away: `1280 * 0.34 / 1536`
	# without it is off by a thousandth, which is half a pixel on the last slot.
	var wanted := floorf(PlatformerStage.VIEW_WIDTH * WIDTH_FRACTION)
	made._scale = wanted / canvas_size.x
	var drawn := canvas_size * made._scale
	made._origin = Vector2(PlatformerStage.VIEW_WIDTH - drawn.x - SAFE_MARGIN, SAFE_MARGIN)

	made._panel = Sprite2D.new()
	made._panel.texture = art
	made._panel.centered = false
	made._panel.scale = Vector2(made._scale, made._scale)
	made._panel.position = made._origin
	made.add_child(made._panel)

	for entry: Variant in (block.get("slots", []) as Array):
		var slot: Dictionary = entry
		var centre := Vector2(
			float(slot.get("x", 0)) + float(slot.get("width", 0)) / 2.0,
			float(slot.get("y", 0)) + float(slot.get("height", 0)) / 2.0
		)
		made._slots.append(made._origin + centre * made._scale)
	for entry: Variant in (manifest.get("items", []) as Array):
		var item: Dictionary = entry
		made._textures.append(
			package.trimmed_texture(str((item.get("asset", {}) as Dictionary).get("path", "")))
		)
	made.visible = false
	return made


## Put what is carried into the slots it belongs in.
##
## A kind's slot is its own index around the ring, so a thing keeps its place for
## as long as it is carried rather than shuffling when something beside it is
## spent.
func sync(world: PlatformerWorld) -> void:
	if not visible or _slots.is_empty():
		return
	_clear()
	var icon_size := ICON_CANVAS_PX * _scale
	for entry: Variant in (world.inventory["carried"] as Array):
		var pair: Array = entry
		var kind := _kind_of(world, str(pair[0]))
		if kind < 0 or kind >= _textures.size() or _textures[kind] == null:
			continue
		var slot := _slots[kind % _slots.size()] as Vector2
		var texture: Texture2D = _textures[kind]
		var icon := Sprite2D.new()
		icon.texture = texture
		icon.centered = true
		icon.position = slot
		var tallest := maxf(1.0, float(maxi(texture.get_width(), texture.get_height())))
		icon.scale = Vector2.ONE * (icon_size / tallest)
		add_child(icon)
		_icons.append(icon)
		var count := Label.new()
		count.text = "x%d" % int(pair[1])
		count.add_theme_font_size_override(
			"font_size", maxi(COUNT_MINIMUM_SIZE, int(icon_size * COUNT_SIZE_FRACTION))
		)
		count.position = slot + Vector2.ONE * (icon_size * COUNT_OFFSET_FRACTION)
		add_child(count)
		_counts.append(count)


func toggle() -> void:
	visible = not visible


func _clear() -> void:
	for node: Variant in _icons + _counts:
		(node as Node).queue_free()
	_icons = []
	_counts = []


static func _kind_of(world: PlatformerWorld, item_id: String) -> int:
	var catalogue: Array = world.package["items"]
	for index in range(catalogue.size()):
		if str((catalogue[index] as Dictionary).get("item_id", "")) == item_id:
			return index
	return -1
