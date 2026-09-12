extends RefCounted

## Optional local-media boundary. Bindings are strictly relative to an explicit
## root; no provider, network, game schema, scene or script loading is involved.
## Files must remain immutable during a call. This is not an OS sandbox against
## another process concurrently replacing directories or files.
var _root := "res://"
var _backend := "resources"


func configure(root: String = "res://", backend: String = "resources") -> Array[String]:
	if backend not in ["resources", "files"]:
		return ["Content backend must be resources or files."]
	var candidate := root.trim_suffix("/") if root != "res://" and root != "/" else root
	if backend == "resources":
		if not candidate.begins_with("res://"):
			return ["Resource content roots must use res://."]
		var suffix := candidate.trim_prefix("res://")
		if not suffix.is_empty() and not _relative_errors(suffix).is_empty():
			return ["Invalid resource content root."]
	else:
		if not candidate.is_absolute_path() or candidate.contains("://") or candidate.contains("\\") or candidate != candidate.simplify_path():
			return ["File content roots must be normalized absolute local directories."]
	if not DirAccess.dir_exists_absolute(candidate):
		return ["Content root directory does not exist: " + candidate]
	var links := _symlink_errors(candidate)
	if not links.is_empty(): return links
	_root = candidate
	_backend = backend
	return []


func get_settings() -> Dictionary:
	return {"root": _root, "backend": _backend}


func resolve(relative_path: String, must_exist: bool = true) -> Dictionary:
	var errors := _relative_errors(relative_path)
	if not errors.is_empty(): return {"path": "", "errors": errors}
	var path := _root.path_join(relative_path)
	errors = _symlink_errors(path)
	if not errors.is_empty(): return {"path": "", "errors": errors}
	if must_exist and not FileAccess.file_exists(path) and not (_backend == "resources" and ResourceLoader.exists(path)):
		return {"path": "", "errors": ["Missing content file: " + relative_path]}
	return {"path": path, "errors": []}


func read_bytes(relative_path: String, expected_sha256: String = "") -> Dictionary:
	if not expected_sha256.is_empty() and not _valid_sha256(expected_sha256):
		return {"bytes": PackedByteArray(), "errors": ["Expected SHA-256 must contain 64 lowercase hexadecimal digits."]}
	var resolved := resolve(relative_path)
	if not resolved.errors.is_empty(): return {"bytes": PackedByteArray(), "errors": resolved.errors}
	var file := FileAccess.open(resolved.path, FileAccess.READ)
	if file == null:
		return {"bytes": PackedByteArray(), "errors": ["Cannot read source bytes: " + relative_path]}
	var bytes := file.get_buffer(file.get_length())
	if bytes.size() != file.get_length():
		return {"bytes": PackedByteArray(), "errors": ["Incomplete content read: " + relative_path]}
	if not expected_sha256.is_empty():
		var hash := HashingContext.new()
		hash.start(HashingContext.HASH_SHA256)
		hash.update(bytes)
		if hash.finish().hex_encode() != expected_sha256:
			return {"bytes": PackedByteArray(), "errors": ["Content SHA-256 mismatch: " + relative_path]}
	return {"bytes": bytes, "errors": []}


func read_json(relative_path: String) -> Dictionary:
	if relative_path.get_extension().to_lower() != "json":
		return {"value": null, "errors": ["Content JSON bindings must name a .json file."]}
	var bytes := read_bytes(relative_path)
	if not bytes.errors.is_empty(): return {"value": null, "errors": bytes.errors}
	var parsed := JSON.new()
	if parsed.parse(bytes.bytes.get_string_from_utf8()) != OK:
		return {"value": null, "errors": ["Invalid content JSON: " + relative_path + " at line " + str(parsed.get_error_line())]}
	return {"value": parsed.data, "errors": []}


func load_texture(relative_path: String, mipmaps: bool = false) -> Dictionary:
	var result := load_image(relative_path, mipmaps)
	if not result.errors.is_empty(): return result
	return {"resource": ImageTexture.create_from_image(result.resource), "errors": []}


func load_image(relative_path: String, mipmaps: bool = false) -> Dictionary:
	if relative_path.get_extension().to_lower() not in ["png", "jpg", "jpeg", "webp"]:
		return _failure("Unsupported content image format: " + relative_path)
	var resolved := resolve(relative_path)
	if not resolved.errors.is_empty(): return {"resource": null, "errors": resolved.errors}
	var picture: Image
	if _backend == "resources" and not FileAccess.file_exists(resolved.path):
		var texture := ResourceLoader.load(resolved.path) as Texture2D
		if texture != null: picture = texture.get_image()
	else:
		var bytes := read_bytes(relative_path)
		if not bytes.errors.is_empty(): return {"resource": null, "errors": bytes.errors}
		picture = Image.new()
		var decoded := ERR_FILE_UNRECOGNIZED
		match relative_path.get_extension().to_lower():
			"png": decoded = picture.load_png_from_buffer(bytes.bytes)
			"jpg", "jpeg": decoded = picture.load_jpg_from_buffer(bytes.bytes)
			"webp": decoded = picture.load_webp_from_buffer(bytes.bytes)
		if decoded != OK: return _failure("Cannot decode content image: " + relative_path)
	if picture == null or picture.is_empty(): return _failure("Cannot decode content image: " + relative_path)
	if picture.is_compressed() and picture.decompress() != OK:
		return _failure("Cannot decompress content image: " + relative_path)
	if mipmaps and not picture.has_mipmaps(): picture.generate_mipmaps()
	return {"resource": picture, "errors": []}


func load_audio(relative_path: String, expected_sha256: String = "") -> Dictionary:
	var extension := relative_path.get_extension().to_lower()
	if extension not in ["mp3", "wav", "ogg"]:
		return _failure("Unsupported content audio format: " + relative_path)
	if not expected_sha256.is_empty() and not _valid_sha256(expected_sha256):
		return _failure("Expected audio SHA-256 must contain 64 lowercase hexadecimal digits.")
	var resolved := resolve(relative_path)
	if not resolved.errors.is_empty(): return {"resource": null, "errors": resolved.errors}
	var stream: AudioStream
	var source := PackedByteArray()
	var raw_source := _backend == "files" or FileAccess.file_exists(resolved.path)
	if raw_source:
		var bytes := read_bytes(relative_path)
		if not bytes.errors.is_empty(): return {"resource": null, "errors": bytes.errors}
		source = bytes.bytes
	else:
		stream = ResourceLoader.load(resolved.path) as AudioStream
		# MP3 stores the exact compressed source bytes, including in a PCK where
		# the source path is remapped to an imported resource.
		if stream is AudioStreamMP3: source = stream.data
		elif not expected_sha256.is_empty() and FileAccess.file_exists(resolved.path):
			source = FileAccess.get_file_as_bytes(resolved.path)
	if not expected_sha256.is_empty():
		if source.is_empty(): return _failure("Source bytes are unavailable for audio hash verification: " + relative_path)
		var hash := HashingContext.new()
		hash.start(HashingContext.HASH_SHA256)
		hash.update(source)
		if hash.finish().hex_encode() != expected_sha256:
			return _failure("Audio SHA-256 mismatch: " + relative_path)
	if raw_source:
		match extension:
			"mp3": stream = AudioStreamMP3.load_from_buffer(source)
			"wav": stream = AudioStreamWAV.load_from_buffer(source)
			"ogg": stream = AudioStreamOggVorbis.load_from_buffer(source)
	if stream == null or not is_finite(stream.get_length()) or stream.get_length() <= 0.0:
		return _failure("Cannot decode content audio: " + relative_path)
	return {"resource": stream, "errors": []}


func load_video(relative_path: String) -> Dictionary:
	if relative_path.get_extension().to_lower() != "ogv":
		return _failure("Content video supports Ogg Theora .ogv files only.")
	var resolved := resolve(relative_path)
	if not resolved.errors.is_empty(): return {"resource": null, "errors": resolved.errors}
	var stream: VideoStream
	if _backend == "resources" and not FileAccess.file_exists(resolved.path):
		stream = ResourceLoader.load(resolved.path) as VideoStream
	else:
		var file := FileAccess.open(resolved.path, FileAccess.READ)
		if file == null or file.get_length() < 4 or file.get_buffer(4).get_string_from_ascii() != "OggS":
			return _failure("Invalid Ogg video container: " + relative_path)
		stream = VideoStreamTheora.new()
		stream.file = resolved.path
	if stream == null: return _failure("Cannot load content video: " + relative_path)
	# Decoding is asynchronous in VideoStreamPlayer; playback is the host's check.
	return {"resource": stream, "errors": []}


static func _relative_errors(path: String) -> Array[String]:
	if path.is_empty() or path.is_absolute_path() or path.contains(":") or path.contains("\\") or path.to_utf8_buffer().has(0):
		return ["Content bindings must be nonempty relative paths without a scheme or backslashes."]
	for segment: String in path.split("/", true):
		if segment in ["", ".", ".."]:
			return ["Content bindings must not contain empty, dot or parent segments."]
	return []


static func _symlink_errors(path: String) -> Array[String]:
	# Imported PCK resources are virtual. In an editor/source project, also
	# check the actual files so a project-local symlink cannot escape the root.
	if path.begins_with("res://") and not OS.has_feature("editor"): return []
	var absolute := ProjectSettings.globalize_path(path)
	var current := absolute.get_base_dir()
	var directory := DirAccess.open(current)
	if directory != null and directory.is_link(absolute.get_file()):
		return ["Content paths must not use symbolic links: " + path]
	while current != current.get_base_dir():
		var parent := DirAccess.open(current.get_base_dir())
		if parent != null and parent.is_link(current.get_file()):
			return ["Content paths must not use symbolic links: " + path]
		current = current.get_base_dir()
	return []


static func _valid_sha256(value: String) -> bool:
	if value.length() != 64: return false
	for character: String in value:
		if not character in "0123456789abcdef": return false
	return true


static func _failure(message: String) -> Dictionary:
	return {"resource": null, "errors": [message]}
