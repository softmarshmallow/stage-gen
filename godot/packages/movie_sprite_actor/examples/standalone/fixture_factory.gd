extends RefCounted

## Original procedural inspection figures, not prepared game assets.
## Facial pixels remain in one source-canvas registration across every body frame.
static func create(directory: String, canvas: Vector2i, count: int, fps: float, grid: Vector2i, wink := false) -> Dictionary:
	var directory_error := DirAccess.make_dir_recursive_absolute(directory)
	if directory_error != OK: return {"errors": ["Cannot create fixture directory: " + error_string(directory_error)]}
	var pages: Array = []
	var capacity := grid.x * grid.y
	var page_count := ceili(float(count) / capacity)
	for page_index: int in range(page_count):
		var atlas := Image.create(canvas.x * grid.x, canvas.y * grid.y, false, Image.FORMAT_RGBA8)
		atlas.fill(Color.TRANSPARENT)
		for cell: int in range(capacity):
			var index := page_index * capacity + cell
			if index >= count: break
			var picture := body(canvas, index, count)
			atlas.blit_rect(picture, Rect2i(Vector2i.ZERO, canvas), Vector2i(cell % grid.x, cell / grid.x) * canvas)
		var name := "page_%02d.png" % page_index
		if atlas.save_png(directory.path_join(name)) != OK: return {"errors": ["Cannot save fixture body atlas."]}
		pages.append(binding(directory, name))
	var eye := Image.create(canvas.x, canvas.y, false, Image.FORMAT_RGBA8)
	eye.fill(Color.TRANSPARENT)
	eye.fill_rect(eye_rect(canvas, wink), Color(0.15, 0.21, 0.34, 1.0))
	if eye.save_png(directory.path_join("eyes.png")) != OK: return {"errors": ["Cannot save fixture eye texture."]}
	var mouth := Image.create(canvas.x, canvas.y, false, Image.FORMAT_RGBA8)
	mouth.fill(Color.TRANSPARENT)
	mouth.fill_rect(mouth_rect(canvas), Color(0.82, 0.19, 0.30, 1.0))
	if mouth.save_png(directory.path_join("mouth_a.png")) != OK: return {"errors": ["Cannot save fixture mouth A texture."]}
	mouth.fill(Color.TRANSPARENT)
	mouth.fill_rect(mouth_rect(canvas), Color(0.44, 0.12, 0.40, 1.0))
	if mouth.save_png(directory.path_join("mouth_o.png")) != OK: return {"errors": ["Cannot save fixture mouth O texture."]}
	var manifest := {"schema_version": 1, "character_id": "inspection_figure", "patch_application": "replace_selected_rgb_preserve_original_alpha", "frame_size": [canvas.x, canvas.y], "frame_count": count, "fps": fps, "columns": grid.x, "rows": grid.y, "pages": pages, "eyes": {"eyes_closed": binding(directory, "eyes.png")}, "mouths": {"mouth_a": binding(directory, "mouth_a.png"), "mouth_o": binding(directory, "mouth_o.png")}}
	if write_json(directory.path_join("manifest.json"), manifest) != OK: return {"errors": ["Cannot save fixture manifest."]}
	return manifest


static func body(canvas: Vector2i, index: int, count: int) -> Image:
	var picture := Image.create(canvas.x, canvas.y, false, Image.FORMAT_RGBA8)
	picture.fill(Color.TRANSPARENT)
	var phase := TAU * float(index) / count
	var torso := Color(0.22 + 0.08 * sin(phase), 0.48, 0.74, 0.92)
	var skin := Color(0.88, 0.70, 0.57, 0.72)
	ellipse(picture, Vector2(canvas) * Vector2(0.5, 0.235), Vector2(canvas) * Vector2(0.255, 0.17), skin)
	ellipse(picture, Vector2(canvas) * Vector2(0.5, 0.59), Vector2(canvas) * Vector2(0.24, 0.22), torso)
	var sway := roundi(sin(phase) * canvas.x * 0.06)
	picture.fill_rect(Rect2i(roundi(canvas.x * 0.31) + sway, roundi(canvas.y * 0.75), maxi(2, roundi(canvas.x * 0.13)), roundi(canvas.y * 0.19)), torso)
	picture.fill_rect(Rect2i(roundi(canvas.x * 0.56) - sway, roundi(canvas.y * 0.75), maxi(2, roundi(canvas.x * 0.13)), roundi(canvas.y * 0.19)), torso)
	ellipse(picture, Vector2(canvas) * Vector2(0.19, 0.58) + Vector2(sway, 0), Vector2(canvas) * Vector2(0.10, 0.10), torso)
	ellipse(picture, Vector2(canvas) * Vector2(0.81, 0.58) - Vector2(sway, 0), Vector2(canvas) * Vector2(0.10, 0.10), torso)
	# Baseline eyes and mouth share exactly the body alpha, not opaque overlays.
	var eyes := eye_rect(canvas)
	picture.fill_rect(eyes, Color(0.26, 0.37, 0.52, skin.a))
	picture.fill_rect(mouth_rect(canvas), Color(0.52, 0.32, 0.31, skin.a))
	return picture


static func eye_rect(canvas: Vector2i, wink := false) -> Rect2i:
	return Rect2i(roundi(canvas.x * 0.34), roundi(canvas.y * 0.21), maxi(1, roundi(canvas.x * (0.12 if wink else 0.32))), maxi(1, roundi(canvas.y * 0.035)))


static func mouth_rect(canvas: Vector2i) -> Rect2i:
	return Rect2i(roundi(canvas.x * 0.44), roundi(canvas.y * 0.31), maxi(1, roundi(canvas.x * 0.12)), maxi(1, roundi(canvas.y * 0.035)))


static func ellipse(picture: Image, center: Vector2, radius: Vector2, color: Color) -> void:
	for y: int in range(maxi(0, floori(center.y - radius.y)), mini(picture.get_height(), ceili(center.y + radius.y))):
		for x: int in range(maxi(0, floori(center.x - radius.x)), mini(picture.get_width(), ceili(center.x + radius.x))):
			if ((Vector2(x, y) - center) / radius).length_squared() <= 1.0: picture.set_pixel(x, y, color)


static func binding(directory: String, name: String) -> Dictionary:
	return {"file": name, "sha256": FileAccess.get_sha256(directory.path_join(name))}


static func write_json(path: String, document: Dictionary) -> Error:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null: return FileAccess.get_open_error()
	file.store_string(JSON.stringify(document))
	return file.get_error()
