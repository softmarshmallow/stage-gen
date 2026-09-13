extends RefCounted

## Atomically activates a validated, immutable local content closure. A game may
## obtain this directory by any delivery mechanism; this loader never downloads.
const CONTENT = preload("res://addons/content_io/local_content.gd")
const CATALOG = preload("../program/catalog.gd")
const PROGRAM = preload("../program/program.gd")
const JSON_DATA = preload("json_data.gd")
const MAX_FILES := 4096
const MAX_BYTES := 536870912
const MAX_MANIFEST_BYTES := 2097152
const DATA_EXTENSIONS := ["json", "scenario", "txt", "md", "png", "jpg", "jpeg", "webp", "wav", "ogg", "mp3", "ogv", "ttf", "otf"]
var _active: Dictionary = {}
var _revisions: Dictionary = {}


func activate(root: String, installed_types: Dictionary, backend: String = "files") -> Dictionary:
	var candidate := stage(root, installed_types, backend)
	if candidate.has("error"): return candidate
	var identity := "%s@%s" % [candidate.manifest.package_id, candidate.manifest.revision]
	if _revisions.has(identity) and _revisions[identity] != candidate.fingerprint:
		return _failure("immutable_revision", "package revision was already activated with different content")
	_revisions[identity] = candidate.fingerprint
	_active = candidate
	return {"package_id": candidate.manifest.package_id, "revision": candidate.manifest.revision, "fingerprint": candidate.fingerprint}


## Callers pin the returned admitted content when they start a session. Future
## activation replaces only this loader's selection, never a running session.
func current() -> Dictionary:
	return _active.duplicate(true)


static func stage(root: String, installed_types: Dictionary, backend: String = "files") -> Dictionary:
	var reader := CONTENT.new()
	var errors := reader.configure(root, backend)
	if not errors.is_empty(): return _failure("content_root", "; ".join(errors))
	var manifest_path := reader.resolve("scenario-package.json")
	if not manifest_path.errors.is_empty(): return _failure("manifest", "; ".join(manifest_path.errors))
	var manifest_file := FileAccess.open(manifest_path.path, FileAccess.READ)
	if manifest_file == null: return _failure("manifest", "cannot read scenario-package.json")
	var manifest_length := manifest_file.get_length()
	manifest_file.close()
	if manifest_length > MAX_MANIFEST_BYTES: return _failure("content_limit", "manifest exceeds 2 MiB")
	var manifest_bytes := reader.read_bytes("scenario-package.json")
	if not manifest_bytes.errors.is_empty(): return _failure("manifest", "; ".join(manifest_bytes.errors))
	var loaded := JSON_DATA.parse(manifest_bytes.bytes, "scenario-package.json")
	if loaded.has("error"): return loaded
	var manifest = loaded.value
	if not manifest is Dictionary or manifest.get("kind") != "scenario-content-package" or manifest.get("schema_version") != 1 or manifest.get("scenario_version") != 3:
		return _failure("manifest", "expected scenario-content-package schema 1, execution version 3")
	if not manifest.get("package_id") is String or str(manifest.package_id).is_empty() or not _positive_integer(manifest.get("revision")):
		return _failure("manifest", "package_id and positive integer revision are required")
	if not str(manifest.package_id).is_valid_identifier() or manifest.package_id != str(manifest.package_id).to_lower(): return _failure("manifest", "package_id must be lower_snake_case")
	for field: String in manifest:
		if field not in ["kind", "schema_version", "scenario_version", "package_id", "revision", "catalog", "programs", "required_capabilities", "files"]:
			return _failure("manifest", "unknown manifest field: " + field)
	if not manifest.get("required_capabilities") is Dictionary or not manifest.get("programs") is Dictionary or manifest.programs.is_empty() or not manifest.get("catalog") is String or not manifest.get("files") is Array:
		return _failure("manifest", "catalog, programs, files and required_capabilities must be declared")
	for capability: String in manifest.required_capabilities:
		if not _positive_integer(manifest.required_capabilities[capability]) or installed_types.get(capability, {}).get("version") != manifest.required_capabilities[capability]:
			return _failure("capability", "required installed capability version is unavailable: " + capability)
	if manifest.files.size() > MAX_FILES: return _failure("content_limit", "too many content files")
	var bytes_by_path := {}
	var total := 0
	for entry: Variant in manifest.files:
		if not entry is Dictionary or not entry.get("path") is String or not entry.get("sha256") is String or not _nonnegative_integer(entry.get("bytes")):
			return _failure("manifest", "each file needs path, sha256 and byte length")
		for field: String in entry:
			if field not in ["path", "sha256", "bytes"]: return _failure("manifest", "unknown file field: " + field)
		var path := str(entry.path)
		if path == "scenario-package.json" or bytes_by_path.has(path) or path.get_extension().to_lower() not in DATA_EXTENSIONS:
			return _failure("content_file", "duplicate, executable or unsupported content file: " + path)
		if float(entry.bytes) > MAX_BYTES: return _failure("content_limit", "content member exceeds 512 MiB")
		total += int(entry.bytes)
		if total > MAX_BYTES: return _failure("content_limit", "content exceeds 512 MiB")
		var resolved := reader.resolve(path)
		if not resolved.errors.is_empty(): return _failure("content_path", "; ".join(resolved.errors))
		var file := FileAccess.open(resolved.path, FileAccess.READ)
		if file == null or file.get_length() != int(entry.bytes): return _failure("content_length", "file length differs: " + path)
		file.close()
		var result := reader.read_bytes(path, entry.sha256)
		if not result.errors.is_empty(): return _failure("content_digest", "; ".join(result.errors))
		bytes_by_path[path] = result.bytes
	var raw_catalog := _json(bytes_by_path, manifest.catalog)
	if raw_catalog.has("error"): return raw_catalog
	var catalog := CATALOG.parse(raw_catalog, installed_types)
	if catalog.has("error"): return catalog
	var programs := {}
	for id: String in manifest.programs:
		if not manifest.programs[id] is String: return _failure("manifest", "program path must be a string")
		var raw := _json(bytes_by_path, manifest.programs[id])
		if raw.has("error"): return raw
		if raw.get("scenario_id") != id: return _failure("scenario_identity", "program ID does not match manifest: " + id)
		var program := PROGRAM.parse(raw, catalog)
		if program.has("error"): return program
		for required: String in program.required_capabilities:
			if manifest.required_capabilities.get(required) != program.required_capabilities[required]:
				return _failure("capability", "manifest omits program requirement: " + required)
		programs[id] = program
	return {"manifest": manifest.duplicate(true), "catalog": catalog, "programs": programs,
		"files": bytes_by_path, "fingerprint": "sha256:" + JSON.stringify(manifest, "", true).sha256_text()}


static func _json(files: Dictionary, path: String) -> Dictionary:
	if not files.has(path): return _failure("content_closure", "manifest reference is absent from files: " + path)
	var parsed := JSON_DATA.parse(files[path], path)
	if parsed.has("error"): return parsed
	if not parsed.value is Dictionary: return _failure("content_shape", "expected a JSON object: " + path)
	return parsed.value


static func _positive_integer(value: Variant) -> bool:
	return _nonnegative_integer(value) and float(value) >= 1.0


static func _nonnegative_integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) >= 0.0 and float(value) == floorf(float(value))


static func _failure(code: String, message: String) -> Dictionary:
	return {"error": {"code": code, "message": message, "path": "scenario-package.json"}}
