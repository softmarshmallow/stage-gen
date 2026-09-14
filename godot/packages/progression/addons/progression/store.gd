extends RefCounted
## A document on disk: one JSON file, written atomically (a sibling temp file, then a rename), read
## back and checked by the validate callable the host passes. A document the host cannot read is not
## migrated: it is moved aside as `<name>.v<version>.json` (or `.bad.json` when it will not parse), a
## fresh one comes from the create callable, and the refusal is returned so the host can print it.
## The host owns the path (user://... in play, a scratch path under a check). Knows nothing about
## what the document holds; the ledger is one document, a game's own state can be another.


static func load_document(path: String, validate: Callable, create: Callable, now: int) -> Dictionary:
	## Returns {document, fresh: bool, refused: String, errors}. validate(doc) answers an Array[String];
	## create(now) answers a fresh document.
	var absolute := ProjectSettings.globalize_path(path)
	if not FileAccess.file_exists(absolute):
		return {"document": create.call(now), "fresh": true, "refused": "", "errors": []}
	var text := FileAccess.get_file_as_string(absolute)
	var parsed := JSON.new()
	if parsed.parse(text) != OK or not parsed.data is Dictionary:
		var aside := _move_aside(absolute, "bad")
		return {"document": create.call(now), "fresh": true, "refused": "The document at %s is not a JSON object; moved to %s" % [path, aside], "errors": []}
	var problems: Array = validate.call(parsed.data)
	if not problems.is_empty():
		var version: Variant = parsed.data.get("schema_version", "none")
		var tag := "v" + (str(int(version)) if version is float and version == floorf(version) else str(version))
		var aside := _move_aside(absolute, tag)
		var reasons: Array[String] = []
		for p: Variant in problems:
			reasons.append(String(p))
		return {"document": create.call(now), "fresh": true, "refused": "The document at %s was refused (%s); moved to %s" % [path, "; ".join(reasons), aside], "errors": []}
	return {"document": parsed.data, "fresh": false, "refused": "", "errors": []}


static func save_document(path: String, doc: Dictionary) -> Array[String]:
	var absolute := ProjectSettings.globalize_path(path)
	var directory := absolute.get_base_dir()
	if DirAccess.make_dir_recursive_absolute(directory) != OK:
		return ["Cannot create the directory: " + directory]
	var temporary := absolute + ".tmp"
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return ["Cannot write: " + temporary]
	file.store_string(JSON.stringify(doc, "  ") + "\n")
	file.close()
	if DirAccess.rename_absolute(temporary, absolute) != OK:
		return ["Cannot replace: " + absolute]
	return []


static func _move_aside(absolute: String, tag: String) -> String:
	var aside := absolute.get_basename() + "." + tag + ".json"
	var n := 1
	while FileAccess.file_exists(aside):
		n += 1
		aside = absolute.get_basename() + "." + tag + "." + str(n) + ".json"
	DirAccess.rename_absolute(absolute, aside)
	return aside
