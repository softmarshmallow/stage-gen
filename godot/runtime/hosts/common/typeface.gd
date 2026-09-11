class_name HostTypeface
extends RefCounted

## The face a run is set in, resolved from what the package published.
##
## [0063](../../../docs/decisions/0063-a-typeface-is-a-package-input.md) rules
## that a typeface is an authored package input rather than host furniture: a
## template-owned face would make every game this repository generates speak in
## one voice, which is the opposite of what a per-game art direction is for. So a
## host resolves a face below the run root and never carries one.
##
## [0017](../../../docs/decisions/0017-the-numeral-face-is-a-typeface-constraint.md)
## is why there are two roles rather than one. A stroke eats a glyph's counters
## from both sides, and the running-text face's close up long before a double
## outline reads as arcade weight — so the numbers a fight is read by want a face
## drawn with open counters and thick strokes, and the words want a text face.
##
## A package that declares neither is not an error. The host draws in whatever the
## engine defaults to **and says which role was missing**, because a run set in the
## first fallback the machine happens to have is precisely the defect 0017 found by
## accident, and finding it twice by accident would be a choice.

const ROLE_TEXT := "typeface"
const ROLE_NUMERAL := "numeral_typeface"


## The two faces a platformer-shaped run asks for, as `{text, numeral}`.
##
## Either may be null. `numeral` falls back to `text` before it falls back to
## nothing, because a package that published one good face should set its numbers
## in it rather than in the machine's.
static func of(package: HostRunDir, block: Dictionary, label: String) -> Dictionary:
	var text := _load(package, block, ROLE_TEXT, label)
	var numeral := _load(package, block, ROLE_NUMERAL, label)
	return {"text": text, "numeral": numeral if numeral != null else text}


## A theme that sets every string drawn under it in `face`, or null.
##
## One theme on the host root rather than an override per label: a face is a
## property of the run, and applying it thirty times is thirty chances to miss one.
static func theme_of(face: FontFile) -> Theme:
	if face == null:
		return null
	var made := Theme.new()
	made.default_font = face
	return made


static func _load(
	package: HostRunDir, block: Dictionary, role: String, label: String
) -> FontFile:
	var face: Dictionary = block.get(role, {})
	var ref := str(face.get("asset", ""))
	if ref.is_empty():
		# Said once, at load, rather than never: a run set in the machine's own
		# fallback looks deliberate, and the only way to tell is to be told.
		push_warning(
			"%s: this package declares no `%s`, so its text is set in the engine's default face"
				% [label, role]
		)
		return null
	var absolute := package.path(ref)
	if absolute.is_empty() or not FileAccess.file_exists(absolute):
		push_warning(
			"%s: the manifest binds a `%s` the run does not carry: %s" % [label, role, ref]
		)
		return null
	var file := FontFile.new()
	var error := file.load_dynamic_font(absolute)
	if error != OK:
		push_warning("%s: the published `%s` did not load (%d): %s" % [label, role, error, ref])
		return null
	return file
