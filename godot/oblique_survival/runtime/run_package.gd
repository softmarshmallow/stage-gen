class_name RunPackage
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

## The one manifest this host reads: the promoted recipe's, emitted by runs
## under `out/`. The spike's `oblique_survival_v0_manifest` was accepted while
## the recipe was being promoted and is gone; a run that still carries it is
## refused by name rather than half-read.
const MANIFEST_KIND := "oblique-survival-manifest-v1"
## The version of that contract. One document, one identity: a manifest that
## names the kind but not this version is a different document.
const MANIFEST_SCHEMA_VERSION := 1
const LAYOUT_REF := "package/world/layout.json"
const MOTION_HINTS := ["sway_top", "bob", "flicker", "none"]
const HIT_REACTIONS := ["shake", "none"]
## `assertManifest` reports only the first eight problems (viewer index.html:227).
const MAX_PROBLEMS := 8

var run_dir: String = ""
var manifest: Dictionary = {}
## `package/world/layout.json`, which the manifest also embeds verbatim.
var layout: Dictionary = {}

var _images: Dictionary = {}
var _textures: Dictionary = {}
var _audio: Dictionary = {}

## Open a run directory. Returns null (after pushing an error) when the
## manifest is missing, unreadable, or refused.
static func open(dir: String) -> RunPackage:
	var pkg := RunPackage.new()
	pkg.run_dir = dir.rstrip("/")
	var manifest_path := pkg.run_dir + "/manifest.json"
	var parsed: Variant = _read_json(manifest_path)
	if not (parsed is Dictionary):
		push_error("run package: no readable manifest at %s" % manifest_path)
		return null
	pkg.manifest = parsed
	var problems := check_manifest(pkg.manifest)
	if not problems.is_empty():
		push_error("manifest refused:\n  %s" % "\n  ".join(problems))
		return null
	var layout_path := pkg.path(LAYOUT_REF)
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

## The refusals of the viewer's `assertManifest` (index.html:200-228), in order.
static func check_manifest(m: Dictionary) -> PackedStringArray:
	var problems := PackedStringArray()
	if m.get("kind", "") != MANIFEST_KIND:
		problems.append("kind %s is not %s" % [m.get("kind", ""), MANIFEST_KIND])
	elif int(m.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
		problems.append("schema_version %s is not %d" % [m.get("schema_version", 0), MANIFEST_SCHEMA_VERSION])
	var scale: Dictionary = m.get("scale", {})
	if not _truthy(scale.get("player_height_meters")):
		problems.append("scale.player_height_meters missing")
	var ground: Dictionary = m.get("ground", {})
	if not _truthy(ground.get("size_meters")):
		problems.append("ground.size_meters missing")
	for id: String in m.get("actors", {}).keys():
		var actor: Dictionary = m["actors"][id]
		for state: String in actor.get("states", {}).keys():
			var spec: Dictionary = actor["states"][state]
			if not _truthy(spec.get("px_per_meter")):
				problems.append("actors.%s.%s.px_per_meter missing" % [id, state])
			if not _truthy(spec.get("columns")):
				problems.append("actors.%s.%s.columns missing" % [id, state])
			var rows: int = int(spec.get("rows", 0)) if _truthy(spec.get("rows")) else 1
			var cells: int = int(spec.get("columns", 0)) * rows
			for index: int in spec.get("canonical_frame_indices", []):
				if index < 0 or index >= cells:
					problems.append("actors.%s.%s frame %d out of range" % [id, state, index])
			if spec.get("mode", "") != "hold" and not _truthy(spec.get("fps")):
				problems.append("actors.%s.%s.fps missing" % [id, state])
	for id: String in m.get("props", {}).keys():
		var prop: Dictionary = m["props"][id]
		for state: String in prop.get("states", {}).keys():
			var spec: Dictionary = prop["states"][state]
			if not _truthy(spec.get("px_per_meter")):
				problems.append("props.%s.%s.px_per_meter missing" % [id, state])
			var contact: Variant = spec.get("ground_contact_y_normalized")
			if not (contact is float or contact is int):
				problems.append("props.%s.%s.ground_contact_y_normalized missing" % [id, state])
		if not MOTION_HINTS.has(prop.get("motion_hint")):
			problems.append("props.%s.motion_hint %s is not a known hint" % [id, prop.get("motion_hint")])
		if not HIT_REACTIONS.has(prop.get("hit_reaction")):
			problems.append("props.%s.hit_reaction %s is not a known reaction" % [id, prop.get("hit_reaction")])
	if problems.size() > MAX_PROBLEMS:
		problems = problems.slice(0, MAX_PROBLEMS)
	return problems

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

static func _read_json(absolute: String) -> Variant:
	if not FileAccess.file_exists(absolute):
		return null
	var text := FileAccess.get_file_as_string(absolute)
	if text == "":
		return null
	return JSON.parse_string(text)

## JavaScript truthiness for the numbers `assertManifest` tests: a missing key,
## null, and 0 all fail.
static func _truthy(value: Variant) -> bool:
	if value == null:
		return false
	if value is float or value is int:
		return value != 0
	if value is String:
		return value != ""
	return true
