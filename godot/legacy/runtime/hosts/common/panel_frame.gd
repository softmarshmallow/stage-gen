class_name HostPanelFrame
extends Control

## One generated atlas cell drawn at any size, with a state switch.
##
## A port of `web/lib/families/ui/widget.ts`. The engine has its own nine-slice
## and the manifest's resolved geometry maps onto it one to one: a cell rect is
## the region, the insets are the corner widths, and the admitted band fill is
## the tile flag. So this owns no drawing of its own. Where it sits and what a
## press on it means stay with the host that places it.
##
## **`draw_scale` is the part that is easy to get wrong.** The sheet is authored
## at some multiple of screen density — two, in every package published so far —
## so the slices are laid out at that multiple of the target size and the whole
## thing is scaled back down. Drawn without it, the corner ornament keeps its
## *sheet* pixel size instead of its drawn proportion to the body, and a small
## button is all corner.

## The frame, laid out at `draw_scale` times the size it is drawn at.
var _patch: NinePatchRect = null
var _block: Dictionary = {}
var _sheet: Image = null
var _state: String = ""


## Build from a run's `ui` block for one role, at a rectangle in design space.
##
## Returns null when the role publishes no cells: a widget with no geometry is
## not a widget, and the host says so rather than adding an untextured
## rectangle to the tree.
static func of(
	sheets: HostUiSheets, role: String, rect: Dictionary, state: String = ""
) -> HostPanelFrame:
	if not sheets.has(role):
		return null
	var block := sheets.block(role)
	var cells: Array = block.get("cells", [])
	if cells.is_empty():
		return null
	var made := HostPanelFrame.new()
	made._block = block
	made._sheet = sheets.image(role)
	made._state = state if state != "" else String((cells[0] as Dictionary).get("state", ""))
	made.mouse_filter = Control.MOUSE_FILTER_IGNORE

	made._patch = NinePatchRect.new()
	made._patch.texture = sheets.texture(role)
	made._patch.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var insets: Dictionary = block.get("insets", {})
	made._patch.patch_margin_left = int(insets.get("left", 0))
	made._patch.patch_margin_top = int(insets.get("top", 0))
	made._patch.patch_margin_right = int(insets.get("right", 0))
	made._patch.patch_margin_bottom = int(insets.get("bottom", 0))
	# `stretch` and `tile` are the two a block may name, and a band drawn the
	# wrong way is the one thing a nine-slice can get visibly wrong.
	if String(block.get("band_fill", "stretch")) == "tile":
		made._patch.axis_stretch_horizontal = NinePatchRect.AXIS_STRETCH_MODE_TILE
		made._patch.axis_stretch_vertical = NinePatchRect.AXIS_STRETCH_MODE_TILE
	var factor := 1.0 / made.scale_factor()
	made._patch.scale = Vector2(factor, factor)
	made.add_child(made._patch)
	made._apply_region()
	made.set_rect(rect)
	return made


## Sheet pixels per screen pixel.
func scale_factor() -> float:
	return maxf(1.0, float(_block.get("draw_scale", 1)))


## Move and resize, keeping the slices laid out at the sheet's own density.
func set_rect(rect: Dictionary) -> void:
	position = Vector2(float(rect["x"]), float(rect["y"]))
	size = Vector2(float(rect["width"]), float(rect["height"]))
	var factor := scale_factor()
	_patch.size = Vector2(size.x * factor, size.y * factor)


## Switch to the sheet's frame for this state, so a button's hover and pressed
## looks are the producer's pixels rather than a tint.
func set_frame_state(state: String) -> void:
	if state == _state:
		return
	_state = state
	_apply_region()


func frame_state() -> String:
	return _state


## The screen rectangle of the geometric interior, for decoration that may run
## under the ornament.
func content_rect() -> Dictionary:
	return _interior(0.0, 0.0, 0.0, 0.0)


## The screen rectangle text is safe in: the interior less the measured ornament
## curl of the current state's cell. This is what a host lays words out from.
func safe_rect() -> Dictionary:
	var cell := HostUiSheets.cell_for(_block, _state)
	var content: Dictionary = cell.get("content_rect", {})
	var safe: Dictionary = cell.get("safe_rect", {})
	if content.is_empty() or safe.is_empty():
		return content_rect()
	return _interior(
		float(safe["x"]) - float(content["x"]),
		float(safe["y"]) - float(content["y"]),
		float(content["x"]) + float(content["width"]) - (float(safe["x"]) + float(safe["width"])),
		float(content["y"]) + float(content["height"]) - (float(safe["y"]) + float(safe["height"]))
	)


## The average colour of the drawn interior, for choosing a readable text
## colour on it. Returns `[r, g, b]` in 0..255, or an empty array when the sheet
## cannot be read — which is the caller's signal to keep whatever colour it was
## authored with rather than guess.
##
## Sampled from the current state's cell rather than assumed, because the sheet
## is generated art: the same role is a cream plate in one package and a
## near-black one in the next, and a constant text colour is legible in only one
## of them. Points are taken on a small grid around the cell's centre — the flat
## band a nine-slice stretches, which is exactly where the words sit — and
## averaged, so one speck of ink grain cannot decide it.
func interior_color() -> Array:
	if _sheet == null:
		return []
	var cell := HostUiSheets.cell_for(_block, _state)
	var box: Dictionary = cell.get("cell", {})
	if box.is_empty():
		return []
	var width := float(box.get("width", 0))
	var height := float(box.get("height", 0))
	if width < 3.0 or height < 3.0:
		return []
	var totals := [0.0, 0.0, 0.0]
	var seen := 0
	for fx: float in [0.35, 0.5, 0.65]:
		for fy: float in [0.35, 0.5, 0.65]:
			var x := int(float(box.get("x", 0)) + floorf(width * fx))
			var y := int(float(box.get("y", 0)) + floorf(height * fy))
			if x < 0 or y < 0 or x >= _sheet.get_width() or y >= _sheet.get_height():
				continue
			var pixel := _sheet.get_pixel(x, y)
			# A fully transparent sample is the panel showing whatever is behind
			# it, which this cannot speak for; ignore it rather than averaging in
			# a meaningless black.
			if pixel.a < 8.0 / 255.0:
				continue
			totals[0] += pixel.r * 255.0
			totals[1] += pixel.g * 255.0
			totals[2] += pixel.b * 255.0
			seen += 1
	if seen == 0:
		return []
	return [totals[0] / seen, totals[1] / seen, totals[2] / seen]


func _apply_region() -> void:
	var cell := HostUiSheets.cell_for(_block, _state)
	var box: Dictionary = cell.get("cell", {})
	if box.is_empty():
		return
	_patch.region_rect = Rect2(
		float(box.get("x", 0)),
		float(box.get("y", 0)),
		float(box.get("width", 0)),
		float(box.get("height", 0))
	)


## The interior in the parent's coordinates, less the insets and whatever curl
## the caller adds to them, all in screen pixels.
func _interior(
	curl_left: float, curl_top: float, curl_right: float, curl_bottom: float
) -> Dictionary:
	var factor := scale_factor()
	var insets: Dictionary = _block.get("insets", {})
	var left := (float(insets.get("left", 0)) + curl_left) / factor
	var top := (float(insets.get("top", 0)) + curl_top) / factor
	var right := (float(insets.get("right", 0)) + curl_right) / factor
	var bottom := (float(insets.get("bottom", 0)) + curl_bottom) / factor
	return {
		"x": position.x + left,
		"y": position.y + top,
		"width": size.x - left - right,
		"height": size.y - top - bottom,
	}
