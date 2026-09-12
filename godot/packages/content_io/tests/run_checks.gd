extends SceneTree

const CONTENT = preload("res://addons/content_io/local_content.gd")
var _errors: Array[String] = []
var _checks := 0


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var fixture := DirAccess.create_temp("presentation-content", true)
	var directory := fixture.get_current_dir()
	# macOS exposes its temporary directory through /var -> /private/var.
	# The loader intentionally requires a root without symlink ancestors.
	if OS.get_name() == "macOS" and directory.begins_with("/var/"):
		directory = "/private" + directory
		fixture = DirAccess.open(directory)
	var image := Image.create(8, 8, false, Image.FORMAT_RGBA8)
	image.fill(Color(0.8, 0.2, 0.1, 0.65))
	image.save_png(directory.path_join("actor.png"))
	image.save_webp(directory.path_join("actor.webp"), true)
	_write(directory.path_join("words.json"), "{\"hello\":\"Prepared local words\"}")
	_write(directory.path_join("invalid.json"), "{broken")
	_write(directory.path_join("not-video.ogv"), "not an Ogg file")
	var tone := AudioStreamWAV.new()
	tone.mix_rate = 8000
	tone.format = AudioStreamWAV.FORMAT_16_BITS
	var pcm := PackedByteArray()
	pcm.resize(1600)
	for index in 800: pcm.encode_s16(index * 2, int(sin(TAU * 440.0 * index / 8000.0) * 1200.0))
	tone.data = pcm
	tone.save_to_wav(directory.path_join("tone.wav"))
	var loader := CONTENT.new()
	_expect(loader.configure(directory, "files").is_empty(), "A real local directory must configure.")
	_expect(loader.read_json("words.json").value == {"hello": "Prepared local words"}, "JSON must come from the selected root.")
	_expect(not loader.read_json("invalid.json").errors.is_empty(), "Malformed JSON must fail.")
	_expect(not loader.read_json("missing.json").errors.is_empty(), "Missing JSON must fail.")
	for path: String in ["", "../words.json", "a/../words.json", "/etc/hosts", "res://words.json", "https://example.invalid/words.json", "a\\words.json", "./words.json", "a//words.json", "words.json/"]:
		_expect(not loader.resolve(path).errors.is_empty(), "Unsafe/noncanonical binding must fail: " + path)
	var expected := FileAccess.get_sha256(directory.path_join("actor.png"))
	_expect(loader.read_bytes("actor.png", expected).errors.is_empty(), "Any supplied source digest must be checked against the admitted bytes.")
	var refused: Dictionary = loader.read_bytes("actor.png", "0".repeat(64))
	_expect(not refused.errors.is_empty() and refused.bytes.is_empty(), "A digest mismatch must return no bytes.")
	_expect(not loader.read_bytes("actor.png", "INVALID").errors.is_empty(), "Malformed generic digests must fail.")
	_expect(loader.load_image("actor.png").resource is Image, "CPU image decoding must be independently usable.")
	var png: Dictionary = loader.load_texture("actor.png", true)
	_expect(png.errors.is_empty() and png.resource.get_image().has_mipmaps(), "Raw PNG decoding must support explicit mipmaps.")
	var webp: Dictionary = loader.load_texture("actor.webp")
	_expect(webp.errors.is_empty() and webp.resource.get_size() == Vector2(8, 8), "Prepared WebP must not require a PNG catalog convention.")
	var audio: Dictionary = loader.load_audio("tone.wav", FileAccess.get_sha256(directory.path_join("tone.wav")))
	_expect(audio.errors.is_empty() and absf(audio.resource.get_length() - 0.1) < 0.001, "Raw WAV must decode with verified source bytes.")
	_expect(not loader.load_audio("tone.wav", "0".repeat(64)).errors.is_empty(), "Wrong source hash must fail before activation.")
	_expect(not loader.load_audio("tone.wav", "invalid").errors.is_empty(), "Malformed expected hashes must fail.")
	_expect(not loader.load_video("not-video.ogv").errors.is_empty(), "A non-Ogg video must fail before playback.")
	_expect(not loader.load_texture("words.json").errors.is_empty(), "Media loading must reject unrelated resource formats.")
	var previous := loader.get_settings()
	_expect(not loader.configure(directory.path_join("absent"), "files").is_empty() and loader.get_settings() == previous, "Failed configuration must preserve the existing root.")
	_expect(not loader.configure(directory, "network").is_empty() and loader.get_settings() == previous, "Unknown backend must not mutate configuration.")
	var second := CONTENT.new()
	_expect(second.get_settings().root == "res://" and loader.get_settings().root == directory, "Loader instances must own separate roots.")
	var link_result := fixture.create_link(directory.path_join("actor.png"), directory.path_join("linked.png"))
	_expect(link_result == OK, "The fixture must create its own file symlink.")
	if link_result == OK:
		_expect(not loader.resolve("linked.png").errors.is_empty(), "A linked file must not bypass the configured root.")
	var nested := directory.path_join("nested")
	DirAccess.make_dir_absolute(nested)
	_write(nested.path_join("inside.json"), "{}")
	link_result = fixture.create_link(nested, directory.path_join("linked_directory"))
	_expect(link_result == OK, "The fixture must create its own directory symlink.")
	if link_result == OK:
		_expect(not loader.resolve("linked_directory/inside.json").errors.is_empty(), "An intermediate linked directory must be rejected.")
		_expect(not second.configure(directory.path_join("linked_directory"), "files").is_empty(), "A linked root must be rejected.")
	# Remove only this run's authored temporary fixture.
	for file: String in ["actor.png", "actor.webp", "words.json", "invalid.json", "not-video.ogv", "tone.wav", "linked.png", "linked_directory", "nested/inside.json", "nested"]:
		DirAccess.remove_absolute(directory.path_join(file))
	DirAccess.remove_absolute(directory)
	for issue: String in _errors: printerr("FAIL Local Content: " + issue)
	if _errors.is_empty(): print("content_io: %d checks passed" % _checks)
	quit(0 if _errors.is_empty() else 1)


func _expect(value: bool, message: String) -> void:
	_checks += 1
	if not value: _errors.append(message)


func _write(path: String, value: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(value)
