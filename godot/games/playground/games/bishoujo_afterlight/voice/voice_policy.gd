extends RefCounted

## Afterlight-owned casting and recording lookup. This never calls a provider.
## Display strings remain authoritative; speech scripts are optional overrides.
const DIRECTORY := "res://games/bishoujo_afterlight/voice/"
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const LANGUAGES := ["en", "ko"]
const POLICIES := ["none", "generated"]
const PROFILE_FIELDS := ["provider", "model", "provider_voice", "language_code", "stability", "output_format"]
var _lines: Dictionary = {}
var _manifest: Dictionary = {}
var _streams: Dictionary = {}
var _inventory: Array[Dictionary] = []
var _unused_configuration: Array[Dictionary] = []
var _unused_recordings: Array[Dictionary] = []
var _content_loader: RefCounted = LOCAL_CONTENT.new()


func load_project(beats: Array, text_sets: Dictionary, content_loader: RefCounted = null) -> Array[String]:
	var errors: Array[String] = []
	var loader: RefCounted = content_loader if content_loader != null else LOCAL_CONTENT.new()
	var policy := _read_json(loader, DIRECTORY + "voices.json", errors)
	var casting := _read_json(loader, DIRECTORY + "cast.json", errors, true)
	var manifest := _read_json(loader, DIRECTORY + "manifest.json", errors, true)
	if not errors.is_empty(): return errors
	errors = configure(policy, casting, manifest, beats, text_sets)
	if errors.is_empty(): _content_loader = loader
	return errors


func configure(policy: Dictionary, casting: Dictionary, manifest: Dictionary, beats: Array, text_sets: Dictionary) -> Array[String]:
	var errors: Array[String] = []
	if policy.get("schema_version") != 1 or not policy.get("speakers") is Dictionary or not policy.get("line_overrides", {}) is Dictionary or not policy.get("speech_scripts", {}) is Dictionary:
		return ["Afterlight voice policy requires schema_version 1 and dictionary speakers, line_overrides and speech_scripts."]
	for document: Dictionary in [casting, manifest]:
		if not document.is_empty() and document.get("schema_version") != 1:
			errors.append("Afterlight casting and recording manifests require schema_version 1.")
	if not casting.get("voices", {}) is Dictionary or not manifest.get("lines", {}) is Dictionary:
		errors.append("Afterlight casting voices and manifest lines must be dictionaries.")
	var speakers: Dictionary = policy["speakers"]
	if not speakers.get("protagonist") is Dictionary or speakers.get("protagonist", {}).get("voice_policy") != "none":
		errors.append("Afterlight explicitly keeps the protagonist's voice_policy as none.")
	for speaker: Variant in speakers:
		if not speakers[speaker] is Dictionary or speakers[speaker].get("voice_policy") not in POLICIES:
			errors.append("Invalid Afterlight speaker voice_policy: " + str(speaker))
	if not errors.is_empty(): return errors
	for speaker: Variant in casting.get("voices", {}):
		if not casting["voices"][speaker] is Dictionary:
			errors.append("Afterlight casting requires a language dictionary for speaker: " + str(speaker))
	for language: Variant in manifest.get("lines", {}):
		if not manifest["lines"][language] is Dictionary:
			errors.append("Afterlight recording manifest requires a line dictionary for language: " + str(language))
	if not errors.is_empty(): return errors
	var authored := _authored_lines(beats)
	var unused_configuration: Array[Dictionary] = []
	for line_id: Variant in policy.get("line_overrides", {}):
		if not line_id is String or str(line_id).strip_edges().is_empty() or not policy["line_overrides"][line_id] is Dictionary:
			errors.append("Voice overrides require a stable text ID and dictionary: " + str(line_id))
			continue
		var override: Dictionary = policy["line_overrides"][line_id]
		for field: Variant in override:
			if field not in ["speaker", "voice_policy", "reason"]:
				errors.append("Unknown Afterlight voice override field: " + str(field))
		if override.has("voice_policy") and override["voice_policy"] not in POLICIES:
			errors.append("Invalid Afterlight line voice_policy: " + str(line_id))
		if override.has("speaker") and (not override["speaker"] is String or str(override["speaker"]).strip_edges().is_empty()):
			errors.append("Afterlight line voice speaker must be a nonempty ID: " + str(line_id))
		if override.has("reason") and not override["reason"] is String:
			errors.append("Afterlight voice override reason must be text: " + str(line_id))
		if not authored.has(line_id):
			unused_configuration.append({"kind": "line_override", "line_id": line_id})
	for language: Variant in policy.get("speech_scripts", {}):
		if language not in LANGUAGES or not policy["speech_scripts"][language] is Dictionary:
			errors.append("Speech scripts require a supported language dictionary.")
			continue
		for line_id: Variant in policy["speech_scripts"][language]:
			var script: Variant = policy["speech_scripts"][language][line_id]
			if not line_id is String or str(line_id).strip_edges().is_empty() or not script is String or str(script).strip_edges().is_empty():
				errors.append("Speech scripts require nonempty text at a stable text ID: " + str(line_id))
			elif not authored.has(line_id):
				unused_configuration.append({"kind": "speech_script", "line_id": line_id, "language": language})
	if not errors.is_empty(): return errors
	var inventory: Array[Dictionary] = []
	var lines := {}
	for language: String in LANGUAGES:
		if not text_sets.get(language) is Dictionary:
			errors.append("Afterlight voice inventory requires display text set: " + language)
			continue
		lines[language] = {}
		for line_id: String in authored:
			var entry: Dictionary = authored[line_id]
			var override: Dictionary = policy.get("line_overrides", {}).get(line_id, {})
			var speaker := str(override.get("speaker", entry["speaker_id"]))
			if not speakers.has(speaker):
				errors.append("Voice line names an unknown speaker: " + line_id)
				continue
			var voice_policy := str(override.get("voice_policy", speakers[speaker]["voice_policy"]))
			if voice_policy not in POLICIES or (speaker == "protagonist" and voice_policy != "none"):
				errors.append("Invalid voice policy, or attempted protagonist voice: " + line_id)
				continue
			if not text_sets[language].get(line_id) is String:
				errors.append("Voice inventory is missing display text: " + language + "/" + line_id)
				continue
			var display: String = text_sets[language][line_id]
			var speech: String = policy.get("speech_scripts", {}).get(language, {}).get(line_id, display)
			var profile: Variant = casting.get("voices", {}).get(speaker, {}).get(language, {})
			if not profile is Dictionary:
				errors.append("Voice casting profile must be a dictionary: " + speaker + "/" + language)
				continue
			var generation_profile := {}
			for field: String in PROFILE_FIELDS:
				if profile.has(field): generation_profile[field] = profile[field]
			var item := {"line_id": line_id, "language": language, "speaker_id": speaker,
				"voice_policy": voice_policy, "display_text": display, "speech_text": speech,
				"voice_profile": generation_profile, "beat_id": entry["beat_id"], "kind": entry["kind"]}
			item["source_revision"] = _source_revision(item)
			inventory.append(item)
			lines[language][line_id] = item
	if not errors.is_empty(): return errors
	_lines = lines
	_inventory = inventory
	_manifest = manifest.duplicate(true)
	_unused_configuration = unused_configuration
	_unused_recordings.clear()
	for language: Variant in _manifest.get("lines", {}):
		for line_id: Variant in _manifest["lines"][language]:
			if not _lines.get(language, {}).has(line_id):
				_unused_recordings.append({"line_id": line_id, "language": language})
	_streams.clear()
	return errors


func get_inventory() -> Dictionary:
	return {"schema_version": 1, "lines": _inventory.duplicate(true)}


func get_status_report() -> Dictionary:
	var counts := {"none": 0, "pending": 0, "ready": 0, "missing": 0, "failed": 0, "stale": 0}
	var lines: Array[Dictionary] = []
	for item: Dictionary in _inventory:
		var resolved := resolve(item["line_id"], item["language"])
		var line := {}
		for field: String in ["line_id", "language", "speaker_id", "voice_policy", "status", "source_revision", "path", "reason"]:
			if resolved.has(field): line[field] = resolved[field]
		counts[resolved["status"]] += 1
		lines.append(line)
	return {"schema_version": 1, "counts": counts, "lines": lines,
		"unused_configuration": _unused_configuration.duplicate(true),
		"unused_recordings": _unused_recordings.duplicate(true)}


## Explicit host-supplied streams use the same ready/revision checks, allowing
## prepared AudioStreams without requiring a provider or a particular codec.
func resolve(line_id: String, language: String, supplied_stream: AudioStream = null) -> Dictionary:
	var result: Dictionary = _lines.get(language, {}).get(line_id, {}).duplicate(true)
	result["stream"] = null
	result["status"] = "failed"
	if not result.has("voice_policy"):
		result["reason"] = "unknown_line"
		return result
	if result["voice_policy"] == "none":
		result["status"] = "none"
		return result
	var record: Variant = _manifest.get("lines", {}).get(language, {}).get(line_id, {})
	if not record is Dictionary:
		result["reason"] = "invalid_record"
		return result
	var status := str(record.get("status", "pending"))
	if status == "pending" or record.is_empty():
		result["status"] = "pending"
		return result
	if record.get("source_revision", "") != result["source_revision"]:
		result["status"] = "stale"
		return result
	if status != "ready":
		result["status"] = status if status in ["failed", "missing", "stale"] else "failed"
		return result
	var path := str(record.get("path", ""))
	result["path"] = path
	var stream := supplied_stream
	if stream == null:
		# Existing manifests keep their portable project-relative identity. A
		# selected external root changes resolution, never source revisions.
		var relative_path := path.trim_prefix("res://")
		var resolved: Dictionary = _content_loader.resolve(relative_path)
		if not resolved.errors.is_empty():
			result["status"] = "missing"
			result["reason"] = "recording_path_unavailable"
			return result
		var expected_hash := str(record.get("audio_sha256", ""))
		var cache_key := str(resolved.path) + "|" + str(result["source_revision"]) + "|" + expected_hash
		if _streams.has(cache_key) and FileAccess.file_exists(resolved.path):
			# Recheck current source bytes without decoding the same MP3 again.
			# Imported-only resources use the loader's remap-aware hash path below.
			if not expected_hash.is_empty():
				var bytes: Dictionary = _content_loader.read_bytes(relative_path)
				if not bytes.errors.is_empty():
					result["status"] = "missing"
					result["reason"] = "recording_path_unavailable"
					return result
				var hash := HashingContext.new()
				hash.start(HashingContext.HASH_SHA256)
				hash.update(bytes.bytes)
				if hash.finish().hex_encode() != expected_hash:
					result["reason"] = "audio_hash_mismatch"
					return result
		else:
			var loaded: Dictionary = _content_loader.load_audio(relative_path, expected_hash)
			if not loaded.errors.is_empty():
				result["reason"] = "audio_hash_mismatch" if str(loaded.errors[0]).begins_with("Audio SHA-256 mismatch") else "audio_decode_failed"
				return result
			_streams[cache_key] = loaded.resource
		stream = _streams[cache_key]
	result["status"] = "ready"
	result["stream"] = stream
	return result


func bind_voiceovers() -> Dictionary:
	var result := {"en": {}, "ko": {}}
	for line: Dictionary in _inventory:
		var resolved := resolve(line["line_id"], line["language"])
		if resolved["status"] == "ready":
			result[line["language"]][line["line_id"]] = resolved["stream"]
	return result


static func _source_revision(item: Dictionary) -> String:
	# Length-prefixed UTF-8 fields avoid ambiguity with embedded text newlines.
	# The selected casting profile includes provider, model, voice and settings.
	var source := "afterlight_voice_v1\n"
	for field: String in ["line_id", "language", "speaker_id", "voice_policy", "display_text", "speech_text"]:
		var value := str(item[field])
		source += str(value.to_utf8_buffer().size()) + ":" + value
	var profile := JSON.stringify(item["voice_profile"], "", true)
	source += str(profile.to_utf8_buffer().size()) + ":" + profile
	return source.sha256_text()


static func _authored_lines(beats: Array) -> Dictionary:
	var result := {}
	for beat: Dictionary in beats:
		var speaker := str(beat.get("speaker", ""))
		if speaker.is_empty(): speaker = "protagonist"
		var keys: Array = beat.get("responses", {}).values() if beat.has("responses") else [beat.get("text", "")]
		for key: String in keys:
			if not key.is_empty(): result[key] = {"speaker_id": speaker, "beat_id": beat["id"], "kind": beat["type"]}
	return result


static func _read_json(loader: RefCounted, path: String, errors: Array[String], optional: bool = false) -> Dictionary:
	var relative_path := path.trim_prefix("res://")
	var resolved: Dictionary = loader.resolve(relative_path)
	if optional and not resolved.errors.is_empty() and str(resolved.errors[0]).begins_with("Missing content file:"): return {}
	var parsed: Dictionary = loader.read_json(relative_path)
	if not parsed.errors.is_empty() or not parsed.value is Dictionary:
		errors.append("Cannot read Afterlight voice document: " + path)
		errors.append_array(parsed.errors)
		return {}
	return parsed.value
