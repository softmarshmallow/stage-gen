class_name CaseStore
extends RefCounted

## Where a stopped case is kept, and where its ending goes.
##
## `genres/case/save.gd` decides what a save *is*; this decides where it lives.
## The browser keeps both in `localStorage` under `stage_gen.case_save.<tag>` and
## `stage_gen.case_result.<tag>`; a host keeps them in `user://`, which is the
## one directory a Godot game may write to and the only place in this project
## that is not a run directory.
##
## A save is written on every statement and every click, so writing is cheap and
## silent, and a save that will not parse is not an error a player can act on —
## they are offered a fresh case instead of a Continue that opens on nothing.

const SAVE_DIR := "user://case_saves"


static func save_path(tag: String) -> String:
	return "%s/%s.json" % [SAVE_DIR, _safe(tag)]


static func result_path(tag: String) -> String:
	return "%s/%s.result.json" % [SAVE_DIR, _safe(tag)]


## The save waiting for this case, or null.
static func read(tag: String) -> Variant:
	var path := save_path(tag)
	if not FileAccess.file_exists(path):
		return null
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not (parsed is Dictionary):
		push_warning("case store: %s will not parse; offering a fresh case" % path)
		return null
	var save: Dictionary = parsed
	# JSON has one array type, and the runtime hands `facts` around as a packed
	# one. Converting here keeps the difference at the boundary that owns it.
	save["facts"] = _strings(save.get("facts"))
	return save


static func write(tag: String, save: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(SAVE_DIR)
	var file := FileAccess.open(save_path(tag), FileAccess.WRITE)
	if file == null:
		push_warning("case store: cannot write %s" % save_path(tag))
		return
	file.store_string(JSON.stringify(save))
	file.close()


static func clear(tag: String) -> void:
	var path := save_path(tag)
	if FileAccess.file_exists(path):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(path))


## What the player carried out, kept after the save is cleared: the case's own
## output, and what the next case would open on.
static func write_result(tag: String, result: Dictionary) -> void:
	DirAccess.make_dir_recursive_absolute(SAVE_DIR)
	var file := FileAccess.open(result_path(tag), FileAccess.WRITE)
	if file == null:
		return
	file.store_string(JSON.stringify(result))
	file.close()


## The moment a save is stamped with. The one field in a save that is not a
## function of the game, which is why the runtime takes it rather than reads it.
static func now() -> String:
	return Time.get_datetime_string_from_system(true)


static func _strings(value: Variant) -> PackedStringArray:
	var made := PackedStringArray()
	if value is PackedStringArray:
		return value
	if value is Array:
		for entry: Variant in (value as Array):
			made.append(String(entry))
	return made


## A run tag is `[A-Za-z0-9][A-Za-z0-9._-]{0,127}` by contract, but a save path
## is a filesystem path and a document is not trusted to have been checked.
const SAFE_GLYPHS := "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"


static func _safe(tag: String) -> String:
	var made := ""
	for index in tag.length():
		var glyph := tag[index]
		made += glyph if SAFE_GLYPHS.contains(glyph) else "_"
	return made if made != "" else "case"
