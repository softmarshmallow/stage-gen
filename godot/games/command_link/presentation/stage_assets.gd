extends RefCounted

## Command Link's prepared-content adapter. It owns local asset/catalog binding,
## diagnostics and contact landmarks; it does not own a scene or any clocks.
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const PROFILE = preload("res://presentation/stage_profile.gd")
var profile: PROFILE
var errors: Array[String] = []
var textures: Dictionary = {}
var images: Dictionary = {}
var manpu_catalog: Dictionary = {}
var manpu_textures: Dictionary = {}
var locations: Dictionary = {}
var location_textures: Dictionary = {}
var touch_point := Vector2(0.5, 0.5)
var touch_radius := 0.034
var layout_loaded := false


func load_assets() -> void:
	for key: String in profile.asset_paths:
		var path: String = profile.asset_paths[key]
		var picture := load_image(path, "Actor image " + key)
		if picture == null:
			continue
		images[key] = picture
		picture.generate_mipmaps()
		textures[key] = ImageTexture.create_from_image(picture)
	if profile.contact_actor_id.is_empty():
		return
	var parsed: Variant = read_json(profile.contact_layout_path)
	if parsed is Dictionary:
		var point: Variant = parsed.get("touch_point")
		var radius: Variant = parsed.get("touch_radius")
		if point is Array and point.size() == 2 and (radius is float or radius is int):
			if (point[0] is float or point[0] is int) and (point[1] is float or point[1] is int):
				touch_point = Vector2(float(point[0]), float(point[1]))
				touch_radius = float(radius)
				layout_loaded = touch_point.is_finite() and is_finite(touch_radius) and touch_radius > 0.0
	if not layout_loaded:
		errors.append("Missing fingertip coordinates for contact actor: " + profile.contact_actor_id)


func content() -> RefCounted:
	if profile.content_loader == null:
		profile.content_loader = LOCAL_CONTENT.new()
	return profile.content_loader


func read_json(path: String) -> Variant:
	# Historical project bindings are interpreted by the example, not the SDK.
	var result: Dictionary = content().read_json(path.trim_prefix("res://"))
	errors.append_array(result.errors)
	return result.value


func load_image(path: String, label: String) -> Image:
	var result: Dictionary = content().load_texture(path.trim_prefix("res://"), true)
	for issue: String in result.errors:
		errors.append(label + ": " + issue)
	var texture: Texture2D = result.resource
	return texture.get_image() if texture != null else null


func load_manpu() -> void:
	if profile.manpu_catalog_path.is_empty():
		return
	var parsed: Variant = read_json(profile.manpu_catalog_path)
	if not (parsed is Dictionary) or not (parsed.get("manpu") is Array):
		errors.append("The manpu catalog must contain a manpu array.")
		return
	for entry: Variant in parsed["manpu"]:
		if not (entry is Dictionary):
			errors.append("A manpu catalog entry is not a record.")
			continue
		var id := String(entry.get("id", ""))
		var path := String(entry.get("file", ""))
		if not profile.manpu_ids.has(id) or manpu_catalog.has(id):
			errors.append("Unknown or duplicate manpu: " + id)
			continue
		var picture := load_image(path, "Manpu " + id)
		if picture == null:
			continue
		if picture.get_width() != picture.get_height():
			errors.append("The manpu image must have a square canvas: " + id)
			continue
		picture.generate_mipmaps()
		manpu_catalog[id] = entry
		manpu_textures[id] = ImageTexture.create_from_image(picture)
	for id: String in profile.manpu_ids:
		if not manpu_textures.has(id):
			errors.append("The manpu catalog does not provide " + id)


func load_locations() -> void:
	if profile.location_catalog_path.is_empty():
		return
	var parsed: Variant = read_json(profile.location_catalog_path)
	if not (parsed is Dictionary) or not (parsed.get("locations") is Array):
		errors.append("The location catalog must contain a locations array.")
		return
	for entry: Variant in parsed["locations"]:
		if not (entry is Dictionary):
			errors.append("A location catalog entry is not a record.")
			continue
		var id := String(entry.get("id", ""))
		var path := String(entry.get("background", ""))
		if not profile.location_ids.has(id) or locations.has(id):
			errors.append("Unknown or duplicate location: " + id)
			continue
		if String(entry.get("name", "")).is_empty() or String(entry.get("detail", "")).is_empty():
			errors.append("A location needs its name and detail: " + id)
			continue
		var picture := load_image(path, "Location " + id)
		if picture == null:
			continue
		if picture.detect_alpha() != Image.ALPHA_NONE:
			errors.append("A location background must be opaque: " + id)
			continue
		picture.generate_mipmaps()
		locations[id] = entry
		location_textures[id] = ImageTexture.create_from_image(picture)
	for id: String in profile.location_ids:
		if not locations.has(id):
			errors.append("The location catalog does not provide " + id)
