class_name HostRunDir
extends RefCounted

## A run directory, opened once and read lazily.
##
## The host owns no media: everything it draws and plays comes from a run the
## pipeline emitted (`manifest.json` beside a `package/` tree). This is the one
## place that touches that directory, so every path is checked here.
##
## Port note: the web viewer fetches `manifest.json` and lets the browser cache
## the rest; here the manifest and the layout are read eagerly (they are the
## contract) and images and audio are cached on first use.
##
## **Genre-neutral, and that is the whole point.** Opening a root, confining a
## reference, reading JSON and decoding media are the same in every genre; what
## a document *is* is not. So a caller hands in the checker for its own document
## and the reference its own layout sits behind, and this file names no manifest
## kind. It used to name survival's, which meant the second host to use it would
## have inherited the first one's contract.

## What a run's document is called when a genre does not say.
const DEFAULT_DOCUMENT_REF := "manifest.json"

var run_dir: String = ""
## The run's own document, whatever it is called. A survival or platformer run
## publishes `manifest.json`; a dialogue-scene run publishes `bundle.json` and a
## case publishes `case.json`. What the file is *named* is as much the genre's
## business as what is in it, so the caller says.
var manifest: Dictionary = {}
## `package/world/layout.json`, which the manifest also embeds verbatim.
var layout: Dictionary = {}

var _images: Dictionary = {}
var _textures: Dictionary = {}
var _audio: Dictionary = {}
var _videos: Dictionary = {}

## Open a run directory. Returns null (after pushing an error) when the
## manifest is missing, unreadable, or refused.
##
## `checker` is the genre's document contract: it takes the parsed manifest and
## answers with the problems, empty for none. Omitting it opens any JSON
## manifest, which is what a caller that parses the document itself wants.
##
## `layout_ref` is a second document a genre keeps beside the manifest; a genre
## with none omits it.
##
## `document_ref` names the run's own document. It defaults to `manifest.json`,
## which is what three of the five genres publish; a dialogue scene publishes
## `bundle.json` and a case publishes `case.json`, and neither has a manifest at
## all.
static func open(
	dir: String,
	checker: Callable = Callable(),
	layout_ref: String = "",
	document_ref: String = DEFAULT_DOCUMENT_REF
) -> HostRunDir:
	var pkg := HostRunDir.new()
	pkg.run_dir = dir.rstrip("/")
	var manifest_path := pkg.run_dir + "/" + document_ref
	var parsed: Variant = _read_json(manifest_path)
	if not (parsed is Dictionary):
		push_error("run package: no readable manifest at %s" % manifest_path)
		return null
	pkg.manifest = parsed
	if checker.is_valid():
		var problems: PackedStringArray = checker.call(pkg.manifest)
		if not problems.is_empty():
			push_error("manifest refused:\n  %s" % "\n  ".join(problems))
			return null
	if layout_ref.is_empty():
		return pkg
	var layout_path := pkg.path(layout_ref)
	var layout_parsed: Variant = _read_json(layout_path)
	if layout_parsed is Dictionary:
		pkg.layout = layout_parsed
	elif pkg.manifest.has("layout"):
		# A run that ships the layout only inside the manifest still opens.
		push_warning("run package: %s unreadable; using manifest.layout" % layout_path)
		pkg.layout = pkg.manifest["layout"]
	else:
		push_error("run package: no layout at %s and none in the manifest" % layout_path)
		return null
	return pkg

## An absolute path for a package-relative reference. Refuses anything that
## would leave the run directory; returns "" and pushes an error.
func path(ref: String) -> String:
	if ref == "":
		return ""
	if ref.begins_with("/") or ref.begins_with("res://") or ref.begins_with("user://") or ref.contains(":\\"):
		push_error("run package: absolute reference refused: %s" % ref)
		return ""
	if ref.split("/").has(".."):
		push_error("run package: traversing reference refused: %s" % ref)
		return ""
	return run_dir + "/" + ref

## The decoded image behind a package reference, cached. Null when missing.
func image(ref: String) -> Image:
	if _images.has(ref):
		return _images[ref]
	var absolute := path(ref)
	var loaded: Image = null
	if absolute != "":
		loaded = Image.load_from_file(absolute)
		if loaded == null:
			push_error("run package: cannot read image %s" % absolute)
	_images[ref] = loaded
	return loaded

## A texture for a package reference, cached. Colour images get mipmaps; data
## plates (splat, biomes, masks) must pass `mipmaps = false` and stay linear.
func texture(ref: String, mipmaps: bool = true) -> ImageTexture:
	var key := ref + ("#mip" if mipmaps else "#data")
	if _textures.has(key):
		return _textures[key]
	var source := image(ref)
	var made: ImageTexture = null
	if source != null:
		var copy := Image.new()
		copy.copy_from(source)
		if mipmaps and not copy.has_mipmaps():
			copy.generate_mipmaps()
		made = ImageTexture.create_from_image(copy)
	_textures[key] = made
	return made

## A texture cropped to its subject's alpha bounding box, cached.
##
## A catalogue sprite is painted on a canvas larger than the thing on it, and a
## calibration is measured against the *subject* rather than against the canvas
## it floats in. So a caller that sizes by the ruler and places by an edge has
## to be handed the subject: drawn untrimmed, a prop stands on its own padding
## instead of on the ground, and a coin fitted into a readable cell is fitted by
## the width of its empty margins.
##
## Alpha zero marks the exterior, which is the same rule the browser's
## `extractCellsBbox` used and what the published alpha policy guarantees. A
## blank or unreadable subject keeps the whole canvas rather than collapsing to
## nothing.
func trimmed_texture(ref: String) -> ImageTexture:
	var key := ref + "#trim"
	if _textures.has(key):
		return _textures[key]
	var source := image(ref)
	var made: ImageTexture = null
	if source != null:
		var copy := Image.new()
		copy.copy_from(source)
		if copy.get_format() != Image.FORMAT_RGBA8:
			copy.convert(Image.FORMAT_RGBA8)
		var used := copy.get_used_rect()
		if used.size.x > 1 and used.size.y > 1:
			copy = copy.get_region(used)
		copy.generate_mipmaps()
		made = ImageTexture.create_from_image(copy)
	_textures[key] = made
	return made

## An mp3 clip from the package, cached. Null when missing.
func audio(ref: String) -> AudioStreamMP3:
	if _audio.has(ref):
		return _audio[ref]
	var absolute := path(ref)
	var stream: AudioStreamMP3 = null
	if absolute != "" and FileAccess.file_exists(absolute):
		var bytes := FileAccess.get_file_as_bytes(absolute)
		if bytes.is_empty():
			push_error("run package: empty audio %s" % absolute)
		else:
			stream = AudioStreamMP3.new()
			stream.data = bytes
	else:
		push_error("run package: cannot read audio %s" % absolute)
	_audio[ref] = stream
	return stream

## An Ogg Theora clip from the package, cached. Null when missing.
##
## The third reader of run-directory media, after textures and audio, and the third to
## reach past `ResourceLoader`: a run's files are written long after the project was
## exported, so nothing in one is imported. `VideoStreamTheora` takes a plain filesystem
## path in `file`, which is measured rather than assumed — `tools/probe_video.gd` plays
## one and reads the clock back. Theora is the only video codec the engine carries.
func video(ref: String) -> VideoStreamTheora:
	if _videos.has(ref):
		return _videos[ref]
	var absolute := path(ref)
	var stream: VideoStreamTheora = null
	if absolute != "" and FileAccess.file_exists(absolute):
		stream = VideoStreamTheora.new()
		stream.file = absolute
	else:
		push_error("run package: cannot read video %s" % absolute)
	_videos[ref] = stream
	return stream

static func _read_json(absolute: String) -> Variant:
	if not FileAccess.file_exists(absolute):
		return null
	var text := FileAccess.get_file_as_string(absolute)
	if text == "":
		return null
	return JSON.parse_string(text)

## JavaScript truthiness for the numbers `assertManifest` tests: a missing key,
## null, and 0 all fail.
