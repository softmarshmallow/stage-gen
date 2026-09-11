extends SceneTree

const ActorHalo = preload("res://addons/game_presentation/effects/actor_halo.gd")
var _errors: Array[String] = []


func _initialize() -> void:
	_run.call_deferred()


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_errors.append(message)


func _run() -> void:
	_contract_checks()
	if DisplayServer.get_name() != "headless":
		await _render_checks()
	else:
		print("SKIP Actor Halo raster checks: headless display has no native canvas raster output.")
	for issue: String in _errors:
		printerr("FAIL Actor Halo: " + issue)
	if _errors.is_empty():
		print("PASS Actor Halo: binding, padded logical layout, validation, isolation, and reset.")
	quit(0 if _errors.is_empty() else 1)


func _texture() -> ImageTexture:
	var pixels := Image.create(32, 32, false, Image.FORMAT_RGBA8)
	pixels.fill(Color.TRANSPARENT)
	for y in range(8, 24):
		for x in range(0, 24):
			pixels.set_pixel(x, y, Color.WHITE if x < 12 else Color.BLACK)
	return ImageTexture.create_from_image(pixels)


func _contract_checks() -> void:
	var halo := ActorHalo.new()
	var other := ActorHalo.new()
	root.add_child(halo)
	root.add_child(other)
	_expect(not halo.visible and halo.mouse_filter == Control.MOUSE_FILTER_IGNORE and halo.focus_mode == Control.FOCUS_NONE, "Unbound halo must be hidden and never intercept player input.")
	_expect(halo.configure({"radius": 20.0, "intensity": 1.5}).is_empty(), "Valid partial settings must configure.")
	var texture := _texture()
	halo.set_source(texture)
	_expect(not halo.visible, "Source alone must not create a visible unplaced quad.")
	var rect := Rect2(100, 150, 64, 96)
	_expect(halo.set_rect(rect).is_empty(), "Valid displayed source rect must bind.")
	_expect(halo.visible and halo.position == Vector2(78, 128) and halo.size == Vector2(108, 140), "Quad must expand beyond all four source edges by radius plus padding.")
	var settings: Dictionary = halo.get_settings()
	var material := halo.material as ShaderMaterial
	_expect(material != other.material, "Each actor must own its shader material.")
	_expect(material.get_shader_parameter("source_size") == rect.size, "Source UV remapping must use logical display size, independent of native texture pixels.")
	for invalid: Dictionary in [{"radius": NAN}, {"radius": -1}, {"radius": 129}, {"intensity": true}, {"intensity": 4.1}, {"color": "white"}, {"color": Color(INF, 0, 0)}, {"radius": 10, "unknown": 1}]:
		_expect(not halo.configure(invalid).is_empty() and halo.get_settings() == settings and halo.get_source_rect() == rect and halo.position == Vector2(78, 128), "Invalid settings must not partially mutate configuration or geometry: " + str(invalid))
	for invalid: Rect2 in [Rect2(0, 0, 0, 20), Rect2(0, 0, -1, 20), Rect2(NAN, 0, 20, 20), Rect2(0, 0, INF, 20)]:
		_expect(not halo.set_rect(invalid).is_empty() and halo.get_source_rect() == rect, "Invalid rectangles must preserve the previous binding.")
	for invalid: float in [-0.1, 1.1, NAN, INF]:
		_expect(not halo.set_strength(invalid).is_empty() and halo.get_strength() == 1.0, "Invalid strength must be rejected atomically.")
	settings["radius"] = 99.0
	_expect(halo.get_settings()["radius"] == 20.0 and other.get_settings()["radius"] == 24.0, "Settings exposure and separate instances must not share mutable state.")
	halo.set_strength(0.0)
	_expect(not halo.visible and halo.texture == texture, "Zero strength must disable only the effect, preserving its source.")
	halo.set_strength(1.0)
	halo.configure({"radius": 0.0})
	_expect(not halo.visible, "Zero radius must produce no glow.")
	halo.configure({"radius": 20.0})
	var parent := Control.new()
	root.add_child(parent)
	halo.reparent(parent, false)
	parent.scale = Vector2(2, 2)
	_expect(halo.size == Vector2(108, 140) and halo.get_global_transform().get_scale() == Vector2(2, 2), "Window/camera parent scaling must scale the halo while preserving logical radius and layout.")
	halo.clear()
	_expect(not halo.visible and halo.texture == null and halo.get_source_rect() == Rect2() and halo.get_settings()["radius"] == 20.0 and halo.get_strength() == 1.0, "Clear must remove the binding while preserving reusable settings and strength.")
	parent.free()
	other.free()


func _render_checks() -> void:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(192, 128)
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var crop := Control.new()
	crop.position = Vector2(24, 16)
	crop.size = Vector2(128, 96)
	viewport.add_child(crop)
	var halo := ActorHalo.new()
	crop.add_child(halo)
	halo.configure({"color": Color.WHITE, "radius": 18.0, "intensity": 2.0})
	halo.set_source(_texture())
	halo.set_rect(Rect2(24, 16, 64, 64))
	await process_frame
	await RenderingServer.frame_post_draw
	var image := viewport.get_texture().get_image()
	_expect(image.get_pixel(43, 64).a > 0.01, "Glow must extend outside the original source quad's left edge without texture clamping.")
	_expect(image.get_pixel(70, 64).a < 0.01 and image.get_pixel(76, 64).a < 0.01, "White/black source interiors and internal RGB edges must remain invisible in the halo-only layer.")
	_expect(image.get_pixel(13, 64).a < 0.01 and image.get_pixel(49, 12).a < 0.01, "Halo must have finite support without a padded alpha rectangle.")
	halo.set_strength(0.0)
	await process_frame
	await RenderingServer.frame_post_draw
	image = viewport.get_texture().get_image()
	_expect(image.get_pixel(43, 64).a < 0.01, "Zero strength must remove rasterized glow.")
	halo.set_strength(1.0)
	crop.clip_contents = true
	crop.position = Vector2(48, 16)
	halo.set_rect(Rect2(0, 16, 64, 64))
	await process_frame
	await RenderingServer.frame_post_draw
	image = viewport.get_texture().get_image()
	_expect(image.get_pixel(43, 64).a < 0.01, "A host crop parent must clip the glow together with the actor.")
	viewport.free()
	print("PASS Actor Halo: native alpha-only outer glow, transparent interiors, bounded padded quad, and host clipping.")
