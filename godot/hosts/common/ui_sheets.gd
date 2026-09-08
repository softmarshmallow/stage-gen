class_name HostUiSheets
extends RefCounted

## The generated interface sheets a run publishes, loaded once for every host.
##
## A port of `web/lib/families/ui/sheets.ts` and the loading half of
## `fallback.ts`. Three roles are shared vocabulary on purpose — a room, a
## visual novel and a case all draw from `panel_frame`, `button_rect` and
## `preview_icons` — so the widget layer never learns a per-genre naming scheme.
##
## A sheet that will not load is replaced by a conspicuous magenta stand-in of
## the whole declared canvas, exactly as the browser's does, and the role is
## remembered in `missing`. That is deliberate on both counts: every widget stays
## constructible, so one unreadable button sheet does not also cost the panel
## that did load, and the absence stays *visible* rather than becoming a panel
## that silently is not drawn. The picture gate reads the same magenta.

## Every sheet the manifest's `ui` block publishes: the two nine-slice roles and
## the icon grid.
const ROLES := ["panel_frame", "button_rect", "preview_icons"]

## The sixteen glyphs the preview grid holds, in reading order. A consumer
## indexes the sheet by these names.
const GLYPHS := [
	"play", "pause", "close", "menu", "gear", "home", "retry", "check",
	"search", "hand", "heart", "star", "arrow_left", "arrow_right",
	"sound_on", "sound_off",
]

## What the stand-in is painted with. The browser's `#ff00ff`.
const STAND_IN := Color(1.0, 0.0, 1.0, 1.0)

## Per role, the block the manifest published.
var blocks: Dictionary = {}
## Per role, the sheet as a texture.
var textures: Dictionary = {}
## Per role, the sheet as an image, for sampling the drawn interior.
var images: Dictionary = {}
## The roles whose art did not arrive and are wearing the stand-in.
var missing: PackedStringArray = PackedStringArray()


## Read the `ui` block of a manifest and load every sheet it names.
##
## `ui` is the document's own `ui` record. A role the document does not publish
## is simply absent — `has(role)` answers, and a host that needs one refuses by
## name rather than drawing an untextured rectangle.
static func of(package: HostRunDir, ui: Variant) -> HostUiSheets:
	var made := HostUiSheets.new()
	var published: Dictionary = ui if ui is Dictionary else {}
	for role in ROLES:
		if not published.has(role):
			continue
		var block: Dictionary = published[role]
		made.blocks[role] = block
		var ref := HostUiSheets._asset_ref(block)
		var texture: ImageTexture = null
		var image: Image = null
		if ref != "":
			image = package.image(ref)
			texture = package.texture(ref)
		if texture == null:
			var canvas: Dictionary = block.get("canvas", {})
			image = Image.create(
				maxi(1, int(canvas.get("width", 1024))),
				maxi(1, int(canvas.get("height", 1024))),
				false,
				Image.FORMAT_RGBA8
			)
			image.fill(STAND_IN)
			texture = ImageTexture.create_from_image(image)
			made.missing.append(role)
			push_warning("ui sheets: %s did not load; wearing the stand-in" % role)
		made.textures[role] = texture
		made.images[role] = image
	return made


func has(role: String) -> bool:
	return blocks.has(role)


func block(role: String) -> Dictionary:
	return blocks.get(role, {})


func texture(role: String) -> ImageTexture:
	return textures.get(role, null)


func image(role: String) -> Image:
	return images.get(role, null)


## The cell one published state names, or the first the sheet publishes.
##
## A role publishes its states in a fixed order — `panel_frame` has only
## `default`, `button_rect` has `normal, hover, pressed, disabled` — and falling
## back to the first is what makes a widget that asks for a state the sheet does
## not carry draw something rather than nothing.
static func cell_for(block_record: Dictionary, state: String) -> Dictionary:
	var cells: Array = block_record.get("cells", [])
	if cells.is_empty():
		return {}
	for entry: Variant in cells:
		var cell: Dictionary = entry
		if String(cell.get("state", "")) == state:
			return cell
	return cells[0]


## One glyph's square in the icon grid, or an empty rectangle for a name the
## grid does not hold.
func glyph_rect(glyph: String) -> Rect2:
	var grid := block("preview_icons")
	for entry: Variant in (grid.get("cells", []) as Array):
		var cell: Dictionary = entry
		if String(cell.get("glyph", "")) != glyph:
			continue
		var box: Dictionary = cell.get("cell", {})
		return Rect2(
			float(box.get("x", 0)),
			float(box.get("y", 0)),
			float(box.get("width", 0)),
			float(box.get("height", 0))
		)
	return Rect2()


## An `asset` that is a path, or a record carrying one. Both shapes are
## published: the room writes the string, the survival document writes a record.
static func _asset_ref(block_record: Dictionary) -> String:
	var asset: Variant = block_record.get("asset", "")
	if asset is Dictionary:
		return String((asset as Dictionary).get("path", ""))
	return String(asset)
