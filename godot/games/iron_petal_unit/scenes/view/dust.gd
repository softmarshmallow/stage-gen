class_name RunnerDustView
extends Node2D

## The surface the dust system draws its live puffs onto.
##
## Two ways to draw one, and the package decides which: `fx.sprite.dust`
## publishes an atlas with one cell per kind, and a run that publishes none
## draws the procedural silhouette instead. The silhouette is not a placeholder —
## at foot scale a puff is a shape with an ink rim, which is the register this
## art is drawn in, so a run that never paid a provider still throws dust.
##
## Sprites are pooled rather than created and freed: a run lays thousands of
## puffs, and each one allocated and released inside a frame is churn at sixty
## hertz. Every image is hidden when the frame opens and only the ones this frame
## drew are shown again, so the pool settles at the busiest frame the run ever had
## and nothing from a past frame is left on screen.

var _atlas: Texture2D = null
var _cells: Dictionary = {}
var _pool: Array = []
var _live: int = 0
var _shapes: RunnerEllipses = null


## Build from the package's `fx.sprite.dust`, falling back to the procedural
## silhouette when the run publishes no atlas or its image cannot be read.
static func of(package: HostRunDir, depth: int) -> RunnerDustView:
	var view := RunnerDustView.new()
	view.z_index = depth
	var sprite: Dictionary = (
		(package.manifest.get("fx", {}) as Dictionary).get("sprite", {}) as Dictionary
	).get("dust", {})
	if not sprite.is_empty():
		var texture := package.texture(String(sprite.get("asset", "")))
		if texture != null:
			view._atlas = texture
			for entry: Variant in (sprite.get("cells", []) as Array):
				var cell: Dictionary = entry
				view._cells[String(cell["kind"])] = Rect2(
					float(cell["x"]), float(cell["y"]), float(cell["width"]), float(cell["height"])
				)
	if view._atlas == null or view._cells.is_empty():
		push_warning("runner dust: this run publishes no dust atlas; drawing the silhouette")
		view._shapes = RunnerEllipses.new()
		view.add_child(view._shapes)
	return view


## Open a frame. Every puff drawn last frame is hidden until it is drawn again.
func begin() -> void:
	for entry: Variant in _pool:
		(entry as Sprite2D).visible = false
	_live = 0
	if _shapes != null:
		_shapes.begin()


func puff(sample: Dictionary) -> void:
	if _shapes != null:
		_draw_silhouette(sample)
		return
	var cell: Rect2 = _cells.get(String(sample["kind"]), Rect2())
	if cell.size.x <= 0.0:
		return
	var rect := RunnerDust.sprite_rect(sample, cell.size.x, cell.size.y)
	if rect.is_empty():
		return
	var sprite := _borrow()
	sprite.region_rect = cell
	sprite.visible = true
	sprite.modulate.a = float(sample["alpha"])
	sprite.scale = Vector2(
		float(rect["width"]) / cell.size.x, float(rect["height"]) / cell.size.y
	)
	sprite.position = Vector2(float(rect["x"]), float(rect["y"]))


func commit() -> void:
	if _shapes != null:
		_shapes.commit()


## Nothing of the last run survives into this one.
func clear_puffs() -> void:
	for entry: Variant in _pool:
		(entry as Sprite2D).visible = false
	_live = 0
	if _shapes != null:
		_shapes.begin()
		_shapes.commit()


## The cloud as three overlapping shapes with an ink rim, for a run with no art.
##
## Opaque lobes rather than translucent ones: two half-transparent ellipses show
## their union as a darker lens where they cross, and flat cel dust has no such
## seam. The whole cloud carries the puff's alpha instead.
func _draw_silhouette(sample: Dictionary) -> void:
	var fill := RunnerDust.FILL_COLOR
	fill.a = float(sample["alpha"])
	var rim := RunnerDust.RIM_COLOR
	rim.a = float(sample["alpha"])
	for entry: Variant in RunnerDust.cloud_lobes(sample):
		var lobe: Dictionary = entry
		_shapes.add_fill(
			float(lobe["x"]), float(lobe["y"]),
			float(lobe["radiusX"]), float(lobe["radiusY"]), fill
		)
		_shapes.add_stroke(
			float(lobe["x"]), float(lobe["y"]),
			float(lobe["radiusX"]), float(lobe["radiusY"]), rim, RunnerDust.RIM_WIDTH_PX
		)


func _borrow() -> Sprite2D:
	if _live < _pool.size():
		var reused: Sprite2D = _pool[_live]
		_live += 1
		return reused
	var made := Sprite2D.new()
	made.texture = _atlas
	made.centered = true
	made.region_enabled = true
	add_child(made)
	_pool.append(made)
	_live += 1
	return made
