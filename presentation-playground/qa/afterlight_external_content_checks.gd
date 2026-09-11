extends SceneTree

const COMPOSITION = preload("res://games/bishoujo_afterlight/root.gd")
const GAME = preload("res://games/bishoujo_afterlight/story.gd")
const LOCAL_CONTENT = preload("res://addons/game_presentation/content/local_content.gd")
const ADAPTER = preload("res://games/bishoujo_afterlight/content_adapter.gd")
const VOICE_POLICY = preload("res://games/bishoujo_afterlight/voice/voice_policy.gd")
var _errors: Array[String] = []

class RejectedHost extends Control:
	var _load_errors: Array[String] = []
	var content: Dictionary = {}


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var arguments := OS.get_cmdline_user_args()
	var index := arguments.find("--content-root")
	if index < 0 or index + 1 >= arguments.size():
		printerr("External Afterlight checks require --content-root ABSOLUTE_DIRECTORY.")
		quit(2)
		return
	var options := {"content-root": arguments[index + 1]}
	var baseline_buses := AudioServer.bus_count
	var default_root := COMPOSITION.new()
	var external_root := COMPOSITION.new()
	_expect(external_root.validate_options(options).is_empty(), "The prepared external content root must validate.")
	var baseline := GAME.new()
	var external := GAME.new()
	default_root.prepare_scene(baseline, "game", {}, {})
	external_root.prepare_scene(external, "game", options, {})
	_expect(baseline._load_errors.is_empty() and external._load_errors.is_empty(), "Both roots must prepare text, catalogs and voices.")
	if _errors.is_empty():
		root.add_child(baseline)
		root.add_child(external)
		baseline.set_process(false)
		external.set_process(false)
		_expect(baseline._load_errors.is_empty() and external._load_errors.is_empty(), "Both complete game instances must initialize their supplied content.")
	if _errors.is_empty():
		_expect(external.content.content_loader.get_settings().backend == "files", "The external host must actually use raw-directory loading.")
		for background_index in baseline._backgrounds.size():
			_same_pixels(baseline._backgrounds[background_index], external._backgrounds[background_index], "background " + str(background_index))
		for field: String in ["_textures", "_portraits", "_details", "_contact_textures", "_burst_textures"]:
			for id: String in baseline.get(field):
				_same_pixels(baseline.get(field)[id], external.get(field)[id], field + "/" + id)
		for mark_id: String in baseline._cast._mark_textures:
			_same_pixels(baseline._cast._mark_textures[mark_id], external._cast._mark_textures[mark_id], "manpu/" + mark_id)
		_expect(baseline.voice_policy.get_inventory() == external.voice_policy.get_inventory(), "Relocation must preserve display/speech text, casting and every source revision.")
		var status: Dictionary = external.voice_policy.get_status_report()
		_expect(status.counts.ready == 80 and status.counts.none == 36, "External recordings must remain all80 ready and36 intentional-none.")
		for language: String in ["en", "ko"]:
			_expect(external.content.voiceovers[language].size() == 40, "Each locale must bind40 prepared recordings.")
			for line_id: String in baseline.content.voiceovers[language]:
				var original: AudioStreamMP3 = baseline.content.voiceovers[language][line_id]
				var relocated: AudioStreamMP3 = external.content.voiceovers[language][line_id]
				_expect(original.data == relocated.data, "Relocation must preserve exact MP3 bytes: " + language + "/" + line_id)
		# Enter every preceding cue in order so the transmission's authored cast,
		# projection, geometry and selected background all come from real direction.
		for beat_index in external.beats.size():
			external._beat_index = beat_index
			external._enter_beat()
			external._advance_clocks(10.0)
			if external.current_beat().id == "eira_on_the_relay": break
		for language: String in ["en", "ko"]:
			external.set_language(language)
			external._begin_text_audio()
			var voice: Dictionary = external.get_voice_state()
			_expect(voice.status == "ready" and voice.playback.active_mode == "voice" and voice.processing.processing, "External " + language + " Eira must use the existing private Transmission Voice route.")
			_expect(voice.playback.bus != voice.playback.voice_bus, "Typing must keep its separate dry route.")
			_expect(external._reveal.sample().phase == "holding", "Ready voice must retain full localized subtitles.")
		external._text_audio.set_paused(true)
		_expect(external._text_audio.get_state().paused, "External playback must obey pause.")
		external._text_audio.stop()
		_expect(not external._text_audio.get_state().voice_playing, "External playback must stop before teardown.")
		_expect(external._load_errors.is_empty(), "External direction must remain free of host errors.")
	# Empty/malformed external metadata must fail preparation, with no fallback
	# to the checkout's manpu/text data and no mutation of the canonical content.
	var temporary := DirAccess.create_temp("afterlight-missing", true)
	var path := temporary.get_current_dir()
	if OS.get_name() == "macOS" and path.begins_with("/var/"): path = "/private" + path
	var missing := RejectedHost.new()
	COMPOSITION.new().prepare_scene(missing, "game", {"content-root": path}, {})
	_expect(not missing._load_errors.is_empty() and missing.content.is_empty(), "Missing external text must be refused rather than loading bundled content.")
	missing.free()
	DirAccess.make_dir_recursive_absolute(path.path_join("assets/manpu"))
	var file := FileAccess.open(path.path_join("assets/manpu/catalog.json"), FileAccess.WRITE)
	file.store_string("{\"manpu\":[{\"id\":\"unsafe\",\"file\":\"../outside.png\"}]}")
	file.close()
	var loader := LOCAL_CONTENT.new()
	loader.configure(path, "files")
	_expect(not ADAPTER.load_manpu(loader).errors.is_empty(), "Catalog entries must not escape the selected root.")
	if not external.content.is_empty(): _cache_checks(external, loader, path)
	for item: String in ["assets/manpu/catalog.json", "assets/manpu", "assets"]:
		DirAccess.remove_absolute(path.path_join(item))
	DirAccess.remove_absolute(path)
	baseline.free()
	external.free()
	# AudioServer retires stopped playback instances on its mixer update.
	await create_timer(0.2).timeout
	_expect(AudioServer.bus_count == baseline_buses, "Both game instances must release their own audio buses.")
	for issue: String in _errors: printerr("FAIL External Afterlight: " + issue)
	if _errors.is_empty(): print("PASS External Afterlight: identical default/external pixels and 80 MP3 files, 80 ready / 36 none, EN/KO transmission routing, full subtitles, dry typing, pause/stop, missing/unsafe content refusal and isolated cleanup; listening not performed")
	quit(0 if _errors.is_empty() else 1)


func _same_pixels(first: Texture2D, second: Texture2D, label: String) -> void:
	_expect(first.get_size() == second.get_size() and first.get_image().get_data() == second.get_image().get_data(), "Identical decoded source pixels and mipmaps required: " + label)


func _cache_checks(game: Control, loader: RefCounted, directory: String) -> void:
	var voice_directory := "games/bishoujo_afterlight/voice"
	DirAccess.make_dir_recursive_absolute(directory.path_join(voice_directory))
	var line_id := "episode.no_ordinary_post"
	for name: String in ["voices.json", "cast.json", "manifest.json"]:
		var loaded: Dictionary = game.content.content_loader.read_json(voice_directory.path_join(name))
		var value: Dictionary = loaded.value.duplicate(true)
		if name == "manifest.json": value.lines.en[line_id].path = "cache-check.mp3"
		var document := FileAccess.open(directory.path_join(voice_directory).path_join(name), FileAccess.WRITE)
		document.store_string(JSON.stringify(value))
		document.close()
	var source: PackedByteArray = game.content.voiceovers.en[line_id].data.duplicate()
	var recording_path := directory.path_join("cache-check.mp3")
	var recording := FileAccess.open(recording_path, FileAccess.WRITE)
	recording.store_buffer(source)
	recording.close()
	var sets := {}
	for language: String in ["en", "ko"]:
		sets[language] = game.content.content_loader.read_json("games/bishoujo_afterlight/text/" + language + ".json").value
	var policy := VOICE_POLICY.new()
	_expect(policy.load_project(game.beats, sets, loader).is_empty(), "An isolated recording cache fixture must configure.")
	var first := policy.resolve(line_id, "en")
	var repeated := policy.resolve(line_id, "en")
	_expect(first.status == "ready" and first.stream == repeated.stream, "Unchanged source/hash/revision must reuse the prepared stream.")
	source[source.size() - 1] = source[source.size() - 1] ^ 1
	recording = FileAccess.open(recording_path, FileAccess.WRITE)
	recording.store_buffer(source)
	recording.close()
	var changed := policy.resolve(line_id, "en")
	_expect(changed.status == "failed" and changed.get("reason") == "audio_hash_mismatch" and changed.stream == null, "A changed source file must invalidate an already cached stream before playback.")
	DirAccess.remove_absolute(recording_path)
	for name: String in ["voices.json", "cast.json", "manifest.json"]:
		DirAccess.remove_absolute(directory.path_join(voice_directory).path_join(name))
	for name: String in [voice_directory, "games/bishoujo_afterlight", "games"]:
		DirAccess.remove_absolute(directory.path_join(name))


func _expect(value: bool, message: String) -> void:
	if not value: _errors.append(message)
