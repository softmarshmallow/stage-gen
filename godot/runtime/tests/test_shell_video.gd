## The clip shot, headless: what the manifest says, and whether the engine will open it.
##
## The picture is the user's call and is proved by playing the run in a window. What is
## proved here is the seam a clip crosses that a still never does — a run-directory file
## in a container the engine has to be handed rather than asked to import, and a shot the
## host must branch on rather than assume is a texture.
##
## A package with no clip shot skips: the family is optional and a run without one is not
## a failure.

func run(h: TestHarness) -> void:
	var pkg: HostRunDir = h.package()
	if not h.assert_true(pkg != null, "the run package opened"):
		return
	var shell: Dictionary = pkg.manifest.get("shell", {})
	if shell.is_empty():
		# A run with no shell is not a failure — but it is not silence either,
		# and `run` still has to reach its end or the runner calls it a crash.
		h.assert_true(true, "this run publishes no shell, so there is no clip to open")
		h.done()
		return
	var opening: Dictionary = shell.get("opening", {})
	var clips: Array = []
	for entry: Variant in opening.get("shots", []):
		var shot: Dictionary = entry
		var plate: Dictionary = shot.get("plate", {})
		if String(plate.get("mode", "still")) == "clip":
			clips.append(plate)
	if clips.is_empty():
		h.assert_true(true, "this run's opening is stills, so there is no clip to open")
		h.done()
		return

	_declared(h, opening, clips)
	_opens(h, pkg, clips)
	_optional_strings(h, opening)


## An absent optional field is published as null, not omitted.
##
## `String(null)` is an invalid call that aborts its caller mid-function, and
## `.get(key, default)` does not save you when the key is there and holds null. A
## wordless opening — every shot carrying no card — is exactly that shape, and it broke
## the shot transition after the clip had already been built and played, so the picture
## looked right while shots piled up behind it.
	h.done()
func _optional_strings(h: TestHarness, opening: Dictionary) -> void:
	for entry: Variant in opening.get("shots", []):
		var shot: Dictionary = entry
		h.assert_true(
			shot.has("card"),
			"a shot publishes its card key even when it carries no card: %s" % shot.get("shot_id")
		)
		var card: Variant = shot.get("card")
		h.assert_true(
			card == null or typeof(card) == TYPE_STRING,
			"a card is a string or null, and the host has to read both"
		)


## What a host reads before it decides how to draw a shot.
func _declared(h: TestHarness, opening: Dictionary, clips: Array) -> void:
	h.assert_true(
		opening.has("ending"),
		"the opening declares how it ends, so the host does not invent a transition"
	)
	for entry: Variant in clips:
		var plate: Dictionary = entry
		var asset := String(plate.get("asset", ""))
		h.assert_true(asset.ends_with(".ogv"), "a clip names the container the engine plays: %s" % asset)
		h.assert_false(
			asset.ends_with(".mp4"),
			"the route's own response is never bound; the host cannot open it"
		)
		var canvas: Dictionary = plate.get("canvas", {})
		var width := int(canvas.get("width", 0))
		var height := int(canvas.get("height", 0))
		h.assert_true(width > 0 and height > 0, "a clip publishes the canvas it fills")
		# 16:9 to a rounding error. `VideoStreamPlayer.expand` has no cover mode, so the
		# card band published against the still canvas only lands correctly over a clip
		# because both are the same shape.
		h.assert_near(float(width) / float(height), 16.0 / 9.0, 0.005, "a clip is 16:9")
		h.assert_true(
			float(plate.get("duration_seconds", 0.0)) > 0.0,
			"a clip publishes the length it was measured at"
		)


## The seam itself: an unimported file, outside the project, handed to the engine.
func _opens(h: TestHarness, pkg: HostRunDir, clips: Array) -> void:
	for entry: Variant in clips:
		var plate: Dictionary = entry
		var ref := String(plate.get("asset", ""))
		var stream := pkg.video(ref)
		if not h.assert_true(stream != null, "the run's clip opened as a Theora stream: %s" % ref):
			continue
		h.assert_true(stream.file != "", "the stream points at a filesystem path, not a res:// id")
		h.assert_true(
			FileAccess.file_exists(stream.file),
			"the path the stream carries is a file that exists"
		)
		# Cached like every other reader, so a preload pass and a shot share one handle.
		h.assert_true(pkg.video(ref) == stream, "a clip is opened once and reused")
