extends RefCounted

## Afterlight's prepared content convention mirrors project media paths beneath
## the selected root. Legacy res:// strings are translated only at this boundary;
## the SDK loader itself accepts strictly relative bindings.
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")


static func relative_binding(path: String) -> String:
	return path.trim_prefix("res://")


static func load_texture(loader: RefCounted, path: String, mipmaps: bool = true) -> Dictionary:
	return loader.load_texture(relative_binding(path), mipmaps)


static func load_manpu(loader: RefCounted = null) -> Dictionary:
	if loader == null: loader = LOCAL_CONTENT.new()
	var document: Dictionary = loader.read_json("assets/manpu/catalog.json")
	if not document.errors.is_empty(): return {"textures": {}, "errors": document.errors}
	if not document.value is Dictionary or not document.value.get("manpu") is Array:
		return {"textures": {}, "errors": ["Afterlight requires a manpu art catalog with a manpu array."]}
	var textures := {}
	var errors: Array[String] = []
	for entry: Variant in document.value.manpu:
		if not entry is Dictionary or not entry.get("id") is String or str(entry.get("id", "")).is_empty() or not entry.get("file") is String:
			errors.append("Afterlight manpu entries require string id and file bindings.")
			continue
		if textures.has(entry.id):
			errors.append("Duplicate Afterlight manpu art id: " + entry.id)
			continue
		var loaded := load_texture(loader, entry.file, false)
		errors.append_array(loaded.errors)
		if loaded.errors.is_empty(): textures[entry.id] = loaded.resource
	if textures.is_empty(): errors.append("Afterlight manpu art catalog must not be empty.")
	return {"textures": textures if errors.is_empty() else {}, "errors": errors}
