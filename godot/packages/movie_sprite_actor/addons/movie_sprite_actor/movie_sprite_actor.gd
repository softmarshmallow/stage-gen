extends Node2D

## Movie Sprite Actor: pre-rendered body motion with independent facial states.
## Existing movie_sprite file/manifest names retain their preparation lineage.
## The host owns the clock, facial timing, speech and actor transform. This node
## draws one source-sized canvas at its origin and never invokes preparation.
signal playback_ready
signal failed(errors: Array[String])

const FACE_SHADER = preload("res://addons/movie_sprite_actor/compositor.gdshader")
const CONTENT_IO = preload("res://addons/content_io/local_content.gd")
const MAX_RESIDENT_PAGES := 2
const MAX_TEXTURE_EDGE := 4096
const MAX_ATLAS_PIXELS := 8388608
const MAX_FACE_BYTES := 64 * 1024 * 1024
const MAX_SOURCE_BYTES := 64 * 1024 * 1024
const MAX_MANIFEST_BYTES := 4 * 1024 * 1024
const MAX_FRAME_COUNT := 1000000
const MAX_PAGE_COUNT := 4096
const MAX_STATES_PER_CHANNEL := 32
const MAX_FPS := 240.0
const MAX_CLOCK_SECONDS := 1.0e12

var _loader: RefCounted
var _manifest: Dictionary = {}
var _frame_size := Vector2i.ZERO
var _atlas_size := Vector2i.ZERO
var _cells_per_page := 0
var _duration_seconds := 0.0
var _sprite: Sprite2D
var _material: ShaderMaterial
var _face_textures: Dictionary = {}
var _pages: Dictionary = {}
var _worker: Thread
var _worker_page := -1
var _frame_index := 0
var _displayed_page := -1
var _clock_seconds := 0.0
var _pending_clock := -1.0
var _loop_count := 0
var _paused := false
var _state := "closed"
var _eyes := "rest"
var _mouth := "rest"
var _errors: Array[String] = []
var _decoded_pages := 0
var _buffering_count := 0
var _was_ready := false
var _session_epoch := 0


func configure(loader: RefCounted, manifest_path: String) -> Array[String]:
	shutdown()
	_errors.clear()
	_manifest = {}
	_frame_size = Vector2i.ZERO
	_atlas_size = Vector2i.ZERO
	_cells_per_page = 0
	_duration_seconds = 0.0
	_frame_index = 0
	_clock_seconds = 0.0
	_pending_clock = -1.0
	_loop_count = 0
	_decoded_pages = 0
	_buffering_count = 0
	_paused = false
	_was_ready = false
	_eyes = "rest"
	_mouth = "rest"
	if loader == null or not loader.has_method("read_bytes") or not loader.has_method("get_settings"):
		return _fail(["Movie sprite requires the local content loader."])
	# A private immutable loader prevents host reconfiguration during a worker read.
	_loader = CONTENT_IO.new()
	var settings: Dictionary = loader.get_settings()
	var loader_errors: Array[String] = _loader.configure(str(settings.get("root", "")), str(settings.get("backend", "")))
	if not loader_errors.is_empty(): return _fail(loader_errors)
	var source_errors := _source_bounds(_loader, manifest_path, MAX_MANIFEST_BYTES)
	if not source_errors.is_empty(): return _fail(source_errors)
	var document: Dictionary = _loader.read_json(manifest_path)
	if not document.errors.is_empty(): return _fail(document.errors)
	if not document.value is Dictionary: return _fail(["Movie sprite manifest must be an object."])
	_manifest = document.value
	var validation := _validate_manifest()
	if not validation.is_empty():
		_manifest = {}
		_frame_size = Vector2i.ZERO
		_atlas_size = Vector2i.ZERO
		_cells_per_page = 0
		_duration_seconds = 0.0
		return _fail(validation)
	_material = ShaderMaterial.new()
	_material.shader = FACE_SHADER
	_material.set_shader_parameter("frame_extent", Vector2(1.0 / float(_manifest.columns), 1.0 / float(_manifest.rows)))
	_sprite = Sprite2D.new()
	_sprite.centered = false
	_sprite.region_enabled = true
	_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	_sprite.material = _material
	add_child(_sprite)
	for family: String in ["eyes", "mouths"]:
		_face_textures[family] = {}
		for state_name: String in _manifest[family]:
			var decoded := _decode_png(_loader, _manifest[family][state_name], _frame_size)
			if not decoded.errors.is_empty(): return _fail(decoded.errors)
			_face_textures[family][state_name] = ImageTexture.create_from_image(decoded.image)
	_state = "loading"
	return _request_page(0)


func advance(delta: float) -> void:
	if _state in ["closed", "failed"]: return
	var epoch := _session_epoch
	_poll_worker()
	if _state == "failed" or _session_epoch != epoch: return
	if _pending_clock >= 0.0:
		var duration := _duration_seconds
		var pending_frame := int(floor(fposmod(_pending_clock, duration) * float(_manifest.fps))) % int(_manifest.frame_count)
		var pending_page := _page_for_frame(pending_frame)
		if not _pages.has(pending_page):
			_request_page(pending_page)
			return
		_clock_seconds = _pending_clock
		_pending_clock = -1.0
		_frame_index = pending_frame
		_loop_count = int(floor(_clock_seconds / duration))
		_show_frame()
		if not _enter_ready(): return
		_prefetch_next()
		return
	var current_page := _page_for_frame(_frame_index)
	if not _pages.has(current_page):
		_request_page(current_page)
		return
	_show_frame()
	# Loading/buffering and pause never accumulate elapsed wall time. The next
	# advance begins from the last accepted clock when a page is available.
	if _state in ["loading", "buffering"]:
		if not _enter_ready(): return
		_prefetch_next()
		return
	if not _paused and is_finite(delta) and delta > 0.0:
		var duration := _duration_seconds
		var next_clock := _clock_seconds + delta
		if not is_finite(next_clock) or next_clock > MAX_CLOCK_SECONDS: return
		var next_frame := int(floor(fposmod(next_clock, duration) * float(_manifest.fps))) % int(_manifest.frame_count)
		var next_page := _page_for_frame(next_frame)
		if not _pages.has(next_page):
			# Hold the last rendered frame; request the page needed by this step.
			_state = "buffering"
			_pending_clock = next_clock
			_buffering_count += 1
			_request_page(next_page)
			return
		_clock_seconds = next_clock
		_loop_count = int(floor(_clock_seconds / duration))
		_frame_index = next_frame
		_show_frame()
	_prefetch_next()


func seek(seconds: float) -> Array[String]:
	if _state in ["closed", "failed"]: return ["Movie sprite is not configured."]
	if not is_finite(seconds) or seconds < 0.0 or seconds > MAX_CLOCK_SECONDS: return ["Movie sprite seek must be finite and between zero and 1e12 seconds."]
	var duration := _duration_seconds
	_clock_seconds = seconds
	_pending_clock = -1.0
	_loop_count = int(floor(seconds / duration))
	_frame_index = int(floor(fposmod(seconds, duration) * float(_manifest.fps))) % int(_manifest.frame_count)
	var epoch := _session_epoch
	_poll_worker()
	if _state == "failed": return _errors.duplicate()
	if _session_epoch != epoch: return ["Movie sprite seek was interrupted by a lifecycle callback."]
	if _pages.has(_page_for_frame(_frame_index)):
		_show_frame()
		_enter_ready()
	else:
		_state = "buffering"
		_request_page(_page_for_frame(_frame_index))
	return []


func set_paused(value: bool) -> void:
	_paused = value
	if value: _pending_clock = -1.0


func set_eye_state(value: String) -> Array[String]:
	return _set_face("eyes", value)


func set_mouth_state(value: String) -> Array[String]:
	return _set_face("mouths", value)


func snapshot() -> Dictionary:
	var resident: Array = _pages.keys()
	resident.sort()
	return {
		"state": _state, "character_id": _manifest.get("character_id", ""),
		"frame_size": _frame_size, "frame_count": _manifest.get("frame_count", 0),
		"fps": _manifest.get("fps", 0.0), "duration_seconds": _duration_seconds,
		"page_count": _manifest.get("pages", []).size(),
		"frame_index": _frame_index, "displayed_page": _displayed_page, "loop_count": _loop_count,
		"clock_seconds": _clock_seconds, "paused": _paused,
		"pending_clock_seconds": _pending_clock,
		"buffering": _state in ["loading", "buffering"],
		"resident_pages": resident, "resident_page_count": _pages.size(),
		"max_resident_pages": MAX_RESIDENT_PAGES,
		"worker_active": _worker != null, "worker_page": _worker_page,
		"eyes": _eyes, "mouth": _mouth, "errors": _errors.duplicate(),
		"decoded_pages": _decoded_pages, "buffering_count": _buffering_count,
		"eye_states": ["rest"] + _manifest.get("eyes", {}).keys(),
		"mouth_states": ["rest"] + _manifest.get("mouths", {}).keys(),
	}


func get_state() -> Dictionary:
	return snapshot()


func shutdown() -> void:
	_session_epoch += 1
	if _worker != null:
		_worker.wait_to_finish()
		_worker = null
	_worker_page = -1
	if is_instance_valid(_sprite):
		_sprite.texture = null
		_sprite.material = null
		_sprite.free()
	_sprite = null
	_displayed_page = -1
	_material = null
	_pages.clear()
	_face_textures.clear()
	_loader = null
	_state = "closed"
	_pending_clock = -1.0


func _exit_tree() -> void:
	shutdown()


func _set_face(family: String, value: String) -> Array[String]:
	if _state in ["closed", "failed"]: return ["Movie sprite is not configured."]
	if value != "rest" and not _face_textures.get(family, {}).has(value):
		return ["Unsupported movie sprite " + family + " state: " + value]
	var prefix := "eye" if family == "eyes" else "mouth"
	_material.set_shader_parameter(prefix + "_enabled", value != "rest")
	if value != "rest": _material.set_shader_parameter(prefix + "_texture", _face_textures[family][value])
	if family == "eyes": _eyes = value
	else: _mouth = value
	return []


func _page_for_frame(frame: int) -> int:
	return frame / _cells_per_page


func _show_frame() -> void:
	var page := _page_for_frame(_frame_index)
	if not _pages.has(page): return
	var cell := _frame_index % _cells_per_page
	var cell_xy := Vector2i(cell % int(_manifest.columns), cell / int(_manifest.columns))
	_sprite.texture = _pages[page]
	_displayed_page = page
	_material.set_shader_parameter("body_texture", _pages[page])
	_sprite.region_rect = Rect2(Vector2(cell_xy * _frame_size), Vector2(_frame_size))
	_material.set_shader_parameter("frame_origin", Vector2(cell_xy) / Vector2(float(_manifest.columns), float(_manifest.rows)))


func _prefetch_next() -> void:
	var current := _page_for_frame(_frame_index)
	var next: int = (current + 1) % _manifest.pages.size()
	for resident: int in _pages.keys():
		if resident != current and resident != next: _pages.erase(resident)
	if not _pages.has(next): _request_page(next)


func _request_page(page: int) -> Array[String]:
	if _worker != null or _pages.has(page) or _state in ["closed", "failed"]: return []
	_worker = Thread.new()
	_worker_page = page
	var size := _atlas_size
	var result := _worker.start(_decode_png.bind(_loader, _manifest.pages[page].duplicate(), size))
	if result != OK:
		_worker = null
		_worker_page = -1
		return _fail(["Cannot start movie sprite page decoder: " + error_string(result)])
	return []


func _poll_worker() -> void:
	if _worker == null or _worker.is_alive(): return
	var page := _worker_page
	var decoded: Dictionary = _worker.wait_to_finish()
	_worker = null
	_worker_page = -1
	if not decoded.errors.is_empty():
		_fail(decoded.errors)
		return
	# Upload only on the main thread, after trimming the bounded GPU cache.
	while _pages.size() >= MAX_RESIDENT_PAGES:
		var discard: int = _pages.keys()[0]
		for candidate: int in _pages.keys():
			if candidate != _displayed_page:
				discard = candidate
				break
		_pages.erase(discard)
	_pages[page] = ImageTexture.create_from_image(decoded.image)
	_decoded_pages += 1


static func _decode_png(loader: RefCounted, entry: Dictionary, expected_size: Vector2i) -> Dictionary:
	var source_errors := _source_bounds(loader, entry.file, MAX_SOURCE_BYTES)
	if not source_errors.is_empty(): return {"image": null, "errors": source_errors}
	var result: Dictionary = loader.read_bytes(entry.file, entry.sha256)
	if not result.errors.is_empty(): return {"image": null, "errors": result.errors}
	var bytes: PackedByteArray = result.bytes
	# Inspect IHDR before handing compressed pixels to the decoder. The canvas was
	# admitted before loading, so malformed headers cannot request a larger image.
	if bytes.size() > MAX_SOURCE_BYTES or not _png_matches_size(bytes, expected_size):
		return {"image": null, "errors": ["Movie sprite PNG header or dimensions failed: " + str(entry.file)]}
	var picture := Image.new()
	if picture.load_png_from_buffer(bytes) != OK or picture.get_size() != expected_size:
		return {"image": null, "errors": ["Movie sprite PNG decode or dimensions failed: " + str(entry.file)]}
	picture.convert(Image.FORMAT_RGBA8)
	return {"image": picture, "errors": []}


static func _source_bounds(loader: RefCounted, reference: String, maximum_bytes: int) -> Array[String]:
	var resolved: Dictionary = loader.resolve(reference)
	if not resolved.errors.is_empty():
		var errors: Array[String] = []
		errors.assign(resolved.errors)
		return errors
	# content_io owns path admission and verifies the exact bytes subsequently
	# returned. This preflight prevents allocating an oversized immutable source.
	# As with content_io, concurrent filesystem replacement is outside the contract.
	var file := FileAccess.open(resolved.path, FileAccess.READ)
	if file == null: return ["Movie sprite requires retained source bytes: " + reference]
	if file.get_length() <= 0 or file.get_length() > maximum_bytes:
		return ["Movie sprite source exceeds the encoded byte limit: " + reference]
	return []


static func _png_matches_size(bytes: PackedByteArray, expected: Vector2i) -> bool:
	if bytes.size() < 33: return false
	if bytes.slice(0, 8) != PackedByteArray([137, 80, 78, 71, 13, 10, 26, 10]): return false
	if _big_endian_u32(bytes, 8) != 13 or bytes.slice(12, 16).get_string_from_ascii() != "IHDR": return false
	return _big_endian_u32(bytes, 16) == expected.x and _big_endian_u32(bytes, 20) == expected.y


static func _big_endian_u32(bytes: PackedByteArray, offset: int) -> int:
	return (int(bytes[offset]) << 24) | (int(bytes[offset + 1]) << 16) | (int(bytes[offset + 2]) << 8) | int(bytes[offset + 3])


func _validate_manifest() -> Array[String]:
	if not _positive_integer(_manifest.get("schema_version"), 1) or not _manifest.get("character_id") is String or str(_manifest.character_id).is_empty():
		return ["Unsupported movie sprite manifest identity or schema version."]
	if _manifest.get("patch_application") != "replace_selected_rgb_preserve_original_alpha":
		return ["Movie sprite requires prepared RGB replacement masks preserving body alpha."]
	var size: Variant = _manifest.get("frame_size")
	if not size is Array or size.size() != 2 or not _positive_integer(size[0], MAX_TEXTURE_EDGE) or not _positive_integer(size[1], MAX_TEXTURE_EDGE):
		return ["Movie sprite frame_size requires two positive integer dimensions at most 4096."]
	if not _positive_integer(_manifest.get("frame_count"), MAX_FRAME_COUNT):
		return ["Movie sprite frame_count must be a positive integer at most 1000000."]
	var fps: Variant = _manifest.get("fps")
	if not _finite_number(fps) or float(fps) <= 0.0 or float(fps) > MAX_FPS:
		return ["Movie sprite fps must be finite, positive and at most 240."]
	if not _positive_integer(_manifest.get("columns"), MAX_TEXTURE_EDGE) or not _positive_integer(_manifest.get("rows"), MAX_TEXTURE_EDGE):
		return ["Movie sprite atlas rows and columns must be positive integers at most 4096."]
	_frame_size = Vector2i(int(size[0]), int(size[1]))
	_atlas_size = _frame_size * Vector2i(int(_manifest.columns), int(_manifest.rows))
	if _atlas_size.x > MAX_TEXTURE_EDGE or _atlas_size.y > MAX_TEXTURE_EDGE or _atlas_size.x * _atlas_size.y > MAX_ATLAS_PIXELS:
		return ["Movie sprite atlas exceeds the 4096-edge or 8388608-pixel resource limit."]
	_cells_per_page = int(_manifest.columns) * int(_manifest.rows)
	_duration_seconds = float(_manifest.frame_count) / float(fps)
	if not is_finite(_duration_seconds) or _duration_seconds <= 0.0:
		return ["Movie sprite timebase must produce a finite positive duration."]
	var expected_pages := (int(_manifest.frame_count) + _cells_per_page - 1) / _cells_per_page
	if expected_pages > MAX_PAGE_COUNT or not _manifest.get("pages") is Array or _manifest.pages.size() != expected_pages:
		return ["Movie sprite requires exactly ceil(frame_count / (columns * rows)) pages, at most 4096."]
	var entries: Array = _manifest.pages.duplicate()
	var face_count := 0
	for family: String in ["eyes", "mouths"]:
		if not _manifest.get(family) is Dictionary or _manifest[family].size() > MAX_STATES_PER_CHANNEL:
			return ["Movie sprite manifest requires " + family + " bindings with at most 32 states."]
		for state_name: Variant in _manifest[family]:
			if not state_name is String or not _valid_state_name(state_name):
				return ["Movie sprite state names require lower_snake_case; rest is reserved."]
			entries.append(_manifest[family][state_name])
			face_count += 1
	if _frame_size.x * _frame_size.y * 4 * face_count > MAX_FACE_BYTES:
		return ["Movie sprite face textures exceed the 64 MiB decoded RGBA limit."]
	for entry: Variant in entries:
		if not entry is Dictionary or not entry.get("file") is String or not entry.get("sha256") is String:
			return ["Movie sprite texture bindings require file and SHA-256 strings."]
		if str(entry.file).get_extension().to_lower() != "png" or not _valid_sha256(entry.sha256):
			return ["Movie sprite texture bindings require PNG and lowercase SHA-256."]
		var resolved: Dictionary = _loader.resolve(entry.file)
		if not resolved.errors.is_empty():
			var errors: Array[String] = []
			errors.assign(resolved.errors)
			return errors
	return []


static func _finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))


static func _positive_integer(value: Variant, maximum: int) -> bool:
	return _finite_number(value) and float(value) > 0.0 and float(value) <= maximum and float(value) == floor(float(value))


static func _valid_state_name(value: String) -> bool:
	if value.is_empty() or value.length() > 64 or value == "rest": return false
	if value[0] not in "abcdefghijklmnopqrstuvwxyz": return false
	for segment: String in value.split("_", true):
		if segment.is_empty(): return false
		for character: String in segment:
			if character not in "abcdefghijklmnopqrstuvwxyz0123456789": return false
	return true


func _enter_ready() -> bool:
	var epoch := _session_epoch
	_state = "ready"
	if not _was_ready:
		_was_ready = true
		playback_ready.emit()
	# Host callbacks may dispose/reconfigure the same actor. The originating
	# operation must not prefetch or change clocks in a replacement session.
	return _session_epoch == epoch and _state == "ready"


static func _valid_sha256(value: String) -> bool:
	if value.length() != 64: return false
	for character: String in value:
		if character not in "0123456789abcdef": return false
	return true


func _fail(errors: Array) -> Array[String]:
	var reported: Array[String] = []
	reported.assign(errors)
	shutdown()
	_errors = reported.duplicate()
	_state = "failed"
	failed.emit(reported.duplicate())
	# Return this operation's failure even if its callback starts a new session.
	return reported
