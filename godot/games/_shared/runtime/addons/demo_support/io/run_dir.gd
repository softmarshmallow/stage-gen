class_name HostRunDir
extends RefCounted

## Game-owned run-document adapter and decoded-media caches.
## Content I/O owns confined file access and decoding; this adapter owns the
## selected document, layout fallback, MP3/Theora choices and alpha trimming.
const Content = preload("res://addons/content_io/local_content.gd")

var _content := Content.new()
var _configured_root := ""

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
	if not pkg._configure_content(): return null
	var parsed: Variant = pkg._read_json(document_ref)
	if not (parsed is Dictionary):
		push_error("run package: no readable document %s" % document_ref)
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
	if layout_path.is_empty(): return null
	var layout_parsed: Variant = pkg._read_json(layout_ref)
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
	if ref.is_empty() or not _configure_content(): return ""
	var result: Dictionary = _content.resolve(ref, false)
	_report(result.errors)
	return result.path


## The decoded image behind a package reference, cached. Null when missing.
func image(ref: String) -> Image:
	if _images.has(ref): return _images[ref]
	if not _configure_content(): return null
	var result: Dictionary = _content.load_image(ref)
	_report(result.errors)
	_images[ref] = result.resource
	return result.resource

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
	if _audio.has(ref): return _audio[ref]
	if not _configure_content(): return null
	var result: Dictionary = _content.load_audio(ref)
	_report(result.errors)
	var stream := result.resource as AudioStreamMP3
	_audio[ref] = stream
	return stream


## An Ogg Theora clip from the package, cached. Playback remains a host check.
func video(ref: String) -> VideoStreamTheora:
	if _videos.has(ref): return _videos[ref]
	if not _configure_content(): return null
	var result: Dictionary = _content.load_video(ref)
	_report(result.errors)
	var stream := result.resource as VideoStreamTheora
	_videos[ref] = stream
	return stream


func _read_json(ref: String) -> Variant:
	if not _configure_content(): return null
	var result: Dictionary = _content.read_json(ref)
	_report(result.errors)
	return result.value


func _configure_content() -> bool:
	if _configured_root == run_dir and not run_dir.is_empty(): return true
	var root := run_dir
	var backend := "resources" if root.begins_with("res://") else "files"
	if root.begins_with("user://"):
		root = ProjectSettings.globalize_path(root)
	elif backend == "files" and not root.is_absolute_path():
		root = ProjectSettings.globalize_path("res://".path_join(root)).simplify_path()
	var errors: Array[String] = _content.configure(root, backend)
	_report(errors)
	if not errors.is_empty(): return false
	_configured_root = run_dir
	return true


static func _report(errors: Array) -> void:
	for error: String in errors: push_error("run package: " + error)
